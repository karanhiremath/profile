use serde::{Deserialize, Serialize};

use crate::dest::{catalog, DestDecision, DestKind};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InventoryEntry {
    pub id: String,
    pub kind: DestKind,
    pub allow_steer: bool,
    pub allow_capture: bool,
    pub family: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FleetInventory {
    pub ok: bool,
    pub dests: Vec<InventoryEntry>,
    pub worker_panes: Vec<String>,
    pub blocked: Vec<String>,
    pub views: Vec<String>,
}

fn family_of(decision: &DestDecision) -> String {
    match decision.kind {
        DestKind::Work if decision.session.starts_with("infra") => "infra".into(),
        DestKind::Work => match decision.session.as_str() {
            "ao0" => "data",
            "ao1" => "model",
            "ao2" => "harness",
            "ao3" => "graph",
            "ao4" => "fleet",
            _ => "work",
        }
        .into(),
        DestKind::Plan if decision.session.starts_with("cos-infra") => "infra think".into(),
        DestKind::Plan => "think".into(),
        DestKind::Cos => "inbox".into(),
        DestKind::Pi => "pi".into(),
        DestKind::Claude => "claude".into(),
        DestKind::HermTui => "herm-tui".into(),
        DestKind::Brief => "spoken".into(),
        DestKind::Host => "host".into(),
        DestKind::Sandbox => "sandbox".into(),
        DestKind::Unknown => "unknown".into(),
    }
}

/// Deterministic catalog. Live tmux attachment is a host-edge enrichment.
pub fn fleet_inventory() -> FleetInventory {
    let dests: Vec<InventoryEntry> = catalog()
        .into_iter()
        .map(|decision| InventoryEntry {
            id: decision.dest.clone(),
            kind: decision.kind,
            allow_steer: decision.allow_steer,
            allow_capture: decision.allow_capture,
            family: family_of(&decision),
        })
        .collect();
    let worker_panes = dests
        .iter()
        .filter(|row| row.allow_capture)
        .map(|row| format!("{}:0.0", row.id))
        .collect();
    let blocked = dests
        .iter()
        .filter(|row| !row.allow_capture)
        .map(|row| row.id.clone())
        .collect();
    FleetInventory {
        ok: true,
        dests,
        worker_panes,
        blocked,
        views: vec![
            "fleet".into(),
            "otel".into(),
            "pane".into(),
            "voices".into(),
            "sessions".into(),
        ],
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OtelCard {
    pub title: String,
    pub state: String,
    pub detail: String,
}

/// Map a fleet-shaped JSON object into OTEL/metrics cards. No collector.
pub fn otel_cards_from_snapshot(snap: &serde_json::Value) -> Vec<OtelCard> {
    let mut cards = Vec::new();
    let jobs = snap.get("jobs").cloned().unwrap_or(serde_json::json!({}));
    let running = jobs.get("running").and_then(|v| v.as_array()).cloned().unwrap_or_default();
    let counts = jobs.get("counts").cloned().unwrap_or(serde_json::json!({}));
    cards.push(OtelCard {
        title: "Jobs".into(),
        state: if running.is_empty() { "idle".into() } else { "running".into() },
        detail: format!("{} running · {}", running.len(), counts),
    });
    for job in running.iter().take(8) {
        cards.push(OtelCard {
            title: job
                .get("id")
                .or_else(|| job.get("job_id"))
                .and_then(|v| v.as_str())
                .unwrap_or("job")
                .into(),
            state: job
                .get("status")
                .and_then(|v| v.as_str())
                .unwrap_or("running")
                .into(),
            detail: job
                .get("summary")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .chars()
                .take(160)
                .collect(),
        });
    }
    if let Some(cos) = snap.get("cos") {
        let live = cos.get("herm_tui_live").and_then(|v| v.as_bool()).unwrap_or(false);
        cards.push(OtelCard {
            title: "Cos herm-tui".into(),
            state: if live { "live".into() } else { "blocked".into() },
            detail: cos
                .get("note")
                .and_then(|v| v.as_str())
                .unwrap_or("Cos state unknown")
                .into(),
        });
    }
    if let Some(oma) = snap.get("oma_online").and_then(|v| v.as_bool()) {
        cards.push(OtelCard {
            title: "Omarchy".into(),
            state: if oma { "online".into() } else { "offline".into() },
            detail: if oma {
                "peer online".into()
            } else {
                "peer offline".into()
            },
        });
    }
    cards
}
