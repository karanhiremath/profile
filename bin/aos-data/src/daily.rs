use crate::error::AosError;
use crate::vault::Vault;
use chrono::NaiveDate;
use std::fs;
use std::io::Write;

pub fn ensure(vault: &Vault, date: NaiveDate) -> Result<std::path::PathBuf, AosError> {
    let path = vault.daily_path(date)?;
    if path.exists() {
        return Ok(path);
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| AosError::msg(e.to_string()))?;
    }
    let body = if let Some(rel) = &vault.manifest.templates.daily {
        let tpl = vault.join(rel)?;
        if tpl.is_file() {
            fs::read_to_string(&tpl).map_err(|e| AosError::msg(e.to_string()))?
        } else {
            default_daily(&vault.manifest.class.as_str(), date)
        }
    } else {
        default_daily(vault.manifest.class.as_str(), date)
    };
    fs::write(&path, body).map_err(|e| AosError::msg(e.to_string()))?;
    Ok(path)
}

pub fn append(vault: &Vault, date: NaiveDate, text: &str) -> Result<std::path::PathBuf, AosError> {
    let path = ensure(vault, date)?;
    let mut f = fs::OpenOptions::new()
        .append(true)
        .open(&path)
        .map_err(|e| AosError::msg(e.to_string()))?;
    let ts = chrono::Local::now().format("%H:%M");
    writeln!(f, "\n- {ts} {text}").map_err(|e| AosError::msg(e.to_string()))?;
    Ok(path)
}

fn default_daily(class: &str, date: NaiveDate) -> String {
    match class {
        "personal" => format!(
            "---\ntags:\n  - notes/daily\n---\n# {d}\n\n# Planning\n\n## personal #personal\n- [ ] \n\n---\n## work #work\n- [ ] \n\n---\n# Notes\n\n## personal #personal\n\n## work #work\n",
            d = date.format("%Y-%m-%d")
        ),
        _ => format!(
            "---\ntype: session\nproject: fleet\nstatus: active\ncreated: {d}\nupdated: {d}\ntags: [daily, session]\n---\n# {d}\n\n## Focus\n\n## Work Log\n\n## Decisions\n\n## Blockers\n\n## Tomorrow\n",
            d = date.format("%Y-%m-%d")
        ),
    }
}
