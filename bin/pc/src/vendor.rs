use anyhow::Result;
use colored::Colorize;
use std::process::Command;
/// Vendor (git pull) a repo on remote hosts via SSH.
/// Returns (host, success) pairs.
pub fn vendor_to_hosts(
    hosts: &[String],
    repo_name: &str,
    timeout_secs: u64,
) -> Vec<(String, Result<()>)> {
    let remote_dir = format!("~/src/{repo_name}");
    let pull_cmd = format!(
        "cd {remote_dir} 2>/dev/null && git pull --ff-only 2>&1"
    );

    eprintln!("\n{}", "Vendoring to hosts...".bold());

    hosts
        .iter()
        .map(|host| {
            eprint!("  {:<20} ", host);
            let result = ssh_pull(host, &pull_cmd, timeout_secs);
            match &result {
                Ok(()) => eprintln!("{}", "✓".green()),
                Err(e) => eprintln!("{} ({})", "✗".red(), e),
            }
            (host.clone(), result)
        })
        .collect()
}

fn ssh_pull(host: &str, cmd: &str, timeout_secs: u64) -> Result<()> {
    let output = Command::new("ssh")
        .args([
            "-o", &format!("ConnectTimeout={timeout_secs}"),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            host,
            cmd,
        ])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let stdout = String::from_utf8_lossy(&output.stdout);
        let msg = if !stderr.trim().is_empty() {
            stderr.trim().to_string()
        } else if !stdout.trim().is_empty() {
            stdout.trim().to_string()
        } else {
            "unknown error".into()
        };
        anyhow::bail!("{msg}");
    }

    // Check for "Already up to date" or actual changes
    let stdout = String::from_utf8_lossy(&output.stdout);
    let first_line = stdout.lines().next().unwrap_or("");
    if !first_line.is_empty()
        && !first_line.contains("Already up to date")
        && !first_line.contains("Updating")
    {
        // Might be an error disguised as stdout
        eprint!(" {}", first_line.dimmed());
    }

    Ok(())
}

/// Get the current git repo name from the working directory.
pub fn current_repo_name() -> Option<String> {
    let output = Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .output()
        .ok()?;

    if !output.status.success() {
        return None;
    }

    let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
    path.rsplit('/').next().map(|s| s.to_string())
}
