mod config;
mod dashboard;
mod error;
mod launch;
mod picker;
mod project;
mod session;
mod tmux;
mod vendor;

use anyhow::Result;
use clap::{Parser, Subcommand};
use colored::Colorize;

use config::Config;
use error::PcError;
use tmux::Tmux;

#[derive(Parser)]
#[command(
    name = "pc",
    about = "pi-code: tmux + nvim + pi session manager",
    version,
    after_help = "Examples:\n  \
        pc                          Interactive project picker\n  \
        pc bifrost                  Launch/attach bifrost session\n  \
        pc bifrost -- -c            Launch with pi --continue\n  \
        pc save                     Save current session\n  \
        pc load bifrost             Restore saved session\n  \
        pc vendor                   Commit, push, vendor to hosts"
)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,

    /// Project name to launch (when not using a subcommand)
    #[arg(value_name = "PROJECT")]
    project: Option<String>,

    /// Arguments passed through to pi (after --)
    #[arg(last = true)]
    pi_args: Vec<String>,
}

#[derive(Subcommand)]
enum Commands {
    /// Save current session layout
    Save {
        /// Session name (defaults to current project)
        name: Option<String>,
    },

    /// Load a saved session layout
    Load {
        /// Session name (fzf picker if omitted)
        name: Option<String>,
    },

    /// List active pi sessions
    Status,

    /// Kill a pi session (interactive picker)
    Kill {
        /// Session name (fzf picker if omitted)
        name: Option<String>,
    },

    /// Machine-readable project list (for telescope/scripts)
    List {
        /// Output as JSON instead of TSV
        #[arg(long)]
        json: bool,
    },

    /// Commit, push, and vendor to remote hosts
    Vendor {
        /// Commit message
        #[arg(short, long)]
        message: Option<String>,

        /// Comma-separated host list (overrides PC_VENDOR_HOSTS)
        #[arg(long)]
        hosts: Option<String>,

        /// Skip commit/push, just pull on hosts
        #[arg(long)]
        pull_only: bool,
    },
}

