//! Hermes profile binding for Cos-voice. Personal YAML only. No secrets.

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

use crate::dest::{is_blocked_personal, session_name};

const BLOCKED_PROFILES: &[&str] = &[
    "chief-of-staff-work",
    "work-notes-steward",
    "cosw",
    "cos-work",
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProfileVoice {
    pub name: String,
    pub found: bool,
    pub lane: String,
    pub tts_enabled: bool,
    pub tts_model: String,
    pub tts_voice_set: bool,
    pub stt_enabled: bool,
    pub stt_model: String,
    pub language: String,
    pub endpoint: String,
}

impl Default for ProfileVoice {
    fn default() -> Self {
        Self {
            name: String::new(),
            found: false,
            lane: "personal".into(),
            tts_enabled: true,
            tts_model: "sonic-3.5".into(),
            tts_voice_set: false,
            stt_enabled: true,
            stt_model: "ink-2".into(),
            language: "en".into(),
            endpoint: "https://api.cartesia.ai".into(),
        }
    }
}

/// Dest chip → committed Hermes profile. `pm`/`pl` are project dests, not a YAML.
pub fn dest_profile(dest: &str) -> Option<String> {
    let name = session_name(dest);
    if is_blocked_personal(&name) || BLOCKED_PROFILES.contains(&name.as_str()) {
        return None;
    }
    match name.as_str() {
        "cos" | "cos-voice" | "chief" => Some("chief-of-staff".into()),
        "notes" => Some("personal-notes-steward".into()),
        other if other == "chief-of-staff" || other.starts_with("personal-") => Some(other.into()),
        _ => None,
    }
}

pub fn profile_blocked(name: &str) -> bool {
    let folded = session_name(name);
    is_blocked_personal(&folded)
        || BLOCKED_PROFILES.contains(&folded.as_str())
        || folded.ends_with("-work")
}

fn home() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("/"))
}

/// Personal search path only. Work Hermes profiles are out of scope here.
pub fn profile_search_dirs() -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    if let Some(extra) = std::env::var_os("COS_VOICE_PROFILE_DIR") {
        dirs.push(PathBuf::from(extra));
    }
    dirs.push(home().join("src/hermes/profiles"));
    dirs.push(home().join("src/profile/bin/hermes/profiles"));
    dirs
}

pub fn profile_path(name: &str) -> Option<PathBuf> {
    if profile_blocked(name) {
        return None;
    }
    let file = format!("{name}.yaml");
    for dir in profile_search_dirs() {
        let path = dir.join(&file);
        if path.is_file() {
            return Some(path);
        }
    }
    None
}

pub fn parse_profile_yaml(text: &str) -> ProfileVoice {
    let mut out = ProfileVoice::default();
    let mut section = "";
    let mut skip_block = false;
    for raw in text.lines() {
        let line = raw.trim_end();
        let trimmed = line.trim();
        if skip_block {
            if !trimmed.is_empty() && !line.starts_with(' ') && !line.starts_with('\t') {
                skip_block = false;
            } else {
                continue;
            }
        }
        if trimmed.ends_with('|') {
            skip_block = true;
            continue;
        }
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if !line.starts_with(' ') && !line.starts_with('\t') {
            if let Some((key, rest)) = trimmed.split_once(':') {
                let key = key.trim();
                let value = unquote(rest.trim());
                match key {
                    "name" if !value.is_empty() => out.name = value,
                    "tts" => section = "tts",
                    "stt" => section = "stt",
                    "endpoint" => section = "endpoint",
                    "llm" | "sandbox" | "terminal" | "herm" | "display" | "toolsets"
                    | "persona" | "surface" | "platform" => section = key,
                    _ => {}
                }
            }
            continue;
        }
        if let Some((key, rest)) = trimmed.split_once(':') {
            let key = key.trim();
            let value = unquote(rest.trim());
            match (section, key) {
                ("tts", "enabled") => out.tts_enabled = truthy(&value),
                ("tts", "model") if !value.is_empty() => out.tts_model = value,
                ("tts", "voice") => out.tts_voice_set = !value.is_empty(),
                ("stt", "enabled") => out.stt_enabled = truthy(&value),
                ("stt", "model") if !value.is_empty() => out.stt_model = value,
                ("stt", "language") if !value.is_empty() => out.language = value,
                ("endpoint", "base_url") => {
                    if value == "https://api.cartesia.ai" {
                        out.endpoint = value;
                    } else if !value.is_empty() {
                        out.endpoint = "redacted".into();
                    }
                }
                _ => {}
            }
        }
    }
    out.found = !out.name.is_empty();
    if profile_blocked(&out.name) {
        out.found = false;
        out.lane = "blocked".into();
    }
    out
}

fn unquote(value: &str) -> String {
    let without_comment = if let Some((head, _)) = value.split_once(" #") {
        head
    } else {
        value
    };
    let trimmed = without_comment.trim();
    if (trimmed.starts_with('"') && trimmed.ends_with('"') && trimmed.len() >= 2)
        || (trimmed.starts_with('\'') && trimmed.ends_with('\'') && trimmed.len() >= 2)
    {
        trimmed[1..trimmed.len() - 1].to_string()
    } else {
        trimmed.to_string()
    }
}

fn truthy(value: &str) -> bool {
    matches!(value, "true" | "True" | "yes" | "1")
}

pub fn load_profile(name: &str) -> ProfileVoice {
    if profile_blocked(name) {
        let mut blocked = ProfileVoice {
            name: session_name(name),
            found: false,
            lane: "blocked".into(),
            tts_enabled: false,
            stt_enabled: false,
            ..ProfileVoice::default()
        };
        blocked.name = session_name(name);
        return blocked;
    }
    match profile_path(name).and_then(|path| fs::read_to_string(path).ok()) {
        Some(text) => {
            let mut parsed = parse_profile_yaml(&text);
            if parsed.name.is_empty() {
                parsed.name = name.to_string();
            }
            parsed.found = true;
            parsed
        }
        None => ProfileVoice {
            name: name.to_string(),
            found: false,
            ..ProfileVoice::default()
        },
    }
}

pub fn load_profile_from(path: &Path) -> Option<ProfileVoice> {
    let text = fs::read_to_string(path).ok()?;
    let mut parsed = parse_profile_yaml(&text);
    parsed.found = !parsed.name.is_empty();
    Some(parsed)
}

pub fn bind_dest(dest: &str) -> ProfileVoice {
    match dest_profile(dest) {
        Some(name) => load_profile(&name),
        None => ProfileVoice {
            name: String::new(),
            found: false,
            tts_enabled: true,
            stt_enabled: true,
            ..ProfileVoice::default()
        },
    }
}
