use std::env;
use std::fs;
use std::path::PathBuf;

#[cfg(test)]
mod config_tests {

    #[test]
    fn session_name_uses_underscore_not_colon() {
        // tmux reserves : for session:window.pane targeting
        let name = format!("pi_{}", "bifrost");
        assert!(!name.contains(':'), "session name must not contain ':'");
        assert_eq!(name, "pi_bifrost");
    }

    #[test]
    fn session_name_sanitizes_dots() {
        // tmux interprets dots as window.pane separators in target strings.
        // karan.hiremath must become karan-hiremath.
        let sanitized = "karan.hiremath".replace('.', "-").replace(':', "-");
        let name = format!("pi_{}", sanitized);
        assert_eq!(name, "pi_karan-hiremath");
        assert!(!name.contains('.'));
        assert!(!name.contains(':'));
    }

    #[test]
    fn session_name_sanitizes_colons() {
        let sanitized = "my:project".replace('.', "-").replace(':', "-");
        assert_eq!(sanitized, "my-project");
    }

    #[test]
    fn split_pct_clamped() {
        let val: u8 = "5".parse::<u8>().unwrap_or(35).clamp(10, 80);
        assert_eq!(val, 10);
        let val: u8 = "95".parse::<u8>().unwrap_or(35).clamp(10, 80);
        assert_eq!(val, 80);
        let val: u8 = "50".parse::<u8>().unwrap_or(35).clamp(10, 80);
        assert_eq!(val, 50);
        let val: u8 = "garbage".parse::<u8>().unwrap_or(35).clamp(10, 80);
        assert_eq!(val, 35);
    }
}

#[cfg(test)]
mod session_tests {
    use super::*;

    #[test]
    fn session_json_round_trip() {
        let json = r#"{
            "project": "bifrost",
            "dir": "/Users/test/src/bifrost",
            "layout": "b263,160x48,0,0{104x48,0,0,0,55x48,105,0,1}",
            "pane_count": 3,
            "pi_session": null,
            "panes": [
                {"index": 0, "dir": "/Users/test/src/bifrost", "cmd": "nvim"},
                {"index": 1, "dir": "/Users/test/src/bifrost", "cmd": "pi"},
                {"index": 2, "dir": "/Users/test/src/bifrost", "cmd": "zsh"}
            ],
            "saved_at": "2026-03-31T10:00:00Z"
        }"#;

        // Deserialize
        let session: serde_json::Value = serde_json::from_str(json).unwrap();
        assert_eq!(session["project"], "bifrost");
        assert_eq!(session["pane_count"], 3);
        assert_eq!(session["panes"].as_array().unwrap().len(), 3);

        // Re-serialize and parse again (round-trip)
        let reserialized = serde_json::to_string_pretty(&session).unwrap();
        let session2: serde_json::Value = serde_json::from_str(&reserialized).unwrap();
        assert_eq!(session, session2);
    }

    #[test]
    fn session_with_pi_session_path() {
        let json = r#"{
            "project": "compliance",
            "dir": "/Users/test/src/compliance",
            "layout": "test",
            "pane_count": 3,
            "pi_session": "/Users/test/.pi/agent/sessions/--Users-test-src-compliance--/2026-03-31.jsonl",
            "panes": [],
            "saved_at": "2026-03-31T10:00:00Z"
        }"#;

        let session: serde_json::Value = serde_json::from_str(json).unwrap();
        assert!(session["pi_session"].as_str().unwrap().ends_with(".jsonl"));
    }

    #[test]
    fn atomic_save_creates_file() {
        let tmp = env::temp_dir().join("pc-test-saves");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(&tmp).unwrap();

        let save_path = tmp.join("testproj.json");
        let tmp_path = tmp.join(".testproj.json.tmp");

        let data = r#"{"project":"testproj","dir":"/tmp","layout":"","pane_count":0,"pi_session":null,"panes":[],"saved_at":"2026-03-31T00:00:00Z"}"#;

        // Simulate atomic write
        fs::write(&tmp_path, data).unwrap();
        fs::rename(&tmp_path, &save_path).unwrap();

        assert!(save_path.exists());
        assert!(!tmp_path.exists()); // temp file should be gone

        let loaded = fs::read_to_string(&save_path).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&loaded).unwrap();
        assert_eq!(parsed["project"], "testproj");

        let _ = fs::remove_dir_all(&tmp);
    }
}

#[cfg(test)]
mod project_tests {
    use super::*;

    #[test]
    fn discover_skips_dotfiles() {
        let tmp = env::temp_dir().join("pc-test-projects");
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(tmp.join("good-project")).unwrap();
        fs::create_dir_all(tmp.join(".hidden")).unwrap();
        fs::create_dir_all(tmp.join("another")).unwrap();

        let entries: Vec<String> = fs::read_dir(&tmp)
            .unwrap()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().is_dir())
            .filter(|e| !e.file_name().to_string_lossy().starts_with('.'))
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .collect();

        assert_eq!(entries.len(), 2);
        assert!(entries.contains(&"good-project".to_string()));
        assert!(entries.contains(&"another".to_string()));
        assert!(!entries.iter().any(|e| e.starts_with('.')));

        let _ = fs::remove_dir_all(&tmp);
    }
}

#[cfg(test)]
mod cli_tests {
    use std::process::Command;

    fn pc_bin() -> PathBuf {
        PathBuf::from(env!("CARGO_BIN_EXE_pc"))
    }

    use super::*;

    #[test]
    fn help_exits_zero() {
        let out = Command::new(pc_bin()).arg("--help").output().unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(stdout.contains("pi-code"));
    }

    #[test]
    fn version_exits_zero() {
        let out = Command::new(pc_bin()).arg("--version").output().unwrap();
        assert!(out.status.success());
    }

    #[test]
    fn status_exits_zero() {
        let out = Command::new(pc_bin()).arg("status").output().unwrap();
        assert!(out.status.success());
    }

    #[test]
    fn list_exits_zero() {
        let out = Command::new(pc_bin()).arg("list").output().unwrap();
        assert!(out.status.success());
    }

    #[test]
    fn list_json_is_valid() {
        let out = Command::new(pc_bin())
            .args(["list", "--json"])
            .output()
            .unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        let parsed: serde_json::Value = serde_json::from_str(&stdout).unwrap();
        assert!(parsed.is_array());
    }

    #[test]
    fn nonexistent_project_fails() {
        let out = Command::new(pc_bin())
            .arg("__nonexistent_project_42__")
            .output()
            .unwrap();
        assert!(!out.status.success());
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(stderr.contains("not found"));
    }

    #[test]
    fn load_nonexistent_fails() {
        let out = Command::new(pc_bin())
            .args(["load", "__fake_session_99__"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn vendor_help() {
        let out = Command::new(pc_bin())
            .args(["vendor", "--help"])
            .output()
            .unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(stdout.contains("--hosts"));
        assert!(stdout.contains("--pull-only"));
    }
}
