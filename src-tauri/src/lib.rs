use std::net::TcpStream;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};

const SERVER_HOST: &str = "127.0.0.1";
const SERVER_PORT: u16 = 8800;
const DASHBOARD_URL: &str = "http://localhost:8800/dashboard";
const READY_TIMEOUT_SECS: u64 = 120;

// Holds the sidecar child process so we can kill it on exit.
struct ServerProcess(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(ServerProcess(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            // Spawn the server management in a background thread so setup() returns
            // quickly and Tauri can render the splash screen while we wait.
            std::thread::spawn(move || {
                manage_server(handle);
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if window.label() == "main" {
                    if let Some(state) = window.try_state::<ServerProcess>() {
                        let mut guard = state.0.lock().unwrap();
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Minder");
}

fn manage_server(app: AppHandle) {
    // Try to start the bundled sidecar. In dev mode (no binary present) this
    // will fail — we fall back to expecting the user to run the server manually.
    let child = try_start_sidecar(&app);

    if let Some(child) = child {
        // Store so we can kill it when the window closes.
        if let Some(state) = app.try_state::<ServerProcess>() {
            *state.0.lock().unwrap() = Some(child);
        }
    }

    // Poll until the server's TCP port is accepting connections.
    let ready = wait_for_server(SERVER_HOST, SERVER_PORT, READY_TIMEOUT_SECS);

    let window = match app.get_webview_window("main") {
        Some(w) => w,
        None => return,
    };

    if ready {
        // Navigate to the dashboard and show the window.
        let url: tauri::Url = DASHBOARD_URL.parse().expect("valid dashboard URL");
        let _ = window.navigate(url);
        let _ = window.show();
    } else {
        // Server didn't come up — show the window with an error overlay.
        let msg = format!(
            "Server did not start within {} seconds. \
             Run 'make native-run' in a terminal and restart the app.",
            READY_TIMEOUT_SECS
        );
        let escaped = msg.replace('\'', "\\'");
        let _ = window.eval(&format!("window.__minderError('{escaped}')"));
        let _ = window.show();
    }
}

fn try_start_sidecar(
    app: &AppHandle,
) -> Option<tauri_plugin_shell::process::CommandChild> {
    use tauri_plugin_shell::ShellExt;

    let sidecar = match app.shell().sidecar("minder-server") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("[minder] sidecar not available (dev mode?): {e}");
            return None;
        }
    };

    match sidecar.spawn() {
        Ok((_rx, child)) => {
            eprintln!("[minder] sidecar started (pid={})", child.pid());
            Some(child)
        }
        Err(e) => {
            eprintln!("[minder] failed to spawn sidecar: {e}");
            None
        }
    }
}

fn wait_for_server(host: &str, port: u16, timeout_secs: u64) -> bool {
    let addr = format!("{host}:{port}");
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);

    while Instant::now() < deadline {
        if TcpStream::connect_timeout(
            &addr.parse().expect("valid addr"),
            Duration::from_millis(200),
        )
        .is_ok()
        {
            eprintln!("[minder] server ready at {addr}");
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }

    eprintln!("[minder] server not ready after {timeout_secs}s");
    false
}
