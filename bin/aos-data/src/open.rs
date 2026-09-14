use crate::error::AosError;
use std::env;
use std::path::Path;
use std::process::Command;

/// Open a path in $VISUAL / $EDITOR / nvim. Never tmux send-keys.
pub fn editor(path: &Path) -> Result<(), AosError> {
    let bin = env::var("VISUAL")
        .or_else(|_| env::var("EDITOR"))
        .unwrap_or_else(|_| {
            let home = env::var("HOME").unwrap_or_default();
            let bob = Path::new(&home).join(".local/share/bob/nvim-bin/nvim");
            if bob.exists() {
                bob.to_string_lossy().into()
            } else {
                "nvim".into()
            }
        });
    let status = Command::new(&bin)
        .arg(path)
        .status()
        .map_err(|e| AosError::msg(format!("editor {bin}: {e}")))?;
    if !status.success() {
        return Err(AosError::msg(format!(
            "editor {bin} exited {}",
            status.code().unwrap_or(1)
        )));
    }
    Ok(())
}
