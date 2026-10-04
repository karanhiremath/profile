//! Host-edge effects for Cos-voice apply. Bind 127.0.0.1 only. No network in the wasm module.

use std::env;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use cos_voice_wasm::{
    allow_capture, apply_json, apply_steer, blocked_frame, decide_dest, encode_pane_frame,
    enrich_sids, fleet_inventory, otel_cards_from_snapshot, parse_index, plan_append, plan_s2s,
    plan_seatbelt, plan_voices_from_json, select_view, SteerEnvelope, SurfaceView,
};

const DEFAULT_BIND: &str = "127.0.0.1:8788";

#[derive(Clone)]
struct HostState {
    view: Arc<Mutex<String>>,
    dest: Arc<Mutex<String>>,
    seq: Arc<AtomicU64>,
}

impl HostState {
    fn new() -> Self {
        Self {
            view: Arc::new(Mutex::new("fleet".into())),
            dest: Arc::new(Mutex::new("ao2".into())),
            seq: Arc::new(AtomicU64::new(0)),
        }
    }
}

fn tmux_bin() -> String {
    env::var("COS_VOICE_TMUX").unwrap_or_else(|_| "tmux".into())
}

fn capture_pane(target: &str) -> Result<String, String> {
    let decision = allow_capture(target).map_err(|denied| {
        denied
            .blocked_reason
            .unwrap_or_else(|| format!("blocked target {target}"))
    })?;
    let tmux = tmux_bin();
    let output = Command::new(&tmux)
        .args([
            "capture-pane",
            "-t",
            &decision.pane_target,
            "-p",
            "-J",
            "-S",
            "-80",
        ])
        .output()
        .map_err(|err| err.to_string())?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        let out = String::from_utf8_lossy(&output.stdout);
        return Err(err.trim().if_empty(out.trim()).to_string());
    }
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

trait IfEmpty {
    fn if_empty(self, fallback: Self) -> Self;
}

impl IfEmpty for &str {
    fn if_empty(self, fallback: Self) -> Self {
        if self.is_empty() {
            fallback
        } else {
            self
        }
    }
}

fn otel_path() -> PathBuf {
    env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(".pi/agent/otel/agent-events.jsonl")
}

fn voice_catalog() -> serde_json::Value {
    env::var("COS_VOICE_CATALOG_PATH")
        .ok()
        .and_then(|path| fs::read_to_string(path).ok())
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or(serde_json::json!([]))
}

fn live_sid_snapshot() -> serde_json::Value {
    let mut sids = serde_json::Map::new();
    let mut panes = serde_json::Map::new();
    if let Ok(map) = env::var("COS_VOICE_SID_MAP") {
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&map) {
            return value;
        }
    }
    if let Ok(sid) = env::var("COS_VOICE_PI_SID") {
        let sid = sid.trim().to_string();
        if !sid.is_empty() {
            sids.insert("this".into(), serde_json::Value::String(sid.clone()));
            sids.insert("pi".into(), serde_json::Value::String(sid));
        }
    }
    if let Ok(sid) = env::var("COS_VOICE_SID") {
        let sid = sid.trim().to_string();
        if !sid.is_empty() {
            if cos_voice_wasm::looks_like_tmux_pane(&sid) {
                panes.insert("cos".into(), serde_json::Value::String(sid));
            } else {
                sids.insert("cos".into(), serde_json::Value::String(sid));
            }
        }
    }
    serde_json::json!({
        "sids": sids,
        "panes": panes,
        "profiles": {
            "cos": "chief-of-staff",
            "notes": "personal-notes-steward"
        }
    })
}

fn buffer_index_path() -> PathBuf {
    env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(".pi/agent/buffers/INDEX.jsonl")
}

fn append_prompt(path: &std::path::Path, text: &str) -> Result<(), String> {
    use std::fs::OpenOptions;
    let mut file = OpenOptions::new()
        .create(false)
        .append(true)
        .open(path)
        .map_err(|err| err.to_string())?;
    file.write_all(b"\n")
        .and_then(|_| file.write_all(text.trim().as_bytes()))
        .and_then(|_| file.write_all(b"\n"))
        .map_err(|err| err.to_string())
}

