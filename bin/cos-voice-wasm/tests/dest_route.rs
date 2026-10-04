use cos_voice_wasm::apply::plan;
use cos_voice_wasm::buffer::{parse_index, plan_append};
use cos_voice_wasm::dest::{
    decide_dest, dest_kind, is_buffer_request, named_dest, route, route_with_mode, DestKind,
};
use cos_voice_wasm::{apply_steer, SteerEnvelope, SteerMode, Transport};

#[test]
fn dest_kinds_match_contract() {
    assert_eq!(dest_kind("cos"), DestKind::Cos);
    assert_eq!(dest_kind("cos-voice"), DestKind::Cos);
    assert_eq!(dest_kind("ao2"), DestKind::Work);
    assert_eq!(dest_kind("infra0"), DestKind::Work);
    assert_eq!(dest_kind("cos-ao4"), DestKind::Plan);
    assert_eq!(dest_kind("brief"), DestKind::Brief);
    assert_eq!(dest_kind("mac"), DestKind::Host);
    assert_eq!(dest_kind("oma"), DestKind::Host);
    assert_eq!(dest_kind("oma-default"), DestKind::Host);
    assert_eq!(dest_kind("mac-s"), DestKind::Sandbox);
    assert_eq!(dest_kind("oma-s"), DestKind::Sandbox);
    assert_eq!(dest_kind("nope"), DestKind::Unknown);
    assert_eq!(dest_kind("this"), DestKind::Pi);
    assert_eq!(dest_kind("pi"), DestKind::Pi);
    assert_eq!(dest_kind("claude"), DestKind::Claude);
    assert_eq!(dest_kind("pm"), DestKind::HermTui);
    assert_eq!(dest_kind("pl"), DestKind::HermTui);
    assert_eq!(dest_kind("notes"), DestKind::HermTui);
    assert_eq!(dest_kind("chief"), DestKind::HermTui);
    assert_eq!(dest_kind("cosw"), DestKind::Unknown);
}

#[test]
fn named_dest_overrides_cos_chip() {
    assert_eq!(named_dest("ao2 land the crate").as_deref(), Some("ao2"));
    assert_eq!(named_dest("please infra0 check disk").as_deref(), Some("infra0"));
}

#[test]
fn work_may_input_buffer_cos_never_send_keys() {
    let work = route("ao2", "continue");
    assert!(work.send_keys);
    assert!(work.transports.contains(&"tmux-input-buffer".into()));

    let cos = route("cos", "status of the fleet");
    assert!(!cos.send_keys);
    assert_eq!(cos.kind, DestKind::Brief);

    let plan = route("cos-ao4", "plan the supervisor");
    assert!(!plan.send_keys);
}

#[test]
fn unknown_dest_is_not_silently_cos() {
    let r = route("mystery", "hello");
    assert_eq!(r.kind, DestKind::Unknown);
    assert!(r.transports.is_empty());
    assert!(!r.send_keys);
}

#[test]
fn operator_dests_never_send_keys() {
    for dest in ["cos", "cos-voice", "cos-mini", "atop", "atop:0.0", "atop-coord"] {
        let routed = route(dest, "continue the work");
        let apply = plan(&routed);
        assert!(!routed.send_keys, "route {dest}");
        assert!(!apply.send_keys, "plan {dest}");
        assert!(apply.blocked_targets.iter().any(|t| t.starts_with("cos") || t.starts_with("atop")));
    }
}

#[test]
fn named_lane_copies_cos_inbox() {
    let r = route("cos", "ao4 verify the meter");
    assert_eq!(r.dest, "ao4");
    assert!(r.copy_cos_inbox);
    assert!(r.send_keys);
}

#[test]
fn spoken_triggers_map_new_kinds() {
    assert_eq!(named_dest("this continue").as_deref(), Some("this"));
    assert_eq!(named_dest("pi land the crate").as_deref(), Some("pi"));
    assert_eq!(named_dest("claude review the diff").as_deref(), Some("claude"));
    assert_eq!(named_dest("pm check the inbox").as_deref(), Some("pm"));
    assert_eq!(named_dest("pl implement the plan").as_deref(), Some("pl"));
    assert_eq!(named_dest("notes capture this").as_deref(), Some("notes"));
    assert_eq!(named_dest("chief continue").as_deref(), Some("cos"));
    assert_eq!(named_dest("please dest claude").as_deref(), Some("claude"));
}

#[test]
fn this_in_the_middle_does_not_steal_claude() {
    assert_eq!(named_dest("send this to claude").as_deref(), Some("claude"));
}

