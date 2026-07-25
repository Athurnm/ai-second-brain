//! Managed Python runtime for the bundled harness.
//!
//! The starter workspace is markdown-only, but the full AI Second Brain harness is not: most of
//! its skills are `run.py` scripts and its `requirements.txt` pulls real dependencies. Office
//! workers will not install Python themselves, and on Windows there is no reliable `python3` on
//! PATH even when Python *is* installed.
//!
//! So the app owns the interpreter. It ships `uv` (a single static binary, no Python needed to
//! run it) as a Tauri sidecar, and on demand creates a virtualenv under the app-data dir and
//! installs the workspace's `requirements.txt` into it. Nothing is ever installed into the user's
//! system Python, and nothing requires a terminal.
//!
//! Resolution order for the `uv` binary:
//!   1. `ASB_UV` env override (dev/founder escape hatch).
//!   2. The bundled sidecar next to the app executable.
//!   3. `uv` on PATH (developer machines; also the graceful path before the sidecar asset lands).
//!
//! The venv lives at `<app_data>/runtime/venv` and is deliberately OUTSIDE the workspace, so
//! "reset my workspace" and "reset my runtime" stay independent operations, and so a workspace
//! folder the user syncs between machines never carries platform-specific binaries with it.

use std::path::{Path, PathBuf};
use std::sync::RwLock;

use tokio::process::Command;

use crate::bridge::CommandNoWindowExt;

/// Env override pointing directly at a `uv` executable.
pub const ENV_UV: &str = "ASB_UV";

/// Env var the harness reads to find the managed interpreter. Hooks and skills use this instead
/// of assuming `python3` exists on PATH.
pub const ENV_PYTHON: &str = "ASB_PYTHON";

/// Subdirectory of the app-data dir that holds the managed runtime.
const RUNTIME_DIR_NAME: &str = "runtime";
const VENV_DIR_NAME: &str = "venv";

/// Cached interpreter path, so `spawn_session` does not stat the filesystem on every message.
static PYTHON_PATH: RwLock<Option<PathBuf>> = RwLock::new(None);

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeStatus {
    /// True when a usable interpreter exists on disk right now.
    pub ready: bool,
    /// Absolute path to the managed interpreter, present whether or not it exists yet.
    pub python_path: String,
    /// True when a `uv` binary could be located, meaning bootstrap is possible at all.
    pub uv_available: bool,
    /// Where `uv` was found, for the diagnostics panel. `None` when unavailable.
    pub uv_source: Option<String>,
    /// True when the workspace declares dependencies that bootstrap would install.
    pub has_requirements: bool,
}

/// Platform-correct interpreter path inside a venv. Windows puts it in `Scripts\python.exe`,
/// everything else in `bin/python3`.
fn venv_python(venv: &Path) -> PathBuf {
    if cfg!(windows) {
        venv.join("Scripts").join("python.exe")
    } else {
        venv.join("bin").join("python3")
    }
}

fn runtime_root(app_data: &Path) -> PathBuf {
    app_data.join(RUNTIME_DIR_NAME)
}

fn venv_dir(app_data: &Path) -> PathBuf {
    runtime_root(app_data).join(VENV_DIR_NAME)
}

/// Absolute path to the managed interpreter, whether or not it has been created yet.
pub fn python_path(app_data: &Path) -> PathBuf {
    venv_python(&venv_dir(app_data))
}

/// The managed interpreter if it actually exists on disk, else `None`. Cached after the first
/// successful lookup; `invalidate_cache` clears it after a bootstrap or reset.
pub fn resolved_python(app_data: &Path) -> Option<PathBuf> {
    if let Ok(guard) = PYTHON_PATH.read() {
        if let Some(p) = guard.as_ref() {
            if p.is_file() {
                return Some(p.clone());
            }
        }
    }
    let p = python_path(app_data);
    if !p.is_file() {
        return None;
    }
    if let Ok(mut guard) = PYTHON_PATH.write() {
        *guard = Some(p.clone());
    }
    Some(p)
}

pub fn invalidate_cache() {
    if let Ok(mut guard) = PYTHON_PATH.write() {
        *guard = None;
    }
}

/// Sidecar file name Tauri produces for the current target. Tauri strips the target triple when
/// it bundles, so at runtime the binary sits next to the executable under its plain name.
fn sidecar_name() -> &'static str {
    if cfg!(windows) {
        "uv.exe"
    } else {
        "uv"
    }
}

