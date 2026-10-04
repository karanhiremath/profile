use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

#[cfg(not(target_arch = "wasm32"))]
use std::net::TcpStream;
#[cfg(not(target_arch = "wasm32"))]
use std::process::Command;
#[cfg(not(target_arch = "wasm32"))]
use std::time::Duration;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Chip {
    pub id: String,
    pub kind: String,
    pub state: String,
    pub title: String,
    pub detail: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ChipReport {
    pub schema: String,
    pub layers: Vec<Chip>,
    pub otel: Vec<Chip>,
    pub alerts: Vec<Chip>,
    pub jobs: BTreeMap<String, usize>,
    pub sources: BTreeMap<String, Value>,
}

pub fn chips_from_atop(dump: &Value) -> ChipReport {
    let mut alerts = Vec::new();
    let mut layers = Vec::new();
    let mut jobs: BTreeMap<String, usize> = BTreeMap::new();

    if let Some(metrics) = dump.get("metrics").and_then(|m| m.as_object()) {
        layers.push(Chip {
            id: "layer.jobs".into(),
            kind: "layer".into(),
            state: metric_state(metrics),
            title: "Jobs".into(),
            detail: format!(
                "running={} failed={} succeeded={}",
                num(metrics.get("jobs_running")),
                num(metrics.get("jobs_failed")),
                num(metrics.get("jobs_succeeded"))
            ),
        });
        layers.push(Chip {
            id: "layer.otel".into(),
            kind: "layer".into(),
            state: if num(metrics.get("events_total")) > 0 {
                "live"
            } else {
                "empty"
            }
            .into(),
            title: "OTEL".into(),
            detail: format!(
                "events_total={} tokens_in={} tokens_out={} cost_usd={}",
                num(metrics.get("events_total")),
                num(metrics.get("tokens_in")),
                num(metrics.get("tokens_out")),
                metrics
                    .get("cost_usd")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0)
            ),
        });
        layers.push(Chip {
            id: "layer.fleet".into(),
            kind: "layer".into(),
            state: "live".into(),
            title: "Fleet".into(),
            detail: format!(
                "sessions={} live_tmux={} alerts_open={}",
                num(metrics.get("sessions")),
                num(metrics.get("live_tmux")),
                num(metrics.get("alerts_open"))
            ),
        });
    }

    if let Some(rows) = dump.get("jobs").and_then(|j| j.as_array()) {
        for job in rows {
            let status = job
                .get("status")
                .and_then(|s| s.as_str())
                .unwrap_or("unknown");
            *jobs.entry(status.to_string()).or_insert(0) += 1;
        }
    }

    if let Some(rows) = dump.get("alerts").and_then(|a| a.as_array()) {
        for alert in rows {
            alerts.push(Chip {
                id: alert
                    .get("id")
                    .and_then(|s| s.as_str())
                    .unwrap_or("alert")
                    .into(),
                kind: "alert".into(),
                state: alert
                    .get("level")
                    .and_then(|s| s.as_str())
                    .unwrap_or("alert")
                    .into(),
                title: alert
                    .get("watch_id")
                    .and_then(|s| s.as_str())
                    .unwrap_or("watch")
                    .into(),
                detail: alert
                    .get("summary")
                    .and_then(|s| s.as_str())
                    .unwrap_or("")
                    .chars()
                    .take(160)
                    .collect(),
            });
        }
    }

    if !has_sid(dump, "tmux:cos:0.") {
        alerts.push(Chip {
            id: "alert.cos-herm-tui".into(),
            kind: "alert".into(),
            state: "down".into(),
            title: "Cos herm-tui".into(),
            detail: "no tmux:cos:0.* session in atop dump".into(),
        });
    }

    let hosts = dump.get("hosts").and_then(|h| h.as_array());
    let oma = hosts.into_iter().flatten().any(|h| {
        h.get("name")
            .and_then(|n| n.as_str())
            .unwrap_or("")
            .to_ascii_lowercase()
            .contains("omarchy")
    });
    if !oma {
        alerts.push(Chip {
            id: "alert.omarchy".into(),
            kind: "alert".into(),
            state: "offline".into(),
            title: "Omarchy".into(),
            detail: "no omarchy host in atop dump".into(),
        });
    }

    if let Some(rows) = dump.get("jobs").and_then(|j| j.as_array()) {
        for job in rows {
            if job.get("status").and_then(|s| s.as_str()) != Some("running") {
                continue;
            }
            let ts = job.get("ts").and_then(|s| s.as_str()).unwrap_or("");
            if ts <= "2026-09-13T04:00:00Z" && !ts.is_empty() {
                alerts.push(Chip {
                    id: format!(
                        "alert.running-too-long:{}",
                        job.get("job_id").and_then(|s| s.as_str()).unwrap_or("job")
                    ),
                    kind: "alert".into(),
                    state: "stale".into(),
                    title: "Running too long".into(),
                    detail: format!(
                        "{} since {}",
                        job.get("job_id").and_then(|s| s.as_str()).unwrap_or("job"),
                        ts
                    ),
                });
            }
        }
    }

    ChipReport {
        schema: "cos-voice.chips.v1".into(),
        layers,
        otel: vec![],
        alerts,
        jobs,
        sources: BTreeMap::from([("atop_schema".into(), dump.get("schema").cloned().unwrap_or(Value::Null))]),
    }
}