#[test]
fn pi_claude_hermtui_never_send_keys() {
    for dest in ["this", "pi", "claude", "pm", "pl", "notes", "chief"] {
        let routed = route(dest, "continue the work");
        let apply = plan(&routed);
        assert!(!routed.send_keys, "route {dest}");
        assert!(!apply.send_keys, "plan {dest}");
    }
    let this_dest = decide_dest("this");
    assert_eq!(this_dest.kind, DestKind::Pi);
    assert!(this_dest.pane_target.is_empty());
    assert!(!this_dest.send_keys);
    let pi = route("this", "continue");
    assert_eq!(pi.kind, DestKind::Pi);
    assert!(pi.transports.contains(&"atop-steer-pi".into()));
    let claude = route("claude", "continue");
    assert_eq!(claude.kind, DestKind::Claude);
    assert!(claude.transports.contains(&"atop-steer-claude-code".into()));
    let pm = route("pm", "continue");
    assert_eq!(pm.kind, DestKind::HermTui);
    assert!(pm.transports.contains(&"hermes-inbox".into()));
    let chief = route("cos", "chief continue");
    assert_eq!(chief.dest, "cos");
    assert!(!chief.send_keys);
}

#[test]
fn cosw_is_blocked() {
    let r = route("cosw", "do the work");
    assert_eq!(r.kind, DestKind::Unknown);
    assert!(r.transports.is_empty());
    assert!(!r.send_keys);
    let spoken = route("cos", "cosw do the work");
    assert_eq!(spoken.dest, "cosw");
    assert!(!spoken.send_keys);
    let decision = decide_dest("cosw");
    assert!(!decision.allow_steer);
    assert!(!decision.send_keys);
    assert_eq!(
        decision.blocked_reason.as_deref(),
        Some("cosw blocked on personal Cos-voice")
    );
}

#[test]
fn buffer_mode_never_send_keys_on_operator_or_work() {
    assert!(is_buffer_request("into the buffer add this"));
    assert!(is_buffer_request("congress please"));
    assert!(is_buffer_request("edit the prompt"));
    assert!(is_buffer_request("draft the next step"));
    for dest in ["cos", "this", "pi", "pm", "pl", "notes", "claude", "ao2"] {
        let routed = route(dest, "into the buffer continue");
        let apply = plan(&routed);
        assert_eq!(routed.mode, "buffer", "{dest}");
        assert!(!routed.send_keys, "{dest}");
        assert!(!apply.send_keys, "{dest}");
        assert_eq!(routed.transports, vec!["nvim-buffer".to_string()], "{dest}");
    }
    let forced = route_with_mode("ao2", "continue the work", Some("buffer"));
    assert_eq!(forced.mode, "buffer");
    assert!(!forced.send_keys);
    assert!(!plan(&forced).send_keys);
}

#[test]
fn buffer_plan_resolves_session_hint_without_sync() {
    let index = r#"
{"ts":"20260913T031611Z","path":"/tmp/pi-editor-A/prompt.md","session_hint":"cos:2.7","size":29}
{"ts":"20260913T032753Z","path":"/tmp/pi-editor-B/prompt.md","session_hint":"ao2:0.0","size":31}
"#;
    let planned = plan_append("ao2", "voice note", &parse_index(index));
    assert_eq!(planned.path.as_deref(), Some("/tmp/pi-editor-B/prompt.md"));
    assert_eq!(planned.session_hint, "ao2:0.0");
    assert!(!planned.send_keys);
    assert!(!planned.sync);
    assert!(!planned.commit);
    let cos = plan_append("cos", "voice note", &parse_index(index));
    assert_eq!(cos.path.as_deref(), Some("/tmp/pi-editor-A/prompt.md"));
    let stolen = plan_append(
        "cos",
        "voice note",
        &parse_index(r#"{"path":"/tmp/pi-editor-C/prompt.md","session_hint":"cos-voice:0.0"}"#),
    );
    assert!(stolen.path.is_none());
}

#[test]
fn pi_target_sid_does_not_grant_worker_send_keys() {
    let applied = apply_steer(&SteerEnvelope {
        text: "continue".into(),
        dest: "this".into(),
        target: Some("ao2:0.0".into()),
        mode: Some(SteerMode::Steer),
        view: None,
        key: None,
    });
    assert!(applied.ok);
    assert_eq!(applied.kind, DestKind::Pi);
    assert!(!applied.send_keys);
    assert_eq!(applied.transport, Transport::AtopPi);
}

#[test]
fn apply_steer_buffer_clears_send_keys() {
    let applied = apply_steer(&SteerEnvelope {
        text: "congress keep going".into(),
        dest: "ao2".into(),
        target: None,
        mode: Some(SteerMode::Buffer),
        view: None,
        key: None,
    });
    assert!(applied.ok);
    assert_eq!(applied.transport, Transport::NvimBuffer);
    assert!(!applied.send_keys);
    assert!(applied.pane_target.is_none());
}