/// Locates a usable `uv`. Returns the path and a short human label for diagnostics.
fn find_uv() -> Option<(PathBuf, String)> {
    if let Ok(raw) = std::env::var(ENV_UV) {
        let p = PathBuf::from(raw);
        if p.is_file() {
            return Some((p, format!("{ENV_UV} env override")));
        }
    }

    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let candidate = dir.join(sidecar_name());
            if candidate.is_file() {
                return Some((candidate, "bundled sidecar".to_string()));
            }
        }
    }

    // PATH scan, done by hand rather than shelling out to `which`/`where`, matching how
    // `bridge::resolve_claude_bin` deliberately avoids spawning a shell to find a binary.
    if let Ok(path) = std::env::var("PATH") {
        for dir in std::env::split_paths(&path) {
            let candidate = dir.join(sidecar_name());
            if candidate.is_file() {
                return Some((candidate, "PATH".to_string()));
            }
        }
    }

    None
}

/// The workspace's dependency manifest, if it declares one.
fn requirements_file(workspace: &Path) -> Option<PathBuf> {
    let p = workspace.join("requirements.txt");
    if p.is_file() {
        Some(p)
    } else {
        None
    }
}

pub fn status(app_data: &Path, workspace: Option<&Path>) -> RuntimeStatus {
    let uv = find_uv();
    RuntimeStatus {
        ready: resolved_python(app_data).is_some(),
        python_path: python_path(app_data).to_string_lossy().into_owned(),
        uv_available: uv.is_some(),
        uv_source: uv.map(|(_, label)| label),
        has_requirements: workspace.and_then(requirements_file).is_some(),
    }
}

/// Creates the venv and installs the workspace's requirements into it.
///
/// Idempotent: `uv venv` on an existing venv is a no-op, and `uv pip install` re-resolves without
/// re-downloading. Safe to call on every launch, though the caller currently only invokes it from
/// the onboarding wizard and the explicit "repair runtime" action.
pub async fn bootstrap(app_data: &Path, workspace: &Path) -> Result<String, String> {
    let (uv, uv_label) = find_uv().ok_or_else(|| {
        "Could not find the bundled `uv` binary, and no `uv` is on PATH. The Python-backed \
         skills cannot be installed without it. Reinstall the app, or set the ASB_UV \
         environment variable to a `uv` executable."
            .to_string()
    })?;

    let venv = venv_dir(app_data);
    if let Some(parent) = venv.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Could not create the runtime directory: {e}"))?;
    }

    let mut log = format!("Using uv from {uv_label}.\n");

    let out = Command::new(&uv)
        .no_window()
        .arg("venv")
        .arg(&venv)
        .output()
        .await
        .map_err(|e| format!("Could not run `uv venv`: {e}"))?;
    if !out.status.success() {
        return Err(format!(
            "`uv venv` failed: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        ));
    }
    log.push_str("Virtualenv ready.\n");

    let python = venv_python(&venv);
    if !python.is_file() {
        return Err(format!(
            "`uv venv` reported success but no interpreter appeared at {}.",
            python.display()
        ));
    }

    match requirements_file(workspace) {
        None => {
            log.push_str(
                "No requirements.txt in the workspace, so nothing to install. The \
                 markdown-only skills work as-is.\n",
            );
        }
        Some(req) => {
            let out = Command::new(&uv)
                .no_window()
                .arg("pip")
                .arg("install")
                .arg("--python")
                .arg(&python)
                .arg("-r")
                .arg(&req)
                .output()
                .await
                .map_err(|e| format!("Could not run `uv pip install`: {e}"))?;
            if !out.status.success() {
                return Err(format!(
                    "Installing the workspace dependencies failed: {}",
                    String::from_utf8_lossy(&out.stderr).trim()
                ));
            }
            log.push_str("Workspace dependencies installed.\n");
        }
    }

    invalidate_cache();
    log.push_str(&format!("Interpreter: {}\n", python.display()));
    Ok(log)
}

/// Deletes the managed runtime so the next bootstrap starts clean. Used by "repair runtime".
pub fn reset(app_data: &Path) -> Result<(), String> {
    let root = runtime_root(app_data);
    if root.exists() {
        std::fs::remove_dir_all(&root)
            .map_err(|e| format!("Could not remove the runtime directory: {e}"))?;
    }
    invalidate_cache();
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn venv_python_is_platform_correct() {
        let venv = PathBuf::from("/tmp/venv");
        let p = venv_python(&venv);
        if cfg!(windows) {
            assert!(p.ends_with("Scripts/python.exe") || p.ends_with("Scripts\\python.exe"));
        } else {
            assert!(p.ends_with("bin/python3"));
        }
    }

    #[test]
    fn runtime_lives_outside_the_workspace() {
        let app_data = PathBuf::from("/tmp/appdata");
        let py = python_path(&app_data);
        assert!(py.starts_with(&app_data));
        assert!(py.to_string_lossy().contains(RUNTIME_DIR_NAME));
    }

    #[test]
    fn status_reports_missing_requirements() {
        let app_data = PathBuf::from("/tmp/asb-does-not-exist");
        let s = status(&app_data, None);
        assert!(!s.ready);
        assert!(!s.has_requirements);
    }
}
