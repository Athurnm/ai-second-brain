//! Read-only summary for the frontend's Dashboard tab. Aggregates a handful of cheap, local
//! signals (workspace file listings, session history, harness commands, provider config, account
//! status) into one payload the frontend renders without touching disk itself.
//!
//! HARD RULE: never let one bad file take down the whole summary. Every field degrades
//! independently to an empty/default value (missing dir -> `[]`, corrupt JSON -> `[]`, no
//! workspace configured -> everything workspace-derived is empty) rather than returning `Err`.

use serde::Serialize;
use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

/// Cap on how many files a single directory listing (inbox/notes) returns to the frontend.
const MAX_LISTING: usize = 8;
/// Cap on how many entries a ledger file (tasks.json/waiting.json) contributes, guarding against
/// an unexpectedly huge file being parsed in full.
const MAX_LEDGER_ITEMS: usize = 50;
/// Cap on how many bytes of a file are read to find its first non-empty line — a note's opening
/// line is always near the top, so there is never a need to read the whole file.
const FIRST_LINE_READ_CAP: usize = 4096;
/// Cap on the rendered length of a first-line snippet.
const FIRST_LINE_MAX_CHARS: usize = 140;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileEntry {
    pub name: String,
    pub mtime_ms: u64,
    pub first_line: String,
}

#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionStats {
    pub sessions7d: u64,
    pub turns7d: u64,
    pub cost7d_usd: f64,
}

#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AccountSummary {
    pub registered: bool,
    pub phone_verified: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LedgerItem {
    pub title: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub due: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DashboardSummary {
    pub inbox: Vec<FileEntry>,
    pub notes: Vec<FileEntry>,
    pub session_stats: SessionStats,
    pub commands: Vec<String>,
    pub providers: Vec<String>,
    pub claude_ok: bool,
    pub account_status: AccountSummary,
    pub tasks: Vec<LedgerItem>,
    pub waiting: Vec<LedgerItem>,
}

fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// Truncates `s` to at most `max` *characters* (not bytes), appending an ellipsis when it had to
/// cut, so a first-line snippet never splits a multi-byte UTF-8 character mid-codepoint.
fn truncate_chars(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        return s.to_string();
    }
    let mut out: String = s.chars().take(max.saturating_sub(1)).collect();
    out.push('…');
    out
}

/// Reads at most `FIRST_LINE_READ_CAP` bytes of `path` and returns its first non-empty line, with
/// a leading markdown heading marker (`#`, `##`, ...) stripped. Returns `""` on any read failure
/// (missing file, permission error, race with a delete) rather than erroring — this is decoration,
/// not data the caller depends on.
fn first_line_of(path: &Path) -> String {
    use std::io::Read;
    let Ok(mut file) = std::fs::File::open(path) else {
        return String::new();
    };
    let mut buf = vec![0u8; FIRST_LINE_READ_CAP];
    let Ok(n) = file.read(&mut buf) else {
        return String::new();
    };
    buf.truncate(n);
    let text = String::from_utf8_lossy(&buf);
    for line in text.lines() {
        let trimmed = line.trim().trim_start_matches('#').trim();
        if !trimmed.is_empty() {
            return truncate_chars(trimmed, FIRST_LINE_MAX_CHARS);
        }
    }
    String::new()
}

/// Lists the files directly inside `dir` (non-recursive), newest `mtime` first, capped at
/// `MAX_LISTING`. A missing/unreadable directory yields `[]`, never an error — both "workspace
/// has no inbox/ yet" and "workspace has no notes/ yet" are legal states.
fn list_dir_entries(dir: &Path) -> Vec<FileEntry> {
    let Ok(read_dir) = std::fs::read_dir(dir) else {
        return Vec::new();
    };

    let mut entries: Vec<(PathBuf, u64)> = Vec::new();
    for entry in read_dir.flatten() {
        let Ok(meta) = entry.metadata() else { continue };
        if !meta.is_file() {
            continue;
        }
        let mtime_ms = meta
            .modified()
            .ok()
            .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        entries.push((entry.path(), mtime_ms));
    }
    entries.sort_by(|a, b| b.1.cmp(&a.1));
    entries.truncate(MAX_LISTING);

    entries
        .into_iter()
        .map(|(path, mtime_ms)| {
            let name = path
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("")
                .to_string();
            let first_line = first_line_of(&path);
            FileEntry {
                name,
                mtime_ms,
                first_line,
            }
        })
        .collect()
}

