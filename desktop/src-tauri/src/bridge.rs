//! CLI process bridge for AI Second Brain Desktop.
//!
//! Zero Tauri dependencies. This module spawns the already-logged-in `claude` CLI, feeds it
//! NDJSON on stdin, and parses its NDJSON stdout into typed [`BridgeEvent`]s over an mpsc
//! channel. Nothing in here knows about Tauri commands, windows, or app state — the `app`
//! module consumes this purely through the public API below.

use std::path::PathBuf;
use std::process::Stdio;
use std::sync::Arc;

use serde_json::Value;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::{mpsc, Mutex};
use uuid::Uuid;

/// Extension trait that suppresses the console window a spawned child would otherwise flash
/// open on Windows. Tauri desktop apps have no console of their own, so every child process
/// (the `claude` CLI, in every case this app spawns one) pops a brand-new one on `CreateProcess`
/// unless `CREATE_NO_WINDOW` is set -- this is what causes the visible flash/flicker on session
/// spawn, `detect_cli`, `check_auth`, and `test_provider`. No-op on Linux/macOS.
///
/// Every `tokio::process::Command` this app spawns MUST call `.no_window()` right after
/// `Command::new(..)`, so future call sites inherit the fix by construction rather than by
/// remembering to add the flag. The sole intentional exception is `app::open_login_terminal`'s
/// Windows branch, which opens a *visible* terminal window on purpose (that's the whole point of
/// the command) and is commented in place there instead of using this trait.
pub(crate) trait CommandNoWindowExt {
    fn no_window(&mut self) -> &mut Self;
}

impl CommandNoWindowExt for Command {
    #[cfg(windows)]
    fn no_window(&mut self) -> &mut Self {
        // 0x0800_0000 = CREATE_NO_WINDOW. Hardcoded rather than pulling in `windows-sys`/`winapi`
        // for a single flag; `tokio::process::Command::creation_flags` is an inherent method on
        // Windows (forwards to `std::os::windows::process::CommandExt`), so no extra import or
        // dependency is needed to call it here.
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        self.creation_flags(CREATE_NO_WINDOW);
        self
    }

    #[cfg(not(windows))]
    fn no_window(&mut self) -> &mut Self {
        self
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub enum PermissionMode {
    Manual,
    AcceptEdits,
    Plan,
    BypassPermissions,
}
impl PermissionMode {
    /// The exact string the CLI's `--permission-mode` flag expects (verified live).
    pub fn as_flag(self) -> &'static str {
        match self {
            PermissionMode::Manual => "manual",
            PermissionMode::AcceptEdits => "acceptEdits",
            PermissionMode::Plan => "plan",
            PermissionMode::BypassPermissions => "bypassPermissions",
        }
    }
}

/// One image attached to an outgoing user message. `data_base64` is the raw base64-encoded
/// image bytes (no `data:` URL prefix); `media_type` is a full MIME type (e.g. `image/png`).
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ImageAttachment {
    pub data_base64: String,
    pub media_type: String,
}

/// Builds the NDJSON `content` array for an outgoing user message: one Anthropic-style image
/// block per attachment, in order, followed by a single trailing text block. Image-before-text
/// matches the Messages API convention (and Claude Code's own CLI behavior) so an attached image
/// is understood as context for the text that follows it. Pure and side-effect free so it's
/// covered directly by unit tests below.
pub fn build_user_content(text: &str, attachments: &[ImageAttachment]) -> Value {
    let mut blocks: Vec<Value> = Vec::with_capacity(attachments.len() + 1);
    for a in attachments {
        blocks.push(serde_json::json!({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": a.media_type,
                "data": a.data_base64,
            }
        }));
    }
    blocks.push(serde_json::json!({ "type": "text", "text": text }));
    Value::Array(blocks)
}

#[derive(Debug)]
pub enum BridgeError {
    /// PATH scan found no executable `claude`.
    ClaudeNotFound,
    Spawn(std::io::Error),
    /// stdin writer gone: process dead or shut down.
    Closed,
    Json(serde_json::Error),
    /// No transcript JSONL file could be located for the given session id.
    TranscriptNotFound,
}

impl std::fmt::Display for BridgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            BridgeError::ClaudeNotFound => write!(f, "claude CLI not found on PATH"),
            BridgeError::Spawn(e) => write!(f, "failed to spawn claude CLI: {e}"),
            BridgeError::Closed => write!(f, "claude session stdin is closed"),
            BridgeError::Json(e) => write!(f, "failed to encode/decode JSON: {e}"),
            BridgeError::TranscriptNotFound => write!(f, "no transcript found for session"),
        }
    }
}

impl std::error::Error for BridgeError {}

impl From<std::io::Error> for BridgeError {
    fn from(e: std::io::Error) -> Self {
        BridgeError::Spawn(e)
    }
}

impl From<serde_json::Error> for BridgeError {
    fn from(e: serde_json::Error) -> Self {
        BridgeError::Json(e)
    }
}

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Usage {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_read_input_tokens: u64,
    pub cache_creation_input_tokens: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DeltaKind {
    Text,
    Thinking,
    ToolInput,
}

#[derive(Debug, Clone)]
pub enum BridgeEvent {
    Init {
        session_id: String,
        model: String,
        permission_mode: String,
        claude_code_version: String,
        cwd: String,
        slash_commands: Vec<String>,
        agents: Vec<String>,
    },
    Status {
        status: String,
        detail: Option<String>,
    },
    BlockStart {
        index: u32,
        block_type: String,
        tool_use_id: Option<String>,
        tool_name: Option<String>,
    },
    Delta {
        index: u32,
        kind: DeltaKind,
        text: String,
    },
    BlockStop {
        index: u32,
    },
    AssistantMessage {
        model: String,
        content: Vec<Value>,
    },
    ToolResult {
        tool_use_id: String,
        content: Value,
        is_error: bool,
    },
    PermissionRequest {
        request_id: String,
        tool_name: String,
        input: Value,
        description: Option<String>,
        suggestions: Vec<Value>,
        blocked_path: Option<String>,
    },
    /// A `control_request` whose `subtype` is anything other than `can_use_tool` AND whose
    /// payload carries a `question` field (see `parse_generic_control_request`). Not a
    /// documented part of the CLI's stream-json contract today — only `can_use_tool` is
    /// live-verified — but the wire format is forward-compatible-by-construction (a plain
    /// string field on a JSON object), so this is a defensive generalization: if a future/
    /// alternate CLI build ever surfaces an interactive question through `control_request`
    /// instead of (or in addition to) the model just asking in plain assistant text, the app
    /// renders a QuestionModal instead of silently dropping the request as `Other`.
    QuestionRequest {
        request_id: String,
        /// The original request's `subtype` (echoed back so a future `respond_question` caller
        /// could branch on it if different subtypes ever need different response shapes; the
        /// generic `control_response` envelope built by `respond_question` does not need it).
        subtype: String,
        /// The question payload's `question` field — rendered as the modal's title.
        title: String,
        /// Optional longer-form markdown detail (`body`/`description`/`detail` field, first
        /// match wins), rendered under the title.
        body: Option<String>,
        /// Selectable options, if the payload provided any (`options` or `choices` field).
        options: Vec<QuestionOption>,
        /// Whether a free-text answer is accepted in addition to (or instead of) the option
        /// buttons. Defaults to `true` when no options were provided at all — otherwise the
        /// human would have no way to answer.
        allow_free_text: bool,
    },
    TurnResult {
        subtype: String,
        is_error: bool,
        result: Option<String>,
        num_turns: u64,
        duration_ms: u64,
        total_cost_usd: f64,
        usage: Usage,
        model: Option<String>,
        permission_denials: Vec<Value>,
    },
    Stderr {
        line: String,
    },
    Other {
        raw: Value,
    },
    Exited {
        code: Option<i32>,
    },
}

#[derive(Debug, Clone)]
pub enum PermissionResponse {
    Allow { updated_input: Value },
    Deny { message: String },
}

/// One selectable answer to a `QuestionRequest`. `label` is what a QuestionModal option button
/// shows; `value` is what actually travels back in the `control_response`. Equal when the
/// payload gave a bare string instead of a `{label, value}` object (see `parse_question_option`).
#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct QuestionOption {
    pub label: String,
    pub value: String,
}

