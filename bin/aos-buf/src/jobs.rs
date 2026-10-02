use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{bail, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JobRec {
    pub schema: String,
    pub id: String,
    pub status: String,
    pub op: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pid: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub socket: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub job_dir: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub started_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub poll: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub apply: Option<Value>,
}

pub fn job_root() -> PathBuf {
    if let Ok(p) = std::env::var("ATOP_VI_JOBDIR") {
        return PathBuf::from(p);
    }
    if let Ok(p) = std::env::var("AOS_BUF_JOBDIR") {
        return PathBuf::from(p);
    }
    let tmp = std::env::var("TMPDIR").unwrap_or_else(|_| "/tmp".into());
    let user = std::env::var("USER").unwrap_or_else(|_| "user".into());
    PathBuf::from(tmp).join(format!("atop-vi.jobs.{user}"))
}

pub fn ensure_job_root() -> Result<PathBuf> {
    let root = job_root();
    fs::create_dir_all(&root)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = fs::metadata(&root)?.permissions();
        perms.set_mode(0o700);
        fs::set_permissions(&root, perms)?;
    }
    Ok(root)
}

pub fn new_job_id() -> String {
    let mut bytes = [0u8; 6];
    getrandom(&mut bytes);
    hex::encode(bytes)
}

fn getrandom(buf: &mut [u8]) {
    use std::fs::File;
    use std::io::Read;
    if let Ok(mut f) = File::open("/dev/urandom") {
        let _ = f.read_exact(buf);
    }
}

pub fn lock_path(root: &Path, socket: &str) -> PathBuf {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    h.update(socket.as_bytes());
    let hex = hex::encode(&h.finalize()[..8]);
    root.join("locks").join(hex)
}

pub fn apply_envelope(
    id: &str,
    status: &str,
    op: &str,
    socket: &str,
    pid: Option<i64>,
    path: &str,
    file: &str,
    buffer: Option<i64>,
    job_dir: &str,
    started_at: &str,
    result: Option<Value>,
) -> Value {
    json!({
        "schema": "aos.apply.v1",
        "id": id,
        "status": status,
        "op": op,
        "target": {
            "kind": "nvim-socket",
            "id": pid.map(|p| p.to_string()).unwrap_or_default(),
            "socket": socket,
        },
        "input": {
            "path": path,
            "file": file,
            "buffer": buffer,
        },
        "job_dir": job_dir,
        "started_at": started_at,
        "poll": format!("aos buf job {id}"),
        "result": result,
    })
}

pub fn write_job(rec: &JobRec) -> Result<()> {
    let dir = rec
        .job_dir
        .as_deref()
        .map(PathBuf::from)
        .ok_or_else(|| anyhow::anyhow!("job_dir missing"))?;
    fs::create_dir_all(&dir)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = fs::metadata(&dir)?.permissions();
        perms.set_mode(0o700);
        fs::set_permissions(&dir, perms)?;
    }
    fs::write(dir.join("job.json"), serde_json::to_vec_pretty(rec)?)?;
    if let Some(apply) = &rec.apply {
        fs::write(dir.join("apply.json"), serde_json::to_vec_pretty(apply)?)?;
    }
    Ok(())
}

fn pid_alive(pid: i64) -> bool {
    if pid <= 0 {
        return false;
    }
    unsafe { libc::kill(pid as i32, 0) == 0 }
}

pub fn load_job(id: &str) -> Result<JobRec> {
    let dir = job_root().join(id);
    let meta = dir.join("job.json");
    if !meta.is_file() {
        bail!("aos-buf: no job {id}");
    }
    let mut rec: JobRec = serde_json::from_slice(&fs::read(&meta)?)?;
    let pid_path = dir.join("pid");
    if let Ok(s) = fs::read_to_string(&pid_path) {
        if let Ok(p) = s.trim().parse::<i64>() {
            rec.pid = Some(p);
        }
    }
    let result_path = dir.join("result.json");
    let alive = rec.pid.map(pid_alive).unwrap_or(false);
    if result_path.is_file() && fs::metadata(&result_path)?.len() > 0 {
        let result: Value = serde_json::from_slice(&fs::read(&result_path)?)?;
        rec.status = result
            .get("status")
            .and_then(|v| v.as_str())
            .unwrap_or(&rec.status)
            .to_string();
        rec.result = Some(result);
    } else if alive {
        rec.status = "running".into();
    } else if rec.status == "running" {
        rec.status = "error".into();
        rec.error = Some("worker exited without a result".into());
    }
    if let Ok(raw) = fs::read(dir.join("apply.json")) {
        if let Ok(mut apply) = serde_json::from_slice::<Value>(&raw) {
            if let Some(obj) = apply.as_object_mut() {
                obj.insert("status".into(), json!(rec.status));
                if let Some(result) = &rec.result {
                    obj.insert("result".into(), result.clone());
                }
            }
            rec.apply = Some(apply);
        }
    }
    rec.poll = Some(format!("aos buf job {}", rec.id));
    Ok(rec)
}

pub fn list_jobs() -> Result<Value> {
    let root = job_root();
    let mut jobs = Vec::new();
    if root.is_dir() {
        let mut names: Vec<_> = fs::read_dir(&root)?
            .flatten()
            .filter(|e| e.path().join("job.json").is_file())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .collect();
        names.sort();
        for name in names {
            if let Ok(rec) = load_job(&name) {
                jobs.push(json!({
                    "id": rec.id,
                    "status": rec.status,
                    "pid": rec.pid,
                    "path": rec.path,
                    "file": rec.file,
                    "job_dir": rec.job_dir,
                }));
            }
        }
    }
    Ok(json!({ "schema": "atop-vi.jobs.v1", "jobs": jobs }))
}
