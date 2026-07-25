//! Managed 9Router sidecar.
//!
//! 9Router (<https://github.com/decolua/9router>, MIT) is a local proxy that fans a request out
//! across whatever free-tier AI accounts the user already has, and exposes them behind one
//! Anthropic-compatible endpoint on `http://127.0.0.1:20128`. That makes it the "no subscription
//! required" on-ramp for this app: point a provider at the local endpoint and the `claude` CLI
//! never knows the difference.
//!
//! The target user does not have a terminal open and will not run `npm install -g` themselves, so
//! the app owns the lifecycle end to end: detect → install → start → open the dashboard → stop.
//! Same philosophy as `runtime.rs` owning the Python interpreter.
//!
//! Two things are deliberately NOT owned here:
//!   * **Node.js.** 9Router ships as an npm package (`engines: node >= 18`) and installing a Node
//!     runtime is an admin-level OS install we cannot do silently. When Node is missing the status
//!     says so and the UI points at the download page. In practice most users already have it,
//!     since the npm route is the common way the `claude` CLI itself gets installed.
//!   * **Which upstream accounts to connect.** That happens in 9Router's own web dashboard, behind
//!     OAuth flows we should not proxy. The app just opens the browser at the right URL.
//!
//! The process is a child of this app and is killed on stop/exit, so a crashed app never leaves an
//! orphan proxy holding the port. Its own state (connected accounts, db.json) lives in `~/.9router`
//! — that path is baked into its CLI with no env override, so the app does not get to choose it.
//!
//! Everything below was verified against a live `9router@0.5.40`, not inferred from its docs:
//!   * `--port` / `--host` / `--no-browser` / `--skip-update` are the real flags (there is no
//!     `PORT`/`DATA_DIR` env contract, contrary to several write-ups).
//!   * `GET /api/health` answers `{"ok":true}`; the root path only 307-redirects, so it is a poor
//!     liveness probe.
//!   * `POST /v1/messages` answers with an Anthropic-shaped error body, i.e. the `/v1` suffix is
//!     part of the base URL. 9Router's own "configure Claude Code" endpoint agrees: it appends
//!     `/v1` to any `ANTHROPIC_BASE_URL` that lacks it.

use std::path::PathBuf;
use std::sync::Mutex;

use tokio::process::{Child, Command};

use crate::bridge::CommandNoWindowExt;

/// Port 9Router listens on. Its default; pinned here because the provider preset's `base_url` has
/// to agree with it and there is no discovery handshake between the two.
pub const PORT: u16 = 20128;

/// Model catalogue. Unauthenticated, unlike most of its `/api/*` surface, so the app can populate
/// a picker before the user has logged into the dashboard.
fn models_url() -> String {
    format!("http://127.0.0.1:{PORT}/v1/models")
}

/// npm package name, and the `bin` it installs (verified against the registry: `9router@0.5.x`
/// declares `bin: { "9router": "cli.js" }`).
const NPM_PACKAGE: &str = "9router";
const BIN_NAME: &str = "9router";

/// The single running child, if any. A `std::sync::Mutex` rather than tokio's: every critical
/// section here is a field read or a `start_kill()`, both synchronous and non-blocking, so an
/// async mutex would buy nothing and would make `stop_blocking` (called from a Drop-ish shutdown
/// path) impossible to write.
static CHILD: Mutex<Option<Child>> = Mutex::new(None);

/// What the provider preset stores as `ANTHROPIC_BASE_URL`. The `/v1` suffix is required: 9Router
/// serves the Anthropic-compatible surface under it, and its own Claude Code configurator appends
/// `/v1` to any base URL missing it.
pub fn api_base_url() -> String {
    format!("http://127.0.0.1:{PORT}/v1")
}

/// Liveness probe. `/api/health` returns `{"ok":true}`; the server root only issues a 307.
fn health_url() -> String {
    format!("http://127.0.0.1:{PORT}/api/health")
}

/// The dashboard is the same server as the API; `localhost` (not `127.0.0.1`) because OAuth
/// redirect URIs registered by upstream providers conventionally use that spelling.
pub fn dashboard_url() -> String {
    format!("http://localhost:{PORT}")
}

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NineRouterStatus {
    /// A `9router` executable was found — the app can start it.
    pub installed: bool,
    /// Something is answering on the port right now.
    pub running: bool,
    /// True when this app spawned the process that is running. False for a `running` proxy the
    /// user started themselves in a terminal, which we must never kill.
    pub managed: bool,
    /// False when npm is missing, which is the one failure the app cannot fix by itself.
    pub npm_available: bool,
    /// Where the `9router` binary was found, for the diagnostics line.
    pub bin_source: Option<String>,
    pub base_url: String,
    pub dashboard_url: String,
}