/// What the human answered a `QuestionRequest` with — mirrors `PermissionResponse`'s Allow/Deny
/// split so `respond_question`'s call site reads the same way `respond_permission`'s does.
#[derive(Debug, Clone)]
pub enum QuestionAnswer {
    Option { value: String },
    FreeText { text: String },
}

#[derive(Clone)]
pub struct SpawnOptions {
    pub repo_root: PathBuf,
    pub session_id: String,
    pub resume: bool,
    pub permission_mode: PermissionMode,
    /// "fable" | "opus" | "sonnet" | "haiku" or a full model name; `None` = CLI default.
    pub model: Option<String>,
    /// "low" | "medium" | "high" | "xhigh" | "max"; `None` = CLI default.
    pub effort: Option<String>,
    /// `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL` overlay for a
    /// non-default provider (empty for the built-in `claude` provider — subscription login gets
    /// no env overrides). Built by `crate::providers::provider_env_vars`.
    pub extra_env: crate::providers::EnvOverlay,
}

/// Manual impl (not `#[derive(Debug)]`): `extra_env` may carry a raw `ANTHROPIC_AUTH_TOKEN`
/// value, and `EnvOverlay`'s own `Debug` already redacts it, but a derived impl on the *outer*
/// struct would still be safe only because it delegates to that redacting impl — spelled out
/// explicitly here so nobody "fixes" this back to a derive without noticing why it isn't one.
impl std::fmt::Debug for SpawnOptions {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SpawnOptions")
            .field("repo_root", &self.repo_root)
            .field("session_id", &self.session_id)
            .field("resume", &self.resume)
            .field("permission_mode", &self.permission_mode)
            .field("model", &self.model)
            .field("effort", &self.effort)
            .field("extra_env", &self.extra_env)
            .finish()
    }
}

/// Manual scan of `PATH` for the first executable file named `claude`.
/// Uses `std::env::split_paths` (portable PATH parsing) rather than hand-splitting on `:`;
/// still a pure filesystem scan, never shells out to `which`, never hardcodes a path.
pub fn resolve_claude_bin() -> Result<PathBuf, BridgeError> {
    // Native Windows: the npm shim is claude.cmd (not directly spawnable with a UNC cwd), but it
    // wraps a real PE executable — prefer that. Try the conventional npm-global location first,
    // then any claude.exe/claude.cmd-derived exe on PATH.
    #[cfg(windows)]
    {
        if let Some(appdata) = std::env::var_os("APPDATA") {
            let exe = PathBuf::from(appdata)
                .join(r"npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe");
            if exe.is_file() {
                return Ok(exe);
            }
        }
        if let Some(path_var) = std::env::var_os("PATH") {
            for dir in std::env::split_paths(&path_var) {
                let exe = dir.join("claude.exe");
                if exe.is_file() {
                    return Ok(exe);
                }
                if dir.join("claude.cmd").is_file() {
                    let derived =
                        dir.join(r"node_modules\@anthropic-ai\claude-code\bin\claude.exe");
                    if derived.is_file() {
                        return Ok(derived);
                    }
                }
            }
        }
        return Err(BridgeError::ClaudeNotFound);
    }
    #[allow(unreachable_code)]
    {
        let is_executable_file = |candidate: &PathBuf| -> bool {
            let Ok(metadata) = std::fs::metadata(candidate) else {
                return false;
            };
            if !metadata.is_file() {
                return false;
            }
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                metadata.permissions().mode() & 0o111 != 0
            }
            #[cfg(not(unix))]
            {
                true
            }
        };

        if let Some(path_var) = std::env::var_os("PATH") {
            for dir in std::env::split_paths(&path_var) {
                let candidate = dir.join("claude");
                if is_executable_file(&candidate) {
                    return Ok(candidate);
                }
            }
        }

        // PATH scan failed: probe well-known install locations the official installers and npm
        // global installs commonly use but that a GUI-launched app's PATH may not include.
        if let Some(home) = std::env::var_os("HOME") {
            let home = PathBuf::from(home);
            let fallbacks = [
                home.join(".local/bin/claude"),
                home.join(".claude/local/claude"),
                home.join(".npm-global/bin/claude"),
            ];
            for candidate in fallbacks {
                if is_executable_file(&candidate) {
                    return Ok(candidate);
                }
            }
        }
        for candidate in ["/usr/local/bin/claude", "/opt/homebrew/bin/claude"] {
            let candidate = PathBuf::from(candidate);
            if is_executable_file(&candidate) {
                return Ok(candidate);
            }
        }

        Err(BridgeError::ClaudeNotFound)
    }
}

/// Cheap-clone handle to a running `claude` process. Dropping all clones does NOT kill the
/// process (shutdown is explicit); the app keeps one clone in its active session map.
///
/// Deviation from a plain `{ session_id, stdin_tx, child }` shape: an extra `shutdown_tx`
/// channel is carried alongside `stdin_tx`. A bare `mpsc::Sender<String>` can't force the
/// writer task to close stdin on demand while sibling clones of this handle are still alive
/// (the channel only closes once EVERY sender clone is dropped), so a dedicated shutdown
/// signal is needed for `shutdown()` to be reliable.
#[derive(Clone)]
pub struct ClaudeSession {
    session_id: String,
    stdin_tx: mpsc::Sender<String>,
    shutdown_tx: mpsc::Sender<()>,
    child: Arc<Mutex<Child>>,
}

impl ClaudeSession {
    pub fn session_id(&self) -> &str {
        &self.session_id
    }

    /// Writes one NDJSON user-turn line to stdin. Kept for backward compatibility / call sites
    /// that never carry attachments; delegates to `send_user_message` with an empty list.
    #[allow(dead_code)]
    pub async fn send_user_text(&self, text: &str) -> Result<(), BridgeError> {
        self.send_user_message(text, &[]).await
    }