/// Tolerantly parses a lightweight ledger file (`journal/tasks.json`, `journal/waiting.json`)
/// into `{title, due, status}` rows. Accepts either a bare JSON array or `{"items": [...]}`.
/// Recognizes a handful of common key spellings per field. A missing file, unparsable JSON, or an
/// entry missing every title-ish key is skipped rather than erroring the whole summary.
fn load_ledger(path: &Path) -> Vec<LedgerItem> {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(value) = serde_json::from_str::<serde_json::Value>(&raw) else {
        return Vec::new();
    };

    let items: Vec<serde_json::Value> = match value {
        serde_json::Value::Array(a) => a,
        serde_json::Value::Object(ref o) => o
            .get("items")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default(),
        _ => Vec::new(),
    };

    items
        .into_iter()
        .take(MAX_LEDGER_ITEMS)
        .filter_map(|v| {
            let obj = v.as_object()?;
            let title = ["title", "name", "task", "description"]
                .iter()
                .find_map(|k| obj.get(*k).and_then(|x| x.as_str()))?
                .to_string();
            let due = ["due", "dueDate", "due_date"]
                .iter()
                .find_map(|k| obj.get(*k).and_then(|x| x.as_str()))
                .map(|s| s.to_string());
            let status = ["status", "state"]
                .iter()
                .find_map(|k| obj.get(*k).and_then(|x| x.as_str()))
                .map(|s| s.to_string());
            Some(LedgerItem { title, due, status })
        })
        .collect()
}

/// Aggregates `sessions.json` history into a rolling 7-day window, keyed off `updated_at_ms`
/// (last activity), not `created_at_ms` — a long-lived session touched today counts as active
/// today even if it was created weeks ago.
fn session_stats(store: &crate::app::SessionStore) -> SessionStats {
    const WEEK_MS: u64 = 7 * 24 * 60 * 60 * 1000;
    let cutoff = now_ms().saturating_sub(WEEK_MS);

    let mut stats = SessionStats::default();
    for meta in store.list() {
        if meta.updated_at_ms >= cutoff {
            stats.sessions7d += 1;
            stats.turns7d += meta.num_turns;
            stats.cost7d_usd += meta.cum_cost_usd;
        }
    }
    stats
}