fn otel_cards() -> serde_json::Value {
    let mut snap = serde_json::json!({});
    if let Ok(text) = fs::read_to_string(otel_path()) {
        let mut events = Vec::new();
        for line in text.lines().rev().take(12) {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(line) {
                events.push(value);
            }
        }
        events.reverse();
        snap["otel_events"] = serde_json::Value::Array(events);
    }
    let mut cards = otel_cards_from_snapshot(&snap);
    if let Some(events) = snap.get("otel_events").and_then(|v| v.as_array()) {
        for event in events.iter().rev().take(6) {
            cards.push(cos_voice_wasm::inventory::OtelCard {
                title: event
                    .get("event_type")
                    .and_then(|v| v.as_str())
                    .unwrap_or("otel")
                    .into(),
                state: event
                    .get("status")
                    .and_then(|v| v.as_str())
                    .unwrap_or("unknown")
                    .into(),
                detail: event
                    .get("summary")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .chars()
                    .take(160)
                    .collect(),
            });
        }
    }
    serde_json::to_value(cards).unwrap_or_else(|_| serde_json::json!([]))
}

fn write_http(stream: &mut TcpStream, code: u16, content_type: &str, body: &[u8]) -> std::io::Result<()> {
    let status = match code {
        200 => "OK",
        400 => "Bad Request",
        403 => "Forbidden",
        404 => "Not Found",
        _ => "Error",
    };
    let header = format!(
        "HTTP/1.1 {code} {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n",
        body.len()
    );
    stream.write_all(header.as_bytes())?;
    stream.write_all(body)
}

fn query_param(query: &str, key: &str) -> Option<String> {
    for pair in query.split('&') {
        let mut parts = pair.splitn(2, '=');
        if parts.next()? == key {
            return Some(parts.next().unwrap_or("").to_string());
        }
    }
    None
}

fn read_request(stream: &mut TcpStream) -> Option<(String, String, String, Vec<u8>)> {
    let mut buf = Vec::new();
    let mut tmp = [0u8; 1024];
    loop {
        let n = stream.read(&mut tmp).ok()?;
        if n == 0 {
            break;
        }
        buf.extend_from_slice(&tmp[..n]);
        if buf.windows(4).any(|w| w == b"\r\n\r\n") {
            break;
        }
        if buf.len() > 64 * 1024 {
            break;
        }
    }
    let text = String::from_utf8_lossy(&buf);
    let (head, rest) = text.split_once("\r\n\r\n")?;
    let mut lines = head.lines();
    let req = lines.next()?;
    let mut parts = req.split_whitespace();
    let method = parts.next()?.to_string();
    let path = parts.next()?.to_string();
    let mut content_length = 0usize;
    for line in lines {
        let lower = line.to_ascii_lowercase();
        if let Some(v) = lower.strip_prefix("content-length:") {
            content_length = v.trim().parse().unwrap_or(0);
        }
    }
    let mut body = rest.as_bytes().to_vec();
    while body.len() < content_length {
        let n = stream.read(&mut tmp).ok()?;
        if n == 0 {
            break;
        }
        body.extend_from_slice(&tmp[..n]);
    }
    body.truncate(content_length);
    Some((method, path, head.to_string(), body))
}

