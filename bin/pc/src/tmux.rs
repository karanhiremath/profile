use anyhow::{Context, Result, bail};
use std::process::{Command, Output, Stdio};

use crate::config::Config;
use crate::error::PcError;

/// Type-safe tmux command builder.
pub struct Tmux<'a> {
    cfg: &'a Config,
}

impl<'a> Tmux<'a> {
    pub fn new(cfg: &'a Config) -> Result<Self> {
        // Verify tmux is available
        Command::new("tmux")
            .arg("-V")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|_| PcError::TmuxNotFound)?;
        Ok(Self { cfg })
    }

    /// Check if we're currently inside a tmux session.
    pub fn is_inside_tmux(&self) -> bool {
        std::env::var("TMUX").is_ok()
    }

    /// Get the current tmux session name (if inside tmux).
    pub fn current_session(&self) -> Option<String> {
        let output = Command::new("tmux")
            .args(["display-message", "-p", "#{session_name}"])
            .output()
            .ok()?;
        let name = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if name.is_empty() { None } else { Some(name) }
    }

    /// Get the current project name if inside a pc session.
    pub fn current_project(&self) -> Option<String> {
        let sess = self.current_session()?;
        sess.strip_prefix(&format!("{}_", self.cfg.session_prefix))
            .map(|s| s.to_string())
    }

    /// Check if a session exists.
    pub fn has_session(&self, session: &str) -> bool {
        Command::new("tmux")
            .args(["has-session", "-t", session])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|s| s.success())
    }

    /// List all active pc session names (without prefix).
    pub fn active_sessions(&self) -> Vec<String> {
        let output = match Command::new("tmux")
            .args(["list-sessions", "-F", "#{session_name}"])
            .output()
        {
            Ok(o) => o,
            Err(_) => return vec![],
        };

        String::from_utf8_lossy(&output.stdout)
            .lines()
            .filter_map(|line| {
                line.strip_prefix(&format!("{}_", self.cfg.session_prefix))
                    .map(|s| s.to_string())
            })
            .collect()
    }

    /// List panes for a session: Vec<(index, dir, command)>
    pub fn list_panes(&self, session: &str) -> Result<Vec<(usize, String, String)>> {
        let output = self.run(&[
            "list-panes",
            "-t",
            session,
            "-F",
            "#{pane_index}|#{pane_current_path}|#{pane_current_command}",
        ])?;

        let text = String::from_utf8_lossy(&output.stdout);
        let mut panes = Vec::new();
        for line in text.lines() {
            let parts: Vec<&str> = line.splitn(3, '|').collect();
            if parts.len() == 3 {
                let idx = parts[0].parse().unwrap_or(0);
                panes.push((idx, parts[1].to_string(), parts[2].to_string()));
            }
        }
        Ok(panes)
    }

    /// Get window layout string for a session.
    pub fn window_layout(&self, session: &str) -> Result<String> {
        let output = self.run(&[
            "list-windows",
            "-t",
            session,
            "-F",
            "#{window_layout}",
        ])?;
        Ok(String::from_utf8_lossy(&output.stdout)
            .lines()
            .next()
            .unwrap_or("")
            .to_string())
    }

    /// Create a new detached session with nvim in the main pane.
    pub fn create_session(&self, session: &str, dir: &str, nvim_cmd: &str) -> Result<()> {
        self.run(&["new-session", "-d", "-s", session, "-c", dir, nvim_cmd])?;
        Ok(())
    }

    /// Split a pane horizontally (right) and run a command.
    pub fn split_right(&self, target: &str, dir: &str, pct: u8, cmd: &str) -> Result<()> {
        self.run(&[
            "split-window",
            "-t",
            target,
            "-h",
            "-l",
            &format!("{pct}%"),
            "-c",
            dir,
            cmd,
        ])?;
        Ok(())
    }

    /// Split a pane vertically (bottom) and run a command.
    pub fn split_bottom(&self, target: &str, dir: &str, pct: u8, cmd: &str) -> Result<()> {
        self.run(&[
            "split-window",
            "-t",
            target,
            "-v",
            "-l",
            &format!("{pct}%"),
            "-c",
            dir,
            cmd,
        ])?;
        Ok(())
    }

    /// Select a pane by target.
    pub fn select_pane(&self, target: &str) -> Result<()> {
        self.run(&["select-pane", "-t", target])?;
        Ok(())
    }

    /// Switch client to a session (when already inside tmux).
    #[allow(dead_code)]
    pub fn switch_client(&self, session: &str) -> Result<()> {
        self.run(&["switch-client", "-t", session])?;
        Ok(())
    }

    /// Attach to a session (when not inside tmux). Replaces current process.
    pub fn attach_session(&self, session: &str) -> Result<()> {
        use std::os::unix::process::CommandExt;
        let err = Command::new("tmux")
            .args(["attach-session", "-t", session])
            .exec();
        bail!("exec tmux attach failed: {err}");
    }

    /// Create a new window in an existing session.
    pub fn new_window(&self, session: &str, name: &str, dir: &str, cmd: &str) -> Result<()> {
        self.run(&["new-window", "-t", session, "-n", name, "-c", dir, cmd])?;
        Ok(())
    }

    /// Create a new window at a specific index (pushes existing windows down).
    pub fn new_window_at(
        &self,
        session: &str,
        name: &str,
        dir: &str,
        cmd: &str,
        index: usize,
    ) -> Result<()> {
        let target = format!("{session}:{index}");
        // -b = insert before, -d = don't switch to it yet
        self.run(&[
            "new-window", "-b", "-d", "-t", &target, "-n", name, "-c", dir, cmd,
        ])?;
        Ok(())
    }

    /// Check if a window exists.
    pub fn has_window(&self, target: &str) -> bool {
        Command::new("tmux")
            .args(["select-window", "-t", target])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .is_ok_and(|s| s.success())
    }

    /// Select a window by target.
    pub fn select_window(&self, target: &str) -> Result<()> {
        self.run(&["select-window", "-t", target])?;
        Ok(())
    }

    /// Rename a window.
    pub fn rename_window(&self, target: &str, name: &str) -> Result<()> {
        self.run(&["rename-window", "-t", target, name])?;
        Ok(())
    }

    /// Kill a session.
    pub fn kill_session(&self, session: &str) -> Result<()> {
        self.run(&["kill-session", "-t", session])?;
        Ok(())
    }

    /// Capture pane content (used by telescope preview).
    #[allow(dead_code)]
    pub fn capture_pane(&self, target: &str, lines: usize) -> Result<String> {
        let output = self.run(&["capture-pane", "-t", target, "-p"])?;
        let text = String::from_utf8_lossy(&output.stdout);
        let captured: Vec<&str> = text.lines().collect();
        let start = captured.len().saturating_sub(lines);
        Ok(captured[start..].join("\n"))
    }

    /// Run a raw tmux command.
    fn run(&self, args: &[&str]) -> Result<Output> {
        let output = Command::new("tmux")
            .args(args)
            .output()
            .with_context(|| format!("tmux {}", args.join(" ")))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            // Some commands (has-session) legitimately fail — don't treat as fatal
            if !stderr.trim().is_empty() {
                return Err(PcError::TmuxCommand(stderr.trim().to_string()).into());
            }
        }
        Ok(output)
    }
}
