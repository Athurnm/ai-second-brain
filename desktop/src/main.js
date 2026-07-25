// AI Second Brain Desktop — vanilla frontend over the Tauri IPC contract.
// No framework, no bundler. window.__TAURI__ is available directly (withGlobalTauri: true).

const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

// Event name constants — MUST match the EVT_* string values in src-tauri/src/app.rs exactly.
const EVT = {
  STATUS: "claude:status",
  INIT: "claude:init",
  BLOCK_START: "claude:block-start",
  DELTA: "claude:delta",
  BLOCK_STOP: "claude:block-stop",
  MESSAGE: "claude:message",
  TOOL_RESULT: "claude:tool-result",
  PERMISSION: "claude:permission-request",
  QUESTION: "claude:question-request",
  RESULT: "claude:result",
  EXIT: "claude:exit",
  STDERR: "claude:stderr",
  RESUME_FALLBACK: "claude:resume-fallback",
  SPAWN_FAILURE: "claude:spawn-failure",
  // Emitted from src-tauri/src/lib.rs (EVT_CHECK_FOR_UPDATES), not app.rs, when the user picks
  // "Check for Updates…" from the native menu.
  UPDATE_CHECK_REQUESTED: "updater:check-requested",
};

// Statuses that render the "starting" pane in an empty timeline. Deliberately NOT
// composer-disabling: the CLI does not emit `init` until the first user message arrives
// on stdin, so gating the composer on init deadlocks the whole app (verified live 19 Jul:
// 45s of open-but-silent stdin produced hooks only, never init).
const STARTUP_STATUSES = new Set(["starting", "hook_started", "hook_response"]);
// Only an in-flight turn disables the composer.
const BUSY_STATUSES = new Set(["requesting"]);

// ---------------------------------------------------------------------------
// state
// ---------------------------------------------------------------------------

/** @type {Map<string, SessionState>} */
const sessions = new Map();
let activeSessionId = null;
let elapsedTickerStarted = false;
let dom = {};

// Images staged for the next outgoing message, tied to whatever session is currently active
// (cleared on send and on session switch). Each entry is
// {id, dataBase64, mediaType, sizeBytes, previewDataUrl}.
let pendingAttachments = [];
const MAX_ATTACHMENTS_PER_MESSAGE = 6;
const ATTACH_MAX_DIMENSION = 1600; // px, long side
const ATTACH_MAX_BYTES = 1.5 * 1024 * 1024; // ~1.5MB before downscaling kicks in

// AI providers — mirrors src-tauri/src/providers.rs's ProviderConfig.kind constants.
const KIND_CLAUDE = "claude";
const KIND_GLM = "glm";
const KIND_KIMI = "kimi";
const KIND_9ROUTER = "9router";
const KIND_CUSTOM = "custom";

let providersCache = null; // masked ProviderConfig[] from list_providers, refreshed on every open/save
let multimodalCache = null; // MultimodalSettings from get_multimodal_settings
let claudeAuthStatus = null; // {authenticated, detail} from check_auth, refreshed lazily
const PROVIDER_EXPANDED = new Set(); // provider ids currently expanded in the card list (UI-only)
let providerDrafts = []; // unsaved "+ Add custom provider" cards, never sent to the backend until Save

// ---------------------------------------------------------------------------
// per-provider model options (session settings' MODEL <select>)
// ---------------------------------------------------------------------------
//
// Mirrors src-tauri/src/providers.rs's builtin model defaults ("glm-4.6" / "kimi-k2-0905-preview")
// and the CLI's own --model surface (fable/opus/sonnet/haiku) for `claude`. "" always means
// "default" (no override): for claude that's the CLI's own default, for glm/kimi/custom that's
// whatever model is stored on the provider itself (see providers::provider_env_vars_for_session).
const MODEL_OPTIONS_BY_KIND = {
  [KIND_CLAUDE]: [
    { value: "", label: "default" },
    { value: "fable", label: "fable" },
    { value: "opus", label: "opus" },
    { value: "sonnet", label: "sonnet" },
    { value: "haiku", label: "haiku" },
  ],
  [KIND_GLM]: [
    { value: "", label: "default" },
    { value: "glm-4.6", label: "glm-4.6" },
    { value: "glm-4.5-air", label: "glm-4.5-air" },
  ],
  [KIND_KIMI]: [
    { value: "", label: "default" },
    { value: "kimi-k2-0905-preview", label: "kimi-k2-0905-preview" },
    { value: "kimi-k2-turbo-preview", label: "kimi-k2-turbo-preview" },
  ],
  // Only "default". Which upstream model answers is 9Router's routing decision, made from the
  // combos configured in its own dashboard; sending ANTHROPIC_MODEL would override that with a
  // name the user never picked here.
  [KIND_9ROUTER]: [{ value: "", label: "routed by 9Router" }],
};

// Sentinel <option> value that reveals the free-text #modelCustomInput for a KIND_CUSTOM
// provider — never sent to the backend as a real model value (see commitCustomModel).
const CUSTOM_MODEL_OTHER = "__custom_other__";

function freshSessionState(meta) {
  return {
    meta,
    // Finalized timeline items rendered so far, in order. Each is {type, node}.
    timeline: [],
    // toolUseId -> {content, isError}. Kept so a tool card can render its result even if the
    // card itself is (re)built after the result already arrived, or after a session switch.
    toolResults: new Map(),
    // In-progress assistant turn being streamed, or null between turns.
    // {el, blocksEl, blocks: Map<index, {...}>}
    streaming: null,
    status: "idle", // idle | starting | ready | requesting | hook_started | hook_response | exited
    statusDetail: null,
    pendingPermission: null, // {requestId, toolName, input, description, suggestions, blockedPath}
    pendingQuestion: null, // {requestId, subtype, title, body, options, allowFreeText}
    turnStartedAt: null, // performance.now() timestamp, set when a message is sent
    lastDurationMs: null,
    initInfo: null, // {model, permissionMode, claudeCodeVersion, cwd, slashCommands, agents}
    diagnostics: [], // stderr lines
    history: null, // null = not fetched, [] = fetched-empty, array = TranscriptEntry[]
    historyNodes: null, // cached DOM nodes built once from s.history
    historyLoading: false,
    // toolUseId -> the tool card <details> element currently showing it (live cards built in
    // handleBlockStart, or built by renderToolCard for history/fallback paths). Lets
    // handleToolResult apply a result in O(1) instead of a timeline-wide querySelector — see
    // the "streaming (delta) rendering" section below.
    toolCardsByToolUseId: new Map(),
    // Text of the last "text" content block seen across the current turn's finalized assistant
    // messages (handleMessage keeps overwriting it) — checked at turn-end (handleTurnResult) for
    // the "AI asked you something" soft-affordance hint chip. Not persisted, not shown mid-turn.
    lastAssistantText: "",
  };
}

function ensureSessionState(sessionId, metaSeed) {
  let s = sessions.get(sessionId);
  if (!s) {
    s = freshSessionState(
      metaSeed || {
        sessionId,
        title: "New session",
        createdAtMs: Date.now(),
        updatedAtMs: Date.now(),
        model: null,
        cumUsage: { inputTokens: 0, outputTokens: 0, cacheReadInputTokens: 0, cacheCreationInputTokens: 0 },
        cumCostUsd: 0,
        numTurns: 0,
        live: true,
      }
    );
    sessions.set(sessionId, s);
  }
  return s;
}

// ---------------------------------------------------------------------------
// small DOM / formatting helpers
// ---------------------------------------------------------------------------

function el(tag, opts = {}, children = []) {
  const node = document.createElement(tag);
  if (opts.class) node.className = opts.class;
  if (opts.text !== undefined) node.textContent = opts.text;
  if (opts.html !== undefined) node.innerHTML = opts.html;
  if (opts.attrs) {
    for (const [k, v] of Object.entries(opts.attrs)) node.setAttribute(k, v);
  }
  for (const c of children) node.appendChild(c);
  return node;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function truncate(s, n) {
  if (s.length <= n) return s;
  return s.slice(0, Math.max(0, n - 1)) + "…";
}

// Minimal, safe markdown-lite renderer: escape first, then apply a handful of conventional
// substitutions on the already-escaped text (so `<`/`>`/`&` in model output can never break
// out of the markup). Covers fenced code blocks, inline code, bold, italics, paragraphs, links.
function renderMarkdownLite(raw) {
  if (!raw) return "";
  const parts = String(raw).split(/```/);
  let html = "";
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      let body = part;
      const nl = body.indexOf("\n");
      let lang = "";
      if (nl !== -1) {
        const firstLine = body.slice(0, nl).trim();
        if (firstLine && /^[a-zA-Z0-9_+-]+$/.test(firstLine)) {
          lang = firstLine;
          body = body.slice(nl + 1);
        }
      }
      const cls = lang ? ` class="lang-${escapeHtml(lang)}"` : "";
      html += `<pre><code${cls}>${escapeHtml(body.replace(/\n$/, ""))}</code></pre>`;
    } else {
      html += renderParagraphs(part);
    }
  });
  return html;
}

function renderParagraphs(text) {
  return text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    .map((p) => `<p>${renderInline(escapeHtml(p)).replace(/\n/g, "<br>")}</p>`)
    .join("");
}

// File-path-looking token detector for the timeline's FINAL-format pass only — see the
// "streaming (delta) rendering" section below for why renderMarkdownLite (and therefore this) is
// never invoked per-delta: deltas only ever appendData raw text, they never call into markdown
// rendering. Matches unix/windows/relative paths ending in a short extension (drive-letter,
// `~/`, `./`/`../`, or bare workspace-relative like `notes/foo.md`).
const FILE_MENTION_RE = /(?:[A-Za-z]:\\|~\/|\.{0,2}\/)?[\w.-]+(?:[\/\\][\w.-]+)+\.[A-Za-z0-9]{1,8}/g;
// Matches the same http(s) URLs renderInline auto-links, used only to stash URL text out of the
// string before FILE_MENTION_RE runs — otherwise a bare "domain.com/path/to/file.png" substring
// inside a URL gets mistaken for a file mention (FILE_MENTION_RE has no way to tell the two apart
// on its own since a URL's path segment is syntactically identical to a real file path).
const URL_GUARD_RE = /(https?:\/\/[^\s<]+[^\s<.,)])/g;

// Wraps file-path-looking tokens in a clickable, colored span. `text` must already be HTML-escaped
// (callers always escape first) — the wrapped match is re-embedded verbatim, so nothing here can
// introduce unescaped `<`/`>`/`&`/`"` into the DOM. Shared by renderInline (chat/user-message
// markdown) and the tool-card finalizers (renderToolCard, finalizeStreamingMessage,
// applyToolResultToCard) — never called from the per-delta flush path.
function linkifyFileMentions(text) {
  const urlStash = [];
  let out = text.replace(URL_GUARD_RE, (m) => {
    urlStash.push(m);
    return `\u0000FMURL${urlStash.length - 1}\u0000`;
  });
  out = out.replace(FILE_MENTION_RE, (m) => `<span class="file-mention" data-file-path="${m}">${m}</span>`);
  out = out.replace(/\u0000FMURL(\d+)\u0000/g, (_m, i) => urlStash[Number(i)]);
  return out;
}

// escape + linkify with no markdown parsing — for tool-card preview/input/result text, which is
// raw JSON/command output, not prose.
function escapeAndLinkifyFileMentions(raw) {
  return linkifyFileMentions(escapeHtml(raw == null ? "" : String(raw)));
}

function renderInline(escaped) {
  let out = escaped;

  // Stash inline code before file-mention linkification (and everything else below) runs, so a
  // path-looking token inside a backtick span is never double-wrapped — restored verbatim
  // (as <code>) at the very end.
  const codeStash = [];
  out = out.replace(/`([^`]+)`/g, (_m, code) => {
    codeStash.push(code);
    return `\u0000FMCODE${codeStash.length - 1}\u0000`;
  });

  out = linkifyFileMentions(out);

  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  out = out.replace(/(https?:\/\/[^\s<]+[^\s<.,)])/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');

  out = out.replace(/\u0000FMCODE(\d+)\u0000/g, (_m, i) => `<code>${codeStash[Number(i)]}</code>`);

  return out;
}

function summarizeToolInput(input) {
  if (input == null) return "";
  if (typeof input !== "object") return truncate(String(input), 120);
  const preferKeys = ["command", "file_path", "path", "pattern", "url", "query", "description"];
  for (const k of preferKeys) {
    if (typeof input[k] === "string" && input[k].length > 0) return truncate(input[k], 120);
  }
  const keys = Object.keys(input);
  if (keys.length === 0) return "";
  const k = keys[0];
  let v = input[k];
  if (v && typeof v === "object") v = JSON.stringify(v);
  return truncate(`${k}: ${v}`, 120);
}

function formatToolResultContent(content) {
  if (content == null) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((block) => {
        if (block && typeof block === "object") {
          if (typeof block.text === "string") return block.text;
          return JSON.stringify(block, null, 2);
        }
        return String(block);
      })
      .join("\n\n");
  }
  return JSON.stringify(content, null, 2);
}

function formatCompactNumber(n) {
  n = n || 0;
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

function formatCost(usd) {
  return `$${(usd || 0).toFixed(4)}`;
}

function formatDuration(ms) {
  if (ms == null) return "";
  if (ms < 1000) return `${ms}ms`;
  const secs = ms / 1000;
  if (secs < 60) return `${secs.toFixed(1)}s`;
  const m = Math.floor(secs / 60);
  const rem = Math.round(secs % 60);
  return `${m}m ${rem}s`;
}

function isNearBottom() {
  const t = dom.timeline;
  return t.scrollHeight - t.scrollTop - t.clientHeight < 120;
}

// Preserves "was the user already at the bottom" scroll behavior: check BEFORE mutating so a
// user who has scrolled up to read history is never yanked back down by new streaming content.
function withStickyScroll(mutateFn) {
  const stick = isNearBottom();
  mutateFn();
  if (stick) dom.timeline.scrollTop = dom.timeline.scrollHeight;
}

function appendToActiveTimeline(node) {
  withStickyScroll(() => dom.timeline.appendChild(node));
}

function clearEmptyState() {
  if (dom.timeline.children.length === 1) {
    const only = dom.timeline.children[0];
    if (
      only.classList.contains("empty-state") ||
      only.classList.contains("starting-state") ||
      only.classList.contains("resume-note")
    ) {
      dom.timeline.innerHTML = "";
    }
  }
}

function showToast(message, kind = "error") {
  const toast = el("div", { class: `toast toast-${kind}`, text: message });
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("show"));
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  }, 4500);
}

// ---------------------------------------------------------------------------
// auto-updater (tauri-plugin-updater + tauri-plugin-process)
//
// No @tauri-apps/plugin-updater/process npm packages: withGlobalTauri only injects
// @tauri-apps/api's own modules onto window.__TAURI__ (core/event/app/...), never a plugin's
// guest-js — same reason opener/dialog above are driven through raw `invoke("plugin:x|cmd")`
// rather than a `window.__TAURI__.opener`/`.dialog` namespace that doesn't exist. `Channel` is
// part of @tauri-apps/api/core, though, so it IS available as `window.__TAURI__.core.Channel`
// for the download-progress callback.
// ---------------------------------------------------------------------------

/** Metadata `{ rid, currentVersion, version, date, body, rawJson }` from the last successful
 *  `plugin:updater|check`, or null once installed/dismissed. Holds the resource id `download_and_install`
 *  needs. */
let pendingUpdate = null;
// "Later" on the auto-check banner must not re-nag for the rest of this run. A manual "Check for
// Updates…" is a fresh explicit ask, so it always shows its result regardless of this flag.
let updateDismissedThisRun = false;

async function checkForUpdates(manual) {
  if (!manual && updateDismissedThisRun) return;
  try {
    const meta = await invoke("plugin:updater|check", {});
    if (!meta) {
      if (manual) showToast("You're already on the latest version.", "info");
      return;
    }
    pendingUpdate = meta;
    showUpdateBanner(meta);
  } catch (err) {
    // Silent on the automatic start-up check (offline is the common case) — loud only when the
    // user explicitly asked via the menu.
    if (manual) showToast("Update check failed: " + err, "error");
  }
}

function showUpdateBanner(meta) {
  if (!dom.updateBanner) return;
  dom.updateBannerText.textContent = `v${meta.version} is available`;
  dom.updateBannerProgress.classList.add("hidden");
  dom.updateBannerProgress.textContent = "";
  dom.updateBannerActions.classList.remove("hidden");
  dom.updateBanner.classList.remove("hidden");
}

function dismissUpdateBanner() {
  updateDismissedThisRun = true;
  if (dom.updateBanner) dom.updateBanner.classList.add("hidden");
}

async function downloadAndInstallUpdate() {
  if (!pendingUpdate || !dom.updateBanner) return;
  dom.updateBannerActions.classList.add("hidden");
  dom.updateBannerProgress.classList.remove("hidden");
  dom.updateBannerProgress.textContent = "Downloading…";
  let received = 0;
  let total = 0;
  try {
    const channel = new window.__TAURI__.core.Channel();
    channel.onmessage = (evt) => {
      if (evt.event === "Started") {
        total = evt.data.contentLength || 0;
      } else if (evt.event === "Progress") {
        received += evt.data.chunkLength;
        dom.updateBannerProgress.textContent = total
          ? `Downloading… ${Math.min(100, Math.round((received / total) * 100))}%`
          : `Downloading… ${(received / 1e6).toFixed(1)} MB`;
      } else if (evt.event === "Finished") {
        dom.updateBannerProgress.textContent = "Installing…";
      }
    };
    await invoke("plugin:updater|download_and_install", { rid: pendingUpdate.rid, onEvent: channel });
    dom.updateBannerProgress.textContent = "Restarting…";
    await invoke("plugin:process|restart");
  } catch (err) {
    showToast("Update failed: " + err, "error");
    dom.updateBannerProgress.classList.add("hidden");
    dom.updateBannerActions.classList.remove("hidden");
  }
}

// ---------------------------------------------------------------------------
// harness command launcher (left rail)
// ---------------------------------------------------------------------------

async function loadHarnessCommands() {
  try {
    const commands = await invoke("list_harness_commands");
    dom.commandList.innerHTML = "";
    if (commands.length === 0) {
      dom.commandList.appendChild(el("div", { class: "rail-empty", text: "No commands found" }));
      // Older builds created workspaces without the starter commands; offer the one-click heal
      // (backend copies only files that are missing, never overwrites user edits).
      const restoreBtn = el("button", { class: "rail-restore-btn", text: "RESTORE STARTER COMMANDS" });
      restoreBtn.addEventListener("click", async () => {
        restoreBtn.disabled = true;
        try {
          const n = await invoke("restore_template_commands");
          showToast(n > 0 ? `Restored ${n} starter command(s)` : "Starter commands already in place", "info");
          await loadHarnessCommands();
        } catch (e) {
          showToast("Could not restore commands: " + e);
          restoreBtn.disabled = false;
        }
      });
      dom.commandList.appendChild(restoreBtn);
      return;
    }
    for (const cmd of commands) {
      const item = el("div", { class: "command-item" });
      item.appendChild(el("div", { class: "cmd-name", text: "/" + cmd.name }));
      if (cmd.description) item.appendChild(el("div", { class: "cmd-desc", text: cmd.description }));
      if (cmd.argumentHint) item.title = `Argument: ${cmd.argumentHint}`;
      item.addEventListener("click", () => seedComposerWithCommand(cmd));
      dom.commandList.appendChild(item);
    }
  } catch (err) {
    dom.commandList.innerHTML = "";
    dom.commandList.appendChild(el("div", { class: "rail-empty", text: "Failed to load commands: " + err }));
  }
}

function seedComposerWithCommand(cmd) {
  const text = `/${cmd.name} `;
  dom.composerInput.value = text;
  dom.composerInput.placeholder = cmd.argumentHint || "Message Claude Code…";
  autoGrowComposer();
  if (!dom.composerInput.disabled) {
    dom.composerInput.focus();
    dom.composerInput.setSelectionRange(text.length, text.length);
  }
}

// ---------------------------------------------------------------------------
// session rail
// ---------------------------------------------------------------------------

async function loadSessions() {
  try {
    const metas = await invoke("list_sessions");
    for (const meta of metas) {
      sessions.set(meta.sessionId, freshSessionState(meta));
    }
    renderSessionList();
    if (metas.length > 0) {
      selectSession(metas[0].sessionId);
    }
  } catch (err) {
    showToast("Failed to load sessions: " + err);
  }
}

// Re-pulls SessionMeta (model/cumUsage/cumCostUsd/numTurns/live) from the backing store rather
// than reimplementing its summing logic client-side (SessionStore.upsert accumulates usage/cost/
// turns turn over turn; refetching avoids that arithmetic drifting out of sync with the source of
// truth on disk).
async function refreshSessionMeta() {
  try {
    const metas = await invoke("list_sessions");
    for (const meta of metas) {
      const s = sessions.get(meta.sessionId);
      if (s) {
        s.meta = meta;
      } else {
        sessions.set(meta.sessionId, freshSessionState(meta));
      }
    }
    renderSessionList();
    if (activeSessionId) updateStatusBar();
  } catch (err) {
    // Non-fatal: local optimistic state stays until the next successful refresh.
  }
}

function renderSessionList() {
  const items = Array.from(sessions.values()).sort((a, b) => b.meta.updatedAtMs - a.meta.updatedAtMs);
  dom.sessionList.innerHTML = "";
  if (items.length === 0) {
    dom.sessionList.appendChild(el("div", { class: "rail-empty", text: "No sessions yet" }));
    return;
  }
  for (const s of items) {
    dom.sessionList.appendChild(renderSessionRow(s));
  }
}

function renderSessionRow(s) {
  const row = el("div", { class: "session-item" + (s.meta.sessionId === activeSessionId ? " active" : "") });

  const top = el("div", { class: "session-item-top" });
  top.appendChild(el("span", { class: "session-dot" + (s.meta.live ? " live" : "") }));
  top.appendChild(el("span", { class: "session-title", text: s.meta.title || "New session" }));
  if (s.pendingPermission) {
    top.appendChild(
      el("span", {
        class: "session-warn",
        text: "needs you",
        attrs: { title: `Waiting for your permission — ${s.pendingPermission.toolName}` },
      })
    );
  }
  row.appendChild(top);
  row.appendChild(el("div", { class: "session-sub", text: sessionSubtitle(s) }));

  const actions = el("div", { class: "session-actions" });
  const renameBtn = el("button", { class: "session-action", text: "Rename" });
  renameBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    startRenameSession(s.meta.sessionId);
  });
  actions.appendChild(renameBtn);

  if (s.meta.live) {
    const stop = el("button", { class: "session-action", text: "Stop" });
    stop.addEventListener("click", (e) => {
      e.stopPropagation();
      stopSession(s.meta.sessionId);
    });
    actions.appendChild(stop);
  }

  const del = el("button", { class: "session-action danger", text: "Delete" });
  del.addEventListener("click", (e) => {
    e.stopPropagation();
    deleteSessionConfirm(s.meta.sessionId);
  });
  actions.appendChild(del);

  row.appendChild(actions);
  row.addEventListener("click", () => selectSession(s.meta.sessionId));
  return row;
}

function sessionSubtitle(s) {
  const bits = [s.meta.live ? "live" : "stopped"];
  if (s.meta.numTurns) bits.push(`${s.meta.numTurns} turn${s.meta.numTurns === 1 ? "" : "s"}`);
  if (s.meta.cumCostUsd) bits.push(formatCost(s.meta.cumCostUsd));
  return bits.join(" · ");
}

function selectSession(sessionId) {
  activeSessionId = sessionId;
  clearPendingAttachments();
  const s = sessions.get(sessionId);
  if (!s) {
    dom.sessionSettingsBtn.disabled = true;
    closeSessionSettingsPopover();
    renderSessionList();
    return;
  }
  dom.chatTitle.textContent = s.meta.title || "New session";
  dom.chatTitle.classList.remove("hidden");
  dom.chatTitleInput.classList.add("hidden");
  dom.chatMeta.textContent = s.initInfo ? `${s.initInfo.model} · ${s.initInfo.cwd}` : "";

  dom.sessionSettingsBtn.disabled = false;
  populateSessionSettings(s);

  renderSessionList();
  fullRenderTimeline(sessionId);
  renderDiagnostics(s);
  updateComposerEnabled();
  updateStatusBar();
  updatePermissionUI();
  updateQuestionUI();
  const endsWithQuestion =
    !s.pendingPermission && !s.pendingQuestion && /[?？]\s*$/.test((s.lastAssistantText || "").trim());
  dom.questionHintChip.classList.toggle("hidden", !endsWithQuestion);
  dom.composerInput.focus();
  if (s.status === "exited") HUD.onSessionExited();
  else HUD.onSessionLive();
  if (s.pendingPermission) HUD.onPermissionRequest();
  else HUD.onPermissionResolved();

  if (s.history === null && s.meta.numTurns > 0 && !s.historyLoading) {
    s.historyLoading = true;
    invoke("get_transcript", { sessionId })
      .then((entries) => {
        s.history = entries;
      })
      .catch(() => {
        s.history = [];
      })
      .finally(() => {
        s.historyLoading = false;
        if (sessionId === activeSessionId) fullRenderTimeline(sessionId);
      });
  }
}

// ---------------------------------------------------------------------------
// session settings row (model / effort / permission mode picker)
// ---------------------------------------------------------------------------

function openSessionSettingsPopover() {
  if (dom.sessionSettingsBtn.disabled) return;
  dom.sessionSettingsPopover.classList.remove("hidden");
  dom.sessionSettingsBtn.setAttribute("aria-expanded", "true");
}
function closeSessionSettingsPopover() {
  dom.sessionSettingsPopover.classList.add("hidden");
  dom.sessionSettingsBtn.setAttribute("aria-expanded", "false");
}
function toggleSessionSettingsPopover() {
  if (dom.sessionSettingsPopover.classList.contains("hidden")) openSessionSettingsPopover();
  else closeSessionSettingsPopover();
}

// Repopulates the MODEL <select> for `providerId`'s kind (claude/glm/kimi/custom) and selects
// `preferredModel` if it's one of the resulting options. Called whenever the session settings
// popover is opened/refreshed for a session AND whenever the provider <select> changes, per the
// contract ("when the session provider changes (or session settings open), repopulate model
// options") — a stale claude-shaped list left over from a prior provider would otherwise let the
// user "pick" e.g. "opus" for a glm session, which the CLI would silently ignore.
function populateModelSelectOptions(providerId, preferredModel) {
  const p = findProviderById(providerId);
  const kind = (p && p.kind) || KIND_CLAUDE;
  dom.modelSelect.innerHTML = "";

  if (kind === KIND_CUSTOM) {
    dom.modelSelect.appendChild(el("option", { text: "default", attrs: { value: "" } }));
    // The provider's own configured model (set in AI PROVIDERS → this provider's "model-name"
    // field) shown as a selectable option distinct from "default", so switching back to it from
    // a one-off "Other…" pick doesn't require retyping it.
    const storedModel = p && p.model;
    if (storedModel) {
      dom.modelSelect.appendChild(el("option", { text: storedModel, attrs: { value: storedModel } }));
    }
    dom.modelSelect.appendChild(el("option", { text: "Other…", attrs: { value: CUSTOM_MODEL_OTHER } }));

    const isKnownValue = !preferredModel || preferredModel === storedModel;
    if (isKnownValue) {
      dom.modelSelect.value = preferredModel || "";
      dom.modelCustomInput.classList.add("hidden");
    } else {
      // preferredModel is a previously-typed custom value that doesn't match "default" or the
      // provider's current stored model — land straight on "Other…" with it pre-filled instead
      // of silently losing it.
      dom.modelSelect.value = CUSTOM_MODEL_OTHER;
      dom.modelCustomInput.value = preferredModel;
      dom.modelCustomInput.classList.remove("hidden");
    }
    return;
  }

  dom.modelCustomInput.classList.add("hidden");
  const options = MODEL_OPTIONS_BY_KIND[kind] || MODEL_OPTIONS_BY_KIND[KIND_CLAUDE];
  for (const opt of options) {
    dom.modelSelect.appendChild(el("option", { text: opt.label, attrs: { value: opt.value } }));
  }
  const known = options.some((opt) => opt.value === preferredModel);
  dom.modelSelect.value = known ? preferredModel : "";
}

function populateSessionSettings(s) {
  dom.effortSelect.value = (s.meta && s.meta.preferredEffort) || "";
  const mode = (s.meta && s.meta.permissionMode) || "manual";
  // The mode picker offers manual/acceptEdits/plan/bypassPermissions and the stored mode is
  // applied directly — no coercion. Selecting bypassPermissions in the UI is gated by a confirm
  // modal (see handleModeSelectChange), but a mode already persisted in session meta (from a
  // prior confirmed selection, or a hand-edited sessions.json) is trusted and shown as-is.
  dom.modeSelect.value = mode;
  // Tracks the last-known-good value so a cancelled FULL AUTO confirm (or a failed settings
  // write) has something to revert the <select> to.
  dom.modeSelect.dataset.prevValue = mode;

  renderProviderSelectOptions();
  const providerId = (s.meta && s.meta.providerId) || "claude";
  if (Array.from(dom.providerSelect.options).some((o) => o.value === providerId)) {
    dom.providerSelect.value = providerId;
  }
  populateModelSelectOptions(dom.providerSelect.value, s.meta && s.meta.preferredModel);
}

// Provider <select> changed — the model list depends on the provider's kind, so it must be
// rebuilt for the NEWLY chosen provider before committing. Any previously selected model is
// dropped back to "default" rather than carried over silently: a model name meaningful for the
// old provider (e.g. "opus") is almost never meaningful for the new one.
function handleProviderSelectChange() {
  populateModelSelectOptions(dom.providerSelect.value, null);
  commitSessionSettings();
}

// MODEL <select> changed. The CUSTOM_MODEL_OTHER sentinel is never itself a valid model value —
// selecting it just reveals the free-text input and waits for commitCustomModel() instead of
// committing immediately.
function handleModelSelectChange() {
  if (dom.modelSelect.value === CUSTOM_MODEL_OTHER) {
    dom.modelCustomInput.classList.remove("hidden");
    dom.modelCustomInput.value = "";
    dom.modelCustomInput.focus();
    return;
  }
  dom.modelCustomInput.classList.add("hidden");
  commitSessionSettings();
}

// Commits a free-typed custom-provider model name (Enter or blur on #modelCustomInput). Persists
// it two places, per contract ("a free-text input persisted to the provider config"): the
// session's own preferredModel (so THIS session's next spawn uses it), and the provider's own
// `model` field via upsert_provider (so it becomes the remembered default for that provider next
// time, and shows up as the non-"Other…" option in populateModelSelectOptions).
async function commitCustomModel() {
  const value = dom.modelCustomInput.value.trim();
  if (!value) return;

  const providerId = dom.providerSelect.value;
  const p = findProviderById(providerId);
  if (p && p.kind === KIND_CUSTOM && p.model !== value) {
    try {
      await invoke("upsert_provider", {
        provider: {
          id: p.id,
          kind: p.kind,
          label: p.label,
          baseUrl: p.baseUrl || null,
          apiKey: p.apiKey || null, // masked sentinel echoed back unchanged — see ProviderStore::upsert
          model: value,
          supportsImages: !!p.supportsImages,
          enabled: p.enabled !== false,
        },
      });
      await loadProviders();
    } catch (err) {
      showToast("Failed to save custom model on the provider: " + err);
    }
  }

  await commitSessionSettings(value);
  if (activeSessionId) {
    const s = sessions.get(activeSessionId);
    if (s) populateModelSelectOptions(dom.providerSelect.value, s.meta && s.meta.preferredModel);
  }
}

// Selecting "FULL AUTO" (bypassPermissions) in the picker is gated by a confirm modal — the
// select's value flips immediately (native <select> behavior) but the setting isn't committed
// until the user explicitly confirms; Cancel reverts the <select> to its prior value.
function handleModeSelectChange() {
  if (dom.modeSelect.value === "bypassPermissions") {
    dom.fullAutoConfirmModal.classList.remove("hidden");
    return;
  }
  dom.modeSelect.dataset.prevValue = dom.modeSelect.value;
  commitSessionSettings();
}

function cancelFullAutoConfirm() {
  dom.fullAutoConfirmModal.classList.add("hidden");
  dom.modeSelect.value = dom.modeSelect.dataset.prevValue || "manual";
}

async function confirmFullAuto() {
  dom.fullAutoConfirmModal.classList.add("hidden");
  dom.modeSelect.dataset.prevValue = "bypassPermissions";
  await commitSessionSettings();
}

// dom.modelSelect.value is only a real model name (or "") when it's NOT the CUSTOM_MODEL_OTHER
// sentinel. If "Other…" is currently selected but the free-text commit hasn't happened yet (e.g.
// the user picked "Other…" then immediately changed effort/mode/provider instead of typing a
// value), reading dom.modelSelect.value directly would send the literal sentinel string as the
// model. Fall back to whatever's already typed in the free-text input, then to the session's
// last-known preferredModel, rather than ever letting the sentinel itself leak out.
function resolveModelSelectValue(s) {
  if (dom.modelSelect.value !== CUSTOM_MODEL_OTHER) return dom.modelSelect.value;
  const typed = dom.modelCustomInput.value.trim();
  if (typed) return typed;
  return (s && s.meta && s.meta.preferredModel) || "";
}

// `modelOverride`, when a string, wins over dom.modelSelect.value — used by commitCustomModel()
// to commit a free-typed value that was never itself a <select> option. Every other call site
// (the change-event listeners) passes the native Event object or nothing, both of which fail the
// `typeof === "string"` check and fall through to reading the <select> (via resolveModelSelectValue)
// as before.
async function commitSessionSettings(modelOverride) {
  const sessionId = activeSessionId;
  if (!sessionId) return;
  const s = sessions.get(sessionId);
  if (!s) return;

  const modelValue = typeof modelOverride === "string" ? modelOverride : resolveModelSelectValue(s);
  try {
    const meta = await invoke("set_session_settings", {
      sessionId,
      model: modelValue,
      effort: dom.effortSelect.value,
      permissionMode: dom.modeSelect.value,
      providerId: dom.providerSelect.value || undefined,
    });
    s.meta = meta;
    if (sessionId === activeSessionId) {
      renderSessionList();
      updateComposerEnabled();
    }
    if (s.meta.live && s.status !== "requesting") {
      await invoke("close_session", { sessionId });
    }
  } catch (err) {
    showToast("Failed to update session settings: " + err);
    populateSessionSettings(s);
  }
}

async function stopSession(sessionId) {
  try {
    await invoke("close_session", { sessionId });
  } catch (err) {
    showToast("Stop failed: " + err);
  }
}

async function deleteSessionConfirm(sessionId) {
  const s = sessions.get(sessionId);
  const ok = window.confirm(
    `Delete "${(s && s.meta.title) || "this session"}"? This only removes it from AI Second Brain Desktop — the CLI's own transcript is untouched.`
  );
  if (!ok) return;
  try {
    await invoke("delete_session", { sessionId });
    sessions.delete(sessionId);
    if (activeSessionId === sessionId) {
      activeSessionId = null;
      dom.timeline.innerHTML = "";
      dom.timeline.appendChild(
        el("div", { class: "empty-state", html: "<p>Pick a command on the left, or start a new session.</p>" })
      );
      dom.chatTitle.textContent = "Select or start a session";
      dom.chatMeta.textContent = "";
      dom.sessionSettingsBtn.disabled = true;
      closeSessionSettingsPopover();
      updateComposerEnabled();
      updateStatusBar();
      closePermissionModal();
    }
    renderSessionList();
  } catch (err) {
    showToast("Delete failed: " + err);
  }
}

function startRenameSession(sessionId) {
  if (sessionId !== activeSessionId) {
    selectSession(sessionId);
  }
  beginChatTitleEdit();
}

// ---------------------------------------------------------------------------
// chat header (inline title rename)
// ---------------------------------------------------------------------------

function beginChatTitleEdit() {
  if (!activeSessionId) return;
  const s = sessions.get(activeSessionId);
  dom.chatTitleInput.value = s.meta.title || "";
  dom.chatTitle.classList.add("hidden");
  dom.chatTitleInput.classList.remove("hidden");
  dom.chatTitleInput.focus();
  dom.chatTitleInput.select();
}

async function commitChatTitleEdit() {
  const sessionId = activeSessionId;
  dom.chatTitleInput.classList.add("hidden");
  dom.chatTitle.classList.remove("hidden");
  if (!sessionId) return;
  const s = sessions.get(sessionId);
  const trimmed = dom.chatTitleInput.value.trim();
  if (!trimmed || trimmed === s.meta.title) return;
  try {
    const meta = await invoke("rename_session", { sessionId, title: trimmed });
    s.meta = meta;
    if (sessionId === activeSessionId) dom.chatTitle.textContent = meta.title;
    renderSessionList();
  } catch (err) {
    showToast("Rename failed: " + err);
  }
}

// ---------------------------------------------------------------------------
// timeline rendering
// ---------------------------------------------------------------------------

// Builds a single history entry (from get_transcript) into the same DOM shapes used for live
// messages, marked with the "history" class for dimming, and cached on s.historyNodes so
// repeated fullRenderTimeline() calls don't re-parse/re-render the same transcript.
function buildHistoryEntryNode(entry) {
  if (entry.role === "user") {
    const node = el("div", { class: "msg user history" });
    const bubble = el("div", { class: "bubble" });
    renderMessageImages(bubble, entry.images);
    if (entry.text) bubble.insertAdjacentHTML("beforeend", renderMarkdownLite(entry.text));
    node.appendChild(bubble);
    return node;
  }

  if (entry.role === "assistant") {
    const node = el("div", { class: "msg assistant history" });
    const bubble = el("div", { class: "bubble" });
    const blocksEl = el("div", { class: "msg-blocks" });
    blocksEl.innerHTML = renderMarkdownLite(entry.text || "");
    bubble.appendChild(blocksEl);
    node.appendChild(bubble);
    return node;
  }

  // role === "tool" — reuse the live tool-card builder with toolUseId = null so a later
  // claude:tool-result for a live turn can never accidentally match a history card via
  // [data-tool-id] lookup (handleToolResult only queries by toolUseId string).
  const node = el("div", { class: "msg assistant history" });
  const bubble = el("div", { class: "bubble" });
  const blocksEl = el("div", { class: "msg-blocks" });
  const dummySessionState = { toolResults: new Map() };
  const card = renderToolCard(dummySessionState, null, entry.toolName, entry.toolInput);
  if (entry.toolResult != null) {
    applyToolResultToCard(card, entry.toolResult, !!entry.isError);
  }
  blocksEl.appendChild(card);
  bubble.appendChild(blocksEl);
  node.appendChild(bubble);
  return node;
}

function buildHistoryNodes(s) {
  const nodes = [];
  for (const entry of s.history) {
    if (!entry || !entry.role) continue;
    nodes.push(buildHistoryEntryNode(entry));
  }
  return nodes;
}

function fullRenderTimeline(sessionId) {
  const s = sessions.get(sessionId);
  if (!s) return;
  dom.timeline.innerHTML = "";

  const hasHistory = Array.isArray(s.history) && s.history.length > 0;
  if (hasHistory) {
    if (!s.historyNodes) {
      s.historyNodes = buildHistoryNodes(s);
    }
    for (const node of s.historyNodes) dom.timeline.appendChild(node);
    dom.timeline.appendChild(el("div", { class: "history-divider", text: "— earlier —" }));
  }

  if (s.timeline.length === 0 && !s.streaming) {
    if (STARTUP_STATUSES.has(s.status)) {
      dom.timeline.appendChild(renderStartingState(s));
      dom.timeline.scrollTop = 0;
      return;
    }
    // A session can be known locally (from list_sessions, or from a prior turn) without any
    // in-app transcript rendered from the current run. Once history is fetched (§2, get_transcript)
    // it's rendered above; this note now only covers the gap while that fetch is still in flight
    // or came back empty (e.g. transcript file not found).
    if (s.meta.numTurns > 0 && (s.historyLoading || (Array.isArray(s.history) && s.history.length === 0))) {
      dom.timeline.appendChild(
        el("div", {
          class: "resume-note",
          text:
            "This session has prior context on the CLI side, but AI Second Brain Desktop only shows messages sent during this app run. Send a message to continue — full context is preserved via resume.",
        })
      );
      return;
    }
    if (!hasHistory) {
      dom.timeline.appendChild(
        el("div", {
          class: "empty-state",
          html: "<p>Pick a command on the left, or type a message below.</p>",
        })
      );
    }
    dom.timeline.scrollTop = dom.timeline.scrollHeight;
    return;
  }

  for (const item of s.timeline) {
    dom.timeline.appendChild(item.node);
  }
  if (s.streaming && s.streaming.el) {
    dom.timeline.appendChild(s.streaming.el);
  }
  dom.timeline.scrollTop = dom.timeline.scrollHeight;
}

function renderStartingState(s) {
  const wrap = el("div", { class: "starting-state" });
  wrap.appendChild(el("div", { class: "spinner" }));
  wrap.appendChild(el("div", { class: "starting-title", text: "Starting Claude Code…" }));
  wrap.appendChild(
    el("div", {
      text: "Loading your workspace — CLAUDE.md, commands, and any other files it defines. You can type your message now — it will be answered as soon as startup finishes.",
    })
  );
  if (s.statusDetail) {
    wrap.appendChild(el("div", { class: "starting-detail", text: s.statusDetail }));
  }
  return wrap;
}

// images: array of {mediaType, previewDataUrl} (live send) or {mediaType, base64} (replayed
// TranscriptImage) — renderMessageImages accepts either shape.
function appendUserMessage(sessionId, text, images) {
  const s = ensureSessionState(sessionId);
  const node = el("div", { class: "msg user" });
  const bubble = el("div", { class: "bubble" });
  renderMessageImages(bubble, images);
  if (text) bubble.insertAdjacentHTML("beforeend", renderMarkdownLite(text));
  node.appendChild(bubble);
  s.timeline.push({ type: "user", node });
  if (sessionId === activeSessionId) {
    clearEmptyState();
    appendToActiveTimeline(node);
  }
}

// Shared renderer for both system-error cards (spawn failures, send failures, turn errors) and
// neutral system notices (e.g. the resume-fallback message) — same left-aligned row shape as a
// normal assistant message, styled by `kind` via CSS (`system-card-error` / `system-card-notice`).
function appendSystemCard(sessionId, text, kind) {
  const node = el("div", { class: "msg assistant" });
  const bubble = el("div", { class: `bubble system-card system-card-${kind}` });
  bubble.appendChild(el("p", { class: "system-card-text", text }));
  node.appendChild(bubble);
  const s = ensureSessionState(sessionId);
  s.timeline.push({ type: kind, node });
  if (sessionId === activeSessionId) {
    clearEmptyState();
    appendToActiveTimeline(node);
  }
}

function appendSystemError(sessionId, text) {
  appendSystemCard(sessionId, text, "error");
}

function appendSystemNotice(sessionId, text) {
  appendSystemCard(sessionId, text, "notice");
}

// ---------------------------------------------------------------------------
// streaming (delta) rendering — incremental, stable-DOM contract
//
// Root causes of the "nge-lag dan susah dibaca" (laggy, hard to read) reports,
// found by tracing the full event path end to end:
//
//   1. THE BIG ONE — handleMessage (claude:message) used to throw away the
//      entire streaming bubble (`s.streaming.el.remove()`) and rebuild every
//      block from scratch via renderFinalizedAssistantMessage, re-parsing
//      markdown even for text that had *just* finished streaming pixel-for-
//      pixel identical content. That's a guaranteed reflow + a visible swap
//      the instant a message finishes — the "jump" users feel as lag.
//   2. `.stream-block` had no `white-space: pre-wrap` (see styles.css), so
//      raw streamed text collapsed every newline into one run-on wall of
//      text — genuinely hard to read — right up until the format-swap above
//      suddenly broke it into real paragraphs. That sudden reflow *is* the
//      visible "susah dibaca" moment.
//   3. `.timeline` had `scroll-behavior: smooth` in CSS, which applies to
//      *any* scrollTop write, not just scrollIntoView. The existing rAF
//      batching (one scrollTop write per frame) still meant a NEW smooth-
//      scroll animation was kicked off up to ~60 times/sec during a fast
//      stream, each one interrupting the last mid-flight — a self-inflicted
//      fight that reads as constant stutter. Fixed in styles.css (removed).
//
// New contract:
//   - Each block gets ONE persistent DOM node, created in handleBlockStart
//     and never removed/replaced afterward. tool_use blocks get their FULL
//     final <details class="tool-card"> shape immediately (icon/name/preview/
//     input <pre>) — "insert once, update status in place." thinking blocks
//     get their final <details class="thinking-block"> shape immediately too
//     (thinking is never markdown-formatted, so there's nothing to swap).
//   - handleDelta only ever appends into a per-block Text node via
//     appendData — never creates a new text node, never touches layout.
//     Deltas are buffered and flushed at most every ~33ms (~30fps) via rAF,
//     so a fast stream still does O(1) DOM writes per frame instead of one
//     per delta.
//   - handleBlockStop formats ONLY that block (markdown-transform its own
//     node's content) — never touches sibling blocks or the message wrapper.
//   - handleMessage (message/turn end) diffs the authoritative `content[]`
//     against the blocks already rendered live, by index (Anthropic's raw
//     content_block_start/delta/stop indices line up 1:1 with the finished
//     message's content array — see bridge.rs's parse_stream_event /
//     parse_assistant_event). Already-rendered blocks are left alone; it
//     only fills in the couple of fields that aren't knowable until the
//     block is complete (a tool_use's full parsed input) and then folds the
//     SAME streaming DOM node into the timeline — no remove, no rebuild.
// ---------------------------------------------------------------------------

function ensureStreamingBubble(s, sessionId) {
  if (!s.streaming) {
    const wrap = el("div", { class: "msg streaming" });
    const bubble = el("div", { class: "bubble" });
    const blocksEl = el("div", { class: "msg-blocks" });
    bubble.appendChild(blocksEl);
    wrap.appendChild(bubble);
    s.streaming = { el: wrap, blocksEl, blocks: new Map() };
    if (sessionId === activeSessionId) {
      clearEmptyState();
      appendToActiveTimeline(wrap);
    }
  }
  return s.streaming;
}

// Builds the FULL final tool-card DOM shape (same markup renderToolCard produces) up front, with
// input/result left empty for the caller to fill in. Shared by the live streaming path
// (handleBlockStart — input fills in as it streams) and the static path (renderToolCard — input
// known immediately), so there is exactly one shape a tool card ever takes: it never needs to be
// swapped for a "more finished" version later, only updated in place.
function buildToolCardSkeleton(name) {
  const details = el("details", { class: "tool-card" });
  const summary = el("summary");
  const icon = el("span", { class: "tool-status-icon pending" });
  icon.appendChild(el("span", { class: "spinner", attrs: { style: "width:11px;height:11px;border-width:2px;" } }));
  summary.appendChild(icon);
  summary.appendChild(el("span", { class: "tool-name", text: name || "Tool" }));
  const preview = el("span", { class: "tool-preview", text: "streaming input…" });
  summary.appendChild(preview);
  details.appendChild(summary);

  const body = el("div", { class: "tool-card-body" });
  body.appendChild(el("div", { class: "tool-card-section-label", text: "Input" }));
  const inputPre = el("pre");
  body.appendChild(inputPre);

  const resultLabel = el("div", { class: "tool-card-section-label result-label hidden", text: "Result" });
  const resultPre = el("pre", { class: "tool-result-pre hidden" });
  body.appendChild(resultLabel);
  body.appendChild(resultPre);
  details.appendChild(body);

  return { cardEl: details, summaryEl: summary, iconEl: icon, previewEl: preview, inputPre, resultLabel, resultPre };
}

// Adds the "View output" chip once the tool's real input is known (block-start only has a name,
// not the parsed input a viewable-path check needs). Safe to call more than once per card.
function attachViewOutputChip(cardEl, summaryEl, name, input) {
  if (summaryEl.querySelector(".view-output-chip")) return;
  const viewableTarget = viewableFilePathFromToolInput(name, input);
  if (!viewableTarget) return;
  const chip = el("button", { class: "view-output-chip", text: "View output", attrs: { type: "button" } });
  chip.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    openViewer(viewableTarget);
  });
  summaryEl.appendChild(chip);
}

