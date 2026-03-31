use std::env;
use std::path::PathBuf;

/// All configuration for pc, resolved from env vars with sensible defaults.
#[derive(Debug, Clone)]
pub struct Config {
    pub pi_bin: String,
    pub nvim_bin: String,
    pub src_dir: PathBuf,
    pub session_prefix: String,
    pub pi_split_pct: u8,
    pub zsh_split_pct: u8,
    pub nvim_open_cmd: String,
    pub db_top_cmd: String,
    pub saves_dir: PathBuf,
    pub vendor_hosts: Vec<String>,
}

impl Config {
    pub fn load() -> Self {
        let home = env::var("HOME").unwrap_or_else(|_| "/tmp".into());

        let src_dir = env::var("PC_SRC_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from(&home).join("src"));

        let saves_dir = env::var("PC_SAVES_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from(&home).join(".config/pc/sessions"));

        let vendor_hosts: Vec<String> = env::var("PC_VENDOR_HOSTS")
            .unwrap_or_default()
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();

        let pi_bin = env::var("PI_BIN").unwrap_or_else(|_| {
            // Try common locations
            for candidate in &["/opt/homebrew/bin/pi", "/usr/local/bin/pi"] {
                if std::path::Path::new(candidate).exists() {
                    return candidate.to_string();
                }
            }
            which("pi").unwrap_or_else(|| "pi".into())
        });

        let nvim_bin = env::var("NVIM_BIN").unwrap_or_else(|_| {
            let bob_nvim = PathBuf::from(&home).join(".local/share/bob/nvim-bin/nvim");
            if bob_nvim.exists() {
                return bob_nvim.to_string_lossy().into();
            }
            which("nvim").unwrap_or_else(|| "nvim".into())
        });

        let pi_split_pct = env::var("PC_SPLIT_PCT")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(35u8)
            .clamp(10, 80);

        let zsh_split_pct = env::var("PC_ZSH_SPLIT_PCT")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(25u8)
            .clamp(10, 60);

        // Open nvim with telescope-pc project picker on startup
        // Note: tmux passes commands through the shell, so avoid bare parentheses.
        let nvim_open_cmd = env::var("PC_NVIM_CMD")
            .unwrap_or_else(|_| "+lua require('kh.telescope-pc').pick_project()".to_string());

        let db_top_cmd = env::var("PC_DB_TOP").unwrap_or_else(|_| "btop".into());

        Self {
            pi_bin,
            nvim_bin,
            src_dir,
            session_prefix: "pi".into(),
            pi_split_pct,
            zsh_split_pct,
            nvim_open_cmd,
            db_top_cmd,
            saves_dir,
            vendor_hosts,
        }
    }

    /// Sanitize a project name for use in tmux targets.
    /// tmux reserves `:` (session:window) and `.` (window.pane) in target strings.
    pub fn sanitize_tmux_name(name: &str) -> String {
        name.replace('.', "-").replace(':', "-")
    }

    /// Full tmux session name for a project.
    pub fn session_name(&self, project: &str) -> String {
        format!("{}_{}", self.session_prefix, Self::sanitize_tmux_name(project))
    }

    /// Window name for the coding workspace.
    pub fn pc_window_name(project: &str) -> String {
        Self::sanitize_tmux_name(project)
    }

    /// Window name for the dashboard.
    pub fn db_window_name(project: &str) -> String {
        format!("{}-db", Self::sanitize_tmux_name(project))
    }

    /// Path to a project directory.
    pub fn project_dir(&self, project: &str) -> PathBuf {
        self.src_dir.join(project)
    }

    /// Pi session storage dir for a given project path.
    pub fn pi_session_dir(&self, project_dir: &std::path::Path) -> PathBuf {
        let encoded = project_dir
            .to_string_lossy()
            .replace('/', "--")
            .trim_start_matches('-')
            .to_string();
        let home = env::var("HOME").unwrap_or_else(|_| "/tmp".into());
        PathBuf::from(home)
            .join(".pi/agent/sessions")
            .join(encoded)
    }
}

/// Locate a binary on PATH.
fn which(name: &str) -> Option<String> {
    env::var("PATH")
        .unwrap_or_default()
        .split(':')
        .map(|dir| PathBuf::from(dir).join(name))
        .find(|p| p.exists())
        .map(|p| p.to_string_lossy().into_owned())
}
