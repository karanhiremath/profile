use cos_voice_wasm::lane::{lane_targets, parse_lane, LaneAction};

#[test]
fn list_lanes() {
    let plan = parse_lane("list lanes");
    assert!(plan.ok);
    assert_eq!(plan.action, LaneAction::List);
    assert_eq!(plan.command, "fleet ls");
}

#[test]
fn attach_cos_ao_four_think_is_plan_view_only() {
    let plan = parse_lane("attach cos ao four think");
    assert_eq!(plan.action, LaneAction::Plan);
    assert_eq!(plan.target, "cos-ao4:think");
    assert_eq!(plan.command, "fleet plan ao4");
    assert!(!plan.allow_send_keys);
}

#[test]
fn steer_ao_four_do_status() {
    let plan = parse_lane("steer ao four do status");
    assert!(plan.ok);
    assert_eq!(plan.target, "ao4:do");
    assert_eq!(plan.command, "fleet steer ao4:do status");
    assert_eq!(plan.message, "status");
    assert!(plan.allow_send_keys);
}

#[test]
fn steer_cos_ao_four_think_is_blocked() {
    let plan = parse_lane("steer cos ao four think status");
    assert!(!plan.ok);
    assert!(!plan.allow_send_keys);
    assert!(plan.blocked_reason.is_some());
}

#[test]
fn steer_operator_panes_blocked() {
    for utterance in ["steer cos do hello", "steer atop do hello"] {
        let plan = parse_lane(utterance);
        assert!(!plan.ok, "{utterance}");
        assert!(!plan.allow_send_keys, "{utterance}");
        assert!(plan.blocked_reason.is_some(), "{utterance}");
    }
}

#[test]
fn steer_unknown_lane_never_guesses() {
    let plan = parse_lane("steer ao nine do hello");
    assert!(!plan.ok);
    assert!(!plan.allow_send_keys);
    assert!(plan.blocked_reason.is_some());
}

#[test]
fn lane_targets_cover_known_windows_only() {
    let targets = lane_targets();
    assert!(targets.contains(&"ao2:do".to_string()));
    assert!(targets.contains(&"ao2:pi".to_string()));
    assert!(targets.contains(&"cos-ao2:think".to_string()));
    assert!(targets.contains(&"cos-ao2:cos".to_string()));
    for bare in ["cos", "atop", "mac", "mac-mini"] {
        assert!(!targets.contains(&bare.to_string()), "unexpected bare entry {bare}");
    }
}

#[test]
fn spoken_digits_and_hyphen_forms_resolve() {
    for utterance in ["work ao4", "work ao-4", "work ao four"] {
        let plan = parse_lane(utterance);
        assert_eq!(plan.action, LaneAction::Work, "{utterance}");
        assert_eq!(plan.lane, "ao4", "{utterance}");
        assert_eq!(plan.target, "ao4:do", "{utterance}");
        assert_eq!(plan.command, "fleet attach ao4", "{utterance}");
    }
    let infra = parse_lane("plan infra two");
    assert_eq!(infra.lane, "infra2");
    assert_eq!(infra.target, "cos-infra2:think");
    assert_eq!(infra.command, "fleet plan infra2");
}

#[test]
fn work_and_plan_never_allow_send_keys() {
    assert!(!parse_lane("attach ao four").allow_send_keys);
    assert!(!parse_lane("work ao four").allow_send_keys);
    assert!(!parse_lane("plan ao four").allow_send_keys);
}

#[test]
fn steer_pi_window_allowed_think_window_not() {
    let pi = parse_lane("steer ao four pi rebuild");
    assert!(pi.ok);
    assert_eq!(pi.target, "ao4:pi");
    assert_eq!(pi.command, "fleet steer ao4:pi rebuild");

    let bare_think = parse_lane("steer ao four think status");
    assert!(!bare_think.ok);
    assert!(bare_think.blocked_reason.is_some());
}

#[test]
fn steer_empty_message_is_blocked() {
    let plan = parse_lane("steer ao four do");
    assert!(!plan.ok);
    assert!(plan.blocked_reason.is_some());
}
