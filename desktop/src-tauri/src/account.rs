// Account/registration + telemetry plumbing for AI Second Brain Desktop.
//
// Talks to the AI Circle Supabase project's edge functions (asb-register / asb-status /
// asb-telemetry) to register an install, poll WhatsApp verification, and ship anonymous usage
// telemetry. Persisted as `account.json` in the Tauri app-data dir, same disk-backed-JSON-store
// pattern as `app::SessionStore`: load once at startup, rewrite the whole file on every mutation,
// never panic on a missing/corrupt file.
//
// Network calls never block the UI thread: every HTTP round trip is `async` with a 10s timeout,
// and failures degrade to a locally-persisted, structured result rather than propagating an error
// that would surface as a raw JS exception.

use serde::{Deserialize, Serialize};

const SUPABASE_URL: &str = "https://ymvtlldxjxmcwrdvewdz.supabase.co";
const SUPABASE_ANON_KEY: &str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InltdnRsbGR4anhtY3dyZHZld2R6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk1NDU3NzYsImV4cCI6MjA5NTEyMTc3Nn0.ZoVk4nWDglzWHY0ED6ULs0CkcHBgfJru4FnLxEyKaQg";

const HTTP_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(10);
const MAX_PENDING_EVENTS: usize = 500;

fn functions_url(fn_name: &str) -> String {
    format!("{SUPABASE_URL}/functions/v1/{fn_name}")
}

fn http_client() -> reqwest::Client {
    // A fresh client per call is cheap at this call frequency (a handful of calls a session plus
    // one flush every 5 minutes) and avoids threading a shared client through Tauri state.
    reqwest::Client::builder()
        .timeout(HTTP_TIMEOUT)
        .build()
        .unwrap_or_else(|_| reqwest::Client::new())
}

fn current_os_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else {
        "linux"
    }
}

fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Profile {
    pub name: String,
    pub email: String,
    pub whatsapp: String,
    pub profession: String,
    pub seniority: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Verification {
    pub code: String,
    pub wa_number: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TelemetryEvent {
    pub event: String,
    pub props: serde_json::Value,
    pub app_version: String,
    pub os: String,
    pub ts: u64,
}

/// The full persisted shape of `account.json`, and also what `get_account_status` hands back to
/// the frontend verbatim.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AccountState {
    pub install_id: String,
    #[serde(default)]
    pub profile: Option<Profile>,
    #[serde(default)]
    pub registered: bool,
    #[serde(default)]
    pub phone_verified: bool,
    #[serde(default)]
    pub verification: Option<Verification>,
    #[serde(default)]
    pub telemetry_opt_out: bool,
    #[serde(default)]
    pub pending_events: Vec<TelemetryEvent>,
}

impl AccountState {
    fn new_with_install_id() -> AccountState {
        AccountState {
            install_id: uuid::Uuid::new_v4().to_string(),
            profile: None,
            registered: false,
            phone_verified: false,
            verification: None,
            telemetry_opt_out: false,
            pending_events: Vec::new(),
        }
    }
}

/// JSON file store, same shape as `app::SessionStore`: missing/corrupt file loads as a fresh state
/// (with a newly minted `install_id`) rather than panicking; every mutation rewrites the file.
pub struct AccountStore {
    path: std::path::PathBuf,
    inner: std::sync::Mutex<AccountState>,
}

impl AccountStore {
    pub fn load(path: std::path::PathBuf) -> AccountStore {
        let state = std::fs::read_to_string(&path)
            .ok()
            .and_then(|raw| serde_json::from_str::<AccountState>(&raw).ok())
            .unwrap_or_else(AccountState::new_with_install_id);
        let store = AccountStore {
            path,
            inner: std::sync::Mutex::new(state),
        };
        // First-load-ever case: persist immediately so the freshly generated install_id survives
        // even if nothing else mutates the store before the app is closed.
        store.persist_locked();
        store
    }

    fn persist_locked(&self) {
        let state = self.inner.lock().unwrap();
        self.persist(&state);
    }

    fn persist(&self, state: &AccountState) {
        if let Ok(json) = serde_json::to_string_pretty(state) {
            if let Err(e) = std::fs::write(&self.path, json) {
                eprintln!("[ai-second-brain-desktop] failed to persist account.json: {e}");
            }
        }
    }

    pub fn snapshot(&self) -> AccountState {
        self.inner.lock().unwrap().clone()
    }

    pub fn install_id(&self) -> String {
        self.inner.lock().unwrap().install_id.clone()
    }

    fn mutate(&self, f: impl FnOnce(&mut AccountState)) -> AccountState {
        let mut state = self.inner.lock().unwrap();
        f(&mut state);
        self.persist(&state);
        state.clone()
    }

    pub fn set_profile(&self, profile: Profile) {
        self.mutate(|s| s.profile = Some(profile));
    }

    pub fn set_registered(&self, verification: Verification) {
        self.mutate(|s| {
            s.registered = true;
            s.verification = Some(verification);
        });
    }

    pub fn set_phone_verified(&self, verified: bool) {
        self.mutate(|s| s.phone_verified = verified);
    }

    pub fn set_telemetry_opt_out(&self, opt_out: bool) {
        self.mutate(|s| s.telemetry_opt_out = opt_out);
    }

    /// Enqueues an event unless telemetry is opted out. Caps the queue at `MAX_PENDING_EVENTS` by
    /// dropping the oldest entries first (FIFO), so the newest activity is always what survives.
    pub fn enqueue_event(&self, event: String, props: serde_json::Value) {
        self.mutate(|s| {
            if s.telemetry_opt_out {
                return;
            }
            s.pending_events.push(TelemetryEvent {
                event,
                props,
                app_version: env!("CARGO_PKG_VERSION").to_string(),
                os: current_os_name().to_string(),
                ts: now_ms(),
            });
            if s.pending_events.len() > MAX_PENDING_EVENTS {
                let excess = s.pending_events.len() - MAX_PENDING_EVENTS;
                s.pending_events.drain(0..excess);
            }
        });
    }

    fn take_pending_events(&self) -> Vec<TelemetryEvent> {
        self.inner.lock().unwrap().pending_events.clone()
    }

    fn clear_pending_events(&self, sent: usize) {
        self.mutate(|s| {
            // Drop exactly the events that were actually sent, in case more were enqueued
            // concurrently while the flush request was in flight.
            let remove = sent.min(s.pending_events.len());
            s.pending_events.drain(0..remove);
        });
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase", tag = "kind")]
pub enum RegisterOutcome {
    Registered {
        user_id: String,
        code: String,
        wa_number: String,
    },
    /// Structured, non-fatal outcome: the profile is saved locally (`registered` stays false) so
    /// registration can be retried later without the user re-typing anything.
    Offline {
        message: String,
    },
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct RegisterResponse {
    user_id: Option<String>,
    code: Option<String>,
    wa_number: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct StatusResponse {
    #[serde(default)]
    registered: bool,
    #[serde(default)]
    phone_verified: bool,
}

// ---- #[tauri::command] handlers ----

#[tauri::command]
pub async fn get_account_status(
    state: tauri::State<'_, AccountStore>,
) -> Result<AccountState, String> {
    Ok(state.snapshot())
}

#[tauri::command]
pub async fn register_account(
    state: tauri::State<'_, AccountStore>,
    profile: Profile,
) -> Result<RegisterOutcome, String> {
    let install_id = state.install_id();

    // Persist locally first: even if the network call below fails, the profile the user just
    // typed is never lost.
    state.set_profile(profile.clone());

    let body = serde_json::json!({
        "name": profile.name,
        "email": profile.email,
        "whatsapp": profile.whatsapp,
        "profession": profile.profession,
        "seniority": profile.seniority,
        "installId": install_id,
    });

    let result = http_client()
        .post(functions_url("asb-register"))
        .header("apikey", SUPABASE_ANON_KEY)
        .header("Authorization", format!("Bearer {SUPABASE_ANON_KEY}"))
        .json(&body)
        .send()
        .await;

    let response = match result {
        Ok(r) => r,
        Err(e) => {
            return Ok(RegisterOutcome::Offline {
                message: format!("Could not reach the registration server: {e}"),
            })
        }
    };

    if !response.status().is_success() {
        let status = response.status();
        let text = response.text().await.unwrap_or_default();
        return Ok(RegisterOutcome::Offline {
            message: format!("Registration failed ({status}): {text}"),
        });
    }

    let parsed = match response.json::<RegisterResponse>().await {
        Ok(p) => p,
        Err(e) => {
            return Ok(RegisterOutcome::Offline {
                message: format!("Registration server sent an unexpected response: {e}"),
            })
        }
    };

    let user_id = parsed.user_id.unwrap_or_default();
    let code = parsed.code.unwrap_or_default();
    let wa_number = parsed.wa_number.unwrap_or_default();

    state.set_registered(Verification {
        code: code.clone(),
        wa_number: wa_number.clone(),
    });

    Ok(RegisterOutcome::Registered {
        user_id,
        code,
        wa_number,
    })
}

#[tauri::command]
pub async fn poll_verification(state: tauri::State<'_, AccountStore>) -> Result<AccountState, String> {
    let install_id = state.install_id();
    let body = serde_json::json!({ "installId": install_id });

    let result = http_client()
        .post(functions_url("asb-status"))
        .header("apikey", SUPABASE_ANON_KEY)
        .header("Authorization", format!("Bearer {SUPABASE_ANON_KEY}"))
        .json(&body)
        .send()
        .await;

    // Network/parse failure: not an error the UI needs to surface, just leave local state as-is
    // and let the next poll try again.
    if let Ok(response) = result {
        if response.status().is_success() {
            if let Ok(parsed) = response.json::<StatusResponse>().await {
                state.set_phone_verified(parsed.phone_verified);
                if parsed.registered {
                    // Server-side confirmation without a local `verification` record (e.g. a
                    // reinstall): flip registered on without clobbering an existing code/waNumber.
                    state.mutate(|s| s.registered = true);
                }
            }
        }
    }

    Ok(state.snapshot())
}

#[tauri::command]
pub async fn set_telemetry_opt_out(
    state: tauri::State<'_, AccountStore>,
    opt_out: bool,
) -> Result<(), String> {
    state.set_telemetry_opt_out(opt_out);
    Ok(())
}

#[tauri::command]
pub async fn record_event(
    state: tauri::State<'_, AccountStore>,
    event: String,
    props: Option<serde_json::Value>,
) -> Result<(), String> {
    state.enqueue_event(event, props.unwrap_or(serde_json::Value::Null));
    Ok(())
}

/// Records an event from Rust-side call sites (session hooks in `app.rs`) without going through
/// the `#[tauri::command]` IPC boundary.
pub fn record_event_internal(app: &tauri::AppHandle, event: &str, props: serde_json::Value) {
    use tauri::Manager;
    let state = app.state::<AccountStore>();
    state.enqueue_event(event.to_string(), props);
}

#[tauri::command]
pub async fn flush_events(state: tauri::State<'_, AccountStore>) -> Result<(), String> {
    flush_events_internal(&state).await;
    Ok(())
}

/// Shared by the `flush_events` command and the periodic background task. Drops the queued
/// events on success; keeps them (for the next attempt) on any network/HTTP failure.
pub async fn flush_events_internal(state: &AccountStore) {
    let events = state.take_pending_events();
    if events.is_empty() {
        return;
    }

    let install_id = state.install_id();
    let body = serde_json::json!({
        "installId": install_id,
        "events": events,
    });

    let result = http_client()
        .post(functions_url("asb-telemetry"))
        .header("apikey", SUPABASE_ANON_KEY)
        .header("Authorization", format!("Bearer {SUPABASE_ANON_KEY}"))
        .json(&body)
        .send()
        .await;

    match result {
        Ok(response) if response.status().is_success() => {
            state.clear_pending_events(events.len());
        }
        _ => {
            // Keep the events queued (capped at MAX_PENDING_EVENTS by enqueue_event) for the next
            // periodic flush or the next explicit flush_events call.
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_store(name: &str) -> AccountStore {
        let mut path = std::env::temp_dir();
        path.push(format!(
            "asb_account_test_{name}_{}.json",
            uuid::Uuid::new_v4()
        ));
        let _ = std::fs::remove_file(&path);
        AccountStore::load(path)
    }

    #[test]
    fn fresh_store_generates_and_persists_an_install_id() {
        let store = temp_store("fresh_install_id");
        let id1 = store.install_id();
        assert!(!id1.is_empty());
        // uuid v4 textual form is always 36 chars.
        assert_eq!(id1.len(), 36);

        // Reloading from the same path must see the SAME id (not regenerate).
        let path = store.path.clone();
        let reloaded = AccountStore::load(path);
        assert_eq!(reloaded.install_id(), id1);

        let _ = std::fs::remove_file(&store.path);
    }

    #[test]
    fn missing_file_does_not_panic_and_yields_default_state() {
        let store = temp_store("missing_file");
        let snap = store.snapshot();
        assert!(!snap.registered);
        assert!(!snap.phone_verified);
        assert!(!snap.telemetry_opt_out);
        assert!(snap.pending_events.is_empty());
        assert!(snap.profile.is_none());
        let _ = std::fs::remove_file(&store.path);
    }

    #[test]
    fn corrupt_file_falls_back_to_fresh_state_instead_of_panicking() {
        let mut path = std::env::temp_dir();
        path.push(format!("asb_account_test_corrupt_{}.json", uuid::Uuid::new_v4()));
        std::fs::write(&path, "{ this is not valid json").unwrap();

        let store = AccountStore::load(path.clone());
        assert!(!store.install_id().is_empty());

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn enqueue_event_respects_telemetry_opt_out() {
        let store = temp_store("opt_out");
        store.set_telemetry_opt_out(true);
        store.enqueue_event("app_open".to_string(), serde_json::Value::Null);
        assert!(store.snapshot().pending_events.is_empty());
        let _ = std::fs::remove_file(&store.path);
    }

    #[test]
    fn enqueue_event_records_when_not_opted_out() {
        let store = temp_store("records");
        store.enqueue_event(
            "session_start".to_string(),
            serde_json::json!({ "sessionId": "abc" }),
        );
        let snap = store.snapshot();
        assert_eq!(snap.pending_events.len(), 1);
        assert_eq!(snap.pending_events[0].event, "session_start");
        assert_eq!(snap.pending_events[0].os, current_os_name());
        let _ = std::fs::remove_file(&store.path);
    }

    #[test]
    fn pending_events_cap_at_500_dropping_oldest_first() {
        let store = temp_store("cap");
        for i in 0..510 {
            store.enqueue_event("e".to_string(), serde_json::json!({ "i": i }));
        }
        let snap = store.snapshot();
        assert_eq!(snap.pending_events.len(), MAX_PENDING_EVENTS);
        // The oldest 10 (i = 0..10) should have been dropped; the surviving window starts at i=10.
        assert_eq!(snap.pending_events[0].props["i"], 10);
        assert_eq!(
            snap.pending_events[MAX_PENDING_EVENTS - 1].props["i"],
            509
        );
        let _ = std::fs::remove_file(&store.path);
    }

    #[test]
    fn clear_pending_events_only_removes_the_sent_prefix() {
        let store = temp_store("clear_prefix");
        for i in 0..5 {
            store.enqueue_event("e".to_string(), serde_json::json!({ "i": i }));
        }
        // Simulate a flush that sent the first 3 events; 2 more may have queued concurrently.
        store.clear_pending_events(3);
        let snap = store.snapshot();
        assert_eq!(snap.pending_events.len(), 2);
        assert_eq!(snap.pending_events[0].props["i"], 3);
        let _ = std::fs::remove_file(&store.path);
    }

    #[test]
    fn set_registered_stores_verification_and_flips_flag() {
        let store = temp_store("set_registered");
        store.set_registered(Verification {
            code: "1234".to_string(),
            wa_number: "+62000".to_string(),
        });
        let snap = store.snapshot();
        assert!(snap.registered);
        assert_eq!(snap.verification.unwrap().code, "1234");
        let _ = std::fs::remove_file(&store.path);
    }
}
