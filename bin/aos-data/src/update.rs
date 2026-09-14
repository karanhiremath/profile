use crate::error::AosError;
use crate::vault::Vault;
use chrono::Utc;
use std::fs;

/// Ledger-contract agent-update event. One file per write.
pub fn add(vault: &Vault, text: &str, surface: &str) -> Result<std::path::PathBuf, AosError> {
    let rel = vault
        .manifest
        .paths
        .updates
        .as_deref()
        .ok_or_else(|| AosError::msg("manifest has no paths.updates"))?;
    let day = Utc::now().format("%Y-%m-%d").to_string();
    let dir = vault.join(&format!("{rel}/{day}"))?;
    fs::create_dir_all(&dir).map_err(|e| AosError::msg(e.to_string()))?;
    let stamp = Utc::now().format("%Y%m%dT%H%M%SZ");
    let surf = sanitize(surface);
    let path = crate::vault::confine(&vault.root, &dir.join(format!("{stamp}--{surf}--cli.md")))?;
    let scope = vault.manifest.class.as_str();
    let ts = chrono::Local::now().to_rfc3339();
    let body = format!(
        "---\nkind: agent-update\nscope: {scope}\ntimestamp: {ts}\nagent: aos-data\nsurface: {surf}\nsession_id: \"\"\nproject: \"\"\nstatus: active\nprivacy: {scope}\nsource_ref: \"\"\nnext_action: \"\"\n---\n# Agent update — {ts} — aos-data\n\n## Since last update\n- {text}\n\n## Current\n- captured via `aos-data capture --to update`\n\n## Blockers / decisions needed\n- None\n\n## Next\n- \n"
    );
    fs::write(&path, body).map_err(|e| AosError::msg(e.to_string()))?;
    Ok(path)
}

fn sanitize(s: &str) -> String {
    s.chars()
        .map(|c| if c.is_ascii_alphanumeric() || c == '-' { c } else { '-' })
        .take(24)
        .collect()
}