fn handle_conn(mut stream: TcpStream, state: HostState) {
    let Some((method, full_path, _, body)) = read_request(&mut stream) else {
        return;
    };
    let (path, query) = match full_path.split_once('?') {
        Some((p, q)) => (p.to_string(), q.to_string()),
        None => (full_path, String::new()),
    };
    let dest = state.dest.lock().ok().map(|d| d.clone()).unwrap_or_else(|| "ao2".into());
    let view = state.view.lock().ok().map(|v| v.clone()).unwrap_or_else(|| "fleet".into());

    let result = match (method.as_str(), path.as_str()) {
        ("GET", "/health") => {
            let payload = serde_json::json!({
                "ok": true,
                "listen": env::var("COS_VOICE_WASM_BIND").unwrap_or_else(|_| DEFAULT_BIND.into()),
                "apply": "cos-voice-wasm",
                "view": view,
                "dest": dest,
                "views": ["fleet", "otel", "pane", "voices", "sessions"],
            });
            write_http(&mut stream, 200, "application/json", payload.to_string().as_bytes())
        }
        ("GET", "/inventory") => {
            let payload = serde_json::to_vec(&fleet_inventory()).unwrap_or_else(|_| b"{}".to_vec());
            write_http(&mut stream, 200, "application/json", &payload)
        }
        ("GET", "/s2s") => {
            let dest = query_param(&query, "dest").unwrap_or_else(|| dest.clone());
            let payload = serde_json::to_vec(&plan_s2s(&dest, None)).unwrap_or_else(|_| b"{}".to_vec());
            write_http(&mut stream, 200, "application/json", &payload)
        }
        ("GET", "/voices") => {
            let payload = serde_json::to_vec(&plan_voices_from_json(&voice_catalog()))
                .unwrap_or_else(|_| b"{}".to_vec());
            write_http(&mut stream, 200, "application/json", &payload)
        }
        ("GET", "/sids") | ("GET", "/sessions") => {
            let payload =
                serde_json::to_vec(&enrich_sids(&live_sid_snapshot())).unwrap_or_else(|_| b"{}".to_vec());
            write_http(&mut stream, 200, "application/json", &payload)
        }
        ("GET", "/seatbelt") => {
            let payload = serde_json::to_vec(&plan_seatbelt(None, None)).unwrap_or_else(|_| b"{}".to_vec());
            write_http(&mut stream, 200, "application/json", &payload)
        }
        ("GET", "/view") => {
            let payload = serde_json::json!({
                "ok": true,
                "view": view,
                "dest": dest,
                "selection": select_view(&view, &dest),
            });
            write_http(&mut stream, 200, "application/json", payload.to_string().as_bytes())
        }
        ("POST", "/view") => {
            let parsed: serde_json::Value = serde_json::from_slice(&body).unwrap_or(serde_json::json!({}));
            let next_view = parsed.get("view").and_then(|v| v.as_str()).unwrap_or(&view);
            let next_dest = parsed.get("dest").and_then(|v| v.as_str()).unwrap_or(&dest);
            let selection = select_view(next_view, next_dest);
            if selection.ok {
                if let Ok(mut slot) = state.view.lock() {
                    *slot = selection.view.as_str().to_string();
                }
                if !next_dest.is_empty() {
                    if let Ok(mut slot) = state.dest.lock() {
                        *slot = next_dest.to_string();
                    }
                }
            }
            let code = if selection.ok { 200 } else { 400 };
            write_http(
                &mut stream,
                code,
                "application/json",
                serde_json::to_string(&selection).unwrap_or_else(|_| "{}".into()).as_bytes(),
            )
        }
        ("GET", "/pane") => {
            let target = query_param(&query, "target").unwrap_or(dest);
            match allow_capture(&target) {
                Ok(decision) => match capture_pane(&decision.pane_target) {
                    Ok(text) => {
                        let seq = state.seq.fetch_add(1, Ordering::Relaxed);
                        let frame = encode_pane_frame(&decision, &text, seq);
                        write_http(
                            &mut stream,
                            200,
                            "application/json",
                            serde_json::to_vec(&frame).unwrap_or_else(|_| b"{}".to_vec()).as_slice(),
                        )
                    }
                    Err(err) => write_http(
                        &mut stream,
                        200,
                        "application/json",
                        serde_json::json!({"ok": false, "error": err, "target": decision.pane_target})
                            .to_string()
                            .as_bytes(),
                    ),
                },
                Err(denied) => {
                    let frame = blocked_frame(
                        &denied.pane_target,
                        denied.blocked_reason.as_deref().unwrap_or("blocked"),
                        state.seq.fetch_add(1, Ordering::Relaxed),
                    );
                    write_http(
                        &mut stream,
                        403,
                        "application/json",
                        serde_json::to_vec(&frame).unwrap_or_else(|_| b"{}".to_vec()).as_slice(),
                    )
                }
            }
        }
        ("GET", "/otel") => {
            write_http(&mut stream, 200, "application/json", otel_cards().to_string().as_bytes())
        }
        ("POST", "/apply") => {
            let payload = String::from_utf8_lossy(&body);
            match apply_json(&payload) {
                Ok(out) => write_http(&mut stream, 200, "application/json", out.as_bytes()),
                Err(err) => write_http(
                    &mut stream,
                    400,
                    "application/json",
                    serde_json::json!({"ok": false, "error": err}).to_string().as_bytes(),
                ),
            }
        }
        ("GET", "/events") => {
            let _ = stream.write_all(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\nConnection: keep-alive\r\n\r\n",
            );
            for _ in 0..3600 {
                let dest = state.dest.lock().ok().map(|d| d.clone()).unwrap_or_else(|| "ao2".into());
                let view = state.view.lock().ok().map(|v| v.clone()).unwrap_or_else(|| "fleet".into());
                let selection = select_view(&view, &dest);
                let mut payload = serde_json::json!({
                    "ok": true,
                    "view": view,
                    "dest": dest,
                    "selection": selection,
                });
                if selection.view == SurfaceView::Pane {
                    if let Some(target) = &selection.pane_target {
                        match capture_pane(target) {
                            Ok(text) => {
                                let decision = decide_dest(target);
                                let seq = state.seq.fetch_add(1, Ordering::Relaxed);
                                payload["pane"] = serde_json::to_value(encode_pane_frame(&decision, &text, seq))
                                    .unwrap_or(serde_json::json!({}));
                            }
                            Err(err) => payload["pane"] = serde_json::json!({"ok": false, "error": err}),
                        }
                    }
                }
                let line = format!("data: {payload}\n\n");
                if stream.write_all(line.as_bytes()).is_err() {
                    break;
                }
                let _ = stream.flush();
                thread::sleep(Duration::from_millis(1000));
            }
            Ok(())
        }
        _ => write_http(
            &mut stream,
            404,
            "application/json",
            br#"{"ok":false,"error":"not found"}"#,
        ),
    };
    let _ = result;
}

