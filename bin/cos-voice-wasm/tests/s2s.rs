use cos_voice_wasm::dest::{dest_kind, DestKind};
use cos_voice_wasm::{apply_json, dest_profile, parse_profile_yaml, plan_s2s};

const COS_YAML: &str = include_str!("fixtures/chief-of-staff.yaml");
const NOTES_YAML: &str = include_str!("fixtures/notes-text-only.yaml");

#[test]
fn dests_bind_personal_profiles_only() {
    assert_eq!(dest_profile("cos").as_deref(), Some("chief-of-staff"));
    assert_eq!(dest_profile("chief").as_deref(), Some("chief-of-staff"));
    assert_eq!(dest_profile("notes").as_deref(), Some("personal-notes-steward"));
    assert!(dest_profile("pm").is_none());
    assert!(dest_profile("pl").is_none());
    assert!(dest_profile("ao2").is_none());
    assert!(dest_profile("cosw").is_none());
}

#[test]
fn yaml_parser_never_keeps_voice_id() {
    let leaked = "name: chief-of-staff\ntts:\n  enabled: true\n  model: sonic-3.5\n  voice: secret-voice-id\nstt:\n  enabled: true\n  model: ink-2\n  language: en\n";
    let parsed = parse_profile_yaml(leaked);
    assert!(parsed.tts_voice_set);
    let dumped = serde_json::to_string(&parsed).unwrap();
    assert!(!dumped.contains("secret-voice-id"));
}

#[test]
fn yaml_redacts_non_public_endpoint() {
    let yaml = "name: chief-of-staff\nendpoint:\n  base_url: https://internal.example\n";
    let parsed = parse_profile_yaml(yaml);
    assert_eq!(parsed.endpoint, "redacted");
    let public = parse_profile_yaml(
        "name: chief-of-staff\nendpoint:\n  base_url: https://api.cartesia.ai   # public\n",
    );
    assert_eq!(public.endpoint, "https://api.cartesia.ai");
}

#[test]
fn cos_s2s_uses_cartesia_and_leaves_loopback() {
    let plan = plan_s2s("cos", Some(COS_YAML));
    assert!(plan.ok);
    assert_eq!(plan.dest, "cos");
    assert_eq!(plan.profile.name, "chief-of-staff");
    assert!(plan.profile.found);
    assert!(plan.profile.stt_enabled);
    assert!(plan.profile.tts_enabled);
    assert_eq!(plan.cartesia.provider, "cartesia");
    assert_eq!(plan.cartesia.stt_model, "ink-2");
    assert_eq!(plan.cartesia.tts_model, "sonic-3.5");
    assert_eq!(plan.cartesia.loopback, "127.0.0.1:8787");
    assert!(!plan.cartesia.replace_loopback);
    assert_eq!(plan.cartesia.secrets, "host-edge");
    assert_eq!(
        plan.cartesia.voice_id,
        cos_voice_wasm::DEFAULT_COS_VOICE_ID
    );
    assert!(!plan.send_keys);
    assert_eq!(plan.attach.command, "attach mac cos");
}

#[test]
fn notes_profile_can_be_text_only() {
    let plan = plan_s2s("notes", Some(NOTES_YAML));
    assert!(plan.ok);
    assert!(!plan.profile.stt_enabled);
    assert!(!plan.profile.tts_enabled);
    assert!(!plan.cartesia.replace_loopback);
    assert!(!plan.send_keys);
}

#[test]
fn same_s2s_plan_on_host_and_sandbox_attach() {
    for dest in ["mac", "oma", "oma-default", "mac-s", "oma-s"] {
        let plan = plan_s2s(dest, Some(COS_YAML));
        assert!(plan.ok, "{dest}");
        assert!(!plan.send_keys, "{dest}");
        assert!(plan.attach.command.starts_with("attach "), "{dest}");
        assert!(!plan.cartesia.replace_loopback, "{dest}");
        assert_eq!(plan.cartesia.provider, "cartesia", "{dest}");
    }
    assert_eq!(dest_kind("oma"), DestKind::Host);
    let oma = plan_s2s("oma", None);
    assert_eq!(oma.attach.command, "attach oma-default");
    assert!(!oma.attach.sandbox);
    let oma_s = plan_s2s("oma-s", None);
    assert_eq!(oma_s.attach.command, "attach oma-default-s home");
    assert!(oma_s.attach.sandbox);
}

#[test]
fn cosw_s2s_is_blocked() {
    let plan = plan_s2s("cosw", Some(COS_YAML));
    assert!(!plan.ok);
    assert!(!plan.send_keys);
    assert_eq!(plan.profile.lane, "blocked");
}

#[test]
fn apply_json_s2s_does_not_need_network() {
    let out = apply_json(r#"{"op":"s2s","dest":"cos","yaml":"name: chief-of-staff\ntts:\n  enabled: true\n  model: sonic-3.5\nstt:\n  enabled: true\n  model: ink-2\n"}"#).unwrap();
    assert!(out.contains("\"replace_loopback\":false"));
    assert!(out.contains("ink-2"));
    assert!(!out.contains("CARTESIA_API_KEY"));
}
