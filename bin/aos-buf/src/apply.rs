use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::os::unix::io::AsRawFd;

use crate::catalog::{self, CatalogEntry};
use crate::jobs::{
    self, apply_envelope, ensure_job_root, lock_path, new_job_id, write_job, JobRec,
};
use crate::rpc::{self, helper_path, helper_request};

pub struct Target {
    pub entry: CatalogEntry,
}

pub fn resolve(id: &str) -> Result<Target> {
    let cat = catalog::build(false);
    let want = id.trim_end_matches('/');
    let mut matches: Vec<CatalogEntry> = cat
        .entries
        .into_iter()
        .filter(|e| {
            let name = Path::new(&e.path)
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("");
            let stem = name.strip_suffix(".md").unwrap_or(name);
            want == e.id
                || want == name
                || want == stem
                || want == e.path
                || e.path.ends_with(&format!("/{want}"))
                || e.path.contains(want)
                || e.pid.map(|p| p.to_string() == want).unwrap_or(false)
                || e.buffer.map(|b| b.to_string() == want).unwrap_or(false)
        })
        .collect();
    if matches.is_empty() {
        bail!("aos-buf: no open prompt buffer matching '{id}'");
    }
    matches.sort_by_key(|e| {
        let name = Path::new(&e.path)
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("");
        (
            if name.starts_with("herm-") { 0 } else { 1 },
            if e.live { 0 } else { 1 },
            e.path.clone(),
        )
    });
    Ok(Target {
        entry: matches.remove(0),
    })
}

pub fn snapshot(target: &Target) -> Result<Value> {
    let sock = target
        .entry
        .socket
        .as_deref()
        .ok_or_else(|| anyhow::anyhow!("target is disk-only; open it in nvim first"))?;
    let helper = helper_path();
    let reqdir = tempfile_dir()?;
    let req = reqdir.join("snap-req.json");
    let out = reqdir.join("snap-out.json");
    rpc::write_json_file(
        &req,
        &json!({
            "op": "snapshot",
            "path": target.entry.path,
            "buffer": target.entry.buffer,
            "output_path": out,
        }),
    )?;
    let mut nvim = rpc::Nvim::connect(Path::new(sock), None)?;
    let _ = helper_request(&mut nvim, &helper, &req)?;
    let rec: Value = serde_json::from_slice(&fs::read(&out)?)?;
    let _ = fs::remove_dir_all(reqdir);
    Ok(rec)
}

pub fn get_text(target: &Target) -> Result<String> {
    let rec = snapshot(target)?;
    if rec.get("status").and_then(|v| v.as_str()) == Some("error") {
        bail!(
            "{}",
            rec.get("error").and_then(|v| v.as_str()).unwrap_or("snapshot failed")
        );
    }
    let lines = rec
        .get("lines")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let mut text = lines
        .iter()
        .map(|v| v.as_str().unwrap_or("").to_string())
        .collect::<Vec<_>>()
        .join("\n");
    if !text.is_empty() {
        text.push('\n');
    }
    Ok(text)
}

fn tempfile_dir() -> Result<PathBuf> {
    let tmp = std::env::var("TMPDIR").unwrap_or_else(|_| "/tmp".into());
    let dir = PathBuf::from(tmp).join(format!("aos-buf.{}", new_job_id()));
    fs::create_dir_all(&dir)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = fs::metadata(&dir)?.permissions();
        perms.set_mode(0o700);
        fs::set_permissions(&dir, perms)?;
    }
    Ok(dir)
}

pub fn run_write(target: &Target, file: &Path, expected_pid: Option<i64>) -> Result<Value> {
    let sock = target
        .entry
        .socket
        .as_deref()
        .ok_or_else(|| anyhow::anyhow!("target is disk-only; open it in nvim first"))?;
    if !file.is_file() {
        bail!("missing file {}", file.display());
    }
    let helper = helper_path();
    let reqdir = tempfile_dir()?;
    let req = reqdir.join("write-req.json");
    let out = reqdir.join("write-out.json");
    rpc::write_json_file(
        &req,
        &json!({
            "op": "write",
            "path": target.entry.path,
            "buffer": target.entry.buffer,
            "file": file,
            "expected_pid": expected_pid,
            "output_path": out,
        }),
    )?;
    let mut nvim = rpc::Nvim::connect(Path::new(sock), None)?;
    let _ = helper_request(&mut nvim, &helper, &req)?;
    let rec: Value = serde_json::from_slice(&fs::read(&out).with_context(|| format!("read {}", out.display()))?)?;
    let _ = fs::remove_dir_all(reqdir);
    if rec.get("status").and_then(|v| v.as_str()) == Some("error") {
        bail!(
            "{}",
            rec.get("error").and_then(|v| v.as_str()).unwrap_or("write failed")
        );
    }
    Ok(rec)
}

