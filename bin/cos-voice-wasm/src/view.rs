use serde::{Deserialize, Serialize};

use crate::dest::{allow_capture, DestDecision};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SurfaceView {
    Fleet,
    Otel,
    Pane,
    Voices,
    Sessions,
}

impl SurfaceView {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Fleet => "fleet",
            Self::Otel => "otel",
            Self::Pane => "pane",
            Self::Voices => "voices",
            Self::Sessions => "sessions",
        }
    }
}

impl Default for SurfaceView {
    fn default() -> Self {
        Self::Fleet
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ViewSelection {
    pub ok: bool,
    pub view: SurfaceView,
    pub dest: String,
    pub pane_target: Option<String>,
    pub error: Option<String>,
}

pub fn parse_view(raw: &str) -> Option<SurfaceView> {
    match raw.trim().to_ascii_lowercase().as_str() {
        "fleet" => Some(SurfaceView::Fleet),
        "otel" | "metrics" => Some(SurfaceView::Otel),
        "pane" | "ghostty" | "tmux" => Some(SurfaceView::Pane),
        "voices" | "voice" => Some(SurfaceView::Voices),
        "sessions" | "sids" | "sid" => Some(SurfaceView::Sessions),
        _ => None,
    }
}

pub fn select_view(view: &str, dest: &str) -> ViewSelection {
    let Some(view) = parse_view(view) else {
        return ViewSelection {
            ok: false,
            view: SurfaceView::Fleet,
            dest: dest.to_string(),
            pane_target: None,
            error: Some(format!("unknown view {view}")),
        };
    };

    match view {
        SurfaceView::Fleet | SurfaceView::Otel | SurfaceView::Voices | SurfaceView::Sessions => {
            ViewSelection {
                ok: true,
                view,
                dest: dest.to_string(),
                pane_target: None,
                error: None,
            }
        }
        SurfaceView::Pane => match allow_capture(dest) {
            Ok(decision) => ViewSelection {
                ok: true,
                view,
                dest: decision.dest,
                pane_target: Some(decision.pane_target),
                error: None,
            },
            Err(decision) => ViewSelection {
                ok: false,
                view,
                dest: decision.dest,
                pane_target: None,
                error: Some(
                    decision
                        .blocked_reason
                        .unwrap_or_else(|| "pane view blocked".into()),
                ),
            },
        },
    }
}

pub fn capture_decision_for_view(selection: &ViewSelection) -> Option<DestDecision> {
    if selection.view != SurfaceView::Pane || !selection.ok {
        return None;
    }
    let target = selection.pane_target.as_deref()?;
    allow_capture(target).ok()
}
