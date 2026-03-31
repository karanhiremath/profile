use std::fmt;
use std::path::PathBuf;

use crate::config::Config;
use crate::tmux::Tmux;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Status {
    Active,
    Idle,
}

impl fmt::Display for Status {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Status::Active => write!(f, "active"),
            Status::Idle => write!(f, "idle"),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Project {
    pub name: String,
    pub path: PathBuf,
    pub status: Status,
}

/// Discover all projects under src_dir, tagged with session status.
pub fn discover(cfg: &Config, tmux: &Tmux) -> Vec<Project> {
    let active: Vec<String> = tmux.active_sessions();

    let mut projects: Vec<Project> = match std::fs::read_dir(&cfg.src_dir) {
        Ok(entries) => entries
            .filter_map(|e| e.ok())
            .filter(|e| e.path().is_dir())
            .filter(|e| {
                // Skip dotfiles
                !e.file_name().to_string_lossy().starts_with('.')
            })
            .map(|e| {
                let name = e.file_name().to_string_lossy().into_owned();
                let status = if active.contains(&name) {
                    Status::Active
                } else {
                    Status::Idle
                };
                Project {
                    name,
                    path: e.path(),
                    status,
                }
            })
            .collect(),
        Err(_) => vec![],
    };

    // Active sessions first, then alphabetical
    projects.sort_by(|a, b| {
        match (&a.status, &b.status) {
            (Status::Active, Status::Idle) => std::cmp::Ordering::Less,
            (Status::Idle, Status::Active) => std::cmp::Ordering::Greater,
            _ => a.name.cmp(&b.name),
        }
    });

    projects
}
