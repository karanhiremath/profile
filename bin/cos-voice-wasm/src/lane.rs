//! Spoken lane grammar -> existing fleet lane primitives (`fleet ls` / `fleet plan` /
//! `fleet attach` / `fleet steer`). Pure string parsing: no sockets, no network, no
//! `std::process`. Reuses `crate::dest::is_operator_blocked` for the steer boundary —
//! never forks or weakens it.

use serde::{Deserialize, Serialize};

use crate::dest::is_operator_blocked;

const LANES: &[&str] = &[
    "ao0", "ao1", "ao2", "ao3", "ao4", "infra0", "infra1", "infra2", "infra3", "infra4",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LaneAction {
    List,
    Plan,
    Work,
    Steer,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LanePlan {
    pub ok: bool,
    pub action: LaneAction,
    pub lane: String,
    pub window: String,
    pub target: String,
    pub command: String,
    pub message: String,
    pub allow_send_keys: bool,
    pub blocked_reason: Option<String>,
}

pub fn lane_targets() -> Vec<String> {
    let mut out = Vec::with_capacity(LANES.len() * 4);
    for lane in LANES {
        out.push(format!("{lane}:do"));
        out.push(format!("{lane}:pi"));
        out.push(format!("cos-{lane}:think"));
        out.push(format!("cos-{lane}:cos"));
    }
    out
}

enum LaneTok {
    Found(String),
    Unknown(String),
}

enum LaneScan {
    Found(String),
    Unknown(String),
    NotFound,
}

fn word_to_digit(w: &str) -> Option<u32> {
    match w {
        "0" | "zero" => Some(0),
        "1" | "one" => Some(1),
        "2" | "two" => Some(2),
        "3" | "three" => Some(3),
        "4" | "four" => Some(4),
        "5" | "five" => Some(5),
        "6" | "six" => Some(6),
        "7" | "seven" => Some(7),
        "8" | "eight" => Some(8),
        "9" | "nine" => Some(9),
        _ => None,
    }
}

fn norm_word(w: &str) -> String {
    w.chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .collect::<String>()
        .to_ascii_lowercase()
}

/// Tries to read a lane code starting at `norm[idx]`. Handles the fused form
/// ("ao4", "ao-4" after normalization collapses to "ao4") and the spoken form
/// ("ao" "four"). Returns the token result plus how many `norm` slots it consumed.
fn try_lane_at(norm: &[String], idx: usize) -> Option<(LaneTok, usize)> {
    let tok = norm.get(idx)?.as_str();
    for prefix in ["ao", "infra"] {
        let Some(rest) = tok.strip_prefix(prefix) else { continue };
        if rest.is_empty() {
            return Some(match norm.get(idx + 1) {
                Some(next) => match word_to_digit(next) {
                    Some(d) => {
                        let lane = format!("{prefix}{d}");
                        if LANES.contains(&lane.as_str()) {
                            (LaneTok::Found(lane), 2)
                        } else {
                            (LaneTok::Unknown(lane), 2)
                        }
                    }
                    None => (LaneTok::Unknown(format!("{prefix} {next}")), 2),
                },
                None => (LaneTok::Unknown(prefix.to_string()), 1),
            });
        }
        return Some(match rest.parse::<u32>() {
            Ok(d) => {
                let lane = format!("{prefix}{d}");
                if LANES.contains(&lane.as_str()) {
                    (LaneTok::Found(lane), 1)
                } else {
                    (LaneTok::Unknown(lane), 1)
                }
            }
            Err(_) => (LaneTok::Unknown(tok.to_string()), 1),
        });
    }
    None
}

fn scan_for_lane(norm: &[String]) -> LaneScan {
    for idx in 0..norm.len() {
        if let Some((tok, _consumed)) = try_lane_at(norm, idx) {
            return match tok {
                LaneTok::Found(lane) => LaneScan::Found(lane),
                LaneTok::Unknown(attempted) => LaneScan::Unknown(attempted),
            };
        }
    }
    LaneScan::NotFound
}

fn plan_plan(lane: String) -> LanePlan {
    let target = format!("cos-{lane}:think");
    LanePlan {
        ok: true,
        action: LaneAction::Plan,
        lane: lane.clone(),
        window: "think".into(),
        command: format!("fleet plan {lane}"),
        target,
        message: String::new(),
        allow_send_keys: false,
        blocked_reason: None,
    }
}

fn work_plan(lane: String) -> LanePlan {
    let target = format!("{lane}:do");
    LanePlan {
        ok: true,
        action: LaneAction::Work,
        lane: lane.clone(),
        window: "do".into(),
        command: format!("fleet attach {lane}"),
        target,
        message: String::new(),
        allow_send_keys: false,
        blocked_reason: None,
    }
}

fn blocked_attach(is_plan: bool, attempted: Option<String>) -> LanePlan {
    let action = if is_plan { LaneAction::Plan } else { LaneAction::Work };
    let reason = match attempted {
        Some(lane) => format!("unknown lane: {lane}"),
        None => "no lane specified".to_string(),
    };
    LanePlan {
        ok: false,
        action,
        lane: String::new(),
        window: String::new(),
        target: String::new(),
        command: String::new(),
        message: String::new(),
        allow_send_keys: false,
        blocked_reason: Some(reason),
    }
}

fn blocked_steer(lane: String, window: String, target: String, message: String, reason: String) -> LanePlan {
    LanePlan {
        ok: false,
        action: LaneAction::Steer,
        lane,
        window,
        target,
        command: String::new(),
        message,
        allow_send_keys: false,
        blocked_reason: Some(reason),
    }
}

fn build_steer(lane: String, session: String, window: String, message: String) -> LanePlan {
    let target = format!("{session}:{window}");
    if is_operator_blocked(&session) {
        return blocked_steer(
            lane,
            window,
            target,
            message,
            format!("{session} is an operator-blocked session (cos-/atop/pi/herm-tui); attach/view only"),
        );
    }
    if window != "do" && window != "pi" {
        return blocked_steer(
            lane,
            window,
            target,
            message,
            "steer may only target a bare <lane>:do or <lane>:pi window".into(),
        );
    }
    if message.is_empty() {
        return blocked_steer(lane, window, target, message, "empty steer message".into());
    }
    let command = format!("fleet steer {target} {message}");
    LanePlan {
        ok: true,
        action: LaneAction::Steer,
        lane,
        window,
        target,
        command,
        message,
        allow_send_keys: true,
        blocked_reason: None,
    }
}

fn parse_steer(words: &[&str], norm: &[String], start: usize) -> LanePlan {
    let rest_norm = &norm[start..];
    let rest_words = &words[start..];
    let cos_prefix = rest_norm.first().map(|t| t == "cos").unwrap_or(false);
    let lane_scan_idx = if cos_prefix { 1 } else { 0 };

    if let Some((tok, consumed)) = try_lane_at(rest_norm, lane_scan_idx) {
        return match tok {
            LaneTok::Found(lane) => {
                let after = lane_scan_idx + consumed;
                let session = if cos_prefix { format!("cos-{lane}") } else { lane.clone() };
                let window = rest_norm.get(after).cloned().unwrap_or_default();
                let msg_start = after + usize::from(!window.is_empty());
                let message = rest_words
                    .get(msg_start..)
                    .map(|s| s.join(" "))
                    .unwrap_or_default()
                    .trim()
                    .to_string();
                build_steer(lane, session, window, message)
            }
            LaneTok::Unknown(attempted) => LanePlan {
                ok: false,
                action: LaneAction::Steer,
                lane: String::new(),
                window: String::new(),
                target: String::new(),
                command: String::new(),
                message: String::new(),
                allow_send_keys: false,
                blocked_reason: Some(format!("unknown lane: {attempted}")),
            },
        };
    }

    // No "ao"/"infra" lane pattern found: the leading word(s) are a literal
    // session name (e.g. bare "cos" or "atop"), not a lane at all.
    let session = if cos_prefix {
        "cos".to_string()
    } else {
        rest_norm.first().cloned().unwrap_or_default()
    };
    let window_idx = 1;
    let window = rest_norm.get(window_idx).cloned().unwrap_or_default();
    let msg_start = window_idx + usize::from(!window.is_empty());
    let message = rest_words
        .get(msg_start..)
        .map(|s| s.join(" "))
        .unwrap_or_default()
        .trim()
        .to_string();
    let target = if window.is_empty() { session.clone() } else { format!("{session}:{window}") };
    let reason = if is_operator_blocked(&session) {
        format!("{session} is an operator-blocked session (cos-/atop/pi/herm-tui); attach/view only")
    } else if session.is_empty() {
        "no lane or session specified".to_string()
    } else {
        format!("unknown lane: {session}")
    };
    LanePlan {
        ok: false,
        action: LaneAction::Steer,
        lane: String::new(),
        window,
        target,
        command: String::new(),
        message,
        allow_send_keys: false,
        blocked_reason: Some(reason),
    }
}

pub fn parse_lane(utterance: &str) -> LanePlan {
    let words: Vec<&str> = utterance.split_whitespace().collect();
    let norm: Vec<String> = words.iter().map(|w| norm_word(w)).collect();

    if let Some(steer_idx) = norm.iter().position(|t| t == "steer") {
        return parse_steer(&words, &norm, steer_idx + 1);
    }

    if norm.iter().any(|t| t == "list") && norm.iter().any(|t| t == "lane" || t == "lanes") {
        return LanePlan {
            ok: true,
            action: LaneAction::List,
            lane: String::new(),
            window: String::new(),
            target: String::new(),
            command: "fleet ls".into(),
            message: String::new(),
            allow_send_keys: false,
            blocked_reason: None,
        };
    }

    let is_plan = norm.iter().any(|t| t == "plan" || t == "cos" || t == "think");
    match scan_for_lane(&norm) {
        LaneScan::Found(lane) => {
            if is_plan {
                plan_plan(lane)
            } else {
                work_plan(lane)
            }
        }
        LaneScan::Unknown(attempted) => blocked_attach(is_plan, Some(attempted)),
        LaneScan::NotFound => blocked_attach(is_plan, None),
    }
}
