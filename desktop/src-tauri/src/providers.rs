// Multi-provider support for AI Second Brain Desktop.
//
// The `claude` CLI talks to any Anthropic-compatible endpoint via three env vars:
// `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, and (optionally) `ANTHROPIC_MODEL`. This module
// owns the set of configured providers (built-in + user-added custom ones), persists them to
// `providers.json` in the Tauri app-data dir (same disk-backed-JSON-store pattern as
// `account::AccountStore` / `app::SessionStore`: load once, rewrite the whole file on every
// mutation, never panic on a missing/corrupt file), and builds the env-var overlay a session
// spawn needs for a non-default provider.
//
// HARD RULE: API keys are never logged. `ProviderConfig::masked()` is the only form that may
// cross the IPC boundary to the frontend; `Debug`/`Display` on anything holding a raw key is
// deliberately avoided (see the custom `Debug` impl further down and `provider_env_vars`, which
// returns a redacted-`Debug` wrapper).

use serde::{Deserialize, Serialize};

use crate::bridge::CommandNoWindowExt;

pub const KIND_CLAUDE: &str = "claude";
pub const KIND_GLM: &str = "glm";
pub const KIND_KIMI: &str = "kimi";
pub const KIND_CUSTOM: &str = "custom";

/// Sentinel prefix `upsert_provider` recognizes as "unchanged" — `list_providers` never returns
/// a raw key, so the frontend echoes back the masked value it was shown; without this guard a
/// no-op "save" from the settings screen would clobber the real key with `****ab12`.
const MASK_PREFIX: &str = "****";

fn default_true() -> bool {
    true
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProviderConfig {
    pub id: String,
    /// "claude" | "glm" | "kimi" | "custom" — a plain string (not an enum) so a future built-in
    /// or a user's `custom` provider never fails deserialization of an older `providers.json`.
    pub kind: String,
    pub label: String,
    #[serde(default)]
    pub base_url: Option<String>,
    #[serde(default)]
    pub api_key: Option<String>,
    #[serde(default)]
    pub model: Option<String>,
    #[serde(default)]
    pub supports_images: bool,
    #[serde(default = "default_true")]
    pub enabled: bool,
}

/// Hand-rolled so an incidental `{:?}`/`dbg!`/panic message on a `ProviderConfig` (or anything
/// containing one, e.g. `Vec<ProviderConfig>`) can never print a raw key — matches the module's
/// hard rule at the top of this file. Mirrors `EnvOverlay`'s redaction approach.
impl std::fmt::Debug for ProviderConfig {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ProviderConfig")
            .field("id", &self.id)
            .field("kind", &self.kind)
            .field("label", &self.label)
            .field("base_url", &self.base_url)
            .field("api_key", &mask_key(&self.api_key))
            .field("model", &self.model)
            .field("supports_images", &self.supports_images)
            .field("enabled", &self.enabled)
            .finish()
    }
}

impl ProviderConfig {
    /// Never send the raw key over IPC: replace it with `****` + last 4 chars (or `****` alone
    /// for anything shorter than that, still enough to show "a key is set").
    fn masked(&self) -> ProviderConfig {
        let mut m = self.clone();
        m.api_key = mask_key(&self.api_key);
        m
    }

    /// Wraps this config's masked form with an explicit `has_key` boolean computed from the
    /// *raw* (pre-mask) key, so the frontend never has to infer "is this provider connected"
    /// from the shape of the masked string.
    fn masked_with_has_key(&self) -> MaskedProviderConfig {
        let has_key = self.api_key.as_deref().map(|k| !k.is_empty()).unwrap_or(false);
        MaskedProviderConfig {
            config: self.masked(),
            has_key,
        }
    }
}

/// `list_providers`/`upsert_provider`'s frontend-facing shape: every `ProviderConfig` field
/// (flattened, so the JSON is indistinguishable from a plain `ProviderConfig` except for the
/// added key) plus `has_key` — an explicit boolean the frontend can branch on directly instead
/// of inferring connectedness from whether the masked `api_key` string happens to be truthy.
#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MaskedProviderConfig {
    #[serde(flatten)]
    pub config: ProviderConfig,
    pub has_key: bool,
}