/// True when the extension-less name is not directly spawnable and npm's `.cmd` shim is what
/// actually exists on disk.
fn bin_candidates() -> Vec<String> {
    if cfg!(windows) {
        vec![
            format!("{BIN_NAME}.cmd"),
            format!("{BIN_NAME}.exe"),
            BIN_NAME.to_string(),
        ]
    } else {
        vec![BIN_NAME.to_string()]
    }
}

fn npm_candidates() -> Vec<String> {
    if cfg!(windows) {
        vec!["npm.cmd".to_string(), "npm.exe".to_string()]
    } else {
        vec!["npm".to_string()]
    }
}

/// Hand-rolled PATH scan plus the well-known npm-global prefixes a GUI-launched app's PATH
/// routinely misses — the same problem, and the same remedy, as `bridge::resolve_claude_bin`.
fn find_on_path(names: &[String]) -> Option<(PathBuf, String)> {
    if let Some(path_var) = std::env::var_os("PATH") {
        for dir in std::env::split_paths(&path_var) {
            for name in names {
                let candidate = dir.join(name);
                if candidate.is_file() {
                    return Some((candidate, "PATH".to_string()));
                }
            }
        }
    }

    let mut roots: Vec<PathBuf> = Vec::new();
    #[cfg(windows)]
    if let Some(appdata) = std::env::var_os("APPDATA") {
        roots.push(PathBuf::from(appdata).join("npm"));
    }
    if let Some(home) = std::env::var_os("HOME") {
        let home = PathBuf::from(home);
        roots.push(home.join(".npm-global/bin"));
        roots.push(home.join(".local/bin"));
        roots.push(home.join("node_modules/.bin"));
    }
    roots.push(PathBuf::from("/usr/local/bin"));
    roots.push(PathBuf::from("/opt/homebrew/bin"));

    for dir in roots {
        for name in names {
            let candidate = dir.join(name);
            if candidate.is_file() {
                return Some((candidate, "npm global prefix".to_string()));
            }
        }
    }
    None
}

fn find_bin() -> Option<(PathBuf, String)> {
    find_on_path(&bin_candidates())
}

fn find_npm() -> Option<(PathBuf, String)> {
    find_on_path(&npm_candidates())
}

/// True when a clone of the child we spawned is still alive. Reaps the handle when the process has
/// exited on its own, so a crashed proxy stops being reported as `managed`.
fn managed_alive() -> bool {
    let Ok(mut guard) = CHILD.lock() else {
        return false;
    };
    let Some(child) = guard.as_mut() else {
        return false;
    };
    match child.try_wait() {
        Ok(Some(_)) => {
            *guard = None;
            false
        }
        Ok(None) => true,
        Err(_) => false,
    }
}

/// Is anything answering on the port? Any HTTP response counts: the question is "is the port held
/// by a live server", not "is that server happy".
async fn is_up() -> bool {
    let Ok(client) = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build()
    else {
        return false;
    };
    client.get(health_url()).send().await.is_ok()
}

pub async fn status() -> NineRouterStatus {
    let bin = find_bin();
    NineRouterStatus {
        installed: bin.is_some(),
        running: is_up().await,
        managed: managed_alive(),
        npm_available: find_npm().is_some(),
        bin_source: bin.map(|(_, label)| label),
        base_url: api_base_url(),
        dashboard_url: dashboard_url(),
    }
}

/// The model ids 9Router will currently route, newest config first as it returns them.
///
/// This is not a nicety. `claude` sends its own default model name (e.g. `claude-opus-4-8`) when
/// `ANTHROPIC_MODEL` is unset, 9Router has no route for that name, and the session dies on a 404
/// that mentions a model the user never chose. So a 9Router provider is only usable once a model
/// from THIS list is pinned onto it.
pub async fn models() -> Result<Vec<String>, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| e.to_string())?;

    let resp = client
        .get(models_url())
        .send()
        .await
        .map_err(|_| "9Router isn't answering. Start it first.".to_string())?;

    let body: serde_json::Value = resp
        .json()
        .await
        .map_err(|e| format!("9Router returned a model list this app couldn't read: {e}"))?;

    // OpenAI-style envelope: `{"object":"list","data":[{"id":"...","object":"model"}, ...]}`.
    let ids: Vec<String> = body
        .get("data")
        .and_then(|d| d.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|m| m.get("id").and_then(|v| v.as_str()).map(str::to_string))
                .collect()
        })
        .unwrap_or_default();

    if ids.is_empty() {
        return Err("9Router isn't offering any models yet. Open its dashboard and connect \
                    at least one account."
            .to_string());
    }
    Ok(ids)
}

