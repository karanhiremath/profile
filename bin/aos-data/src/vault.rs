use crate::error::AosError;
use crate::manifest::{
    builtin_personal, builtin_work, find_manifest, vault_root_for_manifest, Manifest, VaultClass,
};
use serde::Serialize;
use std::env;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct Vault {
    pub root: PathBuf,
    pub manifest: Manifest,
    pub argv0: String,
    pub manifest_path: Option<PathBuf>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Argv0 {
    Notes,
    Kh,
    AosData,
}

impl Argv0 {
    pub fn parse(name: &str) -> Self {
        match Path::new(name)
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or(name)
        {
            "notes" => Self::Notes,
            "kh" => Self::Kh,
            _ => Self::AosData,
        }
    }

    pub fn required_class(self) -> Option<VaultClass> {
        match self {
            Self::Notes => Some(VaultClass::Personal),
            Self::Kh => Some(VaultClass::Work),
            Self::AosData => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Notes => "notes",
            Self::Kh => "kh",
            Self::AosData => "aos-data",
        }
    }
}

impl Vault {
    pub fn resolve(argv0: Argv0, vault_flag: Option<&Path>) -> Result<Self, AosError> {
        let home = env::var("HOME").unwrap_or_else(|_| "/tmp".into());
        let (root, builtin) = match argv0 {
            Argv0::Notes => {
                let root = vault_flag
                    .map(PathBuf::from)
                    .or_else(|| env::var_os("PERSONAL_NOTES_ROOT").map(PathBuf::from))
                    .unwrap_or_else(|| PathBuf::from(&home).join("src/notes"));
                (root, Some(builtin_personal()))
            }
            Argv0::Kh => {
                let root = vault_flag
                    .map(PathBuf::from)
                    .or_else(|| env::var_os("WORK_NOTES_ROOT").map(PathBuf::from))
                    .unwrap_or_else(|| PathBuf::from(&home).join("src/karan.hiremath"));
                (root, Some(builtin_work()))
            }
            Argv0::AosData => {
                if let Some(p) = vault_flag {
                    (p.to_path_buf(), None)
                } else {
                    let cwd = env::current_dir().map_err(|e| AosError::msg(e.to_string()))?;
                    if let Some(m) = find_manifest(&cwd) {
                        let root = vault_root_for_manifest(&m);
                        return load_at(root, Some(m), argv0, None);
                    }
                    return Err(AosError::msg(
                        "aos-data: pass --vault or run from a vault with aos-data.toml",
                    ));
                }
            }
        };
        let root = canonicalize_or(&root);
        if !root.is_dir() {
            return Err(AosError::VaultMissing(root.display().to_string()));
        }
        let found = find_manifest(&root).filter(|p| vault_root_for_manifest(p) == root);
        load_at(root, found, argv0, builtin)
    }

    pub fn join(&self, rel: &str) -> Result<PathBuf, AosError> {
        let p = self.root.join(rel);
        confine(&self.root, &p)
    }

    pub fn daily_rel(&self, date: chrono::NaiveDate) -> String {
        let weekday = date.format("%a").to_string();
        self.manifest
            .paths
            .daily_name
            .replace("{date}", &date.format("%Y-%m-%d").to_string())
            .replace("{weekday}", &weekday)
    }

    pub fn daily_path(&self, date: chrono::NaiveDate) -> Result<PathBuf, AosError> {
        self.join(&format!("{}/{}", self.manifest.paths.daily, self.daily_rel(date)))
    }

    pub fn inbox_dir(&self) -> Result<PathBuf, AosError> {
        self.join(&self.manifest.paths.inbox)
    }
}

fn load_at(
    root: PathBuf,
    manifest_path: Option<PathBuf>,
    argv0: Argv0,
    builtin: Option<Manifest>,
) -> Result<Vault, AosError> {
    let (manifest, manifest_path) = if let Some(p) = manifest_path {
        (Manifest::load(&p)?, Some(p))
    } else if let Some(m) = builtin {
        (m, None)
    } else {
        return Err(AosError::msg(format!(
            "no aos-data.toml under {}",
            root.display()
        )));
    };
    if let Some(req) = argv0.required_class() {
        if manifest.class != req {
            return Err(AosError::ClassMismatch {
                argv0: argv0.as_str().into(),
                required: req.as_str().into(),
                actual: manifest.class.as_str().into(),
            });
        }
    }
    Ok(Vault {
        root,
        manifest,
        argv0: argv0.as_str().into(),
        manifest_path,
    })
}

fn canonicalize_or(p: &Path) -> PathBuf {
    p.canonicalize().unwrap_or_else(|_| p.to_path_buf())
}

pub fn confine(root: &Path, path: &Path) -> Result<PathBuf, AosError> {
    let root_c = canonicalize_or(root);
    let normalized = if path.exists() {
        canonicalize_or(path)
    } else {
        lexical_under(&root_c, path)
    };
    if !normalized.starts_with(&root_c) {
        return Err(AosError::Escape(path.display().to_string()));
    }
    Ok(path.to_path_buf())
}

fn lexical_under(_root: &Path, path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for c in path.components() {
        match c {
            std::path::Component::RootDir => out.push(std::path::MAIN_SEPARATOR_STR),
            std::path::Component::CurDir => {}
            std::path::Component::ParentDir => {
                let _ = out.pop();
            }
            other => out.push(other.as_os_str()),
        }
    }
    out
}

#[derive(Serialize)]
pub struct StatusJson<'a> {
    pub schema: &'static str,
    pub lane: &'a str,
    pub class: &'a str,
    pub name: &'a str,
    pub argv0: &'a str,
    pub vault: String,
    pub daily: String,
    pub daily_exists: bool,
    pub inbox: String,
    pub inbox_count: usize,
    pub manifest: Option<String>,
    pub git_branch: Option<String>,
    pub git_dirty: bool,
    pub git_short: String,
    pub work_load_signal: bool,
}