// Dev-only escape hatch so the streaming self-test (window.__streamBench, bottom of this file)
// can exercise the real handleBlockStart/handleDelta pipeline without also driving the pet-battler
// HUD (which reacts to the same events and would otherwise "attack"/spawn against a fake session).
let __streamBenchActive = false;

function handleBlockStart(payload) {
  const { sessionId, index, blockType, toolUseId, toolName } = payload;
  const s = ensureSessionState(sessionId);
  const streaming = ensureStreamingBubble(s, sessionId);
  if (sessionId === activeSessionId && !__streamBenchActive) HUD.onBlockStart(blockType, toolName);

  let node;
  let record;
  if (blockType === "tool_use") {
    const skeleton = buildToolCardSkeleton(toolName);
    node = skeleton.cardEl;
    if (toolUseId) node.dataset.toolId = toolUseId;
    record = { blockType, toolUseId, toolName, raw: "", ...skeleton };
    if (toolUseId) {
      s.toolCardsByToolUseId.set(toolUseId, node);
      const existingResult = s.toolResults.get(toolUseId);
      if (existingResult) applyToolResultToCard(node, existingResult.content, existingResult.isError);
    }
  } else if (blockType === "thinking") {
    const details = el("details", { class: "thinking-block" });
    details.appendChild(el("summary", { text: "Thinking" }));
    const body = el("div", { class: "thinking-body" });
    const textNode = document.createTextNode("");
    body.appendChild(textNode);
    details.appendChild(body);
    node = details;
    record = { blockType, node, textNode, raw: "", pendingText: "" };
  } else {
    node = el("div", { class: "msg-text-block is-streaming" });
    const textNode = document.createTextNode("");
    node.appendChild(textNode);
    record = { blockType, node, textNode, raw: "", pendingText: "", formatted: false };
  }
  streaming.blocks.set(index, record);

  const mutate = () => streaming.blocksEl.appendChild(node);
  if (sessionId === activeSessionId) withStickyScroll(mutate);
  else mutate();
}

const pendingDeltaBlocks = new Set();
let deltaFlushScheduled = false;
let lastDeltaFlushTs = 0;
const DELTA_FLUSH_INTERVAL_MS = 33; // ~30fps cap — accumulate all deltas between frames, write once

function scheduleDeltaFlush() {
  if (deltaFlushScheduled) return;
  deltaFlushScheduled = true;
  requestAnimationFrame(flushPendingDeltas);
}

function flushPendingDeltas(nowTs) {
  deltaFlushScheduled = false;
  if (pendingDeltaBlocks.size === 0) return;

  const now = typeof nowTs === "number" ? nowTs : performance.now();
  if (now - lastDeltaFlushTs < DELTA_FLUSH_INTERVAL_MS) {
    // Under the 30fps cap since the last flush — keep accumulating and try again next frame,
    // instead of writing to the DOM more often than the cap allows.
    scheduleDeltaFlush();
    return;
  }
  lastDeltaFlushTs = now;

  const stick = isNearBottom(); // read BEFORE any mutation, once for the whole batch
  for (const block of pendingDeltaBlocks) {
    if (block.blockType === "tool_use") {
      // Tool-input fragments are raw partial JSON — shown as a live preview + raw pre, never
      // parsed (the authoritative, complete + parsed input arrives on claude:message).
      block.previewEl.textContent = truncate(block.raw.replace(/\s+/g, " ").trim(), 90) || "streaming input…";
      block.inputPre.textContent = block.raw;
    } else if (block.pendingText) {
      // appendData grows the SAME persistent text node — no new node created per flush, no
      // innerHTML/textContent reset, cost stays O(new chars) not O(total accumulated so far).
      block.textNode.appendData(block.pendingText);
      block.pendingText = "";
    }
  }
  pendingDeltaBlocks.clear();
  // .timeline has no `scroll-behavior: smooth` (styles.css) so this is an instant jump, not an
  // animated one — explicit behavior:"auto" would be redundant but harmless if that ever changes.
  if (stick) dom.timeline.scrollTop = dom.timeline.scrollHeight;
}

function handleDelta(payload) {
  const { sessionId, index, kind, text } = payload;
  const s = ensureSessionState(sessionId);
  if (sessionId === activeSessionId && !__streamBenchActive) HUD.onDelta(kind);
  if (!s.streaming) return; // a block-start should always precede a delta; defensive no-op otherwise
  const block = s.streaming.blocks.get(index);
  if (!block) return;

  block.raw += text;

  if (sessionId !== activeSessionId) {
    // Detached from the DOM — safe (and simplest) to write through immediately, no batching needed.
    if (block.blockType === "tool_use") {
      block.previewEl.textContent = truncate(block.raw.replace(/\s+/g, " ").trim(), 90) || "streaming input…";
      block.inputPre.textContent = block.raw;
    } else {
      block.textNode.appendData(text);
    }
    return;
  }

  if (block.blockType !== "tool_use") block.pendingText = (block.pendingText || "") + text;
  pendingDeltaBlocks.add(block);
  scheduleDeltaFlush();
}

// Formats a text block's accumulated raw text into markdown HTML — the ONLY DOM write this makes
// is replacing that one block's own children, so siblings and the message wrapper are untouched.
// Idempotent (guarded by `formatted`) so it's safe to call from both handleBlockStop (the normal
// path) and finalizeStreamingMessage (a defensive fallback if block-stop was somehow missed).
function finalizeTextBlock(record) {
  if (record.formatted) return;
  record.formatted = true;
  record.node.classList.remove("is-streaming");
  record.node.innerHTML = renderMarkdownLite(record.raw || "");
}

function handleBlockStop(payload) {
  const { sessionId, index } = payload;
  const s = sessions.get(sessionId);
  if (!s || !s.streaming) return;
  const record = s.streaming.blocks.get(index);
  if (!record) return;

  if (record.blockType === "text") {
    // Commit any delta text buffered-but-not-yet-flushed so the last chunk isn't lost if
    // block-stop races the next rAF flush.
    if (record.pendingText) {
      record.textNode.appendData(record.pendingText);
      record.pendingText = "";
    }
    finalizeTextBlock(record);
  }
  // thinking / tool_use: nothing to do here. thinking is plain text in both streaming and final
  // form (no format step exists). tool_use's authoritative parsed input isn't known until
  // claude:message — finalizeStreamingMessage fills that in without touching anything else.
}

// ---------------------------------------------------------------------------
// finalized assistant message + tool cards
// ---------------------------------------------------------------------------

function handleMessage(payload) {
  const { sessionId, model, content } = payload;
  const s = ensureSessionState(sessionId);

  if (model) s.meta.model = model;

  // Track the last "text" block across the whole turn (a turn can finalize several messages —
  // e.g. text, then a tool_use, then more text) so handleTurnResult can check, at turn-end,
  // whether the assistant's actual last words were a question. Overwritten on every text block
  // seen, so by the time the turn ends this holds the true last one.
  for (const block of content || []) {
    if (block && block.type === "text" && typeof block.text === "string") {
      s.lastAssistantText = block.text;
    }
  }

  const node = s.streaming
    ? finalizeStreamingMessage(s, content || [])
    : renderFinalizedAssistantMessage(s, content || []); // fallback: a message with no preceding stream events (edge case)
  s.timeline.push({ type: "assistant", node });

  if (sessionId === activeSessionId) {
    clearEmptyState();
    // The streaming path's node is already the last child of dom.timeline (appended once, back
    // in handleBlockStart, and never removed since) — appending it again would just be a costly
    // no-op reflow. Only the fallback path's brand-new node needs inserting.
    if (!node.isConnected) appendToActiveTimeline(node);
  }
}

// Folds a finished message's authoritative content[] into the SAME DOM node that was already
// streaming it — diffed by index against s.streaming.blocks (safe: content_block_start/delta/stop
// indices from the raw Anthropic stream line up 1:1 with the finished message's content array,
// see bridge.rs parse_stream_event). Already-rendered blocks are left alone; only the couple of
// fields that aren't knowable until the block completes (a tool_use's full parsed input) are
// filled in. No node is removed or rebuilt — this is what kills the old "swap the whole message"
// reflow/jump.
function finalizeStreamingMessage(s, content) {
  const streaming = s.streaming;
  const wrap = streaming.el;
  wrap.classList.remove("streaming");
  wrap.classList.add("assistant");

  content.forEach((block, index) => {
    if (!block || typeof block !== "object") return;
    const record = streaming.blocks.get(index);

    if (block.type === "text") {
      if (record) finalizeTextBlock(record); // no-op if block-stop already formatted it
      else {
        const p = el("div");
        p.innerHTML = renderMarkdownLite(block.text || "");
        streaming.blocksEl.appendChild(p);
      }
    } else if (block.type === "thinking") {
      if (!record) {
        const details = el("details", { class: "thinking-block" });
        details.appendChild(el("summary", { text: "Thinking" }));
        details.appendChild(el("div", { class: "thinking-body", text: block.thinking || "" }));
        streaming.blocksEl.appendChild(details);
      }
      // else: already rendered live, in its final shape — nothing to update.
    } else if (block.type === "tool_use") {
      if (record) {
        // Only the authoritative parsed input was unknowable while streaming — fill it in on the
        // SAME card, in place. This is the tool-card half of the FINAL-format pass (see
        // linkifyFileMentions above) — safe to run here (once, on the authoritative input) even
        // though the live delta flush above deliberately leaves the same fields as plain text.
        record.inputPre.innerHTML = escapeAndLinkifyFileMentions(JSON.stringify(block.input ?? {}, null, 2));
        record.previewEl.innerHTML = escapeAndLinkifyFileMentions(summarizeToolInput(block.input));
        attachViewOutputChip(record.cardEl, record.summaryEl, block.name, block.input);
      } else {
        streaming.blocksEl.appendChild(renderToolCard(s, block.id, block.name, block.input));
      }
    }
  });

  s.streaming = null;
  return wrap;
}

function renderFinalizedAssistantMessage(s, content) {
  const wrap = el("div", { class: "msg assistant" });
  const bubble = el("div", { class: "bubble" });
  const blocksWrap = el("div", { class: "msg-blocks" });
  bubble.appendChild(blocksWrap);
  wrap.appendChild(bubble);

  for (const block of content) {
    if (!block || typeof block !== "object") continue;
    if (block.type === "text") {
      const p = el("div");
      p.innerHTML = renderMarkdownLite(block.text || "");
      blocksWrap.appendChild(p);
    } else if (block.type === "thinking") {
      const details = el("details", { class: "thinking-block" });
      details.appendChild(el("summary", { text: "Thinking" }));
      details.appendChild(el("div", { class: "thinking-body", text: block.thinking || "" }));
      blocksWrap.appendChild(details);
    } else if (block.type === "tool_use") {
      blocksWrap.appendChild(renderToolCard(s, block.id, block.name, block.input));
    }
  }
  return wrap;
}

function renderToolCard(s, toolUseId, name, input) {
  const existingResult = toolUseId ? s.toolResults.get(toolUseId) : null;
  // buildToolCardSkeleton already renders the pending-state icon; applyToolResultToCard (below)
  // overrides it once a result is known, so there's nothing else to do with the icon here.
  const { cardEl, summaryEl, previewEl, inputPre } = buildToolCardSkeleton(name);
  if (toolUseId) cardEl.dataset.toolId = toolUseId;

  previewEl.innerHTML = escapeAndLinkifyFileMentions(summarizeToolInput(input));
  inputPre.innerHTML = escapeAndLinkifyFileMentions(JSON.stringify(input ?? {}, null, 2));
  attachViewOutputChip(cardEl, summaryEl, name, input);

  if (toolUseId) s.toolCardsByToolUseId.set(toolUseId, cardEl);
  if (existingResult) {
    applyToolResultToCard(cardEl, existingResult.content, existingResult.isError);
  }

  return cardEl;
}

function applyToolResultToCard(cardEl, content, isError) {
  const icon = cardEl.querySelector(".tool-status-icon");
  icon.innerHTML = "";
  icon.classList.remove("pending", "ok", "error");
  icon.classList.add(isError ? "error" : "ok");
  icon.textContent = isError ? "✕" : "✓";

  cardEl.querySelector(".result-label").classList.remove("hidden");
  const pre = cardEl.querySelector(".tool-result-pre");
  pre.classList.remove("hidden");
  // Tool results arrive as one complete claude:tool-result event (never streamed in pieces), so
  // this is always a final-pass write — safe to linkify unconditionally.
  pre.innerHTML = escapeAndLinkifyFileMentions(formatToolResultContent(content));
  cardEl.querySelector(".tool-card-body").classList.toggle("error", !!isError);
}

function handleToolResult(payload) {
  const { sessionId, toolUseId, content, isError } = payload;
  const s = ensureSessionState(sessionId);
  if (isError && sessionId === activeSessionId && !__streamBenchActive) HUD.onToolError();
  s.toolResults.set(toolUseId, { content, isError: !!isError });

  // O(1) lookup via the map populated in handleBlockStart/renderToolCard — no querySelector,
  // and (unlike the old activeSessionId-gated querySelector) this now also keeps a BACKGROUND
  // session's already-built tool card in sync, so switching to it later doesn't show a stale
  // "pending" card for a tool that actually finished a while ago.
  const cardEl = s.toolCardsByToolUseId.get(toolUseId);
  if (!cardEl) return;
  if (sessionId === activeSessionId) {
    withStickyScroll(() => applyToolResultToCard(cardEl, content, !!isError));
  } else {
    applyToolResultToCard(cardEl, content, !!isError); // detached DOM — no layout cost either way
  }
}

// ---------------------------------------------------------------------------
// dev-only streaming self-test
//
// Console: window.__streamBench(2000) — synthesizes N text deltas through the REAL
// handleBlockStart/handleDelta/handleBlockStop pipeline (rAF batching, the 30fps flush cap,
// appendData) against a detached DOM subtree, so it never touches whatever session/timeline is
// actually open. Expected: comfortably under 200ms total for 2000 deltas on this machine class —
// the flush cost is O(total characters flushed), not O(delta count), so this should hold
// regardless of how choppy the incoming deltas are.
// ---------------------------------------------------------------------------
window.__streamBench = function __streamBench(nDeltas) {
  nDeltas = Math.max(1, (nDeltas | 0) || 2000);
  const realTimeline = dom.timeline;
  const realActiveId = activeSessionId;
  const fakeSessionId = "__bench__" + Date.now();
  const fakeTimeline = document.createElement("div"); // detached — never appended to document.body

  __streamBenchActive = true;
  dom.timeline = fakeTimeline;
  activeSessionId = fakeSessionId;

  const label = `streamBench(${nDeltas})`;
  console.time(label);
  const t0 = performance.now();
  const chunk = "the quick brown fox jumps over the lazy dog. ";

  handleBlockStart({ sessionId: fakeSessionId, index: 0, blockType: "text", toolUseId: null, toolName: null });
  for (let i = 0; i < nDeltas; i++) {
    handleDelta({ sessionId: fakeSessionId, index: 0, kind: "text", text: chunk });
  }
  handleBlockStop({ sessionId: fakeSessionId, index: 0 });

  function finish() {
    const totalMs = performance.now() - t0;
    console.timeEnd(label);
    console.log(
      `[streamBench] ${nDeltas} deltas / ${(nDeltas * chunk.length).toLocaleString()} chars -> ` +
        `${totalMs.toFixed(1)}ms total (expect <200ms on this machine class). ` +
        `Rendered ${fakeTimeline.textContent.length.toLocaleString()} chars.`
    );
    dom.timeline = realTimeline;
    activeSessionId = realActiveId;
    __streamBenchActive = false;
    sessions.delete(fakeSessionId);
  }

  // All deltas above were enqueued synchronously; the batched flush(es) they scheduled still need
  // their rAF callback(s) to actually run (the 30fps cap can defer a flush to a later frame), so
  // poll for the queue to drain rather than assuming one frame is enough.
  function waitForDrain() {
    if (pendingDeltaBlocks.size === 0 && !deltaFlushScheduled) {
      finish();
      return;
    }
    requestAnimationFrame(waitForDrain);
  }
  requestAnimationFrame(waitForDrain);
};

// ---------------------------------------------------------------------------
// status / init / result / exit / stderr
// ---------------------------------------------------------------------------

function handleStatus(payload) {
  const { sessionId, state, detail } = payload;
  const s = ensureSessionState(sessionId);
  s.status = state;
  s.statusDetail = detail || null;

  if (sessionId === activeSessionId) {
    if (s.timeline.length === 0 && !s.streaming) {
      fullRenderTimeline(sessionId); // keep the starting-state hook detail line current
    }
    updateComposerEnabled();
    updateStatusBar();
  }
  renderSessionList();
}

function handleInit(payload) {
  const { sessionId, model, permissionMode, claudeCodeVersion, cwd, slashCommands, agents } = payload;
  const s = ensureSessionState(sessionId);
  s.initInfo = { model, permissionMode, claudeCodeVersion, cwd, slashCommands, agents };
  if (!s.meta.model) s.meta.model = model;
  s.meta.live = true;

  if (sessionId === activeSessionId) {
    dom.chatMeta.textContent = `${model} · ${cwd}`;
    updateStatusBar();
  }
}

function handleTurnResult(payload) {
  const { sessionId, isError, result, durationMs } = payload;
  const s = ensureSessionState(sessionId);
  s.lastDurationMs = durationMs;
  s.turnStartedAt = null;

  if (isError && result) {
    appendSystemError(sessionId, `Turn ended with an error: ${result}`);
  }

  if (sessionId === activeSessionId) updateStatusBar();

  // Soft affordance: the assistant's actual last word this turn was a question — nudge the user
  // instead of leaving them to notice it themselves. Never shown while a hard modal (permission
  // or question control_request) is already up; that's already the unmissable, blocking case.
  if (sessionId === activeSessionId && !s.pendingPermission && !s.pendingQuestion) {
    const endsWithQuestion = /[?？]\s*$/.test((s.lastAssistantText || "").trim());
    dom.questionHintChip.classList.toggle("hidden", !endsWithQuestion);
    if (endsWithQuestion) dom.composerInput.focus();
  }

  // HUD victory reward needs the real turn cost/tokens delta, which only exists once
  // refreshSessionMeta() has pulled the backend's freshly-summed SessionMeta — snapshot the
  // pre-refresh totals now, diff against the post-refresh totals in .then().
  const prevCost = s.meta.cumCostUsd || 0;
  const prevUsage = s.meta.cumUsage || {};
  const prevTokens = (prevUsage.inputTokens || 0) + (prevUsage.outputTokens || 0);

  // cumUsage/cumCostUsd/numTurns/model/live live on SessionMeta, which the backend already sums
  // turn-over-turn into sessions.json — refetch rather than re-derive that arithmetic here.
  refreshSessionMeta().then(() => {
    if (sessionId !== activeSessionId) return;
    const ns = sessions.get(sessionId);
    const newCost = (ns && ns.meta.cumCostUsd) || 0;
    const nu = (ns && ns.meta.cumUsage) || {};
    const newTokens = (nu.inputTokens || 0) + (nu.outputTokens || 0);
    HUD.onTurnResult({
      isError,
      costUsd: Math.max(0, newCost - prevCost),
      tokens: Math.max(0, newTokens - prevTokens),
    });
  });
}

function handleExit(payload) {
  const { sessionId, code } = payload;
  const s = ensureSessionState(sessionId);
  s.meta.live = false;
  s.status = "exited";
  s.pendingPermission = null; // any open request is moot once the process has exited
  s.pendingQuestion = null;
  s.streaming = null;
  s.turnStartedAt = null;

  if (sessionId === activeSessionId) {
    closePermissionModal();
    closeQuestionModal();
    updatePermissionBanner();
    updateComposerEnabled();
    updateStatusBar();
    HUD.onSessionExited();
  }
  renderSessionList();

  if (code !== 0 && code != null) {
    showToast(`Session process exited with code ${code}.`, "error");
  }
}

// A stale `--resume` target was cleared server-side and the session respawned fresh, once,
// automatically (see EVT_RESUME_FALLBACK in app.rs). Drop a small neutral notice in the timeline
// so the user knows why prior context is gone, instead of the session just quietly working again.
function handleResumeFallback(payload) {
  const { sessionId } = payload;
  appendSystemNotice(
    sessionId,
    "Previous conversation could not be resumed — started fresh."
  );
}

// The CLI process died within ~3s of spawn with a nonzero exit code — a real spawn failure
// (bad provider config, missing binary, immediate crash, ...), not the auto-handled ghost-resume
// case above. Render the collected stderr tail as a readable error card instead of leaving the
// user to dig through the Diagnostics counter to find out why nothing happened.
function handleSpawnFailure(payload) {
  const { sessionId, code, stderrTail } = payload;
  const detail = (stderrTail || "").trim();
  const text = detail
    ? `Session failed to start (exit code ${code}):\n\n${detail}`
    : `Session failed to start (exit code ${code}).`;
  appendSystemError(sessionId, text);
}

function handleStderrEvent(payload) {
  const { sessionId, line } = payload;
  const s = ensureSessionState(sessionId);
  s.diagnostics.push(line);
  if (sessionId === activeSessionId) renderDiagnostics(s);
}

function renderDiagnostics(s) {
  const has = s.diagnostics.length > 0;
  dom.diagnostics.classList.toggle("hidden", !has);
  dom.diagnosticsCount.textContent = String(s.diagnostics.length);
  dom.diagnosticsBody.textContent = s.diagnostics.join("\n");
}

// ---------------------------------------------------------------------------
// permission modal (blocking — never auto-approved, never auto-dismissed)
// ---------------------------------------------------------------------------

let permInputEditing = false;

// How long a permission request can sit unanswered before the inline card grows a "still
// waiting" note (timeout SAFETY, not a timeout ACTION — nothing auto-answers, ever).
const PERMISSION_TIMEOUT_NOTE_MS = 90 * 1000;

function handlePermissionRequest(payload) {
  const { sessionId, requestId, toolName, input, description, suggestions, blockedPath } = payload;
  const s = ensureSessionState(sessionId);

  // Session-scoped "don't ask again for this tool" — set by the inline card's second button.
  // Resolve silently: no card, no modal, no banner, same wire path as a manual Allow.
  if (s.autoAllowTools && s.autoAllowTools.has(toolName)) {
    resolvePermissionRequest(sessionId, requestId, true, input, null);
    return;
  }

  s.pendingPermission = {
    requestId,
    toolName,
    input,
    description,
    suggestions: suggestions || [],
    blockedPath,
    createdAtMs: Date.now(),
    resolved: false, // guards double-respond: card and modal both write this, both check it first
    cardNode: null,
    cardTimeoutNoteNode: null,
  };

  // 1) PRIMARY surface: inline card in the timeline. Appended unconditionally, even for a
  // background session, so it's there waiting the moment the user switches to it — and so it
  // still exists even if the modal below throws.
  appendPermissionCard(sessionId, s.pendingPermission);
  renderSessionList(); // paints the "needs you" rail badge, including for background sessions

  if (sessionId === activeSessionId) {
    updateComposerEnabled();
    updatePermissionUI(); // secondary surface: modal + banner
    HUD.onPermissionRequest();
  }
}

// Single resolver for BOTH the inline card and the modal — the one place that talks to the
// backend, so the "answer the same request id exactly once" guard lives in exactly one spot.
async function resolvePermissionRequest(sessionId, requestId, allow, updatedInput, denyMessage) {
  const s = sessions.get(sessionId);
  if (!s || !s.pendingPermission || s.pendingPermission.requestId !== requestId) return;
  if (s.pendingPermission.resolved) return; // already answered (or in flight) — ignore
  const p = s.pendingPermission;
  p.resolved = true; // set BEFORE invoking, so a near-simultaneous second click is a no-op

  try {
    await invoke("respond_permission", {
      sessionId,
      requestId,
      allow,
      updatedInput: allow ? updatedInput : null,
      denyMessage,
    });
  } catch (err) {
    p.resolved = false; // let the user retry from either surface
    showToast(`Failed to send ${allow ? "approval" : "denial"}: ${err}`);
    return;
  }

  finalizePermissionCard(p, allow, denyMessage);
  if (s.pendingPermission === p) s.pendingPermission = null;
  renderSessionList();

  if (sessionId === activeSessionId) {
    closePermissionModal();
    updateComposerEnabled();
    updatePermissionUI();
    HUD.onPermissionResolved();
  }
}

// Builds the inline permission card and appends it to the timeline (same append contract as
// appendUserMessage / appendSystemCard: push into s.timeline so history replay keeps it, append
// live only if this is the active session). This card is the PRIMARY approval surface — it works
// even if openPermissionModal never opens.
function appendPermissionCard(sessionId, p) {
  const s = ensureSessionState(sessionId);
  const card = el("div", { class: "perm-card" });

  const head = el("div", { class: "perm-card-head" });
  head.appendChild(el("span", { class: "perm-card-icon", text: "⚠" }));
  head.appendChild(el("span", { class: "perm-card-title", text: `Permission needed — ${p.toolName}` }));
  card.appendChild(head);

  if (p.description) {
    card.appendChild(el("div", { class: "perm-card-desc", text: p.description }));
  }
  if (p.blockedPath) {
    const bp = el("div", { class: "perm-card-blocked" });
    bp.appendChild(el("span", { text: "Blocked path: " }));
    bp.appendChild(el("code", { text: p.blockedPath }));
    card.appendChild(bp);
  }

  const inputDetails = el("details", { class: "perm-card-input" });
  inputDetails.appendChild(el("summary", { text: "Input" }));
  inputDetails.appendChild(el("pre", { text: JSON.stringify(p.input, null, 2) }));
  card.appendChild(inputDetails);

  const timeoutNote = el("div", {
    class: "perm-card-timeout-note hidden",
    text: "Still waiting — the session will stay paused until you answer.",
  });
  card.appendChild(timeoutNote);
  p.cardTimeoutNoteNode = timeoutNote;

  const denyRow = el("div", { class: "perm-card-deny-row hidden" });
  const denyReasonInput = el("textarea", {
    class: "perm-card-deny-reason",
    attrs: { rows: "2", placeholder: "Why you're denying this (optional)…" },
  });
  denyRow.appendChild(denyReasonInput);
  card.appendChild(denyRow);

  const actions = el("div", { class: "perm-card-actions" });
  const allowBtn = el("button", { class: "btn btn-success btn-small", text: "Allow", attrs: { type: "button" } });
  const allowAlwaysBtn = el("button", {
    class: "btn btn-ghost btn-small",
    text: `Allow, don't ask again for ${p.toolName}`,
    attrs: { type: "button" },
  });
  const denyBtn = el("button", { class: "btn btn-danger btn-small", text: "Deny", attrs: { type: "button" } });
  const denyConfirmBtn = el("button", {
    class: "btn btn-danger btn-small hidden",
    text: "Confirm deny",
    attrs: { type: "button" },
  });

  allowBtn.addEventListener("click", () => {
    resolvePermissionRequest(sessionId, p.requestId, true, p.input, null);
  });
  allowAlwaysBtn.addEventListener("click", () => {
    const st = sessions.get(sessionId);
    if (st) {
      if (!st.autoAllowTools) st.autoAllowTools = new Set();
      st.autoAllowTools.add(p.toolName);
    }
    resolvePermissionRequest(sessionId, p.requestId, true, p.input, null);
  });
  denyBtn.addEventListener("click", () => {
    denyRow.classList.remove("hidden");
    denyBtn.classList.add("hidden");
    denyConfirmBtn.classList.remove("hidden");
    denyReasonInput.focus();
  });
  denyConfirmBtn.addEventListener("click", () => {
    resolvePermissionRequest(sessionId, p.requestId, false, null, denyReasonInput.value.trim() || null);
  });

  actions.appendChild(allowBtn);
  actions.appendChild(allowAlwaysBtn);
  actions.appendChild(denyBtn);
  actions.appendChild(denyConfirmBtn);
  card.appendChild(actions);

  p.cardNode = card;
  s.timeline.push({ type: "permission", node: card });
  if (sessionId === activeSessionId) {
    clearEmptyState();
    appendToActiveTimeline(card);
  }
}

// Replaces a resolved card's contents with a compact resolved state IN PLACE (same node — no
// remove/re-append, so scroll position and timeline order are untouched).
function finalizePermissionCard(p, allow, denyMessage) {
  if (!p.cardNode) return;
  p.cardNode.className = "perm-card perm-card-resolved" + (allow ? " allowed" : " denied");
  p.cardNode.innerHTML = "";
  p.cardNode.appendChild(el("span", { class: "perm-card-resolved-icon", text: allow ? "✓" : "✕" }));
  p.cardNode.appendChild(el("span", { class: "perm-card-resolved-text", text: `${allow ? "Allowed" : "Denied"} — ${p.toolName}` }));
  if (!allow && denyMessage) {
    p.cardNode.appendChild(el("span", { class: "perm-card-resolved-reason", text: denyMessage }));
  }
}