fn serve(bind: &str) -> Result<(), String> {
    if !bind.starts_with("127.0.0.1:") && !bind.starts_with("localhost:") {
        return Err("bind 127.0.0.1 only".into());
    }
    let listener = TcpListener::bind(bind).map_err(|err| err.to_string())?;
    eprintln!("cos-voice-host listen {bind}");
    let state = HostState::new();
    for incoming in listener.incoming() {
        match incoming {
            Ok(stream) => {
                let state = state.clone();
                thread::spawn(move || handle_conn(stream, state));
            }
            Err(err) => eprintln!("accept: {err}"),
        }
    }
    Ok(())
}

fn usage() -> ! {
    eprintln!(
        "cos-voice-host <apply|allow|view|capture|inventory|s2s|voices|sids|seatbelt|otel|buffer-append|serve> [...]\n\
         apply '{{json}}'\n\
         allow <dest>\n\
         s2s [--dest DEST]\n\
         voices\n\
         sids\n\
         seatbelt\n\
         view <fleet|otel|pane|voices|sessions> [--dest DEST]\n\
         capture <target>\n\
         inventory\n\
         otel\n\
         buffer-append --dest DEST --text TEXT [--index PATH]\n\
         serve [--bind 127.0.0.1:8788]"
    );
    std::process::exit(2);
}

