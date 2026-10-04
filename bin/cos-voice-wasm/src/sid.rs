//! Live sid map. Pane addresses are hints only. Never invent a sid.

use serde::{Deserialize, Serialize};

use crate::dest::{catalog, dest_kind, is_blocked_personal, session_name, DestKind};
use crate::profile::dest_profile;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SidRecord {
    pub dest: String,
    pub kind: DestKind,
    pub profile: Option<String>,
    pub harness: String,
    pub target_form: String,
    pub sid: Option<String>,
    pub pane_hint: Option<String>,
    pub live: bool,
    pub bindable: bool,
    pub note: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SidMap {
    pub ok: bool,
    pub view: String,
    pub rows: Vec<SidRecord>,
    pub bindable: Vec<String>,
    pub unknown: Vec<String>,
    pub note: String,
}

pub fn looks_like_tmux_pane(value: &str) -> bool {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return false;
    }
    let body = trimmed.strip_prefix("tmux:").unwrap_or(trimmed);
    let mut parts = body.split(':');
    let session = parts.next().unwrap_or("");
    let pane = parts.next().unwrap_or("");
    if session.is_empty() || pane.is_empty() || parts.next().is_some() {
        return false;
    }
    let mut xy = pane.split('.');
    let x = xy.next().unwrap_or("");
    let y = xy.next().unwrap_or("");
    !x.is_empty()
        && !y.is_empty()
        && xy.next().is_none()
        && x.chars().all(|c| c.is_ascii_digit())
        && y.chars().all(|c| c.is_ascii_digit())
}

fn harness_for(kind: DestKind) -> &'static str {
    match kind {
        DestKind::Cos | DestKind::HermTui => "hermes",
        DestKind::Pi => "pi",
        DestKind::Claude | DestKind::Work | DestKind::Plan => "claude-code",
        DestKind::Brief | DestKind::Host | DestKind::Sandbox | DestKind::Unknown => "none",
    }
}

fn target_form(kind: DestKind) -> &'static str {
    match kind {
        DestKind::Work => "pane",
        DestKind::Pi | DestKind::Cos | DestKind::HermTui | DestKind::Claude | DestKind::Plan => {
            "sid"
        }
        DestKind::Brief | DestKind::Host | DestKind::Sandbox | DestKind::Unknown => "none",
    }
}

fn contract_note(kind: DestKind, dest: &str) -> String {
    if is_blocked_personal(dest) {
        return "blocked on personal Cos-voice".into();
    }
    match kind {
        DestKind::Pi => "target=<sid> or COS_VOICE_PI_SID; never this:0.0".into(),
        DestKind::HermTui => "resolve via hermes/agents; do not invent a profile or sid".into(),
        DestKind::Cos => {
            "chief-of-staff inbox; tmux pane is not a hermes sid".into()
        }
        DestKind::Claude => "atop-steer claude-code; send-keys only on ao*/infra* panes".into(),
        DestKind::Work => "pane ao*|infra* is a tmux target, not a herm-tui sid".into(),
        DestKind::Plan => "inbox / atop only; no send-keys".into(),
        DestKind::Brief => "spoken only".into(),
        DestKind::Host | DestKind::Sandbox => "inventory only this iteration".into(),
        DestKind::Unknown => "unknown dest".into(),
    }
}

pub fn sid_contract() -> SidMap {
    enrich_sids(&serde_json::json!({}))
}

fn snapshot_map<'a>(
    snapshot: &'a serde_json::Value,
    key: &str,
) -> std::collections::BTreeMap<String, String> {
    let mut out = std::collections::BTreeMap::new();
    if let Some(obj) = snapshot.get(key).and_then(|v| v.as_object()) {
        for (dest, value) in obj {
            if let Some(text) = value.as_str().map(str::trim).filter(|s| !s.is_empty()) {
                out.insert(session_name(dest), text.to_string());
            }
        }
    }
    out
}

fn accept_sid(kind: DestKind, dest: &str, raw: &str) -> Result<String, String> {
    let sid = raw.trim();
    if sid.is_empty() {
        return Err("empty sid".into());
    }
    if is_blocked_personal(dest) {
        return Err("blocked dest".into());
    }
    match kind {
        DestKind::Pi => {
            if sid == "this" || sid == "pi" || looks_like_tmux_pane(sid) {
                Err("pi dest needs target=sid; do not invent this:0.0".into())
            } else {
                Ok(sid.to_string())
            }
        }
        DestKind::Cos | DestKind::HermTui => {
            if looks_like_tmux_pane(sid) {
                Err("pane address is not a hermes sid".into())
            } else {
                Ok(sid.to_string())
            }
        }
        DestKind::Claude | DestKind::Plan => {
            if looks_like_tmux_pane(sid) {
                Err("pane hint is not a confirmed claude/plan sid".into())
            } else {
                Ok(sid.to_string())
            }
        }
        DestKind::Work => {
            if looks_like_tmux_pane(sid) || !sid.contains(':') {
                Ok(if looks_like_tmux_pane(sid) {
                    sid.to_string()
                } else {
                    format!("{dest}:0.0")
                })
            } else {
                Ok(sid.to_string())
            }
        }
        _ => Err("dest does not take a sid".into()),
    }
}

pub fn enrich_sids(snapshot: &serde_json::Value) -> SidMap {
    let sids = snapshot_map(snapshot, "sids");
    let panes = snapshot_map(snapshot, "panes");
    let mut rows = Vec::new();
    for decision in catalog() {
        let dest = decision.dest.clone();
        let kind = dest_kind(&dest);
        let profile = dest_profile(&dest);
        let pane_hint = panes.get(&dest).cloned().filter(|p| looks_like_tmux_pane(p));
        let mut sid = None;
        let mut live = false;
        let mut bindable = false;
        let mut note = contract_note(kind, &dest);
        if is_blocked_personal(&dest) {
            rows.push(SidRecord {
                dest,
                kind: DestKind::Unknown,
                profile: None,
                harness: "none".into(),
                target_form: "none".into(),
                sid: None,
                pane_hint: None,
                live: false,
                bindable: false,
                note,
            });
            continue;
        }
        if let Some(raw) = sids.get(&dest) {
            match accept_sid(kind, &dest, raw) {
                Ok(confirmed) => {
                    sid = Some(confirmed);
                    live = true;
                    bindable = matches!(
                        kind,
                        DestKind::Pi
                            | DestKind::Cos
                            | DestKind::HermTui
                            | DestKind::Claude
                            | DestKind::Work
                            | DestKind::Plan
                    );
                    note = "confirmed snapshot sid".into();
                }
                Err(err) => note = err,
            }
        } else if kind == DestKind::Work {
            bindable = true;
            note = "worker pane target; not a herm-tui sid".into();
        }
        rows.push(SidRecord {
            dest,
            kind,
            profile,
            harness: harness_for(kind).into(),
            target_form: target_form(kind).into(),
            sid,
            pane_hint,
            live,
            bindable,
            note,
        });
    }
    let bindable = rows
        .iter()
        .filter(|row| row.bindable)
        .map(|row| row.dest.clone())
        .collect();
    let unknown = rows
        .iter()
        .filter(|row| {
            matches!(row.target_form.as_str(), "sid") && row.sid.is_none() && !is_blocked_personal(&row.dest)
        })
        .map(|row| row.dest.clone())
        .collect();
    SidMap {
        ok: true,
        view: "sessions".into(),
        rows,
        bindable,
        unknown,
        note: "Live sids are snapshot-only. tmux pane hints never become this/pi/herm-tui sids.".into(),
    }
}