/// `npm install -g 9router`. Slow (~50 MB unpacked) so the caller must not block a UI frame on it;
/// the 10-minute ceiling exists only to keep a wedged install from hanging the app forever.
pub async fn install() -> Result<String, String> {
    let (npm, _) = find_npm().ok_or_else(|| {
        "Node.js is not installed on this computer, and 9Router needs it. Install Node.js \
         (the LTS version) from nodejs.org, then come back and click Install again."
            .to_string()
    })?;

    let out = Command::new(&npm)
        .no_window()
        .arg("install")
        .arg("-g")
        .arg(NPM_PACKAGE)
        .output();

    let out = tokio::time::timeout(std::time::Duration::from_secs(600), out)
        .await
        .map_err(|_| "Installing 9Router timed out after 10 minutes.".to_string())?
        .map_err(|e| format!("Could not run npm: {e}"))?;

    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        return Err(format!(
            "Installing 9Router failed.\n\n{}",
            stderr.trim().chars().take(1500).collect::<String>()
        ));
    }

    if find_bin().is_none() {
        return Err("npm reported success but the 9router command still isn't there. \
                    It may have installed somewhere outside this app's search path."
            .to_string());
    }
    Ok("9Router installed.".to_string())
}

/// Starts the proxy and waits for it to answer. Idempotent against an already-listening port: if
/// something is already up (ours or the user's own), this is a no-op rather than a second process
/// fighting for the port.
pub async fn start() -> Result<String, String> {
    if is_up().await {
        return Ok("9Router is already running.".to_string());
    }

    let (bin, _) = find_bin().ok_or_else(|| {
        "9Router isn't installed yet. Click Install first.".to_string()
    })?;

    let child = Command::new(&bin)
        .no_window()
        .arg("--port")
        .arg(PORT.to_string())
        // Loopback only. 9Router's own default is 0.0.0.0, which would expose a proxy holding the
        // user's AI accounts to every machine on the coffee-shop or office network.
        .arg("--host")
        .arg("127.0.0.1")
        // It pops a browser tab on start otherwise; the app decides when the dashboard opens.
        .arg("--no-browser")
        // Its update check can prompt interactively (it depends on `enquirer`), and stdin is null
        // here — an interactive prompt would hang the start forever instead of failing.
        .arg("--skip-update")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("Could not start 9Router: {e}"))?;

    if let Ok(mut guard) = CHILD.lock() {
        *guard = Some(child);
    }

    // Poll rather than sleep-then-check: a warm start answers in about a second, a cold one takes
    // several, and the UI should unblock as soon as it is actually usable.
    for _ in 0..40 {
        if is_up().await {
            return Ok("9Router is running.".to_string());
        }
        if !managed_alive() {
            return Err("9Router started and then exited immediately. Try Repair, or open \
                        the dashboard once to finish its first-run setup."
                .to_string());
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }

    stop();
    Err("9Router didn't finish starting within 20 seconds.".to_string())
}

/// Kills the managed process. A proxy the user started themselves is left alone — we only ever
/// own what we spawned.
pub fn stop() {
    if let Ok(mut guard) = CHILD.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.start_kill();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The `/v1` suffix is the whole integration: without it the CLI posts to `/messages`, which
    /// 9Router does not serve, and every session fails with a confusing 404.
    #[test]
    fn api_base_url_keeps_the_v1_suffix() {
        assert_eq!(api_base_url(), format!("http://127.0.0.1:{PORT}/v1"));
        assert!(api_base_url().ends_with("/v1"));
    }

    #[test]
    fn health_probe_does_not_use_the_redirecting_root() {
        assert!(health_url().ends_with("/api/health"));
    }

    #[test]
    fn dashboard_url_is_the_server_root_on_the_same_port() {
        assert_eq!(dashboard_url(), format!("http://localhost:{PORT}"));
    }

    #[test]
    fn windows_looks_for_the_cmd_shim_first() {
        if cfg!(windows) {
            assert_eq!(bin_candidates()[0], "9router.cmd");
        } else {
            assert_eq!(bin_candidates(), vec!["9router".to_string()]);
        }
    }

    #[test]
    fn nothing_is_managed_before_a_start() {
        assert!(!managed_alive());
    }
}
