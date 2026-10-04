use cos_voice_wasm::apply::plan;
use cos_voice_wasm::report_from_sources;
use cos_voice_wasm::supervise::snapshot;
use serde_json::{json, Value};
use std::env;
use std::fs;
use std::path::PathBuf;
use std::process;

fn main() {
    let mut args = env::args().skip(1);
    let cmd = args.next().unwrap_or_else(|| "help".into());
    let rest: Vec<String> = args.collect();
    let result = match cmd.as_str() {
        "route" => cmd_route(&rest),
        "s2s" => cmd_s2s(&rest),
        "profile" => cmd_profile(&rest),
        "chips" => cmd_chips(&rest),
        "supervise" => cmd_supervise(&rest),
        "help" | "-h" | "--help" => {
            print_help();
            return;
        }
        other => {
            eprintln!("unknown command {other}");
            print_help();
            process::exit(2);
        }
    };
    match result {
        Ok(value) => {
            println!("{}", serde_json::to_string_pretty(&value).unwrap());
        }
        Err(err) => {
            eprintln!("{err}");
            process::exit(1);
        }
    }
}

fn print_help() {
    eprintln!(
        "cos-voice-apply — dest route, Cartesia s2s plan, chips, supervisor stub\n\n\
         USAGE:\n  cos-voice-apply route --dest DEST --text TEXT [--mode steer|buffer|brief]\n  \
         cos-voice-apply s2s --dest DEST [--yaml PATH]\n  \
         cos-voice-apply profile --dest DEST [--yaml PATH]\n  \
         cos-voice-apply chips [--atop PATH] [--otel PATH] [--jobs-dir PATH] [--no-8787]\n  \
         cos-voice-apply supervise [--once]\n"
    );
}

fn cmd_s2s(args: &[String]) -> Result<Value, String> {
    let dest = flag(args, "--dest").unwrap_or_else(|| "cos".into());
    let yaml = flag(args, "--yaml")
        .map(|path| fs::read_to_string(&path).map_err(|e| e.to_string()))
        .transpose()?;
    let plan = cos_voice_wasm::plan_s2s(&dest, yaml.as_deref());
    serde_json::to_value(plan).map_err(|e| e.to_string())
}

fn cmd_profile(args: &[String]) -> Result<Value, String> {
    let dest = flag(args, "--dest").unwrap_or_else(|| "cos".into());
    let yaml = flag(args, "--yaml")
        .map(|path| fs::read_to_string(&path).map_err(|e| e.to_string()))
        .transpose()?;
    let bound = if let Some(text) = yaml.as_deref() {
        cos_voice_wasm::parse_profile_yaml(text)
    } else {
        cos_voice_wasm::bind_dest(&dest)
    };
    serde_json::to_value(bound).map_err(|e| e.to_string())
}

fn cmd_route(args: &[String]) -> Result<Value, String> {
    let dest = flag(args, "--dest").unwrap_or_else(|| "cos".into());
    let text = flag(args, "--text").unwrap_or_default();
    let mode = flag(args, "--mode");
    let routed = cos_voice_wasm::route_with_mode(&dest, &text, mode.as_deref());
    let apply = plan(&routed);
    Ok(json!({ "route": routed, "apply": apply }))
}

fn cmd_chips(args: &[String]) -> Result<Value, String> {
    let atop = if let Some(path) = flag(args, "--atop") {
        serde_json::from_str(&fs::read_to_string(&path).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?
    } else {
        cos_voice_wasm::chips::load_atop_dump()?
    };
    let otel = flag(args, "--otel")
        .map(PathBuf::from)
        .unwrap_or_else(cos_voice_wasm::default_otel_path);
    let jobs = flag(args, "--jobs-dir")
        .map(PathBuf::from)
        .unwrap_or_else(cos_voice_wasm::default_jobs_dir);
    let probe = !args.iter().any(|a| a == "--no-8787");
    let report = report_from_sources(&atop, &otel, &jobs, probe);
    serde_json::to_value(report).map_err(|e| e.to_string())
}

fn cmd_supervise(args: &[String]) -> Result<Value, String> {
    let _once = args.iter().any(|a| a == "--once");
    let chips = cmd_chips(&[])?;
    let alert_n = chips
        .get("alerts")
        .and_then(|a| a.as_array())
        .map(|a| a.len())
        .unwrap_or(0);
    let snap = snapshot("native-stub", "polled", "idle");
    Ok(json!({
        "supervisor": snap,
        "chip_alerts": alert_n,
        "once": true
    }))
}

fn flag(args: &[String], name: &str) -> Option<String> {
    args.windows(2)
        .find(|w| w[0] == name)
        .map(|w| w[1].clone())
}
