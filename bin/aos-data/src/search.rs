use crate::error::AosError;
use crate::vault::Vault;
use serde::Serialize;
use std::fs;
use std::path::Path;
use std::process::Command;

#[derive(Serialize)]
pub struct Hit {
    pub path: String,
    pub line: usize,
    pub text: String,
}

const SKIP: &[&str] = &[
    ".git",
    ".obsidian",
    ".trash",
    "node_modules",
    "target",
    ".worktrees",
];

pub fn search(vault: &Vault, query: &str, limit: usize) -> Result<Vec<Hit>, AosError> {
    if let Some(hits) = rg(vault, query, limit) {
        return Ok(hits);
    }
    let q = query.to_lowercase();
    let mut hits = Vec::new();
    for rel in vault.manifest.search_roots() {
        let root = vault.join(&rel)?;
        if root.is_dir() {
            walk(&root, &vault.root, &q, limit, &mut hits)?;
        } else if root.is_file() {
            scan_file(&root, &vault.root, &q, limit, &mut hits)?;
        }
        if hits.len() >= limit {
            break;
        }
    }
    Ok(hits)
}

fn walk(
    dir: &Path,
    vault: &Path,
    q: &str,
    limit: usize,
    hits: &mut Vec<Hit>,
) -> Result<(), AosError> {
    let rd = fs::read_dir(dir).map_err(|e| AosError::msg(e.to_string()))?;
    for ent in rd {
        if hits.len() >= limit {
            return Ok(());
        }
        let ent = ent.map_err(|e| AosError::msg(e.to_string()))?;
        let path = ent.path();
        let name = ent.file_name();
        let name = name.to_string_lossy();
        if SKIP.iter().any(|s| name == *s) {
            continue;
        }
        if path.is_dir() {
            walk(&path, vault, q, limit, hits)?;
        } else if path.extension().and_then(|s| s.to_str()) == Some("md") {
            scan_file(&path, vault, q, limit, hits)?;
        }
    }
    Ok(())
}

fn scan_file(
    path: &Path,
    vault: &Path,
    q: &str,
    limit: usize,
    hits: &mut Vec<Hit>,
) -> Result<(), AosError> {
    let Ok(body) = fs::read_to_string(path) else {
        return Ok(());
    };
    let rel = path.strip_prefix(vault).unwrap_or(path);
    for (i, line) in body.lines().enumerate() {
        if hits.len() >= limit {
            break;
        }
        if line.to_lowercase().contains(q) {
            hits.push(Hit {
                path: rel.display().to_string(),
                line: i + 1,
                text: line.trim().chars().take(160).collect(),
            });
        }
    }
    Ok(())
}