fn mask_key(key: &Option<String>) -> Option<String> {
    key.as_ref().and_then(|k| {
        if k.is_empty() {
            None
        } else if k.len() <= 4 {
            Some(MASK_PREFIX.to_string())
        } else {
            Some(format!("{MASK_PREFIX}{}", &k[k.len() - 4..]))
        }
    })
}

fn is_masked_sentinel(key: &Option<String>) -> bool {
    key.as_deref()
        .map(|k| k.starts_with(MASK_PREFIX))
        .unwrap_or(false)
}

pub fn is_builtin_id(id: &str) -> bool {
    id == KIND_CLAUDE || id == KIND_GLM || id == KIND_KIMI
}

fn builtin_defaults() -> Vec<ProviderConfig> {
    vec![
        ProviderConfig {
            id: KIND_CLAUDE.to_string(),
            kind: KIND_CLAUDE.to_string(),
            label: "Claude (Anthropic)".to_string(),
            base_url: None,
            api_key: None,
            model: None,
            supports_images: true,
            enabled: true,
        },
        ProviderConfig {
            id: KIND_GLM.to_string(),
            kind: KIND_GLM.to_string(),
            label: "GLM (z.ai Coding Plan)".to_string(),
            base_url: Some("https://api.z.ai/api/anthropic".to_string()),
            api_key: None,
            model: Some("glm-4.6".to_string()),
            supports_images: false,
            enabled: true,
        },
        ProviderConfig {
            id: KIND_KIMI.to_string(),
            kind: KIND_KIMI.to_string(),
            label: "Kimi (Moonshot AI)".to_string(),
            base_url: Some("https://api.moonshot.ai/anthropic".to_string()),
            api_key: None,
            model: Some("kimi-k2-0905-preview".to_string()),
            supports_images: true,
            enabled: true,
        },
    ]
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct MultimodalSettings {
    #[serde(default = "default_true")]
    pub attachments_enabled: bool,
    #[serde(default = "default_max_dimension")]
    pub max_dimension: u32,
    #[serde(default = "default_jpeg_quality")]
    pub jpeg_quality: u32,
}

fn default_max_dimension() -> u32 {
    1600
}

fn default_jpeg_quality() -> u32 {
    85
}

impl Default for MultimodalSettings {
    fn default() -> Self {
        MultimodalSettings {
            attachments_enabled: true,
            max_dimension: default_max_dimension(),
            jpeg_quality: default_jpeg_quality(),
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ProvidersFile {
    #[serde(default)]
    providers: Vec<ProviderConfig>,
    #[serde(default)]
    multimodal: MultimodalSettings,
}

impl ProvidersFile {
    /// Inserts any built-in whose id is missing from `providers` (fresh install, or a
    /// `providers.json` written by an older version of the app that predates a given built-in).
    /// Never overwrites an existing entry (so a user's saved api_key/enabled/model survive).
    /// `claude` is always placed first.
    fn ensure_builtins(&mut self) {
        for def in builtin_defaults() {
            if !self.providers.iter().any(|p| p.id == def.id) {
                self.providers.push(def);
            }
        }
        self.providers.sort_by_key(|p| if p.id == KIND_CLAUDE { 0 } else { 1 });
    }
}

/// JSON file store, same shape as `account::AccountStore` / `app::SessionStore`: missing/corrupt
/// file loads as fresh defaults (never panics); every mutation rewrites the whole file.
pub struct ProviderStore {
    path: std::path::PathBuf,
    inner: std::sync::Mutex<ProvidersFile>,
}

impl ProviderStore {
    pub fn load(path: std::path::PathBuf) -> ProviderStore {
        let mut file = std::fs::read_to_string(&path)
            .ok()
            .and_then(|raw| serde_json::from_str::<ProvidersFile>(&raw).ok())
            .unwrap_or_default();
        file.ensure_builtins();
        let store = ProviderStore {
            path,
            inner: std::sync::Mutex::new(file),
        };
        store.persist_locked();
        store
    }

    fn persist_locked(&self) {
        let file = self.inner.lock().unwrap();
        self.persist(&file);
    }

    fn persist(&self, file: &ProvidersFile) {
        if let Ok(json) = serde_json::to_string_pretty(file) {
            if let Err(e) = std::fs::write(&self.path, json) {
                eprintln!("[ai-second-brain-desktop] failed to persist providers.json: {e}");
            }
        }
    }

    /// Raw (unmasked) snapshot for internal use (spawn wiring, test_provider). Never hand this to
    /// a `#[tauri::command]` return value.
    pub fn list_raw(&self) -> Vec<ProviderConfig> {
        self.inner.lock().unwrap().providers.clone()
    }

    pub fn get_raw(&self, id: &str) -> Option<ProviderConfig> {
        self.inner
            .lock()
            .unwrap()
            .providers
            .iter()
            .find(|p| p.id == id)
            .cloned()
    }

    /// Frontend-facing listing: every entry's `api_key` masked, `claude` first, each carrying an
    /// explicit `has_key` boolean (see `ProviderConfig::masked_with_has_key`).
    pub fn list_masked(&self) -> Vec<MaskedProviderConfig> {
        self.list_raw()
            .iter()
            .map(ProviderConfig::masked_with_has_key)
            .collect()
    }

    /// Inserts (new id) or replaces (existing id) a provider. If the incoming `api_key` is the
    /// masked sentinel the frontend echoed back unchanged, the previously stored raw key is kept
    /// instead of being overwritten with the mask itself.
    pub fn upsert(&self, mut config: ProviderConfig) -> ProviderConfig {
        let mut file = self.inner.lock().unwrap();
        if is_masked_sentinel(&config.api_key) {
            let previous_key = file
                .providers
                .iter()
                .find(|p| p.id == config.id)
                .and_then(|p| p.api_key.clone());
            config.api_key = previous_key;
        }
        match file.providers.iter_mut().find(|p| p.id == config.id) {
            Some(existing) => *existing = config.clone(),
            None => file.providers.push(config.clone()),
        }
        file.ensure_builtins();
        self.persist(&file);
        config
    }

    /// Built-ins can never be removed (only disabled or have their key cleared via `upsert`).
    pub fn remove(&self, id: &str) -> Result<(), String> {
        if is_builtin_id(id) {
            return Err(format!(
                "\"{id}\" is a built-in provider and cannot be removed; disable it or clear its API key instead"
            ));
        }
        let mut file = self.inner.lock().unwrap();
        let before = file.providers.len();
        file.providers.retain(|p| p.id != id);
        if file.providers.len() == before {
            return Err(format!("unknown provider: {id}"));
        }
        self.persist(&file);
        Ok(())
    }

    pub fn multimodal(&self) -> MultimodalSettings {
        self.inner.lock().unwrap().multimodal.clone()
    }

    pub fn set_multimodal(&self, settings: MultimodalSettings) {
        let mut file = self.inner.lock().unwrap();
        file.multimodal = settings;
        self.persist(&file);
    }
}

/// Builds the `ANTHROPIC_*` env-var overlay a session spawn should inject for `provider`. Empty
/// for the `claude` kind (official subscription login — no override, ever). Only variables with
/// a configured value are included; `ANTHROPIC_MODEL` is omitted entirely when the provider has
/// no model override so the CLI's own default takes over.
///
/// Returned as `EnvOverlay` (not a bare `Vec<(String, String)>`) so its `Debug` impl can redact
/// `ANTHROPIC_AUTH_TOKEN` — this is the one place a raw API key is held in memory outside the
/// store, and it must never leak into a log line via an incidental `{:?}`.
pub fn provider_env_vars(provider: &ProviderConfig) -> EnvOverlay {
    let mut vars = Vec::new();
    if provider.kind != KIND_CLAUDE {
        if let Some(base_url) = &provider.base_url {
            vars.push(("ANTHROPIC_BASE_URL".to_string(), base_url.clone()));
        }
        if let Some(api_key) = &provider.api_key {
            if !api_key.is_empty() {
                vars.push(("ANTHROPIC_AUTH_TOKEN".to_string(), api_key.clone()));
            }
        }
        if let Some(model) = &provider.model {
            vars.push(("ANTHROPIC_MODEL".to_string(), model.clone()));
        }
    }
    EnvOverlay(vars)
}

/// Same as `provider_env_vars`, except `ANTHROPIC_MODEL` is taken from `model_override` when it
/// is `Some` and non-empty, instead of the provider's own persisted default `model`. This is what
/// lets a session's per-session model pick (`SessionMeta::preferred_model`) actually reach a
/// non-`claude` provider's CLI process: for those providers `--model` is meaningless (the flag
/// expects an Anthropic model name like `"opus"`/`"sonnet"`, not e.g. `"glm-4.6"`), so the only
/// channel for a session-level override is this env var. Still empty for the `claude` kind
/// regardless of `model_override` — subscription login never gets an env override, and `--model`
/// remains the right (and only) channel for it (see `app::ensure_session_running`).
pub fn provider_env_vars_for_session(provider: &ProviderConfig, model_override: Option<&str>) -> EnvOverlay {
    match model_override {
        Some(m) if !m.is_empty() => {
            let mut overridden = provider.clone();
            overridden.model = Some(m.to_string());
            provider_env_vars(&overridden)
        }
        _ => provider_env_vars(provider),
    }
}

/// See `provider_env_vars`. `.0` is intentionally not `pub` accessed via `Debug`; use `.iter()` /
/// `.into_vec()` to consume the pairs.
#[derive(Clone, Default)]
pub struct EnvOverlay(Vec<(String, String)>);

impl EnvOverlay {
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn iter(&self) -> std::slice::Iter<'_, (String, String)> {
        self.0.iter()
    }

    pub fn into_vec(self) -> Vec<(String, String)> {
        self.0
    }
}

impl std::fmt::Debug for EnvOverlay {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let redacted: Vec<(&str, &str)> = self
            .0
            .iter()
            .map(|(k, v)| {
                if k == "ANTHROPIC_AUTH_TOKEN" {
                    (k.as_str(), "***redacted***")
                } else {
                    (k.as_str(), v.as_str())
                }
            })
            .collect();
        f.debug_tuple("EnvOverlay").field(&redacted).finish()
    }
}

/// Resolves whether attachments should be offered for a session on `provider_id`: unknown/missing
/// provider id (e.g. a stale session referencing a removed custom provider) degrades to `false`
/// rather than guessing.
pub fn supports_images_for(store: &ProviderStore, provider_id: &str) -> bool {
    store
        .get_raw(provider_id)
        .map(|p| p.supports_images)
        .unwrap_or(false)
}

// ---- #[tauri::command] handlers ----

#[tauri::command]
pub async fn list_providers(
    state: tauri::State<'_, ProviderStore>,
) -> Result<Vec<MaskedProviderConfig>, String> {
    Ok(state.list_masked())
}

#[tauri::command]
pub async fn upsert_provider(
    state: tauri::State<'_, ProviderStore>,
    provider: ProviderConfig,
) -> Result<MaskedProviderConfig, String> {
    if provider.id.trim().is_empty() {
        return Err("provider id cannot be empty".to_string());
    }
    let saved = state.upsert(provider);
    Ok(saved.masked_with_has_key())
}

#[tauri::command]
pub async fn remove_provider(
    state: tauri::State<'_, ProviderStore>,
    id: String,
) -> Result<(), String> {
    state.remove(&id)
}

#[tauri::command]
pub async fn get_multimodal_settings(
    state: tauri::State<'_, ProviderStore>,
) -> Result<MultimodalSettings, String> {
    Ok(state.multimodal())
}

#[tauri::command]
pub async fn set_multimodal_settings(
    state: tauri::State<'_, ProviderStore>,
    settings: MultimodalSettings,
) -> Result<MultimodalSettings, String> {
    state.set_multimodal(settings.clone());
    Ok(settings)
}

/// Spawns a trivial headless prompt through `provider`'s configured endpoint to confirm it's
/// reachable and authenticated. `claude` reuses `app::check_auth`'s exact logic (subscription
/// login has no env vars to inject); every other kind requires an `api_key` and runs with a 60s
/// timeout, per contract.
#[tauri::command]
pub async fn test_provider(
    app: tauri::AppHandle,
    state: tauri::State<'_, ProviderStore>,
    id: String,
) -> Result<String, String> {
    let provider = state
        .get_raw(&id)
        .ok_or_else(|| format!("unknown provider: {id}"))?;

    if provider.kind == KIND_CLAUDE {
        let check = crate::app::check_auth(app).await?;
        return if check.authenticated {
            Ok("ok".to_string())
        } else {
            Err(check.detail.unwrap_or_else(|| "not authenticated".to_string()))
        };
    }

    let Some(api_key) = provider.api_key.clone().filter(|k| !k.is_empty()) else {
        return Err(format!("no API key set for provider \"{}\"", provider.label));
    };

    let bin = crate::bridge::resolve_claude_bin().map_err(|e| e.to_string())?;

    let app_data_dir = { use tauri::Manager; app.path().app_data_dir().map_err(|e| e.to_string())? };
    std::fs::create_dir_all(&app_data_dir).map_err(|e| e.to_string())?;

    let mut cmd = tokio::process::Command::new(&bin);
    cmd.no_window()
        .current_dir(&app_data_dir)
        .arg("-p")
        .arg("Reply with only: OK")
        .arg("--output-format")
        .arg("json")
        .arg("--max-turns")
        .arg("1");

    if let Some(model) = &provider.model {
        cmd.arg("--model").arg(model);
    }

    if let Some(base_url) = &provider.base_url {
        cmd.env("ANTHROPIC_BASE_URL", base_url);
    }
    cmd.env("ANTHROPIC_AUTH_TOKEN", &api_key);
    if let Some(model) = &provider.model {
        cmd.env("ANTHROPIC_MODEL", model);
    }

    cmd.stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);

    let child = cmd.spawn().map_err(|e| e.to_string())?;

    match tokio::time::timeout(std::time::Duration::from_secs(60), child.wait_with_output()).await
    {
        Ok(Ok(output)) if output.status.success() => Ok("ok".to_string()),
        Ok(Ok(output)) => {
            let mut combined = String::from_utf8_lossy(&output.stderr).to_string();
            combined.push_str(&String::from_utf8_lossy(&output.stdout));
            Err(if combined.trim().is_empty() {
                format!("provider test failed with exit code {:?}", output.status.code())
            } else {
                combined
            })
        }
        Ok(Err(e)) => Err(e.to_string()),
        Err(_) => Err("timed out after 60s".to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_path(name: &str) -> std::path::PathBuf {
        let mut path = std::env::temp_dir();
        path.push(format!("asb_providers_test_{name}_{}.json", uuid::Uuid::new_v4()));
        let _ = std::fs::remove_file(&path);
        path
    }

    #[test]
    fn fresh_store_seeds_builtins_with_claude_first() {
        let path = temp_path("fresh");
        let store = ProviderStore::load(path.clone());
        let ids: Vec<String> = store.list_raw().iter().map(|p| p.id.clone()).collect();
        assert_eq!(ids[0], "claude");
        assert!(ids.contains(&"glm".to_string()));
        assert!(ids.contains(&"kimi".to_string()));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn store_roundtrip_persists_and_reloads_a_custom_provider() {
        let path = temp_path("roundtrip");
        let store = ProviderStore::load(path.clone());
        store.upsert(ProviderConfig {
            id: "my-custom".to_string(),
            kind: KIND_CUSTOM.to_string(),
            label: "My Custom".to_string(),
            base_url: Some("https://example.com/anthropic".to_string()),
            api_key: Some("sk-abcdef123456".to_string()),
            model: Some("my-model".to_string()),
            supports_images: true,
            enabled: true,
        });

        let reloaded = ProviderStore::load(path.clone());
        let raw = reloaded.get_raw("my-custom").expect("custom provider persisted");
        assert_eq!(raw.api_key.as_deref(), Some("sk-abcdef123456"));
        assert_eq!(raw.base_url.as_deref(), Some("https://example.com/anthropic"));
        assert!(raw.supports_images);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn missing_file_does_not_panic_and_yields_builtin_defaults() {
        let path = temp_path("missing");
        let store = ProviderStore::load(path.clone());
        assert_eq!(store.list_raw().len(), 3);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn corrupt_file_falls_back_to_fresh_defaults_instead_of_panicking() {
        let path = temp_path("corrupt");
        std::fs::write(&path, "{ not valid json").unwrap();
        let store = ProviderStore::load(path.clone());
        assert_eq!(store.list_raw().len(), 3);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn list_masked_shows_only_last_four_chars_of_api_key() {
        let path = temp_path("mask");
        let store = ProviderStore::load(path.clone());
        store.upsert(ProviderConfig {
            id: "glm".to_string(),
            kind: KIND_GLM.to_string(),
            label: "GLM (z.ai Coding Plan)".to_string(),
            base_url: Some("https://api.z.ai/api/anthropic".to_string()),
            api_key: Some("sk-zai-supersecretlongkey9012".to_string()),
            model: Some("glm-4.6".to_string()),
            supports_images: false,
            enabled: true,
        });

        let masked = store.list_masked();
        let glm = masked.iter().find(|p| p.config.id == "glm").unwrap();
        assert_eq!(glm.config.api_key.as_deref(), Some("****9012"));
        assert!(!glm.config.api_key.as_ref().unwrap().contains("supersecret"));
        assert!(glm.has_key);

        // Raw store still has the real key.
        assert_eq!(
            store.get_raw("glm").unwrap().api_key.as_deref(),
            Some("sk-zai-supersecretlongkey9012")
        );
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn masked_listing_exposes_has_key_boolean_for_connect_guard() {
        let path = temp_path("has_key");
        let store = ProviderStore::load(path.clone());

        // Fresh built-ins never carry a key.
        let masked = store.list_masked();
        let kimi = masked.iter().find(|p| p.config.id == "kimi").unwrap();
        assert!(!kimi.has_key);
        assert!(kimi.config.api_key.is_none());

        store.upsert(ProviderConfig {
            id: "kimi".to_string(),
            kind: KIND_KIMI.to_string(),
            label: "Kimi (Moonshot AI)".to_string(),
            base_url: Some("https://api.moonshot.ai/anthropic".to_string()),
            api_key: Some("real-kimi-key".to_string()),
            model: Some("kimi-k2-0905-preview".to_string()),
            supports_images: true,
            enabled: true,
        });
        let masked = store.list_masked();
        let kimi = masked.iter().find(|p| p.config.id == "kimi").unwrap();
        assert!(kimi.has_key);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn short_api_key_masks_to_bare_prefix() {
        assert_eq!(mask_key(&Some("abcd".to_string())), Some("****".to_string()));
        assert_eq!(mask_key(&None), None);
        assert_eq!(mask_key(&Some(String::new())), None);
    }

    #[test]
    fn upserting_the_masked_sentinel_back_keeps_the_previous_real_key() {
        let path = temp_path("sentinel");
        let store = ProviderStore::load(path.clone());
        store.upsert(ProviderConfig {
            id: "kimi".to_string(),
            kind: KIND_KIMI.to_string(),
            label: "Kimi (Moonshot AI)".to_string(),
            base_url: Some("https://api.moonshot.ai/anthropic".to_string()),
            api_key: Some("real-kimi-key-000111".to_string()),
            model: Some("kimi-k2-0905-preview".to_string()),
            supports_images: true,
            enabled: true,
        });

        // Simulate the frontend re-saving settings after only editing the label, echoing back the
        // masked value it was shown instead of the real key.
        store.upsert(ProviderConfig {
            id: "kimi".to_string(),
            kind: KIND_KIMI.to_string(),
            label: "Kimi (renamed)".to_string(),
            base_url: Some("https://api.moonshot.ai/anthropic".to_string()),
            api_key: Some("****0111".to_string()),
            model: Some("kimi-k2-0905-preview".to_string()),
            supports_images: true,
            enabled: true,
        });

        let raw = store.get_raw("kimi").unwrap();
        assert_eq!(raw.label, "Kimi (renamed)");
        assert_eq!(raw.api_key.as_deref(), Some("real-kimi-key-000111"));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn builtin_providers_cannot_be_removed() {
        let path = temp_path("protect_builtin");
        let store = ProviderStore::load(path.clone());
        assert!(store.remove("claude").is_err());
        assert!(store.remove("glm").is_err());
        assert!(store.remove("kimi").is_err());
        assert_eq!(store.list_raw().len(), 3);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn custom_providers_can_be_removed() {
        let path = temp_path("remove_custom");
        let store = ProviderStore::load(path.clone());
        store.upsert(ProviderConfig {
            id: "custom-1".to_string(),
            kind: KIND_CUSTOM.to_string(),
            label: "Custom One".to_string(),
            base_url: Some("https://x.example/anthropic".to_string()),
            api_key: Some("k".to_string()),
            model: None,
            supports_images: false,
            enabled: true,
        });
        assert!(store.remove("custom-1").is_ok());
        assert!(store.get_raw("custom-1").is_none());
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn removing_unknown_id_is_an_error() {
        let path = temp_path("remove_unknown");
        let store = ProviderStore::load(path.clone());
        assert!(store.remove("does-not-exist").is_err());
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn multimodal_settings_default_to_documented_values() {
        let path = temp_path("multimodal_default");
        let store = ProviderStore::load(path.clone());
        let mm = store.multimodal();
        assert!(mm.attachments_enabled);
        assert_eq!(mm.max_dimension, 1600);
        assert_eq!(mm.jpeg_quality, 85);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn multimodal_settings_roundtrip() {
        let path = temp_path("multimodal_roundtrip");
        let store = ProviderStore::load(path.clone());
        store.set_multimodal(MultimodalSettings {
            attachments_enabled: false,
            max_dimension: 800,
            jpeg_quality: 60,
        });
        let reloaded = ProviderStore::load(path.clone());
        let mm = reloaded.multimodal();
        assert!(!mm.attachments_enabled);
        assert_eq!(mm.max_dimension, 800);
        assert_eq!(mm.jpeg_quality, 60);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn env_vars_are_empty_for_the_claude_provider() {
        let claude = builtin_defaults().into_iter().find(|p| p.id == "claude").unwrap();
        let overlay = provider_env_vars(&claude);
        assert!(overlay.is_empty());
    }

    #[test]
    fn env_vars_include_base_url_key_and_model_for_glm() {
        let mut glm = builtin_defaults().into_iter().find(|p| p.id == "glm").unwrap();
        glm.api_key = Some("sk-test-key".to_string());
        let overlay = provider_env_vars(&glm);
        let vars = overlay.into_vec();
        assert_eq!(
            vars.iter().find(|(k, _)| k == "ANTHROPIC_BASE_URL").map(|(_, v)| v.as_str()),
            Some("https://api.z.ai/api/anthropic")
        );
        assert_eq!(
            vars.iter().find(|(k, _)| k == "ANTHROPIC_AUTH_TOKEN").map(|(_, v)| v.as_str()),
            Some("sk-test-key")
        );
        assert_eq!(
            vars.iter().find(|(k, _)| k == "ANTHROPIC_MODEL").map(|(_, v)| v.as_str()),
            Some("glm-4.6")
        );
    }

    #[test]
    fn env_vars_omit_model_var_when_no_model_override_is_set() {
        let provider = ProviderConfig {
            id: "custom-2".to_string(),
            kind: KIND_CUSTOM.to_string(),
            label: "Custom Two".to_string(),
            base_url: Some("https://x.example/anthropic".to_string()),
            api_key: Some("key".to_string()),
            model: None,
            supports_images: false,
            enabled: true,
        };
        let overlay = provider_env_vars(&provider);
        let vars = overlay.into_vec();
        assert!(!vars.iter().any(|(k, _)| k == "ANTHROPIC_MODEL"));
    }

    #[test]
    fn env_vars_omit_auth_token_when_api_key_is_missing() {
        let provider = ProviderConfig {
            id: "custom-3".to_string(),
            kind: KIND_CUSTOM.to_string(),
            label: "Custom Three".to_string(),
            base_url: Some("https://x.example/anthropic".to_string()),
            api_key: None,
            model: None,
            supports_images: false,
            enabled: true,
        };
        let overlay = provider_env_vars(&provider);
        assert!(!overlay.into_vec().iter().any(|(k, _)| k == "ANTHROPIC_AUTH_TOKEN"));
    }

    #[test]
    fn session_override_replaces_the_provider_default_model_for_glm() {
        let mut glm = builtin_defaults().into_iter().find(|p| p.id == "glm").unwrap();
        glm.api_key = Some("sk-test-key".to_string());
        let overlay = provider_env_vars_for_session(&glm, Some("glm-4.5-air"));
        let vars = overlay.into_vec();
        assert_eq!(
            vars.iter().find(|(k, _)| k == "ANTHROPIC_MODEL").map(|(_, v)| v.as_str()),
            Some("glm-4.5-air")
        );
        // Provider's own stored default ("glm-4.6") must not leak through once overridden.
        assert!(!vars.iter().any(|(_, v)| v == "glm-4.6"));
    }

    #[test]
    fn no_session_override_falls_back_to_the_provider_default_model() {
        let mut glm = builtin_defaults().into_iter().find(|p| p.id == "glm").unwrap();
        glm.api_key = Some("sk-test-key".to_string());
        let overlay = provider_env_vars_for_session(&glm, None);
        let vars = overlay.into_vec();
        assert_eq!(
            vars.iter().find(|(k, _)| k == "ANTHROPIC_MODEL").map(|(_, v)| v.as_str()),
            Some("glm-4.6")
        );
    }

    #[test]
    fn empty_string_override_is_treated_as_no_override() {
        let mut kimi = builtin_defaults().into_iter().find(|p| p.id == "kimi").unwrap();
        kimi.api_key = Some("key".to_string());
        let overlay = provider_env_vars_for_session(&kimi, Some(""));
        let vars = overlay.into_vec();
        assert_eq!(
            vars.iter().find(|(k, _)| k == "ANTHROPIC_MODEL").map(|(_, v)| v.as_str()),
            Some("kimi-k2-0905-preview")
        );
    }

    #[test]
    fn session_override_is_still_empty_overlay_for_the_claude_provider() {
        let claude = builtin_defaults().into_iter().find(|p| p.id == "claude").unwrap();
        let overlay = provider_env_vars_for_session(&claude, Some("opus"));
        assert!(overlay.is_empty());
    }

    #[test]
    fn debug_format_redacts_the_auth_token() {
        let mut glm = builtin_defaults().into_iter().find(|p| p.id == "glm").unwrap();
        glm.api_key = Some("sk-super-secret-value".to_string());
        let overlay = provider_env_vars(&glm);
        let debugged = format!("{overlay:?}");
        assert!(!debugged.contains("sk-super-secret-value"));
        assert!(debugged.contains("***redacted***"));
    }

    #[test]
    fn provider_config_debug_impl_never_prints_the_raw_api_key() {
        let mut glm = builtin_defaults().into_iter().find(|p| p.id == "glm").unwrap();
        glm.api_key = Some("sk-super-secret-value-9012".to_string());
        let debugged = format!("{glm:?}");
        assert!(!debugged.contains("sk-super-secret-value-9012"));
        assert!(debugged.contains("****9012"));

        // Also holds for a collection, since that's the realistic panic/log shape.
        let debugged_vec = format!("{:?}", vec![glm]);
        assert!(!debugged_vec.contains("sk-super-secret-value-9012"));
    }

    #[test]
    fn supports_images_for_reflects_provider_flag_and_defaults_false_for_unknown_id() {
        let path = temp_path("supports_images");
        let store = ProviderStore::load(path.clone());
        assert!(supports_images_for(&store, "claude"));
        assert!(!supports_images_for(&store, "glm"));
        assert!(supports_images_for(&store, "kimi"));
        assert!(!supports_images_for(&store, "does-not-exist"));
        let _ = std::fs::remove_file(&path);
    }
}
