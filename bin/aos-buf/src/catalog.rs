use std::collections::BTreeMap;
use std::fs;
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use walkdir::WalkDir;

use crate::classify::{classify, keep};
use crate::rpc::{self, LIST_DEADLINE};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CatalogEntry {
    pub id: String,
    pub harness: String,
    pub path: String,
    pub live: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pid: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub buffer: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub socket: Option<String>,
    pub modified: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Catalog {
    pub schema: &'static str,
    pub entries: Vec<CatalogEntry>,
}

impl Catalog {
    pub fn new(entries: Vec<CatalogEntry>) -> Self {
        Self {
            schema: "atop-vi.catalog.v1",
            entries,
        }
    }
}

fn username() -> String {
    std::env::var("USER")
        .or_else(|_| std::env::var("LOGNAME"))
        .unwrap_or_else(|_| "user".into())
}

fn current_uid() -> u32 {
    unsafe { libc::getuid() }
}

pub fn owner_ok(sock: &Path) -> bool {
    let dir = match sock.parent() {
        Some(d) => d,
        None => return false,
    };
    let meta = match fs::metadata(sock) {
        Ok(m) => m,
        Err(_) => return false,
    };
    let dmeta = match fs::metadata(dir) {
        Ok(m) => m,
        Err(_) => return false,
    };
    if !meta.file_type().is_socket() {
        return false;
    }
    if meta.uid() != current_uid() || dmeta.uid() != current_uid() {
        return false;
    }
    dmeta.mode() & 0o777 == 0o700
}

fn nvim_roots() -> Vec<PathBuf> {
    let user = username();
    let mut roots = Vec::new();
    let tmp = std::env::var("TMPDIR").unwrap_or_else(|_| "/tmp".into());
    roots.push(PathBuf::from(&tmp).join(format!("nvim.{user}")));
    roots.push(PathBuf::from("/tmp").join(format!("nvim.{user}")));
    roots.push(PathBuf::from("/private/tmp").join(format!("nvim.{user}")));
    if let Ok(entries) = fs::read_dir("/var/folders") {
        for e in entries.flatten() {
            let mid = e.path();
            if let Ok(subs) = fs::read_dir(&mid) {
                for s in subs.flatten() {
                    let t = s.path().join("T").join(format!("nvim.{user}"));
                    if t.is_dir() {
                        roots.push(t);
                    }
                }
            }
        }
    }
    roots
}

pub fn list_sockets() -> Vec<PathBuf> {
    let mut out = Vec::new();
    for root in nvim_roots() {
        if !root.is_dir() {
            continue;
        }
        for ent in WalkDir::new(&root).follow_links(false).into_iter().flatten() {
            let p = ent.path();
            let name = p.file_name().and_then(|s| s.to_str()).unwrap_or("");
            if name.starts_with("nvim.") && owner_ok(p) {
                out.push(p.to_path_buf());
            }
        }
    }
    out.sort();
    out.dedup();
    out
}

fn stem_id(path: &str) -> String {
    Path::new(path)
        .file_name()
        .and_then(|s| s.to_str())
        .map(|n| n.strip_suffix(".md").unwrap_or(n).to_string())
        .unwrap_or_else(|| path.to_string())
}

fn entry_from_buf(path: &str, live: bool, pid: Option<i64>, buffer: Option<i64>, socket: Option<String>, modified: bool) -> Option<CatalogEntry> {
    let harness = classify(path);
    if !keep(path, harness) {
        return None;
    }
    Some(CatalogEntry {
        id: stem_id(path),
        harness: harness.as_str().to_string(),
        path: path.to_string(),
        live,
        pid,
        buffer,
        socket,
        modified,
    })
}

pub fn live_entries() -> Vec<CatalogEntry> {
    let mut out = Vec::new();
    for sock in list_sockets() {
        let mut nvim = match rpc::Nvim::connect(&sock, Some(LIST_DEADLINE)) {
            Ok(n) => n,
            Err(e) => {
                eprintln!("aos-buf: skip {}: {e}", sock.display());
                continue;
            }
        };
        let rec = match rpc::list_buffers(&mut nvim) {
            Ok(v) => v,
            Err(e) => {
                eprintln!("aos-buf: skip {}: {e}", sock.display());
                continue;
            }
        };
        let pid = rec.get("pid").and_then(|v| v.as_i64());
        let bufs = rec.get("buffers").and_then(|v| v.as_array()).cloned().unwrap_or_default();
        for b in bufs {
            let path = b.get("path").and_then(|v| v.as_str()).unwrap_or("");
            if path.is_empty() {
                continue;
            }
            let buffer = b.get("buffer").and_then(|v| v.as_i64());
            let modified = b.get("modified").and_then(|v| v.as_bool()).unwrap_or(false);
            if let Some(ent) = entry_from_buf(
                path,
                true,
                pid,
                buffer,
                Some(sock.to_string_lossy().into_owned()),
                modified,
            ) {
                out.push(ent);
            }
        }
    }
    out
}

fn temp_roots() -> Vec<PathBuf> {
    let mut roots = vec![
        std::env::temp_dir(),
        PathBuf::from("/tmp"),
        PathBuf::from("/private/tmp"),
    ];
    if let Ok(tmp) = std::env::var("TMPDIR") {
        roots.push(PathBuf::from(tmp));
    }
    roots.sort();
    roots.dedup();
    roots
}

pub fn disk_entries() -> Vec<CatalogEntry> {
    let mut out = Vec::new();
    let mut seen = std::collections::HashSet::new();
    let mut add = |p: PathBuf| {
        let Ok(path) = p.canonicalize() else { return };
        if !path.is_file() {
            return;
        }
        let key = path.to_string_lossy().into_owned();
        if !seen.insert(key.clone()) {
            return;
        }
        if let Some(ent) = entry_from_buf(&key, false, None, None, None, false) {
            out.push(ent);
        }
    };
    for root in temp_roots() {
        if !root.is_dir() {
            continue;
        }
        let Ok(rd) = fs::read_dir(&root) else { continue };
        for ent in rd.flatten() {
            let name = ent.file_name();
            let name = name.to_string_lossy();
            let p = ent.path();
            if name.starts_with("herm-") && name.ends_with(".md")
                || name.starts_with("claude-prompt-") && name.ends_with(".md")
                || name.starts_with("cursor-prompt-") && name.ends_with(".md")
                || name.starts_with("atop-vi") && name.ends_with(".md")
            {
                add(p);
            } else if name.starts_with("pi-editor-") {
                add(p.join("prompt.md"));
            } else if name.starts_with("nvim-workbench") {
                add(p.join("original.md"));
            }
        }
    }
    let backup = dirs_claude_prompt_backups();
    if backup.is_dir() {
        let mut files: Vec<_> = fs::read_dir(&backup)
            .into_iter()
            .flatten()
            .flatten()
            .map(|e| e.path())
            .filter(|p| {
                p.file_name()
                    .and_then(|s| s.to_str())
                    .map(|n| n.starts_with("claude-prompt-") && n.ends_with(".md"))
                    .unwrap_or(false)
            })
            .collect();
        files.sort_by_key(|p| std::cmp::Reverse(p.metadata().and_then(|m| m.modified()).ok()));
        for p in files.into_iter().take(8) {
            add(p);
        }
    }
    out
}

fn dirs_claude_prompt_backups() -> PathBuf {
    home().join(".claude/prompt-backups")
}

fn home() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("/"))
}

