//! GitHub-release self-update for the portable aos binary.
//! Never curl|sh. Verify SHA256. `gh` is the transport.
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

pub const DEFAULT_REPO: &str = "karanhiremath/profile";
pub const SCHEMA: &str = "aos.update.v1";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Pin {
    pub repo: String,
    pub tag: String,
    pub sha256: Option<String>,
}

#[derive(Debug, Clone)]
pub struct Opts {
    pub dry_run: bool,
    pub from_source: bool,
    pub tag: Option<String>,
    pub dest: Option<PathBuf>,
}

pub fn version() -> String {
    option_env!("AOS_RELEASE")
        .unwrap_or(env!("CARGO_PKG_VERSION"))
        .to_string()
}

pub fn asset_name(os: &str, arch: &str) -> Result<String> {
    let os = match os {
        "macos" | "darwin" => "darwin",
        "linux" => "linux",
        other => bail!("unsupported os: {other}"),
    };
    let arch = match arch {
        "aarch64" | "arm64" => "arm64",
        "x86_64" | "amd64" => "x64",
        other => bail!("unsupported arch: {other}"),
    };
    Ok(format!("aos-{os}-{arch}"))
}

pub fn current_asset() -> Result<String> {
    asset_name(env::consts::OS, env::consts::ARCH)
}

pub fn sha256_hex(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hex::encode(hasher.finalize())
}

pub fn verify_sha256(data: &[u8], expected: &str) -> Result<()> {
    let actual = sha256_hex(data);
    if actual != expected {
        bail!("sha256 {actual} != pin {expected}");
    }
    Ok(())
}

pub fn sha_for_asset(sums: &str, asset: &str) -> Result<String> {
    for line in sums.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let mut parts = line.split_whitespace();
        let sha = parts.next().context("empty SHA256SUMS line")?;
        let name = parts.next().context("SHA256SUMS missing filename")?;
        let name = name.trim_start_matches('*');
        if name == asset {
            return Ok(sha.to_string());
        }
    }
    bail!("no sha for {asset} in SHA256SUMS");
}

pub fn parse_pin(text: &str) -> Pin {
    let mut pin = Pin {
        repo: DEFAULT_REPO.to_string(),
        tag: String::new(),
        sha256: None,
    };
    for raw in text.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let Some((k, v)) = line.split_once('=') else {
            continue;
        };
        let v = v.trim().trim_matches('"');
        match k.trim() {
            "AOS_REPO" => pin.repo = v.to_string(),
            "AOS_PIN_TAG" => pin.tag = v.to_string(),
            "AOS_PIN_SHA256" => {
                if !v.is_empty() {
                    pin.sha256 = Some(v.to_string());
                }
            }
            _ => {}
        }
    }
    pin
}

pub fn pin_paths() -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Ok(p) = env::var("AOS_PIN_FILE") {
        if !p.is_empty() {
            out.push(PathBuf::from(p));
        }
    }
    if let Some(home) = env::var_os("HOME") {
        out.push(PathBuf::from(home).join(".config/aos/pin.env"));
    }
    if let Ok(profile) = env::var("PROFILE_DIR") {
        out.push(PathBuf::from(profile).join("bin/aos-buf/pin.env"));
    }
    if let Ok(exe) = env::current_exe() {
        if let Some(dir) = exe.parent() {
            out.push(dir.join("pin.env"));
            out.push(dir.join("../share/aos/pin.env"));
        }
    }
    out
}

pub fn load_pin() -> Pin {
    for path in pin_paths() {
        if let Ok(text) = fs::read_to_string(&path) {
            return parse_pin(&text);
        }
    }
    Pin {
        repo: env::var("AOS_REPO").unwrap_or_else(|_| DEFAULT_REPO.to_string()),
        tag: env::var("AOS_PIN_TAG").unwrap_or_default(),
        sha256: env::var("AOS_PIN_SHA256").ok().filter(|s| !s.is_empty()),
    }
}

pub fn dest_bin(explicit: Option<PathBuf>) -> PathBuf {
    if let Some(p) = explicit {
        return p;
    }
    if let Ok(prefix) = env::var("AGENTIC_PREFIX") {
        if !prefix.is_empty() {
            return PathBuf::from(prefix).join("bin/aos");
        }
    }
    let home = env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(home).join(".local/bin/aos")
}