    /// Writes one NDJSON user-turn line to stdin, with zero or more image attachments placed
    /// before the text block (image-then-text is the Anthropic Messages API convention).
    pub async fn send_user_message(
        &self,
        text: &str,
        attachments: &[ImageAttachment],
    ) -> Result<(), BridgeError> {
        let payload = serde_json::json!({
            "type": "user",
            "message": { "role": "user", "content": build_user_content(text, attachments) }
        });
        self.write_line(&payload).await
    }

    /// Writes one NDJSON control_response line answering a `can_use_tool` permission request.
    pub async fn respond_permission(
        &self,
        request_id: &str,
        response: PermissionResponse,
    ) -> Result<(), BridgeError> {
        let response_body = match response {
            PermissionResponse::Allow { updated_input } => serde_json::json!({
                "behavior": "allow",
                "updatedInput": updated_input,
            }),
            PermissionResponse::Deny { message } => serde_json::json!({
                "behavior": "deny",
                "message": message,
            }),
        };
        let payload = serde_json::json!({
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": request_id,
                "response": response_body,
            }
        });
        self.write_line(&payload).await
    }

    /// Writes one NDJSON control_response line answering a `QuestionRequest` (any `control_request`
    /// subtype other than `can_use_tool` that carried a question payload — see
    /// `parse_generic_control_request`). Uses the same `control_response` envelope as
    /// `respond_permission` (only `can_use_tool` needs the `behavior`/`updatedInput` shape); here
    /// the `response` body is just whatever the human picked or typed.
    pub async fn respond_question(
        &self,
        request_id: &str,
        answer: QuestionAnswer,
    ) -> Result<(), BridgeError> {
        let response_body = match answer {
            QuestionAnswer::Option { value } => serde_json::json!({ "value": value }),
            QuestionAnswer::FreeText { text } => serde_json::json!({ "text": text }),
        };
        let payload = serde_json::json!({
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": request_id,
                "response": response_body,
            }
        });
        self.write_line(&payload).await
    }

    /// Writes an interrupt control_request (Agent SDK convention — NOT live-verified).
    /// Caller (app::interrupt_session) enforces the 3s kill fallback.
    pub async fn interrupt(&self) -> Result<(), BridgeError> {
        let payload = serde_json::json!({
            "type": "control_request",
            "request_id": Uuid::new_v4().to_string(),
            "request": { "subtype": "interrupt" }
        });
        self.write_line(&payload).await
    }

    /// Graceful stop: signal the writer task to drop stdin (EOF ends the `-p` loop, verified),
    /// wait up to 5s for the child to exit, then hard-kill if it hasn't. Idempotent: if the
    /// child already exited, `Child::wait()` returns the cached exit status immediately rather
    /// than re-invoking `waitpid`, so a repeat call is cheap and returns `Ok(())`.
    pub async fn shutdown(&self) -> Result<(), BridgeError> {
        // Best-effort: the writer task may already be gone (process died on its own).
        let _ = self.shutdown_tx.send(()).await;

        // Poll with `try_wait` instead of holding the mutex across a long `wait().await`.
        // The waiter task also locks this child to reap it; if BOTH sides parked inside an
        // awaited `wait()` while holding the lock, this function could block on lock acquisition
        // forever and the 5s kill fallback would never run. Polling keeps every critical section
        // non-blocking, so the kill path is always reachable.
        let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(5);
        loop {
            {
                let mut child = self.child.lock().await;
                match child.try_wait() {
                    Ok(Some(_status)) => return Ok(()),
                    Ok(None) => {}
                    Err(e) => return Err(BridgeError::Spawn(e)),
                }
                if tokio::time::Instant::now() >= deadline {
                    // Hard stop. The waiter task reaps the corpse and emits Exited.
                    let _ = child.start_kill();
                    return Ok(());
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        }
    }

    async fn write_line(&self, payload: &Value) -> Result<(), BridgeError> {
        let line = serde_json::to_string(payload)?;
        self.stdin_tx
            .send(line)
            .await
            .map_err(|_| BridgeError::Closed)
    }
}

/// Builds the exact CLI arg vector (everything after the `claude` binary path) for the given
/// spawn options. Pure — no process, no filesystem, no Tauri — so it is unit-testable in isolation.
/// The order is load-bearing and verified live: base flags, then `--permission-mode <flag>`, then
/// the optional `--model`/`--effort` pair, then the `--resume`/`--session-id` terminator.
pub fn build_args(opts: &SpawnOptions) -> Vec<String> {
    let mut args: Vec<String> = vec![
        "-p".into(),
        "--input-format".into(),
        "stream-json".into(),
        "--output-format".into(),
        "stream-json".into(),
        "--verbose".into(),
        "--include-partial-messages".into(),
        "--permission-prompt-tool".into(),
        "stdio".into(),
        "--permission-mode".into(),
        opts.permission_mode.as_flag().into(),
    ];
    if let Some(m) = &opts.model {
        args.push("--model".into());
        args.push(m.clone());
    }
    if let Some(e) = &opts.effort {
        args.push("--effort".into());
        args.push(e.clone());
    }
    if opts.resume {
        args.push("--resume".into());
        args.push(opts.session_id.clone());
    } else {
        args.push("--session-id".into());
        args.push(opts.session_id.clone());
    }
    args
}

/// Substring `claude` prints (on stdout-as-diagnostic or stderr) when a `--resume <id>` target
/// does not exist on the CLI side anymore — e.g. a session recorded locally whose id was never
/// actually accepted by a real conversation (empty API key on a non-claude provider, deleted
/// transcript, etc). Matched case-insensitively.
const GHOST_RESUME_MARKER: &str = "no conversation found";

/// Decides whether a just-exited `--resume` attempt was against a "ghost" session id and should
/// be retried once as a fresh conversation (same `--session-id`, no `--resume`) instead of being
/// left dead. Pure so it's unit-testable without spawning a process: true only when the process
/// exited before ever producing an `Init` event (proof the resumed conversation never actually
/// started) AND at least one collected line names the "no conversation found" condition.
/// `saw_init` alone is not a safe trigger — a session can legitimately exit early for other
/// reasons (auth failure, crash) that a resume-less respawn would not fix and would instead loop.
pub fn should_clear_ghost_resume(saw_init: bool, output_lines: &[String]) -> bool {
    if saw_init {
        return false;
    }
    output_lines
        .iter()
        .any(|line| line.to_lowercase().contains(GHOST_RESUME_MARKER))
}

/// Spawns the CLI with the exact verified arg vector and wires up stdin/stdout/stderr plumbing.
/// Returns immediately after a successful spawn; it is safe to call `send_user_text` right away,
/// before `Init` arrives, because the CLI queues stdin (verified).
pub async fn spawn_session(
    opts: SpawnOptions,
) -> Result<(ClaudeSession, mpsc::Receiver<BridgeEvent>), BridgeError> {
    let bin = resolve_claude_bin()?;

    let mut cmd = Command::new(bin);
    cmd.no_window()
        .current_dir(&opts.repo_root)
        .args(build_args(&opts));
    if !opts.extra_env.is_empty() {
        for (key, value) in opts.extra_env.iter() {
            cmd.env(key, value);
        }
    }
    cmd.stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);

    let mut child = cmd.spawn()?;
    let stdin = child.stdin.take().expect("stdin was piped");
    let stdout = child.stdout.take().expect("stdout was piped");
    let stderr = child.stderr.take().expect("stderr was piped");

    let (event_tx, event_rx) = mpsc::channel::<BridgeEvent>(1024);
    let (stdin_tx, mut stdin_rx) = mpsc::channel::<String>(256);
    let (shutdown_tx, mut shutdown_rx) = mpsc::channel::<()>(1);

    // Stdin writer task: owns the ChildStdin exclusively. Ends on channel close, write
    // failure, or an explicit shutdown signal; in every case `stdin` is dropped at task exit,
    // which sends EOF to the child and ends its `-p` read loop cleanly.
    tokio::spawn(async move {
        let mut stdin = stdin;
        loop {
            tokio::select! {
                biased;
                _ = shutdown_rx.recv() => break,
                maybe_line = stdin_rx.recv() => {
                    match maybe_line {
                        Some(line) => {
                            if stdin.write_all(line.as_bytes()).await.is_err() { break; }
                            if stdin.write_all(b"\n").await.is_err() { break; }
                            if stdin.flush().await.is_err() { break; }
                        }
                        None => break,
                    }
                }
            }
        }
    });

    // Stdout reader task. `BufReader::lines()` / `next_line()` buffers internally across
    // however many chunks the OS delivers, so a JSON object split across two reads still
    // parses correctly once the trailing '\n' arrives — this is the load-bearing correctness
    // property for this whole module.
    let stdout_tx = event_tx.clone();
    let stdout_handle = tokio::spawn(async move {
        let mut reader = BufReader::new(stdout).lines();
        loop {
            match reader.next_line().await {
                Ok(Some(line)) => {
                    if line.trim().is_empty() {
                        continue;
                    }
                    match serde_json::from_str::<Value>(&line) {
                        Ok(value) => {
                            for ev in parse_stdout_events(value) {
                                if stdout_tx.send(ev).await.is_err() {
                                    return;
                                }
                            }
                        }
                        Err(_) => {
                            // Unparseable stdout line -> surfaced as a diagnostic, not a panic.
                            let _ = stdout_tx.send(BridgeEvent::Stderr { line }).await;
                        }
                    }
                }
                Ok(None) => break,
                Err(e) => {
                    let _ = stdout_tx
                        .send(BridgeEvent::Stderr {
                            line: format!("stdout read error: {e}"),
                        })
                        .await;
                    break;
                }
            }
        }
    });

    let stderr_tx = event_tx.clone();
    let stderr_handle = tokio::spawn(async move {
        let mut reader = BufReader::new(stderr).lines();
        loop {
            match reader.next_line().await {
                Ok(Some(line)) => {
                    if stderr_tx.send(BridgeEvent::Stderr { line }).await.is_err() {
                        break;
                    }
                }
                Ok(None) => break,
                Err(_) => break,
            }
        }
    });

    let child_arc = Arc::new(Mutex::new(child));

    // Waiter task: the sole source of the final `Exited` event. Runs after both readers hit
    // EOF, reaps the child, then sends Exited and drops its own event_tx clone. Combined with
    // the stdout/stderr tasks' clones dropping when they end, this guarantees Exited is the
    // last event the receiver ever sees before the channel closes.
    let waiter_child = child_arc.clone();
    tokio::spawn(async move {
        let _ = tokio::join!(stdout_handle, stderr_handle);
        let code = {
            let mut guard = waiter_child.lock().await;
            match guard.wait().await {
                Ok(status) => status.code(),
                Err(_) => None,
            }
        };
        let _ = event_tx.send(BridgeEvent::Exited { code }).await;
    });

    let session = ClaudeSession {
        session_id: opts.session_id,
        stdin_tx,
        shutdown_tx,
        child: child_arc,
    };
    Ok((session, event_rx))
}

