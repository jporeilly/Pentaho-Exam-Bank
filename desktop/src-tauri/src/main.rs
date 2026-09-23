// Windows desktop shell for the Pentaho Exam Bank.
//
// The app is a FastAPI server serving a React SPA. This shell exists to make
// that look like a desktop program: it starts the bundled Python on a free
// port, shows a startup page while it comes up, and navigates the window to
// the server once it answers. Everything after that is the same app a
// checkout serves from run.bat, which is what stops the two builds drifting.
//
// The interesting part is the failure path. A window that stays blank is the
// worst possible bug report, so the startup page shows the backend's own
// output while it waits and, if it never comes up, what the shell resolved
// and what Python said.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod server;

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use server::{last_server_output, Server};
use tauri::{Manager, State};

type SharedServer = Arc<Mutex<Option<Server>>>;

struct AppState {
    server: SharedServer,
}

/// Strip Windows' verbatim `\\?\` prefix.
///
/// Tauri's `resource_dir()` canonicalises, which on Windows yields an
/// extended-length path like `\\?\C:\Program Files\...`. Those are legal for
/// most file APIs and the shell's own `is_file()` checks pass happily - which
/// is why the suite's first packaged app reported everything found while
/// nothing worked.
///
/// They are NOT legal as a process WORKING DIRECTORY: `SetCurrentDirectory`
/// rejects the verbatim form, so `boot.py`'s `os.chdir()` raises and the
/// server dies before uvicorn binds a port.
///
/// Only safe to strip for ordinary drive paths - a genuine UNC (`\\?\UNC\...`)
/// or a >260-char path still needs the prefix.
fn strip_verbatim(p: &Path) -> PathBuf {
    let s = p.to_string_lossy();
    if let Some(rest) = s.strip_prefix(r"\\?\") {
        let bytes = rest.as_bytes();
        let drive_path = bytes.len() >= 3
            && bytes[0].is_ascii_alphabetic()
            && bytes[1] == b':'
            && bytes[2] == b'\\';
        if drive_path && rest.len() < 250 {
            return PathBuf::from(rest);
        }
    }
    p.to_path_buf()
}

