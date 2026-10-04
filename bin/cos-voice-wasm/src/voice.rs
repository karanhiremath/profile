//! Cartesia voice assignment for the WASM view. Public voice ids only.
//! YAML profile secrets stay out of this module.

use serde::{Deserialize, Serialize};

use crate::dest::{catalog, dest_kind, is_blocked_personal, session_name, DestKind};

/// Operator-chosen default for Cos / Cos-voice / chief. Public Cartesia voice id.
pub const DEFAULT_COS_VOICE_ID: &str = "f6141af3-5f94-418c-80ed-a45d450e7e2e";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VoiceCatalogEntry {
    pub id: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub language: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VoiceAssignment {
    pub dest: String,
    pub profile: String,
    pub kind: DestKind,
    pub voice_id: String,
    pub source: String,
    pub distinct: bool,
    pub note: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VoiceView {
    pub ok: bool,
    pub view: String,
    pub default_cos_voice_id: String,
    pub assignments: Vec<VoiceAssignment>,
    pub catalog: Vec<VoiceCatalogEntry>,
    pub unassigned: Vec<String>,
    pub note: String,
}

pub fn is_cos_voice_dest(dest: &str) -> bool {
    matches!(session_name(dest).as_str(), "cos" | "cos-voice" | "chief")
}

pub fn voice_profile_key(dest: &str) -> String {
    let name = session_name(dest);
    match name.as_str() {
        "cos" | "cos-voice" | "chief" => "chief-of-staff".into(),
        "notes" => "personal-notes-steward".into(),
        "this" | "pi" => "pi".into(),
        other => other.to_string(),
    }
}

fn voice_dests() -> Vec<String> {
    catalog()
        .into_iter()
        .filter(|row| {
            !is_blocked_personal(&row.session)
                && matches!(
                    row.kind,
                    DestKind::Cos
                        | DestKind::Pi
                        | DestKind::Claude
                        | DestKind::HermTui
                        | DestKind::Work
                        | DestKind::Plan
                        | DestKind::Brief
                )
        })
        .map(|row| row.dest)
        .collect()
}

pub fn parse_catalog(value: &serde_json::Value) -> Vec<VoiceCatalogEntry> {
    let rows = value
        .get("data")
        .or_else(|| value.get("voices"))
        .or_else(|| value.get("catalog"))
        .cloned()
        .unwrap_or_else(|| {
            if value.is_array() {
                value.clone()
            } else {
                serde_json::json!([])
            }
        });
    let Some(list) = rows.as_array() else {
        return Vec::new();
    };
    let mut out = Vec::new();
    let mut seen = std::collections::BTreeSet::new();
    for row in list {
        let id = row
            .get("id")
            .or_else(|| row.get("voice_id"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();
        if id.is_empty() || !seen.insert(id.clone()) {
            continue;
        }
        out.push(VoiceCatalogEntry {
            name: row
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .chars()
                .take(80)
                .collect(),
            language: row
                .get("language")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .into(),
            id,
        });
    }
    out
}

fn next_unused<'a>(
    catalog: &'a [VoiceCatalogEntry],
    used: &std::collections::BTreeSet<String>,
) -> Option<&'a VoiceCatalogEntry> {
    catalog.iter().find(|row| {
        !used.contains(&row.id) && row.id != DEFAULT_COS_VOICE_ID
    })
}

pub fn assign_voice(
    dest: &str,
    catalog: &[VoiceCatalogEntry],
    used: &std::collections::BTreeSet<String>,
) -> VoiceAssignment {
    let dest = session_name(dest);
    let kind = dest_kind(&dest);
    let profile = voice_profile_key(&dest);
    if dest.is_empty() || is_blocked_personal(&dest) {
        return VoiceAssignment {
            dest: dest.clone(),
            profile,
            kind: DestKind::Unknown,
            voice_id: String::new(),
            source: "blocked".into(),
            distinct: false,
            note: "blocked dest has no voice".into(),
        };
    }
    if is_cos_voice_dest(&dest) || dest == "brief" {
        return VoiceAssignment {
            dest,
            profile,
            kind,
            voice_id: DEFAULT_COS_VOICE_ID.into(),
            source: "default".into(),
            distinct: true,
            note: "Cos-voice default Cartesia voice".into(),
        };
    }
    if let Some(entry) = next_unused(catalog, used) {
        return VoiceAssignment {
            dest,
            profile,
            kind,
            voice_id: entry.id.clone(),
            source: "catalog".into(),
            distinct: true,
            note: format!("distinct catalog voice {}", entry.name),
        };
    }
    VoiceAssignment {
        dest,
        profile,
        kind,
        voice_id: String::new(),
        source: "unassigned".into(),
        distinct: false,
        note: "needs a distinct Cartesia voice; do not reuse the Cos default".into(),
    }
}

pub fn plan_voices(catalog: &[VoiceCatalogEntry]) -> VoiceView {
    let mut used = std::collections::BTreeSet::new();
    used.insert(DEFAULT_COS_VOICE_ID.to_string());
    let mut assignments = Vec::new();
    for dest in voice_dests() {
        let assigned = assign_voice(&dest, catalog, &used);
        if assigned.source == "catalog" && !assigned.voice_id.is_empty() {
            used.insert(assigned.voice_id.clone());
        }
        assignments.push(assigned);
    }
    let unassigned = assignments
        .iter()
        .filter(|row| row.source == "unassigned")
        .map(|row| row.dest.clone())
        .collect();
    VoiceView {
        ok: true,
        view: "voices".into(),
        default_cos_voice_id: DEFAULT_COS_VOICE_ID.into(),
        assignments,
        catalog: catalog.to_vec(),
        unassigned,
        note: "WASM assigns public voice ids only. Host TTS applies them. YAML voice values stay on the host.".into(),
    }
}

pub fn plan_voices_from_json(catalog: &serde_json::Value) -> VoiceView {
    plan_voices(&parse_catalog(catalog))
}
