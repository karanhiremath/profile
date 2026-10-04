use serde::{Deserialize, Serialize};

const COS_DESTS: &[&str] = &["cos", "cos-voice"];
const WORK: &[&str] = &[
    "ao0", "ao1", "ao2", "ao3", "ao4", "infra0", "infra1", "infra2", "infra3", "infra4",
];
const PLAN: &[&str] = &[
    "cos-ao0", "cos-ao1", "cos-ao2", "cos-ao3", "cos-ao4", "cos-infra0", "cos-infra1",
    "cos-infra2", "cos-infra3", "cos-infra4",
];
const PI_DESTS: &[&str] = &["this", "pi"];
const CLAUDE_DESTS: &[&str] = &["claude"];
const HERM_TUI: &[&str] = &["pm", "pl", "notes", "chief"];
const BLOCKED_PERSONAL: &[&str] = &["cosw", "chief-of-staff-work", "cos-work"];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DestKind {
    Cos,
    Pi,
    Claude,
    HermTui,
    Work,
    Plan,
    Brief,
    Host,
    Sandbox,
    Unknown,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Route {
    pub dest: String,
    pub kind: DestKind,
    pub named_from_transcript: Option<String>,
    pub send_keys: bool,
    pub transports: Vec<String>,
    pub copy_cos_inbox: bool,
    #[serde(default)]
    pub mode: String,
}

pub fn is_blocked_personal(dest: &str) -> bool {
    BLOCKED_PERSONAL.contains(&session_name(dest).as_str())
}

pub fn canonicalize_dest(dest: &str) -> String {
    match session_name(dest).as_str() {
        "chief" => "cos".into(),
        "cos-voice" => "cos".into(),
        other => other.to_string(),
    }
}

pub fn dest_kind(dest: &str) -> DestKind {
    let name = dest.split(':').next().unwrap_or("").trim().to_ascii_lowercase();
    if BLOCKED_PERSONAL.contains(&name.as_str()) {
        DestKind::Unknown
    } else if COS_DESTS.contains(&name.as_str()) {
        DestKind::Cos
    } else if PI_DESTS.contains(&name.as_str()) {
        DestKind::Pi
    } else if CLAUDE_DESTS.contains(&name.as_str()) {
        DestKind::Claude
    } else if HERM_TUI.contains(&name.as_str()) {
        DestKind::HermTui
    } else if WORK.contains(&name.as_str()) {
        DestKind::Work
    } else if PLAN.contains(&name.as_str()) {
        DestKind::Plan
    } else if name == "brief" {
        DestKind::Brief
    } else if name == "mac" || name == "oma" || name == "oma-default" {
        DestKind::Host
    } else if name == "mac-s" || name == "oma-s" || name == "oma-default-s" || name.ends_with("-s") {
        DestKind::Sandbox
    } else {
        DestKind::Unknown
    }
}

fn spoken_named_kind(kind: DestKind) -> bool {
    matches!(
        kind,
        DestKind::Work | DestKind::Plan | DestKind::Claude | DestKind::HermTui | DestKind::Cos
    )
}

pub fn named_dest(text: &str) -> Option<String> {
    let cleaned = text.trim();
    if cleaned.is_empty() {
        return None;
    }
    let lower = cleaned.to_ascii_lowercase();
    let first = lower.split(|c: char| c.is_whitespace() || c == ':' || c == ',').next()?;
    if is_blocked_personal(first) {
        return Some(first.to_string());
    }
    if dest_kind(first) != DestKind::Unknown {
        return Some(canonicalize_dest(first));
    }
    for token in lower.split(|c: char| !(c.is_ascii_alphanumeric() || c == '-')) {
        if is_blocked_personal(token) {
            return Some(token.to_string());
        }
        if spoken_named_kind(dest_kind(token)) {
            return Some(canonicalize_dest(token));
        }
    }
    None
}

const BRIEF_CUES: &[&str] = &[
    "status",
    "summary",
    "summarize",
    "fleet",
    "lanes",
    "what's going",
    "whats going",
    "what is going",
    "what changed",
    "brief",
    "update me",
];

const BUFFER_CUES: &[&str] = &["into the buffer", "congress", "edit the prompt", "draft"];

pub fn is_brief_request(text: &str) -> bool {
    let lowered = text.trim().to_ascii_lowercase();
    !lowered.is_empty() && BRIEF_CUES.iter().any(|cue| lowered.contains(cue))
}

pub fn is_buffer_request(text: &str) -> bool {
    let lowered = text.trim().to_ascii_lowercase();
    !lowered.is_empty() && BUFFER_CUES.iter().any(|cue| lowered.contains(cue))
}

fn transports_for(kind: DestKind) -> Vec<String> {
    match kind {
        DestKind::Cos | DestKind::HermTui => vec!["hermes-inbox".into(), "atop-steer".into()],
        DestKind::Pi => vec!["atop-steer-pi".into()],
        DestKind::Claude => vec!["atop-steer-claude-code".into()],
        DestKind::Work => vec!["atop-steer".into(), "tmux-input-buffer".into()],
        DestKind::Plan => vec!["hermes-inbox".into(), "atop-steer".into()],
        DestKind::Brief => vec!["spoken-brief".into()],
        DestKind::Host | DestKind::Sandbox | DestKind::Unknown => vec![],
    }
}

pub fn route(dest: &str, transcript: &str) -> Route {
    route_with_mode(dest, transcript, None)
}

pub fn route_with_mode(dest: &str, transcript: &str, mode: Option<&str>) -> Route {
    let named = named_dest(transcript);
    let dest_in = dest.trim().to_ascii_lowercase();
    let dest_in = if dest_in.is_empty() { "cos".into() } else { dest_in };
    let mode_in = mode.unwrap_or("").trim().to_ascii_lowercase();
    let buffer = mode_in == "buffer" || is_buffer_request(transcript);
    let resolved = if named.is_none()
        && !buffer
        && (dest_in == "brief" || mode_in == "brief" || is_brief_request(transcript))
    {
        "brief".into()
    } else {
        canonicalize_dest(&named.clone().unwrap_or_else(|| dest_in.clone()))
    };
    let kind = dest_kind(&resolved);
    let blocked = is_blocked_personal(&resolved);
    let send_keys =
        !buffer && !blocked && kind == DestKind::Work && !is_operator_blocked(&session_name(&resolved));
    let copy_cos_inbox = !buffer
        && named.is_some()
        && dest_kind(&dest_in) == DestKind::Cos
        && kind != DestKind::Cos
        && !blocked;
    let (mode_out, transports) = if blocked {
        ("steer".into(), vec![])
    } else if buffer && kind != DestKind::Brief && kind != DestKind::Unknown {
        ("buffer".into(), vec!["nvim-buffer".into()])
    } else if kind == DestKind::Brief {
        ("brief".into(), transports_for(kind))
    } else {
        ("steer".into(), transports_for(kind))
    };
    Route {
        dest: resolved,
        kind,
        named_from_transcript: named,
        send_keys,
        transports,
        copy_cos_inbox,
        mode: mode_out,
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Transport {
    HermesInbox,
    InboxAtop,
    InputBuffer,
    Spoken,
    AtopPi,
    AtopClaude,
    HermTui,
    NvimBuffer,
    None,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DestDecision {
    pub dest: String,
    pub session: String,
    pub pane_target: String,
    pub kind: DestKind,
    pub allow_steer: bool,
    pub allow_capture: bool,
    pub allow_inject: bool,
    pub allow_pick: bool,
    pub send_keys: bool,
    pub transport: Transport,
    pub blocked_reason: Option<String>,
}

pub fn session_name(target: &str) -> String {
    target
        .split(':')
        .next()
        .unwrap_or("")
        .trim()
        .to_ascii_lowercase()
}

pub fn default_pane_target(session: &str) -> String {
    format!("{session}:0.0")
}

pub fn is_work_session(session: &str) -> bool {
    dest_kind(session) == DestKind::Work
}

pub fn is_plan_session(session: &str) -> bool {
    dest_kind(session) == DestKind::Plan
}

pub fn is_operator_blocked(session: &str) -> bool {
    if session.is_empty() {
        return true;
    }
    let name = session_name(session);
    if is_blocked_personal(&name) {
        return true;
    }
    name == "cos"
        || name == "cos-voice"
        || name == "cos-mini"
        || name.starts_with("cos-")
        || name == "atop"
        || name.starts_with("atop")
        || name == "pi"
        || name == "this"
        || name == "pm"
        || name == "pl"
        || name == "notes"
        || name == "claude"
        || name == "chief"
}

fn transport_of(kind: DestKind) -> Transport {
    match kind {
        DestKind::Cos => Transport::HermesInbox,
        DestKind::Pi => Transport::AtopPi,
        DestKind::Claude => Transport::AtopClaude,
        DestKind::HermTui => Transport::HermTui,
        DestKind::Work => Transport::InputBuffer,
        DestKind::Plan => Transport::InboxAtop,
        DestKind::Brief => Transport::Spoken,
        DestKind::Host | DestKind::Sandbox | DestKind::Unknown => Transport::None,
    }
}

/// Capture/inject allow-list. Worker panes only. Cos / plan / atop / operator TUIs stay blocked.
pub fn decide_dest(raw: &str) -> DestDecision {
    let parsed = raw.trim();
    let session = session_name(parsed);
    if session.is_empty() {
        return DestDecision {
            dest: parsed.to_string(),
            session: String::new(),
            pane_target: String::new(),
            kind: DestKind::Unknown,
            allow_steer: false,
            allow_capture: false,
            allow_inject: false,
            allow_pick: false,
            send_keys: false,
            transport: Transport::None,
            blocked_reason: Some("empty dest".into()),
        };
    }
    if is_blocked_personal(&session) {
        return DestDecision {
            dest: session.clone(),
            session: session.clone(),
            pane_target: default_pane_target(&session),
            kind: DestKind::Unknown,
            allow_steer: false,
            allow_capture: false,
            allow_inject: false,
            allow_pick: false,
            send_keys: false,
            transport: Transport::None,
            blocked_reason: Some("cosw blocked on personal Cos-voice".into()),
        };
    }
    let kind = dest_kind(&session);
    let pane_target = if kind == DestKind::Pi && !parsed.contains(':') {
        String::new()
    } else if parsed.contains(':') {
        parsed.to_string()
    } else {
        default_pane_target(&session)
    };
    let allow_capture = kind == DestKind::Work && !is_operator_blocked(&session);
    let allow_inject = kind == DestKind::Work;
    let allow_steer = matches!(
        kind,
        DestKind::Cos
            | DestKind::Pi
            | DestKind::Claude
            | DestKind::HermTui
            | DestKind::Work
            | DestKind::Plan
    );
    let blocked_reason = if allow_capture {
        None
    } else if session == "cosw" || is_blocked_personal(&session) {
        Some("cosw blocked on personal Cos-voice".into())
    } else if is_operator_blocked(&session) {
        match kind {
            DestKind::Pi => Some("pi TUI is atop-steer only".into()),
            DestKind::Claude => Some("claude dest is atop-steer; input-buffer only on worker panes".into()),
            DestKind::HermTui => Some("herm-tui is inbox/atop-steer only".into()),
            _ => Some("cos/atop send-keys blocked".into()),
        }
    } else if kind == DestKind::Plan {
        Some("plan panes are inbox-only".into())
    } else if kind == DestKind::Brief {
        None
    } else if kind == DestKind::Host {
        Some("host panes are not a live worker tail".into())
    } else if kind == DestKind::Sandbox {
        Some("sandbox dests are inventory only this iteration".into())
    } else {
        Some("unknown dest".into())
    };
    DestDecision {
        dest: if session == "cos-voice" {
            "cos".into()
        } else {
            session.clone()
        },
        session: session.clone(),
        pane_target,
        kind,
        allow_steer,
        allow_capture,
        allow_inject,
        allow_pick: allow_inject,
        send_keys: allow_inject,
        transport: transport_of(kind),
        blocked_reason,
    }
}

pub fn allow_capture(target: &str) -> Result<DestDecision, DestDecision> {
    let decision = decide_dest(target);
    if decision.allow_capture {
        Ok(decision)
    } else {
        Err(decision)
    }
}

pub fn catalog() -> Vec<DestDecision> {
    let dests = [
        "cos", "cos-voice", "this", "pi", "claude", "pm", "pl", "notes", "chief", "cosw", "ao0",
        "ao1", "ao2", "ao3", "ao4", "infra0", "infra1", "infra2", "infra3", "infra4", "cos-ao0",
        "cos-ao1", "cos-ao2",         "cos-ao3", "cos-ao4", "cos-infra0", "cos-infra1", "cos-infra2",
        "cos-infra3", "cos-infra4", "brief", "atop", "mac", "oma", "oma-default",
        "mac-s", "oma-s",
    ];
    dests.into_iter().map(decide_dest).collect()
}
