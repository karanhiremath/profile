use serde::{Deserialize, Serialize};

use crate::dest::DestDecision;
use crate::view::SurfaceView;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PaneFrame {
    pub ok: bool,
    pub view: SurfaceView,
    pub target: String,
    pub text: String,
    pub blocked: bool,
    pub error: Option<String>,
    pub seq: u64,
}

pub fn encode_pane_frame(decision: &DestDecision, text: &str, seq: u64) -> PaneFrame {
    if !decision.allow_capture {
        return PaneFrame {
            ok: false,
            view: SurfaceView::Pane,
            target: decision.pane_target.clone(),
            text: String::new(),
            blocked: true,
            error: decision.blocked_reason.clone(),
            seq,
        };
    }
    PaneFrame {
        ok: true,
        view: SurfaceView::Pane,
        target: decision.pane_target.clone(),
        text: text.to_string(),
        blocked: false,
        error: None,
        seq,
    }
}

pub fn blocked_frame(target: &str, reason: &str, seq: u64) -> PaneFrame {
    PaneFrame {
        ok: false,
        view: SurfaceView::Pane,
        target: target.to_string(),
        text: String::new(),
        blocked: true,
        error: Some(reason.to_string()),
        seq,
    }
}
