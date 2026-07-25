// Tauri layer for AI Second Brain Desktop: session persistence, workspace command discovery, and
// the #[tauri::command] handlers. Consumes `crate::bridge` only through its public contract
// (SpawnOptions / ClaudeSession / BridgeEvent / PermissionResponse / PermissionMode) — no
// process/NDJSON logic lives here.

use tauri::{Emitter, Manager};

use crate::bridge::CommandNoWindowExt;

pub const EVT_STATUS: &str = "claude:status";
pub const EVT_INIT: &str = "claude:init";
pub const EVT_BLOCK_START: &str = "claude:block-start";
pub const EVT_DELTA: &str = "claude:delta";
pub const EVT_BLOCK_STOP: &str = "claude:block-stop";
pub const EVT_MESSAGE: &str = "claude:message";
pub const EVT_TOOL_RESULT: &str = "claude:tool-result";
pub const EVT_PERMISSION: &str = "claude:permission-request";
/// Emitted for a `control_request` that isn't `can_use_tool` but does carry a question payload
/// (see `bridge::parse_generic_control_request`) — the frontend's QuestionModal, distinct from
/// the permission modal.
pub const EVT_QUESTION: &str = "claude:question-request";
pub const EVT_RESULT: &str = "claude:result";
pub const EVT_EXIT: &str = "claude:exit";
pub const EVT_STDERR: &str = "claude:stderr";
/// Emitted once, right before the automatic resume-less respawn kicked off by
/// `should_clear_ghost_resume` — lets the frontend drop a small notice into the timeline instead
/// of the session just silently going dead a second time.
pub const EVT_RESUME_FALLBACK: &str = "claude:resume-fallback";
/// Emitted when the CLI process exits within `EARLY_EXIT_WINDOW` of spawn with a nonzero code —
/// carries the collected stderr/stdout-diagnostic tail so the frontend can render a readable
/// error card instead of the user only seeing a bare diagnostics counter tick up.
pub const EVT_SPAWN_FAILURE: &str = "claude:spawn-failure";

/// How soon after spawn an exit counts as a "spawn failure" rather than a normal end-of-turn/
/// session-close exit.
const EARLY_EXIT_WINDOW: std::time::Duration = std::time::Duration::from_secs(3);
/// Cap on how many collected diagnostic lines are echoed back in a spawn-failure card — plenty
/// to show the actual error without unbounded growth for a pathologically chatty failure.
const SPAWN_FAILURE_TAIL_LINES: usize = 20;

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HarnessCommand {
    pub name: String,
    pub description: String,
    pub argument_hint: Option<String>,
}

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionMeta {
    pub session_id: String,
    pub title: String,
    pub created_at_ms: u64,
    pub updated_at_ms: u64,
    pub model: Option<String>,
    pub cum_usage: crate::bridge::Usage,
    pub cum_cost_usd: f64,
    pub num_turns: u64,
    #[serde(default)]
    pub preferred_model: Option<String>,
    #[serde(default)]
    pub preferred_effort: Option<String>,
    #[serde(default)]
    pub permission_mode: Option<crate::bridge::PermissionMode>,
    /// Which configured provider (`providers.json`) this session's CLI process talks to.
    /// Defaults to `"claude"` so sessions persisted before multi-provider support keep working
    /// unchanged.
    #[serde(default = "default_provider_id")]
    pub provider_id: String,
    #[serde(skip_deserializing, default)]
    pub live: bool,
    /// Computed fresh on every command that returns this meta to the frontend (never persisted:
    /// a provider's `supports_images` flag can change independently of the session) so the UI can
    /// gate the attach-image button. Defaults to `false` until a handler fills it in.
    #[serde(skip_deserializing, default)]
    pub supports_images: bool,
}

fn default_provider_id() -> String {
    "claude".to_string()
}

/// JSON file store. Missing or corrupt file loads as an empty Vec (never panics). Every
/// mutation rewrites the whole file synchronously.
pub struct SessionStore {
    path: std::path::PathBuf,
    inner: std::sync::Mutex<Vec<SessionMeta>>,
}

impl SessionStore {
    pub fn load(path: std::path::PathBuf) -> SessionStore {
        let sessions = std::fs::read_to_string(&path)
            .ok()
            .and_then(|raw| serde_json::from_str::<Vec<SessionMeta>>(&raw).ok())
            .unwrap_or_default();
        SessionStore {
            path,
            inner: std::sync::Mutex::new(sessions),
        }
    }

    fn persist(&self, sessions: &[SessionMeta]) {
        if let Ok(json) = serde_json::to_string_pretty(sessions) {
            if let Err(e) = std::fs::write(&self.path, json) {
                eprintln!("[ai-second-brain-desktop] failed to persist sessions.json: {e}");
            }
        }
    }

    /// Newest updated_at_ms first.
    pub fn list(&self) -> Vec<SessionMeta> {
        let mut sessions = self.inner.lock().unwrap().clone();
        sessions.sort_by(|a, b| b.updated_at_ms.cmp(&a.updated_at_ms));
        sessions
    }

    pub fn get(&self, session_id: &str) -> Option<SessionMeta> {
        self.inner
            .lock()
            .unwrap()
            .iter()
            .find(|m| m.session_id == session_id)
            .cloned()
    }

    pub fn upsert(&self, meta: SessionMeta) {
        let mut sessions = self.inner.lock().unwrap();
        match sessions.iter_mut().find(|m| m.session_id == meta.session_id) {
            Some(existing) => *existing = meta,
            None => sessions.push(meta),
        }
        self.persist(&sessions);
    }

    pub fn remove(&self, session_id: &str) {
        let mut sessions = self.inner.lock().unwrap();
        sessions.retain(|m| m.session_id != session_id);
        self.persist(&sessions);
    }
}

pub struct AppState {
    pub store: SessionStore,
    pub active: std::sync::Mutex<std::collections::HashMap<String, crate::bridge::ClaudeSession>>,
}

impl AppState {
    pub fn new(store: SessionStore) -> AppState {
        AppState {
            store,
            active: std::sync::Mutex::new(std::collections::HashMap::new()),
        }
    }
}

fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

fn emit_status(app: &tauri::AppHandle, session_id: &str, state: &str, detail: Option<&str>) {
    let _ = app.emit(
        EVT_STATUS,
        serde_json::json!({
            "sessionId": session_id,
            "state": state,
            "detail": detail,
        }),
    );
}

