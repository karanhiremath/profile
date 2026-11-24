pub mod apply;
pub mod buffer;
pub mod chips;
pub mod dest;
pub mod envelope;
pub mod frame;
pub mod inventory;
pub mod lane;
pub mod profile;
pub mod s2s;
pub mod seatbelt;
pub mod sid;
pub mod supervise;
pub mod view;
pub mod voice;

#[cfg(target_arch = "wasm32")]
mod component_guest;

use chips::ChipReport;
use serde_json::Value;
use std::path::{Path, PathBuf};

pub use buffer::{plan_append, parse_index, BufferPlan, BufferRecord};
pub use dest::{
    allow_capture, decide_dest, is_buffer_request, route, route_with_mode, DestDecision, DestKind,
    Transport,
};
pub use envelope::{apply_steer, AppliedSteer, SteerEnvelope, SteerMode};
pub use frame::{blocked_frame, encode_pane_frame, PaneFrame};
pub use inventory::{fleet_inventory, otel_cards_from_snapshot, FleetInventory};
pub use profile::{bind_dest, dest_profile, parse_profile_yaml, ProfileVoice};
pub use s2s::{plan_s2s, AttachPlan, S2sPlan};
pub use seatbelt::{plan_seatbelt, SeatbeltPlan};
pub use sid::{enrich_sids, looks_like_tmux_pane, sid_contract, SidMap};
pub use lane::{lane_targets, parse_lane, LaneAction, LanePlan};
pub use view::{parse_view, select_view, SurfaceView, ViewSelection};
pub use voice::{plan_voices, plan_voices_from_json, VoiceView, DEFAULT_COS_VOICE_ID};

pub fn default_otel_path() -> PathBuf {
    home().join(".pi/agent/otel/agent-events.jsonl")
}

pub fn default_jobs_dir() -> PathBuf {
    home().join(".pi/agent/jobs")
}

pub fn report_from_sources(atop: &Value, otel_path: &Path, jobs_dir: &Path, probe_8787: bool) -> ChipReport {
    let mut report = chips::chips_from_atop(atop);
    chips::merge_otel(&mut report, &chips::load_otel(otel_path));
    chips::merge_job_bus(&mut report, &chips::load_job_bus(jobs_dir));
    if probe_8787 {
        report.alerts.push(chips::probe_loopback_8787());
    }
    report
}

fn home() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/"))
}

/// Apply a JSON envelope or inventory/view request. No network in this path.
pub fn apply_json(input: &str) -> Result<String, String> {
    let value: serde_json::Value =
        serde_json::from_str(input).map_err(|err| format!("invalid json: {err}"))?;
    let op = value.get("op").and_then(|v| v.as_str()).unwrap_or("steer");
    let out = match op {
        "inventory" => serde_json::to_value(fleet_inventory()).map_err(|err| err.to_string())?,
        "dest" => {
            let dest = value.get("dest").and_then(|v| v.as_str()).unwrap_or("");
            serde_json::to_value(decide_dest(dest)).map_err(|err| err.to_string())?
        }
        "view" => {
            let view = value.get("view").and_then(|v| v.as_str()).unwrap_or("fleet");
            let dest = value.get("dest").and_then(|v| v.as_str()).unwrap_or("");
            serde_json::to_value(select_view(view, dest)).map_err(|err| err.to_string())?
        }
        "otel" => {
            let snap = value
                .get("snapshot")
                .cloned()
                .unwrap_or(serde_json::json!({}));
            serde_json::to_value(otel_cards_from_snapshot(&snap)).map_err(|err| err.to_string())?
        }
        "chips" => {
            let snap = value
                .get("snapshot")
                .cloned()
                .unwrap_or(serde_json::json!({}));
            serde_json::to_value(chips::chips_from_atop(&snap)).map_err(|err| err.to_string())?
        }
        "route" => {
            let dest = value.get("dest").and_then(|v| v.as_str()).unwrap_or("cos");
            let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
            let mode = value.get("mode").and_then(|v| v.as_str());
            let routed = dest::route_with_mode(dest, text, mode);
            serde_json::json!({
                "route": routed,
                "apply": apply::plan(&routed)
            })
        }
        "profile" => {
            let dest = value.get("dest").and_then(|v| v.as_str()).unwrap_or("cos");
            let yaml = value.get("yaml").and_then(|v| v.as_str());
            if let Some(text) = yaml {
                serde_json::to_value(profile::parse_profile_yaml(text)).map_err(|err| err.to_string())?
            } else {
                serde_json::to_value(profile::bind_dest(dest)).map_err(|err| err.to_string())?
            }
        }
        "s2s" => {
            let dest = value.get("dest").and_then(|v| v.as_str()).unwrap_or("cos");
            let yaml = value.get("yaml").and_then(|v| v.as_str());
            serde_json::to_value(s2s::plan_s2s(dest, yaml)).map_err(|err| err.to_string())?
        }
        "voices" | "voice" => {
            let catalog = value
                .get("catalog")
                .or_else(|| value.get("voices"))
                .cloned()
                .unwrap_or(serde_json::json!([]));
            serde_json::to_value(voice::plan_voices_from_json(&catalog)).map_err(|err| err.to_string())?
        }
        "sids" | "sessions" => {
            let snapshot = value
                .get("snapshot")
                .cloned()
                .unwrap_or(serde_json::json!({}));
            serde_json::to_value(sid::enrich_sids(&snapshot)).map_err(|err| err.to_string())?
        }
        "seatbelt" => serde_json::to_value(seatbelt::plan_seatbelt(None, None))
            .map_err(|err| err.to_string())?,
        "buffer" => {
            let dest = value.get("dest").and_then(|v| v.as_str()).unwrap_or("cos");
            let text = value.get("text").and_then(|v| v.as_str()).unwrap_or("");
            let index = value.get("index").and_then(|v| v.as_str()).unwrap_or("");
            let planned = buffer::plan_append(dest, text, &buffer::parse_index(index));
            serde_json::to_value(planned).map_err(|err| err.to_string())?
        }
        "steer" | "apply" => {
            let envelope: SteerEnvelope =
                serde_json::from_value(value).map_err(|err| format!("invalid envelope: {err}"))?;
            serde_json::to_value(apply_steer(&envelope)).map_err(|err| err.to_string())?
        }
        other => return Err(format!("unknown op {other}")),
    };
    serde_json::to_string(&out).map_err(|err| err.to_string())
}
