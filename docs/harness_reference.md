# Harness Reference (on-demand detail for CLAUDE.md)

> This file holds the full tool detail that used to live in `CLAUDE.md`. The lean `CLAUDE.md` keeps the always-on rules and routing; **Read the relevant section here when the matching task appears.** A rule lives in exactly one place: core owns rules, this file owns detail.
>
> Anchors: [#platform](#platform) · [#google-workspace](#google-workspace) · [#repo-skills](#repo-skills) · [#subagents](#subagents) · [#preferred-tools](#preferred-tools) · [#dedicated-tools](#dedicated-tools)

---

## repo-skills

Main repo (path varies by machine -- run platform detection below to resolve `REPO_ROOT`):
- **macOS**: `.`
- **WSL (Ubuntu)**: `.`
- **Windows native**: no native checkout -- proxy into the WSL path above via `wsl.exe`

Skills: `.agent/skills/` -- always check here first when looking for a skill/connector.

**Harness layout**: `.claude/` = Claude Code entry points (commands/agents/hooks); `.agent/` = cross-harness SOP source (Antigravity reads it too). Commands shim to `.agent/` bodies -- do not duplicate content across the two.
**Slack send guard**: the PreToolUse hook matches `mcp__.*[Ss]lack.*__.*(post|send|reply).*`: if a Slack MCP server is renamed or added, re-verify the matcher in `.claude/settings.json`.

**Worktree awareness**: This repo is sometimes opened via Windows worktree. The worktree may not have all files. WSL is the source of truth.

---

## platform

This repo runs on three machines (macOS, WSL/Ubuntu, Windows native). Detect once at session start by running the single source of truth:

```bash
bash .agent/scripts/detect_platform.sh
```

It prints `PLATFORM` (macos | wsl | windows), `REPO_ROOT` for this machine, and `RUN_PREFIX`/`RUN_SUFFIX` for wrapping skill calls. Adapt every Python skill call accordingly:

| `uname -s` | PLATFORM | How to run Python skills |
| :---- | :---- | :---- |
| `Darwin` | **macos** | Run natively from `REPO_ROOT`. NO `wsl.exe`. e.g. `python3 .agent/skills/.../x.py` |
| `Linux` | **wsl** | Run natively, as written in this file. |
| `MINGW*` / `MSYS*` / missing | **windows** | Proxy into WSL: `wsl.exe bash -c "cd <WSL_ROOT> && <command>"` |

Example -- `gdocs-create` on **Windows native** (the only platform that needs a prefix):
```bash
wsl.exe bash -c "cd . && timeout 180s python3 .agent/skills/gdocs-create/gdocs_create.py create-doc --title 'Title' --content '...' --account work"
```
On **macOS** and **WSL** the same command runs directly with no prefix.

**Fallback (Windows only, if `wsl.exe` fails)**: use `MSYS_NO_PATHCONV=1 wsl.exe bash -c "..."`. If WSL is not configured on a Windows machine, alert You -- Python skills need WSL there because credentials and tokens live in the WSL filesystem.

**Critical**: `uname -s` is cheap and reliable, so always run detection and never guess. NEVER use `wsl.exe` on macOS (`Darwin`) -- the binary does not exist there and the call will fail.

---

## google-workspace

**Rule: MCP first for read/search. Python skills for create/update/delete. NEVER use the browser tool.**

### Update Protocol (applies to all Drive/Docs operations)

**Drive is the source of truth.** Before creating or updating any document:

1. Check if the file exists (search by title or use known file ID).
2. If it exists → **use `update`, not a new upload**. Preserves title, file ID, sharing settings.
3. Never change the title of an existing document when updating.
4. If Drive and local differ, Drive wins (verify with `modifiedTime`). Sync local to match Drive.
5. Add a changelog entry to the document header on every revision:

```markdown
| Revision | Date | Summary |
| :---- | :---- | :---- |
| v1.0 | 2026-01-15 | Initial draft |
| v1.1 | 2026-05-04 | Updated section 3 |
```

### Full Capability Matrix

| Action | Google Drive | Google Docs | Google Sheets |
| :--- | :--- | :--- | :--- |
| Search/find | MCP `search_files` | MCP `search_files` | MCP `search_files` |
| Read content | MCP `read_file_content` | MCP `read_file_content` | MCP `read_file_content` |
| Get metadata/link | MCP `get_file_metadata` | MCP `get_file_metadata` | MCP `get_file_metadata` |
| Create real Google Doc | `gdocs-create` `create-doc` | `gdocs-create` `create-doc` | - |
| Upload new file | Python `upload` or MCP `create_file` | - | MCP `create_file` mimeType `text/csv` |
| Update/replace content | Python `update --id FILE_ID` | Python `update --id FILE_ID` | - |
| Rename | Python `rename --id FILE_ID` (Work) | Python `rename` | - |
| Delete (trash) | Python `delete --id FILE_ID` | Python `delete --id FILE_ID` | Python `delete --id FILE_ID` |
| Delete (permanent) | Python `delete --id FILE_ID --permanent` | same | same |
| Share | Python `share` | Python `share` | - |
| Read comments | Python `comments --id FILE_ID` | Python `comments` | - |
| Write to Sheets cells | - | - | **Not supported** - ask user to export as CSV |

### Creating a Real Google Doc from Markdown

Always use `gdocs-create` - it produces true editable Google Docs with proper headings, tables, bullets:

```bash
# Create new doc
timeout 180s python3 ".agent/skills/gdocs-create/gdocs_create.py" create-doc \
  --title "Title" --file path.md --account work|personal

# Or with inline content (no temp file needed - saves tokens)
timeout 180s python3 ".agent/skills/gdocs-create/gdocs_create.py" create-doc \
  --title "Title" --content "# My Doc\n\nContent here" --account work
```

Do NOT use MCP `text/plain` (shows raw `#` symbols) or `text/html` (not an editable Google Doc).

### Which Python Skill to Use

| Account | Skill | Key Path |
| :--- | :--- | :--- |
| Work | `work-drive-connector` | `.agent/skills/work-drive-connector/gdrive_manager.py` |
| Personal | `google-drive-connector` | `.agent/skills/google-drive-connector/gdrive_manager.py` |

Both support: `upload`, `update`, `delete`, `search`, `read`, `comments`.
Work also has: `rename`.
`gdocs-create` supports both via `--account work|personal`.

### Token Status
- Work: `.agent/skills/work-drive-connector/token.json` - auto-refreshed ✅
- Personal: `.agent/skills/google-drive-connector/token.json` - auto-refreshed ✅
- Secondary client: `.agent/skills/secondary-drive-connector/token.json` - generic slot for whatever non-Work/non-personal company is in use (`--account secondary` / `--profile secondary`). Currently holds the ex-Secondary token (revoked ❌); drop a new company's credentials here to reuse.

### Known Folder IDs (MCP)
- Personal My Drive root: `<YOUR_DRIVE_ID>`
- Work My Drive: omit parent-id (uses account root)

---

## subagents

Spawn subagents to isolate context, parallelize independent work, or offload bulk mechanical tasks. Don't spawn when the parent needs the reasoning, when synthesis requires holding things together, or when spawn overhead dominates.

Subagent definitions carry matching `model:` / `effort:` frontmatter; synthesis and strategy stay in the main loop. The routing table lives in core CLAUDE.md.

Rules: pick the cheapest row that fully covers the task; mechanical → delegate, judgment → keep in main loop. If a subagent finds it needs a higher tier than itself, return to the parent. The main loop cannot auto-swap its own model/effort. If a task needs a different main-loop tier than the current session, say so and ask You to `/model` or `/effort` (or run it as a Workflow with explicit per-stage model+effort).

**Cross-model offload.** `harvest`, `critic` (the adversarial half of `review`/`/hyperplan`), and `research` MAY route to a non-Claude model via `agy-bridge` instead of a Claude subagent (cheap-bulk or cross-model diversity); `synthesize` and `strategize` NEVER leave Claude. The bridge is capability-routed and cost-logged, and honors a `claude_fallback` sentinel when every non-Claude model is down (honor it, don't degrade). Offload heuristic: during likely-Anthropic-busy hours (~21:00-12:00 WIB) prefer the bridge to conserve the Claude pool. The full capability→model matrix, per-Mtok pricing, and time-routing live in the agy-bridge entry under [#dedicated-tools](#dedicated-tools) + `models.json`.

**Activity log (full-context memory).** On completing a tracked task (a PRD, a Slack send, a doc update, a dashboard/agent action, a daily/evening update), append one event via `python3 .agent/scripts/activity_log.py --actor agent --action <type> --project "<initiative>" --target <id> --summary "..."`. This feeds the dashboard's Tracker/Active-Projects roll-up and gives future sessions a log of what was done. Dashboard ticket edits auto-log via `/api/action`. Keep summaries one line; tag the right project (Marketplace/Platform/B2C/E-Commerce Solution/AI Circle).

**GLM offload mode (toggle).** SessionStart surfaces `GLM MODE: ON/OFF` from `.agent/glm_mode.flag` (toggle `/glm on|off|status`). ON = Router offloads heavy generation/research/draft/bulk to GLM 5.2 via `agy-bridge` (zero Claude quota); Claude still orchestrates, reviews, and applies, and final client-facing synthesis + judgment stay on Claude. OFF (default) = normal routing. A convenience switch over the agy-bridge chains, not a change to them.

**The Router (supervisor).** The main loop IS the team supervisor ("Router"): it classifies each request, picks the cheapest specialist + tier, spawns it, and synthesizes. There is no spawnable "boss" agent: a subagent cannot reliably spawn sub-subagents, so for multi-step parallel fan-out the Router uses the **Workflow tool** (it spawns the agents, not the agent). Specialists do single-domain work, call skills via Bash, and offload generation to GLM 5.2 via `agy-bridge --task draft`.

**Team roster (role labels for the existing agents):** `harvester`=Scout, `meeting-harvester`=Scribe, `draft`=Writer, `draft-reviewer`=Editor, `report-auditor`=Auditor, `hyperplan-critic`=Red Team.

**You / Work data separation (hard).** The personal-brand specialist agents (`social-producer`, `seo-specialist`, `perfmarketing-analyst`) moved to the You repo along with their connectors + tokens. This repo never runs You work; Work PM work stays on the Work connectors.

**Observability.** Scheduled routines + specialist agents write status to `dashboard-data/agent_heartbeat.jsonl` via `.agent/scripts/heartbeat.py`; the `localhost:3737` "⏰ Routines" tab shows last-success/fail per job, so a silent 2am failure is visible without polling.

Parent owns final output and cross-spawn synthesis. User instructions override.

---

## preferred-tools

### Data Fetching

1. **WebFetch**: free, text-only, works on public pages that don't block bots.
2. **agent-browser CLI**: free, local Rust CLI + Chrome via CDP. For dynamic pages or auth walls that WebFetch can't handle. Returns the accessibility tree with element refs (@e1, @e2). ~82% fewer tokens than screenshot-based tools. Install: `npm i -g agent-browser && agent-browser install`. Use `snapshot` for AI-friendly DOM state, element refs for interaction.
3. **Agent-Reach (platform-specific readers)**: for READING/searching specific platforms (Exa semantic search, X/Twitter, Reddit, YouTube subtitles, RSS, GitHub, LinkedIn public profiles), use Agent-Reach instead of hand-rolling a fetch. Read-only (no posting). Best fit for research sweeps and `/deep-research`. See the Dedicated Tools entry below for invocation. Use WebFetch/agent-browser for generic pages; reach for Agent-Reach when the source is one of those named platforms, or when you need semantic search.
4. **Notice recurring fetch patterns and propose wrapping them as dedicated tools.** When the same fetch/parse logic comes up more than once, suggest wrapping it as a named tool (e.g. a skill file or a .py script that calls `agent-browser` with the snapshot and extraction steps baked in for that source). Add the entry to [#dedicated-tools](#dedicated-tools) below and reference it by name on future calls.

### PDF Files

Use `pdftotext`, not the `Read` tool. Use `Read` only when the user directly asks to analyze images or charts inside the document. Read loads PDFs as images.

---

## dedicated-tools

### Research / internet (read-only)
- **Agent-Reach** -- multi-platform reader (Exa search, X authed-as-You, Reddit, YouTube, RSS, GitHub, Jina web). **Read-only, NEVER posts/DMs/comments.** Activate per shell: `source ~/.agent-reach/activate.sh`. Use for `/deep-research` and research sweeps. Commands, auth status, and the WSL DNS-over-TCP gotcha: [[reference_agent_reach_tool]] + `~/.agents/skills/agent-reach/SKILL.md`.

### Google Drive / Docs
- **Work Drive** -- [`.agent/skills/work-drive-connector/gdrive_manager.py`](../.agent/skills/work-drive-connector/gdrive_manager.py): upload/update/delete/search/read/rename/share/comments; `fetch_sheets.py` reads Sheets by tab.
- **GDoc comment replies (as You)** -- [`.agent/skills/work-drive-connector/reply_helper.py`](../.agent/skills/work-drive-connector/reply_helper.py): reply to AND resolve Google Doc comment threads as You (reuses the Work Drive OAuth token; owner verified = brian.faridhi@workincentives.com). `whoami` confirms token owner; `list --id FILE_ID` prints comment IDs; `reply --id FILE_ID --comment COMMENT_ID --text "..." [--resolve]`. Base `gdrive_manager.py comments` only READS; this is the write path. **Caveat: `@email` mentions post as plain text via the API and usually do NOT notify the person**, so ping them separately (Slack DM). Approval-gated: confirm with You before posting, same as Slack.
- **Personal Drive** -- [`.agent/skills/google-drive-connector/gdrive_manager.py`](../.agent/skills/google-drive-connector/gdrive_manager.py): same caps, you@example.com.
- **Secondary-client Drive** -- [`.agent/skills/secondary-drive-connector/gdrive_manager.py`](../.agent/skills/secondary-drive-connector/gdrive_manager.py): generic non-Work/non-personal slot (`--account secondary`); drop creds+token in the dir.
- **Drive Permissions** -- [`.agent/scripts/drive_permissions.py`](../.agent/scripts/drive_permissions.py): **LANDMINE -- every upload auto-publishes as `anyone with link`, so docs leak public by default.** After any new `gdocs-create`/upload that shouldn't be public, run `restrict --domain workincentives.com --apply` (`list <FILE_ID>` to audit; no `--apply` = dry run).
- **Google Docs Creator (preferred)** -- [`.agent/skills/gdocs-create/gdocs_create.py`](../.agent/skills/gdocs-create/gdocs_create.py): markdown -> real editable Google Doc (not raw text). Accounts work|personal|secondary. NOT MCP text/plain (shows raw `#`).
- **Google Docs Writer (legacy)** -- [`.agent/skills/gdocs-writer/scripts/gdocs_writer.py`](../.agent/skills/gdocs-writer/scripts/gdocs_writer.py): markdown->.docx->upload. Prefer gdocs-create unless `.docx` needed.
- **Table Width Balancer** -- [`scripts/set_gdoc_table_widths.py`](../scripts/set_gdoc_table_widths.py): proportional column widths + pageless so content-heavy tables read well. **Run after every `gdocs-create`/`update --convert` on a table-heavy doc; re-run if table text changes.** Flags: `--help` / module docstring.
- **Mermaid Embedder** -- [`scripts/embed_mermaid_in_gdoc.py`](../scripts/embed_mermaid_in_gdoc.py): renders Mermaid -> PNG (kroki) into `[[PLACEHOLDER]]` slots (GDocs can't render Mermaid). **A re-push/re-convert WIPES inline images, so re-run after EVERY `update --convert`.** Sources live in the script's `DIAGRAMS` dict.
- **Work Weekly Reports (tabbed master doc)** -- [`scripts/weekly_reports_tabs.py`](../scripts/weekly_reports_tabs.py): one master Doc (ID `<YOUR_DRIVE_ID>`), one tab per week. **Run after a weekly report is approved instead of creating a standalone Doc.** SOP: [`.agent/skills/work-weekly-report/SKILL.md`](../.agent/skills/work-weekly-report/SKILL.md).
- **GDoc formatting pass** -- after any convert with tables/diagrams/numbered-lists, run the full pass (widths + mermaid embed + numbered-list fix) and verify before sharing; see [[feedback_gdoc_formatting_pass]].

### Calendar
- **Google Calendar** -- [`.agent/skills/google-calendar-connector/gcal_manager.py`](../.agent/skills/google-calendar-connector/gcal_manager.py): list/search/sweep; profiles `work` + `secondary`. Use this Python script for Work, NOT the MCP calendar tool (see [[feedback_work_calendar]]).

### Fathom (meetings)
- **Read** -- interactive: claude.ai Fathom MCP (`mcp__claude_ai_Fathom__*`); headless/registry: [`.agent/skills/fathom-connector/scripts/fathom_client.py`](../.agent/skills/fathom-connector/scripts/fathom_client.py) (`X-Api-Key`). Harvest via the `meeting-harvester` subagent. (Direct `mcp__fathom__*` server was removed -- rejects the API key.)
- **Registry (which recording?)** -- [`scripts/fathom_registry_sync.py`](../scripts/fathom_registry_sync.py) -> [`journal/fathom_registry.json`](../journal/fathom_registry.json). **Grep the JSON FIRST** (by date_wib/matched_meeting/client) before hitting the API.
- **Frame grab (stills)** -- [`.agent/skills/fathom-frame-grab/scripts/fathom_frame_grab.py`](../.agent/skills/fathom-frame-grab/scripts/fathom_frame_grab.py): pull still frames for a BRD/PRD (API gives only transcript). SOP: [`.agent/skills/fathom-frame-grab/SKILL.md`](../.agent/skills/fathom-frame-grab/SKILL.md).

### Meeting recording routing (2026-07-06)
- **Vexa bot = PRIMARY auto-recorder** -- [`meeting-recorder/vexa_bots.py`](../meeting-recorder/vexa_bots.py) `auto` on cron `*/5` joins EVERY Work calendar event with a Meet/Teams link as bot "Your Name"; transcript -> registry + MOM draft. Log `/tmp/vexa_auto.log`, heartbeat job `vexa-auto`. Self-heals gateway-IP drift, restarts container/whisper-server, flags empty transcripts as failures.
- **Fathom = backup + video** for meetings You attends (unchanged).
- **Desktop recorder = manual fallback** -- [`meeting-recorder/recorder.py`](../meeting-recorder/recorder.py) / GUI; `--video` or GUI checkbox adds a screen-record `.mp4` sidecar (`video_path` in registry).
- **Dedupe: one meeting -> one MOM.** All three write to `journal/fathom_registry.json`; entries for the same `matched_meeting`+date are cross-referenced (`related_recordings`) and MOM drafting is skipped when a related entry already has `mom_path`. Full detail: [`meeting-recorder/README.md`](../meeting-recorder/README.md).

### Slack
- **Slack** -- [`.agent/skills/slack-connector/scripts/slack_client.py`](../.agent/skills/slack-connector/scripts/slack_client.py): read history/threads + **SEND AS You via `--action post`** (uses You's user token `SLACK_USER_TOKEN` / xoxp by default, no bot footer; `--thread-ts`, `--text-file`, prints permalink). **NEVER send via the MCP Slack tools (those post as the Claude bot); confirm with You before EVERY send.**

### Figma
- **Figma (raw API)** -- [`.agent/skills/figma-connector/scripts/figma_client.py`](../.agent/skills/figma-connector/scripts/figma_client.py): REST fallback; prefer MCP Figma for design context.
- **Marketplace Figma index** -- [`scripts/marketplace_figma_index_sync.py`](../scripts/marketplace_figma_index_sync.py) -> mirror [`Clients/Work/Marketplace/Marketplace_Figma_Design_Index.md`](../Clients/Work/Marketplace/Marketplace_Figma_Design_Index.md). **Grep the mirror FIRST** for "where's the design for X".

### Work product tracking
- **Master Product List** -- [`.agent/skills/master-product-list/register_prd.py`](../.agent/skills/master-product-list/register_prd.py): register a PRD into the MPL sheet + local md.
- **Work Link Sync** -- [`.agent/skills/work-link-sync/link_sync.py`](../.agent/skills/work-link-sync/link_sync.py): link a GDoc URL to MPL rows + Master Doc; [`batch_master_docs_upload.py`](../.agent/skills/work-link-sync/batch_master_docs_upload.py) for bulk (`--dry-run`).

### Analytics / observability
- **Dashboard Sync** -- [`.agent/skills/dashboard-updater/scripts/dashboard_sync.py`](../.agent/skills/dashboard-updater/scripts/dashboard_sync.py): calendar+Drive+Slack -> `Dashboard.md`.
- **Mixpanel** -- [`.agent/skills/mixpanel-connector/scripts/mixpanel_client.py`](../.agent/skills/mixpanel-connector/scripts/mixpanel_client.py): events/funnels/retention/export (creds in `token.env`).
- **Heartbeat** -- [`.agent/scripts/heartbeat.py`](../.agent/scripts/heartbeat.py): routines/agents append status -> `dashboard-data/agent_heartbeat.jsonl` -> `localhost:3737` "⏰ Routines" tab (catches silent 2am failures). `--job <name> --status ok|fail --summary "..."`.

### Content / document tooling (dual-use; copies also live in the You repo)
- **Gemini Image** -- [`.agent/skills/gemini-image/generate.py`](../.agent/skills/gemini-image/generate.py): image generation. Best `--model gemini-3-pro-image`; key is **metered/billing -- confirm before any batch** ([[reference_gemini_image_skill]]). Brand-specific visual rules live in the You repo.
- **Diagram generator** -- [`.agent/skills/diagram-gen/SKILL.md`](../.agent/skills/diagram-gen/SKILL.md): English -> Mermaid, validate via `render_check.py`, then feed the Mermaid Embedder.
- **Make PDF** -- [`.agent/skills/make-pdf/SKILL.md`](../.agent/skills/make-pdf/SKILL.md): markdown -> publication-quality PDF (WeasyPrint) for lead magnets / one-pagers.

### Cross-model offload
- **agy-bridge** -- [`.agent/skills/agy-bridge/run.py`](../.agent/skills/agy-bridge/run.py): shell out to non-Claude models (agy: Gemini/GPT-OSS; zai: GLM 5.2), capability-routed via [`models.json`](../.agent/skills/agy-bridge/models.json) with a `claude_fallback` tier. **Exit 3 = `{"status":"fallback_to_claude"}` sentinel the caller MUST honor.** Every call logs per-Mtok cost + Claude counterfactual to `dashboard-data/agy_usage_log.jsonl` (`--report` / `localhost:3737` 💸 tab). GLM peak 13:00-17:00 WIB demotes GLM (3x quota). The full capability->model matrix, pricing, and time-routing live in `models.json` + the SOP: [`.agent/skills/agy-bridge/SKILL.md`](../.agent/skills/agy-bridge/SKILL.md).