fn main() {
    if let Err(e) = run() {
        // Don't print "picker cancelled" — that's just the user pressing Esc
        if e.downcast_ref::<PcError>()
            .is_some_and(|pe| matches!(pe, PcError::PickerCancelled))
        {
            std::process::exit(0);
        }
        eprintln!("{} {e}", "error:".red().bold());
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let cli = Cli::parse();
    let cfg = Config::load();
    let tmux = Tmux::new(&cfg)?;

    match cli.command {
        Some(Commands::Status) => cmd_status(&cfg, &tmux),
        Some(Commands::Kill { name }) => cmd_kill(&cfg, &tmux, name.as_deref()),
        Some(Commands::List { json }) => cmd_list(&cfg, &tmux, json),
        Some(Commands::Save { name }) => cmd_save(&cfg, &tmux, name.as_deref()),
        Some(Commands::Load { name }) => cmd_load(&cfg, &tmux, name.as_deref()),
        Some(Commands::Vendor {
            message,
            hosts,
            pull_only,
        }) => cmd_vendor(&cfg, message.as_deref(), hosts.as_deref(), pull_only),
        None => {
            if let Some(ref project) = cli.project {
                launch::launch(&cfg, &tmux, project, &cli.pi_args)
            } else {
                cmd_pick(&cfg, &tmux, &cli.pi_args)
            }
        }
    }
}

// ── Status ─────────────────────────────────────────────

fn cmd_status(cfg: &Config, tmux: &Tmux) -> Result<()> {
    let active = tmux.active_sessions();
    if active.is_empty() {
        eprintln!("{}", "No active pi sessions.".dimmed());
        return Ok(());
    }

    eprintln!("{}", "Active pi sessions:".bold());
    for proj in &active {
        let sess = cfg.session_name(proj);
        let panes = tmux.list_panes(&sess).unwrap_or_default();
        let dir = cfg.project_dir(proj);
        eprintln!(
            "  {} {}  {}  {}",
            "●".green(),
            proj.bold(),
            format!("({}p)", panes.len()).dimmed(),
            dir.display().to_string().dimmed(),
        );
    }
    Ok(())
}

// ── Kill ───────────────────────────────────────────────

fn cmd_kill(cfg: &Config, tmux: &Tmux, name: Option<&str>) -> Result<()> {
    let target = match name {
        Some(n) => n.to_string(),
        None => {
            let active = tmux.active_sessions();
            if active.is_empty() {
                return Err(PcError::NoActiveSessions.into());
            }
            picker::pick(
                &active,
                &picker::PickerOpts {
                    prompt: "Kill session › ".into(),
                    header: "Select a pi session to kill".into(),
                    preview_cmd: None,
                },
            )?
        }
    };

    let sess = cfg.session_name(&target);
    tmux.kill_session(&sess)?;
    eprintln!("{} session {}", "Killed".red(), target.bold());
    Ok(())
}

// ── List ───────────────────────────────────────────────

fn cmd_list(cfg: &Config, tmux: &Tmux, json: bool) -> Result<()> {
    let projects = project::discover(cfg, tmux);

    if json {
        #[derive(serde::Serialize)]
        struct Entry {
            status: String,
            name: String,
            path: String,
        }
        let entries: Vec<Entry> = projects
            .iter()
            .map(|p| Entry {
                status: p.status.to_string(),
                name: p.name.clone(),
                path: p.path.display().to_string(),
            })
            .collect();
        println!("{}", serde_json::to_string_pretty(&entries)?);
    } else {
        for p in &projects {
            println!("{}\t{}\t{}", p.status, p.name, p.path.display());
        }
    }
    Ok(())
}

// ── Save ───────────────────────────────────────────────

fn cmd_save(cfg: &Config, tmux: &Tmux, name: Option<&str>) -> Result<()> {
    let saved = session::save(cfg, tmux, name)?;
    let save_path = cfg.saves_dir.join(format!("{}.json", saved.project));

    eprintln!(
        "{} session {} → {}",
        "Saved".green(),
        saved.project.bold(),
        save_path.display().to_string().dimmed(),
    );

    if let Some(ref pi) = saved.pi_session {
        let basename = std::path::Path::new(pi)
            .file_name()
            .unwrap_or_default()
            .to_string_lossy();
        eprintln!("  {} pi session: {}", "↳".dimmed(), basename.dimmed());
    }
    Ok(())
}

// ── Load ───────────────────────────────────────────────

fn cmd_load(cfg: &Config, tmux: &Tmux, name: Option<&str>) -> Result<()> {
    let target = match name {
        Some(n) => n.to_string(),
        None => {
            let saves = session::list_saved(cfg);
            if saves.is_empty() {
                return Err(
                    PcError::NoSavedSessions(cfg.saves_dir.display().to_string()).into()
                );
            }
            picker::pick(
                &saves,
                &picker::PickerOpts {
                    prompt: "Load session › ".into(),
                    header: "Saved pc sessions".into(),
                    preview_cmd: Some(format!(
                        "cat {}/{{}}.json 2>/dev/null | python3 -m json.tool 2>/dev/null",
                        cfg.saves_dir.display()
                    )),
                },
            )?
        }
    };

    let saved = session::load(cfg, &target)?;

    // Validate before launching
    if let Err(e) = saved.validate() {
        eprintln!("{} {e}", "warning:".yellow().bold());
    }

    eprintln!(
        "{} session {} → {}",
        "Loading".cyan(),
        saved.project.bold(),
        saved.dir.dimmed(),
    );

    // Build pi args from saved session
    let mut pi_args = Vec::new();
    if let Some(ref pi) = saved.pi_session {
        if !pi.is_empty() && std::path::Path::new(pi).exists() {
            pi_args.push("--session".to_string());
            pi_args.push(pi.clone());
            let basename = std::path::Path::new(pi)
                .file_name()
                .unwrap_or_default()
                .to_string_lossy();
            eprintln!("  {} resuming pi: {}", "↳".dimmed(), basename.dimmed());
        }
    }

    launch::launch(cfg, tmux, &saved.project, &pi_args)
}

// ── Pick (default) ─────────────────────────────────────

fn cmd_pick(cfg: &Config, tmux: &Tmux, pi_args: &[String]) -> Result<()> {
    let projects = project::discover(cfg, tmux);
    if projects.is_empty() {
        eprintln!(
            "{} No projects found in {}",
            "error:".red().bold(),
            cfg.src_dir.display()
        );
        return Ok(());
    }

    let items = picker::format_projects(&projects);

    let selection = match picker::pick(
        &items,
        &picker::PickerOpts {
            prompt: "pi › ".into(),
            header: "Pick a project (● = active session)".into(),
            preview_cmd: Some(format!(
                "ls -1 --color=always {}/{{2}} 2>/dev/null || ls -1 {}/{{2}} 2>/dev/null",
                cfg.src_dir.display(),
                cfg.src_dir.display(),
            )),
        },
    ) {
        Ok(s) => s,
        Err(e) if e.downcast_ref::<PcError>().is_some_and(|pe| matches!(pe, PcError::FzfNotFound)) => {
            // Fallback to numbered list
            return match picker::pick_fallback(&items, "Pick a project:") {
                Ok(s) => {
                    let name = picker::extract_project_name(&s);
                    launch::launch(cfg, tmux, &name, pi_args)
                }
                Err(_) => Ok(()),
            };
        }
        Err(e) => return Err(e),
    };

    let name = picker::extract_project_name(&selection);
    launch::launch(cfg, tmux, &name, pi_args)
}

// ── Vendor ─────────────────────────────────────────────

fn cmd_vendor(
    cfg: &Config,
    message: Option<&str>,
    hosts_override: Option<&str>,
    pull_only: bool,
) -> Result<()> {
    if !pull_only {
        let msg = message.unwrap_or("pc: update profile");

        // git add + commit + push
        eprintln!("{} {}...", "Committing".green(), msg.dimmed());

        let status = std::process::Command::new("git")
            .args(["add", "-A"])
            .status()?;
        if !status.success() {
            anyhow::bail!("git add failed");
        }

        // Commit (allow "nothing to commit" to pass through)
        let output = std::process::Command::new("git")
            .args(["commit", "-m", msg])
            .output()?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        if !output.status.success() && !stdout.contains("nothing to commit") {
            let stderr = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!("git commit failed: {stderr}");
        }

        eprintln!("{}", "Pushing...".green());
        let status = std::process::Command::new("git")
            .args(["push"])
            .status()?;
        if !status.success() {
            anyhow::bail!("git push failed");
        }
    }

    // Determine hosts
    let hosts: Vec<String> = if let Some(h) = hosts_override {
        h.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect()
    } else {
        cfg.vendor_hosts.clone()
    };

    if hosts.is_empty() {
        eprintln!(
            "\n{} No vendor hosts configured.",
            "Pushed.".green().bold()
        );
        eprintln!(
            "  Set {} or use {}",
            "PC_VENDOR_HOSTS=\"mini,cxis-dev\"".dimmed(),
            "--hosts".dimmed(),
        );
        return Ok(());
    }

    let repo = vendor::current_repo_name().unwrap_or_else(|| "profile".into());
    let results = vendor::vendor_to_hosts(&hosts, &repo, 5);

    let ok_count = results.iter().filter(|(_, r)| r.is_ok()).count();
    let total = results.len();

    eprintln!(
        "\n{} {ok_count}/{total} hosts updated.",
        if ok_count == total {
            "Done.".green().bold()
        } else {
            "Done.".yellow().bold()
        }
    );

    Ok(())
}