// Every 5s, flip on the "still waiting" note for any pending permission that's been sitting
// unanswered for PERMISSION_TIMEOUT_NOTE_MS — across ALL sessions, not just the active one, since
// the card exists (and the clock is running) whether or not the user is looking at it.
setInterval(() => {
  const now = Date.now();
  for (const s of sessions.values()) {
    const p = s.pendingPermission;
    if (p && !p.resolved && p.cardTimeoutNoteNode && now - p.createdAtMs > PERMISSION_TIMEOUT_NOTE_MS) {
      p.cardTimeoutNoteNode.classList.remove("hidden");
    }
  }
}, 5000);

// Secondary surfaces for the active session only: the blocking modal, and the persistent banner
// above the composer. Both point at the SAME s.pendingPermission the inline card already holds.
function updatePermissionUI() {
  const s = activeSessionId ? sessions.get(activeSessionId) : null;
  if (s && s.pendingPermission) {
    // DEFENSIVE: a modal render failure must never take the inline card (already appended in
    // handlePermissionRequest) down with it — that card is the surface of record.
    try {
      openPermissionModal(s);
    } catch (err) {
      console.error("openPermissionModal failed; the inline timeline card remains the fallback approval surface", err);
    }
  } else {
    closePermissionModal();
  }
  updatePermissionBanner();
}

function updatePermissionBanner() {
  const s = activeSessionId ? sessions.get(activeSessionId) : null;
  if (s && s.pendingPermission) {
    dom.permissionBannerText.textContent = `Claude is waiting for your permission to run ${s.pendingPermission.toolName}`;
    dom.permissionBanner.classList.remove("hidden");
  } else {
    dom.permissionBanner.classList.add("hidden");
  }
}

function updateQuestionUI() {
  const s = activeSessionId ? sessions.get(activeSessionId) : null;
  if (s && s.pendingQuestion) {
    openQuestionModal(s);
  } else {
    closeQuestionModal();
  }
}

function openPermissionModal(s) {
  const p = s.pendingPermission;
  if (!p) return;
  dom.modal.classList.remove("hidden");
  dom.permToolName.textContent = p.toolName;

  if (p.description) {
    dom.permDescription.textContent = p.description;
    dom.permDescriptionRow.classList.remove("hidden");
  } else {
    dom.permDescriptionRow.classList.add("hidden");
  }

  if (p.blockedPath) {
    dom.permBlockedPath.textContent = p.blockedPath;
    dom.permBlockedRow.classList.remove("hidden");
  } else {
    dom.permBlockedRow.classList.add("hidden");
  }

  const pretty = JSON.stringify(p.input, null, 2);
  dom.permInputView.textContent = pretty;
  dom.permInputEdit.value = pretty;
  permInputEditing = false;
  dom.permInputView.classList.remove("hidden");
  dom.permInputEdit.classList.add("hidden");
  dom.permInputError.classList.add("hidden");
  dom.permEditToggle.textContent = "Edit";

  if (p.suggestions && p.suggestions.length > 0) {
    dom.permSuggestionsBody.textContent = JSON.stringify(p.suggestions, null, 2);
    dom.permSuggestions.classList.remove("hidden");
    dom.permSuggestions.open = false;
  } else {
    dom.permSuggestions.classList.add("hidden");
  }

  dom.permDenyRow.classList.add("hidden");
  dom.permDenyReason.value = "";
  dom.permDenyBtn.classList.remove("hidden");
  dom.permDenyConfirmBtn.classList.add("hidden");
}

function closePermissionModal() {
  dom.modal.classList.add("hidden");
}

async function respondToPermission(allow) {
  const s = activeSessionId ? sessions.get(activeSessionId) : null;
  if (!s || !s.pendingPermission) return;
  const requestId = s.pendingPermission.requestId;

  let updatedInput = s.pendingPermission.input;
  let denyMessage = null;

  if (allow && permInputEditing) {
    try {
      updatedInput = JSON.parse(dom.permInputEdit.value);
    } catch (err) {
      dom.permInputError.textContent = "Input is not valid JSON: " + err.message;
      dom.permInputError.classList.remove("hidden");
      return;
    }
  }
  if (!allow) {
    denyMessage = dom.permDenyReason.value.trim() || null;
  }

  // Delegates to the single resolver shared with the inline card — that's what enforces the
  // "answer this request id exactly once" guard, whichever surface the user answers from.
  await resolvePermissionRequest(activeSessionId, requestId, allow, updatedInput, denyMessage);
}

// ---------------------------------------------------------------------------
// question modal (control_request with a question payload — distinct from can_use_tool's
// permission modal; see bridge::BridgeEvent::QuestionRequest)
// ---------------------------------------------------------------------------

function handleQuestionRequest(payload) {
  const { sessionId, requestId, subtype, title, body, options, allowFreeText } = payload;
  const s = ensureSessionState(sessionId);
  s.pendingQuestion = { requestId, subtype, title, body, options: options || [], allowFreeText: !!allowFreeText };

  renderSessionList();
  if (sessionId === activeSessionId) {
    dom.questionHintChip.classList.add("hidden"); // superseded by the hard modal below
    updateComposerEnabled();
    openQuestionModal(s);
  }
}

function openQuestionModal(s) {
  const q = s.pendingQuestion;
  if (!q) return;
  dom.questionModal.classList.remove("hidden");
  dom.questionModalTitle.textContent = q.title || "Claude has a question";

  if (q.body) {
    dom.questionModalBody.innerHTML = renderMarkdownLite(q.body);
  } else {
    dom.questionModalBody.innerHTML = "";
  }

  dom.questionModalOptions.innerHTML = "";
  for (const opt of q.options) {
    const btn = el("button", { class: "question-option-btn", text: opt.label, attrs: { type: "button" } });
    btn.addEventListener("click", () => respondToQuestion({ optionValue: opt.value }));
    dom.questionModalOptions.appendChild(btn);
  }

  const showFreeText = q.allowFreeText;
  dom.questionModalFreeTextRow.classList.toggle("hidden", !showFreeText);
  dom.questionModalSubmitBtn.classList.toggle("hidden", !showFreeText);
  dom.questionModalFreeText.value = "";
  if (showFreeText && q.options.length === 0) dom.questionModalFreeText.focus();
}

function closeQuestionModal() {
  dom.questionModal.classList.add("hidden");
}

async function respondToQuestion({ optionValue, freeText } = {}) {
  const s = activeSessionId ? sessions.get(activeSessionId) : null;
  if (!s || !s.pendingQuestion) return;
  const requestId = s.pendingQuestion.requestId;

  try {
    await invoke("respond_question", {
      sessionId: activeSessionId,
      requestId,
      optionValue: optionValue || null,
      freeText: optionValue ? null : freeText || "",
    });
    s.pendingQuestion = null;
    closeQuestionModal();
    updateComposerEnabled();
    renderSessionList();
  } catch (err) {
    showToast("Failed to send answer: " + err);
  }
}

function submitQuestionFreeText() {
  const text = dom.questionModalFreeText.value.trim();
  if (!text) return;
  respondToQuestion({ freeText: text });
}

// ---------------------------------------------------------------------------
// composer / status bar
// ---------------------------------------------------------------------------

function autoGrowComposer() {
  dom.composerInput.style.height = "auto";
  dom.composerInput.style.height = Math.min(dom.composerInput.scrollHeight, 200) + "px";
}

// Composer is disabled while a turn is in flight ("requesting") in addition to cold start and an
// open permission prompt. The contract only mandates disabling for starting/modal-blocked; disabling
// mid-turn too is the conventional chat-UX choice, since the underlying stdin protocol for
// interleaving a second user message during an active turn is not part of the verified contract.
// True when the active session's provider can accept image attachments AND attachments haven't
// been turned off globally. Unknown/no session degrades to false, same as the backend's
// `supports_images_for` (never guess "yes").
function attachmentsAllowedForActiveSession() {
  const s = activeSessionId ? sessions.get(activeSessionId) : null;
  const providerOk = !!(s && s.meta && s.meta.supportsImages);
  const globalOk = !multimodalCache || multimodalCache.attachmentsEnabled !== false;
  return providerOk && globalOk;
}

const NO_IMAGE_SUPPORT_TOOLTIP = "Provider ini belum support gambar — pakai Claude/Kimi";

// ---------------------------------------------------------------------------
// provider-connect guard — block sending on a provider (session's own, or the default a brand
// new session would be created with) that has no API key saved, instead of silently spawning a
// CLI process that can never actually talk to anything (the dead-chat bug: a session created
// against Kimi with no key ever set, spawn "succeeds", every message vanishes).
// ---------------------------------------------------------------------------

function activeOrDefaultProviderId() {
  const s = activeSessionId ? sessions.get(activeSessionId) : null;
  return (s && s.meta && s.meta.providerId) || getDefaultProviderId();
}

function findProviderById(id) {
  return (providersCache || []).find((p) => p.id === id) || null;
}

// True only for a configured non-Claude provider with no key saved — `claude` (subscription
// login) is never gated here, and an unknown/not-yet-loaded provider degrades to "not blocked"
// rather than guessing.
function providerNeedsConnection(p) {
  if (!p) return false;
  // 9Router is "connected" when the local proxy is up, not when a key exists — it usually has no
  // key at all. Gating it on `hasKey` like the others would leave the composer permanently
  // disabled for exactly the users this provider is meant to serve.
  if (p.kind === KIND_9ROUTER) return !(nineRouterStatusCache && nineRouterStatusCache.running);
  return p.kind !== KIND_CLAUDE && !p.hasKey;
}

// Shows/hides the composer banner for the current provider and returns whether sending should be
// blocked, so `updateComposerEnabled` can fold this straight into its disabled calculation.
function updateProviderConnectBanner() {
  if (!dom.providerConnectBanner) return false;
  const p = findProviderById(activeOrDefaultProviderId());
  // The 9Router verdict depends on live process state, so make sure we have some before judging.
  // One fetch, then repaint — without this the banner would claim "not running" until the user
  // happened to open Settings.
  if (p && p.kind === KIND_9ROUTER && nineRouterStatusCache === null) {
    refreshNineRouterStatus().then(() => updateComposerEnabled());
  }
  const blocked = providerNeedsConnection(p);
  dom.providerConnectBanner.classList.toggle("hidden", !blocked);
  if (blocked) {
    dom.providerConnectBannerText.textContent =
      p.kind === KIND_9ROUTER
        ? `${p.label || p.id} isn't running yet — open Settings and click Start`
        : `${p.label || p.id} is not connected yet — add your API key first`;
    dom.providerConnectBanner.dataset.providerId = p.id;
  }
  return blocked;
}

function updateComposerEnabled() {
  const s = activeSessionId ? sessions.get(activeSessionId) : null;
  const busy = !!s && BUSY_STATUSES.has(s.status);
  // A pending QuestionRequest blocks the composer the same way a pending permission request
  // does: the CLI's turn is parked waiting on a control_response, and the modal (not a plain
  // composer send) is the answer path back to it.
  const blocked = !!s && (!!s.pendingPermission || !!s.pendingQuestion);
  const disabled = !activeSessionId || busy || blocked;
  const providerBlocked = updateProviderConnectBanner();
  const sendDisabled = disabled || providerBlocked;
  dom.composerInput.disabled = sendDisabled;
  dom.sendBtn.disabled = sendDisabled;

  const imagesAllowed = attachmentsAllowedForActiveSession();
  dom.attachBtn.disabled = sendDisabled || !imagesAllowed;
  dom.attachBtn.title = imagesAllowed ? "Attach image" : NO_IMAGE_SUPPORT_TOOLTIP;
  dom.stopBtn.classList.toggle("hidden", !(s && s.status === "requesting"));

  // Session-settings selects (model/effort/mode/provider) piggyback the ORIGINAL disable
  // condition, not `sendDisabled` — a blocked-on-provider composer must still let the user open
  // the provider <select> and switch to a connected one to unblock themselves.
  dom.modelSelect.disabled = disabled;
  dom.modelCustomInput.disabled = disabled;
  dom.effortSelect.disabled = disabled;
  dom.modeSelect.disabled = disabled;
  dom.providerSelect.disabled = disabled;
}

// Sets text + visibility on a status-bar chip and mirrors the same state onto its
// popover twin (may be null-safe — both always exist here, but keep the guard cheap).
function setChip(primaryEl, mirrorEl, text) {
  if (!text) {
    primaryEl.classList.add("hidden");
    if (mirrorEl) mirrorEl.classList.add("hidden");
    return;
  }
  primaryEl.textContent = text;
  primaryEl.classList.remove("hidden");
  if (mirrorEl) {
    mirrorEl.textContent = text;
    mirrorEl.classList.remove("hidden");
  }
}

function updateStatusBar() {
  const s = activeSessionId ? sessions.get(activeSessionId) : null;
  if (!s) {
    dom.statusDot.className = "status-dot";
    dom.statusText.textContent = "No active session";
    setChip(dom.statusModel, dom.popStatusModel, null);
    setChip(dom.statusElapsed, dom.popStatusElapsed, null);
    setChip(dom.statusTokens, dom.popStatusTokens, null);
    setChip(dom.statusCost, dom.popStatusCost, null);
    dom.fullAutoChip.classList.add("hidden");
    dom.popStatusEmpty.classList.remove("hidden");
    return;
  }
  dom.popStatusEmpty.classList.add("hidden");

  dom.fullAutoChip.classList.toggle(
    "hidden",
    !(s.meta && s.meta.permissionMode === "bypassPermissions")
  );

  const dotClass =
    { starting: "starting", hook_started: "starting", hook_response: "starting", requesting: "busy", ready: "ready", exited: "exited" }[
      s.status
    ] || "";
  dom.statusDot.className = "status-dot" + (dotClass ? " " + dotClass : "");

  const textMap = {
    starting: "Starting Claude Code…",
    hook_started: `Running hook${s.statusDetail ? ": " + s.statusDetail : ""}…`,
    hook_response: `Hook finished${s.statusDetail ? ": " + s.statusDetail : ""}`,
    requesting: "Working…",
    ready: s.meta.live ? "Ready" : "Ready (will resume on next message)",
    exited: "Stopped — will auto-resume on next message",
    idle: "Idle",
  };
  dom.statusText.textContent = textMap[s.status] || s.status;

  const model = s.meta.model || (s.initInfo && s.initInfo.model);
  setChip(dom.statusModel, dom.popStatusModel, model || null);

  // Live-ticking elapsed time while a turn is in flight (frontend timer, send -> result), frozen
  // to the CLI-reported durationMs once the turn actually completes.
  if (s.status === "requesting" && s.turnStartedAt) {
    const secs = (performance.now() - s.turnStartedAt) / 1000;
    setChip(dom.statusElapsed, dom.popStatusElapsed, `${secs.toFixed(1)}s elapsed`);
  } else if (s.lastDurationMs != null) {
    setChip(dom.statusElapsed, dom.popStatusElapsed, formatDuration(s.lastDurationMs));
  } else {
    setChip(dom.statusElapsed, dom.popStatusElapsed, null);
  }

  const u = s.meta.cumUsage;
  if (u && (u.inputTokens || u.outputTokens || u.cacheReadInputTokens || u.cacheCreationInputTokens)) {
    setChip(
      dom.statusTokens,
      dom.popStatusTokens,
      `${formatCompactNumber(u.inputTokens)} in / ${formatCompactNumber(u.outputTokens)} out / ${formatCompactNumber(
        u.cacheReadInputTokens
      )} cache-read`
    );
  } else {
    setChip(dom.statusTokens, dom.popStatusTokens, null);
  }

  setChip(
    dom.statusCost,
    dom.popStatusCost,
    s.meta.cumCostUsd ? `${formatCost(s.meta.cumCostUsd)} subscription-equivalent — not a bill` : null
  );
}

function ensureElapsedTicker() {
  if (elapsedTickerStarted) return;
  elapsedTickerStarted = true;
  setInterval(() => {
    if (activeSessionId) {
      const s = sessions.get(activeSessionId);
      if (s && s.status === "requesting") updateStatusBar();
    }
  }, 200);
}

// ---------------------------------------------------------------------------
// attachments — paste / drag-drop / file-picker staging, thumbnail strip, lightbox
// ---------------------------------------------------------------------------

function formatBytes(n) {
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)}KB`;
  return `${(n / (1024 * 1024)).toFixed(1)}MB`;
}

function dataUrlToBase64(dataUrl) {
  const comma = dataUrl.indexOf(",");
  return comma === -1 ? dataUrl : dataUrl.slice(comma + 1);
}

function blobToDataURL(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error("failed to read file"));
    reader.readAsDataURL(blob);
  });
}

function loadImageElement(blob) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("not a valid image"));
    };
    img.src = url;
  });
}

// Downscales an image blob to at most ATTACH_MAX_DIMENSION px on the long side / roughly
// ATTACH_MAX_BYTES, re-encoding via canvas when either limit is exceeded; otherwise passes the
// original bytes through untouched. Returns {dataBase64, mediaType}.
async function processImageForAttach(blob, mediaTypeHint) {
  const mediaType = blob.type || mediaTypeHint || "image/png";
  const img = await loadImageElement(blob);
  const longSide = Math.max(img.naturalWidth, img.naturalHeight);
  if (longSide <= ATTACH_MAX_DIMENSION && blob.size <= ATTACH_MAX_BYTES) {
    const dataUrl = await blobToDataURL(blob);
    return { dataBase64: dataUrlToBase64(dataUrl), mediaType };
  }
  const scale = Math.min(1, ATTACH_MAX_DIMENSION / (longSide || 1));
  const w = Math.max(1, Math.round(img.naturalWidth * scale));
  const h = Math.max(1, Math.round(img.naturalHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0, w, h);
  // PNGs stay PNG only if that alone (just the resize) gets them under budget; otherwise JPEG,
  // which compresses far better for photos and is an acceptable tradeoff for chat attachments.
  const outType = mediaType === "image/png" && blob.size <= ATTACH_MAX_BYTES ? "image/png" : "image/jpeg";
  const dataUrl = canvas.toDataURL(outType, outType === "image/jpeg" ? 0.85 : undefined);
  return { dataBase64: dataUrlToBase64(dataUrl), mediaType: outType };
}

function renderAttachmentStrip() {
  dom.attachmentStrip.innerHTML = "";
  if (!pendingAttachments.length) {
    dom.attachmentStrip.classList.add("hidden");
    return;
  }
  dom.attachmentStrip.classList.remove("hidden");
  for (const att of pendingAttachments) {
    const item = el("div", { class: "attach-thumb" });
    item.appendChild(el("img", { attrs: { src: att.previewDataUrl, alt: "attached image" } }));
    const removeBtn = el("button", {
      class: "attach-thumb-remove",
      text: "×",
      attrs: { type: "button", title: "Remove" },
    });
    removeBtn.addEventListener("click", () => removeAttachment(att.id));
    item.appendChild(removeBtn);
    item.appendChild(el("span", { class: "attach-thumb-size", text: formatBytes(att.sizeBytes) }));
    dom.attachmentStrip.appendChild(item);
  }
}

function addAttachment(processed) {
  if (pendingAttachments.length >= MAX_ATTACHMENTS_PER_MESSAGE) {
    showToast(`Up to ${MAX_ATTACHMENTS_PER_MESSAGE} images per message`);
    return;
  }
  const sizeBytes = Math.round((processed.dataBase64.length * 3) / 4);
  pendingAttachments.push({
    id: `att-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    dataBase64: processed.dataBase64,
    mediaType: processed.mediaType,
    sizeBytes,
    previewDataUrl: `data:${processed.mediaType};base64,${processed.dataBase64}`,
  });
  renderAttachmentStrip();
}

function removeAttachment(id) {
  pendingAttachments = pendingAttachments.filter((a) => a.id !== id);
  renderAttachmentStrip();
}

function clearPendingAttachments() {
  pendingAttachments = [];
  renderAttachmentStrip();
}

async function attachBlob(blob, mediaTypeHint) {
  try {
    const processed = await processImageForAttach(blob, mediaTypeHint);
    addAttachment(processed);
  } catch (err) {
    showToast("Failed to attach image: " + err);
  }
}

async function onAttachButtonClick() {
  let paths;
  try {
    paths = await invoke("plugin:dialog|open", {
      options: {
        multiple: true,
        title: "Attach images",
        filters: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "gif", "webp", "bmp"] }],
      },
    });
  } catch (err) {
    showToast("Failed to open the file picker: " + err);
    return;
  }
  if (!paths) return;
  const list = Array.isArray(paths) ? paths : [paths];
  for (const path of list) {
    try {
      const file = await invoke("read_image_file", { path });
      const bytes = base64ToBytes(file.dataBase64);
      await attachBlob(new Blob([bytes], { type: file.mediaType }), file.mediaType);
    } catch (err) {
      showToast("Failed to attach file: " + err);
    }
  }
}

function base64ToBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function onComposerPaste(e) {
  const items = e.clipboardData && e.clipboardData.items;
  if (!items) return;
  const imageItems = Array.from(items).filter((it) => it.type && it.type.startsWith("image/"));
  if (!imageItems.length) return;
  if (!attachmentsAllowedForActiveSession()) {
    e.preventDefault();
    showToast(NO_IMAGE_SUPPORT_TOOLTIP);
    return;
  }
  e.preventDefault();
  for (const it of imageItems) {
    const file = it.getAsFile();
    if (file) await attachBlob(file);
  }
}

async function onComposerDrop(e) {
  e.preventDefault();
  dom.composer.classList.remove("drag-over");
  const files = Array.from((e.dataTransfer && e.dataTransfer.files) || []).filter((f) =>
    f.type.startsWith("image/")
  );
  if (!files.length) return;
  if (!attachmentsAllowedForActiveSession()) {
    showToast(NO_IMAGE_SUPPORT_TOOLTIP);
    return;
  }
  for (const f of files) await attachBlob(f);
}

// Renders one message's attached images inline in its bubble. Accepts either a live-send shape
// ({mediaType, previewDataUrl}) or a replayed TranscriptImage shape ({mediaType, base64}, base64
// possibly absent for images too large to have been inlined into the transcript payload).
function renderMessageImages(bubble, images) {
  if (!images || !images.length) return;
  const strip = el("div", { class: "msg-images" });
  for (const img of images) {
    const src = img.previewDataUrl || (img.base64 ? `data:${img.mediaType};base64,${img.base64}` : null);
    if (src) {
      const thumb = el("img", { class: "msg-image-thumb", attrs: { src, alt: "attached image" } });
      thumb.addEventListener("click", () => openLightbox(src));
      strip.appendChild(thumb);
    } else {
      strip.appendChild(el("div", { class: "msg-image-placeholder", text: "[image]" }));
    }
  }
  bubble.appendChild(strip);
}

function openLightbox(src) {
  dom.lightboxImg.src = src;
  dom.lightbox.classList.remove("hidden");
}

function closeLightbox() {
  dom.lightbox.classList.add("hidden");
  dom.lightboxImg.src = "";
}

// ---------------------------------------------------------------------------
// built-in file viewer — images / markdown / text / sandboxed html / pdf-and-other fallback
// ---------------------------------------------------------------------------

// Extensions the "VIEW OUTPUT" chip offers on a Write/Edit tool card. Matches what
// `read_workspace_file` (src-tauri/src/viewer.rs) knows how to classify.
const VIEWABLE_EXTENSIONS = new Set([
  "png", "jpg", "jpeg", "gif", "svg",
  "md", "markdown",
  "html", "htm",
  "txt", "csv",
  "pdf",
]);

function viewableFilePathFromToolInput(toolName, input) {
  if (!input || typeof input !== "object") return null;
  if (toolName !== "Write" && toolName !== "Edit") return null;
  const path = input.file_path;
  if (typeof path !== "string" || !path) return null;
  const dot = path.lastIndexOf(".");
  if (dot === -1) return null;
  const ext = path.slice(dot + 1).toLowerCase();
  return VIEWABLE_EXTENSIONS.has(ext) ? path : null;
}

async function openViewer(path) {
  dom.viewerFileName.textContent = path.split(/[\\/]/).pop() || path;
  dom.viewerBody.className = "viewer-body";
  dom.viewerBody.innerHTML = `<div class="viewer-fallback">Loading&hellip;</div>`;
  dom.viewerOpenExternalBtn.classList.add("hidden");
  dom.viewerOpenExternalBtn.onclick = null;
  dom.viewerModal.classList.remove("hidden");

  let file;
  try {
    file = await invoke("read_workspace_file", { path });
  } catch (err) {
    dom.viewerBody.innerHTML = "";
    dom.viewerBody.appendChild(el("div", { class: "viewer-fallback", text: `Couldn't open this file: ${err}` }));
    return;
  }

  renderViewerContent(file);
}

// Entry point for a clicked `.file-mention` span (timeline final-format pass — see
// linkifyFileMentions). Unlike openViewer (which always opens the modal and shows its own inline
// "Couldn't open this file" fallback on error), a mention click probes access FIRST so a broken
// mention never opens an empty/error modal — it just toasts "File not accessible" per spec.
async function openFileMentionFromTimeline(path) {
  try {
    await invoke("read_workspace_file", { path });
  } catch {
    showToast("File not accessible");
    return;
  }
  openViewer(path);
}

function closeViewer() {
  dom.viewerModal.classList.add("hidden");
  dom.viewerBody.innerHTML = "";
  dom.viewerFileName.textContent = "";
  teardownViewerComments();
}

function offerOpenExternally(path) {
  dom.viewerOpenExternalBtn.classList.remove("hidden");
  dom.viewerOpenExternalBtn.onclick = () => {
    invoke("plugin:opener|open_path", { path }).catch((err) => showToast("Couldn't open externally: " + err));
  };
}

function renderViewerContent(file) {
  dom.viewerFileName.textContent = file.fileName || dom.viewerFileName.textContent;
  dom.viewerBody.innerHTML = "";
  // Default to "not commentable" — the three kinds below that support it re-enable it explicitly
  // once their content is actually in the DOM (for "html" that's inside the iframe's load handler).
  teardownViewerComments();

  if (file.kind === "image") {
    dom.viewerBody.classList.add("viewer-body-center");
    const img = el("img", {
      class: "viewer-image",
      attrs: { src: `data:${file.mediaType};base64,${file.base64 || ""}`, alt: file.fileName || "" },
    });
    img.addEventListener("click", () => img.classList.toggle("zoomed"));
    dom.viewerBody.appendChild(img);
    return;
  }

  if (file.kind === "markdown") {
    const wrap = el("div", { class: "viewer-markdown", html: renderMarkdownFull(file.text || "") });
    dom.viewerBody.appendChild(wrap);
    initViewerComments(file.path, dom.viewerBody, window);
    return;
  }

  if (file.kind === "text") {
    const pre = el("pre", { class: "viewer-pre", text: file.text || "" });
    dom.viewerBody.appendChild(pre);
    initViewerComments(file.path, dom.viewerBody, window);
    return;
  }

  if (file.kind === "html") {
    const iframe = el("iframe", {
      class: "viewer-html-frame",
      attrs: { sandbox: "allow-same-origin", srcdoc: file.text || "" },
    });
    // srcdoc content loads asynchronously — contentDocument/contentWindow aren't usable (and the
    // comment quotes can't be highlighted or selected against) until "load" fires.
    iframe.addEventListener("load", () => {
      const idoc = iframe.contentDocument;
      if (!idoc || !idoc.body) return; // torn down (viewer closed / re-opened) before load fired
      initViewerComments(file.path, idoc.body, iframe.contentWindow, iframe);
    });
    dom.viewerBody.appendChild(iframe);
    offerOpenExternally(file.path);
    return;
  }

  // pdf / other: no inline renderer, point at the default app instead.
  dom.viewerBody.classList.add("viewer-body-center");
  dom.viewerBody.appendChild(
    el("div", { class: "viewer-fallback", text: "This file type opens in your default app." })
  );
  offerOpenExternally(file.path);
}

// ---------------------------------------------------------------------------
// viewer file comments — select text in a markdown/text/html file, comment on it, send the
// batch to the AI. No backend: persisted client-side only, per absolute file path.
// ---------------------------------------------------------------------------

const FILE_COMMENTS_STORAGE_KEY = "asb-file-comments";

// Set by initViewerComments for the file currently open in the viewer; null whenever the open
// file isn't a commentable kind (or nothing is open). `contentRoot`/`selectionWin` are the
// (element, window) pair selection is read from — dom.viewerBody/window for markdown/text, an
// iframe's contentDocument.body/contentWindow for html. `pendingQuote` is the text last selected,
// stashed here (rather than re-read from the live selection) so the fab's own click handler is
// never racing a selection that's already been cleared by the click itself.
let viewerCommentState = null;
let viewerSelectionAbort = null; // AbortController — torn down/recreated on every open/close