pub fn merge(live: Vec<CatalogEntry>, disk: Vec<CatalogEntry>) -> Vec<CatalogEntry> {
    let mut by_path: BTreeMap<String, CatalogEntry> = BTreeMap::new();
    for e in disk.into_iter().chain(live) {
        match by_path.get(&e.path) {
            Some(prev) if prev.live || !e.live => {}
            _ => {
                by_path.insert(e.path.clone(), e);
            }
        }
    }
    let mut out: Vec<_> = by_path.into_values().collect();
    out.sort_by(|a, b| {
        let ha = classify(&a.path).order();
        let hb = classify(&b.path).order();
        ha.cmp(&hb).then_with(|| a.path.cmp(&b.path))
    });
    out
}

pub fn build(no_disk: bool) -> Catalog {
    let live = live_entries();
    let disk = if no_disk { Vec::new() } else { disk_entries() };
    Catalog::new(merge(live, disk))
}

pub fn print_list(cat: &Catalog) {
    for e in &cat.entries {
        let live = if e.live { "live" } else { "disk" };
        let pid = e
            .pid
            .map(|p| format!("pid={p}"))
            .unwrap_or_else(|| "pid=-".into());
        println!("{}\t{live}\t{}\t{pid}\t{}", e.harness, e.id, e.path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn live_wins_same_path() {
        let disk = vec![CatalogEntry {
            id: "prompt".into(),
            harness: "pi".into(),
            path: "/tmp/p.md".into(),
            live: false,
            pid: None,
            buffer: None,
            socket: None,
            modified: false,
        }];
        let live = vec![CatalogEntry {
            id: "prompt".into(),
            harness: "pi".into(),
            path: "/tmp/p.md".into(),
            live: true,
            pid: Some(1),
            buffer: Some(1),
            socket: Some("/tmp/s".into()),
            modified: true,
        }];
        let m = merge(live, disk);
        assert_eq!(m.len(), 1);
        assert!(m[0].live);
        assert_eq!(m[0].pid, Some(1));
    }
}
