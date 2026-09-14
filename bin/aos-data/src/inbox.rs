use crate::error::AosError;
use crate::vault::Vault;
use serde::Serialize;
use std::fs;

#[derive(Serialize)]
pub struct InboxItem {
    pub name: String,
    pub path: String,
}

pub fn list(vault: &Vault) -> Result<Vec<InboxItem>, AosError> {
    let dir = vault.inbox_dir()?;
    if !dir.is_dir() {
        return Ok(Vec::new());
    }
    let mut items = Vec::new();
    let mut rd = fs::read_dir(&dir).map_err(|e| AosError::msg(e.to_string()))?;
    while let Some(ent) = rd.next() {
        let ent = ent.map_err(|e| AosError::msg(e.to_string()))?;
        let path = ent.path();
        if path.extension().and_then(|s| s.to_str()) != Some("md")
            && path.extension().and_then(|s| s.to_str()) != Some("yaml")
        {
            continue;
        }
        items.push(InboxItem {
            name: ent.file_name().to_string_lossy().into(),
            path: path.display().to_string(),
        });
    }
    items.sort_by(|a, b| b.name.cmp(&a.name));
    Ok(items)
}

pub fn add(vault: &Vault, text: &str) -> Result<std::path::PathBuf, AosError> {
    let dir = vault.inbox_dir()?;
    fs::create_dir_all(&dir).map_err(|e| AosError::msg(e.to_string()))?;
    let stamp = chrono::Utc::now().format("%Y%m%dT%H%M%SZ");
    let path = crate::vault::confine(&vault.root, &dir.join(format!("{stamp}.md")))?;
    let scope = vault.manifest.class.as_str();
    let body = format!(
        "---\nkind: capture\nscope: {scope}\ncreated: {}\n---\n# Capture\n\n{text}\n",
        chrono::Local::now().to_rfc3339()
    );
    fs::write(&path, body).map_err(|e| AosError::msg(e.to_string()))?;
    Ok(path)
}