/// Internal (not a command). Spawns the CLI for `session_id` if it is not already live and
/// wires a detached forwarder task that turns `BridgeEvent`s into `claude:*` emits.
///
/// INTERPRETATION NOTE: the contract lists this helper without `async`, but it must await
/// `bridge::spawn_session` (an async fn) to get back the `(ClaudeSession, Receiver)` pair before
/// it can insert into `active` and return `Ok`/`Err` to the caller. Tauri async commands already
/// run on the async runtime, so a blocking `block_on` here would panic ("cannot block the current
/// thread from within a runtime"). Making this helper `async fn` and `.await`-ing it from every
/// command that calls it is the only construction that both compiles and matches the documented
/// behavior (spawn returns immediately; only the detached forwarder loop keeps running).
async fn ensure_session_running(
    app: &tauri::AppHandle,
    session_id: &str,
    resume: bool,
) -> Result<(), String> {
    let state = app.state::<AppState>();

    if state.active.lock().unwrap().contains_key(session_id) {
        return Ok(());
    }

    let meta = state.store.get(session_id);
    let repo_root =
        crate::workspace::root().ok_or_else(|| "workspace not configured".to_string())?;

    // FULL AUTO (bypassPermissions) is a supported mode now — the frontend gates it behind an
    // explicit confirm modal before ever letting a session settings write set it, so this is a
    // straight pass-through of whatever the stored session meta carries.
    let permission_mode = meta
        .as_ref()
        .and_then(|m| m.permission_mode)
        .unwrap_or(crate::bridge::PermissionMode::Manual);

    // Resolve the session's provider (defaulting to "claude" for sessions predating multi-
    // provider support, or if the referenced id was since removed) and build its env overlay.
    // Empty for "claude" — subscription login never gets an env override.
    let provider_id = meta
        .as_ref()
        .map(|m| m.provider_id.clone())
        .unwrap_or_else(default_provider_id);
    let provider_store = app.state::<crate::providers::ProviderStore>();
    let provider = provider_store.get_raw(&provider_id);
    let is_claude_provider = provider
        .as_ref()
        .map(|p| p.kind == crate::providers::KIND_CLAUDE)
        .unwrap_or(true); // unknown/removed provider id degrades to the claude default, never guesses non-claude
    let preferred_model = meta.as_ref().and_then(|m| m.preferred_model.clone());

    // Per-session model selection reaches the CLI two different ways depending on the provider:
    // `claude` accepts an Anthropic model name (fable/opus/sonnet/haiku/full name) straight on
    // `--model`; every other provider's own model names (e.g. "glm-4.6", "kimi-k2-turbo-preview")
    // mean nothing to that flag, so the override has to travel via `ANTHROPIC_MODEL` instead —
    // `provider_env_vars_for_session` is what threads `preferred_model` into that env overlay,
    // taking priority over the provider's own persisted default model.
    let mut extra_env = provider
        .as_ref()
        .map(|p| crate::providers::provider_env_vars_for_session(p, preferred_model.as_deref()))
        .unwrap_or_default();

    // Harness runtime vars. Hooks and Python-backed skills must never assume a `python3` on PATH
    // (there isn't one on stock Windows), so they read the managed interpreter from `ASB_PYTHON`.
    // Only set when the venv actually exists: an env var pointing at a missing interpreter is
    // worse than an absent one, because a skill would trust it and fail confusingly.
    if let Ok(app_data_dir) = app.path().app_data_dir() {
        if let Some(python) = crate::runtime::resolved_python(&app_data_dir) {
            extra_env.set(crate::runtime::ENV_PYTHON, python.to_string_lossy().as_ref());
        }
    }
    extra_env.set(
        crate::workspace::ENV_WORKSPACE,
        repo_root.to_string_lossy().as_ref(),
    );
    let model_flag = if is_claude_provider { preferred_model } else { None };

    let opts = crate::bridge::SpawnOptions {
        repo_root,
        session_id: session_id.to_string(),
        resume,
        permission_mode,
        model: model_flag,
        effort: meta.as_ref().and_then(|m| m.preferred_effort.clone()),
        extra_env,
    };

    let (session, rx) = crate::bridge::spawn_session(opts)
        .await
        .map_err(|e| e.to_string())?;

    // Standard sync `MutexGuard` is not `Send`, so it must never be alive across an `.await` —
    // the guard's scope below is closed (block ends) before the possible `shutdown().await`.
    let loser = {
        let mut active = state.active.lock().unwrap();
        if active.contains_key(session_id) {
            // Lost a race with a concurrent ensure_session_running for the same id: drop the
            // handle we just spawned and keep whichever one got inserted first.
            Some(session)
        } else {
            active.insert(session_id.to_string(), session);
            None
        }
    };
    if let Some(loser) = loser {
        let _ = loser.shutdown().await;
        return Ok(());
    }

    emit_status(app, session_id, "starting", None);

    let app_handle = app.clone();
    let sid = session_id.to_string();
    tauri::async_runtime::spawn(async move {
        forward_events(app_handle, sid, rx, resume).await;
    });

    Ok(())
}

/// Plain (non-`async fn`) wrapper around `ensure_session_running` that returns a boxed,
/// type-erased future instead of `ensure_session_running`'s own opaque `impl Future`.
///
/// `forward_events` needs to call back into `ensure_session_running` for the ghost-resume
/// fallback respawn, and `ensure_session_running` itself spawns `forward_events` — an `async fn`
/// calling another `async fn` that (transitively) calls it back forms a cycle the compiler can't
/// resolve when computing each one's opaque return type (E0391 "cycle detected... verify auto
/// trait bounds"). Boxing this one call site as `Pin<Box<dyn Future>>` gives it a concrete,
/// non-opaque type and breaks the cycle; the ordinary (non-recursive) call sites elsewhere keep
/// calling `ensure_session_running` directly.
fn ensure_session_running_boxed(
    app: tauri::AppHandle,
    session_id: String,
    resume: bool,
) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<(), String>> + Send>> {
    Box::pin(async move { ensure_session_running(&app, &session_id, resume).await })
}

