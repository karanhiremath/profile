use cos_voice_wasm::{
    apply_json, enrich_sids, looks_like_tmux_pane, plan_s2s, plan_seatbelt, plan_voices_from_json,
    select_view, sid_contract, DEFAULT_COS_VOICE_ID,
};
use serde_json::json;
use std::path::Path;

#[test]
fn cos_default_voice_is_the_operator_id() {
    assert_eq!(DEFAULT_COS_VOICE_ID, "f6141af3-5f94-418c-80ed-a45d450e7e2e");
    let plan = plan_s2s("cos", None);
    assert_eq!(plan.cartesia.voice_id, DEFAULT_COS_VOICE_ID);
    assert_eq!(plan.cartesia.voice_source, "default");
    assert!(!plan.cartesia.replace_loopback);
}

#[test]
fn voices_view_keeps_cos_default_distinct() {
    let catalog = json!([
        {"id": "f6141af3-5f94-418c-80ed-a45d450e7e2e", "name": "Cos default"},
        {"id": "11111111-1111-4111-8111-111111111111", "name": "Ao2"},
        {"id": "22222222-2222-4222-8222-222222222222", "name": "Notes"}
    ]);
    let view = plan_voices_from_json(&catalog);
    assert_eq!(view.view, "voices");
    let cos = view
        .assignments
        .iter()
        .find(|row| row.dest == "cos")
        .expect("cos");
    assert_eq!(cos.voice_id, DEFAULT_COS_VOICE_ID);
    assert_eq!(cos.source, "default");
    assert!(view.assignments.iter().any(|row| row.source == "catalog"));
    assert!(view
        .assignments
        .iter()
        .filter(|row| row.source == "catalog")
        .all(|row| row.voice_id != DEFAULT_COS_VOICE_ID));
    let ao2 = view
        .assignments
        .iter()
        .find(|row| row.dest == "ao2")
        .expect("ao2");
    assert_ne!(ao2.source, "default");
    assert_ne!(ao2.voice_id, DEFAULT_COS_VOICE_ID);
}

#[test]
fn yaml_still_does_not_leak_into_voice_view() {
    let dumped = apply_json(r#"{"op":"voices","catalog":[]}"#).unwrap();
    assert!(dumped.contains(DEFAULT_COS_VOICE_ID));
    assert!(!dumped.contains("CARTESIA_API_KEY"));
}

#[test]
fn sid_contract_does_not_invent_operator_sids() {
    let map = sid_contract();
    assert_eq!(map.view, "sessions");
    for dest in ["this", "pi", "pm", "pl", "notes", "cos", "claude"] {
        let row = map.rows.iter().find(|row| row.dest == dest).expect(dest);
        assert!(row.sid.is_none(), "{dest}");
        assert!(!row.live, "{dest}");
        assert!(map.unknown.iter().any(|d| d == dest), "{dest}");
    }
    let work = map.rows.iter().find(|row| row.dest == "ao2").unwrap();
    assert!(work.bindable);
    assert_eq!(work.target_form, "pane");
}

#[test]
fn snapshot_sid_is_accepted_and_pane_is_rejected_for_pi() {
    let ok = enrich_sids(&json!({
        "sids": {"this": "cdev-session-abc", "pi": "cdev-session-abc"},
        "panes": {"this": "pi:0.0"}
    }));
    let this = ok.rows.iter().find(|row| row.dest == "this").unwrap();
    assert_eq!(this.sid.as_deref(), Some("cdev-session-abc"));
    assert!(this.bindable);
    assert_eq!(this.pane_hint.as_deref(), Some("pi:0.0"));

    let rejected = enrich_sids(&json!({"sids": {"this": "this:0.0", "pm": "pm:0.0"}}));
    let this = rejected.rows.iter().find(|row| row.dest == "this").unwrap();
    assert!(this.sid.is_none());
    assert!(this.note.contains("do not invent"));
    let pm = rejected.rows.iter().find(|row| row.dest == "pm").unwrap();
    assert!(pm.sid.is_none());
    assert!(pm.note.contains("pane address"));
}

#[test]
fn pane_shaped_values_are_detected() {
    assert!(looks_like_tmux_pane("ao2:0.0"));
    assert!(looks_like_tmux_pane("tmux:cos:2.7"));
    assert!(!looks_like_tmux_pane("cdev-session-abc"));
    assert!(!looks_like_tmux_pane("this"));
}

#[test]
fn seatbelt_plan_never_takes_8787() {
    let plan = plan_seatbelt(Some(Path::new("/Users/karan")), None);
    assert!(!plan.replace_loopback);
    assert!(plan.wrap.contains("127.0.0.1:8788"));
    assert!(!plan.wrap.contains(":8787"));
    assert!(plan
        .deny
        .iter()
        .any(|p| p.ends_with(".local/share/hermes-agents/chief-of-staff-work")));
    assert!(plan.deny.iter().any(|p| p.ends_with(".ssh")));
}

#[test]
fn views_include_voices_and_sessions() {
    assert!(select_view("voices", "cos").ok);
    assert!(select_view("sessions", "pi").ok);
    let inv = apply_json(r#"{"op":"inventory"}"#).unwrap();
    assert!(inv.contains("\"voices\""));
    assert!(inv.contains("\"sessions\""));
}