fn source_crate() -> Result<PathBuf> {
    let cands = [
        env::var("PROFILE_DIR")
            .ok()
            .map(|p| PathBuf::from(p).join("bin/aos-buf/Cargo.toml")),
        env::current_dir()
            .ok()
            .map(|p| p.join("bin/aos-buf/Cargo.toml")),
        env::var("HOME")
            .ok()
            .map(|h| PathBuf::from(h).join("src/profile/bin/aos-buf/Cargo.toml")),
    ];
    for cand in cands.into_iter().flatten() {
        if cand.is_file() {
            return Ok(cand);
        }
    }
    bail!("no aos-buf crate; set PROFILE_DIR or pass a GitHub --tag");
}

fn run_gh(args: &[&str]) -> Result<std::process::Output> {
    Command::new("gh")
        .args(args)
        .output()
        .context("gh missing; install GitHub CLI (just gh) or use --from-source")
}

pub fn run(opts: Opts) -> Result<Value> {
    if opts.from_source {
        return from_source(&opts);
    }
    let mut pin = load_pin();
    if let Some(tag) = opts.tag.clone() {
        pin.tag = tag;
    }
    if pin.tag.is_empty() {
        pin.tag = latest_aos_tag(&pin.repo).unwrap_or_default();
    }
    let asset = current_asset()?;
    let dest = dest_bin(opts.dest);
    if pin.tag.is_empty() {
        if opts.dry_run {
            return Ok(json!({
                "schema": SCHEMA,
                "mode": "source-fallback",
                "reason": "no AOS_PIN_TAG and no aos-v* GitHub release",
                "asset": asset,
                "dest": dest,
                "version": version(),
            }));
        }
        eprintln!("aos: no GitHub pin/release; building from source");
        return from_source(&Opts {
            dry_run: false,
            dest: Some(dest),
            ..opts
        });
    }
    let plan = json!({
        "schema": SCHEMA,
        "mode": "github",
        "repo": pin.repo,
        "tag": pin.tag,
        "asset": asset,
        "dest": dest,
        "version": version(),
    });
    if opts.dry_run {
        return Ok(plan);
    }
    install_github(&pin, &asset, &dest)?;
    Ok(json!({
        "schema": SCHEMA,
        "status": "ok",
        "mode": "github",
        "repo": pin.repo,
        "tag": pin.tag,
        "asset": asset,
        "dest": dest,
        "version": version(),
    }))
}

fn latest_aos_tag(repo: &str) -> Result<String> {
    let out = run_gh(&[
        "release",
        "list",
        "-R",
        repo,
        "--limit",
        "20",
        "--json",
        "tagName",
    ])?;
    if !out.status.success() {
        bail!(
            "gh release list failed: {}",
            String::from_utf8_lossy(&out.stderr)
        );
    }
    let v: Value = serde_json::from_slice(&out.stdout)?;
    let Some(arr) = v.as_array() else {
        bail!("gh release list: expected array");
    };
    for item in arr {
        if let Some(tag) = item.get("tagName").and_then(|t| t.as_str()) {
            if tag.starts_with("aos-v") {
                return Ok(tag.to_string());
            }
        }
    }
    bail!("no aos-v* release on {repo}");
}

fn install_github(pin: &Pin, asset: &str, dest: &Path) -> Result<()> {
    if Command::new("gh").arg("--version").output().is_err() {
        bail!("gh missing; install GitHub CLI (just gh) or use --from-source");
    }
    let tmp = tempfile_dir()?;
    let sums = "SHA256SUMS.txt";
    let download = run_gh(&[
        "release",
        "download",
        &pin.tag,
        "-R",
        &pin.repo,
        "-p",
        asset,
        "-p",
        sums,
        "--dir",
        &tmp.to_string_lossy(),
        "--clobber",
    ])?;
    if !download.status.success() {
        let _ = fs::remove_dir_all(&tmp);
        bail!(
            "gh release download failed: {}",
            String::from_utf8_lossy(&download.stderr)
        );
    }
    let bin_path = tmp.join(asset);
    let sums_path = tmp.join(sums);
    let bytes = fs::read(&bin_path).with_context(|| format!("read {}", bin_path.display()))?;
    let expected = if let Some(pin_sha) = &pin.sha256 {
        pin_sha.clone()
    } else {
        let text = fs::read_to_string(&sums_path).context("read SHA256SUMS.txt")?;
        sha_for_asset(&text, asset)?
    };
    verify_sha256(&bytes, &expected)?;
    atomic_install(&bytes, dest)?;
    let _ = fs::remove_dir_all(&tmp);
    eprintln!("aos: installed {} ({}) -> {}", pin.tag, asset, dest.display());
    Ok(())
}