/// Detached per-session task: drains the bridge event channel for the lifetime of the process
/// and maps every `BridgeEvent` onto the `claude:*` IPC events, always attaching `sessionId`.
///
/// `resume` is whatever this particular spawn used for `--resume`/`--session-id` (see
/// `SpawnOptions::resume`) — it gates the ghost-resume fallback below: only a spawn that actually
/// asked the CLI to resume a prior conversation can turn out to be resuming a "ghost" (ANDed with
/// `should_clear_ghost_resume`'s own no-Init + marker check). The fallback respawn always uses
/// `resume: false`, so it can never itself re-trigger this branch — the retry happens at most once.
async fn forward_events(
    app: tauri::AppHandle,
    session_id: String,
    mut rx: tokio::sync::mpsc::Receiver<crate::bridge::BridgeEvent>,
    resume: bool,
) {
    use crate::bridge::BridgeEvent;

    let mut saw_init = false;
    let mut output_lines: Vec<String> = Vec::new();
    let spawned_at = std::time::Instant::now();

    while let Some(event) = rx.recv().await {
        match &event {
            BridgeEvent::Init { .. } => saw_init = true,
            BridgeEvent::Stderr { line } => output_lines.push(line.clone()),
            _ => {}
        }

        match event {
            BridgeEvent::Init {
                session_id: _,
                model,
                permission_mode,
                claude_code_version,
                cwd,
                slash_commands,
                agents,
            } => {
                let _ = app.emit(
                    EVT_INIT,
                    serde_json::json!({
                        "sessionId": session_id,
                        "model": model,
                        "permissionMode": permission_mode,
                        "claudeCodeVersion": claude_code_version,
                        "cwd": cwd,
                        "slashCommands": slash_commands,
                        "agents": agents,
                    }),
                );
                emit_status(&app, &session_id, "ready", None);
            }
            BridgeEvent::Status { status, detail } => {
                emit_status(&app, &session_id, &status, detail.as_deref());
            }
            BridgeEvent::BlockStart {
                index,
                block_type,
                tool_use_id,
                tool_name,
            } => {
                let _ = app.emit(
                    EVT_BLOCK_START,
                    serde_json::json!({
                        "sessionId": session_id,
                        "index": index,
                        "blockType": block_type,
                        "toolUseId": tool_use_id,
                        "toolName": tool_name,
                    }),
                );
            }
            BridgeEvent::Delta { index, kind, text } => {
                let _ = app.emit(
                    EVT_DELTA,
                    serde_json::json!({
                        "sessionId": session_id,
                        "index": index,
                        "kind": kind,
                        "text": text,
                    }),
                );
            }
            BridgeEvent::BlockStop { index } => {
                let _ = app.emit(
                    EVT_BLOCK_STOP,
                    serde_json::json!({
                        "sessionId": session_id,
                        "index": index,
                    }),
                );
            }
            BridgeEvent::AssistantMessage { model, content } => {
                let _ = app.emit(
                    EVT_MESSAGE,
                    serde_json::json!({
                        "sessionId": session_id,
                        "model": model,
                        "content": content,
                    }),
                );
            }
            BridgeEvent::ToolResult {
                tool_use_id,
                content,
                is_error,
            } => {
                let _ = app.emit(
                    EVT_TOOL_RESULT,
                    serde_json::json!({
                        "sessionId": session_id,
                        "toolUseId": tool_use_id,
                        "content": content,
                        "isError": is_error,
                    }),
                );
            }
            BridgeEvent::PermissionRequest {
                request_id,
                tool_name,
                input,
                description,
                suggestions,
                blocked_path,
                tool_use_id,
                display_name,
            } => {
                let _ = app.emit(
                    EVT_PERMISSION,
                    serde_json::json!({
                        "sessionId": session_id,
                        "requestId": request_id,
                        "toolName": tool_name,
                        "input": input,
                        "description": description,
                        "suggestions": suggestions,
                        "blockedPath": blocked_path,
                        "toolUseId": tool_use_id,
                        "displayName": display_name,
                    }),
                );
            }
            BridgeEvent::QuestionRequest {
                request_id,
                subtype,
                title,
                body,
                options,
                allow_free_text,
            } => {
                let _ = app.emit(
                    EVT_QUESTION,
                    serde_json::json!({
                        "sessionId": session_id,
                        "requestId": request_id,
                        "subtype": subtype,
                        "title": title,
                        "body": body,
                        "options": options,
                        "allowFreeText": allow_free_text,
                    }),
                );
            }
            BridgeEvent::TurnResult {
                subtype,
                is_error,
                result,
                num_turns,
                duration_ms,
                total_cost_usd,
                usage,
                model,
                permission_denials,
            } => {
                let _ = app.emit(
                    EVT_RESULT,
                    serde_json::json!({
                        "sessionId": session_id,
                        "subtype": subtype,
                        "isError": is_error,
                        "result": result,
                        "numTurns": num_turns,
                        "durationMs": duration_ms,
                        "totalCostUsd": total_cost_usd,
                        "usage": usage,
                        "model": model,
                        "permissionDenials": permission_denials,
                    }),
                );

                let state = app.state::<AppState>();
                let now = now_ms();
                let mut meta = state.store.get(&session_id).unwrap_or_else(|| SessionMeta {
                    session_id: session_id.clone(),
                    title: "New session".to_string(),
                    created_at_ms: now,
                    updated_at_ms: now,
                    model: None,
                    cum_usage: crate::bridge::Usage::default(),
                    cum_cost_usd: 0.0,
                    num_turns: 0,
                    preferred_model: None,
                    preferred_effort: None,
                    permission_mode: None,
                    provider_id: default_provider_id(),
                    live: false,
                    supports_images: false,
                });
                meta.cum_usage.input_tokens += usage.input_tokens;
                meta.cum_usage.output_tokens += usage.output_tokens;
                meta.cum_usage.cache_read_input_tokens += usage.cache_read_input_tokens;
                meta.cum_usage.cache_creation_input_tokens += usage.cache_creation_input_tokens;
                meta.cum_cost_usd += total_cost_usd;
                meta.num_turns += num_turns;
                if model.is_some() {
                    meta.model = model;
                }
                meta.updated_at_ms = now;
                state.store.upsert(meta);

                emit_status(&app, &session_id, "ready", None);
            }
            BridgeEvent::Stderr { line } => {
                let _ = app.emit(
                    EVT_STDERR,
                    serde_json::json!({
                        "sessionId": session_id,
                        "line": line,
                    }),
                );
            }
            BridgeEvent::Other { raw } => {
                // Unmapped system/control lines (rate_limit_event, control_response acks, ...):
                // logged for diagnostics and dropped, per contract (v1).
                eprintln!("[ai-second-brain-desktop] unhandled bridge event ({session_id}): {raw}");
            }
            BridgeEvent::Exited { code } => {
                state_remove_active(&app, &session_id);

                // A ghost `--resume` target: the process died before ever producing an Init and
                // the CLI told us why. Clear the dead resume attempt and respawn fresh, once —
                // `resume: false` on the retry means this branch can never fire for it again.
                if resume && crate::bridge::should_clear_ghost_resume(saw_init, &output_lines) {
                    let _ = app.emit(
                        EVT_RESUME_FALLBACK,
                        serde_json::json!({ "sessionId": session_id }),
                    );
                    let app_handle = app.clone();
                    let sid = session_id.clone();
                    tauri::async_runtime::spawn(async move {
                        let _ = ensure_session_running_boxed(app_handle, sid, false).await;
                    });
                } else if spawned_at.elapsed() < EARLY_EXIT_WINDOW
                    && matches!(code, Some(c) if c != 0)
                {
                    // Not a resumable ghost — a genuine early spawn failure (bad provider config,
                    // missing binary, immediate crash, ...). Surface the actual diagnostic tail
                    // instead of leaving the user staring at a dead composer.
                    let start = output_lines.len().saturating_sub(SPAWN_FAILURE_TAIL_LINES);
                    let tail = output_lines[start..].join("\n");
                    let _ = app.emit(
                        EVT_SPAWN_FAILURE,
                        serde_json::json!({
                            "sessionId": session_id,
                            "code": code,
                            "stderrTail": tail,
                        }),
                    );
                }

                let _ = app.emit(
                    EVT_EXIT,
                    serde_json::json!({
                        "sessionId": session_id,
                        "code": code,
                    }),
                );
                emit_status(&app, &session_id, "exited", None);
            }
        }
    }
}

fn state_remove_active(app: &tauri::AppHandle, session_id: &str) {
    let state = app.state::<AppState>();
    state.active.lock().unwrap().remove(session_id);
}

/// Strips one layer of matching single/double quotes and surrounding whitespace, as seen in
/// frontmatter values (`description: "..."` vs bare `description: ...`).
fn strip_quotes(raw: &str) -> String {
    let s = raw.trim();
    let bytes = s.as_bytes();
    if bytes.len() >= 2
        && ((bytes[0] == b'"' && bytes[bytes.len() - 1] == b'"')
            || (bytes[0] == b'\'' && bytes[bytes.len() - 1] == b'\''))
    {
        s[1..s.len() - 1].to_string()
    } else {
        s.to_string()
    }
}

