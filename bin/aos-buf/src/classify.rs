use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Harness {
    AtopVi,
    Herm,
    Pi,
    Claude,
    Codex,
    Cursor,
    Opencode,
    Workbench,
    Tmp,
    Other,
}

impl Harness {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::AtopVi => "atop-vi",
            Self::Herm => "herm",
            Self::Pi => "pi",
            Self::Claude => "claude",
            Self::Codex => "codex",
            Self::Cursor => "cursor",
            Self::Opencode => "opencode",
            Self::Workbench => "workbench",
            Self::Tmp => "tmp",
            Self::Other => "other",
        }
    }

    pub fn order(self) -> u8 {
        match self {
            Self::AtopVi => 0,
            Self::Herm => 1,
            Self::Pi => 2,
            Self::Claude => 3,
            Self::Codex => 4,
            Self::Cursor => 5,
            Self::Opencode => 6,
            Self::Workbench => 7,
            Self::Tmp => 8,
            Self::Other => 99,
        }
    }
}

pub fn classify(path: &str) -> Harness {
    let p = path.replace('\\', "/").to_ascii_lowercase();
    let name = Path::new(&p)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    if name.starts_with("herm-") || p.contains("/herm-") {
        return Harness::Herm;
    }
    if p.contains("pi-editor") {
        return Harness::Pi;
    }
    if name.starts_with("claude-prompt") || p.contains("/.claude/prompt") {
        return Harness::Claude;
    }
    if (p.contains("/documents/codex/") || p.contains("/.codex/")) && name.contains("prompt") {
        return Harness::Codex;
    }
    if p.contains("nvim-prompt-workbench") || p.contains("nvim-workbench") {
        return Harness::Workbench;
    }
    if name.starts_with("atop-vi") || p.contains("/atop-vi.") {
        return Harness::AtopVi;
    }
    if name.contains("cursor-prompt") || (p.contains("/.cursor/") && name.contains("prompt")) {
        return Harness::Cursor;
    }
    if p.contains("opencode") && name.contains("prompt") {
        return Harness::Opencode;
    }
    if name == "prompt.md" {
        return Harness::Pi;
    }
    if name.ends_with(".md") && (p.contains("/tmp/") || p.contains("/var/folders/") || p.contains("/t/"))
    {
        return Harness::Tmp;
    }
    Harness::Other
}

pub fn keep(path: &str, harness: Harness) -> bool {
    let name = Path::new(path)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("");
    if name.contains('|') || name.ends_with(".json") || name.starts_with("snapshot-req") {
        return false;
    }
    if matches!(
        harness,
        Harness::Herm
            | Harness::Pi
            | Harness::Claude
            | Harness::Codex
            | Harness::Cursor
            | Harness::Opencode
            | Harness::Workbench
            | Harness::AtopVi
            | Harness::Tmp
    ) {
        return true;
    }
    let lower = name.to_ascii_lowercase();
    lower == "prompt.md" || lower == "checkpoint.md" || lower.starts_with("prompt")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classifies_known_harnesses() {
        assert_eq!(classify("/tmp/pi-editor-abc/prompt.md"), Harness::Pi);
        assert_eq!(classify("/tmp/herm-123.md"), Harness::Herm);
        assert_eq!(classify("/tmp/atop-vi.karan.md"), Harness::AtopVi);
        assert_eq!(classify("/tmp/claude-prompt-x.md"), Harness::Claude);
    }

    #[test]
    fn drops_json_and_pipes() {
        assert!(!keep("/tmp/foo.json", Harness::Tmp));
        assert!(!keep("/tmp/a|b.md", Harness::Tmp));
    }
}
