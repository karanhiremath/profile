use crate::dest::{is_operator_blocked, session_name, DestKind, Route};
use serde::{Deserialize, Serialize};

/// Deterministic apply plan. Effects stay at the edge; this crate does not
/// send-keys into Cos or Atop. Browser/PTY frames are a sibling surface.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ApplyPlan {
    pub dest: String,
    pub kind: String,
    pub transports: Vec<String>,
    pub send_keys: bool,
    pub blocked_targets: Vec<String>,
    pub note: String,
}

pub fn plan(route: &Route) -> ApplyPlan {
    let session = session_name(&route.dest);
    let buffer = route.mode == "buffer" || route.transports.iter().any(|t| t == "nvim-buffer");
    let send_keys = !buffer
        && route.send_keys
        && route.kind == DestKind::Work
        && !is_operator_blocked(&session);
    ApplyPlan {
        dest: route.dest.clone(),
        kind: format!("{:?}", route.kind).to_ascii_lowercase(),
        transports: route.transports.clone(),
        send_keys,
        blocked_targets: vec![
            "cos".into(),
            "cos-*".into(),
            "atop*".into(),
            "cosw".into(),
            "pi".into(),
            "this".into(),
            "pi-tui".into(),
            "herm-tui".into(),
        ],
        note: if buffer {
            "congress nvim prompt.md; no send-keys; no buffer sync".into()
        } else if send_keys {
            "worker input-buffer allowed; Cos/Atop still blocked".into()
        } else if matches!(route.kind, DestKind::Host | DestKind::Sandbox) {
            "attach grammar; no send-keys; s2s plan only".into()
        } else {
            "inbox / atop-steer / brief only".into()
        },
    }
}