/// Strips common markdown-inline noise from a single line so it reads as plain prose in the
/// command-rail preview: leading heading (`#`), blockquote (`>`), and list markers (`-`, `*`,
/// `+`, `1.`, `1)`); bold/italic/backtick markers (`*`, `_`, `` ` ``); `[text](url)` link syntax
/// collapsed to just `text`; and any run of whitespace collapsed to a single space. Pure function
/// — no I/O, easy to unit test in isolation from file parsing.
fn strip_markdown_inline(s: &str) -> String {
    let mut t = s.trim();

    // Strip leading block markers, repeatedly (e.g. "> - item", "## item").
    loop {
        let before = t;
        t = t.trim_start_matches('#').trim_start();
        t = t.trim_start_matches('>').trim_start();
        if let Some(rest) = t
            .strip_prefix("- ")
            .or_else(|| t.strip_prefix("* "))
            .or_else(|| t.strip_prefix("+ "))
        {
            t = rest.trim_start();
        } else {
            let digits_end = t.find(|c: char| !c.is_ascii_digit()).unwrap_or(0);
            if digits_end > 0 {
                if let Some(rest) = t[digits_end..]
                    .strip_prefix(". ")
                    .or_else(|| t[digits_end..].strip_prefix(") "))
                {
                    t = rest.trim_start();
                }
            }
        }
        if t == before {
            break;
        }
    }

    // Collapse `[text](url)` to `text` (single-pass, non-nested — good enough for a one-line
    // preview; a malformed/unterminated `[`/`(` just falls through unchanged below).
    let chars: Vec<char> = t.chars().collect();
    let mut out = String::with_capacity(chars.len());
    let mut i = 0usize;
    while i < chars.len() {
        if chars[i] == '[' {
            if let Some(close_rel) = chars[i..].iter().position(|&c| c == ']') {
                let close_idx = i + close_rel;
                if chars.get(close_idx + 1) == Some(&'(') {
                    if let Some(paren_rel) = chars[close_idx + 2..].iter().position(|&c| c == ')')
                    {
                        let text: String = chars[i + 1..close_idx].iter().collect();
                        out.push_str(&text);
                        i = close_idx + 2 + paren_rel + 1;
                        continue;
                    }
                }
            }
        }
        out.push(chars[i]);
        i += 1;
    }

    // Drop bold/italic/backtick marker characters outright.
    let out: String = out.chars().filter(|&c| c != '*' && c != '_' && c != '`').collect();

    out.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Truncates `s` to at most `max_chars` characters (counting Unicode scalar values, never
/// splitting a multi-byte codepoint), appending `…` in place of the last character when it had
/// to cut anything.
fn truncate_with_ellipsis(s: &str, max_chars: usize) -> String {
    if s.chars().count() <= max_chars {
        return s.to_string();
    }
    let keep = max_chars.saturating_sub(1);
    let mut truncated: String = s.chars().take(keep).collect();
    truncated.push('…');
    truncated
}

/// Parses one `.claude/commands/*.md` file into a `HarnessCommand`. Handles both observed
/// frontmatter forms (bare and quoted values) and the no-frontmatter case (e.g. `glm.md`, which
/// opens straight on a `# /glm` heading with no `---` fence at all).
fn parse_harness_command(name: String, content: &str) -> HarnessCommand {
    let lines: Vec<&str> = content.lines().collect();
    let mut description: Option<String> = None;
    let mut argument_hint: Option<String> = None;
    let mut body_start = 0usize;

    if lines.first().map(|l| l.trim()) == Some("---") {
        let mut i = 1usize;
        let mut fence_end = lines.len();
        while i < lines.len() {
            if lines[i].trim() == "---" {
                fence_end = i;
                break;
            }
            let trimmed = lines[i].trim_start();
            if let Some(rest) = trimmed.strip_prefix("description:") {
                description = Some(strip_quotes(rest));
            } else if let Some(rest) = trimmed.strip_prefix("argument-hint:") {
                argument_hint = Some(strip_quotes(rest));
            }
            i += 1;
        }
        body_start = (fence_end + 1).min(lines.len());
    }

    if description.is_none() {
        for line in &lines[body_start..] {
            let t = line.trim();
            if t.is_empty() {
                continue;
            }
            let cleaned = strip_markdown_inline(t);
            if cleaned.is_empty() {
                continue;
            }
            description = Some(truncate_with_ellipsis(&cleaned, 80));
            break;
        }
    }

    HarnessCommand {
        name,
        description: description.unwrap_or_default(),
        argument_hint,
    }
}

#[cfg(test)]
mod parse_harness_command_tests {
    use super::*;

    #[test]
    fn strip_markdown_inline_strips_heading_marker() {
        assert_eq!(strip_markdown_inline("## /glm"), "/glm");
    }

    #[test]
    fn strip_markdown_inline_strips_blockquote_marker() {
        assert_eq!(strip_markdown_inline("> quoted note"), "quoted note");
    }

    #[test]
    fn strip_markdown_inline_strips_bullet_markers() {
        assert_eq!(strip_markdown_inline("- do the thing"), "do the thing");
        assert_eq!(strip_markdown_inline("* do the thing"), "do the thing");
        assert_eq!(strip_markdown_inline("+ do the thing"), "do the thing");
    }

    #[test]
    fn strip_markdown_inline_strips_ordered_list_markers() {
        assert_eq!(strip_markdown_inline("1. do the thing"), "do the thing");
        assert_eq!(strip_markdown_inline("2) do the thing"), "do the thing");
    }

    #[test]
    fn strip_markdown_inline_strips_emphasis_and_code_markers() {
        assert_eq!(
            strip_markdown_inline("**bold** and *italic* and `code`"),
            "bold and italic and code"
        );
    }

    #[test]
    fn strip_markdown_inline_collapses_link_syntax() {
        assert_eq!(
            strip_markdown_inline("see [the docs](https://example.com/docs) for detail"),
            "see the docs for detail"
        );
    }

    #[test]
    fn strip_markdown_inline_collapses_whitespace() {
        assert_eq!(strip_markdown_inline("a    b\tc"), "a b c");
    }

    #[test]
    fn strip_markdown_inline_combines_multiple_leading_markers() {
        assert_eq!(strip_markdown_inline("> - **task**"), "task");
    }

    #[test]
    fn truncate_with_ellipsis_leaves_short_strings_untouched() {
        assert_eq!(truncate_with_ellipsis("short", 80), "short");
    }

    #[test]
    fn truncate_with_ellipsis_cuts_on_char_boundary_with_ellipsis() {
        let long = "a".repeat(100);
        let truncated = truncate_with_ellipsis(&long, 80);
        assert_eq!(truncated.chars().count(), 80);
        assert!(truncated.ends_with('…'));
        assert_eq!(&truncated[..79], &"a".repeat(79));
    }

    #[test]
    fn truncate_with_ellipsis_never_splits_a_multibyte_codepoint() {
        // Every char here is a multi-byte UTF-8 scalar; a byte-based truncate would panic.
        let long: String = std::iter::repeat('é').take(100).collect();
        let truncated = truncate_with_ellipsis(&long, 80);
        assert_eq!(truncated.chars().count(), 80);
        assert!(truncated.ends_with('…'));
    }

    #[test]
    fn parse_harness_command_fallback_uses_cleaned_first_body_line() {
        let content =
            "---\n---\n- **Step one**: do [the thing](https://x.example/y) now\nmore text";
        let cmd = parse_harness_command("demo".to_string(), content);
        assert_eq!(cmd.description, "Step one: do the thing now");
    }

    #[test]
    fn parse_harness_command_fallback_truncates_long_first_line() {
        let long_line = "x ".repeat(60); // 120 chars before trimming/collapsing
        let content = format!("---\n---\n{long_line}");
        let cmd = parse_harness_command("demo".to_string(), &content);
        assert_eq!(cmd.description.chars().count(), 80);
        assert!(cmd.description.ends_with('…'));
    }

    #[test]
    fn parse_harness_command_prefers_frontmatter_description() {
        let content = "---\ndescription: \"Explicit description\"\n---\n# heading text ignored";
        let cmd = parse_harness_command("demo".to_string(), content);
        assert_eq!(cmd.description, "Explicit description");
    }

    #[test]
    fn command_token_extracts_slash_command_name() {
        assert_eq!(command_token("/mom please summarize"), "/mom");
        assert_eq!(command_token("  /weekly-report"), "/weekly-report");
    }

    #[test]
    fn command_token_is_freeform_for_plain_text() {
        assert_eq!(command_token("hey can you help me draft this"), "freeform");
        assert_eq!(command_token(""), "freeform");
    }

    #[test]
    fn command_token_never_leaks_message_content() {
        let secret = command_token("my password is hunter2, please remember it");
        assert_eq!(secret, "freeform");
        assert!(!secret.contains("hunter2"));
    }
}

// ---- #[tauri::command] handlers ----

#[tauri::command]
pub async fn list_harness_commands() -> Result<Vec<HarnessCommand>, String> {
    // No workspace configured yet, or a user-chosen bare folder with no .claude/commands: both
    // are legal states, not errors — the frontend already renders "No commands found" for [].
    let Some(root) = crate::workspace::root() else {
        return Ok(vec![]);
    };
    let commands_dir = root.join(".claude").join("commands");
    let Ok(dir) = std::fs::read_dir(&commands_dir) else {
        return Ok(vec![]);
    };
    let mut commands = Vec::new();
    for entry in dir {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("md") {
            continue;
        }
        let Some(name) = path.file_stem().and_then(|s| s.to_str()) else {
            continue;
        };
        let content = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
        commands.push(parse_harness_command(name.to_string(), &content));
    }
    commands.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(commands)
}

/// Looks up `provider_id` in the `ProviderStore` and returns its `supports_images` flag,
/// defaulting to `false` for an unknown/removed provider id rather than guessing.
fn provider_supports_images(app: &tauri::AppHandle, provider_id: &str) -> bool {
    let provider_store = app.state::<crate::providers::ProviderStore>();
    crate::providers::supports_images_for(&provider_store, provider_id)
}

#[tauri::command]
pub async fn list_sessions(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
) -> Result<Vec<SessionMeta>, String> {
    let active_ids: std::collections::HashSet<String> =
        state.active.lock().unwrap().keys().cloned().collect();
    let mut sessions = state.store.list();
    for meta in sessions.iter_mut() {
        meta.live = active_ids.contains(&meta.session_id);
        meta.supports_images = provider_supports_images(&app, &meta.provider_id);
    }
    Ok(sessions)
}

#[tauri::command]
pub async fn new_session(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    title: Option<String>,
    model: Option<String>,
    effort: Option<String>,
    permission_mode: Option<crate::bridge::PermissionMode>,
    provider_id: Option<String>,
) -> Result<SessionMeta, String> {
    let session_id = uuid::Uuid::new_v4().to_string();
    let now = now_ms();
    let provider_id = provider_id
        .filter(|v| !v.is_empty())
        .unwrap_or_else(default_provider_id);
    let mut meta = SessionMeta {
        session_id: session_id.clone(),
        title: title.unwrap_or_else(|| "New session".to_string()),
        created_at_ms: now,
        updated_at_ms: now,
        model: None,
        cum_usage: crate::bridge::Usage::default(),
        cum_cost_usd: 0.0,
        num_turns: 0,
        preferred_model: model,
        preferred_effort: effort,
        permission_mode,
        provider_id,
        live: false,
        supports_images: false,
    };
    state.store.upsert(meta.clone());

    ensure_session_running(&app, &session_id, false).await?;

    crate::account::record_event_internal(&app, "session_start", serde_json::json!({}));

    meta.live = true;
    meta.supports_images = provider_supports_images(&app, &meta.provider_id);
    Ok(meta)
}

#[tauri::command]
pub async fn send_message(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    session_id: String,
    text: String,
    attachments: Option<Vec<crate::bridge::ImageAttachment>>,
) -> Result<(), String> {
    let already_live = state.active.lock().unwrap().contains_key(&session_id);
    if !already_live {
        if state.store.get(&session_id).is_none() {
            return Err(format!("unknown session: {session_id}"));
        }
        // Not in the active map but known to the store: seamless auto-resume.
        ensure_session_running(&app, &session_id, true).await?;
    }

    let handle = {
        let active = state.active.lock().unwrap();
        active.get(&session_id).cloned()
    };
    let handle = handle.ok_or_else(|| format!("session failed to start: {session_id}"))?;

    // Telemetry only ever carries which command was invoked (or the literal "freeform"), never
    // the message text itself.
    let cmd = command_token(&text);
    crate::account::record_event_internal(
        &app,
        "command_run",
        serde_json::json!({ "cmd": cmd }),
    );

    let attachments = attachments.unwrap_or_default();
    handle
        .send_user_message(&text, &attachments)
        .await
        .map_err(|e| e.to_string())
}

/// Max source file size accepted by the attach-file picker. Kept generous since the frontend
/// already downscales anything large before it ever reaches disk via `save`; this is a backstop
/// against picking an arbitrary huge file directly from disk.
const MAX_IMAGE_FILE_BYTES: u64 = 10 * 1024 * 1024; // 10MB

/// Reads an image file from disk (chosen via the file picker) and returns it base64-encoded
/// with a best-effort MIME type, for the frontend to attach to an outgoing message. Tauri's
/// dialog plugin only returns a path, not file bytes, so this command bridges the gap without
/// needing an fs plugin.
#[tauri::command]
pub async fn read_image_file(path: String) -> Result<serde_json::Value, String> {
    let meta = std::fs::metadata(&path).map_err(|e| format!("cannot read {path}: {e}"))?;
    if meta.len() > MAX_IMAGE_FILE_BYTES {
        return Err(format!(
            "{path} is {} bytes, over the {MAX_IMAGE_FILE_BYTES} byte limit",
            meta.len()
        ));
    }
    let bytes = std::fs::read(&path).map_err(|e| format!("cannot read {path}: {e}"))?;
    let media_type = match std::path::Path::new(&path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase()
        .as_str()
    {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "bmp" => "image/bmp",
        _ => "application/octet-stream",
    };
    use base64::Engine;
    let data_base64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
    Ok(serde_json::json!({ "dataBase64": data_base64, "mediaType": media_type }))
}

/// Extracts the telemetry-safe "which command" label for a user message: the first whitespace
/// token (without the leading `/`) when the text starts with a slash command, else the literal
/// string `"freeform"`. Never returns any other part of the message content.
fn command_token(text: &str) -> String {
    let trimmed = text.trim_start();
    if let Some(rest) = trimmed.strip_prefix('/') {
        let token = rest.split_whitespace().next().unwrap_or("");
        format!("/{token}")
    } else {
        "freeform".to_string()
    }
}

#[tauri::command]
pub async fn respond_permission(
    state: tauri::State<'_, AppState>,
    session_id: String,
    request_id: String,
    allow: bool,
    updated_input: Option<serde_json::Value>,
    deny_message: Option<String>,
) -> Result<(), String> {
    let handle = {
        let active = state.active.lock().unwrap();
        active.get(&session_id).cloned()
    };
    let handle = handle.ok_or_else(|| format!("session not live: {session_id}"))?;

    // On allow, the frontend is contractually the one echoing back the original `input` object
    // (or its edited version) as `updated_input`. A missing value has no server-side "original"
    // to fall back to (only the forwarded event carried it, and that's frontend-side state), so
    // it degrades to `null` rather than guessing.
    let response = if allow {
        crate::bridge::PermissionResponse::Allow {
            updated_input: updated_input.unwrap_or(serde_json::Value::Null),
        }
    } else {
        crate::bridge::PermissionResponse::Deny {
            message: deny_message
                .unwrap_or_else(|| "Denied by user in AI Second Brain Desktop".to_string()),
        }
    };

    handle
        .respond_permission(&request_id, response)
        .await
        .map_err(|e| e.to_string())
}

/// Answers a `QuestionRequest` (see `EVT_QUESTION`/`bridge::BridgeEvent::QuestionRequest`).
/// Exactly one of `option_value`/`free_text` is expected from the frontend depending on which
/// path the QuestionModal used — `option_value` wins if somehow both are sent, since a clicked
/// option button is the more specific signal.
#[tauri::command]
pub async fn respond_question(
    state: tauri::State<'_, AppState>,
    session_id: String,
    request_id: String,
    option_value: Option<String>,
    free_text: Option<String>,
) -> Result<(), String> {
    let handle = {
        let active = state.active.lock().unwrap();
        active.get(&session_id).cloned()
    };
    let handle = handle.ok_or_else(|| format!("session not live: {session_id}"))?;

    let answer = match option_value {
        Some(value) => crate::bridge::QuestionAnswer::Option { value },
        None => crate::bridge::QuestionAnswer::FreeText {
            text: free_text.unwrap_or_default(),
        },
    };

    handle
        .respond_question(&request_id, answer)
        .await
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn interrupt_session(
    state: tauri::State<'_, AppState>,
    session_id: String,
) -> Result<(), String> {
    let handle = {
        let active = state.active.lock().unwrap();
        active.get(&session_id).cloned()
    };
    let Some(handle) = handle else {
        return Ok(()); // nothing live to interrupt
    };

    handle.interrupt().await.map_err(|e| e.to_string())?;

    // The forwarder removes `session_id` from `active` the moment it observes Exited (and stays
    // live through further TurnResults). Polling that flag is the only signal this command
    // handler has for "did a TurnResult/Exited land within 3s" without threading a second channel
    // through the forwarder, and it is cheap since this only runs on an explicit stop click.
    let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(3);
    while tokio::time::Instant::now() < deadline {
        let still_active = state.active.lock().unwrap().contains_key(&session_id);
        if !still_active {
            return Ok(());
        }
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    }

    if state.active.lock().unwrap().contains_key(&session_id) {
        handle.shutdown().await.map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub async fn close_session(
    state: tauri::State<'_, AppState>,
    session_id: String,
) -> Result<(), String> {
    let handle = {
        let active = state.active.lock().unwrap();
        active.get(&session_id).cloned()
    };
    match handle {
        Some(h) => h.shutdown().await.map_err(|e| e.to_string()),
        None => Ok(()),
    }
}

#[tauri::command]
pub async fn rename_session(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    session_id: String,
    title: String,
) -> Result<SessionMeta, String> {
    let mut meta = state
        .store
        .get(&session_id)
        .ok_or_else(|| format!("unknown session: {session_id}"))?;
    meta.title = title;
    meta.updated_at_ms = now_ms();
    state.store.upsert(meta.clone());
    meta.live = state.active.lock().unwrap().contains_key(&session_id);
    meta.supports_images = provider_supports_images(&app, &meta.provider_id);
    Ok(meta)
}

/// Persist-only: never touches a live process. Restart-to-apply is the frontend's job (it
/// closes the session and lets the next `send_message` auto-resume with the new flags).
#[tauri::command]
pub async fn set_session_settings(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    session_id: String,
    model: Option<String>,
    effort: Option<String>,
    permission_mode: Option<crate::bridge::PermissionMode>,
    provider_id: Option<String>,
) -> Result<SessionMeta, String> {
    let mut meta = state
        .store
        .get(&session_id)
        .ok_or_else(|| format!("unknown session: {session_id}"))?;

    if let Some(v) = model {
        meta.preferred_model = if v.is_empty() { None } else { Some(v) };
    }
    if let Some(v) = effort {
        meta.preferred_effort = if v.is_empty() { None } else { Some(v) };
    }
    if let Some(mode) = permission_mode {
        meta.permission_mode = Some(mode);
    }
    if let Some(v) = provider_id {
        if !v.is_empty() {
            meta.provider_id = v;
        }
    }

    meta.updated_at_ms = now_ms();
    state.store.upsert(meta.clone());
    meta.live = state.active.lock().unwrap().contains_key(&session_id);
    meta.supports_images = provider_supports_images(&app, &meta.provider_id);
    Ok(meta)
}

/// Thin wrapper over the bridge's pure transcript reader. Runs the blocking file read off the
/// async runtime via `spawn_blocking` (files up to ~400 KB). A missing workspace root or a
/// missing transcript are both not errors from the frontend's point of view (empty history just
/// falls back to the resume-note), so both degrade to `Ok(vec![])` here rather than propagating.
#[tauri::command]
pub async fn get_transcript(
    session_id: String,
) -> Result<Vec<crate::bridge::TranscriptEntry>, String> {
    let Some(root) = crate::workspace::root() else {
        return Ok(vec![]);
    };
    let workspace_root = root.to_string_lossy().to_string();
    tauri::async_runtime::spawn_blocking(move || {
        match crate::bridge::read_transcript(&workspace_root, &session_id) {
            Ok(entries) => Ok(entries),
            Err(crate::bridge::BridgeError::TranscriptNotFound) => Ok(vec![]),
            Err(e) => Err(e.to_string()),
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn delete_session(
    state: tauri::State<'_, AppState>,
    session_id: String,
) -> Result<(), String> {
    let handle = {
        let active = state.active.lock().unwrap();
        active.get(&session_id).cloned()
    };
    if let Some(h) = handle {
        let _ = h.shutdown().await;
        state.active.lock().unwrap().remove(&session_id);
    }
    state.store.remove(&session_id);
    Ok(())
}

// ---- onboarding: CLI detection, auth check, workspace resolution/creation ------------------

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CliDetection {
    pub found: bool,
    pub path: Option<String>,
    pub version: Option<String>,
    pub install_command: String,
    pub os: String,
}

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AuthCheck {
    pub authenticated: bool,
    pub detail: Option<String>,
}

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkspaceStatus {
    pub configured: bool,
    pub root: Option<String>,
    pub source: Option<crate::workspace::Source>,
    pub error: Option<String>,
    pub default_path: String,
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

fn install_command_for_os() -> &'static str {
    if cfg!(target_os = "windows") {
        "irm https://claude.ai/install.ps1 | iex"
    } else {
        "curl -fsSL https://claude.ai/install.sh | bash"
    }
}

/// Last `n` **characters** (not bytes) of `s`, so multi-byte UTF-8 is never sliced mid-codepoint.
fn last_n_chars(s: &str, n: usize) -> String {
    let total = s.chars().count();
    if total <= n {
        s.to_string()
    } else {
        s.chars().skip(total - n).collect()
    }
}

fn workspace_status_for(app_data_dir: &std::path::Path) -> WorkspaceStatus {
    let default_path = app_data_dir
        .join(crate::workspace::DEFAULT_WORKSPACE_DIR_NAME)
        .to_string_lossy()
        .to_string();
    match crate::workspace::resolve(app_data_dir) {
        crate::workspace::ResolveOutcome::Resolved { root, source } => WorkspaceStatus {
            configured: true,
            root: Some(root.to_string_lossy().to_string()),
            source: Some(source),
            error: None,
            default_path,
        },
        crate::workspace::ResolveOutcome::NotConfigured => WorkspaceStatus {
            configured: false,
            root: None,
            source: None,
            error: None,
            default_path,
        },
        crate::workspace::ResolveOutcome::Invalid {
            attempted: _,
            source,
            reason,
        } => WorkspaceStatus {
            configured: false,
            root: None,
            source: Some(source),
            error: Some(reason),
            default_path,
        },
    }
}

/// Detects the `claude` CLI via `bridge::resolve_claude_bin()` (PATH + well-known-dir fallbacks)
/// and, if found, asks it for its version. Never runs an installer — this version only shows the
/// per-OS install command with a copy button and lets the user re-check.
#[tauri::command]
pub async fn detect_cli() -> Result<CliDetection, String> {
    let os = current_os_name().to_string();
    let install_command = install_command_for_os().to_string();

    let Ok(bin) = crate::bridge::resolve_claude_bin() else {
        return Ok(CliDetection {
            found: false,
            path: None,
            version: None,
            install_command,
            os,
        });
    };

    let mut cmd = tokio::process::Command::new(&bin);
    cmd.no_window()
        .arg("--version")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .kill_on_drop(true);

    let version = match cmd.spawn() {
        Ok(child) => {
            match tokio::time::timeout(std::time::Duration::from_secs(2), child.wait_with_output())
                .await
            {
                Ok(Ok(output)) if output.status.success() => {
                    let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
                    if text.is_empty() {
                        None
                    } else {
                        Some(text)
                    }
                }
                _ => None,
            }
        }
        Err(_) => None,
    };

    Ok(CliDetection {
        found: true,
        path: Some(bin.to_string_lossy().to_string()),
        version,
        install_command,
        os,
    })
}

/// Spawns a trivial headless prompt to determine whether the resolved `claude` CLI is logged in.
/// Runs with `cwd` = the app-data dir (NOT the workspace) so no user `CLAUDE.md` loads. Exit code
/// is the sole source of truth (never string-matched against stderr/stdout: a known headless
/// false-negative gotcha with "Not logged in").
#[tauri::command]
pub async fn check_auth(app: tauri::AppHandle) -> Result<AuthCheck, String> {
    let Ok(bin) = crate::bridge::resolve_claude_bin() else {
        return Ok(AuthCheck {
            authenticated: false,
            detail: Some("claude CLI not found".to_string()),
        });
    };

    let app_data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&app_data_dir).map_err(|e| e.to_string())?;

    let mut cmd = tokio::process::Command::new(&bin);
    cmd.no_window()
        .current_dir(&app_data_dir)
        .arg("-p")
        .arg("Reply with the single word: ok")
        .arg("--output-format")
        .arg("json")
        .arg("--max-turns")
        .arg("1")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);

    let child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            return Ok(AuthCheck {
                authenticated: false,
                detail: Some(e.to_string()),
            })
        }
    };

    // On timeout, the `wait_with_output()` future (which owns `child`) is dropped, and
    // `kill_on_drop(true)` above ensures the process is killed rather than left running.
    match tokio::time::timeout(std::time::Duration::from_secs(90), child.wait_with_output()).await
    {
        Ok(Ok(output)) => {
            if output.status.success() {
                Ok(AuthCheck {
                    authenticated: true,
                    detail: None,
                })
            } else {
                let mut combined = String::from_utf8_lossy(&output.stderr).to_string();
                combined.push_str(&String::from_utf8_lossy(&output.stdout));
                Ok(AuthCheck {
                    authenticated: false,
                    detail: Some(last_n_chars(&combined, 500)),
                })
            }
        }
        Ok(Err(e)) => Ok(AuthCheck {
            authenticated: false,
            detail: Some(e.to_string()),
        }),
        Err(_) => Ok(AuthCheck {
            authenticated: false,
            detail: Some("timed out".to_string()),
        }),
    }
}

/// Re-runs workspace resolution and reports the outcome, always including `default_path` (used by
/// the create-workspace screen even when nothing is configured yet).
#[tauri::command]
pub async fn get_workspace_status(app: tauri::AppHandle) -> Result<WorkspaceStatus, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    Ok(workspace_status_for(&app_data_dir))
}

/// Resolves the bundled workspace-template directory. The bundle ships `commands/` (not
/// `.claude/commands/`) because Tauri resource globs and per-OS bundlers are unreliable with
/// dot-directories; the map-form `resources` entry in tauri.conf.json can land the copy at
/// either of two spots depending on dev vs. bundled build, so both are probed here.
fn resolve_template_dir(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    let primary = app
        .path()
        .resolve("resources/workspace-template", tauri::path::BaseDirectory::Resource)
        .map_err(|e| e.to_string())?;
    if primary.is_dir() {
        return Ok(primary);
    }
    let fallback = app
        .path()
        .resource_dir()
        .map_err(|e| e.to_string())?
        .join("workspace-template");
    if fallback.is_dir() {
        Ok(fallback)
    } else {
        Err(format!(
            "bundled workspace template not found (tried {} and {})",
            primary.display(),
            fallback.display()
        ))
    }
}

/// Copies every bundled template command that is MISSING from the workspace's
/// `.claude/commands/` into it. Never overwrites an existing file, so user edits are safe.
/// Returns how many files were copied. This is what heals workspaces created by older builds
/// (whose template had fewer/no commands) and bare user-chosen folders — without it, the rail
/// shows "No commands found" forever and slash commands silently do nothing.
pub fn sync_template_commands(app: &tauri::AppHandle) -> Result<usize, String> {
    let Some(root) = crate::workspace::root() else {
        return Ok(0);
    };
    let template_dir = resolve_template_dir(app)?;
    let commands_src = template_dir.join("commands");
    let commands_dst = root.join(".claude").join("commands");
    std::fs::create_dir_all(&commands_dst).map_err(|e| e.to_string())?;
    let mut copied = 0usize;
    for entry in std::fs::read_dir(&commands_src).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let src_path = entry.path();
        if src_path.extension().and_then(|e| e.to_str()) != Some("md") {
            continue;
        }
        let dst_path = commands_dst.join(entry.file_name());
        if dst_path.exists() {
            continue;
        }
        std::fs::copy(&src_path, &dst_path).map_err(|e| e.to_string())?;
        copied += 1;
    }
    Ok(copied)
}

/// Frontend-triggered variant of [`sync_template_commands`], wired to the
/// "Restore starter commands" button in the (empty) command rail.
#[tauri::command]
pub async fn restore_template_commands(app: tauri::AppHandle) -> Result<usize, String> {
    sync_template_commands(&app)
}

/// Creates a new workspace from the bundled starter template at `path` (or the default
/// `<app_data_dir>/workspace` if `path` is `None`), then persists it as the configured workspace.
/// Refuses to write into an existing non-empty directory.
#[tauri::command]
pub async fn create_workspace(
    app: tauri::AppHandle,
    path: Option<String>,
) -> Result<WorkspaceStatus, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let default_path = app_data_dir.join(crate::workspace::DEFAULT_WORKSPACE_DIR_NAME);
    let target = match path {
        Some(p) if !p.trim().is_empty() => std::path::PathBuf::from(p),
        _ => default_path,
    };

    if target.exists() {
        let non_empty = std::fs::read_dir(&target)
            .map(|mut it| it.next().is_some())
            .unwrap_or(false);
        if non_empty {
            return Err(format!("Directory is not empty: {}", target.display()));
        }
    }

    let template_dir = resolve_template_dir(&app)?;

    std::fs::create_dir_all(&target).map_err(|e| e.to_string())?;

    for file_name in ["CLAUDE.md", "README.md"] {
        let src = template_dir.join(file_name);
        let dst = target.join(file_name);
        std::fs::copy(&src, &dst).map_err(|e| format!("failed to copy {file_name}: {e}"))?;
    }
    for dir_name in ["inbox", "notes"] {
        let src = template_dir.join(dir_name);
        let dst = target.join(dir_name);
        crate::workspace::copy_dir_recursive(&src, &dst)
            .map_err(|e| format!("failed to copy {dir_name}/: {e}"))?;
    }

    // Remap commands/*.md -> .claude/commands/*.md at extraction time.
    let commands_src = template_dir.join("commands");
    let commands_dst = target.join(".claude").join("commands");
    std::fs::create_dir_all(&commands_dst).map_err(|e| e.to_string())?;
    for entry in std::fs::read_dir(&commands_src).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let src_path = entry.path();
        if src_path.extension().and_then(|e| e.to_str()) == Some("md") {
            let dst_path = commands_dst.join(entry.file_name());
            std::fs::copy(&src_path, &dst_path).map_err(|e| e.to_string())?;
        }
    }

    let cfg = crate::workspace::WorkspaceConfig {
        version: 1,
        workspace_root: target.to_string_lossy().to_string(),
        created_from_template: true,
        template_version: Some(env!("CARGO_PKG_VERSION").to_string()),
    };
    crate::workspace::save_config(&app_data_dir, &cfg)?;
    crate::workspace::set_root(target);

    Ok(workspace_status_for(&app_data_dir))
}

// ---- managed Python runtime ----

/// Reports whether the managed interpreter exists, where `uv` was found, and whether the current
/// workspace declares dependencies. Cheap enough to poll from the settings panel.
#[tauri::command]
pub async fn runtime_status(app: tauri::AppHandle) -> Result<crate::runtime::RuntimeStatus, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let workspace = crate::workspace::root();
    Ok(crate::runtime::status(&app_data_dir, workspace.as_deref()))
}

/// Creates the managed virtualenv and installs the workspace's `requirements.txt` into it.
/// Returns a short human-readable log for the onboarding wizard to display.
#[tauri::command]
pub async fn runtime_bootstrap(app: tauri::AppHandle) -> Result<String, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let workspace = crate::workspace::root().ok_or_else(|| {
        "No workspace is configured yet, so there are no dependencies to install.".to_string()
    })?;
    crate::runtime::bootstrap(&app_data_dir, &workspace).await
}

