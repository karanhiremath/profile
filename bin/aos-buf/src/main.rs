mod apply;
mod catalog;
mod classify;
mod jobs;
mod rpc;
mod update;

use std::path::PathBuf;

use anyhow::Result;
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(
    name = "aos-buf",
    about = "AOS platform binary. Buffer catalog / get / apply. Self-update from GitHub. Never send-keys.",
    after_help = "Verbs:\n  \
        aos update [--dry-run] [--from-source] [--tag aos-vX]\n  \
        aos version\n  \
        aos buf catalog|list|get|apply|set|jobs|job\n  \
        aos apply <id> --file PATH"
)]
struct Cli {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// atop-vi.catalog.v1 JSON
    Catalog {
        #[arg(long)]
        no_disk: bool,
    },
    /// TSV catalog (harness live id pid path)
    List {
        #[arg(long)]
        json: bool,
        #[arg(long)]
        no_disk: bool,
    },
    /// Print live buffer text
    Get { id: String },
    /// JSON snapshot
    Snapshot { id: String },
    /// Queue write; aos.apply.v1 on stdout
    Apply {
        id: String,
        #[arg(long)]
        file: PathBuf,
        #[arg(long)]
        wait: bool,
    },
    /// Queue write; atop-vi.job.v1 on stdout
    Set {
        id: String,
        #[arg(long)]
        file: PathBuf,
        #[arg(long)]
        wait: bool,
    },
    Jobs,
    Job { id: String },
    Status { id: String },
    /// Install or replace ~/.local/bin/aos from a GitHub release (or --from-source)
    Update {
        #[arg(long)]
        dry_run: bool,
        #[arg(long)]
        from_source: bool,
        #[arg(long)]
        tag: Option<String>,
        #[arg(long)]
        dest: Option<PathBuf>,
    },
    /// Print the binary version
    Version,
    /// Pass-through so `aos buf catalog` matches the wrapper
    Buf {
        #[arg(trailing_var_arg = true, allow_hyphen_values = true)]
        rest: Vec<String>,
    },
    #[command(hide = true)]
    InternApply {
        #[arg(long)]
        job_dir: PathBuf,
        #[arg(long)]
        socket: String,
        #[arg(long)]
        path: String,
        #[arg(long)]
        buffer: i64,
        #[arg(long)]
        file: PathBuf,
        #[arg(long)]
        pid: i64,
        #[arg(long)]
        session: String,
    },
}

fn main() {
    if let Err(e) = run() {
        eprintln!("aos-buf: {e:#}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    dispatch(Cli::parse())
}

fn dispatch(cli: Cli) -> Result<()> {
    match cli.cmd {
        Cmd::Catalog { no_disk } => {
            let cat = catalog::build(no_disk);
            println!("{}", serde_json::to_string_pretty(&cat)?);
        }
        Cmd::List { json, no_disk } => {
            let cat = catalog::build(no_disk);
            if json {
                println!("{}", serde_json::to_string_pretty(&cat)?);
            } else {
                catalog::print_list(&cat);
            }
        }
        Cmd::Get { id } => {
            let t = apply::resolve(&id)?;
            print!("{}", apply::get_text(&t)?);
        }
        Cmd::Snapshot { id } => {
            let t = apply::resolve(&id)?;
            println!("{}", serde_json::to_string_pretty(&apply::snapshot(&t)?)?);
        }
        Cmd::Apply { id, file, wait } => {
            let file = abs(file)?;
            let t = apply::resolve(&id)?;
            let v = apply::queue_set(&t, &file, wait, true)?;
            println!("{}", serde_json::to_string_pretty(&v)?);
        }
        Cmd::Set { id, file, wait } => {
            let file = abs(file)?;
            let t = apply::resolve(&id)?;
            let v = apply::queue_set(&t, &file, wait, false)?;
            if wait {
                apply::print_wrote(&v);
            } else {
                println!("{}", serde_json::to_string_pretty(&v)?);
            }
        }
        Cmd::Jobs => {
            println!("{}", serde_json::to_string_pretty(&jobs::list_jobs()?)?);
        }
        Cmd::Job { id } | Cmd::Status { id } => {
            println!("{}", serde_json::to_string_pretty(&jobs::load_job(&id)?)?);
        }
        Cmd::Update {
            dry_run,
            from_source,
            tag,
            dest,
        } => {
            let rec = update::run(update::Opts {
                dry_run,
                from_source,
                tag,
                dest,
            })?;
            println!("{}", serde_json::to_string_pretty(&rec)?);
        }
        Cmd::Version => {
            println!("{}", update::version());
        }
        Cmd::Buf { rest } => {
            let mut argv = vec![env!("CARGO_PKG_NAME").to_string()];
            argv.extend(rest);
            let inner = Cli::try_parse_from(argv)?;
            return dispatch(inner);
        }
        Cmd::InternApply {
            job_dir,
            socket,
            path,
            buffer,
            file,
            pid,
            session,
        } => {
            let rec = apply::intern_apply(&job_dir, &socket, &path, buffer, &file, pid, &session)?;
            if rec.get("status").and_then(|v| v.as_str()) == Some("error") {
                std::process::exit(1);
            }
        }
    }
    Ok(())
}

fn abs(p: PathBuf) -> Result<PathBuf> {
    if p.is_absolute() {
        Ok(p)
    } else {
        Ok(std::env::current_dir()?.join(p))
    }
}