function loadAllFileComments() {
  try {
    const raw = localStorage.getItem(FILE_COMMENTS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveAllFileComments(all) {
  try {
    localStorage.setItem(FILE_COMMENTS_STORAGE_KEY, JSON.stringify(all));
  } catch (err) {
    showToast("Couldn't save comment: " + err);
  }
}

function getFileComments(path) {
  const all = loadAllFileComments();
  return Array.isArray(all[path]) ? all[path] : [];
}

function addFileComment(path, quote, body) {
  const all = loadAllFileComments();
  const list = Array.isArray(all[path]) ? all[path].slice() : [];
  const comment = {
    id:
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `c_${Date.now()}_${Math.random().toString(36).slice(2)}`,
    file: path,
    quote,
    body,
    createdAt: Date.now(),
  };
  list.push(comment);
  all[path] = list;
  saveAllFileComments(all);
  return comment;
}

function deleteFileComment(path, commentId) {
  const all = loadAllFileComments();
  const list = Array.isArray(all[path]) ? all[path] : [];
  all[path] = list.filter((c) => c.id !== commentId);
  saveAllFileComments(all);
}

// Wraps the FIRST occurrence of `quote` inside `container`'s rendered text in a <mark>, walking
// text nodes so the match can span multiple inline elements (e.g. a selection that crossed a
// <strong>/<code> boundary) without disturbing anything outside the matched range. No-op
// (returns false) if the quote text can't be found verbatim anymore (file edited since the
// comment was made) — comment stays in the list, just unhighlighted.
function highlightQuoteInContainer(container, quote, commentId) {
  if (!container || !quote) return false;
  const ownerDoc = container.ownerDocument;
  const walker = ownerDoc.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let fullText = "";
  let node;
  while ((node = walker.nextNode())) {
    nodes.push({ node, start: fullText.length, end: fullText.length + node.data.length });
    fullText += node.data;
  }
  const idx = fullText.indexOf(quote);
  if (idx === -1) return false;
  const endIdx = idx + quote.length;

  // Collected before any mutation, so wrapping one node below never invalidates another's offsets.
  for (const entry of nodes) {
    const overlapStart = Math.max(idx, entry.start);
    const overlapEnd = Math.min(endIdx, entry.end);
    if (overlapStart >= overlapEnd) continue;
    const range = ownerDoc.createRange();
    range.setStart(entry.node, overlapStart - entry.start);
    range.setEnd(entry.node, overlapEnd - entry.start);
    const mark = ownerDoc.createElement("mark");
    mark.className = "comment-highlight";
    mark.dataset.commentId = commentId;
    range.surroundContents(mark);
  }
  return true;
}

function unhighlightComment(container, commentId) {
  if (!container) return;
  container.querySelectorAll(`mark.comment-highlight[data-comment-id="${commentId}"]`).forEach((mark) => {
    mark.replaceWith(container.ownerDocument.createTextNode(mark.textContent));
  });
  container.normalize();
}

function renderViewerCommentsList() {
  if (!viewerCommentState) return;
  const comments = getFileComments(viewerCommentState.path);
  dom.viewerCommentsCount.textContent = String(comments.length);
  dom.viewerCommentsList.innerHTML = "";
  if (comments.length === 0) {
    dom.viewerCommentsList.appendChild(
      el("div", { class: "viewer-comments-empty", text: "Select text in the file to add a comment." })
    );
  } else {
    for (const comment of comments) {
      dom.viewerCommentsList.appendChild(buildCommentListItem(comment));
    }
  }
  dom.viewerSendCommentsBtn.textContent = `Send ${comments.length} comment${comments.length === 1 ? "" : "s"} to AI`;
  dom.viewerSendCommentsBtn.classList.toggle("hidden", comments.length === 0);
}

function buildCommentListItem(comment) {
  const item = el("div", { class: "viewer-comment-item" });
  item.dataset.commentId = comment.id;
  item.appendChild(el("blockquote", { class: "viewer-comment-quote", text: comment.quote }));
  item.appendChild(el("p", { class: "viewer-comment-body", text: comment.body }));
  const actions = el("div", { class: "viewer-comment-actions" });
  const delBtn = el("button", { class: "btn btn-ghost btn-small", text: "Delete", attrs: { type: "button" } });
  delBtn.addEventListener("click", () => handleDeleteComment(comment.id));
  actions.appendChild(delBtn);
  item.appendChild(actions);
  return item;
}

function handleDeleteComment(commentId) {
  if (!viewerCommentState) return;
  deleteFileComment(viewerCommentState.path, commentId);
  unhighlightComment(viewerCommentState.contentRoot, commentId);
  renderViewerCommentsList();
}

// Opens the "small input anchored in the comments panel" (inserted at the top of the list, above
// any saved comments) once the floating Comment button is clicked.
function openPendingCommentEditor(quote) {
  const existingPending = dom.viewerCommentsList.querySelector(".viewer-comment-pending");
  if (existingPending) existingPending.remove();
  const emptyState = dom.viewerCommentsList.querySelector(".viewer-comments-empty");
  if (emptyState) emptyState.remove();

  const item = el("div", { class: "viewer-comment-item viewer-comment-pending" });
  item.appendChild(el("blockquote", { class: "viewer-comment-quote", text: quote }));
  const textarea = el("textarea", {
    class: "viewer-comment-textarea",
    attrs: { placeholder: "Add a comment…" },
  });
  item.appendChild(textarea);
  const actions = el("div", { class: "viewer-comment-actions" });
  const cancelBtn = el("button", { class: "btn btn-ghost btn-small", text: "Cancel", attrs: { type: "button" } });
  const saveBtn = el("button", { class: "btn btn-accent btn-small", text: "Save", attrs: { type: "button" } });
  cancelBtn.addEventListener("click", () => {
    item.remove();
    if (!dom.viewerCommentsList.children.length) renderViewerCommentsList(); // restore empty-state copy
  });
  saveBtn.addEventListener("click", () => {
    const body = textarea.value.trim();
    if (!body) {
      textarea.focus();
      return;
    }
    if (!viewerCommentState) return;
    const comment = addFileComment(viewerCommentState.path, quote, body);
    highlightQuoteInContainer(viewerCommentState.contentRoot, quote, comment.id);
    clearViewerSelection();
    renderViewerCommentsList();
  });
  actions.appendChild(cancelBtn);
  actions.appendChild(saveBtn);
  item.appendChild(actions);

  dom.viewerCommentsList.insertBefore(item, dom.viewerCommentsList.firstChild);
  textarea.focus();
}

function clearViewerSelection() {
  try {
    window.getSelection().removeAllRanges();
  } catch {
    // ignore
  }
  if (viewerCommentState && viewerCommentState.selectionWin && viewerCommentState.selectionWin !== window) {
    try {
      viewerCommentState.selectionWin.getSelection().removeAllRanges();
    } catch {
      // detached iframe window (viewer closed mid-selection) — nothing to clear
    }
  }
}

function hideCommentFab() {
  dom.viewerCommentFab.classList.add("hidden");
}

// `iframeEl` is passed only for the html-kind case, so the selection Range's rect (relative to
// the iframe's OWN viewport) can be translated into the parent page's coordinate space, where the
// `position: fixed` fab actually lives.
function handleViewerMouseUp(selectionWin, iframeEl) {
  const sel = selectionWin.getSelection();
  const text = sel ? sel.toString().trim() : "";
  if (!text || !sel.rangeCount) {
    hideCommentFab();
    return;
  }
  const rect = sel.getRangeAt(0).getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) {
    hideCommentFab();
    return;
  }
  let top = rect.top;
  let left = rect.left + rect.width / 2;
  if (iframeEl) {
    const iframeRect = iframeEl.getBoundingClientRect();
    top += iframeRect.top;
    left += iframeRect.left;
  }
  viewerCommentState.pendingQuote = text;
  dom.viewerCommentFab.style.top = `${Math.max(8, top - 8)}px`;
  dom.viewerCommentFab.style.left = `${Math.max(8, left)}px`;
  dom.viewerCommentFab.classList.remove("hidden");
}

// Called once per viewer render for a commentable kind, with the (element, window) pair
// selection should be read from — see the callers in renderViewerContent. `iframeEl` is only
// passed for the html kind (needed for the fab-positioning coordinate translation above).
function initViewerComments(path, contentRoot, selectionWin, iframeEl) {
  teardownViewerComments();
  viewerCommentState = { path, contentRoot, selectionWin, iframeEl: iframeEl || null, pendingQuote: "" };
  dom.viewerCommentsPanel.classList.remove("hidden");
  renderViewerCommentsList();

  for (const comment of getFileComments(path)) {
    highlightQuoteInContainer(contentRoot, comment.quote, comment.id);
  }

  viewerSelectionAbort = new AbortController();
  const doc = contentRoot.ownerDocument;
  doc.addEventListener("mouseup", () => handleViewerMouseUp(selectionWin, iframeEl), {
    signal: viewerSelectionAbort.signal,
  });
}

function teardownViewerComments() {
  if (viewerSelectionAbort) {
    viewerSelectionAbort.abort();
    viewerSelectionAbort = null;
  }
  viewerCommentState = null;
  dom.viewerCommentsPanel.classList.add("hidden");
  hideCommentFab();
}

// "Send N comments to AI" — drafts the review request into the composer and switches to chat.
// Per spec this only composes; it does not clear the comments and does not send on the user's
// behalf (they still have to press Send themselves).
function handleSendCommentsToAI() {
  if (!viewerCommentState) return;
  const comments = getFileComments(viewerCommentState.path);
  if (comments.length === 0) return;
  const lines = comments.map((c, i) => `${i + 1}. On "${c.quote}": ${c.body}`);
  const message = `Review my comments on ${viewerCommentState.path}:\n${lines.join("\n")}`;
  dom.composerInput.value = message;
  autoGrowComposer();
  closeViewer();
  dom.composerInput.focus();
}

// Small, self-contained markdown renderer for the viewer (deliberately separate from the
// streaming-chat `renderMarkdownLite`: this one runs over a whole file, so it also handles
// headings, blockquotes, lists, and tables). Escapes HTML first, then transforms the escaped
// text — model/file content can never break out of the markup this way.
function renderMarkdownFull(raw) {
  if (!raw) return "";
  const lines = String(raw).replace(/\r\n/g, "\n").split("\n");
  let html = "";
  let i = 0;
  let paragraph = [];
  let list = null; // {type: 'ul'|'ol', items: [...]}

  const flushParagraph = () => {
    if (paragraph.length) {
      html += `<p>${renderMdInline(paragraph.join("\n"))}</p>`;
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      html += `<${list.type}>${list.items.map((it) => `<li>${renderMdInline(it)}</li>`).join("")}</${list.type}>`;
      list = null;
    }
  };

  while (i < lines.length) {
    const line = lines[i];
    const escaped = escapeHtml(line);

    // Fenced code block.
    const fence = line.match(/^```(.*)$/);
    if (fence) {
      flushParagraph();
      flushList();
      const lang = fence[1].trim();
      const body = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        body.push(lines[i]);
        i++;
      }
      i++; // skip closing fence
      const cls = lang && /^[a-zA-Z0-9_+-]+$/.test(lang) ? ` class="lang-${escapeHtml(lang)}"` : "";
      html += `<pre><code${cls}>${escapeHtml(body.join("\n"))}</code></pre>`;
      continue;
    }

    // Heading.
    const heading = escaped.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      html += `<h${level}>${renderMdInline(heading[2].trim())}</h${level}>`;
      i++;
      continue;
    }

    // Blockquote (consecutive `>` lines merge into one blockquote).
    if (/^>\s?/.test(escaped)) {
      flushParagraph();
      flushList();
      const quoted = [];
      while (i < lines.length && /^>\s?/.test(escapeHtml(lines[i]))) {
        quoted.push(escapeHtml(lines[i]).replace(/^>\s?/, ""));
        i++;
      }
      html += `<blockquote>${renderMdInline(quoted.join("\n")).replace(/\n/g, "<br>")}</blockquote>`;
      continue;
    }

    // Table (header row + separator row, e.g. "| a | b |" / "| - | - |").
    if (/^\|.*\|\s*$/.test(line) && lines[i + 1] && /^\|?[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
      flushParagraph();
      flushList();
      const parseRow = (row) =>
        row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      const headerCells = parseRow(line);
      i += 2;
      const bodyRows = [];
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) {
        bodyRows.push(parseRow(lines[i]));
        i++;
      }
      html += "<table><thead><tr>";
      html += headerCells.map((c) => `<th>${renderMdInline(escapeHtml(c))}</th>`).join("");
      html += "</tr></thead><tbody>";
      for (const row of bodyRows) {
        html += "<tr>" + row.map((c) => `<td>${renderMdInline(escapeHtml(c))}</td>`).join("") + "</tr>";
      }
      html += "</tbody></table>";
      continue;
    }

    // Lists (unordered `-`/`*`/`+`, ordered `1.`).
    const ul = escaped.match(/^\s*[-*+]\s+(.*)$/);
    const ol = escaped.match(/^\s*\d+\.\s+(.*)$/);
    if (ul || ol) {
      flushParagraph();
      const type = ul ? "ul" : "ol";
      if (!list || list.type !== type) {
        flushList();
        list = { type, items: [] };
      }
      list.items.push((ul || ol)[1]);
      i++;
      continue;
    }
    flushList();

    if (line.trim() === "") {
      flushParagraph();
      i++;
      continue;
    }

    paragraph.push(escaped);
    i++;
  }
  flushParagraph();
  flushList();
  return html;
}

function renderMdInline(escaped) {
  let out = escaped;
  out = out.replace(/`([^`]+)`/g, (_m, code) => `<code>${code}</code>`);
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  // `[text](url)` links open externally rather than navigating the app's own webview.
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_m, text, url) => {
    return `<a href="#" data-external-url="${url}">${text}</a>`;
  });
  out = out.replace(/(https?:\/\/[^\s<]+[^\s<.,)])/g, '<a href="#" data-external-url="$1">$1</a>');
  return out;
}

// ---------------------------------------------------------------------------
// send flow
// ---------------------------------------------------------------------------

async function handleSend() {
  const text = dom.composerInput.value.trim();
  if ((!text && pendingAttachments.length === 0) || dom.sendBtn.disabled) return;

  let sessionId = activeSessionId;
  try {
    if (!sessionId) {
      const meta = await invoke("new_session", { title: null, providerId: getDefaultProviderId() });
      sessionId = meta.sessionId;
      sessions.set(sessionId, freshSessionState(meta));
      activeSessionId = sessionId;
      renderSessionList();
    }

    const s = sessions.get(sessionId);
    const isFirstMessage = s.timeline.length === 0;

    // Snapshot + clear the staged attachments before the send resolves, so a fast follow-up
    // message never accidentally re-attaches the same images.
    const attachmentsPayload = pendingAttachments.map((a) => ({
      dataBase64: a.dataBase64,
      mediaType: a.mediaType,
    }));
    const attachmentsForBubble = pendingAttachments.map((a) => ({
      mediaType: a.mediaType,
      previewDataUrl: a.previewDataUrl,
    }));
    clearPendingAttachments();

    dom.composerInput.value = "";
    dom.composerInput.placeholder = "Message Claude Code…";
    autoGrowComposer();
    dom.questionHintChip.classList.add("hidden"); // the user just replied — the nudge served its purpose

    appendUserMessage(sessionId, text, attachmentsForBubble);
    s.turnStartedAt = performance.now();
    s.lastDurationMs = null;
    updateComposerEnabled();
    updateStatusBar();
    if (sessionId === activeSessionId) HUD.onUserSend(text);

    await invoke("send_message", { sessionId, text, attachments: attachmentsPayload });

    // Nice-to-have: adopt the first message as the session title until the user renames it.
    if (isFirstMessage && (!s.meta.title || s.meta.title === "New session")) {
      const title = truncate(text.replace(/\s+/g, " ").trim(), 60);
      s.meta.title = title;
      if (sessionId === activeSessionId) dom.chatTitle.textContent = title;
      renderSessionList();
      invoke("rename_session", { sessionId, title }).catch(() => {});
    }
  } catch (err) {
    appendSystemError(sessionId || activeSessionId, `Failed to send: ${err}`);
    if (sessionId) {
      const s = sessions.get(sessionId);
      if (s) {
        s.turnStartedAt = null;
        updateComposerEnabled();
      }
    }
  }
}

// ---------------------------------------------------------------------------
// AI providers — shared card component rendered into both the onboarding wizard's
// "Connect your AI" step and the Settings > AI Providers modal. Cards are collapsed by default;
// `claude` is a plain non-expandable status card (no key of its own — it's the CLI's own login).
// ---------------------------------------------------------------------------

const PROVIDER_GUIDES = {
  [KIND_GLM]: {
    blurb: "Murah untuk bulk drafting — a cheap, fast option for everyday coding and drafting work.",
    steps: [
      "Buka z.ai and subscribe to the GLM Coding Plan.",
      "Buat API key di halaman API keys (create a new key on the API keys page).",
      "Paste key di sini, then hit Save.",
    ],
    linkLabel: "Open z.ai →",
    linkUrl: "https://z.ai",
    note: "Text-only for now — no image attachments.",
  },
  [KIND_KIMI]: {
    blurb: "Kimi (Moonshot AI) is a solid all-round option that also supports image attachments.",
    steps: [
      "Buka platform.moonshot.ai.",
      "Buat API key di halaman API keys.",
      "Paste key di sini, then hit Save.",
    ],
    linkLabel: "Open platform.moonshot.ai →",
    linkUrl: "https://platform.moonshot.ai",
    note: null,
  },
  [KIND_9ROUTER]: {
    blurb:
      "Gratis. 9Router runs on this computer and forwards your work to the free AI accounts you " +
      "already have (Google, GitHub, and others). Nothing is sent to us, and there is no card to add.",
    steps: [
      "Klik Install — this app downloads 9Router for you. Only needed once.",
      "Klik Start, then Open dashboard: connect the free accounts you want to use. Nothing works until at least one is connected.",
      "Balik ke sini and pick a Model that matches an account you connected. The API key box stays empty unless 9Router gave you one.",
    ],
    linkLabel: "What is 9Router? →",
    linkUrl: "https://github.com/decolua/9router",
    note: "Which AI answers depends on the accounts you connect, so quality and image support vary.",
  },
};

// ---------------------------------------------------------------------------
// 9Router sidecar controls (the Install → Start → Open dashboard strip)
// ---------------------------------------------------------------------------
//
// Lives inside the 9Router provider card and in onboarding's connect step. The app owns the whole
// lifecycle (see src-tauri/src/ninerouter.rs) because the target user has no terminal open, so
// this strip is the only surface where install/start/stop happen.

let nineRouterStatusCache = null;

async function refreshNineRouterStatus() {
  try {
    nineRouterStatusCache = await invoke("ninerouter_status");
  } catch (err) {
    nineRouterStatusCache = null;
  }
  return nineRouterStatusCache;
}

/** Plain-language state, deliberately not the raw flags — "Not installed" means nothing to
 *  someone who never installed software from a terminal. */
function nineRouterStateCopy(st) {
  if (!st) return { tone: "unknown", label: "Checking…", detail: "" };
  if (st.running) {
    return {
      tone: "ok",
      label: "Running",
      detail: st.managed
        ? "Started by this app. It stops when you close the app."
        : "Already running on this computer (not started by this app).",
    };
  }
  if (st.installed) {
    return { tone: "idle", label: "Installed, not running", detail: "Click Start to turn it on." };
  }
  if (!st.npmAvailable) {
    return {
      tone: "blocked",
      label: "Needs Node.js first",
      detail:
        "9Router is built on Node.js, which isn't on this computer yet. Install the LTS version " +
        "from nodejs.org, then come back here.",
    };
  }
  return { tone: "idle", label: "Not installed yet", detail: "Click Install — it takes a minute or two." };
}

/** Builds the control strip. `onChange` re-renders whatever container is hosting it, so the
 *  card's status chip and the composer's provider banner stay in step with reality. */
function buildNineRouterControls(onChange) {
  const wrap = el("div", { class: "ninerouter-controls" });
  const statusRow = el("div", { class: "ninerouter-status" });
  const dot = el("span", { class: "ninerouter-dot" });
  const label = el("span", { class: "ninerouter-status-label" });
  statusRow.appendChild(dot);
  statusRow.appendChild(label);
  wrap.appendChild(statusRow);

  const detail = el("p", { class: "ninerouter-detail" });
  wrap.appendChild(detail);

  const actions = el("div", { class: "provider-card-actions" });
  const installBtn = el("button", { class: "btn btn-accent btn-small", text: "Install", attrs: { type: "button" } });
  const startBtn = el("button", { class: "btn btn-accent btn-small", text: "Start", attrs: { type: "button" } });
  const stopBtn = el("button", { class: "btn btn-ghost btn-small", text: "Stop", attrs: { type: "button" } });
  const dashBtn = el("button", {
    class: "btn btn-ghost btn-small",
    text: "Open dashboard",
    attrs: { type: "button" },
  });
  actions.appendChild(installBtn);
  actions.appendChild(startBtn);
  actions.appendChild(stopBtn);
  actions.appendChild(dashBtn);
  wrap.appendChild(actions);

  const log = el("div", { class: "ninerouter-log hidden" });
  wrap.appendChild(log);

  function paint() {
    const st = nineRouterStatusCache;
    const copy = nineRouterStateCopy(st);
    dot.className = "ninerouter-dot tone-" + copy.tone;
    label.textContent = copy.label;
    detail.textContent = copy.detail;

    installBtn.classList.toggle("hidden", !!(st && st.installed));
    installBtn.disabled = !!(st && !st.npmAvailable);
    startBtn.classList.toggle("hidden", !st || !st.installed || st.running);
    // Only ever offer to stop what we started; a proxy the user runs themselves is not ours.
    stopBtn.classList.toggle("hidden", !st || !st.running || !st.managed);
    dashBtn.classList.toggle("hidden", !st || !st.running);
  }

  /** Runs a backend command with the buttons disabled and the outcome shown inline, so a
   *  multi-minute npm install can't be clicked twice or look frozen. */
  async function run(btn, busyText, command) {
    const original = btn.textContent;
    const siblings = [installBtn, startBtn, stopBtn];
    siblings.forEach((b) => (b.disabled = true));
    btn.textContent = busyText;
    log.classList.remove("hidden");
    log.classList.remove("is-error");
    log.textContent = busyText;
    try {
      const msg = await invoke(command);
      log.textContent = typeof msg === "string" && msg ? msg : "Done.";
    } catch (err) {
      log.classList.add("is-error");
      log.textContent = String(err);
    } finally {
      btn.textContent = original;
      siblings.forEach((b) => (b.disabled = false));
      await refreshNineRouterStatus();
      paint();
      if (onChange) onChange();
    }
  }

  installBtn.addEventListener("click", () => run(installBtn, "Installing…", "ninerouter_install"));
  startBtn.addEventListener("click", () => run(startBtn, "Starting…", "ninerouter_start"));
  stopBtn.addEventListener("click", () => run(stopBtn, "Stopping…", "ninerouter_stop"));
  dashBtn.addEventListener("click", () => {
    const url = (nineRouterStatusCache && nineRouterStatusCache.dashboardUrl) || "http://localhost:20128";
    invoke("plugin:opener|open_url", { url }).catch((err) => showToast("Couldn't open the dashboard: " + err));
  });

  paint();
  // Status is fetched lazily so building the card stays synchronous like every other card here.
  refreshNineRouterStatus().then(paint);
  return wrap;
}

/** Model picker for 9Router.
 *
 *  Required, not decorative: with no model pinned, the CLI sends its own default name
 *  ("claude-opus-4-8"), 9Router has no route for it, and every message dies on a 404 naming a
 *  model the user never chose. The list comes from the running proxy, so it reflects exactly the
 *  accounts they connected. */
function buildNineRouterModelPicker(p) {
  const wrap = el("div", { class: "ninerouter-models" });
  const select = el("select", { class: "ob-input ninerouter-model-select" });
  const hint = el("p", { class: "provider-note" });
  wrap.appendChild(providerFieldRow("Model", select));
  wrap.appendChild(hint);

  function setPlaceholder(text) {
    select.innerHTML = "";
    select.appendChild(el("option", { text, attrs: { value: "" } }));
    select.disabled = true;
  }
  setPlaceholder("Start 9Router to see models…");

  async function load() {
    if (!(nineRouterStatusCache && nineRouterStatusCache.running)) return;
    let ids;
    try {
      ids = await invoke("ninerouter_models");
    } catch (err) {
      setPlaceholder("No models yet");
      hint.textContent = String(err);
      return;
    }
    select.innerHTML = "";
    for (const id of ids) select.appendChild(el("option", { text: id, attrs: { value: id } }));
    select.disabled = false;

    // Auto-adopt the first model when nothing is pinned yet, so a user who just clicked Start and
    // connected an account can send a message without first understanding what a model id is.
    // Their own saved choice always wins, even if it is no longer offered — silently switching a
    // deliberate pick would be worse than showing it as missing.
    if (p.model && ids.includes(p.model)) {
      select.value = p.model;
      hint.textContent = "";
    } else if (p.model) {
      select.value = "";
      hint.textContent = `Saved model "${p.model}" isn't offered right now. Pick another, or reconnect that account in the dashboard.`;
    } else {
      // This list is 9Router's catalogue of routable model names, NOT the subset the user has
      // accounts for — the unauthenticated endpoint cannot tell us which is which. So auto-picking
      // gets them a working default only if that account happens to be connected, and the hint has
      // to say so rather than imply everything is ready.
      select.value = ids[0];
      hint.textContent =
        "Picked for you. Whichever model you choose needs its account connected in the 9Router " +
        "dashboard, otherwise messages come back as 'model not found'.";
      await persist(ids[0]);
    }
  }

  async function persist(model) {
    try {
      const current = (providersCache || []).find((x) => x.id === p.id) || p;
      // Send back the masked key verbatim — upsert_provider treats the "****" sentinel as
      // "unchanged" and keeps the real key (see providers.rs), so this never clobbers it.
      await invoke("upsert_provider", { provider: { ...current, model } });
      await loadProviders();
    } catch (err) {
      hint.textContent = "Couldn't save that model: " + err;
    }
  }

  select.addEventListener("change", () => {
    if (!select.value) return;
    hint.textContent = "";
    persist(select.value);
  });

  load();
  return wrap;
}

async function loadProviders() {
  try {
    providersCache = await invoke("list_providers");
  } catch (err) {
    providersCache = providersCache || [];
    showToast("Failed to load AI providers: " + err);
  }
  return providersCache;
}

async function loadMultimodalSettings() {
  try {
    multimodalCache = await invoke("get_multimodal_settings");
  } catch (err) {
    multimodalCache = multimodalCache || { attachmentsEnabled: true, maxDimension: 1600, jpegQuality: 85 };
  }
  return multimodalCache;
}

async function refreshClaudeAuthStatus() {
  try {
    claudeAuthStatus = await invoke("check_auth");
  } catch (err) {
    claudeAuthStatus = { authenticated: false, detail: String(err) };
  }
  renderProviderContainers();
}

function renderProviderContainers() {
  // Note: the onboarding wizard's own provider surfaces (step 4's obProviderChoiceCards via
  // renderObProviderChoiceCards, step 6's obProviderKeyCard via renderObConnectStep) render
  // through their own dedicated functions, not this generic one — only the Settings modal
  // uses the full buildProviderCard() list.
  if (dom.settingsProviderCards) renderProviderCardsInto(dom.settingsProviderCards);
}

function renderProviderCardsInto(container) {
  container.innerHTML = "";
  for (const p of providersCache || []) {
    container.appendChild(buildProviderCard(p, false));
  }
  container.appendChild(buildAntigravityCard());
  for (const draft of providerDrafts) {
    container.appendChild(buildProviderCard(draft, true));
  }
}

// Populates the session-settings provider <select> from enabled providers, preserving whatever
// value was already selected if it still exists in the refreshed list.
function renderProviderSelectOptions() {
  if (!dom.providerSelect) return;
  const current = dom.providerSelect.value;
  dom.providerSelect.innerHTML = "";
  const list = (providersCache || []).filter((p) => p.enabled !== false);
  for (const p of list) {
    const label = providerNeedsConnection(p) ? `${p.label || p.id} — not connected` : p.label || p.id;
    dom.providerSelect.appendChild(el("option", { text: label, attrs: { value: p.id } }));
  }
  if (list.some((p) => p.id === current)) dom.providerSelect.value = current;
}

function providerStatusLabel(p) {
  if (p.kind === KIND_9ROUTER) return nineRouterStateCopy(nineRouterStatusCache).label;
  return p.apiKey ? `Key saved (${p.apiKey})` : "Not connected";
}

function providerFieldRow(labelText, inputEl) {
  const wrap = el("label", { class: "ob-field" });
  wrap.appendChild(el("span", { class: "ob-field-label", text: labelText }));
  wrap.appendChild(inputEl);
  return wrap;
}

function buildClaudeCard(p) {
  const card = el("div", { class: "provider-card provider-card-included" });
  card.dataset.providerId = p.id;
  const head = el("div", { class: "provider-card-head" });
  const titleRow = el("div", { class: "provider-card-title" });
  titleRow.appendChild(el("span", { class: "provider-name", text: p.label || "Claude (Anthropic)" }));
  titleRow.appendChild(el("span", { class: "provider-badge included", text: "Included" }));
  head.appendChild(titleRow);
  head.appendChild(
    el("div", { class: "provider-card-sub", text: "Your Claude subscription is the main engine." })
  );
  const statusText = !claudeAuthStatus
    ? "Checking…"
    : claudeAuthStatus.authenticated
    ? "Signed in"
    : "Not signed in yet";
  head.appendChild(el("div", { class: "provider-card-status-line", text: statusText }));
  card.appendChild(head);
  return card;
}

function buildAntigravityCard() {
  const id = "antigravity";
  const expanded = PROVIDER_EXPANDED.has(id);
  const card = el("div", { class: "provider-card" });
  card.dataset.providerId = id;

  const head = el("button", { class: "provider-card-head provider-card-toggle", attrs: { type: "button" } });
  const titleRow = el("div", { class: "provider-card-title" });
  titleRow.appendChild(el("span", { class: "provider-name", text: "Antigravity (Google)" }));
  titleRow.appendChild(el("span", { class: "provider-badge guide-only", text: "GUIDE ONLY" }));
  head.appendChild(titleRow);
  head.appendChild(el("span", { class: "provider-card-chevron", text: expanded ? "▾" : "▸" }));
  head.addEventListener("click", () => {
    if (expanded) PROVIDER_EXPANDED.delete(id);
    else PROVIDER_EXPANDED.add(id);
    renderProviderContainers();
  });
  card.appendChild(head);

  if (expanded) {
    const body = el("div", { class: "provider-card-body" });
    body.appendChild(
      el("p", {
        class: "provider-guide-blurb",
        text:
          "Antigravity is Google's agentic IDE, built around Gemini. It's a separate app that " +
          "runs side-by-side with AI Second Brain Desktop — deep in-app integration is on the " +
          "roadmap, but for now this is just a pointer to get it installed.",
      })
    );
    body.appendChild(
      el("a", {
        class: "provider-guide-link",
        text: "Install Antigravity →",
        attrs: { href: "https://antigravity.google", target: "_blank", rel: "noopener" },
      })
    );
    card.appendChild(body);
  }
  return card;
}

function buildProviderCard(p, isDraft) {
  if (p.kind === KIND_CLAUDE) return buildClaudeCard(p);

  const expanded = isDraft || PROVIDER_EXPANDED.has(p.id);
  const card = el("div", { class: "provider-card" });
  card.dataset.providerId = p.id;

  const head = el("button", { class: "provider-card-head provider-card-toggle", attrs: { type: "button" } });
  const titleRow = el("div", { class: "provider-card-title" });
  titleRow.appendChild(
    el("span", { class: "provider-name", text: p.label || (isDraft ? "New custom provider" : p.id) })
  );
  head.appendChild(titleRow);
  if (!isDraft) {
    head.appendChild(el("span", { class: "provider-card-status", text: providerStatusLabel(p) }));
  }
  head.appendChild(el("span", { class: "provider-card-chevron", text: expanded ? "▾" : "▸" }));
  head.addEventListener("click", () => {
    if (isDraft) return; // drafts always render expanded — nothing to toggle
    if (PROVIDER_EXPANDED.has(p.id)) PROVIDER_EXPANDED.delete(p.id);
    else PROVIDER_EXPANDED.add(p.id);
    renderProviderContainers();
  });
  card.appendChild(head);

  if (!expanded) return card;

  const body = el("div", { class: "provider-card-body" });
  body.addEventListener("click", (e) => e.stopPropagation()); // don't collapse when working inside

  if (p.kind === KIND_CUSTOM) {
    body.appendChild(
      providerFieldRow(
        "Name",
        el("input", {
          class: "ob-input provider-label-input",
          attrs: { type: "text", value: p.label || "", placeholder: "My custom provider" },
        })
      )
    );
    body.appendChild(
      providerFieldRow(
        "Base URL",
        el("input", {
          class: "ob-input provider-baseurl-input",
          attrs: { type: "text", value: p.baseUrl || "", placeholder: "https://api.example.com/anthropic" },
        })
      )
    );
    body.appendChild(
      providerFieldRow(
        "Model",
        el("input", {
          class: "ob-input provider-model-input",
          attrs: { type: "text", value: p.model || "", placeholder: "model-name (optional)" },
        })
      )
    );
  } else {
    const guide = PROVIDER_GUIDES[p.kind];
    if (guide) {
      body.appendChild(el("p", { class: "provider-guide-blurb", text: guide.blurb }));
      const stepsList = el("ol", { class: "provider-guide-steps" });
      for (const step of guide.steps) stepsList.appendChild(el("li", { text: step }));
      body.appendChild(stepsList);
      body.appendChild(
        el("a", {
          class: "provider-guide-link",
          text: guide.linkLabel,
          attrs: { href: guide.linkUrl, target: "_blank", rel: "noopener" },
        })
      );
    }
  }

  // 9Router is a process this app runs, not an account to sign into, so its card leads with the
  // install/start controls and treats the key as the rare exception rather than the main event.
  if (p.kind === KIND_9ROUTER) {
    body.appendChild(buildNineRouterControls(() => renderProviderContainers()));
    body.appendChild(buildNineRouterModelPicker(p));
  }

  const keyInput = el("input", {
    class: "ob-input provider-key-input",
    attrs: {
      type: "password",
      value: p.apiKey || "",
      placeholder: p.kind === KIND_9ROUTER ? "Usually empty — only if 9Router gave you a key" : "Paste your API key",
    },
  });
  body.appendChild(providerFieldRow(p.kind === KIND_9ROUTER ? "API key (optional)" : "API key", keyInput));

  if (p.kind === KIND_CUSTOM) {
    const imagesRow = el("label", { class: "ob-checkbox-row" });
    const imagesCheckbox = el("input", { class: "provider-images-checkbox", attrs: { type: "checkbox" } });
    imagesCheckbox.checked = !!p.supportsImages;
    imagesRow.appendChild(imagesCheckbox);
    imagesRow.appendChild(el("span", { text: "This provider supports image attachments" }));
    body.appendChild(imagesRow);
  } else {
    const guide = PROVIDER_GUIDES[p.kind];
    if (guide && guide.note) body.appendChild(el("p", { class: "provider-note", text: guide.note }));
  }

  const enabledRow = el("label", { class: "ob-checkbox-row" });
  const enabledCheckbox = el("input", { class: "provider-enabled-checkbox", attrs: { type: "checkbox" } });
  enabledCheckbox.checked = p.enabled !== false;
  enabledRow.appendChild(enabledCheckbox);
  enabledRow.appendChild(el("span", { text: "Enabled (shows up in the session provider picker)" }));
  body.appendChild(enabledRow);

  const actions = el("div", { class: "provider-card-actions" });
  const testBtn = el("button", { class: "btn btn-ghost btn-small", text: "Test", attrs: { type: "button" } });
  const saveBtn = el("button", { class: "btn btn-accent btn-small", text: "Save", attrs: { type: "button" } });
  actions.appendChild(testBtn);
  actions.appendChild(saveBtn);
  if (isDraft) {
    testBtn.disabled = true;
    testBtn.title = "Save first";
    const cancelBtn = el("button", { class: "btn btn-ghost btn-small", text: "Cancel", attrs: { type: "button" } });
    cancelBtn.addEventListener("click", () => cancelProviderDraft(p.id));
    actions.appendChild(cancelBtn);
  } else if (p.kind === KIND_CUSTOM) {
    const removeBtn = el("button", {
      class: "btn btn-ghost btn-small provider-remove-btn",
      text: "Remove",
      attrs: { type: "button" },
    });
    removeBtn.addEventListener("click", () => removeProviderCard(p.id));
    actions.appendChild(removeBtn);
  }
  body.appendChild(actions);

  const resultEl = el("div", { class: "provider-test-result hidden" });
  body.appendChild(resultEl);

  testBtn.addEventListener("click", () => testProviderCard(p.id, resultEl, testBtn));
  saveBtn.addEventListener("click", () => saveProviderCard(p, card, isDraft, saveBtn));

  card.appendChild(body);
  return card;
}

function slugifyProviderId(label) {
  const base =
    label
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "") || "custom";
  return `custom-${base}-${Math.random().toString(36).slice(2, 6)}`;
}

async function saveProviderCard(p, cardEl, isDraft, saveBtn) {
  const label = p.kind === KIND_CUSTOM ? cardEl.querySelector(".provider-label-input").value.trim() : p.label;
  if (p.kind === KIND_CUSTOM && !label) {
    showToast("Give this custom provider a name first");
    return;
  }

  const apiKeyInput = cardEl.querySelector(".provider-key-input");
  const typedKey = apiKeyInput.value.trim();

  const payload = {
    id: isDraft ? slugifyProviderId(label) : p.id,
    kind: p.kind,
    label: label || p.label,
    baseUrl:
      p.kind === KIND_CUSTOM ? cardEl.querySelector(".provider-baseurl-input").value.trim() || null : p.baseUrl || null,
    apiKey: typedKey ? typedKey : null,
    model:
      p.kind === KIND_CUSTOM ? cardEl.querySelector(".provider-model-input").value.trim() || null : p.model || null,
    supportsImages:
      p.kind === KIND_CUSTOM ? cardEl.querySelector(".provider-images-checkbox").checked : !!p.supportsImages,
    enabled: cardEl.querySelector(".provider-enabled-checkbox").checked,
  };

  saveBtn.disabled = true;
  try {
    await invoke("upsert_provider", { provider: payload });
    if (isDraft) {
      providerDrafts = providerDrafts.filter((d) => d.id !== p.id);
      PROVIDER_EXPANDED.add(payload.id);
    }
    await loadProviders();
    renderProviderContainers();
    renderProviderSelectOptions();
    updateComposerEnabled(); // key just saved may clear the provider-connect banner immediately
    const prevText = saveBtn.textContent;
    saveBtn.textContent = "Saved!";
    setTimeout(() => {
      saveBtn.textContent = prevText;
      saveBtn.disabled = false;
    }, 1200);
  } catch (err) {
    showToast("Failed to save provider: " + err);
    saveBtn.disabled = false;
  }
}

async function testProviderCard(id, resultEl, btn) {
  btn.disabled = true;
  resultEl.classList.remove("hidden", "ok", "err");
  resultEl.textContent = "Testing…";
  try {
    await invoke("test_provider", { id });
    resultEl.textContent = "Connected ✓";
    resultEl.classList.add("ok");
  } catch (err) {
    resultEl.textContent = String(err);
    resultEl.classList.add("err");
  } finally {
    btn.disabled = false;
  }
}

async function removeProviderCard(id) {
  if (!window.confirm("Remove this provider? Sessions using it will fall back to Claude.")) return;
  try {
    await invoke("remove_provider", { id });
    await loadProviders();
    renderProviderContainers();
    renderProviderSelectOptions();
  } catch (err) {
    showToast("Failed to remove provider: " + err);
  }
}

function addCustomProviderDraft() {
  const draftId = `draft-${Date.now()}`;
  providerDrafts.push({
    id: draftId,
    kind: KIND_CUSTOM,
    label: "",
    baseUrl: "",
    apiKey: "",
    model: "",
    supportsImages: false,
    enabled: true,
  });
  renderProviderContainers();
}

function cancelProviderDraft(draftId) {
  providerDrafts = providerDrafts.filter((d) => d.id !== draftId);
  renderProviderContainers();
}

// ---- Settings > AI Providers modal ----

// `focusProviderId`: opened from the provider-connect banner (or anywhere else that knows which
// provider needs attention) — expands that provider's card and scrolls it into view once the
// list re-renders, instead of leaving the user to hunt for it in a collapsed list.
function openProvidersModal(focusProviderId) {
  dom.providersModal.classList.remove("hidden");
  loadProviders().then(() => {
    if (focusProviderId) PROVIDER_EXPANDED.add(focusProviderId);
    renderProviderContainers();
    renderProviderSelectOptions();
    if (focusProviderId) {
      const card = dom.settingsProviderCards && dom.settingsProviderCards.querySelector(
        `[data-provider-id="${focusProviderId}"]`
      );
      if (card) card.scrollIntoView({ block: "center" });
    }
  });
  refreshClaudeAuthStatus();
  loadMultimodalSettings().then(populateMultimodalFields);
}

function closeProvidersModal() {
  dom.providersModal.classList.add("hidden");
}

function populateMultimodalFields() {
  if (!multimodalCache) return;
  dom.mmAttachmentsEnabled.checked = multimodalCache.attachmentsEnabled !== false;
  dom.mmMaxDimension.value = String(multimodalCache.maxDimension || 1600);
  dom.mmQuality.value = String(multimodalCache.jpegQuality || 85);
}

async function commitMultimodalSettings() {
  try {
    multimodalCache = await invoke("set_multimodal_settings", {
      settings: {
        attachmentsEnabled: dom.mmAttachmentsEnabled.checked,
        maxDimension: parseInt(dom.mmMaxDimension.value, 10),
        jpegQuality: parseInt(dom.mmQuality.value, 10),
      },
    });
    updateComposerEnabled();
    dom.mmSaveStatus.classList.remove("hidden");
    setTimeout(() => dom.mmSaveStatus.classList.add("hidden"), 1500);
  } catch (err) {
    showToast("Failed to save image-attachment settings: " + err);
  }
}

// ---------------------------------------------------------------------------
// wiring
// ---------------------------------------------------------------------------

function grabDom() {
  dom = {
    newSessionBtn: document.getElementById("newSessionBtn"),
    commandList: document.getElementById("commandList"),
    sessionList: document.getElementById("sessionList"),
    chatTitle: document.getElementById("chatTitle"),
    chatTitleInput: document.getElementById("chatTitleInput"),
    chatMeta: document.getElementById("chatMeta"),
    sessionSettings: document.getElementById("sessionSettings"),
    sessionSettingsBtn: document.getElementById("sessionSettingsBtn"),
    sessionSettingsPopover: document.getElementById("sessionSettingsPopover"),
    sessionSettingsAnchor: document.getElementById("sessionSettingsAnchor"),
    popStatusModel: document.getElementById("popStatusModel"),
    popStatusElapsed: document.getElementById("popStatusElapsed"),
    popStatusTokens: document.getElementById("popStatusTokens"),
    popStatusCost: document.getElementById("popStatusCost"),
    popStatusEmpty: document.getElementById("popStatusEmpty"),
    modelSelect: document.getElementById("modelSelect"),
    modelCustomInput: document.getElementById("modelCustomInput"),
    effortSelect: document.getElementById("effortSelect"),
    modeSelect: document.getElementById("modeSelect"),
    providerSelect: document.getElementById("providerSelect"),
    timeline: document.getElementById("timeline"),
    diagnostics: document.getElementById("diagnostics"),
    diagnosticsToggle: document.getElementById("diagnosticsToggle"),
    diagnosticsCount: document.getElementById("diagnosticsCount"),
    diagnosticsBody: document.getElementById("diagnosticsBody"),
    composer: document.getElementById("composer"),
    composerInput: document.getElementById("composerInput"),
    providerConnectBanner: document.getElementById("providerConnectBanner"),
    providerConnectBannerText: document.getElementById("providerConnectBannerText"),
    providerConnectBannerBtn: document.getElementById("providerConnectBannerBtn"),
    updateBanner: document.getElementById("updateBanner"),
    updateBannerText: document.getElementById("updateBannerText"),
    updateBannerProgress: document.getElementById("updateBannerProgress"),
    updateBannerActions: document.getElementById("updateBannerActions"),
    updateBannerLaterBtn: document.getElementById("updateBannerLaterBtn"),
    updateBannerUpdateBtn: document.getElementById("updateBannerUpdateBtn"),
    attachBtn: document.getElementById("attachBtn"),
    attachmentStrip: document.getElementById("attachmentStrip"),
    lightbox: document.getElementById("lightbox"),
    lightboxImg: document.getElementById("lightboxImg"),
    viewerModal: document.getElementById("viewerModal"),
    viewerFileName: document.getElementById("viewerFileName"),
    viewerBody: document.getElementById("viewerBody"),
    viewerOpenExternalBtn: document.getElementById("viewerOpenExternalBtn"),
    viewerCloseBtn: document.getElementById("viewerCloseBtn"),
    viewerCommentsPanel: document.getElementById("viewerCommentsPanel"),
    viewerCommentsCount: document.getElementById("viewerCommentsCount"),
    viewerCommentsList: document.getElementById("viewerCommentsList"),
    viewerSendCommentsBtn: document.getElementById("viewerSendCommentsBtn"),
    viewerCommentFab: document.getElementById("viewerCommentFab"),
    sendBtn: document.getElementById("sendBtn"),
    stopBtn: document.getElementById("stopBtn"),
    statusDot: document.getElementById("statusDot"),
    statusText: document.getElementById("statusText"),
    statusModel: document.getElementById("statusModel"),
    statusElapsed: document.getElementById("statusElapsed"),
    statusTokens: document.getElementById("statusTokens"),
    statusCost: document.getElementById("statusCost"),
    providersSettingsBtn: document.getElementById("providersSettingsBtn"),
    fullAutoChip: document.getElementById("fullAutoChip"),
    fullAutoConfirmModal: document.getElementById("fullAutoConfirmModal"),
    fullAutoCancelBtn: document.getElementById("fullAutoCancelBtn"),
    fullAutoConfirmBtn: document.getElementById("fullAutoConfirmBtn"),
    modal: document.getElementById("permissionModal"),
    permToolName: document.getElementById("permToolName"),
    permDescriptionRow: document.getElementById("permDescriptionRow"),
    permDescription: document.getElementById("permDescription"),
    permBlockedRow: document.getElementById("permBlockedRow"),
    permBlockedPath: document.getElementById("permBlockedPath"),
    permInputView: document.getElementById("permInputView"),
    permInputEdit: document.getElementById("permInputEdit"),
    permInputError: document.getElementById("permInputError"),
    permEditToggle: document.getElementById("permEditToggle"),
    permSuggestions: document.getElementById("permSuggestions"),
    permSuggestionsBody: document.getElementById("permSuggestionsBody"),
    permDenyRow: document.getElementById("permDenyRow"),
    permDenyReason: document.getElementById("permDenyReason"),
    permDenyBtn: document.getElementById("permDenyBtn"),
    permDenyConfirmBtn: document.getElementById("permDenyConfirmBtn"),
    permAllowBtn: document.getElementById("permAllowBtn"),

    permissionBanner: document.getElementById("permissionBanner"),
    permissionBannerText: document.getElementById("permissionBannerText"),
    permissionBannerReviewBtn: document.getElementById("permissionBannerReviewBtn"),

    questionHintChip: document.getElementById("questionHintChip"),
    questionModal: document.getElementById("questionModal"),
    questionModalTitle: document.getElementById("questionModalTitle"),
    questionModalBody: document.getElementById("questionModalBody"),
    questionModalOptions: document.getElementById("questionModalOptions"),
    questionModalFreeTextRow: document.getElementById("questionModalFreeTextRow"),
    questionModalFreeText: document.getElementById("questionModalFreeText"),
    questionModalSubmitBtn: document.getElementById("questionModalSubmitBtn"),

    providersModal: document.getElementById("providersModal"),
    providersModalCloseBtn: document.getElementById("providersModalCloseBtn"),
    settingsProviderCards: document.getElementById("settingsProviderCards"),
    settingsAddCustomProviderBtn: document.getElementById("settingsAddCustomProviderBtn"),
    mmSaveStatus: document.getElementById("mmSaveStatus"),
    mmAttachmentsEnabled: document.getElementById("mmAttachmentsEnabled"),
    mmMaxDimension: document.getElementById("mmMaxDimension"),
    mmQuality: document.getElementById("mmQuality"),

    onboarding: document.getElementById("onboarding"),
    obDots: document.getElementById("obDots"),
    obStep1: document.getElementById("obStep1"),
    obStep2: document.getElementById("obStep2"),
    obStep3: document.getElementById("obStep3"),
    obStep4: document.getElementById("obStep4"),
    obStep5: document.getElementById("obStep5"),
    obStep6: document.getElementById("obStep6"),
    obStep7: document.getElementById("obStep7"),
    obStep8: document.getElementById("obStep8"),
    obScreenBusy: document.getElementById("obScreenBusy"),
    obBusyText: document.getElementById("obBusyText"),

    // Step 1 — welcome
    obWelcomeNextBtn: document.getElementById("obWelcomeNextBtn"),

    // Step 2 — register
    obFieldName: document.getElementById("obFieldName"),
    obFieldEmail: document.getElementById("obFieldEmail"),
    obFieldWhatsapp: document.getElementById("obFieldWhatsapp"),
    obWhatsappNote: document.getElementById("obWhatsappNote"),
    obWhatsappError: document.getElementById("obWhatsappError"),
    obFieldProfession: document.getElementById("obFieldProfession"),
    obFieldSeniority: document.getElementById("obFieldSeniority"),
    obFieldTelemetryOptOut: document.getElementById("obFieldTelemetryOptOut"),
    obRegisterBtn: document.getElementById("obRegisterBtn"),
    obStep2BackBtn: document.getElementById("obStep2BackBtn"),
    obRegisterOfflineBanner: document.getElementById("obRegisterOfflineBanner"),
    obRegisterOfflineMsg: document.getElementById("obRegisterOfflineMsg"),
    obRegisterTryAgainBtn: document.getElementById("obRegisterTryAgainBtn"),
    obRegisterContinueOfflineBtn: document.getElementById("obRegisterContinueOfflineBtn"),
    obRegisterError: document.getElementById("obRegisterError"),

    // Step 3 — verify WhatsApp
    obVerifyCode: document.getElementById("obVerifyCode"),
    obVerifyDestination: document.getElementById("obVerifyDestination"),
    obVerifyWaLink: document.getElementById("obVerifyWaLink"),
    obVerifyCopyBtn: document.getElementById("obVerifyCopyBtn"),
    obVerifyStatus: document.getElementById("obVerifyStatus"),
    obStep3BackBtn: document.getElementById("obStep3BackBtn"),
    obVerifySkipBtn: document.getElementById("obVerifySkipBtn"),

    // Step 4 — which AI do you have
    obProviderChoiceCards: document.getElementById("obProviderChoiceCards"),
    obStep4BackBtn: document.getElementById("obStep4BackBtn"),

    // Step 5 — install Claude Code
    obInstallCommand: document.getElementById("obInstallCommand"),
    obCopyInstallBtn: document.getElementById("obCopyInstallBtn"),
    obCliDetecting: document.getElementById("obCliDetecting"),
    obCliError: document.getElementById("obCliError"),
    obStep5BackBtn: document.getElementById("obStep5BackBtn"),
    obRecheckCliBtn: document.getElementById("obRecheckCliBtn"),

    // Step 6 — connect your AI (conditional: Claude sign-in, or API key for GLM/Kimi)
    obClaudeSigninBlock: document.getElementById("obClaudeSigninBlock"),
    obLoginManualInstructions: document.getElementById("obLoginManualInstructions"),
    obAuthDetail: document.getElementById("obAuthDetail"),
    obAuthChecking: document.getElementById("obAuthChecking"),
    obProviderKeyBlock: document.getElementById("obProviderKeyBlock"),
    obProviderKeyCard: document.getElementById("obProviderKeyCard"),
    obAlsoClaudeLink: document.getElementById("obAlsoClaudeLink"),
    obStep6BackBtn: document.getElementById("obStep6BackBtn"),
    obOpenLoginBtn: document.getElementById("obOpenLoginBtn"),
    obRecheckAuthBtn: document.getElementById("obRecheckAuthBtn"),
    obProviderKeyIntro: document.getElementById("obProviderKeyIntro"),
    obProviderKeyContinueBtn: document.getElementById("obProviderKeyContinueBtn"),

    // Step 7 — workspace
    obCreateDefaultBtn: document.getElementById("obCreateDefaultBtn"),
    obDefaultPath: document.getElementById("obDefaultPath"),
    obChooseFolderBtn: document.getElementById("obChooseFolderBtn"),
    obWorkspaceError: document.getElementById("obWorkspaceError"),
    obStep7BackBtn: document.getElementById("obStep7BackBtn"),

    // Step 8 — quick tour
    obStep8BackBtn: document.getElementById("obStep8BackBtn"),
    obStartTourBtn: document.getElementById("obStartTourBtn"),
    obTour: document.getElementById("obTour"),
    obTourClickBlock: document.getElementById("obTourClickBlock"),
    obTourSpotlight: document.getElementById("obTourSpotlight"),
    obTourArrow: document.getElementById("obTourArrow"),
    obTourTooltip: document.getElementById("obTourTooltip"),
    obTourTitle: document.getElementById("obTourTitle"),
    obTourText: document.getElementById("obTourText"),
    obTourStepLabel: document.getElementById("obTourStepLabel"),
    obTourSkipBtn: document.getElementById("obTourSkipBtn"),
    obTourBackBtn: document.getElementById("obTourBackBtn"),
    obTourNextBtn: document.getElementById("obTourNextBtn"),

    waVerifyChip: document.getElementById("waVerifyChip"),

    // Dashboard tab
    viewTabChat: document.getElementById("viewTabChat"),
    viewTabDash: document.getElementById("viewTabDash"),
    chatView: document.getElementById("chatView"),
    dashView: document.getElementById("dashView"),
    dashDate: document.getElementById("dashDate"),
    dashUpdatedAt: document.getElementById("dashUpdatedAt"),
    dashRefreshBtn: document.getElementById("dashRefreshBtn"),
    dashSubTabs: document.getElementById("dashSubTabs"),
    dashLoading: document.getElementById("dashLoading"),
    dashHero: document.getElementById("dashHero"),
    dashMomentum: document.getElementById("dashMomentum"),
    dashBriefingCard: document.getElementById("dashBriefingCard"),
    dashBriefingMeta: document.getElementById("dashBriefingMeta"),
    dashBriefingBody: document.getElementById("dashBriefingBody"),
    dashActionsCount: document.getElementById("dashActionsCount"),
    dashActions: document.getElementById("dashActions"),
    dashActivity: document.getElementById("dashActivity"),
    dashInboxCount: document.getElementById("dashInboxCount"),
    dashInboxList: document.getElementById("dashInboxList"),
    dashOverdueCount: document.getElementById("dashOverdueCount"),
    dashOverdueList: document.getElementById("dashOverdueList"),
    dashDueTodayCount: document.getElementById("dashDueTodayCount"),
    dashDueTodayList: document.getElementById("dashDueTodayList"),
    dashWaitingCount: document.getElementById("dashWaitingCount"),
    dashWaitingList: document.getElementById("dashWaitingList"),
    dashMeetingsList: document.getElementById("dashMeetingsList"),
    dashUsageHero: document.getElementById("dashUsageHero"),
    dashUsageTrend: document.getElementById("dashUsageTrend"),
    dashSystemList: document.getElementById("dashSystemList"),
  };
}

// ---------------------------------------------------------------------------
// top-level Chat / Dashboard view switcher
// ---------------------------------------------------------------------------

let currentMainView = "chat";

function switchMainView(view) {
  currentMainView = view;
  const showDash = view === "dashboard";
  dom.viewTabChat.classList.toggle("is-active", !showDash);
  dom.viewTabDash.classList.toggle("is-active", showDash);
  dom.chatView.classList.toggle("is-active", !showDash);
  dom.dashView.classList.toggle("is-active", showDash);
  if (showDash) Dashboard.onShown();
}

// Deep-link: switches to the Chat tab and pre-fills the composer with `cmdLine` (a slash
// command, optionally with arguments), matching the mock's documented toast behavior. Shared by
// every Dashboard card action button.
function deepLinkToChat(cmdLine) {
  switchMainView("chat");
  dom.composerInput.value = cmdLine.endsWith(" ") ? cmdLine : cmdLine + " ";
  dom.composerInput.placeholder = "Message Claude Code…";
  autoGrowComposer();
  if (!dom.composerInput.disabled) {
    dom.composerInput.focus();
    dom.composerInput.setSelectionRange(dom.composerInput.value.length, dom.composerInput.value.length);
  }
}

function bindStaticListeners() {
  dom.newSessionBtn.addEventListener("click", async () => {
    try {
      const meta = await invoke("new_session", { title: null, providerId: getDefaultProviderId() });
      sessions.set(meta.sessionId, freshSessionState(meta));
      selectSession(meta.sessionId);
    } catch (err) {
      showToast("Failed to start a new session: " + err);
    }
  });

  dom.sendBtn.addEventListener("click", handleSend);
  dom.composerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });
  dom.composerInput.addEventListener("input", autoGrowComposer);
  dom.composerInput.addEventListener("paste", onComposerPaste);

  dom.attachBtn.addEventListener("click", onAttachButtonClick);

  ["dragover", "dragenter"].forEach((evt) =>
    dom.composer.addEventListener(evt, (e) => {
      e.preventDefault();
      dom.composer.classList.add("drag-over");
    })
  );
  dom.composer.addEventListener("dragleave", () => dom.composer.classList.remove("drag-over"));
  dom.composer.addEventListener("drop", onComposerDrop);

  dom.lightbox.addEventListener("click", closeLightbox);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !dom.lightbox.classList.contains("hidden")) closeLightbox();
    if (e.key === "Escape" && !dom.viewerModal.classList.contains("hidden")) closeViewer();
  });

  dom.viewerCloseBtn.addEventListener("click", closeViewer);
  dom.viewerModal.addEventListener("click", (e) => {
    if (e.target === dom.viewerModal) closeViewer();
  });
  dom.viewerBody.addEventListener("click", (e) => {
    const link = e.target.closest("a[data-external-url]");
    if (!link) return;
    e.preventDefault();
    const url = link.getAttribute("data-external-url");
    invoke("plugin:opener|open_url", { url }).catch((err) => showToast("Couldn't open link: " + err));
  });

  // Delegated so it covers every `.file-mention` span the final-format pass ever produces
  // (assistant text, user messages, history, tool-card preview/input/result) without needing a
  // per-node listener. preventDefault+stopPropagation so a mention sitting inside a tool card's
  // <summary> never also toggles that card's <details> open/closed.
  dom.timeline.addEventListener("click", (e) => {
    const mention = e.target.closest(".file-mention");
    if (!mention) return;
    e.preventDefault();
    e.stopPropagation();
    const path = mention.dataset.filePath;
    if (path) openFileMentionFromTimeline(path);
  });

  // Fab and send-button are stable elements (never recreated), so these are wired once — unlike
  // the mouseup selection listener, which is per-open (see initViewerComments) because for the
  // html kind it targets a brand-new iframe document every time.
  dom.viewerCommentFab.addEventListener("click", () => {
    if (!viewerCommentState || !viewerCommentState.pendingQuote) return;
    openPendingCommentEditor(viewerCommentState.pendingQuote);
    hideCommentFab();
  });
  dom.viewerSendCommentsBtn.addEventListener("click", handleSendCommentsToAI);
  // Safety net for the html/iframe case: the per-open mouseup listener that positions/hides the
  // fab is scoped to whichever document the selection lives in (the iframe's own document for
  // html), so a click that lands in the comments panel or titlebar (outside the iframe) would
  // otherwise leave a stale fab on screen. A new selection's own mousedown re-triggers this too,
  // which is fine — the fab reappears in its new position on the next mouseup regardless.
  dom.viewerModal.addEventListener("mousedown", (e) => {
    if (e.target === dom.viewerCommentFab) return;
    hideCommentFab();
  });

  dom.stopBtn.addEventListener("click", async () => {
    if (!activeSessionId) return;
    try {
      await invoke("interrupt_session", { sessionId: activeSessionId });
    } catch (err) {
      showToast("Interrupt failed: " + err);
    }
  });

  dom.modelSelect.addEventListener("change", handleModelSelectChange);
  dom.modelCustomInput.addEventListener("blur", commitCustomModel);
  dom.modelCustomInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      dom.modelCustomInput.blur(); // triggers the blur handler above
    }
  });
  dom.effortSelect.addEventListener("change", commitSessionSettings);
  dom.modeSelect.addEventListener("change", handleModeSelectChange);
  dom.providerSelect.addEventListener("change", handleProviderSelectChange);
  dom.fullAutoCancelBtn.addEventListener("click", cancelFullAutoConfirm);
  dom.fullAutoConfirmBtn.addEventListener("click", confirmFullAuto);

  dom.sessionSettingsBtn.addEventListener("click", () => toggleSessionSettingsPopover());
  document.addEventListener("click", (e) => {
    if (dom.sessionSettingsPopover.classList.contains("hidden")) return;
    if (dom.sessionSettingsAnchor.contains(e.target)) return;
    closeSessionSettingsPopover();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !dom.sessionSettingsPopover.classList.contains("hidden")) closeSessionSettingsPopover();
  });

  dom.chatTitle.addEventListener("dblclick", beginChatTitleEdit);
  dom.chatTitleInput.addEventListener("blur", commitChatTitleEdit);
  dom.chatTitleInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      dom.chatTitleInput.blur();
    } else if (e.key === "Escape") {
      e.preventDefault();
      const s = activeSessionId ? sessions.get(activeSessionId) : null;
      dom.chatTitleInput.value = (s && s.meta.title) || "";
      dom.chatTitleInput.blur();
    }
  });

  dom.diagnosticsToggle.addEventListener("click", () => {
    dom.diagnosticsBody.classList.toggle("hidden");
  });

  dom.permEditToggle.addEventListener("click", () => {
    permInputEditing = !permInputEditing;
    dom.permInputView.classList.toggle("hidden", permInputEditing);
    dom.permInputEdit.classList.toggle("hidden", !permInputEditing);
    dom.permEditToggle.textContent = permInputEditing ? "View" : "Edit";
    dom.permInputError.classList.add("hidden");
  });

  dom.permDenyBtn.addEventListener("click", () => {
    dom.permDenyRow.classList.remove("hidden");
    dom.permDenyBtn.classList.add("hidden");
    dom.permDenyConfirmBtn.classList.remove("hidden");
    dom.permDenyReason.focus();
  });
  dom.permDenyConfirmBtn.addEventListener("click", () => respondToPermission(false));
  dom.permAllowBtn.addEventListener("click", () => respondToPermission(true));

  // Persistent banner's [Review] — scroll the inline card into view and (re)open the modal, for
  // whichever secondary path the user prefers. The banner itself never auto-hides; only
  // resolving the request does that (via updatePermissionUI()).
  dom.permissionBannerReviewBtn.addEventListener("click", () => {
    const s = activeSessionId ? sessions.get(activeSessionId) : null;
    if (!s || !s.pendingPermission) return;
    if (s.pendingPermission.cardNode) {
      s.pendingPermission.cardNode.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    try {
      openPermissionModal(s);
    } catch (err) {
      console.error("openPermissionModal failed from Review banner; the inline card is still there", err);
    }
  });

  dom.questionModalSubmitBtn.addEventListener("click", submitQuestionFreeText);
  dom.questionModalFreeText.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      submitQuestionFreeText();
    }
  });
  dom.questionHintChip.addEventListener("click", () => {
    dom.questionHintChip.classList.add("hidden");
    dom.composerInput.focus();
  });

  dom.providersSettingsBtn.addEventListener("click", () => openProvidersModal());
  if (dom.providerConnectBannerBtn) {
    dom.providerConnectBannerBtn.addEventListener("click", () => {
      openProvidersModal(dom.providerConnectBanner.dataset.providerId);
    });
  }
  dom.providersModalCloseBtn.addEventListener("click", closeProvidersModal);
  dom.providersModal.addEventListener("click", (e) => {
    if (e.target === dom.providersModal) closeProvidersModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !dom.providersModal.classList.contains("hidden")) closeProvidersModal();
  });
  dom.settingsAddCustomProviderBtn.addEventListener("click", addCustomProviderDraft);
  dom.mmAttachmentsEnabled.addEventListener("change", commitMultimodalSettings);
  dom.mmMaxDimension.addEventListener("change", commitMultimodalSettings);
  dom.mmQuality.addEventListener("change", commitMultimodalSettings);

  dom.viewTabChat.addEventListener("click", () => switchMainView("chat"));
  dom.viewTabDash.addEventListener("click", () => switchMainView("dashboard"));
  Dashboard.bindListeners();

  dom.updateBannerLaterBtn.addEventListener("click", dismissUpdateBanner);
  dom.updateBannerUpdateBtn.addEventListener("click", downloadAndInstallUpdate);
}