fn main() {
    let mut args = env::args().skip(1);
    let cmd = args.next().unwrap_or_else(|| usage());
    match cmd.as_str() {
        "apply" => {
            let payload = args.next().unwrap_or_else(|| usage());
            match apply_json(&payload) {
                Ok(out) => println!("{out}"),
                Err(err) => {
                    eprintln!("{err}");
                    std::process::exit(1);
                }
            }
        }
        "allow" => {
            let dest = args.next().unwrap_or_else(|| usage());
            println!("{}", serde_json::to_string(&decide_dest(&dest)).unwrap());
        }
        "view" => {
            let view = args.next().unwrap_or_else(|| usage());
            let mut dest = String::from("ao2");
            while let Some(flag) = args.next() {
                if flag == "--dest" {
                    dest = args.next().unwrap_or_else(|| usage());
                }
            }
            let selection = select_view(&view, &dest);
            println!("{}", serde_json::to_string(&selection).unwrap());
            if !selection.ok {
                std::process::exit(1);
            }
        }
        "capture" => {
            let target = args.next().unwrap_or_else(|| usage());
            match capture_pane(&target) {
                Ok(text) => {
                    let decision = decide_dest(&target);
                    let frame = encode_pane_frame(&decision, &text, 0);
                    println!("{}", serde_json::to_string(&frame).unwrap());
                }
                Err(err) => {
                    eprintln!("{err}");
                    std::process::exit(1);
                }
            }
        }
        "inventory" => {
            println!("{}", serde_json::to_string(&fleet_inventory()).unwrap());
        }
        "s2s" => {
            let rest: Vec<String> = args.collect();
            let dest = rest
                .windows(2)
                .find(|w| w[0] == "--dest")
                .map(|w| w[1].clone())
                .or_else(|| rest.first().cloned())
                .unwrap_or_else(|| "cos".into());
            println!("{}", serde_json::to_string(&plan_s2s(&dest, None)).unwrap());
        }
        "voices" => {
            println!(
                "{}",
                serde_json::to_string(&plan_voices_from_json(&voice_catalog())).unwrap()
            );
        }
        "sids" | "sessions" => {
            println!(
                "{}",
                serde_json::to_string(&enrich_sids(&live_sid_snapshot())).unwrap()
            );
        }
        "seatbelt" => {
            println!("{}", serde_json::to_string(&plan_seatbelt(None, None)).unwrap());
        }
        "otel" => {
            println!("{}", otel_cards());
        }
        "steer" => {
            let dest = args.next().unwrap_or_else(|| "cos".into());
            let text = args.collect::<Vec<_>>().join(" ");
            let applied = apply_steer(&SteerEnvelope {
                text,
                dest,
                target: None,
                mode: None,
                view: None,
                key: None,
            });
            println!("{}", serde_json::to_string(&applied).unwrap());
            if !applied.ok {
                std::process::exit(1);
            }
        }
        "buffer-append" => {
            let rest: Vec<String> = args.collect();
            let dest = rest
                .windows(2)
                .find(|w| w[0] == "--dest")
                .map(|w| w[1].clone())
                .unwrap_or_else(|| "cos".into());
            let text = rest
                .windows(2)
                .find(|w| w[0] == "--text")
                .map(|w| w[1].clone())
                .unwrap_or_default();
            let index_path = rest
                .windows(2)
                .find(|w| w[0] == "--index")
                .map(|w| PathBuf::from(&w[1]))
                .unwrap_or_else(buffer_index_path);
            let index = fs::read_to_string(&index_path).unwrap_or_default();
            let planned = plan_append(&dest, &text, &parse_index(&index));
            let mut written = false;
            let mut error: Option<String> = None;
            if text.trim().is_empty() {
                error = Some("empty text".into());
            } else if let Some(path) = planned.path.as_deref() {
                let path = PathBuf::from(path);
                if path.is_file() {
                    match append_prompt(&path, &text) {
                        Ok(()) => written = true,
                        Err(err) => error = Some(err),
                    }
                } else {
                    error = Some("prompt.md missing; not created".into());
                }
            } else {
                error = Some("no open prompt.md for dest".into());
            }
            let payload = serde_json::json!({
                "ok": written && error.is_none(),
                "written": written,
                "send_keys": false,
                "sync": false,
                "commit": false,
                "plan": planned,
                "error": error,
            });
            println!("{}", payload);
            if error.is_some() {
                std::process::exit(1);
            }
        }
        "serve" => {
            let mut bind = env::var("COS_VOICE_WASM_BIND").unwrap_or_else(|_| DEFAULT_BIND.into());
            while let Some(flag) = args.next() {
                if flag == "--bind" {
                    bind = args.next().unwrap_or_else(|| usage());
                }
            }
            if let Err(err) = serve(&bind) {
                eprintln!("{err}");
                std::process::exit(1);
            }
        }
        _ => usage(),
    }
}