/// Deletes the managed runtime and rebuilds it from scratch. The "repair" path for when a
/// half-finished install leaves the venv unusable.
#[tauri::command]
pub async fn runtime_repair(app: tauri::AppHandle) -> Result<String, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    crate::runtime::reset(&app_data_dir)?;
    let workspace = crate::workspace::root().ok_or_else(|| {
        "No workspace is configured yet, so there are no dependencies to install.".to_string()
    })?;
    crate::runtime::bootstrap(&app_data_dir, &workspace).await
}

// ---- managed 9Router proxy ----

/// Whether 9Router is installed, running, and ours. Cheap enough for the provider card to poll.
#[tauri::command]
pub async fn ninerouter_status() -> Result<crate::ninerouter::NineRouterStatus, String> {
    Ok(crate::ninerouter::status().await)
}

/// `npm install -g 9router`. Minutes long on a cold cache, so the frontend must show progress
/// rather than block.
#[tauri::command]
pub async fn ninerouter_install() -> Result<String, String> {
    crate::ninerouter::install().await
}

/// Starts the proxy and waits until it answers.
#[tauri::command]
pub async fn ninerouter_start() -> Result<String, String> {
    crate::ninerouter::start().await
}

/// Model ids the running proxy can route to. Empty-list and not-running both come back as errors
/// with a next step in them, since the picker has nothing useful to show in either case.
#[tauri::command]
pub async fn ninerouter_models() -> Result<Vec<String>, String> {
    crate::ninerouter::models().await
}

