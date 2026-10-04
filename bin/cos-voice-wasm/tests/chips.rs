use cos_voice_wasm::chips::{chips_from_atop, merge_job_bus, merge_otel};
use serde_json::json;
use std::path::PathBuf;

fn fixture() -> serde_json::Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/atop-snapshot.min.json");
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

#[test]
fn chips_see_failed_jobs_and_missing_cos() {
    let report = chips_from_atop(&fixture());
    assert_eq!(report.schema, "cos-voice.chips.v1");
    assert!(report.jobs.get("failed").copied().unwrap_or(0) >= 5);
    assert!(
        report.alerts.iter().any(|c| c.id.contains("wasm-otel")),
        "wasm-otel alert missing: {:?}",
        report.alerts
    );
    assert!(
        report.alerts.iter().any(|c| c.id == "alert.cos-herm-tui"),
        "cos herm-tui chip missing"
    );
    assert!(report.alerts.iter().any(|c| c.id == "alert.omarchy"));
}

#[test]
fn otel_undelivered_steer_is_a_chip() {
    let mut report = chips_from_atop(&fixture());
    merge_otel(
        &mut report,
        &[json!({
            "event_type": "fleet.steer.attempt",
            "status": "undelivered",
            "summary": "hermes mid-run-tool-boundary via hermes-http"
        })],
    );
    assert_eq!(report.otel[0].state, "undelivered");
    assert_eq!(report.otel[0].title, "fleet.steer.attempt");
}

#[test]
fn stale_running_job_bus_is_flagged() {
    let mut report = chips_from_atop(&fixture());
    merge_job_bus(
        &mut report,
        &[json!({
            "jobId": "subagent-1789301611815-wasm-otel",
            "status": "running",
            "message": "pid dead; status was stale running. Do not steer this job."
        })],
    );
    assert!(report.alerts.iter().any(|c| c.id.contains("stale-running")));
}