async function wireBackendEvents() {
  await Promise.all([
    listen(EVT.STATUS, (e) => handleStatus(e.payload)),
    listen(EVT.INIT, (e) => handleInit(e.payload)),
    listen(EVT.BLOCK_START, (e) => handleBlockStart(e.payload)),
    listen(EVT.DELTA, (e) => handleDelta(e.payload)),
    listen(EVT.BLOCK_STOP, (e) => handleBlockStop(e.payload)),
    listen(EVT.MESSAGE, (e) => handleMessage(e.payload)),
    listen(EVT.TOOL_RESULT, (e) => handleToolResult(e.payload)),
    listen(EVT.PERMISSION, (e) => handlePermissionRequest(e.payload)),
    listen(EVT.QUESTION, (e) => handleQuestionRequest(e.payload)),
    listen(EVT.RESULT, (e) => handleTurnResult(e.payload)),
    listen(EVT.EXIT, (e) => handleExit(e.payload)),
    listen(EVT.RESUME_FALLBACK, (e) => handleResumeFallback(e.payload)),
    listen(EVT.SPAWN_FAILURE, (e) => handleSpawnFailure(e.payload)),
    listen(EVT.STDERR, (e) => handleStderrEvent(e.payload)),
    listen(EVT.UPDATE_CHECK_REQUESTED, () => checkForUpdates(true)),
  ]);
}

// ---------------------------------------------------------------------------
// onboarding wizard — 8-step guided stepper for non-technical office workers:
// 1 welcome -> 2 register -> 3 verify WhatsApp -> 4 which AI do you have
// (provider choice) -> 5 install Claude Code (the engine, everyone gets this)
// -> 6 connect your AI (conditional: claude.ai sign-in, or API key for
// glm/kimi) -> 7 workspace -> 8 you're all set (launches the quick tour
// overlay). Persisted to localStorage so a closed-mid-wizard app resumes
// where it left off, and shown whenever onboarding isn't marked complete OR
// the workspace isn't configured (e.g. the folder was moved/deleted after a
// prior successful run).
// ---------------------------------------------------------------------------

// Bump whenever a step's MEANING or the step order changes (not just its copy). A persisted
// state written under an older schema is never resumed positionally — the step numbers no
// longer mean the same screens (e.g. old step 4 was "install Claude Code"; step 4 is now
// "which AI do you have"). Mismatch -> restart from the welcome screen instead of landing the
// user on the wrong step.
const OB_SCHEMA_VERSION = 2;
const OB_STORAGE_KEY = "asb-onboarding";
// Separate, schema-independent key: the provider picked in step 4, used as the default for
// every session created going forward (see `getDefaultProviderId`). Deliberately NOT reset by
// an OB_SCHEMA_VERSION bump — a real provider choice the user already made shouldn't be
// forgotten just because the wizard's own step layout changed.
const OB_DEFAULT_PROVIDER_KEY = "asb-default-provider";

// 9Router, not Claude, is what a brand-new user falls back to. Everyone can run it — it costs
// nothing and needs no account — whereas defaulting to Claude means the first thing the app does
// to someone without a subscription is refuse to work. A stored choice always wins, so anyone who
// picked their own provider in onboarding keeps it.
function getDefaultProviderId() {
  try {
    return localStorage.getItem(OB_DEFAULT_PROVIDER_KEY) || KIND_9ROUTER;
  } catch (e) {
    return KIND_9ROUTER;
  }
}

function setDefaultProviderId(id) {
  try {
    localStorage.setItem(OB_DEFAULT_PROVIDER_KEY, id);
  } catch (e) {
    // localStorage unavailable — new sessions just fall back to the hard-coded default.
  }
}
const OB_TOUR_STEPS = [
  {
    selector: ".rail-commands",
    title: "Your commands",
    text: "These are your ready-made commands — click one to launch it with the right prompt already filled in.",
  },
  {
    selector: "#composer",
    title: "Talk to it directly",
    text: "Type anything here and press the + to attach an image, or just press Enter to talk to your second brain, no command needed.",
  },
  {
    selector: "#sessionSettingsBtn",
    title: "Session settings",
    text: "Pick the model, effort, and permission mode here — this also controls how much it can do without asking you first.",
  },
  {
    selector: "#hudBar",
    title: "Your pet companion",
    text: "This little companion starts as an egg and hatches as you get real work done — keep using the app to level it up.",
  },
  {
    selector: "#viewTabs",
    title: "Chat & Dashboard",
    text: "Switch between the live chat and the dashboard, which rolls up your commitments, inbox, and meetings in one place.",
  },
];

let obAccountState = null;
let obWorkspaceStatus = null;
let obCliPollTimer = null;
let obVerifyPollTimer = null;
// Polls 9Router's status while step 6 gates Continue on it — see `updateObNineRouterGate`.
let obNineRouterGateTimer = null;
let obTourIndex = 0;
// Provider picked on step 4 ("Which AI do you already have?"). null = not chosen yet this
// session (e.g. resuming from before step 4 was reached) — treated as 9Router wherever a concrete
// choice is needed, matching `getDefaultProviderId`, because that is the option that works
// without anyone having paid for anything. See `getDefaultProviderId`/`setDefaultProviderId` for
// the longer-lived, schema-independent copy used by new-session creation.
let obChosenProvider = null;
// step 6 ("Connect your AI") render state: which block is primary, and whether the optional
// "I also have a Claude subscription" link has been clicked to reveal the sign-in flow
// alongside an API-key choice.
let obConnectMode = "claude"; // "claude" | "key"
let obAlsoClaudeRevealed = false;

const OB_FRESH_LOCAL_STATE = { complete: false, step: 1, schemaVersion: OB_SCHEMA_VERSION, chosenProvider: null };

function loadObLocalState() {
  try {
    const raw = localStorage.getItem(OB_STORAGE_KEY);
    if (!raw) return { ...OB_FRESH_LOCAL_STATE };
    const parsed = JSON.parse(raw);
    if (parsed.schemaVersion !== OB_SCHEMA_VERSION) return { ...OB_FRESH_LOCAL_STATE };
    return {
      complete: !!parsed.complete,
      step: parsed.step || 1,
      schemaVersion: OB_SCHEMA_VERSION,
      chosenProvider: parsed.chosenProvider || null,
    };
  } catch (e) {
    return { ...OB_FRESH_LOCAL_STATE };
  }
}

function saveObLocalState(patch) {
  const next = { ...loadObLocalState(), ...patch, schemaVersion: OB_SCHEMA_VERSION };
  try {
    localStorage.setItem(OB_STORAGE_KEY, JSON.stringify(next));
  } catch (e) {
    // localStorage unavailable (private mode, etc.) — onboarding just re-runs next launch.
  }
  return next;
}

// Applies the "steps 2-3 auto-skip if account already registered/verified" rule when moving
// FORWARD to `target`. Never used for Back navigation (Back always shows the literal step asked
// for, even if it would otherwise be auto-skipped, since the user asked to see it again).
function obResolveForward(target) {
  let step = target;
  if (step <= 2 && obAccountState && obAccountState.registered) step = 3;
  if (step <= 3 && obAccountState && obAccountState.phoneVerified) step = 4;
  return step;
}

function obClearStepTimers() {
  if (obCliPollTimer) {
    clearInterval(obCliPollTimer);
    obCliPollTimer = null;
  }
  if (obVerifyPollTimer) {
    clearInterval(obVerifyPollTimer);
    obVerifyPollTimer = null;
  }
  if (obNineRouterGateTimer) {
    clearInterval(obNineRouterGateTimer);
    obNineRouterGateTimer = null;
  }
}

function obUpdateDots(step) {
  const dots = dom.obDots.querySelectorAll(".ob-dot");
  dots.forEach((d, i) => {
    const n = i + 1;
    d.classList.toggle("active", n === step);
    d.classList.toggle("done", n < step);
  });
}

const OB_STEP_COUNT = 8;

function obShowStep(step) {
  obClearStepTimers();
  dom.obScreenBusy.classList.add("hidden");
  for (let i = 1; i <= OB_STEP_COUNT; i++) {
    dom["obStep" + i].classList.toggle("hidden", i !== step);
  }
  dom.obDots.classList.remove("hidden");
  obUpdateDots(step);
  saveObLocalState({ step });
  obEnterStep(step);
}

function obSetBusy(text) {
  obClearStepTimers();
  for (let i = 1; i <= OB_STEP_COUNT; i++) dom["obStep" + i].classList.add("hidden");
  dom.obDots.classList.add("hidden");
  dom.obScreenBusy.classList.remove("hidden");
  dom.obBusyText.textContent = text;
}

function obEnterStep(step) {
  if (step === 2) obEnterRegisterStep();
  else if (step === 3) obEnterVerifyStep();
  else if (step === 4) obEnterProviderChoiceStep();
  else if (step === 5) obEnterCliStep();
  else if (step === 6) obEnterConnectStep();
  else if (step === 7) obEnterWorkspaceStep();
}

// ---- step 2: register ----

// Normalizes a user-typed WhatsApp number into international digits (no leading "+", no
// leading 0). Indonesia-defaults a leading-0 local number to country code 62. Returns whether
// the raw value was a local-format conversion (for the inline note) and whether the final
// digits pass the international-format check (9-15 digits, not starting with 0).
function obWhatsappNormalize(raw) {
  const trimmed = String(raw || "").trim();
  let cleaned = trimmed.replace(/[\s\-.()]/g, "").replace(/^\+/, "");
  let converted = false;
  if (/^0\d/.test(cleaned)) {
    cleaned = "62" + cleaned.slice(1);
    converted = true;
  }
  const digits = cleaned.replace(/\D/g, "");
  const valid = /^[1-9]\d{8,14}$/.test(digits);
  return { raw: trimmed, digits, converted, valid };
}

// Re-validates the WhatsApp field, updates its inline note/error state, and (optionally)
// snaps the visible value to the normalized digits. Also gates the register button so it's
// disabled while the current value is non-empty but invalid. Single source of truth for both
// what's displayed and what's ultimately stored/submitted.
function obRefreshWhatsappField(rewriteValue) {
  const result = obWhatsappNormalize(dom.obFieldWhatsapp.value);
  const isEmpty = result.raw === "";
  const isInvalid = !isEmpty && !result.valid;

  dom.obFieldWhatsapp.classList.toggle("ob-input-invalid", isInvalid);

  if (result.converted && !isEmpty) {
    dom.obWhatsappNote.textContent = `${result.raw} → ${result.digits} (international format)`;
    dom.obWhatsappNote.classList.remove("hidden");
  } else {
    dom.obWhatsappNote.classList.add("hidden");
  }

  if (isInvalid) {
    dom.obWhatsappError.textContent = "Use international format, e.g. 6281234567890";
    dom.obWhatsappError.classList.remove("hidden");
  } else {
    dom.obWhatsappError.classList.add("hidden");
  }

  if (rewriteValue && !isEmpty) dom.obFieldWhatsapp.value = result.digits;
  dom.obRegisterBtn.disabled = isInvalid;
  return result;
}

function obEnterRegisterStep() {
  const p = obAccountState && obAccountState.profile;
  if (p) {
    dom.obFieldName.value = p.name || "";
    dom.obFieldEmail.value = p.email || "";
    dom.obFieldWhatsapp.value = p.whatsapp || "";
    if (p.profession) dom.obFieldProfession.value = p.profession;
    if (p.seniority) dom.obFieldSeniority.value = p.seniority;
  }
  dom.obFieldTelemetryOptOut.checked = !!(obAccountState && obAccountState.telemetryOptOut);
  dom.obRegisterOfflineBanner.classList.add("hidden");
  dom.obRegisterError.classList.add("hidden");
  obRefreshWhatsappField(true);
}

async function obSubmitRegister() {
  const name = dom.obFieldName.value.trim();
  const email = dom.obFieldEmail.value.trim();
  const waResult = obRefreshWhatsappField(true);
  const whatsapp = waResult.digits;
  const profession = dom.obFieldProfession.value;
  const seniority = dom.obFieldSeniority.value;

  dom.obRegisterError.classList.add("hidden");
  dom.obRegisterOfflineBanner.classList.add("hidden");

  if (!name || !email || !waResult.raw || !profession || !seniority) {
    dom.obRegisterError.textContent = "Please fill in every field before continuing.";
    dom.obRegisterError.classList.remove("hidden");
    return;
  }

  if (!waResult.valid) {
    dom.obRegisterError.textContent = "Use international format for WhatsApp, e.g. 6281234567890.";
    dom.obRegisterError.classList.remove("hidden");
    return;
  }

  dom.obRegisterBtn.disabled = true;
  try {
    await invoke("set_telemetry_opt_out", { optOut: dom.obFieldTelemetryOptOut.checked });
    const outcome = await invoke("register_account", {
      profile: { name, email, whatsapp, profession, seniority },
    });
    obAccountState = await invoke("get_account_status").catch(() => obAccountState);
    obUpdateWaChip();

    if (outcome && outcome.kind === "Offline") {
      dom.obRegisterOfflineMsg.textContent =
        outcome.message || "Could not reach the registration server. Your details are saved locally.";
      dom.obRegisterOfflineBanner.classList.remove("hidden");
    } else {
      obShowStep(obResolveForward(3));
    }
  } catch (err) {
    dom.obRegisterError.textContent = "Registration failed: " + err;
    dom.obRegisterError.classList.remove("hidden");
  } finally {
    obRefreshWhatsappField(false);
  }
}

// ---- step 3: verify WhatsApp ----

// Formats a raw digit string into a readable "+cc xxx-xxxx-xxx"-style number. Special-cases the
// common Indonesian mobile shape (62 + 10 digits) to match how Brian's own number reads; falls
// back to a generic 2-digit-country-code + 3-digit grouping for anything else.
function obFormatPhoneForDisplay(digits) {
  if (!digits) return "";
  if (digits.startsWith("62") && digits.length === 12) {
    return `+62 ${digits.slice(2, 5)}-${digits.slice(5, 9)}-${digits.slice(9, 12)}`;
  }
  const ccLen = digits.length > 10 ? 2 : 1;
  const cc = digits.slice(0, ccLen);
  const rest = digits.slice(ccLen);
  const chunks = [];
  for (let i = 0; i < rest.length; i += 3) chunks.push(rest.slice(i, i + 3));
  return `+${cc} ${chunks.join("-")}`;
}

// Single source of truth for "where does the verification code go": derives the destination
// number, its display formatting, and the wa.me deep link from the same waNumber field, so the
// destination line and the "Open WhatsApp" button can never disagree.
function obGetVerifyTarget() {
  const v = obAccountState && obAccountState.verification;
  const waNumber = (v && v.waNumber) || "";
  const digits = waNumber.replace(/[^0-9]/g, "");
  const display = obFormatPhoneForDisplay(digits);
  const link = digits
    ? `https://wa.me/${digits}?text=${encodeURIComponent((v && v.code) || "")}`
    : "#";
  return { waNumber, digits, display, link };
}

function obEnterVerifyStep() {
  const v = obAccountState && obAccountState.verification;
  dom.obVerifyCode.textContent = (v && v.code) || "------";

  const target = obGetVerifyTarget();
  dom.obVerifyWaLink.href = target.link;
  dom.obVerifyWaLink.textContent = target.display
    ? `Open WhatsApp → ${target.display}`
    : "Open WhatsApp";
  if (target.display) {
    dom.obVerifyDestination.textContent = `Send it to: ${target.display} (our verification number)`;
    dom.obVerifyDestination.classList.remove("hidden");
  } else {
    dom.obVerifyDestination.classList.add("hidden");
  }

  if (obAccountState && obAccountState.phoneVerified) {
    dom.obVerifyStatus.textContent = "Verified!";
    return;
  }
  dom.obVerifyStatus.textContent = "Waiting for verification…";
  obPollVerification();
  obVerifyPollTimer = setInterval(obPollVerification, 5000);
}

async function obPollVerification() {
  try {
    const state = await invoke("poll_verification");
    obAccountState = state;
    if (state.phoneVerified) {
      dom.obVerifyStatus.textContent = "Verified! Moving on…";
      obClearStepTimers();
      obUpdateWaChip();
      setTimeout(() => obShowStep(4), 800);
    }
  } catch (err) {
    // Non-fatal: the next 5s poll (or the manual re-open of this step) tries again.
  }
}

// ---- step 4: which AI do you already have (provider choice) ----

const OB_PROVIDER_CHOICE_COPY = {
  [KIND_9ROUTER]: {
    title: "Free — nothing to pay",
    badge: "Start here",
    blurb:
      "Uses the free AI accounts you already have. This app sets it up for you. Pick this if you " +
      "don't pay for an AI subscription, or if you're not sure.",
  },
  [KIND_CLAUDE]: {
    title: "I have a Claude subscription",
    badge: "Most capable",
    blurb: "Sign in with the Claude account you already pay for. No API key needed.",
  },
  [KIND_GLM]: {
    title: "GLM by z.ai",
    badge: null,
    blurb: "Cheap coding plan — paste an API key. No claude.ai sign-in required.",
  },
  [KIND_KIMI]: {
    title: "Kimi (Moonshot)",
    badge: null,
    blurb: "API key, supports image attachments. No claude.ai sign-in required.",
  },
};
// 9Router leads. This step is where a user without a subscription would otherwise be stuck, so
// the first card has to be the one that always works; the paid options follow for people who
// already have one, and each still gets its own guided setup.
const OB_PROVIDER_CHOICE_ORDER = [KIND_9ROUTER, KIND_CLAUDE, KIND_GLM, KIND_KIMI];

async function obEnterProviderChoiceStep() {
  await loadProviders();
  // Show the free option already selected rather than leaving the step blank. Someone who does
  // not recognise any of these names should be able to press Continue and land somewhere that
  // works, instead of having to guess which one they are allowed to use.
  if (!obChosenProvider) obChosenProvider = KIND_9ROUTER;
  renderObProviderChoiceCards();
}

function renderObProviderChoiceCards() {
  dom.obProviderChoiceCards.innerHTML = "";
  for (const kind of OB_PROVIDER_CHOICE_ORDER) {
    const p = (providersCache || []).find((x) => x.id === kind);
    if (!p) continue;
    dom.obProviderChoiceCards.appendChild(buildObProviderChoiceCard(p));
  }
}

function buildObProviderChoiceCard(p) {
  const copy = OB_PROVIDER_CHOICE_COPY[p.kind] || { title: p.label, badge: null, blurb: "" };
  const selected = obChosenProvider === p.id;
  const card = el("button", {
    class: "provider-choice-card" + (selected ? " selected" : ""),
    attrs: { type: "button" },
  });
  const titleRow = el("div", { class: "provider-choice-card-title-row" });
  titleRow.appendChild(el("span", { class: "provider-choice-card-title", text: copy.title }));
  if (copy.badge) titleRow.appendChild(el("span", { class: "provider-badge included", text: copy.badge }));
  card.appendChild(titleRow);
  card.appendChild(el("p", { class: "provider-choice-card-blurb", text: copy.blurb }));
  card.addEventListener("click", () => obSelectProviderChoice(p.id));
  return card;
}

// Persists the choice (both the wizard-scoped `chosenProvider` and the long-lived
// default-for-new-sessions key), makes sure it's enabled via the existing provider commands
// (never any bespoke "set default" endpoint), then advances to the CLI install step.
async function obSelectProviderChoice(id) {
  obChosenProvider = id;
  setDefaultProviderId(id);
  saveObLocalState({ chosenProvider: id });
  renderObProviderChoiceCards(); // reflect the selection immediately, before the round-trip below

  try {
    const existing = (providersCache || []).find((p) => p.id === id);
    if (existing && existing.enabled === false) {
      await invoke("upsert_provider", { provider: { ...existing, enabled: true } });
      await loadProviders();
    }
  } catch (err) {
    showToast("Failed to enable provider: " + err);
  }

  obShowStep(5);
}

// ---- step 5: install Claude Code (the engine — everyone gets this, regardless of step 4) ----

function obEnterCliStep() {
  obCheckCliOnce();
  obCliPollTimer = setInterval(obCheckCliOnce, 5000);
}

async function obCheckCliOnce() {
  dom.obCliError.classList.add("hidden");
  try {
    const detection = await invoke("detect_cli");
    dom.obInstallCommand.textContent = detection.installCommand;
    if (detection.found) {
      dom.obCliDetecting.textContent = `Found it — Claude Code ${detection.version || ""} is installed.`;
      obClearStepTimers();
      setTimeout(() => obShowStep(6), 600);
    } else {
      dom.obCliDetecting.textContent = "Checking for Claude Code…";
    }
  } catch (err) {
    dom.obCliError.textContent = "Could not check for the CLI: " + err;
    dom.obCliError.classList.remove("hidden");
  }
}

// ---- step 6: connect your AI (conditional: claude.ai sign-in, or API key for glm/kimi) ----

