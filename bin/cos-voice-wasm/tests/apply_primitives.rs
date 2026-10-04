use cos_voice_wasm::{
    allow_capture, apply_json, apply_steer, decide_dest, encode_pane_frame, fleet_inventory,
    otel_cards_from_snapshot, select_view, DestKind, SteerEnvelope, SteerMode, Transport,
};

#[test]
fn work_dests_may_be_captured_and_injected() {
    for dest in ["ao0", "ao2", "ao4", "infra0", "infra4"] {
        let decision = decide_dest(dest);
        assert_eq!(decision.kind, DestKind::Work, "{dest}");
        assert!(decision.allow_capture, "{dest}");
        assert!(decision.allow_inject, "{dest}");
        assert!(decision.send_keys, "{dest}");
        assert_eq!(decision.transport, Transport::InputBuffer);
        assert_eq!(decision.pane_target, format!("{dest}:0.0"));
    }
}

#[test]
fn cos_and_atop_are_blocked_for_capture() {
    for dest in ["cos", "cos-voice", "cos-ao2", "cos-infra0", "atop", "atop-coord"] {
        let denied = allow_capture(dest).expect_err(dest);
        assert!(!denied.allow_capture, "{dest}");
        assert!(!denied.allow_inject, "{dest}");
        assert!(!denied.send_keys, "{dest}");
    }
}

#[test]
fn plan_dest_is_inbox_only() {
    let decision = decide_dest("cos-ao2");
    assert_eq!(decision.kind, DestKind::Plan);
    assert!(decision.allow_steer);
    assert!(!decision.allow_capture);
    assert_eq!(decision.transport, Transport::InboxAtop);
}

#[test]
fn empty_dest_is_denied() {
    let decision = decide_dest("  ");
    assert_eq!(decision.kind, DestKind::Unknown);
    assert!(!decision.allow_steer);
    assert_eq!(decision.blocked_reason.as_deref(), Some("empty dest"));
}

#[test]
fn steer_envelope_routes_named_lane_from_text() {
    let applied = apply_steer(&SteerEnvelope {
        text: "ao2 restart the listener".into(),
        dest: "cos".into(),
        target: None,
        mode: Some(SteerMode::Steer),
        view: Some("pane".into()),
        key: None,
    });
    assert!(applied.ok);
    assert_eq!(applied.dest, "ao2");
    assert_eq!(applied.kind, DestKind::Work);
    assert_eq!(applied.transport, Transport::InputBuffer);
    assert!(applied.send_keys);
    assert_eq!(applied.pane_target.as_deref(), Some("ao2:0.0"));
}

#[test]
fn steer_to_cos_never_grants_send_keys() {
    let applied = apply_steer(&SteerEnvelope {
        text: "keep going on the crate".into(),
        dest: "cos".into(),
        target: None,
        mode: Some(SteerMode::Steer),
        view: None,
        key: None,
    });
    assert!(applied.ok);
    assert_eq!(applied.dest, "cos");
    assert!(!applied.send_keys);
    assert_eq!(applied.transport, Transport::HermesInbox);
    assert!(applied.pane_target.is_none());
}

#[test]
fn brief_mode_is_spoken_only() {
    let applied = apply_steer(&SteerEnvelope {
        text: "fleet status".into(),
        dest: "ao2".into(),
        target: None,
        mode: Some(SteerMode::Brief),
        view: None,
        key: None,
    });
    assert!(applied.ok);
    assert_eq!(applied.dest, "brief");
    assert_eq!(applied.transport, Transport::Spoken);
    assert!(!applied.send_keys);
}

#[test]
fn empty_text_fails_closed() {
    let applied = apply_steer(&SteerEnvelope {
        text: "  ".into(),
        dest: "ao2".into(),
        target: None,
        mode: None,
        view: None,
        key: None,
    });
    assert!(!applied.ok);
    assert_eq!(applied.error.as_deref(), Some("empty text"));
}

#[test]
fn pick_on_cos_is_denied() {
    let applied = apply_steer(&SteerEnvelope {
        text: String::new(),
        dest: "cos".into(),
        target: None,
        mode: Some(SteerMode::Pick),
        view: None,
        key: Some("y".into()),
    });
    assert!(!applied.ok);
    assert!(!applied.send_keys);
}

