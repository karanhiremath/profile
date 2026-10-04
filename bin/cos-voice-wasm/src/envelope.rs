use serde::{Deserialize, Serialize};

use crate::dest::{
    decide_dest, is_brief_request, is_buffer_request, named_dest, DestDecision, DestKind,
    Transport,
};

const PICK_KEYS: &[&str] = &["y", "n", "Y", "N", "1", "2", "3", "4", "5", "6", "7", "8", "9", "Enter", "Escape", "esc"];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SteerMode {
    Steer,
    Brief,
    Pick,
    Buffer,
}

impl Default for SteerMode {
    fn default() -> Self {
        Self::Steer
    }
}

/// Compact steer envelope. No I/O. Host applies the resulting transport at the edge.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SteerEnvelope {
    pub text: String,
    #[serde(default)]
    pub dest: String,
    #[serde(default)]
    pub target: Option<String>,
    #[serde(default)]
    pub mode: Option<SteerMode>,
    #[serde(default)]
    pub view: Option<String>,
    #[serde(default)]
    pub key: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AppliedSteer {
    pub ok: bool,
    pub dest: String,
    pub kind: DestKind,
    pub transport: Transport,
    pub send_keys: bool,
    pub pane_target: Option<String>,
    pub view: Option<String>,
    pub pick_key: Option<String>,
    pub prompt: String,
    pub error: Option<String>,
    pub decision: DestDecision,
}

fn compact_prompt(dest: &str, transcript: &str) -> String {
    format!(
        "Voice steer dest={dest}.\nTranscript: {}",
        transcript.trim()
    )
}

fn normalize_pick(key: &str) -> Option<String> {
    let token = key.trim();
    match token {
        "enter" | "ENTER" | "\n" | "\r" => Some("Enter".into()),
        "esc" | "ESC" | "escape" => Some("Escape".into()),
        other if PICK_KEYS.contains(&other) => {
            if other == "esc" {
                Some("Escape".into())
            } else {
                Some(other.to_string())
            }
        }
        _ => None,
    }
}

pub fn apply_steer(envelope: &SteerEnvelope) -> AppliedSteer {
    let text = envelope.text.trim();
    let dest_in = envelope.dest.trim();
    let mode = envelope.mode.unwrap_or_default();

    if mode != SteerMode::Pick && text.is_empty() {
        let decision = decide_dest(dest_in);
        return AppliedSteer {
            ok: false,
            dest: decision.dest.clone(),
            kind: decision.kind,
            transport: Transport::None,
            send_keys: false,
            pane_target: None,
            view: envelope.view.clone(),
            pick_key: None,
            prompt: String::new(),
            error: Some("empty text".into()),
            decision,
        };
    }

    if mode == SteerMode::Brief || dest_in == "brief" || (is_brief_request(text) && !is_buffer_request(text) && mode != SteerMode::Buffer) {
        let decision = decide_dest("brief");
        return AppliedSteer {
            ok: true,
            dest: "brief".into(),
            kind: DestKind::Brief,
            transport: Transport::Spoken,
            send_keys: false,
            pane_target: None,
            view: envelope.view.clone(),
            pick_key: None,
            prompt: text.to_string(),
            error: None,
            decision,
        };
    }

    if mode == SteerMode::Pick {
        let target = envelope
            .target
            .as_deref()
            .filter(|s| !s.is_empty())
            .unwrap_or(dest_in);
        let decision = decide_dest(target);
        let key = envelope.key.as_deref().unwrap_or("");
        let normalized = normalize_pick(key);
        if !decision.allow_pick {
            return AppliedSteer {
                ok: false,
                dest: decision.dest.clone(),
                kind: decision.kind,
                transport: Transport::None,
                send_keys: false,
                pane_target: None,
                view: envelope.view.clone(),
                pick_key: None,
                prompt: String::new(),
                error: Some(
                    decision
                        .blocked_reason
                        .clone()
                        .unwrap_or_else(|| format!("pick blocked on {}", decision.dest)),
                ),
                decision,
            };
        }
        return match normalized {
            Some(pick_key) => AppliedSteer {
                ok: true,
                dest: decision.dest.clone(),
                kind: decision.kind,
                transport: Transport::InputBuffer,
                send_keys: true,
                pane_target: Some(decision.pane_target.clone()),
                view: envelope.view.clone(),
                pick_key: Some(pick_key),
                prompt: String::new(),
                error: None,
                decision,
            },
            None => AppliedSteer {
                ok: false,
                dest: decision.dest.clone(),
                kind: decision.kind,
                transport: Transport::None,
                send_keys: false,
                pane_target: Some(decision.pane_target.clone()),
                view: envelope.view.clone(),
                pick_key: None,
                prompt: String::new(),
                error: Some("key not allowed".into()),
                decision,
            },
        };
    }

    let named = named_dest(text);
    let route = named
        .or_else(|| {
            if dest_in.is_empty() {
                None
            } else {
                Some(dest_in.to_string())
            }
        })
        .unwrap_or_else(|| "cos".into());
    let dest_decision = decide_dest(&route);
    let target = envelope
        .target
        .as_deref()
        .filter(|s| !s.is_empty())
        .unwrap_or(route.as_str());
    let decision = if matches!(
        dest_decision.kind,
        DestKind::Pi | DestKind::Claude | DestKind::HermTui | DestKind::Cos
    ) {
        dest_decision
    } else {
        decide_dest(target)
    };
    if !decision.allow_steer && decision.kind != DestKind::Brief {
        return AppliedSteer {
            ok: false,
            dest: decision.dest.clone(),
            kind: decision.kind,
            transport: Transport::None,
            send_keys: false,
            pane_target: None,
            view: envelope.view.clone(),
            pick_key: None,
            prompt: String::new(),
            error: Some(
                decision
                    .blocked_reason
                    .clone()
                    .unwrap_or_else(|| format!("unknown dest {}", decision.dest)),
            ),
            decision,
        };
    }

    let buffer = mode == SteerMode::Buffer || is_buffer_request(text);
    AppliedSteer {
        ok: true,
        dest: decision.dest.clone(),
        kind: decision.kind,
        transport: if buffer {
            Transport::NvimBuffer
        } else {
            decision.transport
        },
        send_keys: decision.send_keys && !buffer,
        pane_target: if buffer {
            None
        } else if decision.allow_capture {
            Some(decision.pane_target.clone())
        } else {
            None
        },
        view: envelope.view.clone(),
        pick_key: None,
        prompt: compact_prompt(&decision.dest, text),
        error: None,
        decision,
    }
}