// Renders whichever block(s) apply given `obConnectMode`/`obAlsoClaudeRevealed`, and toggles the
// shared footer buttons (sign-in ones vs. the key-entry "Continue") to match.
function renderObConnectStep() {
  const showClaude = obConnectMode === "claude" || obAlsoClaudeRevealed;
  const showKey = obConnectMode === "key";

  dom.obClaudeSigninBlock.classList.toggle("hidden", !showClaude);
  dom.obProviderKeyBlock.classList.toggle("hidden", !showKey);
  dom.obOpenLoginBtn.classList.toggle("hidden", !showClaude);
  dom.obRecheckAuthBtn.classList.toggle("hidden", !showClaude);
  dom.obProviderKeyContinueBtn.classList.toggle("hidden", !showKey);
  dom.obAlsoClaudeLink.classList.toggle("hidden", obConnectMode !== "key" || obAlsoClaudeRevealed);

  if (showKey) {
    const provider = (providersCache || []).find((p) => p.id === obChosenProvider);
    dom.obProviderKeyCard.innerHTML = "";
    if (provider) dom.obProviderKeyCard.appendChild(buildProviderCard(provider, false));
    // 9Router has no key to paste — the same step is an install-and-start step for it, so the
    // heading must not tell the user to go find a key that does not exist.
    const is9Router = !!provider && provider.kind === KIND_9ROUTER;
    if (dom.obProviderKeyIntro) {
      dom.obProviderKeyIntro.textContent = is9Router
        ? "Install and start 9Router below, then connect your free accounts in its dashboard."
        : "Paste your API key below, then test it — no claude.ai sign-in needed.";
    }
    // Don't let someone walk out of this step with a proxy that was never started: they would
    // finish onboarding, type their first message, and get a connection error with no idea which
    // step they skipped. Every other provider stays ungated, since a key can legitimately be
    // added later from Settings.
    updateObNineRouterGate(is9Router);
  }
}

/** Gates onboarding's Continue button on 9Router actually running.
 *
 *  Not a nag: the alternative is finishing the wizard, sending a first message, and getting a
 *  connection error that names nothing the user can act on. Re-checks on a timer because the
 *  proxy comes up from a button inside the card below, not from anything this function drives. */
function updateObNineRouterGate(is9Router) {
  const btn = dom.obProviderKeyContinueBtn;
  if (!btn) return;

  if (obNineRouterGateTimer) {
    clearInterval(obNineRouterGateTimer);
    obNineRouterGateTimer = null;
  }
  if (!is9Router) {
    btn.disabled = false;
    btn.title = "";
    btn.textContent = "Continue";
    return;
  }

  const paint = () => {
    const running = !!(nineRouterStatusCache && nineRouterStatusCache.running);
    btn.disabled = !running;
    btn.textContent = running ? "Continue" : "Waiting for 9Router…";
    btn.title = running ? "" : "Click Install, then Start, in the card above.";
  };
  paint();
  refreshNineRouterStatus().then(paint);
  obNineRouterGateTimer = setInterval(() => refreshNineRouterStatus().then(paint), 3000);
}

async function obEnterConnectStep() {
  const chosen = obChosenProvider || KIND_9ROUTER;
  obConnectMode = chosen === KIND_CLAUDE ? "claude" : "key";
  obAlsoClaudeRevealed = false;
  if (!providersCache) await loadProviders(); // resuming straight into step 6 skips step 4's load
  renderObConnectStep();
  if (obConnectMode === "claude") {
    dom.obAuthDetail.textContent = "";
    dom.obAuthChecking.classList.add("hidden");
    dom.obLoginManualInstructions.classList.add("hidden");
  }
}

// "I also have a Claude subscription — sign in too": reveals the sign-in flow ALONGSIDE the
// API-key block, it never replaces it — the chosen provider (glm/kimi) is still what continues
// the wizard unless the user explicitly finishes the Claude sign-in instead.
function obRevealClaudeSigninAlso() {
  obAlsoClaudeRevealed = true;
  dom.obAuthDetail.textContent = "";
  dom.obAuthChecking.classList.add("hidden");
  dom.obLoginManualInstructions.classList.add("hidden");
  renderObConnectStep();
}

async function obOpenLoginTerminal() {
  try {
    await invoke("open_login_terminal");
    dom.obLoginManualInstructions.classList.add("hidden");
  } catch (err) {
    dom.obLoginManualInstructions.classList.remove("hidden");
  }
}

async function obCheckAuthOnce() {
  dom.obAuthChecking.classList.remove("hidden");
  dom.obRecheckAuthBtn.disabled = true;
  dom.obAuthDetail.textContent = "";
  try {
    const check = await invoke("check_auth");
    if (check.authenticated) {
      dom.obAuthDetail.textContent = "Signed in! Moving on…";
      setTimeout(() => obShowStep(7), 600);
    } else {
      dom.obAuthDetail.textContent = check.detail || "Not signed in yet.";
    }
  } catch (err) {
    dom.obAuthDetail.textContent = "Could not check login status: " + err;
  } finally {
    dom.obAuthChecking.classList.add("hidden");
    dom.obRecheckAuthBtn.disabled = false;
  }
}

// ---- step 7: workspace ----

function obEnterWorkspaceStep() {
  dom.obDefaultPath.textContent = (obWorkspaceStatus && obWorkspaceStatus.defaultPath) || "";
  if (obWorkspaceStatus && obWorkspaceStatus.error) {
    dom.obWorkspaceError.textContent = obWorkspaceStatus.error;
    dom.obWorkspaceError.classList.remove("hidden");
  } else {
    dom.obWorkspaceError.classList.add("hidden");
  }
}

function setWorkspaceButtonsDisabled(disabled) {
  dom.obCreateDefaultBtn.disabled = disabled;
  dom.obChooseFolderBtn.disabled = disabled;
}

async function onboardingCreateDefault() {
  setWorkspaceButtonsDisabled(true);
  obSetBusy("Creating your workspace…");
  try {
    obWorkspaceStatus = await invoke("create_workspace", { path: null });
    // The rail's command list was already loaded (empty) at DOMContentLoaded, before a workspace
    // existed — refresh it now or step 8's tour highlights an empty "No commands found" rail
    // even though `.claude/commands` was just populated from the template.
    await loadHarnessCommands();
    obShowStep(8);
  } catch (err) {
    obShowStep(7);
    dom.obWorkspaceError.textContent = String(err);
    dom.obWorkspaceError.classList.remove("hidden");
  } finally {
    setWorkspaceButtonsDisabled(false);
  }
}

async function onboardingChooseFolder() {
  let dir;
  try {
    dir = await invoke("plugin:dialog|open", {
      options: { directory: true, title: "Choose your workspace folder" },
    });
  } catch (err) {
    showToast("Failed to open the folder picker: " + err);
    return;
  }
  if (!dir) return; // user cancelled — stay on the workspace screen

  setWorkspaceButtonsDisabled(true);
  obSetBusy("Setting up your workspace…");
  try {
    obWorkspaceStatus = await invoke("choose_workspace", { path: dir });
    // Same "No commands found" bug as `onboardingCreateDefault`: refresh the rail now that a
    // workspace (and possibly a .claude/commands dir) exists.
    await loadHarnessCommands();
    obShowStep(8);
  } catch (err) {
    obShowStep(7);
    dom.obWorkspaceError.textContent = String(err);
    dom.obWorkspaceError.classList.remove("hidden");
  } finally {
    setWorkspaceButtonsDisabled(false);
  }
}

// ---- step 7: quick tour ----
//
// Spotlight pattern: a full-screen dim (giant box-shadow cutout, see .ob-tour-spotlight)
// with the real target element popped above it, plus a card+arrow that sits adjacent to
// the target and flips to whichever side actually fits the viewport. Positions are
// recomputed on every step and on resize. A stop whose target is missing/display:none
// (e.g. attach button hidden for a provider without image support, or a HUD collapsed to
// nothing) is skipped rather than shown floating in the middle of the screen.

// Resolves a tour stop's target element, treating "not in the DOM" and "hidden" the same
// way (both mean: skip this stop) so callers never have to special-case null vs invisible.
function obResolveTourTarget(step) {
  const el = step && document.querySelector(step.selector);
  if (!el) return null;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return null;
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  return el;
}

// Walks from `fromIndex` in `direction` (+1/-1) and returns the first step index whose
// target currently resolves, or -1 if none do (used by Next/Back to skip hidden stops).
function obFindVisibleTourIndex(fromIndex, direction) {
  let i = fromIndex;
  while (i >= 0 && i < OB_TOUR_STEPS.length) {
    if (obResolveTourTarget(OB_TOUR_STEPS[i])) return i;
    i += direction;
  }
  return -1;
}

function obStartTour() {
  dom.onboarding.classList.add("hidden");
  const first = obFindVisibleTourIndex(0, 1);
  if (first === -1) {
    // Nothing to point at (extremely unlikely) — don't show an empty tour.
    obFinishTour();
    return;
  }
  obTourIndex = first;
  dom.obTour.classList.remove("hidden");
  obShowTourStep();
  window.addEventListener("resize", obRepositionTour);
}

// Positions the spotlight cutout, the target's own highlight ring, the arrow, and the
// tooltip card together for the current step. Re-run on every step change and on resize.
function obRepositionTour() {
  const step = OB_TOUR_STEPS[obTourIndex];
  const target = step && obResolveTourTarget(step);
  const tooltip = dom.obTourTooltip;
  const spotlight = dom.obTourSpotlight;
  const arrow = dom.obTourArrow;
  if (!target) {
    spotlight.style.opacity = "0";
    arrow.classList.add("hidden");
    tooltip.style.transform = "none";
    tooltip.style.top = "50%";
    tooltip.style.left = "50%";
    tooltip.style.transform = "translate(-50%, -50%)";
    return;
  }

  const pad = 8;
  const rect = target.getBoundingClientRect();
  const spotRect = {
    top: rect.top - pad,
    left: rect.left - pad,
    width: rect.width + pad * 2,
    height: rect.height + pad * 2,
  };
  spotlight.style.opacity = "1";
  spotlight.style.top = `${spotRect.top}px`;
  spotlight.style.left = `${spotRect.left}px`;
  spotlight.style.width = `${spotRect.width}px`;
  spotlight.style.height = `${spotRect.height}px`;

  tooltip.style.transform = "none";
  const gap = 16; // distance from spotlight edge to card, leaves room for the arrow
  const margin = 12; // minimum distance from the viewport edge
  tooltip.style.visibility = "hidden";
  arrow.classList.add("hidden");
  requestAnimationFrame(() => {
    const tw = tooltip.offsetWidth;
    const th = tooltip.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Prefer below the target; flip above if it wouldn't fit; if neither vertical slot
    // has room (short viewport), fall back to whichever side to the target has more space.
    const spaceBelow = vh - spotRect.top - spotRect.height - gap - margin;
    const spaceAbove = spotRect.top - gap - margin;
    let placement;
    if (th <= spaceBelow) placement = "bottom";
    else if (th <= spaceAbove) placement = "top";
    else placement = spaceBelow >= spaceAbove ? "bottom" : "top";

    let top;
    let left = spotRect.left + spotRect.width / 2 - tw / 2;
    if (placement === "bottom") {
      top = spotRect.top + spotRect.height + gap;
    } else {
      top = spotRect.top - th - gap;
    }
    // Clamp horizontally to the viewport, then clamp vertically as a last resort so the
    // card never renders off-screen even if it didn't fit either slot.
    if (left + tw > vw - margin) left = vw - margin - tw;
    if (left < margin) left = margin;
    if (top + th > vh - margin) top = vh - margin - th;
    if (top < margin) top = margin;

    tooltip.style.top = `${top}px`;
    tooltip.style.left = `${left}px`;
    tooltip.style.visibility = "visible";

    // Arrow: a small rotated diamond, half showing, sitting on the edge of the card that
    // touches the spotlight, pointed at the target's horizontal (or vertical) center.
    arrow.classList.remove("ob-tour-arrow-top", "ob-tour-arrow-bottom", "ob-tour-arrow-left", "ob-tour-arrow-right");
    const arrowSize = 14;
    const targetCenterX = spotRect.left + spotRect.width / 2;
    let arrowX = Math.min(Math.max(targetCenterX, left + 16), left + tw - 16) - arrowSize / 2;
    let arrowY;
    let side;
    if (placement === "bottom") {
      side = "top"; // arrow sits on the card's top edge, pointing up at the target
      arrowY = top - arrowSize / 2;
    } else {
      side = "bottom"; // arrow sits on the card's bottom edge, pointing down at the target
      arrowY = top + th - arrowSize / 2;
    }
    arrow.classList.add(`ob-tour-arrow-${side}`);
    arrow.style.left = `${arrowX}px`;
    arrow.style.top = `${arrowY}px`;
    arrow.classList.remove("hidden");
  });
}

function obShowTourStep() {
  document.querySelectorAll(".ob-tour-highlight").forEach((n) => n.classList.remove("ob-tour-highlight"));
  const step = OB_TOUR_STEPS[obTourIndex];
  dom.obTourTitle.textContent = step.title || "";
  dom.obTourText.textContent = step.text;
  dom.obTourStepLabel.textContent = `${obTourIndex + 1} / ${OB_TOUR_STEPS.length}`;
  dom.obTourNextBtn.textContent = obFindVisibleTourIndex(obTourIndex + 1, 1) === -1 ? "Finish" : "Next";
  dom.obTourBackBtn.disabled = obFindVisibleTourIndex(obTourIndex - 1, -1) === -1;
  const target = obResolveTourTarget(step);
  if (target) target.classList.add("ob-tour-highlight");
  obRepositionTour();
}

function obTourNext() {
  const next = obFindVisibleTourIndex(obTourIndex + 1, 1);
  if (next === -1) {
    obFinishTour();
  } else {
    obTourIndex = next;
    obShowTourStep();
  }
}

function obTourBack() {
  const prev = obFindVisibleTourIndex(obTourIndex - 1, -1);
  if (prev !== -1) {
    obTourIndex = prev;
    obShowTourStep();
  }
}

function obFinishTour() {
  document.querySelectorAll(".ob-tour-highlight").forEach((n) => n.classList.remove("ob-tour-highlight"));
  dom.obTour.classList.add("hidden");
  window.removeEventListener("resize", obRepositionTour);
  saveObLocalState({ complete: true, step: OB_STEP_COUNT });
  obUpdateWaChip();
  dom.composerInput.value = "/daily-review ";
  autoGrowComposer();
  if (!dom.composerInput.disabled) dom.composerInput.focus();
}

// ---- persistent "Verify WhatsApp" nag chip (status bar) ----

function obUpdateWaChip() {
  const show = !!(obAccountState && obAccountState.registered && !obAccountState.phoneVerified);
  dom.waVerifyChip.classList.toggle("hidden", !show);
}

// ---- wiring + entry point ----

function bindOnboardingListeners() {
  dom.obWelcomeNextBtn.addEventListener("click", () => obShowStep(obResolveForward(2)));

  dom.obRegisterBtn.addEventListener("click", obSubmitRegister);
  dom.obStep2BackBtn.addEventListener("click", () => obShowStep(1));
  dom.obRegisterTryAgainBtn.addEventListener("click", obSubmitRegister);
  dom.obRegisterContinueOfflineBtn.addEventListener("click", () => obShowStep(obResolveForward(3)));
  dom.obFieldWhatsapp.addEventListener("input", () => obRefreshWhatsappField(false));
  dom.obFieldWhatsapp.addEventListener("blur", () => obRefreshWhatsappField(true));

  dom.obVerifyCopyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(dom.obVerifyWaLink.href || "");
      const prev = dom.obVerifyCopyBtn.textContent;
      dom.obVerifyCopyBtn.textContent = "Copied!";
      setTimeout(() => (dom.obVerifyCopyBtn.textContent = prev), 1500);
    } catch (err) {
      showToast("Failed to copy: " + err);
    }
  });
  dom.obStep3BackBtn.addEventListener("click", () => obShowStep(2));
  dom.obVerifySkipBtn.addEventListener("click", () => obShowStep(4));

  dom.obCopyInstallBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(dom.obInstallCommand.textContent || "");
      const prev = dom.obCopyInstallBtn.textContent;
      dom.obCopyInstallBtn.textContent = "Copied!";
      setTimeout(() => (dom.obCopyInstallBtn.textContent = prev), 1500);
    } catch (err) {
      showToast("Failed to copy: " + err);
    }
  });
  // step 4 — which AI do you already have (cards themselves wire their own click handler in
  // buildObProviderChoiceCard; only Back lives here)
  dom.obStep4BackBtn.addEventListener("click", () => obShowStep(3));

  // step 5 — install Claude Code
  dom.obRecheckCliBtn.addEventListener("click", obCheckCliOnce);
  dom.obStep5BackBtn.addEventListener("click", () => obShowStep(4));

  // step 6 — connect your AI (conditional)
  dom.obOpenLoginBtn.addEventListener("click", obOpenLoginTerminal);
  dom.obRecheckAuthBtn.addEventListener("click", obCheckAuthOnce);
  dom.obAlsoClaudeLink.addEventListener("click", obRevealClaudeSigninAlso);
  dom.obProviderKeyContinueBtn.addEventListener("click", () => obShowStep(7));
  dom.obStep6BackBtn.addEventListener("click", () => obShowStep(5));

  dom.obCreateDefaultBtn.addEventListener("click", onboardingCreateDefault);
  dom.obChooseFolderBtn.addEventListener("click", onboardingChooseFolder);
  dom.obStep7BackBtn.addEventListener("click", () => obShowStep(6));

  dom.obStep8BackBtn.addEventListener("click", () => obShowStep(7));
  dom.obStartTourBtn.addEventListener("click", obStartTour);
  dom.obTourNextBtn.addEventListener("click", obTourNext);
  dom.obTourBackBtn.addEventListener("click", obTourBack);
  dom.obTourSkipBtn.addEventListener("click", obFinishTour);

  dom.waVerifyChip.addEventListener("click", () => {
    dom.onboarding.classList.remove("hidden");
    obShowStep(3);
  });
}

async function runOnboarding() {
  bindOnboardingListeners();

  try {
    obWorkspaceStatus = await invoke("get_workspace_status");
  } catch (err) {
    showToast("Failed to read workspace status: " + err);
    obWorkspaceStatus = { configured: false, error: null, defaultPath: "" };
  }

  try {
    obAccountState = await invoke("get_account_status");
  } catch (err) {
    obAccountState = null;
  }
  obUpdateWaChip();

  const persisted = loadObLocalState();
  obChosenProvider = persisted.chosenProvider || null;
  const workspaceOk = !!(obWorkspaceStatus.configured && !obWorkspaceStatus.error);

  if (persisted.complete && workspaceOk) return; // fully onboarded — normal instant startup

  dom.onboarding.classList.remove("hidden");

  // Resume at the persisted step, but re-apply the register/verify auto-skip in case account
  // state has changed since the wizard was last open (e.g. verified from another device).
  let startStep = obResolveForward(Math.max(persisted.step || 1, 1));
  // Never silently resume straight into "you're all set" if the workspace isn't actually there —
  // that would show the tour over a broken/missing workspace.
  if (startStep === OB_STEP_COUNT && !workspaceOk) startStep = OB_STEP_COUNT - 1;

  obShowStep(startStep);
}

