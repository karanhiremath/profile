//! Seatbelt deny wrap for the Cos-voice dest apply host. No :8787 takeover.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const PROFILE_RELPATH: &str = "sandbox/cos-voice-dest.sb";
pub const SANDBOX_EXEC: &str = "/usr/bin/sandbox-exec";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SeatbeltPlan {
    pub ok: bool,
    pub sandbox_exec: String,
    pub profile_name: String,
    pub profile_relpath: String,
    pub deny: Vec<String>,
    pub allow: Vec<String>,
    pub wrap: String,
    pub replace_loopback: bool,
    pub note: String,
}

pub fn deny_paths(home: &Path) -> Vec<String> {
    [
        ".ssh",
        ".aws",
        ".kube",
        ".gnupg",
        ".hermes/.env",
        ".codex/auth.json",
        ".local/share/hermes-agents/chief-of-staff-work",
        ".local/share/hermes-agents/work-notes-steward",
    ]
    .into_iter()
    .map(|rel| home.join(rel).display().to_string())
    .collect()
}

pub fn allow_paths(home: &Path) -> Vec<String> {
    [
        "src/profile/bin/cos-voice-wasm",
        "src/profile/bin/ghostty-voice",
        "src/notes/03_tech/agentic-os/fleet",
        ".pi/agent/buffers/INDEX.jsonl",
        ".pi/agent/otel/agent-events.jsonl",
    ]
    .into_iter()
    .map(|rel| home.join(rel).display().to_string())
    .collect()
}

pub fn render_profile(template: &str, home: &Path) -> String {
    template.replace("__HOME__", &home.display().to_string())
}

pub fn wrap_command(profile: &Path, argv: &[&str]) -> String {
    let mut parts = vec![
        SANDBOX_EXEC.to_string(),
        "-f".into(),
        profile.display().to_string(),
    ];
    parts.extend(argv.iter().map(|s| s.to_string()));
    parts.join(" ")
}

pub fn plan_seatbelt(home: Option<&Path>, host_bin: Option<&Path>) -> SeatbeltPlan {
    let home = home
        .map(Path::to_path_buf)
        .or_else(|| std::env::var_os("HOME").map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("/"));
    let bin = host_bin
        .map(Path::to_path_buf)
        .unwrap_or_else(|| {
            home.join("src/profile/bin/cos-voice-wasm/target/debug/cos-voice-host")
        });
    let profile = home.join("src/profile/bin/cos-voice-wasm").join(PROFILE_RELPATH);
    SeatbeltPlan {
        ok: true,
        sandbox_exec: SANDBOX_EXEC.into(),
        profile_name: "cos-voice-dest".into(),
        profile_relpath: PROFILE_RELPATH.into(),
        deny: deny_paths(&home),
        allow: allow_paths(&home),
        wrap: wrap_command(
            &profile,
            &[bin.to_str().unwrap_or("cos-voice-host"), "serve", "--bind", "127.0.0.1:8788"],
        ),
        replace_loopback: false,
        note: "Deny wrap for dest apply on :8788. Do not bounce :8787. Work ledger path is not invented.".into(),
    }
}
