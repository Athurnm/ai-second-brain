# Browser-Service Upgrade Plan — anti-bot, authed, structured scraping

> Status: **SCOPING ONLY** (approved 2026-06-29). No scraper code is written until You greenlights a specific use case. Modeled on a deep read of `github.com/garrytan/gstack` `browse/src/*.ts` (60 files).

## Why

Today's `browser-service` ([scripts/ensure_cdp.sh](scripts/ensure_cdp.sh)) launches **headless Chromium on CDP `127.0.0.1:9222`** with a static UA and a **single shared `--user-data-dir`** (`~/.config/antigravity-chrome-data`), driven by the `browser_subagent` tool. Three gaps block the real jobs You needs:

- **No stealth** — the launch keeps Playwright/automation tells (`navigator.webdriver`, missing `window.chrome.*`, `--enable-automation` not stripped). Cloudflare/DataDome on LinkedIn and e-commerce sites block it.
- **No auth-session import** — no way to reuse a logged-in Chrome session, so authed scraping (LinkedIn, competitor portals) is impossible without scripting fragile logins + 2FA.
- **One shared profile** — Work and You scraping would share cookies/state, **violating the hard Work⟂You data-separation rule**.

We do **not** rebuild gstack's persistent Bun daemon. We own the CDP socket directly, so each technique below drops in via `ensure_cdp.sh` launch flags + CDP commands (`Page.addScriptToEvaluateOnNewDocument`, `Network.*`) — no dependency on the (uninstalled) `agent-browser` CLI.

## Target use cases

- **(a)** Marketplace competitor-price scraping — authed, anti-bot, structured data. **Work-scoped.**
- **(b)** Live SEO render checks on you.com — render a JS page, read DOM/meta. **You-scoped.**
- **(c)** LinkedIn trend scraping for content research — authed session, infinite scroll, anti-bot. **You-scoped.**

## The 7 imitable techniques (ranked value × ease)

| # | Technique (gstack source → mechanism) | Use case | Where it lands in PSB | Effort |
|:--|:--|:--|:--|:--|
| 1 | **Stealth init-script** — `stealth.ts` `buildStealthScript`: `Function.prototype.toString` Proxy (defeats depth-3 `[native code]` check), `navigator.webdriver`→false, restore `window.chrome.runtime/app/csi/loadTimes` with full enum shape, strip `cdc_*`/`__webdriver*` globals (twice: immediate + `setTimeout 0`). **Rule: do NOT fake `navigator.plugins`/`languages`** — fingerprinters cross-check these and faking flags *more* bot-like. | (a)(c) | (i) add launch flags `--disable-blink-features=AutomationControlled` + strip default `--enable-automation`/`--disable-extensions` to `ensure_cdp.sh`; (ii) send the JS layer via CDP `Page.addScriptToEvaluateOnNewDocument` once per session before navigation. | Low |
| 2 | **Cookie import from real browser** — `cookie-import-browser.ts`: decrypt installed-Chrome cookies → feed `Network.setCookie`. **CAVEAT: You browses from Windows into WSL → cookies live in the Windows Chrome profile.** Use the **Windows DPAPI** path (DPAPI-decrypt `os_crypt.encrypted_key` from `Local State` via PowerShell `ProtectedData::Unprotect`, then AES-256-GCM), OR the **Chrome-127+ v20 fallback** (launch Chrome headless on the real profile with `--remote-debugging-port`, pull `Network.getAllCookies` over CDP). The simple Linux libsecret + AES-128-CBC path does NOT apply here. | (a)(c) | New `scripts/import_cookies.py` (or `.ps1` wrapper via `wsl.exe`) → emits a cookie JSON → loaded via CDP `Network.setCookie` per scrape session. | Med |
| 3 | **Network/XHR JSON capture** — `network-capture.ts`: filtered `page.on('response')` (Playwright) / CDP `Network.responseReceived` + `Network.getResponseBody`, stored in a size-capped FIFO buffer (50MB/5MB caps) → JSONL. Reads clean price JSON from the site's own API instead of parsing obfuscated DOM. | (a) | New `scripts/net_capture.py` enabling `Network` domain on the CDP session + a URL-regex filter → JSONL. ~30 lines. | Low |
| 4 | **AX-snapshot upgrades** — `snapshot.ts`: server-side `getByRole`+`.nth()` Locator map, `count()===0` fail-fast staleness (~5ms vs 30s), `-D` unified-diff vs last snapshot (verify a click worked), `-C` cursor/portal scan (`cursor:pointer`/`onclick`/`tabindex>=0` + Radix/floating-ui portals) for dropdowns the AX tree misses. | (b)(c) | Enhancement to whatever the `browser_subagent` tool returns; the `-C` portal scan + `-D` diff are the high-value adds for LinkedIn's React dropdowns. | Med |
| 5 | **Persistent + SEPARATED session profiles** — gstack `launchPersistentContext(userDataDir)`. PSB already passes `--user-data-dir` but **shares one profile**. Split into per-scope profiles so cookies/state never cross the firewall. | (c)(a) | `ensure_cdp.sh` takes a `--profile work|you` arg → `~/.config/psb-chrome/<scope>`; separate CDP ports per scope so two scopes can't share a live context. | Low |
| 6 | **Untrusted-content envelope** — `content-security.ts` L1–L3: wrap every page snapshot in `═══ BEGIN/END UNTRUSTED WEB CONTENT ═══` (escape the sentinels if the page itself forges them), strip hidden elements (opacity<0.1, font<1px, off-screen), ARIA injection-regex (`/ignore (previous\|all) instructions/i`). A scraping agent reads attacker-controlled text; this is the cheap deterministic guard before any LLM reads it. | (a)(c) | A wrapper applied to snapshot output before it re-enters the agent context. For the ML-judge layer gstack runs (112MB ONNX), **substitute a haiku critic via `agy-bridge --task critic`** — do NOT port the model. | Low |
| 7 | **Deny-default CDP allowlist + headed CAPTCHA handoff** — `cdp-allowlist.ts`: whitelist `Domain.method`, **block** `Runtime.evaluate`/`callFunctionOn` (=RCE), `Page.navigate` (bypasses URL blocklist), `Network.getResponseBody`/`getCookies` (exfil), `Target.*`, `Fetch.*`. Plus the `resume` flow: on CAPTCHA/2FA open visible Chrome, You solves, resume with state intact. | (c) | A small allowlist JSON the Python wrapper checks before dispatching any raw CDP method; a headed-relaunch path for CAPTCHA. | Low (policy) |