// ---------------------------------------------------------------------------
// PET BATTLER HUD — a quest companion driven entirely by real session events.
// Self-contained module: owns its own canvas, tick loop, and localStorage save
// (key "asb-pet"); the rest of the app only ever calls the handful of one-line
// hooks exposed on the returned object (HUD.onBlockStart, HUD.onDelta, ...)
// from inside the existing claude:* event handlers above. Never touches the
// chat timeline DOM, never blocks the composer.
//
// Sprites/palettes/evolution/effects engine ported from the approved design
// mock (hud_mock_template.html). The mock's canvas was 640x300; this in-app
// arena is 640x200 (per integration spec), so every Y-position and sprite
// pixel size below is the mock's value scaled by 2/3 — the mock's 24-wide
// hi-res matrices, palettes, and battle mechanics are otherwise unchanged.
// ---------------------------------------------------------------------------
const HUD = (() => {
  const SAVE_KEY = "asb-pet";
  const INTRO_KEY = "asb-pet-intro-seen";
  const MODE_KEY = "asb-hud-mode";
  const LEGACY_COLLAPSE_KEY = "asb-hud-collapsed"; // pre-modes boolean, read once for migration
  const ARENA_SCALE = { compact: 0.6, expanded: 1 };
  const MODE_GLYPH = { compact: "⤢", expanded: "▾", collapsed: "▸" };
  const MODE_TITLE = { compact: "Expand pet HUD", expanded: "Minimize pet HUD", collapsed: "Restore pet HUD" };

  /* ============ PALETTES: 0 outline 1 body 2 light 3 eye/gold 4 accent 5 shade ============ */
  const PAL = {
    bit: ["#12224a", "#3B82F6", "#93c5fd", "#C8902A", "#8b5cf6", "#1d4ed8"],
    byte: ["#12224a", "#94a3b8", "#e2e8f0", "#C8902A", "#3B82F6", "#475569"],
    link: ["#12224a", "#38bdf8", "#bae6fd", "#C8902A", "#0ea5e9", "#0369a1"],
    pixel: ["#12224a", "#ec4899", "#fbcfe8", "#C8902A", "#8b5cf6", "#9d174d"],
    scribe: ["#12224a", "#e2d9c3", "#f5efe0", "#C8902A", "#a16207", "#a8a29e"],
  };
  /* 32x28 hi-res rookie-and-up sprites (facing right) — replace the old 24-wide
     SPR24 set so ROOKIE/CHAMPION/ULTIMATE render visibly larger (see ARENA below). */
  const SPR32 = {
    bit: [
      '................................',
      '................................',
      '..........00000000..............',
      '........0011111110..............',
      '.......011111111110.............',
      '......0111222211110.............',
      '......0122333322110.............',
      '......0122333322510.............',
      '......0122333322510.............',
      '......0111222211110.............',
      '......0111555555110.............',
      '......0111555555110.............',
      '.......011111111110.............',
      '........0011111110..............',
      '..........00550000..............',
      '............55055...............',
      '............55055...............',
      '............00500...............',
      '................................',
      '................................',
      '................................',
      '................................',
      '................................',
      '................................',
      '................................',
      '................................',
      '................................',
      '................................',
    ],
    byte: [
      '................................',
      '...........00...................',
      '..........0110..................',
      '..........0110..................',
      '..........0110..................',
      '.......00001100.................',
      '......0111111000................',
      '.....011112211110...............',
      '.....011133331110...............',
      '.....012233331110...............',
      '.....012211111110...............',
      '.....011115555110...............',
      '.....011115555110...............',
      '......0111111110................',
      '......0550011500................',
      '......055.011.05................',
      '......055.011.05................',
      '......00000110005...............',
      '........011111005...............',
      '........011111000...............',
      '........0555500.................',
      '........055.00.00...............',
      '........055.00.04...............',
      '........00..00.04...............',
      '.............0..4...............',
      '..............004...............',
      '...............04...............',
      '................................',
    ],
    link: [
      '................................',
      '................................',
      '...........00000................',
      '..........0222210...............',
      '.........022222210..............',
      '.........022111210..............',
      '.........021331210..............',
      '.........021331210..............',
      '.........022111210..............',
      '.........02222110...............',
      '..........021110................',
      '.......0...0110...0.............',
      '......030...00...030............',
      '.....03330......03330...........',
      '....0000000....0000000..........',
      '....0444444444444444400.........',
      '.....044444444444444440.........',
      '......00000000000000000.........',
      '.........050..050...............',
      '.........050..050...............',
      '........0050.0050...............',
      '........0050.0050...............',
      '........0000000000..............',
      '................................',
      '................................',
      '................................',
      '................................',
      '................................',
    ],
    pixel: [
      '................................',
      '................................',
      '................................',
      '..........00000000..............',
      '........001111111100............',
      '.......0111111111110............',
      '......011112221111110...........',
      '......012211111112210...........',
      '.....01221333113312210..........',
      '.....01221333113312210..........',
      '.....01221111111112210..........',
      '.....01221133311112210..........',
      '.....01221133331112210..........',
      '.....01221111133112210..........',
      '.....01121111111151110..........',
      '......011111111111110...........',
      '......011111111111110...........',
      '.......0111111111110............',
      '........01111111110.............',
      '.........000011000..............',
      '...........050050...............',
      '...........050050...............',
      '..........05000050..............',
      '..........00000000..............',
      '................................',
      '................................',
      '................................',
      '................................',
    ],
    scribe: [
      '................................',
      '................................',
      '............040.................',
      '...........04340................',
      '..........0433340...............',
      '.........043333340..............',
      '........04333333340.............',
      '.......0433333333400............',
      '......0000000000011110..........',
      '.....0112221110111110...........',
      '....011222211101111110..........',
      '...01155551111011151110.........',
      '..0115555511111011511110........',
      '..0115555511111011511110........',
      '..0115555511111011511110........',
      '..0115555511111011511110........',
      '..0115555511111011511110........',
      '..0115555511111011511110........',
      '...01155551111011151110.........',
      '....011222211101111110..........',
      '.....0112221110111110...........',
      '......00000000000000............',
      '................................',
      '................................',
      '................................',
      '................................',
      '................................',
      '................................',
    ],
  };
  /* baby 12x12 (chibi) */
  const SPR12 = {
    bit: ['............','...000000...','..01111110..','.0111111110.','.0112222110.','.0122552210.','.0125335210.','.0122552210.','.0112222110.','..01111110..','...000000...','............'],
    byte: ['.44......44.','.040....040.','..00000000..','.0111111110.','.0122112210.','.0111111110.','..00111100..','.0111111110.','.0101101010.','..00..00....','............','............'],
    link: ['....0000....','...011110...','..01222210..','.4011221103.','44012211033.','.4011111110.','..01111110..','...011110...','....0110....','...00..00...','............','............'],
    pixel: ['............','....0000....','..00111100..','.0111111110.','.0114411110.','.0114411410.','.0111331110.','.0111111110.','..00111100..','....0000....','............','............'],
    scribe: ['............','.0000..0000.','.0111001110.','.0122111210.','.0122212210.','.0111111110.','.0000000000.','...0....0...','...3....3...','............','............','............'],
  };
  /* 32x28 egg — bigger canvas than the old 12-wide egg so it reads at a
     comparable in-arena size to the new rookie-and-up sprites (see ARENA.EGG_PX). */
  const EGG = [
    '................................',
    '................................',
    '................................',
    '............000000..............',
    '..........0011111100............',
    '........0011111111100...........',
    '.......011111111111110..........',
    '......0111122111111110..........',
    '.....011112221111111110.........',
    '.....011111111111111110.........',
    '....01133001110033111110........',
    '....013300330033001111110.......',
    '....011333111333111111110.......',
    '....011111555555111111110.......',
    '....011111555555111111110.......',
    '....011111115555111111110.......',
    '....011111111111111111110.......',
    '.....0111111111111111110........',
    '.....0111111111111111110........',
    '......011111111111111110........',
    '......011111111111111110........',
    '.......0111111111111110.........',
    '........01111111111110..........',
    '.........001111111100...........',
    '...........000000000............',
    '................................',
    '................................',
    '................................',
  ];
  /* champion armor overlay + ultimate crown, authored at 25x20 and algorithmically
     extended/redrawn to 32x28 (nearest-neighbor) so it lines up with the new
     32x28 SPR32 body instead of the retired 24-wide SPR24 silhouette. */
  const ARMOR_SRC = ['...........33...........', '..........3443..........', '........................', '........................', '........................', '........................', '........................', '..44..............44....', '.4444............4444...', '.4444............4444...', '..44..............44....', '...........3............', '..........343...........', '...........3............', '........................', '........................', '........................', '........................', '........................', '........................'];
  function scaleMatrix(m, newW, newH) {
    const h = m.length, w = m[0].length, out = [];
    for (let y = 0; y < newH; y++) {
      const sy = Math.min(h - 1, Math.floor((y * h) / newH));
      let row = "";
      for (let x = 0; x < newW; x++) row += m[sy][Math.min(w - 1, Math.floor((x * w) / newW))];
      out.push(row);
    }
    return out;
  }
  const ARMOR = scaleMatrix(ARMOR_SRC, 32, 28);
  const STAGES = ["EGG", "BABY", "ROOKIE", "CHAMPION", "ULTIMATE"];
  const THRESH = [1, 5, 15, 30, 50];
  function stageIdx(lv) {
    let s = 0;
    for (let i = 0; i < THRESH.length; i++) if (lv >= THRESH[i]) s = i;
    return s;
  }
  // px sizes derive from ARENA.H (the 200-tall virtual arena; see ARENA below) so the
  // pet reads at ~170-190px tall in expanded mode and scales down proportionally in
  // compact/collapsed via arenaScale — not tuned-by-eye magic numbers per stage.
  function stageSpec(sp, st) {
    if (st === 0) return { m: EGG, px: ARENA.EGG_PX, armor: 0, wings: 0, aura: 0 };
    if (st === 1) return { m: SPR12[sp], px: 8, armor: 0, wings: 0, aura: 0 };
    if (st === 2) return { m: SPR32[sp], px: ARENA.PET_PX, armor: 0, wings: 0, aura: 0 };
    if (st === 3) return { m: SPR32[sp], px: ARENA.PET_PX, armor: 1, wings: 0, aura: 0 };
    return { m: SPR32[sp], px: ARENA.PET_PX, armor: 1, wings: 1, aura: 1 };
  }
  function drawMat(ctx2, m, pal, cx, baseY, px, flip, tint, alpha) {
    const w = m[0].length * px, h = m.length * px, x0 = Math.round(cx - w / 2), y0 = Math.round(baseY - h);
    ctx2.save();
    ctx2.globalAlpha = alpha == null ? 1 : alpha;
    for (let y = 0; y < m.length; y++) {
      for (let x = 0; x < m[y].length; x++) {
        const ch = m[y][x];
        if (ch === "." || ch === undefined) continue;
        const xx = flip ? m[y].length - 1 - x : x;
        ctx2.fillStyle = tint || pal[+ch] || pal[1];
        ctx2.fillRect(x0 + xx * px, y0 + y * px, px, px);
      }
    }
    ctx2.restore();
    return { x: x0, y: y0, w, h };
  }
  function up2(m) {
    const o = [];
    m.forEach((r) => {
      let a = "";
      for (const c of r) a += c + c;
      o.push(a);
      o.push(a);
    });
    return o;
  }
  const ENEMIES = [
    ["EMAIL GOBLIN", ["#12224a", "#16a34a", "#bbf7d0", "#facc15", "#166534"], up2(["..0......0..", "..00....00..", "..01000010..", ".0111111110.", ".0121121210.", ".0111111110.", ".0114444110.", ".0111441110.", ".0111111110.", "..01100110..", "..00....00..", "............"]), "goblin"],
    ["BUG SLIME", ["#12224a", "#dc2626", "#fecaca", "#facc15", "#7f1d1d"], up2(["............", "....0000....", "..00111100..", ".0112211110.", ".0112211410.", "01111111110.", "01113311110.", ".0111111110.", "..00000000..", "............", "............", "............"]), "slime"],
    ["REPORT GOLEM", ["#12224a", "#78716c", "#e7e5e4", "#facc15", "#44403c"], up2(["..000000....", "..011110....", "..012210....", ".00111100...", ".0111111000.", ".0111111110.", ".0111111110.", "..0111100...", "..0110110...", "..0110110...", "..000.000...", "............"]), "golem"],
    ["DEADLINE REAPER", ["#12224a", "#7c3aed", "#ddd6fe", "#facc15", "#4c1d95"], up2([".....000....", "....01110...", "...0112110..", "...0122210..", "...0111110..", "..011111110.", ".01111111100", ".0111111104.", "..011111104.", "...0000004..", "......04....", "......4....."]), "reaper"],
  ];
  const SPECIES = [
    ["bit", "BIT", "Data & Analysis"],
    ["byte", "BYTE", "Code & Dev"],
    ["link", "LINK", "Web & Search"],
    ["pixel", "PIXEL", "Design & UI"],
    ["scribe", "SCRIBE", "Writing & Comms"],
  ];

  // ---------------------------------------------------------------------------
  // SPRITE ASSETS (v2 art) — PNGs produced by tools/build_pet_sprites.py from
  // AI-generated source art, landed in assets/sprites/. Preloaded once at
  // init(); every draw site checks readiness and falls back to the matrix
  // renderer above (per-species/per-enemy/per-egg granularity) if a given
  // PNG is missing, still loading, or failed to decode — the matrix set is
  // never deleted, only shadowed once its PNG replacement is ready.
  // ---------------------------------------------------------------------------
  const SPRITE_BASE = "assets/sprites/";
  const ANIM_STATES = ["idle", "walk", "attack"];
  const SPR_CACHE = {}; // key ("bit_idle", "enemy_goblin", "bg_journey", ...) -> { img, ready, failed }
  function spriteKeysToLoad() {
    const keys = [];
    SPECIES.forEach(([id]) => ANIM_STATES.forEach((st) => keys.push(id + "_" + st)));
    keys.push("egg_idle");
    ENEMIES.forEach(([, , , id]) => keys.push("enemy_" + id));
    keys.push("bg_journey", "bg_battle");
    return keys;
  }
  function preloadSprites() {
    spriteKeysToLoad().forEach((key) => {
      const rec = { img: new Image(), ready: false, failed: false };
      rec.img.onload = () => {
        rec.ready = true;
      };
      rec.img.onerror = () => {
        rec.failed = true;
      };
      rec.img.src = SPRITE_BASE + key + ".png";
      SPR_CACHE[key] = rec;
    });
  }
  // Returns the decoded <img> for `key`, or null while loading/missing/failed
  // — every call site treats null as "use the matrix fallback for this bit".
  function spr(key) {
    const rec = SPR_CACHE[key];
    return rec && rec.ready ? rec.img : null;
  }
  function speciesSpritesReady(species) {
    return !!spr(species + "_idle");
  }

  // Offscreen-canvas tint cache: solid-recolors (HURT red flash, EVOLVING
  // white/accent flash) are expensive to redo every frame pixel-by-pixel, so
  // each (image, color) combination is rendered once via 'source-atop' and
  // reused for the lifetime of the HUD session.
  const TINT_CACHE = new Map();
  function tintedSprite(img, color) {
    const key = img.src + "|" + color;
    let c = TINT_CACHE.get(key);
    if (c) return c;
    c = document.createElement("canvas");
    c.width = img.naturalWidth;
    c.height = img.naturalHeight;
    const tctx = c.getContext("2d");
    tctx.drawImage(img, 0, 0);
    tctx.globalCompositeOperation = "source-atop";
    tctx.fillStyle = color;
    tctx.fillRect(0, 0, c.width, c.height);
    TINT_CACHE.set(key, c);
    return c;
  }
  // Draws `img` (or its tinted variant) at integer scale, bottom-anchored at
  // (cx, baseY) in the caller's current coordinate space. Height-driven
  // scale so callers control on-screen size without touching source pixels.
  function drawSpriteImg(ctx2, img, cx, baseY, targetH, { flip = false, tint = null, alpha = 1, filter = null } = {}) {
    const source = tint ? tintedSprite(img, tint) : img;
    const scale = targetH / img.naturalHeight;
    const w = Math.max(1, Math.round(img.naturalWidth * scale));
    const h = Math.max(1, Math.round(targetH));
    const x0 = Math.round(cx - w / 2);
    const y0 = Math.round(baseY - h);
    ctx2.save();
    ctx2.globalAlpha = alpha;
    ctx2.imageSmoothingEnabled = false;
    if (filter) ctx2.filter = filter;
    if (flip) {
      ctx2.translate(x0 + w, y0);
      ctx2.scale(-1, 1);
      ctx2.drawImage(source, 0, 0, w, h);
    } else {
      ctx2.drawImage(source, x0, y0, w, h);
    }
    ctx2.restore();
    return { x: x0, y: y0, w, h };
  }

  const ITEMS = [
    ["hat", "Classic Top Hat", "Cosmetic", 500, "Pet wears a tiny top hat"],
    ["shades", "Cyber Shades", "Cosmetic", 750, "Glowing pixel shades"],
    ["aura", "Neon Aura", "Cosmetic", 2500, "Neon glow behind the pet"],
    ["plant", "Desk Plant", "Arena decor", 300, "Cactus in the arena corner"],
    ["lamp", "Lava Lamp", "Arena decor", 800, "Animated lava lamp in the arena"],
    ["grid", "Synthwave Arena", "Arena skin", 1200, "Arena becomes a retro purple grid"],
    ["confetti", "Confetti Popper", "Consumable", 100, "Confetti rain on every K.O."],
    ["plasma", "Plasma Shot", "Attack FX", 1500, "Blue bolt -> pink plasma, bigger impact"],
    ["treat", "Digital Treat", "Consumable", 50, "Restores pet HP & mood"],
    ["tag", "Name Tag", "Utility", 1000, "Rename your pet"],
  ];

  // ---- runtime battle state (single instance — reflects whichever session is active) ----
  const G = {
    mode: "idle", frame: 0, t: 0,
    petX: 100, petLunge: 0, petHurt: 0, petHP: 100,
    enemy: null, enemyAttack: 0,
    projectiles: [], particles: [], dmg: [], booms: [],
    shake: 0, hitstop: 0, banner: null, evolving: 0, freeze: false,
    pendingPromptText: "", awaitingFirstBlock: false, toolRunsThisTurn: 0, lastChargeLabel: null,
    // ---- v2 sprite/journey-mode state ----
    scene: "journey", sceneAnim: null, // sceneAnim: { from, to, t } during the 0.4s slide
    lastActivityAt: Date.now(),
    journeyFarX: 0, journeyNearX: 0, journeyProps: [],
    blinkTimer: 90 + Math.floor(Math.random() * 40), blinkFrames: 0,
    celebrate: 0,
  };
  const JOURNEY_IDLE_MS = 8000; // no active turn for this long -> switch to journey scene
  const SLEEP_IDLE_MS = 120000; // additionally idle this long within journey -> pet naps in place
  const SCENE_TRANS_TICKS = 5; // 0.4s at the 80ms tick rate
  // Sprite draw heights (virtual-space units) chosen so PET_SPRITE_VH[mode] * ARENA_SCALE[mode]
  // lands exactly on 96 (1x the 96px-tall source art) in compact and 192 (2x) in expanded —
  // integer source-pixel multiples in both modes, not a hand-tuned px constant.
  const PET_SPRITE_VH = { compact: 160, expanded: 192 };
  const ENEMY_SPRITE_GROW = 1.15; // enemies read as bosses: a bit taller than the pet, matching the old matrix's PET_PX vs ENEMY_PX ratio
  const JOURNEY_PET_X = 260; // slightly left of the 640-wide arena's center (320) while walking in place
  function markActivity() {
    G.lastActivityAt = Date.now();
  }

  // Virtual arena geometry (640x200 units). draw() applies ctx.scale(arenaScale, ...)
  // per HUD mode (see ARENA_SCALE above), so every Y/size below is defined ONCE in this
  // virtual space and lands at the right physical size in both compact (120px) and
  // expanded (200px) HUD modes automatically — no separate compact/expanded numbers.
  const GROUND_Y = 180, BASE_Y = 178, PROJ_Y = 125, HIT_Y = 133, DMG_ENEMY_Y = 73, DMG_PET_Y = 80;
  const ARENA_H = 200; // virtual arena height (== expanded-mode physical px; compact scales this down by ARENA_SCALE.compact)
  // Target pet height as a fraction of the virtual arena so the pet reads ~170-190px
  // tall in the 200px expanded arena (and ~100-115px once ARENA_SCALE.compact shrinks
  // it) instead of a hand-picked px constant per stage.
  const PET_TARGET_H = Math.round(ARENA_H * 0.9); // 180
  const EGG_TARGET_H = Math.round(ARENA_H * 0.8); // 160 — egg reads slightly smaller than a full body
  const PET_PX = Math.floor(PET_TARGET_H / 28); // SPR32 is 28 rows tall -> 6
  const EGG_PX = Math.floor(EGG_TARGET_H / 28); // EGG is also 28 rows tall -> 5
  // Enemies (24x24, via up2()) scale up proportionally with the bigger pet — old
  // rookie was 20 rows @ px6 (120 virtual px tall); new rookie is 28 rows @ px6 (168),
  // a 1.4x grow factor also applied to the old enemy px (5.4) and to wing/aura geometry below.
  // Rounded to an integer (drawMat fillRects at fractional px blur on non-integer
  // device-pixel boundaries even with image-rendering:pixelated on the canvas).
  const PET_GROW = (28 * PET_PX) / (20 * 6); // 1.4 — new rookie height vs the old SPR24 rookie height
  const ARENA = {
    W: 640,
    H: ARENA_H,
    GROUND_Y, BASE_Y, PROJ_Y, HIT_Y, DMG_ENEMY_Y, DMG_PET_Y,
    PET_PX,
    EGG_PX,
    ENEMY_PX: Math.round(5.4 * PET_GROW), // 8
  };

  let save = null;
  let dom = {};
  let cv = null, ctx = null;
  let tickTimer = null;
  let selectedSpecies = "byte";
  let toastTimer = null;
  let hudMode = "compact";
  let arenaScale = ARENA_SCALE.compact;
  // Backing-store multiplier so canvas bitmaps match physical device pixels on
  // Windows display scaling (125%/150%) instead of the browser upscaling a
  // 1x buffer and blurring every sprite edge. CSS size (width:100%/fixed px)
  // never changes — only the internal draw-buffer resolution does.
  let dpr = Math.max(1, window.devicePixelRatio || 1);
  // Sizes canvas `el` to a dpr-scaled backing store while keeping its logical
  // (CSS-pixel) size at cssW x cssH — every non-arena HUD canvas (mini icon,
  // intro egg, picker cards) goes through this so drawMini() can keep drawing
  // in logical-pixel coordinates via the stored dataset size.
  function prepCrispCanvas(el, cssW, cssH) {
    if (!el) return;
    el.width = Math.round(cssW * dpr);
    el.height = Math.round(cssH * dpr);
    el.dataset.cssW = cssW;
    el.dataset.cssH = cssH;
  }

  function level() {
    return Math.floor(Math.pow(Math.max(0, save.xp) / 100, 0.8)) + 1;
  }

  function loadSave() {
    try {
      const raw = localStorage.getItem(SAVE_KEY);
      if (raw) return JSON.parse(raw);
    } catch (e) {}
    return null;
  }
  function persistSave() {
    try {
      localStorage.setItem(SAVE_KEY, JSON.stringify(save));
    } catch (e) {}
  }
  function todayLocalStr() {
    const d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function applyStreak() {
    const todayStr = todayLocalStr();
    if (save.lastActiveDate === todayStr) return;
    if (save.lastActiveDate) {
      const prev = new Date(save.lastActiveDate + "T00:00:00");
      const today = new Date(todayStr + "T00:00:00");
      const diffDays = Math.round((today - prev) / 86400000);
      if (diffDays === 1) save.streakDays = (save.streakDays || 0) + 1;
      else if (diffDays > 1) save.streakDays = 1;
      // diffDays <= 0 (clock skew) — leave as-is
    } else {
      save.streakDays = 1;
    }
    save.lastActiveDate = todayStr;
    persistSave();
  }
  function streakMultiplier() {
    return Math.min(1 + Math.max(0, (save.streakDays || 1) - 1) * 0.05, 1.5);
  }

  function escapeHtml(t) {
    const d = document.createElement("div");
    d.textContent = t;
    return d.innerHTML;
  }
  function say(t, cursor) {
    dom.questCopy.innerHTML = cursor ? '<span class="hud-cursor">' + escapeHtml(t) + "</span>" : escapeHtml(t);
    dom.miniQuest.textContent = t;
  }
  function toast(t) {
    dom.toast.textContent = "> " + t;
    dom.toast.classList.add("hud-show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => dom.toast.classList.remove("hud-show"), 1600);
  }

  // px is derived to fit whatever matrix stageSpec(sp, st) returns inside the
  // target canvas (with `pad` px of headroom) — the picker/intro/mini-icon canvases
  // no longer need per-call-site tuning when sprite matrix dimensions change (12x12
  // baby vs 32x28 rookie-and-up vs 32x28 egg all auto-fit correctly).
  //
  // `useSprite` (default true) tries the v2 PNG (idle frame — "picker shows idle
  // frames") first and only falls back to the matrix renderer if it isn't loaded;
  // the collapsed 20px mini-icon passes false because a tiny matrix glyph reads
  // more clearly than a heavily downscaled photoreal sprite at that size.
  function drawMini(cvm, sp, st, pad, useSprite) {
    const c2 = cvm.getContext("2d");
    // Draw in logical CSS-pixel space (the size the canvas was prepped at via
    // prepCrispCanvas) regardless of the dpr-scaled backing-store resolution —
    // setTransform both maps logical->device pixels and resets any transform
    // left over from a previous draw, so repeat calls never compound the scale.
    const cssW = Number(cvm.dataset.cssW) || cvm.width;
    const cssH = Number(cvm.dataset.cssH) || cvm.height;
    const localDpr = cvm.dataset.cssW ? cvm.width / cssW : 1;
    c2.setTransform(localDpr, 0, 0, localDpr, 0, 0);
    c2.clearRect(0, 0, cssW, cssH);
    const p = pad == null ? 4 : pad;
    if (useSprite !== false) {
      const img = st === 0 ? spr("egg_idle") : spr(sp + "_idle");
      if (img) {
        const availH = cssH - p, availW = cssW - p;
        const fit = Math.min(availH / img.naturalHeight, availW / img.naturalWidth);
        const scale = st === 1 ? fit * 0.5 : fit; // BABY: half scale until dedicated art
        const targetH = img.naturalHeight * scale;
        const pr = drawSpriteImg(c2, img, cssW / 2, cssH - 2, targetH);
        if (st >= 3) drawStageBadge(c2, pr.x + pr.w - 10, pr.y, st, PAL[sp]);
        return;
      }
    }
    // Fractional px (not floored to an integer) — these are small non-arena previews
    // (picker cards, intro egg, collapsed mini-icon) where sub-pixel scaling already
    // was the norm (e.g. the old mini-icon rendered at px 0.9), and flooring to an
    // integer here would either overflow a small canvas or under-fill a larger one.
    // The dpr-scaled backing store (prepCrispCanvas) is what keeps the edges crisp
    // now, not integer px.
    const spec = stageSpec(sp, st);
    const px = Math.max(0.4, Math.min((cssW - p) / spec.m[0].length, (cssH - p) / spec.m.length));
    drawMat(c2, spec.m, PAL[sp], cssW / 2, cssH - 2, px, false, null);
    if (spec.armor) drawMat(c2, ARMOR, PAL[sp], cssW / 2, cssH - 2, px, false, null);
  }
  function renderMiniIcon() {
    drawMini(dom.miniIcon, save.species, stageIdx(level()), null, false);
  }

  function updatePanels() {
    const lv = level(), st = stageIdx(lv);
    dom.petName.textContent = save.name;
    dom.petStage.textContent = STAGES[st] + " · " + save.species.toUpperCase();
    dom.petLv.textContent = "LVL " + lv;
    dom.petHP.style.width = G.petHP + "%";
    const nxt = st < 4 ? THRESH[st + 1] : null;
    dom.xpLbl.textContent = nxt ? "XP → " + STAGES[st + 1] + " @ L" + nxt : "XP · MAX STAGE";
    const cur = THRESH[st];
    dom.petXP.style.width = (nxt ? Math.min(100, Math.round(((lv - cur) / (nxt - cur)) * 100)) : 100) + "%";
    if (G.enemy && !G.enemy.dead) {
      dom.enemyPanel.style.visibility = "visible";
      dom.enemyName.textContent = G.enemy.name;
      dom.enemyHP.style.width = Math.round((G.enemy.hp / G.enemy.maxhp) * 100) + "%";
    } else {
      dom.enemyPanel.style.visibility = "hidden";
    }
    dom.gold.textContent = save.gold.toLocaleString();
    dom.shopGold.textContent = save.gold.toLocaleString();
    renderStreak();
    if (isCollapsed()) renderMiniIcon();
  }
  function renderStreak() {
    const d = save.streakDays || 1;
    dom.streak.textContent = d > 1 ? "🔥" + d + "d ×" + streakMultiplier().toFixed(2) : "—";
  }

  // ---- enemy keyword heuristic (email/inbox, bug/fix/error, report/doc/write, deadline/urgent/today) ----
  function pickEnemyIndexForPrompt(text) {
    const t = (text || "").toLowerCase();
    if (/\b(email|inbox|mail)\b/.test(t)) return 0;
    if (/\b(bug|fix|error|broken|crash)\b/.test(t)) return 1;
    if (/\b(report|doc|write|draft|document)\b/.test(t)) return 2;
    if (/\b(deadline|urgent|today|asap)\b/.test(t)) return 3;
    return Math.floor(Math.random() * ENEMIES.length);
  }

  // Journey <-> battle scene transition: a quest/turn starting slides the arena
  // from the journey backdrop into the battle backdrop over SCENE_TRANS_TICKS
  // (see draw()'s scene-background section); the reverse happens from the
  // idle watchdog in tick() once the fight is over and JOURNEY_IDLE_MS has
  // passed with no new activity.
  function enterBattleScene() {
    if (G.scene === "battle" && !G.sceneAnim) return;
    G.sceneAnim = { from: "journey", to: "battle", t: SCENE_TRANS_TICKS };
    G.scene = "battle";
  }

  function spawnForTurn(promptText) {
    const e = ENEMIES[pickEnemyIndexForPrompt(promptText)];
    G.enemy = { name: e[0], pal: e[1], m: e[2], spriteId: e[3], hp: 100, maxhp: 100, x: 780, slide: 1, dead: 0, flash: 0, kb: 0 };
    G.mode = "battle";
    G.freeze = false;
    setBlocked(false);
    enterBattleScene();
    markActivity();
    G.banner = { text: "A WILD " + e[0] + " APPEARED!", t: 26, color: "#DBEAFE" };
    G.lastChargeLabel = null;
    say("QUEST START: " + e[0] + " blocks the way");
    updatePanels();
  }

  function charge(kind) {
    if (!G.enemy || G.enemy.dead || G.freeze) return;
    G.mode = "charge";
    markActivity();
    const label = kind === "thinking" ? "CHARGING POWER... (thinking)" : "WRITING...";
    if (G.lastChargeLabel !== label) {
      G.lastChargeLabel = label;
      say(label, true);
    }
  }

  function attack(toolName) {
    if (!G.enemy || G.enemy.dead) spawnForTurn(G.pendingPromptText || "");
    G.mode = "battle";
    G.freeze = false;
    setBlocked(false);
    G.petLunge = 8;
    G.lastChargeLabel = null;
    markActivity();
    G.projectiles.push({ x: G.petX + 110, y: PROJ_Y, vx: 20, hit: false, plasma: !!save.owned.plasma });
    say("[" + (toolName || "TOOL") + "] — ATTACK!");
  }

  function enemyCounter() {
    if (!G.enemy || G.enemy.dead) return;
    G.mode = "battle";
    G.freeze = false;
    setBlocked(false);
    G.enemyAttack = 10;
    G.lastChargeLabel = null;
    markActivity();
    say("ERROR! " + G.enemy.name + " COUNTERATTACKS!");
  }

  function setBlocked(on) {
    dom.arenaWrap.classList.toggle("hud-blocked", !!on);
  }
  function freeze(on) {
    G.freeze = on;
    setBlocked(on);
    if (on) {
      G.banner = { text: "⌛ TIME STOP — NEEDS YOUR PERMISSION", t: 9999, color: "#C8902A" };
      say("!! TIME STOP: PERMISSION NEEDED !!", true);
    } else if (G.banner && G.banner.t > 9000) {
      G.banner = null;
    }
  }

  function boom(x, y, r, big) {
    G.booms.push({ x, y, r: 3, max: r, life: big ? 14 : 10 });
    for (let i = 0; i < (big ? 26 : 14); i++) {
      const a = (Math.PI * 2 * i) / (big ? 26 : 14);
      G.particles.push({ x, y, vx: Math.cos(a) * (big ? 3.4 : 2.3), vy: Math.sin(a) * (big ? 3.4 : 2.3) - 0.7, c: i % 3 ? "#DBEAFE" : "#3B82F6", life: big ? 20 : 14, coin: false });
    }
  }

  function victory({ toolRuns = 0, xpBase = 10, costUsd = 0, tokens = 0 } = {}) {
    const e = G.enemy;
    if (e && !e.dead) {
      e.hp = 0;
      e.dead = 1;
      e.flash = 12;
      boom(e.x, 127, 32, 1);
      G.shake = 10;
      G.hitstop = 3;
      for (let i = 0; i < 26; i++) {
        G.particles.push({ x: e.x, y: 120, vx: Math.random() * 9 - 4.5, vy: -(Math.random() * 7 + 2), c: ["#C8902A", "#3B82F6", "#10B981", "#DBEAFE"][i % 4], life: 28, coin: i < 12 });
      }
      if (save.owned.confetti) {
        for (let i = 0; i < 30; i++) {
          G.particles.push({ x: Math.random() * 640, y: -6, vx: Math.random() * 2 - 1, vy: Math.random() * 3 + 1, c: ["#f472b6", "#C8902A", "#3B82F6", "#10B981"][i % 4], life: 40, coin: false });
        }
      }
    }
    const mult = streakMultiplier();
    // Real reward: $0.01 turn cost = 10 gold; if cost is unavailable, fall back to tokens/100.
    let gold = costUsd > 0 ? costUsd * 1000 : tokens / 100;
    gold = Math.max(1, Math.round(gold * mult));
    const xp = Math.round((xpBase + toolRuns * 5) * mult);
    const before = stageIdx(level());
    save.xp += xp;
    save.gold += gold;
    G.petHP = 100;
    persistSave();
    G.banner = { text: "★ VICTORY! +" + xp + " XP · +" + gold + " GOLD ★", t: 40, color: "#10B981" };
    G.lastChargeLabel = null;
    G.celebrate = 34; // CELEBRATE anim: idle-hop + star particles for ~2.7s
    markActivity(); // the JOURNEY_IDLE_MS watchdog in tick() sends the scene back once this settles
    for (let i = 0; i < 10; i++) {
      G.particles.push({ x: G.petX + (Math.random() * 40 - 20), y: BASE_Y - 90 - Math.random() * 20, vx: Math.random() * 0.6 - 0.3, vy: -0.6 - Math.random() * 0.4, c: "#FDE68A", life: 30 + Math.floor(Math.random() * 10), coin: false, star: true });
    }
    say((e ? e.name + " K.O! " : "") + "QUEST COMPLETE");
    if (stageIdx(level()) > before) setTimeout(evolveSeq, 1100);
    updatePanels();
  }

  function evolveSeq() {
    G.evolving = 18;
    G.banner = { text: "▲ EVOLVING...", t: 18, color: "#DBEAFE" };
    setTimeout(() => {
      G.banner = { text: "★ EVOLVED INTO " + STAGES[stageIdx(level())] + "! ★", t: 36, color: "#C8902A" };
      boom(G.petX, 74, 20, 0);
      updatePanels();
    }, 18 * 80);
  }

  function sessionExited() {
    G.freeze = false;
    setBlocked(false);
    dom.arenaWrap.classList.add("hud-dimmed");
    G.banner = { text: "HERO HAS LEFT THE REALM", t: 9999, color: "#7c93c4" };
    say("SESSION ENDED", true);
  }
  function sessionLive() {
    dom.arenaWrap.classList.remove("hud-dimmed");
    if (G.banner && G.banner.text === "HERO HAS LEFT THE REALM") G.banner = null;
  }

  // ---- loop ----
  function tick() {
    G.t++;
    if (G.t % 4 === 0) G.frame++;
    if (G.hitstop > 0) {
      G.hitstop--;
      draw(true);
      return;
    }
    if (!G.freeze) {
      if (G.petLunge > 0) G.petLunge--;
      if (G.petHurt > 0) G.petHurt--;
      if (G.shake > 0) G.shake--;
      if (G.evolving > 0) G.evolving--;
      if (G.enemy && !G.enemy.dead && G.enemy.slide) {
        G.enemy.x -= 18;
        if (G.enemy.x <= 490) {
          G.enemy.x = 490;
          G.enemy.slide = 0;
          updatePanels();
        }
      }
      if (G.enemy && G.enemy.kb > 0) {
        G.enemy.kb--;
        G.enemy.x = 490 + G.enemy.kb * 4;
      }
      if (G.enemyAttack > 0) {
        G.enemyAttack--;
        if (G.enemy && !G.enemy.dead) {
          const p = G.enemyAttack;
          G.enemy.x = p > 5 ? 490 - (10 - p) * 30 : 490 - p * 30;
          if (p === 5) {
            G.petHurt = 8;
            G.petHP = Math.max(10, G.petHP - 15);
            G.shake = 7;
            G.hitstop = 2;
            boom(G.petX + 70, HIT_Y, 20, 0);
            G.dmg.push({ x: G.petX, y: DMG_PET_Y, t: "-15", c: "#EF4444", life: 22, big: 1 });
            updatePanels();
          }
          if (p === 0) G.enemy.x = 490;
        }
      }
      G.projectiles.forEach((p) => {
        p.x += p.vx;
        G.particles.push({ x: p.x - 14, y: PROJ_Y + Math.random() * 8 - 4, vx: -1.5, vy: 0, c: p.plasma ? "#f472b6" : "#3B82F6", life: 7, coin: false });
        if (G.enemy && !G.enemy.dead && !p.hit && p.x >= G.enemy.x - 80) {
          p.hit = true;
          const crit = Math.random() < 0.3, d = (crit ? 20 : 10) + Math.floor(Math.random() * 8);
          G.enemy.hp = Math.max(4, G.enemy.hp - d);
          G.enemy.flash = 5;
          G.enemy.kb = 5;
          G.shake = crit ? 9 : 6;
          G.hitstop = crit ? 3 : 2;
          boom(G.enemy.x - 40, HIT_Y, crit ? 25 : 17, crit ? 1 : 0);
          G.dmg.push({ x: G.enemy.x - 60, y: DMG_ENEMY_Y, t: (crit ? "CRIT! -" : "-") + d, c: crit ? "#C8902A" : "#3B82F6", life: 24, big: crit });
          updatePanels();
        }
      });
      G.projectiles = G.projectiles.filter((p) => !p.hit && p.x < 680);
      G.particles.forEach((p) => {
        if (p.coin && p.life < 14) {
          p.x += (30 - p.x) * 0.25;
          p.y += (20 - p.y) * 0.25;
        } else {
          p.x += p.vx;
          p.y += p.vy;
          p.vy += 0.28;
        }
        p.life--;
      });
      G.particles = G.particles.filter((p) => p.life > 0);
      G.booms.forEach((b) => {
        b.r += Math.ceil((b.max - b.r) * 0.4);
        b.life--;
      });
      G.booms = G.booms.filter((b) => b.life > 0);
      G.dmg.forEach((d) => {
        d.y -= 1;
        d.life--;
      });
      G.dmg = G.dmg.filter((d) => d.life > 0);
      if (G.enemy && G.enemy.flash > 0) G.enemy.flash--;
      if (G.banner && G.banner.t < 9000) {
        G.banner.t--;
        if (G.banner.t <= 0) G.banner = null;
      }
      if (G.celebrate > 0) G.celebrate--;
      tickScene();
      tickBlink();
    }
    draw(false);
  }

  // ---- journey <-> battle scene machine + parallax/props (see enterBattleScene()) ----
  function tickScene() {
    if (G.sceneAnim) {
      G.sceneAnim.t--;
      if (G.sceneAnim.t <= 0) G.sceneAnim = null;
    }
    // Battle -> journey watchdog: only once the fight is actually over (no live
    // enemy) and nothing has happened for JOURNEY_IDLE_MS — never yanks the
    // backdrop out from under a live enemy or a time-stop permission prompt.
    if (G.scene === "battle" && !G.sceneAnim && (!G.enemy || G.enemy.dead) && !G.freeze && Date.now() - G.lastActivityAt > JOURNEY_IDLE_MS) {
      G.scene = "journey";
      G.sceneAnim = { from: "battle", to: "journey", t: SCENE_TRANS_TICKS };
      G.enemy = null;
    }
    if (G.scene !== "journey") return;
    // Two-layer parallax per spec: the bg plate itself drifts as the far layer,
    // a cropped ground strip (see drawJourneyGround()) scrolls 5x faster as the near layer.
    G.journeyFarX += 0.2;
    G.journeyNearX += 1;
    // Occasional distant, non-interactive props — reuse enemy silhouettes, tinted dark.
    if (G.t % 47 === 0 && Math.random() < 0.3 && G.journeyProps.length < 2) {
      const e = ENEMIES[Math.floor(Math.random() * ENEMIES.length)];
      G.journeyProps.push({ x: 680, y: BASE_Y - 6, spriteId: e[3], m: e[2], pal: e[1] });
    }
    G.journeyProps.forEach((p) => (p.x -= 1));
    G.journeyProps = G.journeyProps.filter((p) => p.x > -60);
  }
  function tickBlink() {
    if (G.blinkFrames > 0) {
      G.blinkFrames--;
      return;
    }
    G.blinkTimer--;
    if (G.blinkTimer <= 0) {
      G.blinkFrames = 2; // ~160ms brief dip
      G.blinkTimer = 60 + Math.floor(Math.random() * 70); // next blink in ~5-10.5s
    }
  }

  // Arena background/floor/starfield/banner-backdrop per named app theme — sprite
  // outlines are already dark navy (PAL[x][0]) so they stay readable everywhere;
  // "gameboy" additionally gets a CSS filter on the canvas itself (styles.css)
  // rather than a themePalette entry, so its sprites go through the same
  // 4-shade DMG tint as the environment.
  const THEME_ARENA_PALETTES = {
    light: { sky: "#e4e9f2", star: "rgba(59,130,246,.16)", ground: "#c7cedb", groundLine: "#94a3b8", banner: "rgba(6,15,36,.78)" },
    dark: { sky: "#0B1B3A", star: "rgba(59,130,246,.12)", ground: "#081227", groundLine: "#1E3A8A", banner: "rgba(6,15,36,.78)" },
    matrix: { sky: "#000000", star: "rgba(0,255,65,.25)", ground: "#001a00", groundLine: "#00ff41", banner: "rgba(0,15,0,.85)" },
    synthwave: { sky: "#2b1055", star: "rgba(255,45,149,.25)", ground: "#1a0b2e", groundLine: "#ff2d95", banner: "rgba(20,8,35,.85)" },
    gameboy: { sky: "#9bbc0f", star: "rgba(15,56,15,.25)", ground: "#306230", groundLine: "#0f380f", banner: "rgba(15,56,15,.85)" },
    dracula: { sky: "#282a36", star: "rgba(189,147,249,.18)", ground: "#21222c", groundLine: "#6272a4", banner: "rgba(33,34,44,.85)" },
    nord: { sky: "#2e3440", star: "rgba(136,192,208,.18)", ground: "#272c36", groundLine: "#5e81ac", banner: "rgba(30,34,42,.85)" },
    paper: { sky: "#eef1f7", star: "rgba(37,99,235,.14)", ground: "#dfe6f0", groundLine: "#94a3b8", banner: "rgba(38,36,29,.75)" },
    "midnight-gold": { sky: "#0a0a0f", star: "rgba(212,175,55,.18)", ground: "#060609", groundLine: "#d4af37", banner: "rgba(10,10,15,.85)" },
    "psb-rgb": { sky: "#070d1f", star: "rgba(167,139,250,.2)", ground: "#14275a", groundLine: "#60a5fa", banner: "rgba(7,13,31,.85)" },
  };
  function themePalette() {
    const theme = document.documentElement.dataset.theme;
    return THEME_ARENA_PALETTES[theme] || THEME_ARENA_PALETTES.dark;
  }

  // ---- v2 sprite-scene helpers (background plates, journey parallax, badges) ----
  function petSpriteTargetVH(stage) {
    const base = PET_SPRITE_VH[hudMode] || PET_SPRITE_VH.expanded;
    return stage === 1 ? Math.round(base / 2) : base; // BABY: half scale, no dedicated art yet
  }
  function enemySpriteTargetVH() {
    const base = PET_SPRITE_VH[hudMode] || PET_SPRITE_VH.expanded;
    return Math.round(base * ENEMY_SPRITE_GROW);
  }
  // "cover"-fits `img` into a W x H rect at horizontal pan `panX`, biased to show
  // ground over sky when the aspect ratio forces a vertical crop.
  function drawCoverLayer(img, panX, W, H) {
    const scale = Math.max(W / img.naturalWidth, H / img.naturalHeight);
    const dw = img.naturalWidth * scale, dh = img.naturalHeight * scale;
    ctx.drawImage(img, (W - dw) / 2 + panX, H - dh, dw, dh);
  }
  // Bottom-strip crop of the journey plate, tiled and scrolled 5x faster than the
  // far layer (1px/tick vs 0.2px/tick) — the "near ground strip" from the spec.
  function drawJourneyGround(jImg, tpal) {
    const W = 640, bandH = 34, bandY = 200 - bandH;
    const scale = Math.max(W / jImg.naturalWidth, 200 / jImg.naturalHeight);
    const stripSrcH = Math.max(1, Math.round(bandH / scale));
    const srcY = Math.max(0, jImg.naturalHeight - stripSrcH - 4);
    const tileW = 160;
    const nearX = -(G.journeyNearX % tileW);
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, bandY, W, bandH);
    ctx.clip();
    for (let x = nearX - tileW; x < W + tileW; x += tileW) {
      ctx.drawImage(jImg, 0, srcY, jImg.naturalWidth, stripSrcH, x, bandY, tileW, bandH);
    }
    ctx.fillStyle = tpal.groundLine;
    ctx.fillRect(0, bandY, W, 2);
    ctx.restore();
  }
  // Slow (~72s) dawn -> day -> dusk -> night wash over the journey scene.
  const DAY_TINT_CYCLE_TICKS = 900;
  const DAY_TINT_STOPS = [
    { at: 0, c: [255, 244, 214] },
    { at: 0.25, c: [255, 255, 255] },
    { at: 0.55, c: [255, 176, 120] },
    { at: 0.8, c: [70, 80, 140] },
    { at: 1, c: [255, 244, 214] },
  ];
  function drawDayTint() {
    const phase = (G.t % DAY_TINT_CYCLE_TICKS) / DAY_TINT_CYCLE_TICKS;
    let a = DAY_TINT_STOPS[0], b = DAY_TINT_STOPS[DAY_TINT_STOPS.length - 1];
    for (let i = 0; i < DAY_TINT_STOPS.length - 1; i++) {
      if (phase >= DAY_TINT_STOPS[i].at && phase <= DAY_TINT_STOPS[i + 1].at) {
        a = DAY_TINT_STOPS[i];
        b = DAY_TINT_STOPS[i + 1];
        break;
      }
    }
    const span = b.at - a.at || 1;
    const f = (phase - a.at) / span;
    const c = a.c.map((v, i2) => Math.round(v + (b.c[i2] - v) * f));
    ctx.fillStyle = "rgba(" + c[0] + "," + c[1] + "," + c[2] + ",0.1)";
    ctx.fillRect(0, 0, 640, 200);
  }
  // Draws whichever scene plate(s) the current scene/sceneAnim need; returns
  // false (drawing nothing) when a needed plate isn't loaded yet, so draw()
  // falls back to the legacy theme-colored sky/ground fill.
  function drawSceneBackground(tpal) {
    const jImg = spr("bg_journey"), bImg = spr("bg_battle");
    const needsJourney = G.scene === "journey" || (G.sceneAnim && (G.sceneAnim.from === "journey" || G.sceneAnim.to === "journey"));
    const needsBattle = G.scene === "battle" || (G.sceneAnim && (G.sceneAnim.from === "battle" || G.sceneAnim.to === "battle"));
    if ((needsJourney && !jImg) || (needsBattle && !bImg)) return false;
    const W = 640, H = 200;
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, W, H);
    ctx.clip();
    if (G.sceneAnim) {
      const prog = 1 - G.sceneAnim.t / SCENE_TRANS_TICKS;
      const fromImg = G.sceneAnim.from === "journey" ? jImg : bImg;
      const toImg = G.sceneAnim.to === "journey" ? jImg : bImg;
      const slide = prog * W;
      drawCoverLayer(fromImg, -slide, W, H);
      drawCoverLayer(toImg, W - slide, W, H);
    } else if (G.scene === "journey") {
      const scale = Math.max(W / jImg.naturalWidth, H / jImg.naturalHeight);
      const dw = jImg.naturalWidth * scale;
      const farX = -(G.journeyFarX % dw);
      drawCoverLayer(jImg, farX, W, H);
      drawCoverLayer(jImg, farX + dw, W, H); // second copy covers the wrap seam
      drawJourneyGround(jImg, tpal);
      drawDayTint();
    } else {
      drawCoverLayer(bImg, 0, W, H);
    }
    ctx.restore();
    return true;
  }
  function drawStageBadge(ctx2, cx, topY, stage, pal) {
    if (stage < 3) return;
    const short = stage === 4 ? "★ ULT" : "◆ CH";
    ctx2.save();
    ctx2.font = "11px VT323, monospace";
    const w = ctx2.measureText(short).width + 10;
    const bx = cx + 6, by = topY - 2;
    ctx2.fillStyle = "rgba(6,15,36,.82)";
    ctx2.fillRect(bx, by, w, 14);
    ctx2.strokeStyle = pal[3];
    ctx2.lineWidth = 1;
    ctx2.strokeRect(bx + 0.5, by + 0.5, w - 1, 13);
    ctx2.fillStyle = pal[3];
    ctx2.fillText(short, bx + 5, by + 11);
    ctx2.restore();
  }

  function draw(frozen) {
    ctx.clearRect(0, 0, cv.width, cv.height);
    const sx = G.shake ? Math.random() * 7 - 3.5 : 0, sy = G.shake ? Math.random() * 5 - 2.5 : 0;
    const tpal = themePalette();
    ctx.save();
    // Everything below draws in a fixed 640x200 virtual coordinate space; scaling the
    // context (rather than rewriting the ~300 lines of hardcoded geometry below) is what
    // lets compact/expanded HUD modes shrink the whole arena — sprites included —
    // proportionally instead of CSS-squishing a fixed-resolution bitmap.
    ctx.scale(arenaScale * dpr, arenaScale * dpr);
    ctx.translate(sx, sy);

    // "Synthwave Arena" cosmetic keeps replacing the whole backdrop, same as before;
    // otherwise try the v2 photographic scene plates and fall back to the legacy
    // theme-colored sky/ground fill if the plate(s) the current scene needs aren't
    // loaded yet (or failed/missing — matrix-era look, never a blank arena).
    const usingSceneArt = !save.owned.grid && drawSceneBackground(tpal);
    if (!usingSceneArt) {
      if (save.owned.grid) {
        ctx.fillStyle = "#160b2e";
        ctx.fillRect(-8, -8, 656, 216);
        ctx.strokeStyle = "rgba(139,92,246,.3)";
        ctx.lineWidth = 1;
        for (let x = 0; x <= 640; x += 40) {
          ctx.beginPath();
          ctx.moveTo(x, 100);
          ctx.lineTo((x - 320) * 2 + 320, 200);
          ctx.stroke();
        }
        for (let y = 100; y <= 200; y += 14) {
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(640, y);
          ctx.stroke();
        }
      } else {
        ctx.fillStyle = tpal.sky;
        ctx.fillRect(-8, -8, 656, 216);
        ctx.fillStyle = tpal.star;
        for (let i = 0; i < 24; i++) ctx.fillRect((i * 97 + G.t) % 640, (i * 37) % 94 + 4, 3, 3);
      }
      ctx.fillStyle = tpal.ground;
      ctx.fillRect(-8, GROUND_Y, 656, 28);
      ctx.fillStyle = tpal.groundLine;
      ctx.fillRect(-8, GROUND_Y - 2, 656, 2);
    }
    if (save.owned.plant) {
      ctx.fillStyle = "#10B981";
      ctx.fillRect(34, 162, 5, 15);
      ctx.fillRect(28, 155, 5, 8);
      ctx.fillRect(44, 155, 5, 8);
      ctx.fillStyle = "#92400e";
      ctx.fillRect(28, 177, 26, 8);
    }
    if (save.owned.lamp) {
      ctx.fillStyle = "#7c3aed";
      ctx.fillRect(596, 145, 10, 33);
      ctx.fillStyle = G.frame % 2 ? "#f472b6" : "#fb923c";
      ctx.fillRect(598, 152 + (G.frame % 2 ? 4 : 10), 6, 8);
    }

    const inJourney = usingSceneArt && G.scene === "journey";
    if (inJourney) {
      // Distant, non-interactive scenery: reused enemy silhouettes, tinted dark,
      // drawn behind the pet — purely decorative, no collision/interaction.
      G.journeyProps.forEach((p) => {
        const simg = spr("enemy_" + p.spriteId);
        if (simg) drawSpriteImg(ctx, simg, p.x, p.y, Math.round(enemySpriteTargetVH() * 0.55), { tint: "#0b1330", alpha: 0.4 });
        else drawMat(ctx, p.m, p.pal, p.x, p.y, Math.round(ARENA.ENEMY_PX * 0.55), true, "#0b1330", 0.4);
      });
    }

    const st = stageIdx(level());
    const spec = G.evolving ? stageSpec(save.species, G.frame % 2 ? st : Math.max(0, st - 1)) : stageSpec(save.species, st);
    const pal = PAL[save.species];
    const bob = G.freeze || frozen ? 0 : G.frame % 2 ? 0 : -2;
    const petCX = inJourney ? JOURNEY_PET_X : G.petX + (G.petLunge > 4 ? (9 - G.petLunge) * 22 : G.petLunge > 0 ? G.petLunge * 8 : 0);
    let tint = null;
    if (G.evolving) tint = G.frame % 2 ? "#ffffff" : pal[4];
    else if (G.petHurt > 0 && G.frame % 2) tint = "#EF4444";

    // Wing/aura points were authored against the old (shorter) SPR24 rookie. Scale
    // both their y-offset from BASE_Y and their x-offset from petCX by PET_GROW so they
    // stay proportioned to the taller SPR32 body instead of clipping into/under it.
    // Kept for both the matrix AND sprite pet paths — they draw as vector shapes
    // behind the pet either way, so they read fine over photoreal art too.
    const wy = (v) => BASE_Y + (v - BASE_Y) * PET_GROW;
    const wx = (dx) => dx * PET_GROW;
    if (spec.wings) {
      ctx.save();
      ctx.globalAlpha = 0.8;
      ctx.fillStyle = pal[4];
      const fl = (G.frame % 2 ? 7 : 0) * PET_GROW;
      ctx.beginPath();
      ctx.moveTo(petCX - wx(16), wy(80));
      ctx.lineTo(petCX - wx(78), wy(-4) - fl);
      ctx.lineTo(petCX - wx(64), wy(80));
      ctx.lineTo(petCX - wx(92), wy(108) - fl);
      ctx.lineTo(petCX - wx(15), wy(126));
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(petCX + wx(16), wy(80));
      ctx.lineTo(petCX + wx(78), wy(-4) - fl);
      ctx.lineTo(petCX + wx(64), wy(80));
      ctx.lineTo(petCX + wx(92), wy(108) - fl);
      ctx.lineTo(petCX + wx(15), wy(126));
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }
    if (spec.aura || save.owned.aura) {
      ctx.save();
      ctx.globalAlpha = 0.28 + (G.frame % 2 ? 0.08 : 0);
      ctx.fillStyle = pal[4];
      ctx.beginPath();
      ctx.arc(petCX, wy(98), 58 * PET_GROW, 0, 7);
      ctx.fill();
      ctx.restore();
    }

    // ---- pet: sprite path (with per-species fallback to the matrix renderer) ----
    const usingPetSprite = st >= 1 && speciesSpritesReady(save.species);
    const asleep = inJourney && !G.freeze && Date.now() - G.lastActivityAt > SLEEP_IDLE_MS;
    let pr;
    if (st === 0) {
      const eggImg = spr("egg_idle");
      pr = eggImg ? drawSpriteImg(ctx, eggImg, petCX, BASE_Y + bob, petSpriteTargetVH(0), { tint }) : drawMat(ctx, spec.m, pal, petCX, BASE_Y + bob, spec.px, false, tint);
    } else if (usingPetSprite) {
      let animState = "idle";
      let poseBob = bob;
      let filter = null;
      if (G.petLunge > 0 && spr(save.species + "_attack")) {
        animState = "attack";
      } else if (asleep) {
        filter = "brightness(0.55)";
      } else if (inJourney && spr(save.species + "_walk") && Math.floor((G.t * 80) / 260) % 2) {
        animState = "walk";
      } else if (G.celebrate > 0) {
        poseBob = bob - (G.frame % 2 ? 10 : 4); // CELEBRATE: idle frame hopping
      }
      if (!filter && !tint && G.blinkFrames > 0) filter = "brightness(0.95)"; // occasional blink dip
      const img = spr(save.species + "_" + animState) || spr(save.species + "_idle");
      const targetVH = petSpriteTargetVH(st === 1 ? 1 : 2);
      if (G.petLunge > 0) {
        // ATTACK afterimage trail: fixed fading ghosts behind the lunge, no extra state needed.
        [24, 16, 8].forEach((d, i) => drawSpriteImg(ctx, img, petCX - d, BASE_Y + poseBob, targetVH, { alpha: 0.1 + i * 0.06 }));
      }
      pr = drawSpriteImg(ctx, img, petCX, BASE_Y + poseBob, targetVH, { tint, filter });
      if (st >= 3) drawStageBadge(ctx, pr.x + pr.w, pr.y, st, pal);
      if (asleep) {
        ctx.save();
        ctx.font = "13px VT323, monospace";
        ctx.fillStyle = "rgba(219,234,254,.85)";
        for (let i = 0; i < 3; i++) {
          const phase = (G.t + i * 24) % 90;
          ctx.globalAlpha = Math.max(0, 1 - phase / 90);
          ctx.fillText("z", petCX + 22 + i * 5, pr.y - phase * 0.6);
        }
        ctx.restore();
      }
    } else {
      pr = drawMat(ctx, spec.m, pal, petCX, BASE_Y + bob, spec.px, false, tint);
      if (spec.armor && !tint) drawMat(ctx, ARMOR, pal, petCX, BASE_Y + bob, spec.px, false, null);
    }
    if (save.owned.hat) {
      ctx.fillStyle = "#111827";
      ctx.fillRect(petCX - 14, pr.y - 8 + bob, 28, 6);
      ctx.fillRect(petCX - 8, pr.y - 19 + bob, 16, 12);
      ctx.fillStyle = "#C8902A";
      ctx.fillRect(petCX - 8, pr.y - 11 + bob, 16, 3);
    }
    if (save.owned.shades) {
      ctx.fillStyle = "#0ff";
      ctx.fillRect(pr.x + 9, pr.y + Math.round(pr.h * 0.3), pr.w - 18, 5);
    }
    if (G.mode === "charge" && !G.freeze) {
      ctx.fillStyle = G.frame % 2 ? "#DBEAFE" : "#3B82F6";
      for (let i = 0; i < 7; i++) ctx.fillRect(petCX - 40 + ((G.t * 5 + i * 23) % 80), 53 + ((i * 21 + G.t * 4) % 74), 4, 4);
    }

    if (G.enemy && !inJourney) {
      const e = G.enemy;
      let et = null;
      if (e.flash > 0 && G.frame % 2) et = "#ffffff";
      if (e.dead) et = G.frame % 2 ? "#ffffff" : null;
      const ea = e.dead ? Math.max(0, e.flash / 12) : 1;
      const eimg = spr("enemy_" + e.spriteId);
      if (eimg) drawSpriteImg(ctx, eimg, e.x, BASE_Y + (G.frame % 2 ? 0 : -2), enemySpriteTargetVH(), { tint: et, alpha: ea });
      else drawMat(ctx, e.m, e.pal, e.x, BASE_Y + (G.frame % 2 ? 0 : -2), ARENA.ENEMY_PX, true, et, ea);
    }
    // Projectile/impact FX scale up a notch to match the taller v2 sprites (spec #5).
    const fxScale = usingPetSprite ? 1.18 : 1;
    G.projectiles.forEach((p) => {
      const c1 = p.plasma ? "#f472b6" : "#3B82F6", c2 = p.plasma ? "#fbcfe8" : "#DBEAFE";
      ctx.fillStyle = c1;
      ctx.fillRect(p.x - 19 * fxScale, PROJ_Y + 2, 35 * fxScale, 13 * fxScale);
      ctx.fillRect(p.x - 11 * fxScale, PROJ_Y - 4, 22 * fxScale, 24 * fxScale);
      ctx.fillStyle = c2;
      ctx.fillRect(p.x - 3 * fxScale, PROJ_Y + 2, 16 * fxScale, 13 * fxScale);
      ctx.fillRect(p.x + 5 * fxScale, PROJ_Y - 1, 11 * fxScale, 19 * fxScale);
    });
    G.booms.forEach((b) => {
      ctx.save();
      ctx.globalAlpha = Math.max(0.15, b.life / 14);
      ctx.strokeStyle = "#DBEAFE";
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r * fxScale, 0, 7);
      ctx.stroke();
      ctx.strokeStyle = "#3B82F6";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r * 0.6 * fxScale, 0, 7);
      ctx.stroke();
      ctx.restore();
    });
    G.particles.forEach((p) => {
      if (p.star) {
        ctx.save();
        ctx.globalAlpha = Math.max(0.15, p.life / 30);
        ctx.fillStyle = p.c;
        ctx.fillRect(p.x - 1, p.y - 4, 2, 8);
        ctx.fillRect(p.x - 4, p.y - 1, 8, 2);
        ctx.fillRect(p.x - 3, p.y - 3, 1, 1);
        ctx.fillRect(p.x + 2, p.y - 3, 1, 1);
        ctx.fillRect(p.x - 3, p.y + 2, 1, 1);
        ctx.fillRect(p.x + 2, p.y + 2, 1, 1);
        ctx.restore();
      } else if (p.coin) {
        ctx.fillStyle = "#C8902A";
        ctx.fillRect(p.x, p.y, 7, 7);
        ctx.fillStyle = "#ffd76a";
        ctx.fillRect(p.x + 1.5, p.y + 1.5, 3, 3);
      } else {
        ctx.fillStyle = p.c;
        ctx.fillRect(p.x, p.y, 4, 4);
      }
    });
    G.dmg.forEach((d) => {
      ctx.font = Math.round((d.big ? 26 : 19) * fxScale) + "px VT323, monospace";
      ctx.fillStyle = d.c;
      ctx.strokeStyle = "rgba(6,15,36,.9)";
      ctx.lineWidth = 3;
      ctx.strokeText(d.t, d.x, d.y);
      ctx.fillText(d.t, d.x, d.y);
    });
    if (G.banner) {
      ctx.font = "17px VT323, monospace";
      const w = ctx.measureText(G.banner.text).width;
      ctx.fillStyle = tpal.banner;
      ctx.fillRect(320 - w / 2 - 10, 14, w + 20, 22);
      ctx.fillStyle = G.banner.color;
      ctx.fillText(G.banner.text, 320 - w / 2, 30);
    }
    if (G.freeze) {
      ctx.fillStyle = "rgba(200,144,42,.08)";
      ctx.fillRect(-8, -8, 656, 216);
    }
    if (G.hitstop) {
      ctx.fillStyle = "rgba(255,255,255,.10)";
      ctx.fillRect(-8, -8, 656, 216);
    }
    ctx.restore();
  }

  // ---- compact / expanded / collapsed cycle + visibility-gated loop ----
  // Cycle: compact (default, 120px arena) -> expanded (200px, full mock sizing) ->
  // collapsed (slim icon bar, existing behavior) -> back to compact.
  function isCollapsed() {
    return hudMode === "collapsed";
  }
  function nextMode(m) {
    return m === "compact" ? "expanded" : m === "expanded" ? "collapsed" : "compact";
  }
  function applyMode(mode) {
    hudMode = mode;
    const collapsed = mode === "collapsed";
    dom.full.classList.toggle("hidden", collapsed);
    dom.collapsed.classList.toggle("hidden", !collapsed);
    dom.bar.dataset.hudMode = mode;
    if (!collapsed) {
      arenaScale = ARENA_SCALE[mode] || 1;
      if (cv) {
        cv.width = Math.round(640 * arenaScale * dpr);
        cv.height = Math.round(200 * arenaScale * dpr);
      }
    }
    dom.collapseBtn.textContent = MODE_GLYPH[mode];
    dom.collapseBtn.title = MODE_TITLE[mode];
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch (e) {}
    if (collapsed) renderMiniIcon();
    syncLoop();
  }
  function syncLoop() {
    const shouldRun = !isCollapsed() && document.visibilityState === "visible";
    if (shouldRun && !tickTimer) tickTimer = setInterval(tick, 80);
    else if (!shouldRun && tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
  }

  // ---- pet intro (first HUD appearance, dismissible — never blocks chat) ----
  // 3 panels anchored to the HUD: (a) what the pet is, (b) how it grows (real work =
  // XP/gold), (c) hands off into the existing species/name picker. Reopenable any time
  // via the "?" button next to the shop button.
  let introStep = 0;
  function renderIntroStep() {
    dom.introSteps.forEach((el2) => el2.classList.toggle("hidden", Number(el2.dataset.step) !== introStep));
    dom.introDots.forEach((el2) => el2.classList.toggle("is-active", Number(el2.dataset.dot) === introStep));
    dom.introNextBtn.textContent = introStep === dom.introSteps.length - 1 ? "Pick partner" : "Next";
    if (introStep === 0) drawMini(dom.introEggCanvas, "byte", 0);
  }
  function markIntroSeen() {
    try {
      localStorage.setItem(INTRO_KEY, "1");
    } catch (e) {}
  }
  function openIntro() {
    introStep = 0;
    renderIntroStep();
    dom.introOverlay.classList.remove("hidden");
  }
  function closeIntro() {
    dom.introOverlay.classList.add("hidden");
    markIntroSeen();
  }
  function introAdvance() {
    if (introStep < dom.introSteps.length - 1) {
      introStep++;
      renderIntroStep();
      return;
    }
    closeIntro();
    openPicker();
  }

  // ---- pet picker (first run, dismissible — never blocks chat) ----
  function openPicker() {
    selectedSpecies = save.species || "byte";
    dom.pickerGrid.innerHTML = "";
    SPECIES.forEach(([id, nm, th]) => {
      const d = document.createElement("div");
      d.className = "hud-pcard" + (id === selectedSpecies ? " hud-sel" : "");
      d.innerHTML = '<canvas width="112" height="96"></canvas><div class="hud-nm">' + nm + '</div><div class="hud-th">' + th + "</div>";
      d.addEventListener("click", () => {
        selectedSpecies = id;
        dom.pickerGrid.querySelectorAll(".hud-pcard").forEach((p) => p.classList.remove("hud-sel"));
        d.classList.add("hud-sel");
      });
      dom.pickerGrid.appendChild(d);
      prepCrispCanvas(d.querySelector("canvas"), 112, 96);
      drawMini(d.querySelector("canvas"), id, 2);
    });
    dom.pickerNameInput.value = save.name || "PET";
    dom.pickerModal.classList.remove("hidden");
  }
  function closePicker() {
    dom.pickerModal.classList.add("hidden");
  }
  function confirmPicker() {
    save.species = selectedSpecies;
    const nm = (dom.pickerNameInput.value || "PET").toUpperCase().trim().slice(0, 14);
    save.name = nm || "PET";
    persistSave();
    updatePanels();
    closePicker();
    toast("PARTNER SET: " + save.name);
  }

  // ---- shop ----
  function renderShop() {
    dom.shopGrid.innerHTML = "";
    ITEMS.forEach(([id, nm, cat, pr, fx]) => {
      const d = document.createElement("div");
      d.className = "hud-item" + (save.owned[id] ? " hud-owned" : "");
      d.innerHTML =
        '<div class="hud-in">' + nm + '</div><div class="hud-ic">' + cat + '</div><div class="hud-fx">' + fx + '</div><button type="button">' +
        (save.owned[id] ? "OWNED" : pr.toLocaleString() + " G") +
        "</button>";
      d.querySelector("button").addEventListener("click", () => {
        if (save.owned[id]) return;
        if (save.gold < pr) {
          toast("NOT ENOUGH GOLD!");
          return;
        }
        save.gold -= pr;
        save.owned[id] = 1;
        if (id === "treat") G.petHP = 100;
        if (id === "tag") {
          const nm2 = window.prompt("New name for " + save.name + ":", save.name);
          if (nm2 && nm2.trim()) save.name = nm2.toUpperCase().trim().slice(0, 14);
        }
        persistSave();
        toast(nm + " PURCHASED!");
        renderShop();
        updatePanels();
      });
      dom.shopGrid.appendChild(d);
    });
  }
  function openShop() {
    renderShop();
    dom.shopModal.classList.remove("hidden");
  }
  function closeShop() {
    dom.shopModal.classList.add("hidden");
  }

  function init() {
    dom = {
      bar: document.getElementById("hudBar"),
      collapseBtn: document.getElementById("hudCollapseBtn"),
      collapsed: document.getElementById("hudCollapsed"),
      miniIcon: document.getElementById("hudMiniIcon"),
      miniQuest: document.getElementById("hudMiniQuest"),
      full: document.getElementById("hudFull"),
      arenaWrap: document.getElementById("hudArenaWrap"),
      petName: document.getElementById("hudPetName"),
      petStage: document.getElementById("hudPetStage"),
      petLv: document.getElementById("hudPetLv"),
      petHP: document.getElementById("hudPetHP"),
      xpLbl: document.getElementById("hudXpLbl"),
      petXP: document.getElementById("hudPetXP"),
      enemyPanel: document.getElementById("hudEnemyPanel"),
      enemyName: document.getElementById("hudEnemyName"),
      enemyKind: document.getElementById("hudEnemyKind"),
      enemyHP: document.getElementById("hudEnemyHP"),
      questCopy: document.getElementById("hudQuestCopy"),
      gold: document.getElementById("hudGold"),
      streak: document.getElementById("hudStreak"),
      shopBtn: document.getElementById("hudShopBtn"),
      pickerModal: document.getElementById("hudPickerModal"),
      pickerGrid: document.getElementById("hudPickerGrid"),
      pickerNameInput: document.getElementById("hudPetNameInput"),
      pickerSkipBtn: document.getElementById("hudPickerSkipBtn"),
      pickerConfirmBtn: document.getElementById("hudPickerConfirmBtn"),
      shopModal: document.getElementById("hudShopModal"),
      shopGold: document.getElementById("hudShopGold"),
      shopGrid: document.getElementById("hudShopGrid"),
      shopCloseBtn: document.getElementById("hudShopCloseBtn"),
      toast: document.getElementById("hudToast"),
      introReopenBtn: document.getElementById("hudIntroReopenBtn"),
      introOverlay: document.getElementById("hudIntroOverlay"),
      introSteps: Array.from(document.querySelectorAll(".hud-intro-step")),
      introDots: Array.from(document.querySelectorAll(".hud-intro-dot")),
      introEggCanvas: document.getElementById("hudIntroEggCanvas"),
      introNextBtn: document.getElementById("hudIntroNextBtn"),
      introSkipBtn: document.getElementById("hudIntroSkipBtn"),
    };
    if (!dom.bar || !dom.full) return; // HUD markup not present — no-op, never break the rest of the app

    cv = document.getElementById("hudArena");
    ctx = cv.getContext("2d");
    // Fixed-size non-arena canvases: prep once for the current dpr (drawMini()
    // re-clears/redraws through the stored logical size on every call).
    prepCrispCanvas(dom.miniIcon, 20, 20);
    prepCrispCanvas(dom.introEggCanvas, 100, 88);
    preloadSprites();

    let needsPicker = false;
    save = loadSave();
    if (!save) {
      save = { species: "byte", name: "PET", xp: 0, gold: 0, owned: {}, streakDays: 1, lastActiveDate: null };
      needsPicker = true;
    }
    save.owned = save.owned || {};
    applyStreak();
    persistSave();

    say("WAITING FOR QUEST...", true);
    updatePanels();

    const initialMode = (() => {
      try {
        const m = localStorage.getItem(MODE_KEY);
        if (m === "compact" || m === "expanded" || m === "collapsed") return m;
        // Migrate the old boolean flag once; brand-new users default to compact.
        if (localStorage.getItem(LEGACY_COLLAPSE_KEY) === "1") return "collapsed";
        return "compact";
      } catch (e) {
        return "compact";
      }
    })();
    applyMode(initialMode);

    dom.collapseBtn.addEventListener("click", () => applyMode(nextMode(hudMode)));
    dom.shopBtn.addEventListener("click", openShop);
    dom.shopCloseBtn.addEventListener("click", closeShop);
    dom.pickerSkipBtn.addEventListener("click", closePicker);
    dom.pickerConfirmBtn.addEventListener("click", confirmPicker);
    dom.introReopenBtn.addEventListener("click", openIntro);
    dom.introNextBtn.addEventListener("click", introAdvance);
    dom.introSkipBtn.addEventListener("click", closeIntro);
    document.addEventListener("visibilitychange", syncLoop);

    const introSeen = (() => {
      try {
        return localStorage.getItem(INTRO_KEY) === "1";
      } catch (e) {
        return true; // storage unavailable — don't nag every load
      }
    })();
    if (!introSeen) openIntro(); // panel (c) hands off into the picker itself
    else if (needsPicker) openPicker(); // returning HUD state with no saved pet, intro already seen

    syncLoop();
    watchDpr();
  }

  // Re-preps every fixed-size canvas when the effective devicePixelRatio changes —
  // dragging the window to a monitor with different Windows display scaling (or the
  // user changing that scaling live) fires this without a reload. matchMedia's
  // resolution query only fires once per threshold crossing, so it's re-armed with
  // the new ratio after every change.
  function watchDpr() {
    const mq = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
    const onChange = () => {
      dpr = Math.max(1, window.devicePixelRatio || 1);
      if (cv && !isCollapsed()) {
        cv.width = Math.round(640 * arenaScale * dpr);
        cv.height = Math.round(200 * arenaScale * dpr);
      }
      prepCrispCanvas(dom.miniIcon, 20, 20);
      prepCrispCanvas(dom.introEggCanvas, 100, 88);
      if (isCollapsed()) renderMiniIcon();
      watchDpr();
    };
    mq.addEventListener("change", onChange, { once: true });
  }

  return {
    init,
    onUserSend(text) {
      if (!save) return;
      G.pendingPromptText = text;
      G.awaitingFirstBlock = true;
      G.toolRunsThisTurn = 0;
      markActivity();
      sessionLive();
    },
    onBlockStart(blockType, toolName) {
      if (!save) return;
      if (G.awaitingFirstBlock) {
        G.awaitingFirstBlock = false;
        spawnForTurn(G.pendingPromptText || "");
      }
      if (blockType === "tool_use") {
        G.toolRunsThisTurn = (G.toolRunsThisTurn || 0) + 1;
        attack(toolName);
      }
    },
    onDelta(kind) {
      if (!save) return;
      if (kind === "thinking" || kind === "text") charge(kind);
    },
    onToolError() {
      if (!save) return;
      enemyCounter();
    },
    onPermissionRequest() {
      if (!save) return;
      freeze(true);
    },
    onPermissionResolved() {
      if (!save) return;
      freeze(false);
    },
    onTurnResult({ isError, costUsd, tokens }) {
      if (!save || isError) return;
      victory({ toolRuns: G.toolRunsThisTurn || 0, xpBase: 10, costUsd: costUsd || 0, tokens: tokens || 0 });
      G.toolRunsThisTurn = 0;
    },
    onSessionExited() {
      if (!save) return;
      sessionExited();
    },
    onSessionLive() {
      if (!save) return;
      sessionLive();
    },
  };
})();

