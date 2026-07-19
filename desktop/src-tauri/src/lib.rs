mod account;
mod app;
mod bridge;
mod dashboard;
mod providers;
mod viewer;
mod workspace;

// `Manager` brings `.path()` and `.manage()` into scope for `App`/`AppHandle`.
// `Emitter` brings `.emit()` into scope, used to notify the frontend when the
// "Check for Updates" menu item is clicked.
use tauri::{Emitter, Manager};
use tauri::menu::{AboutMetadata, MenuBuilder, PredefinedMenuItem, SubmenuBuilder};
use tauri_plugin_opener::OpenerExt;

const AI_CIRCLE_URL: &str = "https://brianarfi.com/ai-circle";

/// Emitted when the user picks "Check for Updates…" from the native menu. The frontend listens
/// for this and runs the same updater-check path as the silent on-start check, except loud on
/// failure (toast) since this one was explicitly requested.
pub const EVT_CHECK_FOR_UPDATES: &str = "updater:check-requested";

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .setup(|tauri_app| {
            let dir = tauri_app.path().app_data_dir()?;
            std::fs::create_dir_all(&dir)?;
            tauri_app.manage(app::AppState::new(app::SessionStore::load(
                dir.join("sessions.json"),
            )));
            tauri_app.manage(account::AccountStore::load(dir.join("account.json")));
            tauri_app.manage(providers::ProviderStore::load(dir.join("providers.json")));
            // Resolve the workspace root now so it's ready before the frontend calls anything;
            // NotConfigured/Invalid leave the root at `None` and onboarding takes over.
            if let workspace::ResolveOutcome::Resolved { root, .. } = workspace::resolve(&dir) {
                workspace::set_root(root);
            }

            let handle = tauri_app.handle();

            // Heal older/bare workspaces: copy any bundled template command the workspace is
            // missing (never overwrites). Without this, a workspace created by an earlier build
            // shows "No commands found" forever and slash commands do nothing.
            match app::sync_template_commands(handle) {
                Ok(n) if n > 0 => eprintln!("[asb] template sync: copied {n} starter command(s)"),
                Ok(_) => {}
                Err(e) => eprintln!("[asb] template sync skipped: {e}"),
            }

            let about_metadata = AboutMetadata {
                name: Some("AI Second Brain".into()),
                version: Some(env!("CARGO_PKG_VERSION").into()),
                website: Some(AI_CIRCLE_URL.into()),
                comments: Some("Your local-first AI second brain.".into()),
                ..Default::default()
            };

            let edit_menu = SubmenuBuilder::new(handle, "Edit")
                .undo()
                .redo()
                .separator()
                .cut()
                .copy()
                .paste()
                .select_all()
                .build()?;

            let app_menu = SubmenuBuilder::new(handle, "AI Second Brain")
                .item(&PredefinedMenuItem::about(
                    handle,
                    Some("About AI Second Brain"),
                    Some(about_metadata),
                )?)
                .separator()
                .text("check-for-updates", "Check for Updates…")
                .text("visit-ai-circle", "Visit AI Circle")
                .separator()
                .quit()
                .build()?;

            let menu = MenuBuilder::new(handle)
                .item(&app_menu)
                .item(&edit_menu)
                .build()?;

            tauri_app.set_menu(menu)?;

            // Telemetry: record this launch, then flush immediately (best-effort, never blocks
            // startup) and again on a 5-minute interval for the life of the process.
            account::record_event_internal(handle, "app_open", serde_json::json!({}));
            let flush_handle = handle.clone();
            tauri::async_runtime::spawn(async move {
                let state = flush_handle.state::<account::AccountStore>();
                account::flush_events_internal(&state).await;

                let mut ticker = tokio::time::interval(std::time::Duration::from_secs(5 * 60));
                // The first tick fires immediately; the flush above already covers "on start", so
                // skip it here to avoid a redundant back-to-back flush.
                ticker.tick().await;
                loop {
                    ticker.tick().await;
                    let state = flush_handle.state::<account::AccountStore>();
                    account::flush_events_internal(&state).await;
                }
            });

            Ok(())
        })
        .on_menu_event(|app, event| {
            if event.id() == "visit-ai-circle" {
                let _ = app.opener().open_url(AI_CIRCLE_URL, None::<&str>);
            } else if event.id() == "check-for-updates" {
                let _ = app.emit(EVT_CHECK_FOR_UPDATES, ());
            }
        })
        .invoke_handler(tauri::generate_handler![
            app::list_harness_commands,
            app::restore_template_commands,
            app::list_sessions,
            app::new_session,
            app::send_message,
            app::read_image_file,
            app::respond_permission,
            app::respond_question,
            app::interrupt_session,
            app::close_session,
            app::rename_session,
            app::delete_session,
            app::set_session_settings,
            app::get_transcript,
            app::detect_cli,
            app::check_auth,
            app::get_workspace_status,
            app::create_workspace,
            app::choose_workspace,
            app::open_login_terminal,
            viewer::read_workspace_file,
            dashboard::dashboard_summary,
            account::get_account_status,
            account::register_account,
            account::poll_verification,
            account::set_telemetry_opt_out,
            account::record_event,
            account::flush_events,
            providers::list_providers,
            providers::upsert_provider,
            providers::remove_provider,
            providers::test_provider,
            providers::get_multimodal_settings,
            providers::set_multimodal_settings
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
