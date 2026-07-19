//! Workspace resolution for AI Second Brain Desktop.
//!
//! Zero Tauri dependencies (mirrors the purity of `bridge.rs`): the caller (`lib.rs`/`app.rs`)
//! passes in the app-data directory it already has from `tauri_app.path()`. Resolution order
//! (product decision, verbatim): env `ASB_WORKSPACE` -> config file in app-data -> first-run
//! onboarding. The resolved root is cached in a process-wide static so every command can read it
//! without re-touching disk or re-reading the environment on every call.

use std::path::{Path, PathBuf};
use std::sync::RwLock;

/// Env var override. Wins over the config file. Must be an existing directory; if set but
/// missing/not-a-dir, resolution returns `Invalid` (never silently falls through to the config
/// file or onboarding) so the founder path — pointing a private build at a private harness — never
/// fails silently.
pub const ENV_WORKSPACE: &str = "ASB_WORKSPACE";

/// File name of the workspace config, sitting in the same app-data dir as `sessions.json`.
pub const CONFIG_FILE_NAME: &str = "workspace.json";

/// Default workspace root, relative to the app-data dir, offered on the create-workspace screen.
pub const DEFAULT_WORKSPACE_DIR_NAME: &str = "workspace";

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkspaceConfig {
    pub version: u32,
    pub workspace_root: String,
    #[serde(default)]
    pub created_from_template: bool,
    #[serde(default)]
    pub template_version: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub enum Source {
    Env,
    Config,
}

#[derive(Debug)]
pub enum ResolveOutcome {
    Resolved {
        root: PathBuf,
        source: Source,
    },
    /// No env override, no config file (or the config file is missing/unparsable) -> onboarding.
    NotConfigured,
    /// Env or config named a root, but it does not exist / is not a directory.
    Invalid {
        attempted: String,
        source: Source,
        reason: String,
    },
}

/// Resolves the workspace root: `ASB_WORKSPACE` env var first, then `<app_data_dir>/workspace.json`.
/// A well-formed config or env value that points somewhere non-existent is `Invalid`, never
/// silently degraded to `NotConfigured` — onboarding surfaces the exact reason. A missing or
/// unparsable config file (nothing has ever been configured yet) is `NotConfigured`.
pub fn resolve(app_data_dir: &Path) -> ResolveOutcome {
    if let Ok(val) = std::env::var(ENV_WORKSPACE) {
        let path = PathBuf::from(&val);
        return if path.is_dir() {
            ResolveOutcome::Resolved {
                root: path,
                source: Source::Env,
            }
        } else {
            ResolveOutcome::Invalid {
                attempted: val,
                source: Source::Env,
                reason: format!(
                    "{ENV_WORKSPACE} points to {}, which is not a directory",
                    path.display()
                ),
            }
        };
    }

    let config_path = app_data_dir.join(CONFIG_FILE_NAME);
    let Ok(raw) = std::fs::read_to_string(&config_path) else {
        return ResolveOutcome::NotConfigured;
    };
    let Ok(cfg) = serde_json::from_str::<WorkspaceConfig>(&raw) else {
        return ResolveOutcome::NotConfigured;
    };

    let path = PathBuf::from(&cfg.workspace_root);
    if path.is_dir() {
        ResolveOutcome::Resolved {
            root: path,
            source: Source::Config,
        }
    } else {
        ResolveOutcome::Invalid {
            attempted: cfg.workspace_root.clone(),
            source: Source::Config,
            reason: format!(
                "{CONFIG_FILE_NAME} points to {}, which is not a directory",
                cfg.workspace_root
            ),
        }
    }
}

/// Writes the config atomically: write to a sibling temp file, then rename over the target so a
/// crash mid-write never leaves a half-written `workspace.json` behind.
pub fn save_config(app_data_dir: &Path, cfg: &WorkspaceConfig) -> Result<(), String> {
    std::fs::create_dir_all(app_data_dir).map_err(|e| e.to_string())?;
    let final_path = app_data_dir.join(CONFIG_FILE_NAME);
    let tmp_path = app_data_dir.join(format!("{CONFIG_FILE_NAME}.tmp"));
    let json = serde_json::to_string_pretty(cfg).map_err(|e| e.to_string())?;
    std::fs::write(&tmp_path, json).map_err(|e| e.to_string())?;
    std::fs::rename(&tmp_path, &final_path).map_err(|e| e.to_string())?;
    Ok(())
}

static WORKSPACE_ROOT: RwLock<Option<PathBuf>> = RwLock::new(None);

/// Caches the resolved workspace root for the lifetime of the process. Called once at startup
/// (on a `Resolved` outcome) and again by `create_workspace`/`choose_workspace` once onboarding
/// completes.
pub fn set_root(root: PathBuf) {
    let mut guard = WORKSPACE_ROOT.write().unwrap();
    *guard = Some(root);
}

/// `None` until a workspace has been resolved or configured via onboarding; every command that
/// needs the workspace root degrades gracefully (empty list / "not configured" error) rather than
/// panicking when this is `None`.
pub fn root() -> Option<PathBuf> {
    WORKSPACE_ROOT.read().unwrap().clone()
}

/// Recursively copies every file and subdirectory from `src` into `dst`, creating directories as
/// needed. Used by `create_workspace` to copy the bundled `inbox/`/`notes/` template folders
/// verbatim (the `commands/` folder is remapped, not copied verbatim, so it is handled separately
/// by the caller).
pub fn copy_dir_recursive(src: &Path, dst: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());
        if file_type.is_dir() {
            copy_dir_recursive(&src_path, &dst_path)?;
        } else if file_type.is_file() {
            std::fs::copy(&src_path, &dst_path)?;
        }
    }
    Ok(())
}
