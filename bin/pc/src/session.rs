use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

use crate::config::Config;
use crate::error::PcError;
use crate::tmux::Tmux;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaneInfo {
    pub index: usize,
    pub dir: String,
    pub cmd: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SavedSession {
    pub project: String,
    pub dir: String,
    pub layout: String,
    pub pane_count: usize,
    pub pi_session: Option<String>,
    pub panes: Vec<PaneInfo>,
    pub saved_at: DateTime<Utc>,
}

impl SavedSession {
    /// Validate that the session data is sane.
    pub fn validate(&self) -> Result<()> {
        if self.project.is_empty() {
            return Err(PcError::SessionCorrupted("empty project name".into()).into());
        }
        if !Path::new(&self.dir).exists() {
            return Err(PcError::DirNotFound(self.dir.clone()).into());
        }
        if let Some(ref pi) = self.pi_session {
            if !pi.is_empty() && !Path::new(pi).exists() {
                // Warn but don't fail — pi session may have been cleaned up
                eprintln!(
                    "  \x1b[2mNote: pi session file no longer exists: {}\x1b[0m",
                    pi
                );
            }
        }
        Ok(())
    }
}

/// Save the current session to disk.
pub fn save(cfg: &Config, tmux: &Tmux, name: Option<&str>) -> Result<SavedSession> {
    // Determine which session to save
    let project = match name {
        Some(n) => n.to_string(),
        None => tmux
            .current_project()
            .ok_or(PcError::NotInSession)?,
    };

    let sess = cfg.session_name(&project);
    if !tmux.has_session(&sess) {
        return Err(PcError::NoActiveSessions.into());
    }

    let dir = cfg.project_dir(&project);
    let layout = tmux.window_layout(&sess).unwrap_or_default();
    let panes_raw = tmux.list_panes(&sess)?;
    let pane_count = panes_raw.len();

    let panes: Vec<PaneInfo> = panes_raw
        .into_iter()
        .map(|(idx, dir, cmd)| PaneInfo {
            index: idx,
            dir,
            cmd,
        })
        .collect();

    // Find the latest pi session file
    let pi_session_dir = cfg.pi_session_dir(&dir);
    let pi_session = find_latest_session_file(&pi_session_dir);

    let saved = SavedSession {
        project,
        dir: dir.to_string_lossy().into_owned(),
        layout,
        pane_count,
        pi_session,
        panes,
        saved_at: Utc::now(),
    };

    // Atomic write: temp file → rename
    let saves_dir = &cfg.saves_dir;
    fs::create_dir_all(saves_dir)
        .with_context(|| format!("creating saves dir: {}", saves_dir.display()))?;

    let save_path = saves_dir.join(format!("{}.json", saved.project));
    let tmp_path = saves_dir.join(format!(".{}.json.tmp", saved.project));

    let json = serde_json::to_string_pretty(&saved)?;
    fs::write(&tmp_path, &json)
        .with_context(|| format!("writing {}", tmp_path.display()))?;
    fs::rename(&tmp_path, &save_path)
        .with_context(|| format!("renaming to {}", save_path.display()))?;

    Ok(saved)
}

/// Load a saved session from disk.
pub fn load(cfg: &Config, name: &str) -> Result<SavedSession> {
    let path = cfg.saves_dir.join(format!("{name}.json"));
    if !path.exists() {
        return Err(PcError::SaveNotFound(name.into()).into());
    }

    let data = fs::read_to_string(&path)
        .with_context(|| format!("reading {}", path.display()))?;

    let session: SavedSession = serde_json::from_str(&data)
        .with_context(|| PcError::SessionCorrupted(path.display().to_string()))?;

    Ok(session)
}

/// List all saved session names.
pub fn list_saved(cfg: &Config) -> Vec<String> {
    let dir = &cfg.saves_dir;
    match fs::read_dir(dir) {
        Ok(entries) => entries
            .filter_map(|e| e.ok())
            .filter_map(|e| {
                let name = e.file_name().to_string_lossy().into_owned();
                name.strip_suffix(".json").map(|s| s.to_string())
            })
            .collect(),
        Err(_) => vec![],
    }
}

/// Find the most recent .jsonl file in a directory.
fn find_latest_session_file(dir: &PathBuf) -> Option<String> {
    let mut entries: Vec<_> = fs::read_dir(dir)
        .ok()?
        .filter_map(|e| e.ok())
        .filter(|e| {
            e.path()
                .extension()
                .is_some_and(|ext| ext == "jsonl")
        })
        .collect();

    entries.sort_by_key(|e| {
        e.metadata()
            .and_then(|m| m.modified())
            .unwrap_or(std::time::SystemTime::UNIX_EPOCH)
    });

    entries
        .last()
        .map(|e| e.path().to_string_lossy().into_owned())
}
