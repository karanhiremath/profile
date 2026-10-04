use serde::{Deserialize, Serialize};

/// One INDEX.jsonl row. Voice appends to `path`; it does not sync or commit.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BufferRecord {
    #[serde(default)]
    pub ts: String,
    #[serde(default)]
    pub path: String,
    #[serde(default)]
    pub session_hint: Option<String>,
    #[serde(default)]
    pub size: Option<u64>,
    #[serde(default)]
    pub buffer_dir: Option<String>,
    #[serde(default)]
    pub pane_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BufferPlan {
    pub dest: String,
    pub session_hint: String,
    pub path: Option<String>,
    pub send_keys: bool,
    pub sync: bool,
    pub commit: bool,
    pub append: String,
    pub note: String,
}

pub fn parse_index(text: &str) -> Vec<BufferRecord> {
    text.lines()
        .filter(|line| !line.trim().is_empty())
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect()
}

pub fn hint_matches(session_hint: &str, dest: &str) -> bool {
    let hint = session_hint.trim();
    let dest = dest.trim();
    if hint.is_empty() || dest.is_empty() {
        return false;
    }
    let hint_session = hint.split(':').next().unwrap_or("").trim();
    let dest_session = dest.split(':').next().unwrap_or("").trim();
    !hint_session.is_empty()
        && !dest_session.is_empty()
        && hint_session.eq_ignore_ascii_case(dest_session)
}

pub fn latest_for_session<'a>(records: &'a [BufferRecord], dest: &str) -> Option<&'a BufferRecord> {
    records.iter().rev().find(|row| {
        row.session_hint
            .as_deref()
            .is_some_and(|hint| hint_matches(hint, dest))
            && !row.path.trim().is_empty()
    })
}

/// Plan a congress append. No filesystem writes. Host/edge applies `path`.
pub fn plan_append(dest: &str, transcript: &str, records: &[BufferRecord]) -> BufferPlan {
    let dest = dest.trim().to_ascii_lowercase();
    let dest = if dest.is_empty() { "cos".into() } else { dest };
    let row = latest_for_session(records, &dest);
    BufferPlan {
        dest: dest.clone(),
        session_hint: row
            .and_then(|r| r.session_hint.clone())
            .unwrap_or_else(|| dest),
        path: row.map(|r| r.path.clone()),
        send_keys: false,
        sync: false,
        commit: false,
        append: transcript.trim().to_string(),
        note: if row.is_some() {
            "append prompt.md; no send-keys; no buffer sync".into()
        } else {
            "no open prompt.md for dest; no send-keys".into()
        },
    }
}
