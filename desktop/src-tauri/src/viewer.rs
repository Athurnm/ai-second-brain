//! Built-in file viewer: reads a single file from inside the current workspace for display in
//! the frontend's `#viewer` modal (images, markdown, text/code, sandboxed html, or a
//! "open externally" fallback for pdf/other). Zero Tauri dependencies in the path-guard/
//! classification logic (mirrors `workspace.rs`) so it can be unit tested directly.

use std::path::{Path, PathBuf};

/// Hard cap on what the viewer will read into memory / ship over IPC. Generous for a text/code
/// file or a reasonably-sized image; a backstop against accidentally opening something huge.
const MAX_VIEWABLE_BYTES: u64 = 15 * 1024 * 1024; // 15MB

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkspaceFile {
    /// "image" | "markdown" | "text" | "html" | "pdf" | "other"
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub base64: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub text: Option<String>,
    pub media_type: String,
    pub file_name: String,
    /// Canonicalized absolute path, handed back so the frontend's "Open externally" button can
    /// pass it straight to `plugin:opener|open_path` without re-deriving it.
    pub path: String,
}

/// Resolves `requested` (absolute, or relative to `root`) to a canonical path that is guaranteed
/// to sit inside `root`. Canonicalization alone is what makes `..` traversal safe to reject: any
/// `..` component collapses out before the `starts_with` check runs, so there is no separate
/// string-based "contains .." check to get wrong.
fn resolve_safe_path(root: &Path, requested: &str) -> Result<PathBuf, String> {
    let root_canon = root
        .canonicalize()
        .map_err(|e| format!("workspace root invalid: {e}"))?;

    let candidate = Path::new(requested);
    let joined = if candidate.is_absolute() {
        candidate.to_path_buf()
    } else {
        root.join(candidate)
    };

    let canon = joined
        .canonicalize()
        .map_err(|e| format!("cannot resolve {}: {e}", joined.display()))?;

    if canon.starts_with(&root_canon) {
        Ok(canon)
    } else {
        Err(format!("path is outside the workspace: {requested}"))
    }
}

/// Classifies a (lowercased) file extension into a viewer `kind` + best-guess media type.
fn classify_extension(ext: &str) -> (&'static str, &'static str) {
    match ext.to_ascii_lowercase().as_str() {
        "png" => ("image", "image/png"),
        "jpg" | "jpeg" => ("image", "image/jpeg"),
        "gif" => ("image", "image/gif"),
        "webp" => ("image", "image/webp"),
        "bmp" => ("image", "image/bmp"),
        "svg" => ("image", "image/svg+xml"),
        "md" | "markdown" => ("markdown", "text/markdown"),
        "html" | "htm" => ("html", "text/html"),
        "pdf" => ("pdf", "application/pdf"),
        "txt" | "csv" | "log" | "json" | "js" | "ts" | "jsx" | "tsx" | "rs" | "py" | "sh"
        | "yaml" | "yml" | "toml" | "css" | "xml" | "ini" | "conf" => ("text", "text/plain"),
        _ => ("other", "application/octet-stream"),
    }
}

fn read_workspace_file_inner(root: &Path, requested: &str) -> Result<WorkspaceFile, String> {
    let canon = resolve_safe_path(root, requested)?;

    let meta = std::fs::metadata(&canon).map_err(|e| format!("cannot read {}: {e}", canon.display()))?;
    if !meta.is_file() {
        return Err(format!("{} is not a file", canon.display()));
    }
    if meta.len() > MAX_VIEWABLE_BYTES {
        return Err(format!(
            "{} is {} bytes, over the {MAX_VIEWABLE_BYTES} byte viewer limit",
            canon.display(),
            meta.len()
        ));
    }

    let ext = canon.extension().and_then(|e| e.to_str()).unwrap_or("");
    let (kind, media_type) = classify_extension(ext);
    let file_name = canon
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("file")
        .to_string();
    let path = canon.to_string_lossy().to_string();

    match kind {
        "image" => {
            let bytes = std::fs::read(&canon).map_err(|e| e.to_string())?;
            use base64::Engine;
            let base64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
            Ok(WorkspaceFile {
                kind: kind.to_string(),
                base64: Some(base64),
                text: None,
                media_type: media_type.to_string(),
                file_name,
                path,
            })
        }
        "markdown" | "text" | "html" => {
            // Lossy fallback rather than erroring on a stray non-UTF8 byte — a viewer is
            // best-effort display, not a byte-exact editor round-trip.
            let bytes = std::fs::read(&canon).map_err(|e| e.to_string())?;
            let text = String::from_utf8_lossy(&bytes).to_string();
            Ok(WorkspaceFile {
                kind: kind.to_string(),
                base64: None,
                text: Some(text),
                media_type: media_type.to_string(),
                file_name,
                path,
            })
        }
        _ => Ok(WorkspaceFile {
            kind: kind.to_string(),
            base64: None,
            text: None,
            media_type: media_type.to_string(),
            file_name,
            path,
        }),
    }
}

