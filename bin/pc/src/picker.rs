use anyhow::Result;
use std::io::Write;
use std::process::{Command, Stdio};

use crate::error::PcError;
use crate::project::{Project, Status};

pub struct PickerOpts {
    pub prompt: String,
    pub header: String,
    pub preview_cmd: Option<String>,
}

/// Run fzf with the given items and options. Returns the selected line.
pub fn pick(items: &[String], opts: &PickerOpts) -> Result<String> {
    // Check fzf exists
    Command::new("fzf")
        .arg("--version")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|_| PcError::FzfNotFound)?;

    let input = items.join("\n");

    let mut cmd = Command::new("fzf");
    cmd.arg("--prompt").arg(&opts.prompt);
    cmd.arg("--header").arg(&opts.header);

    if let Some(ref preview) = opts.preview_cmd {
        cmd.arg("--preview").arg(preview);
        cmd.arg("--preview-window").arg("right:40%:wrap");
    }

    cmd.stdin(Stdio::piped());
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::inherit()); // fzf needs the terminal

    let mut child = cmd.spawn()?;

    if let Some(ref mut stdin) = child.stdin {
        stdin.write_all(input.as_bytes())?;
    }

    let output = child.wait_with_output()?;

    if !output.status.success() {
        return Err(PcError::PickerCancelled.into());
    }

    let selected = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if selected.is_empty() {
        return Err(PcError::PickerCancelled.into());
    }

    Ok(selected)
}

/// Format projects for the fzf picker.
pub fn format_projects(projects: &[Project]) -> Vec<String> {
    projects
        .iter()
        .map(|p| {
            let marker = match p.status {
                Status::Active => "●",
                Status::Idle => " ",
            };
            format!("{} {}", marker, p.name)
        })
        .collect()
}

/// Extract the project name from a picker selection line.
pub fn extract_project_name(selection: &str) -> String {
    selection
        .trim()
        .trim_start_matches('●')
        .trim()
        .to_string()
}

/// Fallback numbered list when fzf is not available.
pub fn pick_fallback(items: &[String], prompt: &str) -> Result<String> {
    eprintln!("{prompt}");
    for (i, item) in items.iter().enumerate() {
        eprintln!("  [{:>2}] {}", i + 1, item);
    }
    eprint!("  > ");
    std::io::stderr().flush()?;

    let mut input = String::new();
    std::io::stdin().read_line(&mut input)?;
    let idx: usize = input.trim().parse().unwrap_or(0);

    if idx == 0 || idx > items.len() {
        return Err(PcError::PickerCancelled.into());
    }

    Ok(items[idx - 1].clone())
}