## What we explicitly do NOT port
- gstack's **C++ Chromium patches** (`--gstack-gpu-vendor`, `--gstack-ua-platform`) — needs a forked Chromium build; out of reach and unnecessary.
- **PTY/SSE session-cookie registries** (`pty-session-cookie.ts`) — only relevant to gstack's headed sidebar UI.
- The **112MB/721MB ONNX injection classifiers** — substitute `agy-bridge` haiku/GLM critic (technique #6).

## Recommended build order
Fastest path to an authed, anti-bot, structured scraper:
1. **#1 stealth** (launch flags + CDP init-script) — unblocks anti-bot sites
2. **#2 cookie import** (Windows DPAPI / v20 fallback) — gives an authed session
3. **#3 network capture** — clean structured extraction

Then **#5 separated persistent profiles**, **#4 snapshot diff/cursor-scan**, **#6 untrusted envelope**. **#7 allowlist** is policy, adopt alongside #1.

## Open question to resolve before any build
The current driver is the `browser_subagent` tool over CDP 9222 (the `agent-browser` CLI named in CLAUDE.md is **not installed**). Confirm whether stealth/cookie/network steps run as: (A) a Python wrapper that opens its own CDP client to 9222 around `browser_subagent` calls, or (B) extending `ensure_cdp.sh` for launch-level changes + a one-shot CDP injector script for per-session steps. **Recommendation: B for launch flags + profiles (#1 flags, #5), a Python CDP injector for #1 JS / #2 / #3 / #6.**

## Data-separation guardrail (non-negotiable)
- Work scraping (a) uses profile `~/.config/psb-chrome/work`; You (b)(c) uses `~/.config/psb-chrome/you`. **Never one shared profile.**
- Cookie imports are scoped per source; a Work competitor-portal cookie never lands in the You profile and vice versa.
- Captured data writes to scope-tagged paths; no cross-scope index (same reason the RAG KB was dropped in hyperplan).

## Source mirror
gstack browser source mirrored for extracting concrete ports at:
`/tmp/claude-1000/-home-you-antigravity-projects-product-second-brain/4c1e8675-e8b0-4594-ae52-b76dcbca5e5b/scratchpad/gstack/`