fn from_source(opts: &Opts) -> Result<Value> {
    let manifest = source_crate()?;
    let dest = dest_bin(opts.dest.clone());
    let rec = json!({
        "schema": SCHEMA,
        "mode": "source",
        "manifest": manifest,
        "dest": dest,
        "version": version(),
    });
    if opts.dry_run {
        return Ok(rec);
    }
    let status = Command::new("cargo")
        .args([
            "build",
            "--release",
            "--manifest-path",
            &manifest.to_string_lossy(),
            "--bin",
            "aos",
        ])
        .status()
        .context("cargo build")?;
    if !status.success() {
        bail!("cargo build --bin aos failed");
    }
    let built = manifest
        .parent()
        .unwrap()
        .join("target/release/aos");
    let bytes = fs::read(&built).with_context(|| format!("read {}", built.display()))?;
    atomic_install(&bytes, &dest)?;
    let dest_buf = dest.with_file_name("aos-buf");
    if dest_buf != dest {
        let _ = fs::remove_file(&dest_buf);
        std::os::unix::fs::symlink(&dest, &dest_buf).ok();
    }
    eprintln!("aos: built from source -> {}", dest.display());
    Ok(json!({
        "schema": SCHEMA,
        "status": "ok",
        "mode": "source",
        "manifest": manifest,
        "dest": dest,
        "version": version(),
    }))
}

fn atomic_install(bytes: &[u8], dest: &Path) -> Result<()> {
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = dest.with_extension("new");
    fs::write(&tmp, bytes)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&tmp, fs::Permissions::from_mode(0o755))?;
    }
    if dest.exists() {
        let bak = dest.with_extension("bak");
        let _ = fs::remove_file(&bak);
        fs::rename(dest, &bak).ok();
    }
    fs::rename(&tmp, dest).with_context(|| format!("install {}", dest.display()))?;
    Ok(())
}

fn tempfile_dir() -> Result<PathBuf> {
    let base = env::temp_dir().join(format!("aos-update-{}", std::process::id()));
    if base.exists() {
        fs::remove_dir_all(&base)?;
    }
    fs::create_dir_all(&base)?;
    Ok(base)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn assets() {
        assert_eq!(asset_name("macos", "aarch64").unwrap(), "aos-darwin-arm64");
        assert_eq!(asset_name("linux", "x86_64").unwrap(), "aos-linux-x64");
        assert_eq!(asset_name("linux", "arm64").unwrap(), "aos-linux-arm64");
        assert!(asset_name("windows", "x86_64").is_err());
    }

    #[test]
    fn pin_parse() {
        let p = parse_pin(
            "AOS_REPO=example/profile\nAOS_PIN_TAG=aos-v0.1.0\nAOS_PIN_SHA256=abc\n",
        );
        assert_eq!(p.repo, "example/profile");
        assert_eq!(p.tag, "aos-v0.1.0");
        assert_eq!(p.sha256.as_deref(), Some("abc"));
    }

    #[test]
    fn sums() {
        let text = "deadbeef  aos-darwin-arm64\ncafe  aos-linux-x64\n";
        assert_eq!(sha_for_asset(text, "aos-darwin-arm64").unwrap(), "deadbeef");
        assert!(sha_for_asset(text, "missing").is_err());
    }

    #[test]
    fn sha_roundtrip() {
        let data = b"aos";
        let hex = sha256_hex(data);
        verify_sha256(data, &hex).unwrap();
        assert!(verify_sha256(data, "00").is_err());
    }
}