// ---- stdout line -> BridgeEvent normalization ---------------------------------------------

fn parse_stdout_events(value: Value) -> Vec<BridgeEvent> {
    let type_field = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
    match type_field {
        "system" => parse_system_event(value),
        "stream_event" => parse_stream_event(value),
        "assistant" => parse_assistant_event(value),
        "user" => parse_user_event(value),
        "control_request" => parse_control_request(value),
        "result" => vec![parse_result_event(value)],
        // control_response acks, rate_limit_event, and any unknown type are forwarded verbatim;
        // it is the app module's job (not this one) to decide what to drop.
        _ => vec![BridgeEvent::Other { raw: value }],
    }
}

// NOTE on Init field names: the exact wire schema of the `system/init` event is not in
// `claude --help`, so the keys below are read literally as the contracted BridgeEvent field
// names (session_id, model, permission_mode, claude_code_version, cwd, slash_commands, agents).
// Any field absent on the wire simply defaults to empty rather than failing the parse.
fn parse_system_event(value: Value) -> Vec<BridgeEvent> {
    let subtype = value.get("subtype").and_then(|v| v.as_str()).unwrap_or("");
    match subtype {
        "init" => vec![BridgeEvent::Init {
            session_id: str_field(&value, "session_id"),
            model: str_field(&value, "model"),
            // Wire key is camelCase `permissionMode` (verified live on 2.1.209: the init event's
            // keys are mostly snake_case but this one is not). The snake_case fallback is kept in
            // case a future CLI normalizes it.
            permission_mode: opt_str_field(&value, "permissionMode")
                .or_else(|| opt_str_field(&value, "permission_mode"))
                .unwrap_or_default(),
            claude_code_version: str_field(&value, "claude_code_version"),
            cwd: str_field(&value, "cwd"),
            slash_commands: str_vec_field(&value, "slash_commands"),
            agents: str_vec_field(&value, "agents"),
        }],
        "status" => vec![BridgeEvent::Status {
            status: str_field(&value, "status"),
            detail: None,
        }],
        "hook_started" => vec![BridgeEvent::Status {
            status: "hook_started".to_string(),
            detail: opt_str_field(&value, "hook_name"),
        }],
        "hook_response" => vec![BridgeEvent::Status {
            status: "hook_response".to_string(),
            detail: opt_str_field(&value, "hook_name"),
        }],
        _ => vec![BridgeEvent::Other { raw: value }],
    }
}