/// Where the app root (exam_bank/ + frontend/dist/) lives.
///
/// Packaged: bundle.resources drops the staged tree beside the executable.
/// Dev (`npm run tauri:dev`): walk up to the checkout and use it in place, so
/// there is no build step between editing Python and seeing the change.
fn app_dir(handle: &tauri::AppHandle) -> PathBuf {
    if let Ok(res) = handle.path().resource_dir() {
        let packaged = strip_verbatim(&res.join("app"));
        if packaged.join("exam_bank").join("api").join("app.py").is_file() {
            return packaged;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("..")
}

/// boot.py - staged inside the app tree, or taken from the checkout in dev.
/// Mirrors app_dir()'s packaged-then-checkout resolution deliberately: one
/// rule applied twice beats two rules that can disagree about which tree is
/// live.
fn boot_py(handle: &tauri::AppHandle) -> PathBuf {
    if let Ok(res) = handle.path().resource_dir() {
        let packaged = strip_verbatim(&res.join("app").join("boot.py"));
        if packaged.is_file() {
            return packaged;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join("boot.py")
}

/// Per-user data directory: the bank's database, its config and its backups.
///
/// Program Files is not writable, and utils/config.py creates these at import
/// - so this is not a preference, it is what stops the app dying on startup.
fn state_dir(handle: &tauri::AppHandle) -> PathBuf {
    handle
        .path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
}

/// The startup page polls this until the server answers, then navigates.
#[tauri::command]
fn server_url(state: State<'_, AppState>) -> Option<String> {
    state.server.lock().ok()?.as_ref().map(|s| s.url())
}

/// The backend's output so far, for the startup page to show WHILE it waits.
///
/// Deliberately separate from `diagnostics`, which stats several paths: this
/// is polled every few hundred milliseconds. It also means the startup screen
/// shows what is really happening - uvicorn's own "Application startup
/// complete" - rather than a bar that moves whether or not anything works.
#[tauri::command]
fn server_log() -> Vec<String> {
    last_server_output()
}

/// False once the backend process has exited. Lets the startup page fail fast
/// on a dead server instead of waiting out a timeout meant for a slow one.
#[tauri::command]
fn server_alive(state: State<'_, AppState>) -> bool {
    let Ok(mut guard) = state.server.lock() else {
        return true;
    };
    match guard.as_mut() {
        Some(srv) => !matches!(srv.exited(), Some(true)),
        None => false,
    }
}

/// Is the backend actually answering HTTP?
///
/// Asked of Rust rather than fetched from the page: see `server::http_ok` for
/// why a cross-origin fetch from a tauri:// page can never succeed here.
#[tauri::command]
fn server_ready(state: State<'_, AppState>) -> bool {
    let Ok(guard) = state.server.lock() else {
        return false;
    };
    match guard.as_ref() {
        // /api/version is the cheapest endpoint that proves the app is
        // assembled: it touches no database and no model.
        Some(srv) => server::http_ok(srv.port, "/api/version"),
        None => false,
    }
}

/// What the shell resolved, for a startup that never finished.
#[tauri::command]
fn diagnostics(handle: tauri::AppHandle) -> serde_json::Value {
    let app = app_dir(&handle);
    let boot = boot_py(&handle);
    let state = state_dir(&handle);
    let resource = strip_verbatim(&handle.path().resource_dir().unwrap_or_default());
    let python = resource.join("python").join("python.exe");

    serde_json::json!({
        "appDir": app.to_string_lossy(),
        "appDirOk": app.join("exam_bank").join("api").join("app.py").is_file(),
        "uiOk": app.join("frontend").join("dist").join("index.html").is_file(),
        "bootPy": boot.to_string_lossy(),
        "bootPyOk": boot.is_file(),
        "python": python.to_string_lossy(),
        // Absent in a dev run, which falls back to PATH - so this being
        // false is only a problem in a packaged build.
        "pythonOk": python.is_file(),
        "stateDir": state.to_string_lossy(),
        "log": last_server_output(),
    })
}

/// Open the folder holding the database, config and backups.
///
/// Worth a button: it is not beside the app, and an author looking for their
/// bank would otherwise search Program Files and find nothing.
#[tauri::command]
fn open_state_dir(handle: tauri::AppHandle) -> String {
    let dir = state_dir(&handle);
    std::fs::create_dir_all(&dir).ok();
    let shown = dir.to_string_lossy().into_owned();
    let _ = tauri_plugin_opener::open_path(&shown, None::<&str>);
    shown
}

fn reveal_now(handle: &tauri::AppHandle) {
    if let Some(window) = handle.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

/// Show the window. The window starts hidden so a failed start is never a
/// bare white rectangle; the startup page calls this once it has painted.
#[tauri::command]
fn reveal(handle: tauri::AppHandle) {
    reveal_now(&handle);
}

/// Show the window whatever happens.
///
/// If the startup page itself fails to load - a broken bundle, a webview that
/// never runs the script - nothing would ever call `reveal`, and the app would
/// be a process with no window and no way to say why. A few seconds is long
/// enough for any real startup and short enough not to be noticed.
fn reveal_watchdog(handle: tauri::AppHandle) {
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_secs(4));
        reveal_now(&handle);
    });
}

fn main() {
    let shared: SharedServer = Arc::new(Mutex::new(None));
    let for_close = shared.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(AppState {
            server: shared.clone(),
        })
        .invoke_handler(tauri::generate_handler![
            server_url,
            server_log,
            server_alive,
            server_ready,
            diagnostics,
            open_state_dir,
            reveal
        ])
        .setup(move |app| {
            let handle = app.handle().clone();
            reveal_watchdog(handle.clone());
            let resource_dir = strip_verbatim(&handle.path().resource_dir().unwrap_or_default());
            let app_dir = app_dir(&handle);
            let boot_py = boot_py(&handle);
            let state_dir = state_dir(&handle);
            std::fs::create_dir_all(&state_dir).ok();

            match Server::start(&resource_dir, &boot_py, &app_dir, &state_dir) {
                Ok(srv) => {
                    *shared.lock().unwrap() = Some(srv);
                }
                Err(e) => {
                    // Do not abort: the startup page reports this alongside
                    // the diagnostics, which is far more useful than a window
                    // that never appears.
                    eprintln!("failed to start the backend: {e}");
                }
            }
            Ok(())
        })
        .on_window_event(move |_window, event| {
            // Stop the server on close rather than waiting for process exit,
            // so the port and the database lock are free immediately if the
            // author relaunches.
            if let tauri::WindowEvent::Destroyed = event {
                if let Ok(mut guard) = for_close.lock() {
                    if let Some(srv) = guard.as_mut() {
                        srv.stop();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running the Pentaho Exam Bank shell");
}
