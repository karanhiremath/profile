use crate::error::AosError;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

pub const SCHEMA: &str = "aos.data.v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum VaultClass {
    Personal,
    Work,
}

impl VaultClass {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Personal => "personal",
            Self::Work => "work",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Manifest {
    pub schema: String,
    pub lane: String,
    pub class: VaultClass,
    pub name: String,
    #[serde(default)]
    pub paths: Paths,
    #[serde(default)]
    pub templates: Templates,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Paths {
    #[serde(default = "default_daily")]
    pub daily: String,
    #[serde(default = "default_daily_name")]
    pub daily_name: String,
    #[serde(default = "default_inbox")]
    pub inbox: String,
    #[serde(default)]
    pub weekly: Option<String>,
    #[serde(default)]
    pub monthly: Option<String>,
    #[serde(default)]
    pub updates: Option<String>,
    #[serde(default)]
    pub search_roots: Vec<String>,
}

impl Default for Paths {
    fn default() -> Self {
        Self {
            daily: default_daily(),
            daily_name: default_daily_name(),
            inbox: default_inbox(),
            weekly: None,
            monthly: None,
            updates: None,
            search_roots: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Templates {
    pub daily: Option<String>,
}

fn default_daily() -> String {
    "daily".into()
}
fn default_daily_name() -> String {
    "{date}.md".into()
}
fn default_inbox() -> String {
    "01_in".into()
}

impl Manifest {
    pub fn load(path: &Path) -> Result<Self, AosError> {
        let raw = fs::read_to_string(path).map_err(|e| AosError::msg(format!("{path}: {e}", path = path.display())))?;
        let m: Manifest = toml::from_str(&raw).map_err(|e| AosError::msg(format!("manifest: {e}")))?;
        if m.schema != SCHEMA {
            return Err(AosError::msg(format!(
                "unsupported schema {} (want {SCHEMA})",
                m.schema
            )));
        }
        if m.lane != "ao0" && m.lane != "aos-data" {
            return Err(AosError::msg(format!("lane must be ao0 (got {})", m.lane)));
        }
        Ok(m)
    }

    pub fn search_roots(&self) -> Vec<String> {
        if self.paths.search_roots.is_empty() {
            vec![
                self.paths.daily.clone(),
                self.paths.inbox.clone(),
            ]
        } else {
            self.paths.search_roots.clone()
        }
    }
}

pub fn find_manifest(start: &Path) -> Option<PathBuf> {
    let mut cur = start.to_path_buf();
    loop {
        for rel in [
            "aos-data.toml",
            ".aos-data.toml",
            "03_tech/agentic-os/aos-data.toml",
            "agentic/aos-data.toml",
        ] {
            let p = cur.join(rel);
            if p.is_file() {
                return Some(p);
            }
        }
        if !cur.pop() {
            return None;
        }
    }
}

/// Manifest may sit at vault root or under 03_tech/agentic-os / agentic.
pub fn vault_root_for_manifest(manifest: &Path) -> PathBuf {
    let parent = manifest.parent().unwrap_or(manifest);
    let name = parent.file_name().and_then(|s| s.to_str()).unwrap_or("");
    if name == "agentic-os" {
        if let Some(tech) = parent.parent() {
            if tech.file_name().and_then(|s| s.to_str()) == Some("03_tech") {
                if let Some(root) = tech.parent() {
                    return root.to_path_buf();
                }
            }
        }
    }
    if name == "agentic" {
        if let Some(root) = parent.parent() {
            return root.to_path_buf();
        }
    }
    parent.to_path_buf()
}

pub fn builtin_personal() -> Manifest {
    Manifest {
        schema: SCHEMA.into(),
        lane: "ao0".into(),
        class: VaultClass::Personal,
        name: "notes".into(),
        paths: Paths {
            daily: "02_personal/daily".into(),
            daily_name: "{date} {weekday}.md".into(),
            inbox: "01_in".into(),
            weekly: Some("02_personal/weekly".into()),
            monthly: Some("02_personal/monthly".into()),
            updates: Some("03_tech/agentic-os/fleet/updates".into()),
            search_roots: vec![
                "01_in".into(),
                "02_personal".into(),
                "03_tech".into(),
            ],
        },
        templates: Templates::default(),
    }
}

pub fn builtin_work() -> Manifest {
    Manifest {
        schema: SCHEMA.into(),
        lane: "ao0".into(),
        class: VaultClass::Work,
        name: "kh".into(),
        paths: Paths {
            daily: "daily".into(),
            daily_name: "{date}.md".into(),
            inbox: "scratch".into(),
            weekly: Some("agentic/memory/weekly".into()),
            monthly: Some("agentic/memory/monthly".into()),
            updates: Some("agentic/memory/sessions".into()),
            search_roots: vec![
                "daily".into(),
                "agentic/memory".into(),
                "areas".into(),
                "projects".into(),
                "scratch".into(),
            ],
        },
        templates: Templates {
            daily: Some("templates/daily-note.md".into()),
        },
    }
}