pub fn intern_apply(
    job_dir: &Path,
    socket: &str,
    path: &str,
    buffer: i64,
    file: &Path,
    expected_pid: i64,
    session: &str,
) -> Result<Value> {
    let root = job_dir
        .parent()
        .map(|p| p.to_path_buf())
        .unwrap_or_else(jobs::job_root);
    fs::create_dir_all(root.join("locks"))?;
    let lockp = lock_path(&root, socket);
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(&lockp)?;
    let rc = unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX) };
    if rc != 0 {
        bail!("flock {}: errno {}", lockp.display(), std::io::Error::last_os_error());
    }
    let target = Target {
        entry: CatalogEntry {
            id: String::new(),
            harness: String::new(),
            path: path.to_string(),
            live: true,
            pid: Some(expected_pid),
            buffer: Some(buffer),
            socket: Some(socket.to_string()),
            modified: false,
        },
    };
    let result = match run_write(&target, file, Some(expected_pid)) {
        Ok(rec) => {
            let mut rec = rec;
            if let Some(obj) = rec.as_object_mut() {
                obj.entry("status").or_insert(json!("ok"));
            }
            rec
        }
        Err(e) => json!({ "status": "error", "error": e.to_string() }),
    };
    fs::write(job_dir.join("result.json"), serde_json::to_vec_pretty(&result)?)?;
    let started = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
    let status = result
        .get("status")
        .and_then(|v| v.as_str())
        .unwrap_or("error");
    let apply = apply_envelope(
        job_dir
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("job"),
        status,
        "set",
        socket,
        Some(expected_pid),
        path,
        &file.to_string_lossy(),
        Some(buffer),
        &job_dir.to_string_lossy(),
        &started,
        Some(result.clone()),
    );
    fs::write(job_dir.join("apply.json"), serde_json::to_vec_pretty(&apply)?)?;
    let _ = session;
    let _ = unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_UN) };
    Ok(result)
}

pub fn queue_set(target: &Target, file: &Path, wait: bool, as_apply: bool) -> Result<Value> {
    if !file.is_file() {
        bail!("missing file {}", file.display());
    }
    let sock = target
        .entry
        .socket
        .clone()
        .ok_or_else(|| anyhow::anyhow!("target is disk-only; open it in nvim first"))?;
    if wait {
        let rec = run_write(target, file, target.entry.pid)?;
        if as_apply {
            let id = new_job_id();
            let started = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
            let status = rec
                .get("status")
                .and_then(|v| v.as_str())
                .unwrap_or("ok")
                .to_string();
            return Ok(apply_envelope(
                &id,
                &status,
                "set",
                &sock,
                target.entry.pid,
                &target.entry.path,
                &file.to_string_lossy(),
                target.entry.buffer,
                "",
                &started,
                Some(rec),
            ));
        }
        return Ok(json!({
            "wrote": true,
            "path": rec.get("path"),
            "pid": rec.get("pid"),
            "buffer": rec.get("buffer"),
            "sha256": rec.get("sha256"),
            "status": rec.get("status").unwrap_or(&json!("ok")),
        }));
    }
    let root = ensure_job_root()?;
    let id = new_job_id();
    let dir = root.join(&id);
    fs::create_dir_all(&dir)?;
    let started = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
    let apply = apply_envelope(
        &id,
        "running",
        "set",
        &sock,
        target.entry.pid,
        &target.entry.path,
        &file.to_string_lossy(),
        target.entry.buffer,
        &dir.to_string_lossy(),
        &started,
        None,
    );
    let rec = JobRec {
        schema: "atop-vi.job.v1".into(),
        id: id.clone(),
        status: "running".into(),
        op: "set".into(),
        pid: None,
        session: Some(target.entry.id.clone()),
        path: Some(target.entry.path.clone()),
        file: Some(file.to_string_lossy().into_owned()),
        socket: Some(sock.clone()),
        job_dir: Some(dir.to_string_lossy().into_owned()),
        started_at: Some(started),
        poll: Some(format!("aos buf job {id}")),
        result: None,
        error: None,
        apply: Some(apply.clone()),
    };
    write_job(&rec)?;
    let exe = std::env::current_exe()?;
    let stderr = File::create(dir.join("stderr"))?;
    let child = Command::new(exe)
        .arg("intern-apply")
        .arg("--job-dir")
        .arg(&dir)
        .arg("--socket")
        .arg(&sock)
        .arg("--path")
        .arg(&target.entry.path)
        .arg("--buffer")
        .arg(target.entry.buffer.unwrap_or(0).to_string())
        .arg("--file")
        .arg(file)
        .arg("--pid")
        .arg(target.entry.pid.unwrap_or(0).to_string())
        .arg("--session")
        .arg(&target.entry.id)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(stderr)
        .spawn()
        .context("spawn intern-apply")?;
    let pid = child.id() as i64;
    let mut rec = rec;
    rec.pid = Some(pid);
    write_job(&rec)?;
    let mut f = File::create(dir.join("pid"))?;
    writeln!(f, "{pid}")?;
    if as_apply {
        Ok(apply)
    } else {
        Ok(serde_json::to_value(&rec)?)
    }
}

pub fn print_wrote(v: &Value) {
    if v.get("wrote").and_then(|x| x.as_bool()) == Some(true) {
        println!(
            "wrote {} pid={} buf={} sha256={}",
            v.get("path").and_then(|x| x.as_str()).unwrap_or("-"),
            v.get("pid").map(|x| x.to_string()).unwrap_or_else(|| "-".into()),
            v.get("buffer").map(|x| x.to_string()).unwrap_or_else(|| "-".into()),
            v.get("sha256").and_then(|x| x.as_str()).unwrap_or("-"),
        );
    } else {
        println!("{}", serde_json::to_string_pretty(v).unwrap_or_default());
    }
}