/// Stops the proxy, but only if this app is the one that started it.
#[tauri::command]
pub async fn ninerouter_stop() -> Result<(), String> {
    crate::ninerouter::stop();
    Ok(())
}

/// Best-effort attempt to open the OS's terminal running `claude /login`, for non-technical
/// users who don't have a terminal already open. Never blocks on the login itself — just spawns
/// a detached terminal process and returns immediately. Any failure (no supported terminal
/// emulator found, spawn error, etc.) is surfaced as an `Err(String)` that the frontend turns into
/// manual "open a terminal and run `claude /login`" instructions rather than a raw crash.
///
/// INTENTIONAL EXCEPTION to the "every spawned process is hidden" rule: every branch below opens
/// a visible terminal window on purpose -- that's the entire point of this command (the user
/// needs to see and interact with the interactive `claude /login` prompt). None of these go
/// through `CommandNoWindowExt::no_window()`; do not "fix" that.
#[tauri::command]
pub async fn open_login_terminal() -> Result<(), String> {
    if cfg!(target_os = "windows") {
        std::process::Command::new("cmd")
            .args(["/c", "start", "cmd", "/k", "claude /login"])
            .spawn()
            .map(|_| ())
            .map_err(|e| e.to_string())
    } else if cfg!(target_os = "macos") {
        let script = "tell application \"Terminal\" to do script \"claude /login\"";
        std::process::Command::new("osascript")
            .args(["-e", script])
            .spawn()
            .map(|_| ())
            .map_err(|e| e.to_string())
    } else {
        // Linux: try a handful of common terminal emulators in order, falling back to the next
        // candidate if the current one isn't installed. `x-terminal-emulator` is the Debian/Ubuntu
        // alternatives-system entry point and covers the widest range of desktops in one shot.
        let candidates: &[(&str, &[&str])] = &[
            ("x-terminal-emulator", &["-e", "bash", "-lc", "claude /login; exec bash"]),
            ("gnome-terminal", &["--", "bash", "-lc", "claude /login; exec bash"]),
            ("konsole", &["-e", "bash", "-lc", "claude /login; exec bash"]),
            ("xfce4-terminal", &["-e", "bash -lc 'claude /login; exec bash'"]),
            ("xterm", &["-e", "bash", "-lc", "claude /login; exec bash"]),
        ];
        for (bin, args) in candidates {
            if std::process::Command::new(bin).args(*args).spawn().is_ok() {
                return Ok(());
            }
        }
        Err("Could not find a terminal emulator to open automatically.".to_string())
    }
}

/// Advanced path: point the app at any existing folder (including a founder's own private
/// harness). No requirement that `.claude/commands` exists — an empty command rail is fine.
#[tauri::command]
pub async fn choose_workspace(
    app: tauri::AppHandle,
    path: String,
) -> Result<WorkspaceStatus, String> {
    let target = std::path::PathBuf::from(&path);
    if !target.is_dir() {
        return Err(format!("Not a directory: {path}"));
    }

    let app_data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let cfg = crate::workspace::WorkspaceConfig {
        version: 1,
        workspace_root: target.to_string_lossy().to_string(),
        created_from_template: false,
        template_version: None,
    };
    crate::workspace::save_config(&app_data_dir, &cfg)?;
    crate::workspace::set_root(target);

    Ok(workspace_status_for(&app_data_dir))
}