fn parse_stream_event(value: Value) -> Vec<BridgeEvent> {
    let Some(event) = value.get("event") else {
        return vec![BridgeEvent::Other { raw: value }];
    };
    let ev_type = event.get("type").and_then(|v| v.as_str()).unwrap_or("");
    match ev_type {
        "content_block_start" => {
            let index = u32_field(event, "index");
            let block = event.get("content_block");
            let block_type = block
                .and_then(|b| b.get("type"))
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let tool_use_id = block
                .and_then(|b| b.get("id"))
                .and_then(|v| v.as_str())
                .map(String::from);
            let tool_name = block
                .and_then(|b| b.get("name"))
                .and_then(|v| v.as_str())
                .map(String::from);
            vec![BridgeEvent::BlockStart {
                index,
                block_type,
                tool_use_id,
                tool_name,
            }]
        }
        "content_block_delta" => {
            let index = u32_field(event, "index");
            let delta = event.get("delta");
            let delta_type = delta
                .and_then(|d| d.get("type"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            match delta_type {
                "text_delta" => vec![BridgeEvent::Delta {
                    index,
                    kind: DeltaKind::Text,
                    text: delta
                        .and_then(|d| d.get("text"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string(),
                }],
                "thinking_delta" => vec![BridgeEvent::Delta {
                    index,
                    kind: DeltaKind::Thinking,
                    text: delta
                        .and_then(|d| d.get("thinking"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string(),
                }],
                "input_json_delta" => vec![BridgeEvent::Delta {
                    index,
                    kind: DeltaKind::ToolInput,
                    text: delta
                        .and_then(|d| d.get("partial_json"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string(),
                }],
                // Contract: signature_delta lines are dropped, not emitted as anything.
                "signature_delta" => vec![],
                _ => vec![BridgeEvent::Other { raw: value.clone() }],
            }
        }
        "content_block_stop" => vec![BridgeEvent::BlockStop {
            index: u32_field(event, "index"),
        }],
        // message_start / message_delta / message_stop and anything else: forwarded verbatim.
        _ => vec![BridgeEvent::Other { raw: value.clone() }],
    }
}

fn parse_assistant_event(value: Value) -> Vec<BridgeEvent> {
    let message = value.get("message");
    let model = message
        .and_then(|m| m.get("model"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let content = message
        .and_then(|m| m.get("content"))
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    vec![BridgeEvent::AssistantMessage { model, content }]
}

fn parse_user_event(value: Value) -> Vec<BridgeEvent> {
    let mut events = Vec::new();
    if let Some(content) = value
        .get("message")
        .and_then(|m| m.get("content"))
        .and_then(|v| v.as_array())
    {
        for block in content {
            if block.get("type").and_then(|v| v.as_str()) == Some("tool_result") {
                events.push(BridgeEvent::ToolResult {
                    tool_use_id: str_field(block, "tool_use_id"),
                    content: block.get("content").cloned().unwrap_or(Value::Null),
                    is_error: block
                        .get("is_error")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false),
                });
            }
        }
    }
    if events.is_empty() {
        // A "user" message with no tool_result blocks (e.g. an echoed user turn) has no
        // dedicated event in the contract; forward it verbatim rather than dropping it.
        events.push(BridgeEvent::Other { raw: value });
    }
    events
}

/// Every `control_request` this app receives from the CLI's stdout is normalized here. Only
/// `subtype: "can_use_tool"` is live-verified against the real CLI; everything else falls through
/// to `parse_generic_control_request`, which is a best-effort, forward-compatible detector for a
/// question-shaped payload (see that function's doc comment) rather than a documented protocol
/// branch — anything that doesn't match a question shape is forwarded verbatim as `Other` so
/// nothing this app doesn't understand is ever silently swallowed.
fn parse_control_request(value: Value) -> Vec<BridgeEvent> {
    let request_id = str_field(&value, "request_id");
    // Both derived up front as owned values (not borrows of `value`) so `value` itself is free to
    // move into the `Other` fallback path below without fighting the borrow checker.
    let subtype = value
        .get("request")
        .and_then(|r| r.get("subtype"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let request = value.get("request").cloned();
    match subtype.as_str() {
        "can_use_tool" => parse_can_use_tool_request(request_id, request.as_ref()),
        other => parse_generic_control_request(request_id, other, request.as_ref(), value),
    }
}

fn parse_can_use_tool_request(request_id: String, request: Option<&Value>) -> Vec<BridgeEvent> {
    let tool_name = request.map(|r| str_field(r, "tool_name")).unwrap_or_default();
    let input = request
        .and_then(|r| r.get("input"))
        .cloned()
        .unwrap_or(Value::Null);
    let description = request.and_then(|r| opt_str_field(r, "description"));
    let suggestions = request
        .and_then(|r| r.get("permission_suggestions"))
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let blocked_path = request.and_then(|r| opt_str_field(r, "blocked_path"));
    vec![BridgeEvent::PermissionRequest {
        request_id,
        tool_name,
        input,
        description,
        suggestions,
        blocked_path,
    }]
}

/// Field name candidates checked (in priority order) for a non-`can_use_tool` `control_request`'s
/// question text and its optional longer-form detail/options. Kept deliberately narrow — matching
/// only on a field literally named `question` is what keeps this generalization from misfiring on
/// some future, entirely unrelated `control_request` subtype (e.g. `hook_callback`/`mcp_message`)
/// that happens to carry an unrelated `title`-like field.
const QUESTION_BODY_FIELD_CANDIDATES: [&str; 3] = ["body", "description", "detail"];
const QUESTION_OPTIONS_FIELD_CANDIDATES: [&str; 2] = ["options", "choices"];

/// Detects whether a non-`can_use_tool` `control_request` is carrying a question the human
/// should answer (title via a `question` field, optional markdown `body`, optional `options`/
/// `choices` list, optional explicit `allow_free_text`/`allowFreeText` bool) and, if so, emits a
/// `QuestionRequest`. Anything lacking a `question` field is forwarded verbatim as `Other` —
/// unmapped, but never lost (see `app::forward_events`'s `Other` arm, which logs it).
fn parse_generic_control_request(
    request_id: String,
    subtype: &str,
    request: Option<&Value>,
    raw: Value,
) -> Vec<BridgeEvent> {
    let Some(request) = request else {
        return vec![BridgeEvent::Other { raw }];
    };
    let Some(title) = opt_str_field(request, "question") else {
        return vec![BridgeEvent::Other { raw }];
    };
    let body = QUESTION_BODY_FIELD_CANDIDATES
        .iter()
        .find_map(|k| opt_str_field(request, k));
    let options: Vec<QuestionOption> = QUESTION_OPTIONS_FIELD_CANDIDATES
        .iter()
        .find_map(|k| request.get(*k))
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().map(parse_question_option).collect())
        .unwrap_or_default();
    let allow_free_text = request
        .get("allow_free_text")
        .or_else(|| request.get("allowFreeText"))
        .and_then(|v| v.as_bool())
        // No options at all -> free text MUST be allowed, or the human has no way to answer.
        .unwrap_or(options.is_empty());
    vec![BridgeEvent::QuestionRequest {
        request_id,
        subtype: subtype.to_string(),
        title,
        body,
        options,
        allow_free_text,
    }]
}

/// One entry of an `options`/`choices` array: either a bare string (label == value) or a
/// `{label, value}` (or `{text, value}`) object. Anything else degrades to empty strings rather
/// than panicking on a malformed entry.
fn parse_question_option(v: &Value) -> QuestionOption {
    if let Some(s) = v.as_str() {
        return QuestionOption {
            label: s.to_string(),
            value: s.to_string(),
        };
    }
    let label = v
        .get("label")
        .and_then(|x| x.as_str())
        .or_else(|| v.get("text").and_then(|x| x.as_str()))
        .unwrap_or("")
        .to_string();
    let value = v
        .get("value")
        .and_then(|x| x.as_str())
        .map(String::from)
        .unwrap_or_else(|| label.clone());
    QuestionOption { label, value }
}

fn parse_result_event(value: Value) -> BridgeEvent {
    let usage = value
        .get("usage")
        .map(|u| Usage {
            input_tokens: u64_field(u, "input_tokens"),
            output_tokens: u64_field(u, "output_tokens"),
            cache_read_input_tokens: u64_field(u, "cache_read_input_tokens"),
            cache_creation_input_tokens: u64_field(u, "cache_creation_input_tokens"),
        })
        .unwrap_or_default();
    // model = first key of the `modelUsage` map (contract's literal wording; camelCase wire
    // key even though sibling result fields are snake_case).
    let model = value
        .get("modelUsage")
        .and_then(|mu| mu.as_object())
        .and_then(|obj| obj.keys().next())
        .cloned();
    BridgeEvent::TurnResult {
        subtype: str_field(&value, "subtype"),
        is_error: value.get("is_error").and_then(|v| v.as_bool()).unwrap_or(false),
        result: opt_str_field(&value, "result"),
        num_turns: u64_field(&value, "num_turns"),
        duration_ms: u64_field(&value, "duration_ms"),
        total_cost_usd: value
            .get("total_cost_usd")
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0),
        usage,
        model,
        permission_denials: value
            .get("permission_denials")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default(),
    }
}

// ---- small Value extraction helpers --------------------------------------------------------

fn str_field(value: &Value, key: &str) -> String {
    value.get(key).and_then(|v| v.as_str()).unwrap_or("").to_string()
}

fn opt_str_field(value: &Value, key: &str) -> Option<String> {
    value.get(key).and_then(|v| v.as_str()).map(String::from)
}

fn u64_field(value: &Value, key: &str) -> u64 {
    value.get(key).and_then(|v| v.as_u64()).unwrap_or(0)
}

fn u32_field(value: &Value, key: &str) -> u32 {
    value.get(key).and_then(|v| v.as_u64()).unwrap_or(0) as u32
}

fn str_vec_field(value: &Value, key: &str) -> Vec<String> {
    value
        .get(key)
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().filter_map(|v| v.as_str().map(String::from)).collect())
        .unwrap_or_default()
}

// ---- transcript replay ----------------------------------------------------------------------
//
// Pure functions, zero Tauri deps: read a session's on-disk JSONL transcript (the same file the
// `claude` CLI itself writes to `~/.claude/projects/<sanitized-cwd>/<session-id>.jsonl`) and
// reduce it to a small, frontend-friendly entry list. Never fails hard on a single bad line —
// per-line parsing is best-effort, since a transcript should always render *something* even if
// one line is malformed or from a CLI version whose shape drifted.

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TranscriptEntry {
    pub role: String, // "user" | "assistant" | "tool"
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_input: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_result: Option<String>,
    pub is_error: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ts: Option<String>, // ISO-8601, copied verbatim from the line's `timestamp`
    /// Image blocks that accompanied this (user) message, in original order. `None` when the
    /// message had no images.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub images: Option<Vec<TranscriptImage>>,
}

/// One replayed image from a transcript line. `base64` is only populated when the encoded image
/// is small enough to inline cheaply into the frontend payload; otherwise it's `None` and the
/// frontend renders a `[image]` placeholder instead of a thumbnail.
#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TranscriptImage {
    pub media_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub base64: Option<String>,
}

/// Base64 length above which a replayed image is dropped in favor of a `[image]` placeholder
/// (roughly 150KB of decoded bytes at base64's ~4/3 expansion).
const MAX_INLINE_IMAGE_BASE64_LEN: usize = 200_000;

/// Maps every character that is not ASCII alphanumeric to `-`. This is the exact rule the CLI
/// itself uses to turn a cwd string into its `~/.claude/projects/<dir>` directory name (verified
/// against live JSONL: leading `\\` -> `--`, `.` -> `-`; case is preserved, never normalized).
fn sanitize(s: &str) -> String {
    s.chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
        .collect()
}

/// Every `~/.claude/projects`-equivalent root worth searching. Always includes `$HOME`'s; also
/// includes the Windows-side `.claude/projects` when `resolve_claude_bin()` resolves to a path
/// under `/mnt/<drive>/Users/<user>` (i.e. the `claude` binary itself lives on the Windows side
/// of a WSL mount), since that CLI process writes transcripts under its own Windows HOME.
fn candidate_roots() -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Ok(bin) = resolve_claude_bin() {
        let comps: Vec<String> = bin
            .components()
            .map(|c| c.as_os_str().to_string_lossy().to_string())
            .collect();
        if let Some(pos) = comps.iter().position(|c| c == "mnt") {
            if comps.len() > pos + 3 && comps[pos + 2] == "Users" {
                let drive = &comps[pos + 1];
                let user = &comps[pos + 3];
                roots.push(PathBuf::from(format!(
                    "/mnt/{drive}/Users/{user}/.claude/projects"
                )));
            }
        }
    }
    if let Some(home) = std::env::var_os("HOME") {
        roots.push(PathBuf::from(home).join(".claude/projects"));
    }
    // Native Windows: the CLI writes transcripts under %USERPROFILE%\.claude\projects.
    #[cfg(windows)]
    if let Some(profile) = std::env::var_os("USERPROFILE") {
        roots.push(PathBuf::from(profile).join(r".claude\projects"));
    }
    roots
}

/// Every project-dir name a `claude` process could have recorded for `repo_root`, in priority
/// order: the plain posix path, then (when running under WSL, i.e. `WSL_DISTRO_NAME` is set) the
/// UNC form the Windows-side binary sees when it treats the WSL filesystem as a network share.
fn candidate_dir_names(repo_root: &str) -> Vec<String> {
    let mut names = vec![sanitize(repo_root)];
    if let Ok(distro) = std::env::var("WSL_DISTRO_NAME") {
        let unc = format!("\\\\wsl.localhost\\{distro}{}", repo_root.replace('/', "\\"));
        names.push(sanitize(&unc));
    }
    names
}

/// Locates the on-disk JSONL transcript for `session_id` under `workspace_root`, or `None` if it
/// can't be found under any known root. Tries the exact expected
/// `<root>/<dir-name>/<session_id>.jsonl` paths first; falls back to a one-level-deep scan of
/// every root (session ids are UUIDs, effectively unique) in case the cwd-sanitization rule ever
/// drifts from what's implemented here.
pub fn find_transcript_file(workspace_root: &str, session_id: &str) -> Option<PathBuf> {
    let roots = candidate_roots();
    let names = candidate_dir_names(workspace_root);

    for root in &roots {
        for name in &names {
            let candidate = root.join(name).join(format!("{session_id}.jsonl"));
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }

    for root in &roots {
        let Ok(entries) = std::fs::read_dir(root) else {
            continue;
        };
        for entry in entries.flatten() {
            let candidate = entry.path().join(format!("{session_id}.jsonl"));
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }

    None
}

/// Flattens a `tool_result` block's `content` field to a single string: a plain string is used
/// as-is; an array of blocks is joined (each block contributing its `.text` field if present,
/// else a pretty-printed dump of the whole block), separated by blank lines.
fn flatten_tool_result_content(content: Option<&Value>) -> String {
    match content {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Array(blocks)) => blocks
            .iter()
            .map(|block| match block.get("text").and_then(|v| v.as_str()) {
                Some(text) => text.to_string(),
                None => serde_json::to_string_pretty(block).unwrap_or_default(),
            })
            .collect::<Vec<_>>()
            .join("\n\n"),
        Some(other) => other.to_string(),
        None => String::new(),
    }
}

/// Reads and reduces the JSONL transcript for `session_id` under `workspace_root` into a bounded
/// list of entries: the last 500 entries survive, each `tool_result` string truncated to 10,000
/// chars. Every line is parsed best-effort — an unparseable line, an unrecognized `type`, or a
/// sidechain/meta-flagged line is silently skipped rather than failing the whole read.
pub fn read_transcript(
    workspace_root: &str,
    session_id: &str,
) -> Result<Vec<TranscriptEntry>, BridgeError> {
    let path =
        find_transcript_file(workspace_root, session_id).ok_or(BridgeError::TranscriptNotFound)?;
    let raw = std::fs::read_to_string(&path)?;

    let mut out: Vec<TranscriptEntry> = Vec::new();
    let mut pending_tools: std::collections::HashMap<String, usize> =
        std::collections::HashMap::new();

    for line in raw.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Ok(value) = serde_json::from_str::<Value>(line) else {
            continue;
        };
        let type_field = value.get("type").and_then(|v| v.as_str()).unwrap_or("");
        if type_field != "user" && type_field != "assistant" {
            continue;
        }
        if value.get("isSidechain").and_then(|v| v.as_bool()).unwrap_or(false) {
            continue;
        }
        if value.get("isMeta").and_then(|v| v.as_bool()).unwrap_or(false) {
            continue;
        }
        let ts = opt_str_field(&value, "timestamp");
        let message_content = value.get("message").and_then(|m| m.get("content"));

        if type_field == "user" {
            match message_content {
                Some(Value::String(text)) => {
                    if !text.trim().is_empty() {
                        out.push(TranscriptEntry {
                            role: "user".to_string(),
                            text: Some(text.clone()),
                            tool_name: None,
                            tool_input: None,
                            tool_result: None,
                            is_error: false,
                            ts: ts.clone(),
                            images: None,
                        });
                    }
                }
                Some(Value::Array(blocks)) => {
                    // Images (built by build_user_content as one block per attachment,
                    // ahead of the text block) are buffered here and attached to the next
                    // text entry so the frontend renders them together as one message.
                    let mut pending_images: Vec<TranscriptImage> = Vec::new();
                    for block in blocks {
                        match block.get("type").and_then(|v| v.as_str()).unwrap_or("") {
                            "text" => {
                                let text = block.get("text").and_then(|v| v.as_str()).unwrap_or("");
                                let images = if pending_images.is_empty() {
                                    None
                                } else {
                                    Some(std::mem::take(&mut pending_images))
                                };
                                if !text.trim().is_empty() || images.is_some() {
                                    out.push(TranscriptEntry {
                                        role: "user".to_string(),
                                        text: Some(text.to_string()),
                                        tool_name: None,
                                        tool_input: None,
                                        tool_result: None,
                                        is_error: false,
                                        ts: ts.clone(),
                                        images,
                                    });
                                }
                            }
                            "image" => {
                                let media_type = block
                                    .get("source")
                                    .and_then(|s| s.get("media_type"))
                                    .and_then(|v| v.as_str())
                                    .unwrap_or("image/png")
                                    .to_string();
                                let base64 = block
                                    .get("source")
                                    .and_then(|s| s.get("data"))
                                    .and_then(|v| v.as_str())
                                    .filter(|d| d.len() <= MAX_INLINE_IMAGE_BASE64_LEN)
                                    .map(|d| d.to_string());
                                pending_images.push(TranscriptImage { media_type, base64 });
                            }
                            "tool_result" => {
                                let tool_use_id = str_field(block, "tool_use_id");
                                let is_error = block
                                    .get("is_error")
                                    .and_then(|v| v.as_bool())
                                    .unwrap_or(false);
                                let flattened = flatten_tool_result_content(block.get("content"));
                                let matched = if tool_use_id.is_empty() {
                                    None
                                } else {
                                    pending_tools.get(&tool_use_id).copied()
                                };
                                match matched.and_then(|idx| out.get_mut(idx)) {
                                    Some(entry) => {
                                        entry.tool_result = Some(flattened);
                                        entry.is_error = is_error;
                                    }
                                    None => {
                                        out.push(TranscriptEntry {
                                            role: "tool".to_string(),
                                            text: None,
                                            tool_name: None,
                                            tool_input: None,
                                            tool_result: Some(flattened),
                                            is_error,
                                            ts: ts.clone(),
                                            images: None,
                                        });
                                    }
                                }
                            }
                            _ => {}
                        }
                    }
                    // Malformed/unexpected shape: images with no trailing text block. Still
                    // surface them as their own entry rather than silently dropping them.
                    if !pending_images.is_empty() {
                        out.push(TranscriptEntry {
                            role: "user".to_string(),
                            text: None,
                            tool_name: None,
                            tool_input: None,
                            tool_result: None,
                            is_error: false,
                            ts: ts.clone(),
                            images: Some(pending_images),
                        });
                    }
                }
                _ => {}
            }
        } else {
            // "assistant"
            if let Some(blocks) = message_content.and_then(|v| v.as_array()) {
                for block in blocks {
                    match block.get("type").and_then(|v| v.as_str()).unwrap_or("") {
                        "text" => {
                            let text = block.get("text").and_then(|v| v.as_str()).unwrap_or("");
                            if !text.trim().is_empty() {
                                out.push(TranscriptEntry {
                                    role: "assistant".to_string(),
                                    text: Some(text.to_string()),
                                    tool_name: None,
                                    tool_input: None,
                                    tool_result: None,
                                    is_error: false,
                                    ts: ts.clone(),
                                    images: None,
                                });
                            }
                        }
                        "thinking" => {}
                        "tool_use" => {
                            let tool_name = opt_str_field(block, "name");
                            let tool_input = block.get("input").cloned();
                            out.push(TranscriptEntry {
                                role: "tool".to_string(),
                                text: None,
                                tool_name,
                                tool_input,
                                tool_result: None,
                                is_error: false,
                                ts: ts.clone(),
                                images: None,
                            });
                            if let Some(id) = block.get("id").and_then(|v| v.as_str()) {
                                pending_tools.insert(id.to_string(), out.len() - 1);
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
    }

    // Cap at the last 500 entries, then truncate each tool_result to 10,000 chars.
    let start = out.len().saturating_sub(500);
    let mut capped = out.split_off(start);
    for entry in capped.iter_mut() {
        if let Some(tr) = &entry.tool_result {
            if tr.chars().count() > 10_000 {
                entry.tool_result = Some(tr.chars().take(10_000).collect());
            }
        }
    }
    Ok(capped)
}

#[cfg(test)]
mod content_builder_tests {
    use super::*;

    #[test]
    fn no_attachments_yields_single_text_block() {
        let content = build_user_content("hello", &[]);
        let blocks = content.as_array().expect("array");
        assert_eq!(blocks.len(), 1);
        assert_eq!(blocks[0]["type"], "text");
        assert_eq!(blocks[0]["text"], "hello");
    }

    #[test]
    fn images_precede_the_text_block_in_order() {
        let attachments = vec![
            ImageAttachment {
                data_base64: "AAA".to_string(),
                media_type: "image/png".to_string(),
            },
            ImageAttachment {
                data_base64: "BBB".to_string(),
                media_type: "image/jpeg".to_string(),
            },
        ];
        let content = build_user_content("what is this?", &attachments);
        let blocks = content.as_array().expect("array");
        assert_eq!(blocks.len(), 3);

        assert_eq!(blocks[0]["type"], "image");
        assert_eq!(blocks[0]["source"]["type"], "base64");
        assert_eq!(blocks[0]["source"]["media_type"], "image/png");
        assert_eq!(blocks[0]["source"]["data"], "AAA");

        assert_eq!(blocks[1]["type"], "image");
        assert_eq!(blocks[1]["source"]["media_type"], "image/jpeg");
        assert_eq!(blocks[1]["source"]["data"], "BBB");

        assert_eq!(blocks[2]["type"], "text");
        assert_eq!(blocks[2]["text"], "what is this?");
    }

    #[test]
    fn empty_text_with_attachments_still_appends_trailing_text_block() {
        let attachments = vec![ImageAttachment {
            data_base64: "AAA".to_string(),
            media_type: "image/png".to_string(),
        }];
        let content = build_user_content("", &attachments);
        let blocks = content.as_array().expect("array");
        assert_eq!(blocks.len(), 2);
        assert_eq!(blocks[0]["type"], "image");
        assert_eq!(blocks[1]["type"], "text");
        assert_eq!(blocks[1]["text"], "");
    }
}

#[cfg(test)]
mod ghost_resume_tests {
    use super::*;

    #[test]
    fn ghost_marker_with_no_init_triggers_a_resume_clear() {
        let lines = vec!["Error: No conversation found with session ID: abc-123".to_string()];
        assert!(should_clear_ghost_resume(false, &lines));
    }

    #[test]
    fn marker_match_is_case_insensitive() {
        let lines = vec!["NO CONVERSATION FOUND with session ID: abc-123".to_string()];
        assert!(should_clear_ghost_resume(false, &lines));
    }

    #[test]
    fn init_having_arrived_never_triggers_a_clear_even_with_the_marker_present() {
        // A real conversation started (Init observed) then hit some later, unrelated failure that
        // happens to mention the marker text — must not be treated as a ghost resume.
        let lines = vec!["No conversation found in unrelated log noise".to_string()];
        assert!(!should_clear_ghost_resume(true, &lines));
    }

    #[test]
    fn early_exit_without_the_marker_is_not_treated_as_a_ghost_resume() {
        // Some other early-exit reason (e.g. auth failure) must not trigger the fallback — it
        // would just loop into the same failure with a fresh conversation.
        let lines = vec!["Error: invalid API key".to_string()];
        assert!(!should_clear_ghost_resume(false, &lines));
    }

    #[test]
    fn no_output_lines_at_all_is_not_treated_as_a_ghost_resume() {
        assert!(!should_clear_ghost_resume(false, &[]));
    }
}

#[cfg(test)]
mod control_request_tests {
    use super::*;

    fn can_use_tool_line() -> Value {
        serde_json::json!({
            "type": "control_request",
            "request_id": "req-1",
            "request": {
                "subtype": "can_use_tool",
                "tool_name": "Bash",
                "input": { "command": "ls" },
            }
        })
    }

    #[test]
    fn can_use_tool_still_yields_a_permission_request() {
        let events = parse_stdout_events(can_use_tool_line());
        assert_eq!(events.len(), 1);
        assert!(matches!(events[0], BridgeEvent::PermissionRequest { .. }));
    }

    #[test]
    fn unknown_subtype_with_no_question_field_forwards_as_other() {
        let line = serde_json::json!({
            "type": "control_request",
            "request_id": "req-2",
            "request": { "subtype": "hook_callback", "hook_event_name": "PreToolUse" }
        });
        let events = parse_stdout_events(line);
        assert_eq!(events.len(), 1);
        assert!(matches!(events[0], BridgeEvent::Other { .. }));
    }

    #[test]
    fn missing_request_object_forwards_as_other_without_panicking() {
        let line = serde_json::json!({ "type": "control_request", "request_id": "req-3" });
        let events = parse_stdout_events(line);
        assert_eq!(events.len(), 1);
        assert!(matches!(events[0], BridgeEvent::Other { .. }));
    }

    #[test]
    fn unknown_subtype_with_a_question_field_yields_a_question_request() {
        let line = serde_json::json!({
            "type": "control_request",
            "request_id": "req-4",
            "request": {
                "subtype": "ask_user_question",
                "question": "Which environment should I deploy to?",
                "body": "Pick one before I continue.",
                "options": ["staging", "production"],
            }
        });
        let events = parse_stdout_events(line);
        assert_eq!(events.len(), 1);
        match &events[0] {
            BridgeEvent::QuestionRequest {
                request_id,
                subtype,
                title,
                body,
                options,
                allow_free_text,
            } => {
                assert_eq!(request_id, "req-4");
                assert_eq!(subtype, "ask_user_question");
                assert_eq!(title, "Which environment should I deploy to?");
                assert_eq!(body.as_deref(), Some("Pick one before I continue."));
                assert_eq!(options.len(), 2);
                assert_eq!(options[0].label, "staging");
                assert_eq!(options[0].value, "staging");
                assert_eq!(options[1].label, "production");
                // Options were provided and no explicit allow_free_text flag -> defaults to false.
                assert!(!allow_free_text);
            }
            other => panic!("expected QuestionRequest, got {other:?}"),
        }
    }

    #[test]
    fn question_with_no_options_defaults_to_allowing_free_text() {
        let line = serde_json::json!({
            "type": "control_request",
            "request_id": "req-5",
            "request": { "subtype": "side_question", "question": "What's the deploy target?" }
        });
        let events = parse_stdout_events(line);
        match &events[0] {
            BridgeEvent::QuestionRequest { options, allow_free_text, .. } => {
                assert!(options.is_empty());
                assert!(allow_free_text);
            }
            other => panic!("expected QuestionRequest, got {other:?}"),
        }
    }

    #[test]
    fn explicit_allow_free_text_flag_overrides_the_options_based_default() {
        let line = serde_json::json!({
            "type": "control_request",
            "request_id": "req-6",
            "request": {
                "subtype": "ask_user_question",
                "question": "Pick a size",
                "choices": [{ "label": "Small", "value": "s" }, { "label": "Large", "value": "l" }],
                "allowFreeText": true,
            }
        });
        let events = parse_stdout_events(line);
        match &events[0] {
            BridgeEvent::QuestionRequest { options, allow_free_text, .. } => {
                assert_eq!(options.len(), 2);
                assert_eq!(options[0].label, "Small");
                assert_eq!(options[0].value, "s");
                assert!(allow_free_text);
            }
            other => panic!("expected QuestionRequest, got {other:?}"),
        }
    }
}