// ---------------------------------------------------------------------------
// Dashboard tab — read-only workspace/session summary rendered from
// `dashboard_summary` (src-tauri/src/dashboard.rs). Every action button
// deep-links back to the Chat tab via `deepLinkToChat`, matching the
// approved mock's documented toast behavior. Lazily loaded: nothing is
// fetched until the tab is first shown.
// ---------------------------------------------------------------------------

const Dashboard = (() => {
  let summary = null;
  let loading = false;
  let loadedOnce = false;

  function fmtDate(ms) {
    return new Date(ms).toLocaleDateString(undefined, {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }

  function fmtTime(ms) {
    return new Date(ms).toLocaleTimeString(undefined, { hour12: false });
  }

  function fmtRelative(ms) {
    if (!ms) return "";
    const diffMs = Date.now() - ms;
    const min = Math.round(diffMs / 60000);
    if (min < 1) return "just now";
    if (min < 60) return `${min}m ago`;
    const hr = Math.round(min / 60);
    if (hr < 24) return `${hr}h ago`;
    return `${Math.round(hr / 24)}d ago`;
  }

  // Reads the HUD pet-save (localStorage key "asb-pet", owned by the `HUD` module above) purely
  // for its `streakDays` field. Read-only, never writes — the HUD module remains the sole owner
  // of that state.
  function petState() {
    try {
      return JSON.parse(localStorage.getItem("asb-pet") || "{}");
    } catch (err) {
      return {};
    }
  }

  function setChildren(node, children) {
    node.innerHTML = "";
    for (const c of children) node.appendChild(c);
  }

  function statTile({ label, value, sub, tone, cmd }) {
    const tile = el("div", { class: "stat-tile" + (tone ? ` stat--${tone}` : "") });
    tile.appendChild(el("div", { class: "stat-label", text: label }));
    tile.appendChild(el("div", { class: "stat-value num", text: String(value) }));
    if (sub) tile.appendChild(el("div", { class: "stat-sub", text: sub }));
    if (cmd) tile.addEventListener("click", () => deepLinkToChat(cmd));
    return tile;
  }

  function row({ main, sub, chip, chipTone, btnLabel, cmd }) {
    const rowEl = el("div", { class: "row" });
    const grow = el("div", { class: "grow" });
    grow.appendChild(el("div", { text: main }));
    if (sub) grow.appendChild(el("div", { class: "sub", text: sub }));
    rowEl.appendChild(grow);
    if (chip) {
      rowEl.appendChild(el("span", { class: "chip" + (chipTone ? ` ${chipTone}` : ""), text: chip }));
    }
    if (btnLabel && cmd) {
      const btn = el("button", { class: "ai-btn", text: "▶ " + btnLabel, attrs: { type: "button" } });
      btn.addEventListener("click", () => deepLinkToChat(cmd));
      rowEl.appendChild(btn);
    }
    return rowEl;
  }

  function emptyState(text, cmd, cmdLabel) {
    const wrap = el("div", { class: "empty" });
    wrap.appendChild(document.createTextNode(cmd ? text + " " : text));
    if (cmd) {
      const btn = el("button", {
        class: "dash-empty-link",
        text: cmdLabel || cmd,
        attrs: { type: "button" },
      });
      btn.addEventListener("click", () => deepLinkToChat(cmd));
      wrap.appendChild(btn);
    }
    return wrap;
  }

  // Best-effort classification of a ledger item's free-text `due` field. Only an unambiguously
  // parseable date (`new Date(due)` succeeds) is ever called "overdue"/"today" — anything else
  // (missing, freeform text) is left `"unknown"` rather than guessed, per the no-guessing rule.
  function dueBucket(due) {
    if (!due) return "unknown";
    const d = new Date(due);
    if (isNaN(d.getTime())) return "unknown";
    const today = new Date();
    if (d.toDateString() === today.toDateString()) return "today";
    return d.getTime() < new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
      ? "overdue"
      : "future";
  }

  function renderHero() {
    const tiles = [];
    const tasks = summary.tasks || [];
    const waiting = summary.waiting || [];
    if (tasks.length) {
      const overdue = tasks.filter((t) => dueBucket(t.due) === "overdue").length;
      const dueToday = tasks.filter((t) => dueBucket(t.due) === "today").length;
      tiles.push(
        statTile({
          label: "⏰ Overdue",
          value: overdue,
          sub: "open past due",
          tone: overdue > 0 ? "serious" : undefined,
          cmd: "/follow-ups",
        })
      );
      tiles.push(
        statTile({
          label: "📅 Due today",
          value: dueToday,
          sub: "on the clock",
          tone: dueToday > 0 ? "warn" : undefined,
          cmd: "/follow-ups",
        })
      );
    }
    if (waiting.length) {
      tiles.push(
        statTile({
          label: "🤝 Waiting replies",
          value: waiting.length,
          sub: "tracked in waiting ledger",
          tone: "warn",
          cmd: "/follow-ups",
        })
      );
    }
    tiles.push(
      statTile({
        label: "📥 Inbox",
        value: summary.inbox.length,
        sub: summary.inbox.length ? "sweep ready" : "all clear",
        tone: summary.inbox.length ? "good" : undefined,
        cmd: "/organize-inbox",
      })
    );
    const streak = petState().streakDays || 0;
    tiles.push(
      statTile({
        label: "🔥 Streak",
        value: streak ? streak + "d" : "—",
        sub: streak ? "keep it going" : "start today",
        tone: streak ? "good" : undefined,
      })
    );
    setChildren(dom.dashHero, tiles);
  }

  function renderMomentum() {
    // `dashboard_summary` only returns rolling 7-day totals, never a per-day series — there is
    // never enough granularity for an honest sparkline, so this always renders the single
    // aggregate usage card rather than fabricate a trend line from thin air.
    const stats = summary.sessionStats;
    const card = el("div", { class: "trend" });
    card.appendChild(el("div", { class: "t", text: "💬 Sessions · last 7 days" }));
    card.appendChild(el("div", { class: "v num", text: String(stats.sessions7d) }));
    card.appendChild(
      el("div", {
        class: "u",
        text: `${stats.turns7d} turns · $${stats.cost7dUsd.toFixed(2)} compute`,
      })
    );
    setChildren(dom.dashMomentum, [card]);
  }

  async function renderBriefing() {
    const daily = (summary.notes || []).find((n) => /^daily-review/i.test(n.name));
    if (!daily) {
      dom.dashBriefingMeta.textContent = "";
      setChildren(dom.dashBriefingBody, [emptyState("No daily briefing yet.", "/daily-review", "Generate one")]);
      return;
    }
    dom.dashBriefingMeta.textContent = daily.name + " · " + fmtRelative(daily.mtimeMs);
    dom.dashBriefingBody.innerHTML = "<p>Loading…</p>";
    try {
      const file = await invoke("read_workspace_file", { path: "notes/" + daily.name });
      dom.dashBriefingBody.innerHTML = renderMarkdownFull(file.text || "");
    } catch (err) {
      setChildren(dom.dashBriefingBody, [emptyState("Couldn't load " + daily.name + ": " + err)]);
    }
  }

  function renderActions() {
    const items = [];
    for (const t of summary.tasks || []) {
      const bucket = dueBucket(t.due);
      items.push(
        row({
          main: t.title,
          sub: t.due ? "due " + t.due : t.status,
          chip: bucket === "overdue" ? "overdue" : bucket === "today" ? "due today" : t.status,
          chipTone: bucket === "overdue" ? "serious" : bucket === "today" ? "warn" : undefined,
          btnLabel: "Open",
          cmd: "/follow-ups",
        })
      );
    }
    for (const w of summary.waiting || []) {
      items.push(
        row({
          main: w.title,
          sub: w.status || "waiting on a reply",
          chip: "waiting",
          chipTone: "warn",
          btnLabel: "Nudge",
          cmd: "/follow-ups",
        })
      );
    }
    dom.dashActionsCount.textContent = items.length ? `${items.length} open` : "none tracked";
    if (!items.length) {
      setChildren(dom.dashActions, [
        emptyState("No tracked tasks or waiting items yet.", "/follow-ups", "Run /follow-ups"),
      ]);
      return;
    }
    setChildren(dom.dashActions, items);
  }

  function renderActivity() {
    const files = [...(summary.inbox || []), ...(summary.notes || [])]
      .sort((a, b) => b.mtimeMs - a.mtimeMs)
      .slice(0, 8);
    if (!files.length) {
      setChildren(dom.dashActivity, [emptyState("Nothing touched in inbox or notes yet.")]);
      return;
    }
    setChildren(
      dom.dashActivity,
      files.map((f) =>
        row({
          main: f.name,
          sub: [f.firstLine, fmtRelative(f.mtimeMs)].filter(Boolean).join(" · "),
        })
      )
    );
  }

  function renderInbox() {
    dom.dashInboxCount.textContent = String(summary.inbox.length);
    if (!summary.inbox.length) {
      setChildren(dom.dashInboxList, [emptyState("Inbox is empty.", "/organize-inbox", "Organize inbox")]);
      return;
    }
    setChildren(
      dom.dashInboxList,
      summary.inbox.map((f) =>
        row({
          main: f.name,
          sub: [f.firstLine, fmtRelative(f.mtimeMs)].filter(Boolean).join(" · "),
          btnLabel: "Organize",
          cmd: "/organize-inbox",
        })
      )
    );
  }

  function renderWork() {
    const tasks = summary.tasks || [];
    const overdue = tasks.filter((t) => dueBucket(t.due) === "overdue");
    const dueToday = tasks.filter((t) => dueBucket(t.due) === "today");
    const waiting = summary.waiting || [];

    dom.dashOverdueCount.textContent = String(overdue.length);
    dom.dashDueTodayCount.textContent = String(dueToday.length);
    dom.dashWaitingCount.textContent = String(waiting.length);

    setChildren(
      dom.dashOverdueList,
      overdue.length
        ? overdue.map((t) =>
            row({ main: t.title, sub: t.status, chip: t.due, chipTone: "serious", btnLabel: "Prep", cmd: "/meeting-prep" })
          )
        : [emptyState("Nothing overdue.")]
    );
    setChildren(
      dom.dashDueTodayList,
      dueToday.length
        ? dueToday.map((t) =>
            row({ main: t.title, sub: t.status, chip: "today", chipTone: "warn", btnLabel: "Draft", cmd: "/follow-ups" })
          )
        : [emptyState("Nothing due today.")]
    );
    setChildren(
      dom.dashWaitingList,
      waiting.length
        ? waiting.map((w) =>
            row({ main: w.title, sub: w.status, chip: "waiting", chipTone: "warn", btnLabel: "Nudge", cmd: "/follow-ups" })
          )
        : [
            emptyState(
              "No tracked ledgers found yet — this fills in once journal/tasks.json or journal/waiting.json exist.",
              "/follow-ups",
              "Run /follow-ups"
            ),
          ]
    );
  }

  function renderMeetings() {
    // No meetings ledger is wired into `dashboard_summary` — always a friendly pointer at
    // /meeting-prep rather than guessing at meeting data this tab doesn't have.
    setChildren(dom.dashMeetingsList, [emptyState("No meeting ledger yet.", "/meeting-prep", "Run /meeting-prep")]);
  }

  function renderUsage() {
    const stats = summary.sessionStats;
    setChildren(dom.dashUsageHero, [
      statTile({ label: "Sessions · 7d", value: stats.sessions7d }),
      statTile({ label: "Turns · 7d", value: stats.turns7d }),
      statTile({ label: "Cost · 7d", value: "$" + stats.cost7dUsd.toFixed(2) }),
    ]);
    setChildren(dom.dashUsageTrend, [
      emptyState("Daily usage history isn't tracked yet — only rolling 7-day totals are available above."),
    ]);
  }

  function renderSystem() {
    const rows = [];
    rows.push(
      row({
        main: "Claude Code CLI",
        sub: summary.claudeOk ? "found on this machine" : "not found",
        chip: summary.claudeOk ? "ok" : "missing",
        chipTone: summary.claudeOk ? "good" : "serious",
      })
    );
    const wsOk = !!(obWorkspaceStatus && obWorkspaceStatus.configured && !obWorkspaceStatus.error);
    rows.push(
      row({
        main: "Workspace",
        sub: wsOk ? obWorkspaceStatus.root || "configured" : "not configured",
        chip: wsOk ? "ok" : "missing",
        chipTone: wsOk ? "good" : "serious",
      })
    );
    rows.push(
      row({
        main: "AI providers",
        sub: summary.providers.length ? summary.providers.join(" · ") : "none enabled",
        chip: String(summary.providers.length),
        chipTone: summary.providers.length ? "good" : undefined,
      })
    );
    rows.push(
      row({
        main: "Account",
        sub: summary.accountStatus.registered
          ? summary.accountStatus.phoneVerified
            ? "registered · WhatsApp verified"
            : "registered · WhatsApp not verified"
          : "not registered",
        chip: summary.accountStatus.registered ? "ok" : "—",
        chipTone: summary.accountStatus.registered ? "good" : undefined,
      })
    );
    setChildren(dom.dashSystemList, rows);
  }

  function renderAll() {
    renderHero();
    renderMomentum();
    renderBriefing();
    renderActions();
    renderActivity();
    renderInbox();
    renderWork();
    renderMeetings();
    renderUsage();
    renderSystem();
  }

  function setLoading(isLoading) {
    loading = isLoading;
    dom.dashLoading.classList.toggle("hidden", !isLoading);
    dom.dashRefreshBtn.disabled = isLoading;
  }

  async function refresh() {
    if (loading) return;
    setLoading(true);
    try {
      summary = await invoke("dashboard_summary");
      loadedOnce = true;
      renderAll();
      dom.dashUpdatedAt.textContent = "updated " + fmtTime(Date.now());
    } catch (err) {
      showToast("Failed to load dashboard: " + err);
    } finally {
      setLoading(false);
    }
  }

  function switchSubTab(tab) {
    dom.dashSubTabs.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.dt === tab);
    });
    dom.dashView.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("is-active", panel.id === "dp-" + tab);
    });
  }

  function bindListeners() {
    dom.dashRefreshBtn.addEventListener("click", refresh);
    dom.dashSubTabs.addEventListener("click", (e) => {
      const btn = e.target.closest(".tab-btn");
      if (!btn) return;
      switchSubTab(btn.dataset.dt);
    });
    dom.dashView.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-cmd]");
      if (!btn) return;
      deepLinkToChat(btn.dataset.cmd);
    });
    window.addEventListener("focus", () => {
      if (currentMainView === "dashboard" && loadedOnce) refresh();
    });
  }

  function onShown() {
    dom.dashDate.textContent = fmtDate(Date.now());
    if (!loadedOnce) refresh();
  }

  return { bindListeners, onShown, refresh };
})();

window.addEventListener("DOMContentLoaded", async () => {
  grabDom();
  bindStaticListeners();
  ensureElapsedTicker();
  HUD.init();
  try {
    await wireBackendEvents();
  } catch (err) {
    showToast("Failed to attach to Claude Code events: " + err);
  }
  try {
    await runOnboarding();
  } catch (err) {
    showToast("Onboarding failed: " + err);
  }
  // Providers/multimodal settings must be loaded before sessions render (populateSessionSettings
  // needs providersCache to populate the provider <select>), so this comes before that Promise.all.
  await Promise.all([loadProviders(), loadMultimodalSettings()]);
  refreshClaudeAuthStatus();
  await Promise.all([loadHarnessCommands(), loadSessions()]);
  updateComposerEnabled();
  updateStatusBar();
  // Non-blocking: never gate startup on a network round-trip, and swallow failures (offline is
  // the common case) since this is the silent auto-check, not the manual menu one.
  checkForUpdates(false).catch(() => {});
});

// ---------------------------------------------------------------------------
// theme picker — named themes (dark/light + pop-culture set), persisted to
// localStorage under the same "asb-theme" key the old dark/light toggle used
// (those two values are still valid theme names, so no migration write is
// needed — the known-list guard in index.html's inline script and here is
// the migration: anything unrecognized falls back to "dark").
// ---------------------------------------------------------------------------
const THEME_LIST = [
  { id: "dark", label: "DARK", dots: ["#0B1B3A", "#3B82F6", "#e7edfb"] },
  { id: "light", label: "LIGHT", dots: ["#f4f1e8", "#166e41", "#1d241f"] },
  { id: "matrix", label: "MATRIX", dots: ["#000000", "#00ff41", "#33ff66"] },
  { id: "synthwave", label: "SYNTHWAVE", dots: ["#1a0b2e", "#ff2d95", "#00e5ff"] },
  { id: "gameboy", label: "GAME BOY", dots: ["#9bbc0f", "#306230", "#0f380f"] },
  { id: "dracula", label: "DRACULA", dots: ["#282a36", "#bd93f9", "#50fa7b"] },
  { id: "nord", label: "NORD", dots: ["#2e3440", "#88c0d0", "#eceff4"] },
  { id: "paper", label: "PAPER", dots: ["#fbf9f4", "#2563eb", "#26241d"] },
  { id: "midnight-gold", label: "MIDNIGHT GOLD", dots: ["#0a0a0f", "#d4af37", "#f0ead8"] },
  { id: "psb-rgb", label: "PSB RGB", dots: ["#60a5fa", "#a78bfa", "#34d399"] },
];
const THEME_IDS = new Set(THEME_LIST.map((t) => t.id));
const themeToggleBtn = document.getElementById("themeToggle");
const themePopover = document.getElementById("themePopover");

function applyTheme(theme) {
  if (!THEME_IDS.has(theme)) theme = "dark";
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("asb-theme", theme); } catch (e) {}
  const active = THEME_LIST.find((t) => t.id === theme);
  if (themeToggleBtn) {
    themeToggleBtn.textContent = "▓ " + (active ? active.label : theme.toUpperCase());
    themeToggleBtn.setAttribute("aria-label", "Choose theme (current: " + (active ? active.label : theme) + ")");
  }
  if (themePopover) {
    themePopover.querySelectorAll(".theme-swatch-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.themeId === theme);
    });
  }
}

function closeThemePopover() {
  if (!themePopover) return;
  themePopover.classList.add("hidden");
  if (themeToggleBtn) themeToggleBtn.setAttribute("aria-expanded", "false");
}

if (themePopover) {
  themePopover.innerHTML = THEME_LIST.map((t) => {
    const dots = t.dots.map((c) => '<span style="background:' + c + '"></span>').join("");
    return (
      '<button type="button" class="theme-swatch-btn" data-theme-id="' + t.id + '" role="menuitemradio" aria-label="' + t.label + ' theme">' +
      '<span class="theme-swatch-dots">' + dots + "</span>" +
      "<span>" + t.label + "</span>" +
      "</button>"
    );
  }).join("");
  themePopover.addEventListener("click", (e) => {
    const btn = e.target.closest(".theme-swatch-btn");
    if (!btn) return;
    applyTheme(btn.dataset.themeId);
    closeThemePopover();
  });
}

applyTheme(THEME_IDS.has(document.documentElement.dataset.theme) ? document.documentElement.dataset.theme : "dark");

if (themeToggleBtn) {
  themeToggleBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!themePopover) return;
    const willOpen = themePopover.classList.contains("hidden");
    themePopover.classList.toggle("hidden", !willOpen);
    themeToggleBtn.setAttribute("aria-expanded", String(willOpen));
  });
  document.addEventListener("click", (e) => {
    if (themePopover && !themePopover.classList.contains("hidden") && !themePopover.contains(e.target) && e.target !== themeToggleBtn) {
      closeThemePopover();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeThemePopover();
  });
}