pub fn merge_otel(report: &mut ChipReport, events: &[Value]) {
    report.sources.insert("otel_events".into(), events.len().into());
    for event in events.iter().rev().take(8) {
        report.otel.push(Chip {
            id: format!(
                "otel.{}",
                event
                    .get("event_type")
                    .or_else(|| event.get("type"))
                    .and_then(|s| s.as_str())
                    .unwrap_or("event")
            ),
            kind: "otel".into(),
            state: event
                .get("status")
                .and_then(|s| s.as_str())
                .unwrap_or("unknown")
                .into(),
            title: event
                .get("event_type")
                .or_else(|| event.get("type"))
                .and_then(|s| s.as_str())
                .unwrap_or("event")
                .into(),
            detail: event
                .get("summary")
                .and_then(|s| s.as_str())
                .unwrap_or("")
                .chars()
                .take(160)
                .collect(),
        });
    }
}

pub fn merge_job_bus(report: &mut ChipReport, statuses: &[Value]) {
    report
        .sources
        .insert("job_bus_status_files".into(), statuses.len().into());
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for status in statuses {
        let st = status
            .get("status")
            .and_then(|s| s.as_str())
            .unwrap_or("unknown");
        *counts.entry(st.to_string()).or_insert(0) += 1;
        let msg = status.get("message").and_then(|s| s.as_str()).unwrap_or("");
        if st == "running" && msg.contains("pid dead") {
            report.alerts.push(Chip {
                id: format!(
                    "alert.stale-running:{}",
                    status.get("jobId").and_then(|s| s.as_str()).unwrap_or("job")
                ),
                kind: "alert".into(),
                state: "stale".into(),
                title: "Stale running".into(),
                detail: msg.chars().take(160).collect(),
            });
        }
    }
    report
        .sources
        .insert("job_bus_counts".into(), serde_json::to_value(counts).unwrap_or(Value::Null));
}

#[cfg(not(target_arch = "wasm32"))]
pub fn probe_loopback_8787() -> Chip {
    match TcpStream::connect_timeout(
        &"127.0.0.1:8787".parse().expect("addr"),
        Duration::from_millis(200),
    ) {
        Ok(_) => Chip {
            id: "alert.8787".into(),
            kind: "alert".into(),
            state: "open".into(),
            title: ":8787".into(),
            detail: "loopback open".into(),
        },
        Err(_) => Chip {
            id: "alert.8787".into(),
            kind: "alert".into(),
            state: "down".into(),
            title: ":8787".into(),
            detail: "loopback closed; ghostty-voice Python not serving".into(),
        },
    }
}

#[cfg(target_arch = "wasm32")]
pub fn probe_loopback_8787() -> Chip {
    Chip {
        id: "alert.8787".into(),
        kind: "alert".into(),
        state: "host-edge".into(),
        title: ":8787".into(),
        detail: "loopback probe is a host effect".into(),
    }
}

#[cfg(not(target_arch = "wasm32"))]
pub fn load_atop_dump() -> Result<Value, String> {
    let out = Command::new("atop")
        .arg("dump")
        .output()
        .map_err(|e| e.to_string())?;
    if !out.status.success() {
        return Err(format!("atop dump exit {}", out.status));
    }
    serde_json::from_slice(&out.stdout).map_err(|e| e.to_string())
}

#[cfg(target_arch = "wasm32")]
pub fn load_atop_dump() -> Result<Value, String> {
    Err("atop dump is a host effect".into())
}

pub fn load_otel(path: &Path) -> Vec<Value> {
    let Ok(text) = fs::read_to_string(path) else {
        return vec![];
    };
    text.lines()
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect()
}

pub fn load_job_bus(dir: &Path) -> Vec<Value> {
    let mut rows = Vec::new();
    let walker = walk_status(dir);
    for path in walker {
        if let Ok(text) = fs::read_to_string(&path) {
            if let Ok(value) = serde_json::from_str::<Value>(&text) {
                rows.push(value);
            }
        }
    }
    rows
}

fn walk_status(dir: &Path) -> Vec<std::path::PathBuf> {
    let mut out = Vec::new();
    let Ok(entries) = fs::read_dir(dir) else {
        return out;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            out.extend(walk_status(&path));
        } else if path
            .file_name()
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.ends_with(".status.json"))
        {
            out.push(path);
        }
    }
    out
}

fn has_sid(dump: &Value, prefix: &str) -> bool {
    dump.get("sessions")
        .and_then(|s| s.as_array())
        .into_iter()
        .flatten()
        .any(|s| {
            s.get("sid")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .starts_with(prefix)
        })
}

fn num(v: Option<&Value>) -> i64 {
    v.and_then(|x| x.as_i64().or_else(|| x.as_u64().map(|n| n as i64)))
        .unwrap_or(0)
}

fn metric_state(metrics: &serde_json::Map<String, Value>) -> String {
    if num(metrics.get("jobs_failed")) > 0 {
        "alert".into()
    } else if num(metrics.get("jobs_running")) > 0 {
        "busy".into()
    } else {
        "idle".into()
    }
}
