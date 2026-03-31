use anyhow::Result;
use std::process::Command;

use crate::config::Config;
use crate::tmux::Tmux;

/// A dashboard panel: name, command to run, and a probe to check availability.
#[derive(Debug, Clone)]
#[allow(dead_code)]
struct Panel {
    name: &'static str, // used in debug output and future TUI labels
    cmd: String,
    weight: u8,
}

/// Detect available tools and build the dashboard layout.
///
/// Layout:
/// ┌────────────────────────────────┐
/// │           BTOP                 │   ← always (pane 0, top full-width)
/// ├────────┬────────┬──────────────┤
/// │ panel1 │ panel2 │   panel3     │   ← auto-detected bottom row
/// └────────┴────────┴──────────────┘
/// Create the dashboard as a named window in an existing session.
pub fn create_dashboard_in_session(
    cfg: &Config,
    tmux: &Tmux,
    session: &str,
    window_name: &str,
    dir: &str,
) -> Result<()> {
    tmux.new_window(session, window_name, dir, &cfg.db_top_cmd)?;
    let target = format!("{session}:{window_name}");
    build_bottom_panels(cfg, tmux, &target, dir)
}

/// Build the auto-detected bottom row of dashboard panels.
fn build_bottom_panels(cfg: &Config, tmux: &Tmux, target: &str, dir: &str) -> Result<()> {

    // ── Detect available panels for bottom row ─────────
    let mut panels = detect_panels(cfg);

    // Always have at least a shell
    if panels.is_empty() {
        panels.push(Panel {
            name: "shell",
            cmd: "zsh".into(),
            weight: 0,
        });
    }

    // Sort by weight (highest first = leftmost)
    panels.sort_by(|a, b| b.weight.cmp(&a.weight));

    // Cap at 3 panels in the bottom row
    panels.truncate(3);

    // ── Build bottom row ───────────────────────────────
    // First panel: split bottom from btop (pane 0)
    let first = &panels[0];
    tmux.split_bottom(&format!("{target}.0"), dir, 45, &first.cmd)?;

    // Remaining panels: split right from the previous
    for (i, panel) in panels.iter().skip(1).enumerate() {
        let pane_idx = i + 1;
        let remaining = panels.len() - i - 1;
        let pct = match remaining {
            0 => 50,
            _ => 100 / (remaining as u8 + 1),
        };
        let pct = pct.max(30).min(60);
        tmux.split_right(&format!("{target}.{pane_idx}"), dir, pct, &panel.cmd)?;
    }

    Ok(())
}

/// Probe the environment and return available dashboard panels.
fn detect_panels(cfg: &Config) -> Vec<Panel> {
    let mut panels = Vec::new();

    // ── Kubernetes: k9s if contexts are available ──────
    if has_binary("k9s") && has_kube_contexts() {
        panels.push(Panel {
            name: "k9s",
            cmd: "k9s".into(),
            weight: 90,
        });
    } else if has_binary("kubectl") && has_kube_contexts() {
        // Fallback: watch pods
        panels.push(Panel {
            name: "k8s",
            cmd: "watch -n5 kubectl get pods -A --sort-by=.metadata.creationTimestamp | tail -40"
                .into(),
            weight: 90,
        });
    }

    // ── Slurm: squeue/sinfo if available ───────────────
    if has_binary("squeue") {
        panels.push(Panel {
            name: "slurm",
            cmd: "watch -n10 'echo \"=== QUEUE ===\"; squeue -u $USER --format=\"%.8i %.9P %.30j %.8T %.10M %.6D %R\" 2>/dev/null; echo; echo \"=== NODES ===\"; sinfo --format=\"%10P %5a %10l %6D %8t %N\" 2>/dev/null'".into(),
            weight: 85,
        });
    }

    // ── Datadog: log tail when API key is present ──────
    if has_dd_env() {
        // Live tail recent logs via datadog-ci
        panels.push(Panel {
            name: "dd-logs",
            cmd: concat!(
                "zsh -c '",
                "echo \"Datadog Log Tail\"; echo \"─────────────────\"; ",
                "if command -v npx &>/dev/null; then ",
                "  npx -y @datadog/datadog-ci logs tail --follow 2>/dev/null || ",
                "  (echo \"Falling back to API curl...\"; ",
                "   watch -n15 \"curl -s -X POST \\\"https://api.datadoghq.com/api/v2/logs/events/search\\\" ",
                "     -H \\\"DD-API-KEY: $DD_API_KEY\\\" ",
                "     -H \\\"DD-APPLICATION-KEY: $DD_APP_KEY\\\" ",
                "     -H \\\"Content-Type: application/json\\\" ",
                "     -d \\'\\{\\\"filter\\\":\\{\\\"query\\\":\\\"*\\\",\\\"from\\\":\\\"now-15m\\\",\\\"to\\\":\\\"now\\\"\\},\\\"sort\\\":\\\"timestamp\\\",\\\"page\\\":\\{\\\"limit\\\":20\\}\\}\\' ",
                "     2>/dev/null | python3 -m json.tool 2>/dev/null | head -80\"); ",
                "else echo \"npx not found\"; exec zsh; fi'",
            ).into(),
            weight: 70,
        });
    }

    // ── OTEL / logs viewer ─────────────────────────────
    let otel_script = format!(
        "{}/agentic/scripts/view-agent-logs.sh",
        cfg.src_dir.join("karan.hiremath").display()
    );
    if std::path::Path::new(&otel_script).exists() {
        panels.push(Panel {
            name: "otel",
            cmd: format!("zsh -c '{otel_script} 2>/dev/null || echo \"OTEL not running — start with start-otel.sh\"; exec zsh'"),
            weight: 60,
        });
    }

    // ── Docker/Podman: container overview ──────────────
    if has_binary("docker") && is_docker_running() {
        panels.push(Panel {
            name: "docker",
            cmd: "watch -n5 'docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\"'"
                .into(),
            weight: 50,
        });
    } else if has_binary("podman") {
        panels.push(Panel {
            name: "podman",
            cmd: "watch -n5 'podman ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\"'"
                .into(),
            weight: 50,
        });
    }

    // ── GPU: nvidia-smi if available ───────────────────
    if has_binary("nvidia-smi") {
        panels.push(Panel {
            name: "gpu",
            cmd: "watch -n2 nvidia-smi".into(),
            weight: 95,
        });
    }

    // ── Fallback: always offer a shell ─────────────────
    panels.push(Panel {
        name: "shell",
        cmd: "zsh".into(),
        weight: 10,
    });

    panels
}

fn has_binary(name: &str) -> bool {
    Command::new("which")
        .arg(name)
        .output()
        .is_ok_and(|o| o.status.success())
}

fn has_kube_contexts() -> bool {
    Command::new("kubectl")
        .args(["config", "get-contexts", "-o", "name"])
        .output()
        .is_ok_and(|o| {
            o.status.success()
                && !String::from_utf8_lossy(&o.stdout).trim().is_empty()
        })
}

fn has_dd_env() -> bool {
    std::env::var("DD_API_KEY")
        .is_ok_and(|v| !v.is_empty())
}

fn is_docker_running() -> bool {
    Command::new("docker")
        .arg("info")
        .output()
        .is_ok_and(|o| o.status.success())
}
