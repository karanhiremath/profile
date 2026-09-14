use anyhow::Result;
use aos_data::vault::{Argv0, StatusJson, Vault};
use aos_data::{daily, inbox, search, tui, SCHEMA};
use chrono::Local;
use clap::{Parser, Subcommand};
use std::io::{self, Write};
use std::path::PathBuf;
use std::process::ExitCode;

#[derive(Parser)]
#[command(
    name = "aos-data",
    about = "ao0 vault toolkit — portable CLI/TUI for notes and kh Obsidian ledgers",
    after_help = "argv0 aliases: notes (personal) · kh (work) · aos-data (--vault)\n\
        Examples:\n  notes\n  notes daily --open\n  kh capture --to daily 'shipped x'\n  aos-data --vault ~/src/notes status --json"
)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
    /// Vault root (overrides argv0 defaults)
    #[arg(long, global = true)]
    vault: Option<PathBuf>,
    /// Machine stdout (json)
    #[arg(long, global = true)]
    json: bool,
}

#[derive(Subcommand)]
enum Commands {
    /// Vault + daily + inbox snapshot
    Status,
    /// Ensure/print today's (or --date) daily
    Daily {
        #[arg(long)]
        date: Option<String>,
        #[arg(long)]
        open: bool,
    },
    /// List inbox files
    Inbox,
    /// Append-only capture
    Capture {
        text: String,
        #[arg(long, default_value = "inbox")]
        to: String,
    },
    /// Case-insensitive markdown search
    Search {
        query: String,
        #[arg(long, default_value_t = 50)]
        limit: usize,
    },
    /// Interactive TUI
    Tui,
    /// Check vault + editor
    Doctor,
}

fn main() -> ExitCode {
    if let Err(e) = run() {
        eprintln!("error: {e}");
        return ExitCode::from(1);
    }
    ExitCode::SUCCESS
}

fn run() -> Result<()> {
    let argv0 = std::env::args()
        .next()
        .map(|s| Argv0::parse(&s))
        .unwrap_or(Argv0::AosData);
    let cli = Cli::parse();
    let vault = Vault::resolve(argv0, cli.vault.as_deref())?;

    match cli.command {
        None | Some(Commands::Tui) => {
            if cli.json {
                print_status(&vault, true)?;
            } else {
                tui::run(&vault)?;
            }
        }
        Some(Commands::Status) => print_status(&vault, cli.json)?,
        Some(Commands::Daily { date, open }) => {
            let d = parse_date(date.as_deref())?;
            let path = daily::ensure(&vault, d)?;
            if cli.json {
                println!("{}", serde_json::json!({"path": path}));
            } else {
                println!("{}", path.display());
            }
            if open {
                aos_data::open::editor(&path)?;
            }
        }
        Some(Commands::Inbox) => {
            let items = inbox::list(&vault)?;
            if cli.json {
                serde_json::to_writer(io::stdout(), &items)?;
                println!();
            } else {
                for i in items {
                    println!("{}", i.name);
                }
            }
        }
        Some(Commands::Capture { text, to }) => {
            let path = match to.as_str() {
                "daily" => daily::append(&vault, Local::now().date_naive(), &text)?,
                "inbox" => inbox::add(&vault, &text)?,
                other => anyhow::bail!("--to must be inbox|daily (got {other})"),
            };
            if cli.json {
                println!("{}", serde_json::json!({"path": path}));
            } else {
                println!("{}", path.display());
            }
        }
        Some(Commands::Search { query, limit }) => {
            let hits = search::search(&vault, &query, limit)?;
            if cli.json {
                serde_json::to_writer(io::stdout(), &hits)?;
                println!();
            } else {
                for h in hits {
                    println!("{}:{}:{}", h.path, h.line, h.text);
                }
            }
        }
        Some(Commands::Doctor) => {
            let editor_ok = std::env::var("VISUAL")
                .or_else(|_| std::env::var("EDITOR"))
                .ok();
            let payload = serde_json::json!({
                "vault": vault.root,
                "class": vault.manifest.class.as_str(),
                "daily_dir": vault.join(&vault.manifest.paths.daily)?.exists(),
                "inbox_dir": vault.inbox_dir()?.exists(),
                "manifest": vault.manifest_path,
                "editor": editor_ok,
            });
            if cli.json {
                println!("{payload}");
            } else {
                println!("{payload}");
            }
        }
    }
    Ok(())
}

fn print_status(vault: &Vault, json: bool) -> Result<()> {
    let date = Local::now().date_naive();
    let daily = vault.daily_path(date)?;
    let inbox_items = inbox::list(vault)?;
    let st = StatusJson {
        schema: SCHEMA,
        lane: &vault.manifest.lane,
        class: vault.manifest.class.as_str(),
        name: &vault.manifest.name,
        argv0: &vault.argv0,
        vault: vault.root.display().to_string(),
        daily: daily.display().to_string(),
        daily_exists: daily.exists(),
        inbox: vault.inbox_dir()?.display().to_string(),
        inbox_count: inbox_items.len(),
        manifest: vault.manifest_path.as_ref().map(|p| p.display().to_string()),
    };
    if json {
        serde_json::to_writer(io::stdout(), &st)?;
        writeln!(io::stdout())?;
    } else {
        writeln!(
            io::stdout(),
            "{}\t{}\t{}\tdaily={}\tinbox={}",
            st.class,
            st.name,
            st.vault,
            if st.daily_exists { "yes" } else { "no" },
            st.inbox_count
        )?;
    }
    Ok(())
}

fn parse_date(raw: Option<&str>) -> Result<chrono::NaiveDate> {
    match raw {
        None => Ok(Local::now().date_naive()),
        Some(s) => Ok(chrono::NaiveDate::parse_from_str(s, "%Y-%m-%d")?),
    }
}