#[tauri::command]
pub async fn dashboard_summary(app: tauri::AppHandle) -> Result<DashboardSummary, String> {
    use tauri::Manager;

    let root = crate::workspace::root();

    let (inbox, notes, tasks, waiting) = match &root {
        Some(root) => (
            list_dir_entries(&root.join("inbox")),
            list_dir_entries(&root.join("notes")),
            load_ledger(&root.join("journal").join("tasks.json")),
            load_ledger(&root.join("journal").join("waiting.json")),
        ),
        None => (Vec::new(), Vec::new(), Vec::new(), Vec::new()),
    };

    let session_stats = {
        let state = app.state::<crate::app::AppState>();
        session_stats(&state.store)
    };

    let commands = crate::app::list_harness_commands()
        .await
        .unwrap_or_default()
        .into_iter()
        .map(|c| c.name)
        .collect();

    let providers = {
        let store = app.state::<crate::providers::ProviderStore>();
        store
            .list_masked()
            .into_iter()
            .filter(|p| p.config.enabled)
            .map(|p| p.config.label)
            .collect()
    };

    let claude_ok = crate::bridge::resolve_claude_bin().is_ok();

    let account_status = {
        let store = app.state::<crate::account::AccountStore>();
        let snap = store.snapshot();
        AccountSummary {
            registered: snap.registered,
            phone_verified: snap.phone_verified,
        }
    };

    Ok(DashboardSummary {
        inbox,
        notes,
        session_stats,
        commands,
        providers,
        claude_ok,
        account_status,
        tasks,
        waiting,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static COUNTER: AtomicU64 = AtomicU64::new(0);

    struct TempRoot {
        path: PathBuf,
    }

    impl TempRoot {
        fn new() -> TempRoot {
            let n = COUNTER.fetch_add(1, Ordering::SeqCst);
            let path = std::env::temp_dir().join(format!(
                "asb-dashboard-test-{}-{}-{n}",
                std::process::id(),
                n
            ));
            std::fs::create_dir_all(&path).unwrap();
            TempRoot { path }
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.path);
        }
    }

    #[test]
    fn first_line_of_strips_markdown_heading_and_skips_blank_lines() {
        let tmp = TempRoot::new();
        let file = tmp.path.join("note.md");
        std::fs::write(&file, "\n\n## Daily Review\nsome body text").unwrap();
        assert_eq!(first_line_of(&file), "Daily Review");
    }

    #[test]
    fn first_line_of_truncates_long_lines_with_an_ellipsis() {
        let tmp = TempRoot::new();
        let file = tmp.path.join("long.md");
        let long_line = "x".repeat(500);
        std::fs::write(&file, &long_line).unwrap();
        let result = first_line_of(&file);
        assert_eq!(result.chars().count(), FIRST_LINE_MAX_CHARS);
        assert!(result.ends_with('…'));
    }

    #[test]
    fn first_line_of_missing_file_returns_empty_string_not_an_error() {
        let tmp = TempRoot::new();
        let missing = tmp.path.join("does-not-exist.md");
        assert_eq!(first_line_of(&missing), "");
    }

    #[test]
    fn list_dir_entries_missing_dir_returns_empty_vec() {
        let tmp = TempRoot::new();
        let missing = tmp.path.join("no-such-dir");
        assert!(list_dir_entries(&missing).is_empty());
    }

    #[test]
    fn list_dir_entries_sorts_newest_first_and_caps_at_max_listing() {
        let tmp = TempRoot::new();
        let dir = tmp.path.join("inbox");
        std::fs::create_dir_all(&dir).unwrap();
        for i in 0..(MAX_LISTING + 4) {
            let path = dir.join(format!("f{i}.md"));
            std::fs::write(&path, format!("line {i}")).unwrap();
        }
        let entries = list_dir_entries(&dir);
        assert_eq!(entries.len(), MAX_LISTING);
        // Sorted newest-mtime-first: never increasing as we walk the list.
        for pair in entries.windows(2) {
            assert!(pair[0].mtime_ms >= pair[1].mtime_ms);
        }
    }

    #[test]
    fn list_dir_entries_ignores_subdirectories() {
        let tmp = TempRoot::new();
        let dir = tmp.path.join("notes");
        std::fs::create_dir_all(dir.join("subdir")).unwrap();
        std::fs::write(dir.join("a.md"), "hello").unwrap();
        let entries = list_dir_entries(&dir);
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].name, "a.md");
    }

    #[test]
    fn load_ledger_missing_file_returns_empty_vec() {
        let tmp = TempRoot::new();
        let missing = tmp.path.join("tasks.json");
        assert!(load_ledger(&missing).is_empty());
    }

    #[test]
    fn load_ledger_corrupt_json_returns_empty_vec_not_an_error() {
        let tmp = TempRoot::new();
        let file = tmp.path.join("tasks.json");
        std::fs::write(&file, "{ not valid json").unwrap();
        assert!(load_ledger(&file).is_empty());
    }

    #[test]
    fn load_ledger_parses_a_bare_array_with_common_key_spellings() {
        let tmp = TempRoot::new();
        let file = tmp.path.join("tasks.json");
        std::fs::write(
            &file,
            r#"[
                {"title": "Draft proposal", "due": "2026-07-20", "status": "open"},
                {"name": "Send recap", "dueDate": "2026-07-21"}
            ]"#,
        )
        .unwrap();
        let items = load_ledger(&file);
        assert_eq!(items.len(), 2);
        assert_eq!(items[0].title, "Draft proposal");
        assert_eq!(items[0].due.as_deref(), Some("2026-07-20"));
        assert_eq!(items[0].status.as_deref(), Some("open"));
        assert_eq!(items[1].title, "Send recap");
        assert_eq!(items[1].due.as_deref(), Some("2026-07-21"));
        assert!(items[1].status.is_none());
    }

    #[test]
    fn load_ledger_parses_wrapped_items_object_shape() {
        let tmp = TempRoot::new();
        let file = tmp.path.join("waiting.json");
        std::fs::write(&file, r#"{"items": [{"task": "Nudge finance"}]}"#).unwrap();
        let items = load_ledger(&file);
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].title, "Nudge finance");
    }

    #[test]
    fn load_ledger_skips_entries_with_no_recognizable_title_key() {
        let tmp = TempRoot::new();
        let file = tmp.path.join("tasks.json");
        std::fs::write(&file, r#"[{"due": "2026-07-20"}, {"title": "Kept"}]"#).unwrap();
        let items = load_ledger(&file);
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].title, "Kept");
    }

    #[test]
    fn load_ledger_caps_at_max_ledger_items() {
        let tmp = TempRoot::new();
        let file = tmp.path.join("tasks.json");
        let arr: Vec<String> = (0..(MAX_LEDGER_ITEMS + 20))
            .map(|i| format!(r#"{{"title": "t{i}"}}"#))
            .collect();
        std::fs::write(&file, format!("[{}]", arr.join(","))).unwrap();
        let items = load_ledger(&file);
        assert_eq!(items.len(), MAX_LEDGER_ITEMS);
    }

    #[test]
    fn session_stats_counts_only_sessions_updated_within_the_last_7_days() {
        let mut path = std::env::temp_dir();
        path.push(format!(
            "asb_dashboard_sessionstats_{}.json",
            uuid::Uuid::new_v4()
        ));
        let _ = std::fs::remove_file(&path);
        let store = crate::app::SessionStore::load(path.clone());

        let now = now_ms();
        let eight_days_ago = now.saturating_sub(8 * 24 * 60 * 60 * 1000);

        let recent = crate::app::SessionMeta {
            session_id: "recent".to_string(),
            title: "Recent".to_string(),
            created_at_ms: now,
            updated_at_ms: now,
            num_turns: 5,
            cum_cost_usd: 1.5,
            ..Default::default()
        };
        let stale = crate::app::SessionMeta {
            session_id: "stale".to_string(),
            title: "Stale".to_string(),
            created_at_ms: eight_days_ago,
            updated_at_ms: eight_days_ago,
            num_turns: 99,
            cum_cost_usd: 99.0,
            ..Default::default()
        };
        store.upsert(recent);
        store.upsert(stale);

        let stats = session_stats(&store);
        assert_eq!(stats.sessions7d, 1);
        assert_eq!(stats.turns7d, 5);
        assert!((stats.cost7d_usd - 1.5).abs() < f64::EPSILON);

        let _ = std::fs::remove_file(&path);
    }
}
