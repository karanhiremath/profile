//! Cartesia speech-to-speech plan. No network, no keys, no :8787 takeover.

use serde::{Deserialize, Serialize};

use crate::apply::plan;
use crate::dest::{is_blocked_personal, route, session_name, DestKind};
use crate::profile::{bind_dest, parse_profile_yaml, profile_blocked, ProfileVoice};
use crate::voice::{assign_voice, DEFAULT_COS_VOICE_ID};

const LOOPBACK: &str = "127.0.0.1:8787";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttachPlan {
    pub kind: String,
    pub instance: String,
    pub session: String,
    pub sandbox: bool,
    pub command: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CartesiaPlan {
    pub provider: String,
    pub stt_model: String,
    pub stt_mode: String,
    pub batch_fallback: String,
    pub tts_model: String,
    pub language: String,
    pub secrets: String,
    pub loopback: String,
    pub replace_loopback: bool,
    pub voice_id: String,
    pub voice_source: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RequiredCheck {
    pub cartesia_key: String,
    pub voice_id: String,
    pub loopback_8787: String,
    pub apply_8788: String,
    pub profile_yaml: String,
    pub send_keys: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct S2sPlan {
    pub ok: bool,
    pub dest: String,
    pub kind: String,
    pub profile: ProfileVoice,
    pub cartesia: CartesiaPlan,
    pub attach: AttachPlan,
    pub send_keys: bool,
    pub required: RequiredCheck,
    pub note: String,
}

pub fn attach_for(dest: &str) -> AttachPlan {
    let name = session_name(dest);
    match name.as_str() {
        "mac" => attach("mac", "default", "mac", false),
        "oma" | "oma-default" => attach("oma", "default", "home", false),
        "mac-s" => attach("mac", "default", "notes", true),
        "oma-s" | "oma-default-s" => attach("oma", "default", "home", true),
        "cos" | "cos-voice" | "chief" => attach("mac", "default", "cos", false),
        "notes" => attach("mac", "default", "notes", false),
        other if other.ends_with("-s") => {
            let kind = other.trim_end_matches("-s");
            attach(kind, "default", "notes", true)
        }
        other => attach("mac", "default", other, false),
    }
}

fn attach(kind: &str, instance: &str, session: &str, sandbox: bool) -> AttachPlan {
    let command = if sandbox {
        if kind == "oma" {
            format!("attach oma-default-s {session}")
        } else {
            format!("attach {kind}-s {session}")
        }
    } else if kind == "oma" {
        if session == "home" {
            "attach oma-default".into()
        } else {
            format!("attach oma-default {session}")
        }
    } else if session == kind {
        format!("attach {kind}")
    } else {
        format!("attach {kind} {session}")
    };
    AttachPlan {
        kind: kind.into(),
        instance: instance.into(),
        session: session.into(),
        sandbox,
        command,
    }
}

pub fn plan_s2s(dest: &str, yaml: Option<&str>) -> S2sPlan {
    let routed = route(dest, "");
    let apply = plan(&routed);
    let name = session_name(&routed.dest);
    let blocked = is_blocked_personal(&name) || profile_blocked(&name);
    let mut profile = if let Some(text) = yaml {
        let mut parsed = parse_profile_yaml(text);
        if parsed.name.is_empty() {
            parsed.name = crate::profile::dest_profile(&routed.dest).unwrap_or_default();
        }
        parsed.found = !parsed.name.is_empty() && !profile_blocked(&parsed.name);
        parsed
    } else {
        bind_dest(&routed.dest)
    };
    if blocked {
        profile.found = false;
        profile.lane = "blocked".into();
        profile.tts_enabled = false;
        profile.stt_enabled = false;
    }
    let voice_on = profile.stt_enabled || profile.tts_enabled;
    let assigned = assign_voice(&routed.dest, &[], &std::collections::BTreeSet::new());
    let cartesia = CartesiaPlan {
        provider: "cartesia".into(),
        stt_model: if profile.stt_model.is_empty() {
            "ink-2".into()
        } else {
            profile.stt_model.clone()
        },
        stt_mode: "stream-while-hold".into(),
        batch_fallback: "ink-whisper".into(),
        tts_model: if profile.tts_model.is_empty() {
            "sonic-3.5".into()
        } else {
            profile.tts_model.clone()
        },
        language: profile.language.clone(),
        secrets: "host-edge".into(),
        loopback: LOOPBACK.into(),
        replace_loopback: false,
        voice_id: if blocked {
            String::new()
        } else {
            assigned.voice_id
        },
        voice_source: if blocked {
            "blocked".into()
        } else {
            assigned.source
        },
    };
    let attach = attach_for(&routed.dest);
    let kind = format!("{:?}", routed.kind).to_ascii_lowercase();
    let note = if blocked {
        "blocked personal/work profile; no s2s".into()
    } else if !voice_on && profile.found {
        "profile is text-only; browser TTS/STT on :8787 stays the live loop".into()
    } else if matches!(routed.kind, DestKind::Host | DestKind::Sandbox) {
        "same Cartesia s2s plan on attach grammar; no send-keys; :8787 untouched".into()
    } else {
        "Cartesia s2s plan from Hermes profile; browser TTS/STT on :8787 stays live".into()
    };
    S2sPlan {
        ok: !blocked,
        dest: routed.dest,
        kind,
        profile,
        cartesia,
        attach,
        send_keys: apply.send_keys,
        required: RequiredCheck {
            cartesia_key: "host-edge present|missing; never in wasm".into(),
            voice_id: format!(
                "default Cos {DEFAULT_COS_VOICE_ID}; dest-distinct from catalog; never from YAML"
            ),
            loopback_8787: "keep live Python Ink-2/Sonic; do not bounce unless approved".into(),
            apply_8788: "crate/CLI sidecar only".into(),
            profile_yaml: if blocked {
                "blocked".into()
            } else {
                "personal Hermes YAML; no work profiles".into()
            },
            send_keys: "never Cos/Atop/pi/herm-tui".into(),
        },
        note,
    }
}
