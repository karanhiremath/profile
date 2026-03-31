use anyhow::Result;
use colored::Colorize;

use crate::config::Config;
use crate::dashboard;
use crate::error::PcError;
use crate::tmux::Tmux;

/// Launch a pc workspace for a project.
///
/// **Inside tmux:** adds coding + dashboard windows to current session.
/// **Outside tmux:** creates a new session and attaches.
///
/// Coding window "<project>":          Dashboard "<project>-db":
/// ┌──────────┬──────────┐             ┌────────────────────┐
/// │  NVIM    │          │             │       BTOP          │
/// │(telescope│   PI     │             ├──────┬──────┬───────┤
/// ├──────────┤          │             │ k9s  │slurm │dd-logs│
/// │  ZSH     │          │             └──────┴──────┴───────┘
/// └──────────┴──────────┘
///
/// Pane 0: nvim, Pane 1: pi, Pane 2: zsh
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

/// Build the coding window layout: 3 panes, send commands, apply layout.
fn build_coding_window(
    cfg: &Config,
    tmux: &Tmux,
    target: &str, // session:window
    dir: &str,
    pi_args: &[String],
) -> Result<()> {
    // Create 2 more panes (window already has pane 0)
    tmux.split_pane(&format!("{target}.0"), dir, "-h")?; // pane 1: right
    tmux.split_pane(&format!("{target}.0"), dir, "-v")?; // pane 2: below pane 0

    // Apply layout: nvim (top-left), pi (right full), zsh (bottom-left)
    tmux.apply_layout(target, "main-vertical")?;

    // Now pane indices are stable. Send commands.
    // Pane 0: nvim with telescope
    let nvim_cmd = format!(
        "{} '+lua require(\"kh.telescope-pc\").pick_project()'",
        cfg.nvim_bin
    );
    tmux.send_keys(&format!("{target}.0"), &nvim_cmd)?;

    // Pane 1: pi
    let mut pi_cmd = cfg.pi_bin.clone();
    for arg in pi_args {
        pi_cmd.push(' ');
        pi_cmd.push_str(arg);
    }
    tmux.send_keys(&format!("{target}.1"), &pi_cmd)?;

    // Pane 2: zsh (already running, just clear)
    tmux.send_keys(&format!("{target}.2"), "clear")?;

    // Focus nvim pane
    tmux.select_pane(&format!("{target}.0"))?;

    Ok(())
}

fn launch_in_session(
    cfg: &Config,
    tmux: &Tmux,
    project: &str,
    dir: &str,
    pi_args: &[String],
) -> Result<()> {
    let pc_win = Config::pc_window_name(project);
    let db_win = Config::db_window_name(project);
    let sess = tmux.current_session().ok_or(PcError::NotInSession)?;
    let pc_target = format!("{sess}:{pc_win}");

    if tmux.has_window(&sess, &pc_win) {
        eprintln!("{} to window {}", "Switching".cyan(), pc_win.bold());
        tmux.select_window(&pc_target)?;
        return Ok(());
    }

    eprintln!(
        "{} workspace {} → {}",
        "Creating".green(),
        project.bold(),
        dir.dimmed()
    );

    // Create coding window (plain shell), then build layout
    tmux.new_window(&sess, &pc_win, dir, "zsh")?;
    build_coding_window(cfg, tmux, &pc_target, dir, pi_args)?;

    // Dashboard
    dashboard::create_dashboard_in_session(cfg, tmux, &sess, &db_win, dir)?;

    // Switch to coding window
    tmux.select_window(&pc_target)?;
    Ok(())
}

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

    if tmux.has_session(&sess) {
        eprintln!("{} to session {}", "Attaching".cyan(), project.bold());
        return tmux.attach_session(&sess);
    }

    eprintln!(
        "{} session {} → {}",
        "Creating".green(),
        project.bold(),
        dir.dimmed()
    );

    // Create session with a plain shell, rename window, build layout
    tmux.create_session(&sess, dir, "zsh")?;
    tmux.rename_window(&format!("{sess}:0"), &pc_win)?;

    let pc_target = format!("{sess}:{pc_win}");
    build_coding_window(cfg, tmux, &pc_target, dir, pi_args)?;

    // Dashboard
    dashboard::create_dashboard_in_session(cfg, tmux, &sess, &db_win, dir)?;

    // Select coding window and attach
    tmux.select_window(&pc_target)?;
    tmux.attach_session(&sess)
}
