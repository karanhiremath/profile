use crate::error::AosError;
use serde::Serialize;
use std::path::Path;
use std::process::Command;

#[derive(Debug, Clone, Default, Serialize)]
pub struct GitSnap {
    pub branch: Option<String>,
    pub short: String,
    pub dirty: bool,
}

pub fn snap(root: &Path) -> Result<GitSnap, AosError> {
    let out = Command::new("git")
        .args(["-C", &root.display().to_string(), "status", "--short", "--branch"])
        .output()
        .map_err(|e| AosError::msg(format!("git: {e}")))?;
    if !out.status.success() {
        return Ok(GitSnap::default());
    }
    let text = String::from_utf8_lossy(&out.stdout);
    let mut lines = text.lines();
    let head = lines.next().unwrap_or_default();
    let branch = head
        .strip_prefix("## ")
        .map(|s| s.split(['.', ' ']).next().unwrap_or(s).to_string());
    let rest: Vec<&str> = lines.filter(|l| !l.is_empty()).collect();
    Ok(GitSnap {
        branch,
        short: rest.join("\n"),
        dirty: !rest.is_empty(),
    })
}
