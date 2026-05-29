use std::net::TcpStream;
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandEvent;

const SERVER_HOST: &str = "127.0.0.1";
const SERVER_PORT: u16 = 8800;
const DASHBOARD_URL: &str = "http://localhost:8800/dashboard";
const READY_TIMEOUT_SECS: u64 = 120;

// Holds the sidecar child process so we can kill it on exit.
struct ServerProcess(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);

// Shared bootstrap logs in memory for the diagnostics UI.
struct BootstrapLogs(Arc<Mutex<Vec<String>>>);

#[tauri::command]
fn get_bootstrap_logs(state: tauri::State<'_, BootstrapLogs>) -> Vec<String> {
    let guard = state.0.lock().unwrap();
    guard.clone()
}

#[tauri::command]
fn get_bootstrap_config() -> serde_json::Value {
    serde_json::json!({
        "host": SERVER_HOST,
        "port": SERVER_PORT,
        "dashboard_url": DASHBOARD_URL,
    })
}

pub fn run() {
    let log_buffer = Arc::new(Mutex::new(Vec::<String>::new()));
    let log_buffer_for_state = log_buffer.clone();
    let log_buffer_for_manage = log_buffer.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(ServerProcess(Mutex::new(None)))
        .manage(BootstrapLogs(log_buffer_for_state))
        .invoke_handler(tauri::generate_handler![get_bootstrap_logs, get_bootstrap_config])
        .setup(|app| {
            let handle = app.handle().clone();
            // Spawn the server management in a background thread so setup() returns
            // quickly and Tauri can render the splash screen while we wait.
            std::thread::spawn(move || {
                manage_server(handle, log_buffer_for_manage);
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            match event {
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    if window.label() == "main" {
                        // Hide the window instead of closing it so the
                        // Python sidecar keeps running in the background.
                        api.prevent_close();
                        let _ = window.hide();
                    }
                }
                tauri::WindowEvent::Destroyed => {
                    // Window is being destroyed (app is truly quitting).
                    // Kill the sidecar so it doesn't linger as an orphan.
                    if window.label() == "main" {
                        if let Some(state) = window.try_state::<ServerProcess>() {
                            let mut guard = state.0.lock().unwrap();
                            if let Some(child) = guard.take() {
                                let _ = child.kill();
                            }
                        }
                    }
                }
                _ => {}
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            match event {
                tauri::RunEvent::Exit => {
                    if let Some(state) = app_handle.try_state::<ServerProcess>() {
                        let mut guard = state.0.lock().unwrap();
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
                tauri::RunEvent::ExitRequested { .. } => {
                    if let Some(state) = app_handle.try_state::<ServerProcess>() {
                        let mut guard = state.0.lock().unwrap();
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
                _ => {}
            }
        });
}

fn manage_server(app: AppHandle, log_buffer: Arc<Mutex<Vec<String>>>) {
    let window = match app.get_webview_window("main") {
        Some(w) => w,
        None => return,
    };

    // Ensure the loading splash screen is visible immediately
    let _ = window.show();

    // Retrieve sidecar configuration from Shell plugin
    let sidecar = match app.shell().sidecar("minder-server") {
        Ok(s) => s,
        Err(e) => {
            let msg = format!("Sidecar 'minder-server' not available: {e}");
            eprintln!("[minder] {msg}");
            let escaped = msg.replace('\'', "\\'");
            let _ = window.eval(&format!("window.__minderError('{escaped}')"));
            return;
        }
    };

    // Spawn sidecar process
    let (mut rx, child) = match sidecar.spawn() {
        Ok((rx, child)) => {
            eprintln!("[minder] sidecar spawned (pid={})", child.pid());
            (rx, child)
        }
        Err(e) => {
            let msg = format!("Failed to spawn minder-server sidecar: {e}");
            eprintln!("[minder] {msg}");
            let escaped = msg.replace('\'', "\\'");
            let _ = window.eval(&format!("window.__minderError('{escaped}')"));
            return;
        }
    };

    // Store in global process container so we can kill it on close
    if let Some(state) = app.try_state::<ServerProcess>() {
        *state.0.lock().unwrap() = Some(child);
    }

    // Shared diagnostic and startup states
    let log_buffer_clone = log_buffer.clone();
    let terminated = Arc::new(AtomicBool::new(false));
    let terminated_clone = terminated.clone();
    // Once the server is ready and we navigate away from the splash page we
    // must stop eval-ing __minderStatus because that function only exists on
    // the splash screen.  Setting this flag to true disables the eval calls.
    let splash_done = Arc::new(AtomicBool::new(false));
    let splash_done_clone = splash_done.clone();
    let window_clone = window.clone();

    // Spawn a background thread to read child process stdout/stderr streams
    std::thread::spawn(move || {
        tauri::async_runtime::block_on(async move {
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(line_bytes) => {
                        let line = String::from_utf8_lossy(&line_bytes).to_string();
                        process_sidecar_log_line(&window_clone, &line, &log_buffer_clone, &splash_done_clone);
                    }
                    CommandEvent::Stderr(line_bytes) => {
                        let line = String::from_utf8_lossy(&line_bytes).to_string();
                        process_sidecar_log_line(&window_clone, &line, &log_buffer_clone, &splash_done_clone);
                    }
                    CommandEvent::Terminated(status) => {
                        terminated_clone.store(true, Ordering::SeqCst);
                        let mut guard = log_buffer_clone.lock().unwrap();
                        guard.push(format!("[minder] sidecar process exited prematurely with code {:?}", status.code));
                        if !splash_done_clone.load(Ordering::SeqCst) {
                            let msg = format!("Process exited unexpectedly (code {:?})", status.code);
                            let escaped = msg.replace('\'', "\\'");
                            let _ = window_clone.eval(&format!("window.__minderError('Startup Failed: {escaped}')"));
                        }
                    }
                    CommandEvent::Error(err) => {
                        let mut guard = log_buffer_clone.lock().unwrap();
                        guard.push(format!("[minder] process error: {err}"));
                    }
                    _ => {}
                }
            }
        });
    });

    // Poll until the server's TCP port accepts connections or child process exits
    let ready = wait_for_server(SERVER_HOST, SERVER_PORT, READY_TIMEOUT_SECS, &terminated);

    if ready {
        // Mark splash as done BEFORE navigating so the log reader thread stops
        // calling window.__minderStatus on the dashboard page.
        splash_done.store(true, Ordering::SeqCst);
        // Navigate to dashboard control panel
        let url: tauri::Url = DASHBOARD_URL.parse().expect("valid dashboard URL");
        let _ = window.navigate(url);
        let _ = window.show();
    } else {
        // Server failed to start — retrieve diagnostic traceback logs
        let logs = {
            let guard = log_buffer.lock().unwrap();
            guard.join("\n")
        };
        let error_msg = if logs.trim().is_empty() {
            format!(
                "Server failed to start within {} seconds (no output captured).",
                READY_TIMEOUT_SECS
            )
        } else {
            format!(
                "Server failed to start within {} seconds.\n\nDiagnostic Output:\n{}",
                READY_TIMEOUT_SECS, logs
            )
        };
        let escaped = error_msg.replace('\'', "\\'").replace('\n', "\\n").replace('\r', "");
        let _ = window.eval(&format!("window.__minderError('{escaped}')"));
        let _ = window.show();
    }
}

fn process_sidecar_log_line(
    window: &tauri::WebviewWindow,
    line: &str,
    log_buffer: &Arc<Mutex<Vec<String>>>,
    splash_done: &AtomicBool,
) {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return;
    }

    // Output to main app logs for debug visibility
    eprintln!("[sidecar] {trimmed}");

    // Append to log buffer (always, even after navigation)
    {
        let mut guard = log_buffer.lock().unwrap();
        guard.push(trimmed.to_string());
        if guard.len() > 300 {
            guard.remove(0);
        }
    }

    // Only call window.__minderStatus while the splash screen is showing.
    // After navigation to the dashboard the function no longer exists and
    // calling it would throw uncaught exceptions on every log line.
    if splash_done.load(Ordering::SeqCst) {
        return;
    }

    // Try to parse as JSON log line
    if let Ok(val) = serde_json::from_str::<serde_json::Value>(trimmed) {
        if let Some(msg) = val.get("message").and_then(|m| m.as_str()) {
            let escaped_msg = msg.replace('\'', "\\'").replace('\n', " ");
            if msg.contains("[model-bootstrap]") {
                if msg.contains("Checking") {
                    let _ = window.eval(&format!("window.__minderStatus('Checking model cache', '{}')", escaped_msg));
                } else if msg.contains("Downloading") || msg.contains("starting download") {
                    let _ = window.eval(&format!("window.__minderStatus('Downloading AI models', '{}')", escaped_msg));
                } else if msg.contains("already cached") || msg.contains("Ready:") {
                    let _ = window.eval(&format!("window.__minderStatus('Loading AI models', '{}')", escaped_msg));
                }
            } else if msg.contains("Turbovec") || msg.contains("Milvus") {
                let _ = window.eval(&format!("window.__minderStatus('Initializing search database', '{}')", escaped_msg));
            } else if msg.contains("Admin") || msg.contains("ADMIN") {
                let _ = window.eval(&format!("window.__minderStatus('Configuring control plane', '{}')", escaped_msg));
            } else {
                let _ = window.eval(&format!("window.__minderStatus('Starting Minder Services', '{}')", escaped_msg));
            }
        }
    } else {
        // Fallback for non-JSON print lines
        let escaped_line = trimmed.replace('\'', "\\'").replace('\n', " ");
        if trimmed.contains("MINDER SERVER STARTING") {
            let _ = window.eval("window.__minderStatus('Starting Minder Server', 'Initializing application components...')");
        } else if trimmed.contains("MINDER ADMIN EXISTS") {
            let _ = window.eval(&format!("window.__minderStatus('Configuring control plane', '{}')", escaped_line));
        } else if trimmed.contains("Uvicorn running on") || trimmed.contains("Started server process") {
            let _ = window.eval("window.__minderStatus('Starting Services', 'FastAPI HTTP server active...')");
        }
    }
}

fn wait_for_server(host: &str, port: u16, timeout_secs: u64, terminated: &AtomicBool) -> bool {
    let addr = format!("{host}:{port}");
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);

    while Instant::now() < deadline {
        if terminated.load(Ordering::SeqCst) {
            eprintln!("[minder] sidecar process terminated prematurely during startup");
            return false;
        }
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