#[test]
fn pick_on_worker_accepts_allowlisted_key() {
    let applied = apply_steer(&SteerEnvelope {
        text: String::new(),
        dest: "infra0".into(),
        target: Some("infra0:0.0".into()),
        mode: Some(SteerMode::Pick),
        view: None,
        key: Some("Enter".into()),
    });
    assert!(applied.ok);
    assert_eq!(applied.pick_key.as_deref(), Some("Enter"));
    assert!(applied.send_keys);
}

#[test]
fn pane_view_requires_worker_dest() {
    let ok = select_view("pane", "ao2");
    assert!(ok.ok);
    assert_eq!(ok.pane_target.as_deref(), Some("ao2:0.0"));
    let blocked = select_view("pane", "cos");
    assert!(!blocked.ok);
    let unknown = select_view("dag", "ao2");
    assert!(!unknown.ok);
}

#[test]
fn inventory_lists_worker_panes_and_blocked_operator() {
    let inv = fleet_inventory();
    assert!(inv.ok);
    assert!(inv.worker_panes.contains(&"ao2:0.0".into()));
    assert!(inv.blocked.iter().any(|d| d == "cos"));
    assert_eq!(
        inv.views,
        ["fleet", "otel", "pane", "voices", "sessions"]
    );
}

#[test]
fn pane_frame_is_empty_when_capture_denied() {
    let denied = decide_dest("cos");
    let frame = encode_pane_frame(&denied, "secret", 3);
    assert!(!frame.ok);
    assert!(frame.blocked);
    assert!(frame.text.is_empty());
}

#[test]
fn otel_cards_come_from_snapshot_not_a_collector() {
    let snap = serde_json::json!({
        "jobs": {
            "counts": {"running": 1},
            "running": [{"id": "job-1", "status": "running", "summary": "apply crate"}]
        },
        "cos": {"herm_tui_live": false, "note": "inbox only"},
        "oma_online": false
    });
    let cards = otel_cards_from_snapshot(&snap);
    assert!(cards.iter().any(|c| c.title == "Jobs" && c.state == "running"));
    assert!(cards.iter().any(|c| c.title == "job-1"));
    assert!(cards.iter().any(|c| c.title == "Omarchy" && c.state == "offline"));
}

#[test]
fn pi_claude_hermtui_steer_without_send_keys() {
    let pi = decide_dest("this");
    assert_eq!(pi.kind, DestKind::Pi);
    assert!(pi.allow_steer);
    assert!(!pi.send_keys);
    assert_eq!(pi.transport, Transport::AtopPi);

    let claude = decide_dest("claude");
    assert_eq!(claude.kind, DestKind::Claude);
    assert!(claude.allow_steer);
    assert!(!claude.send_keys);

    let pm = decide_dest("pm");
    assert_eq!(pm.kind, DestKind::HermTui);
    assert!(pm.allow_steer);
    assert!(!pm.send_keys);

    let blocked = decide_dest("cosw");
    assert!(!blocked.allow_steer);
    assert!(!blocked.send_keys);
}

#[test]
fn host_and_sandbox_are_inventory_only() {
    let mac = decide_dest("mac");
    assert_eq!(mac.kind, DestKind::Host);
    assert!(!mac.allow_capture);
    assert!(!mac.allow_inject);
    assert!(!mac.send_keys);
    assert_eq!(mac.transport, Transport::None);

    let sandbox = decide_dest("mac-s");
    assert_eq!(sandbox.kind, DestKind::Sandbox);
    assert!(!sandbox.allow_capture);
    assert!(!sandbox.send_keys);
    assert!(allow_capture("oma-s").is_err());

    let inv = fleet_inventory();
    assert!(inv.dests.iter().any(|d| d.id == "mac" && d.family == "host"));
    assert!(inv.dests.iter().any(|d| d.id == "oma-s" && d.family == "sandbox"));
    assert!(!inv.worker_panes.iter().any(|p| p.starts_with("mac")));
}

#[test]
fn apply_json_inventory_and_dest_ops() {
    let inv = apply_json(r#"{"op":"inventory"}"#).unwrap();
    assert!(inv.contains("worker_panes"));
    let dest = apply_json(r#"{"op":"dest","dest":"ao2"}"#).unwrap();
    assert!(dest.contains("\"allow_capture\":true"));
    let view = apply_json(r#"{"op":"view","view":"pane","dest":"cos"}"#).unwrap();
    assert!(view.contains("\"ok\":false"));
}
