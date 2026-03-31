use anyhow::Result;
use colored::Colorize;

use crate::config::Config;
use crate::dashboard;
use crate::error::PcError;
use crate::tmux::Tmux;

/// Launch or attach to a pc workspace.
///
/// **Inside tmux:** adds "pc" and "db" windows to the current session.
/// **Outside tmux:** creates a new session `pi_<project>` and attaches.
///
/// Window "<project>" (coding):        Window "<project>-db" (dashboard):
/// ┌──────────┬──────────┐             ┌────────────────────┐
/// │  NVIM    │          │             │       BTOP          │
/// │(telescope│   PI     │             ├──────┬──────┬───────┤
/// ├──────────┤          │             │ k9s  │slurm │dd-logs│
/// │  ZSH     │          │             └──────┴──────┴───────┘
/// └──────────┴──────────┘             (auto-detected panels)
///
/// Panes in coding window: 0=nvim 1=pi 2=zsh
pub fn launch(cfg: &Config, tmux: &Tmux, project: &str, pi_args: &[String]) -> Result<()> {
    let dir = cfg.project_dir(project);

    if !dir.exists() {
        return Err(PcError::ProjectNotFound(
            project.into(),
            cfg.src_dir.display().to_string(),
        )
        .into());
    }

    let dir_str = dir.to_string_lossy();

    if tmux.is_inside_tmux() {
        launch_in_session(cfg, tmux, project, &dir_str, pi_args)
    } else {
        launch_new_session(cfg, tmux, project, &dir_str, pi_args)
    }
}

/// Inside tmux: add windows to the current session, switch to the pc window.
fn launch_in_session(
    cfg: &Config,
    tmux: &Tmux,
    project: &str,
    dir: &str,
    pi_args: &[String],
) -> Result<()> {
    let pc_win = Config::pc_window_name(project);
    let db_win = Config::db_window_name(project);

    let current_sess = tmux
        .current_session()
        .ok_or(PcError::NotInSession)?;

    let pc_target = format!("{current_sess}:{pc_win}");

    // If the pc window already exists, just switch to it
    if tmux.has_window(&pc_target) {
        eprintln!(
            "{} to existing window {}",
            "Switching".cyan(),
            pc_win.bold()
        );
        tmux.select_window(&pc_target)?;
        return Ok(());
    }

    eprintln!(
        "{} workspace {} in session {}",
        "Creating".green(),
        project.bold(),
        current_sess.dimmed()
    );

    let pi_cmd = build_pi_cmd(cfg, pi_args);
    let nvim_cmd = format!("{} {}", cfg.nvim_bin, cfg.nvim_open_cmd);

    // ── Coding window ──────────────────────────────────
    // New window at position 0 (first)
    tmux.new_window_at(&current_sess, &pc_win, dir, &nvim_cmd, 0)?;

    let pc_target = format!("{current_sess}:{pc_win}");

    // Split pane 0 right → pane 1 (pi, full-height)
    tmux.split_right(&format!("{pc_target}.0"), dir, cfg.pi_split_pct, &pi_cmd)?;

    // Split pane 0 bottom → pane 2 (zsh)
    tmux.split_bottom(&format!("{pc_target}.0"), dir, cfg.zsh_split_pct, "zsh")?;

    // Focus nvim
    tmux.select_pane(&format!("{pc_target}.0"))?;

    // ── Dashboard window ───────────────────────────────
    dashboard::create_dashboard_in_session(cfg, tmux, &current_sess, &db_win, dir)?;

    // Switch to the coding window
    tmux.select_window(&pc_target)?;

    Ok(())
}

/// Outside tmux: create a new session and attach.
fn launch_new_session(
    cfg: &Config,
    tmux: &Tmux,
    project: &str,
    dir: &str,
    pi_args: &[String],
) -> Result<()> {
    let sess = cfg.session_name(project);
    let pc_win = Config::pc_window_name(project);
    let db_win = Config::db_window_name(project);

    // If session exists, just attach
    if tmux.has_session(&sess) {
        eprintln!(
            "{} to existing session {}",
            "Attaching".cyan(),
            project.bold()
        );
        return tmux.attach_session(&sess);
    }

    eprintln!(
        "{} session {} → {}",
        "Creating".green(),
        project.bold(),
        dir.dimmed()
    );

    let pi_cmd = build_pi_cmd(cfg, pi_args);
    let nvim_cmd = format!("{} {}", cfg.nvim_bin, cfg.nvim_open_cmd);

    // ── Coding window (first window in new session) ────
    tmux.create_session(&sess, dir, &nvim_cmd)?;
    tmux.rename_window(&format!("{sess}:0"), &pc_win)?;

    let pc_target = format!("{sess}:{pc_win}");

    // Split pane 0 right → pane 1 (pi, full-height)
    tmux.split_right(&format!("{pc_target}.0"), dir, cfg.pi_split_pct, &pi_cmd)?;

    // Split pane 0 bottom → pane 2 (zsh)
    tmux.split_bottom(&format!("{pc_target}.0"), dir, cfg.zsh_split_pct, "zsh")?;

    // Focus nvim
    tmux.select_pane(&format!("{pc_target}.0"))?;

    // ── Dashboard window ───────────────────────────────
    dashboard::create_dashboard_in_session(cfg, tmux, &sess, &db_win, dir)?;

    // Select the coding window
    tmux.select_window(&pc_target)?;

    // Attach
    tmux.attach_session(&sess)
}

fn build_pi_cmd(cfg: &Config, pi_args: &[String]) -> String {
    let mut cmd = cfg.pi_bin.clone();
    for arg in pi_args {
        cmd.push(' ');
        cmd.push_str(arg);
    }
    cmd
}