#[tauri::command]
pub async fn read_workspace_file(path: String) -> Result<WorkspaceFile, String> {
    let root = crate::workspace::root().ok_or_else(|| "workspace not configured".to_string())?;
    tauri::async_runtime::spawn_blocking(move || read_workspace_file_inner(&root, &path))
        .await
        .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static COUNTER: AtomicU64 = AtomicU64::new(0);

    /// Unique-per-test scratch dir under the OS temp dir, cleaned up on drop.
    struct TempRoot {
        path: PathBuf,
    }

    impl TempRoot {
        fn new() -> TempRoot {
            let n = COUNTER.fetch_add(1, Ordering::SeqCst);
            let path = std::env::temp_dir().join(format!(
                "asb-viewer-test-{}-{}-{n}",
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
    fn resolve_safe_path_allows_a_file_inside_the_workspace() {
        let tmp = TempRoot::new();
        let root = tmp.path.join("workspace");
        std::fs::create_dir_all(root.join("notes")).unwrap();
        std::fs::write(root.join("notes").join("a.md"), b"hello").unwrap();

        let resolved = resolve_safe_path(&root, "notes/a.md").expect("should resolve");
        assert_eq!(resolved, root.join("notes").join("a.md").canonicalize().unwrap());
    }

    #[test]
    fn resolve_safe_path_rejects_dot_dot_traversal() {
        let tmp = TempRoot::new();
        let root = tmp.path.join("workspace");
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(tmp.path.join("secret.txt"), b"nope").unwrap();

        let err = resolve_safe_path(&root, "../secret.txt").unwrap_err();
        assert!(err.contains("outside the workspace"));
    }

    #[test]
    fn resolve_safe_path_rejects_an_absolute_path_outside_the_workspace() {
        let tmp = TempRoot::new();
        let root = tmp.path.join("workspace");
        std::fs::create_dir_all(&root).unwrap();
        let outside = tmp.path.join("outside.txt");
        std::fs::write(&outside, b"nope").unwrap();

        let err = resolve_safe_path(&root, outside.to_str().unwrap()).unwrap_err();
        assert!(err.contains("outside the workspace"));
    }

    #[test]
    fn resolve_safe_path_allows_an_absolute_path_inside_the_workspace() {
        let tmp = TempRoot::new();
        let root = tmp.path.join("workspace");
        std::fs::create_dir_all(&root).unwrap();
        let inside = root.join("inside.txt");
        std::fs::write(&inside, b"yep").unwrap();

        let resolved = resolve_safe_path(&root, inside.to_str().unwrap()).expect("should resolve");
        assert_eq!(resolved, inside.canonicalize().unwrap());
    }

    #[test]
    fn classify_extension_covers_the_documented_kinds() {
        assert_eq!(classify_extension("png").0, "image");
        assert_eq!(classify_extension("JPG").0, "image");
        assert_eq!(classify_extension("md").0, "markdown");
        assert_eq!(classify_extension("html").0, "html");
        assert_eq!(classify_extension("pdf").0, "pdf");
        assert_eq!(classify_extension("txt").0, "text");
        assert_eq!(classify_extension("bin").0, "other");
    }

    #[test]
    fn read_workspace_file_inner_reads_a_markdown_file_as_text() {
        let tmp = TempRoot::new();
        let root = tmp.path.join("workspace");
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(root.join("note.md"), b"# Hello").unwrap();

        let file = read_workspace_file_inner(&root, "note.md").expect("should read");
        assert_eq!(file.kind, "markdown");
        assert_eq!(file.text.as_deref(), Some("# Hello"));
        assert_eq!(file.file_name, "note.md");
    }

    #[test]
    fn read_workspace_file_inner_rejects_a_file_over_the_size_cap() {
        let tmp = TempRoot::new();
        let root = tmp.path.join("workspace");
        std::fs::create_dir_all(&root).unwrap();
        let big = vec![0u8; (MAX_VIEWABLE_BYTES + 1) as usize];
        std::fs::write(root.join("big.txt"), &big).unwrap();

        let err = read_workspace_file_inner(&root, "big.txt").unwrap_err();
        assert!(err.contains("byte viewer limit"));
    }

    #[test]
    fn read_workspace_file_inner_rejects_traversal_outside_the_workspace() {
        let tmp = TempRoot::new();
        let root = tmp.path.join("workspace");
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(tmp.path.join("secret.txt"), b"nope").unwrap();

        let err = read_workspace_file_inner(&root, "../secret.txt").unwrap_err();
        assert!(err.contains("outside the workspace"));
    }
}
