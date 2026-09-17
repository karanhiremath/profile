use std::io::{self, Write};
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use rmpv::{decode, encode, Value};
use serde_json::Value as Json;

pub const LIST_DEADLINE: Duration = Duration::from_millis(400);

pub struct Nvim {
    stream: UnixStream,
    next_id: i64,
}

impl Nvim {
    pub fn connect(socket: &Path, timeout: Option<Duration>) -> Result<Self> {
        let stream = UnixStream::connect(socket)
            .with_context(|| format!("connect {}", socket.display()))?;
        if let Some(t) = timeout {
            stream.set_read_timeout(Some(t))?;
            stream.set_write_timeout(Some(t))?;
        }
        Ok(Self { stream, next_id: 1 })
    }

    pub fn call(&mut self, method: &str, params: Vec<Value>) -> Result<Value> {
        let id = self.next_id;
        self.next_id += 1;
        let msg = Value::Array(vec![
            Value::from(0),
            Value::from(id),
            Value::from(method),
            Value::Array(params),
        ]);
        encode::write_value(&mut self.stream, &msg)?;
        self.stream.flush()?;
        let resp = decode::read_value(&mut self.stream).map_err(|e| match e {
            decode::Error::InvalidMarkerRead(ioe) if ioe.kind() == io::ErrorKind::TimedOut => {
                anyhow!("rpc timeout")
            }
            decode::Error::InvalidDataRead(ioe) if ioe.kind() == io::ErrorKind::TimedOut => {
                anyhow!("rpc timeout")
            }
            other => anyhow!("rpc decode: {other}"),
        })?;
        let arr = resp
            .as_array()
            .ok_or_else(|| anyhow!("rpc response is not an array"))?;
        if arr.len() < 4 || arr[0].as_i64() != Some(1) {
            return Err(anyhow!("unexpected rpc response"));
        }
        if !arr[2].is_nil() {
            return Err(anyhow!("nvim error: {}", arr[2]));
        }
        Ok(arr[3].clone())
    }

    pub fn exec_lua(&mut self, code: &str, args: Vec<Value>) -> Result<Value> {
        self.call("nvim_exec_lua", vec![Value::from(code), Value::Array(args)])
    }
}

pub fn value_to_json(v: &Value) -> Json {
    match v {
        Value::Nil => Json::Null,
        Value::Boolean(b) => Json::Bool(*b),
        Value::Integer(i) => i
            .as_i64()
            .map(|n| Json::from(n))
            .or_else(|| i.as_u64().map(Json::from))
            .unwrap_or(Json::Null),
        Value::F32(f) => Json::from(*f as f64),
        Value::F64(f) => Json::from(*f),
        Value::String(s) => Json::from(s.as_str().unwrap_or("")),
        Value::Binary(b) => Json::from(String::from_utf8_lossy(b).into_owned()),
        Value::Array(items) => Json::Array(items.iter().map(value_to_json).collect()),
        Value::Map(pairs) => {
            let mut obj = serde_json::Map::new();
            for (k, val) in pairs {
                let key = match k {
                    Value::String(s) => s.as_str().unwrap_or("").to_string(),
                    other => other.to_string(),
                };
                obj.insert(key, value_to_json(val));
            }
            Json::Object(obj)
        }
        Value::Ext(_, data) => Json::from(hex::encode(data)),
    }
}

pub fn list_buffers(nvim: &mut Nvim) -> Result<Json> {
    let code = r#"
local out = {}
for _, buf in ipairs(vim.api.nvim_list_bufs()) do
  if vim.api.nvim_buf_is_loaded(buf) and vim.bo[buf].buftype == "" then
    local path = vim.api.nvim_buf_get_name(buf)
    if path ~= "" then
      out[#out + 1] = { buffer = buf, path = path, modified = vim.bo[buf].modified }
    end
  end
end
return { pid = vim.fn.getpid(), server = vim.v.servername, buffers = out }
"#;
    let v = nvim.exec_lua(code, vec![])?;
    Ok(value_to_json(&v))
}

pub fn helper_request(nvim: &mut Nvim, helper: &Path, req: &Path) -> Result<Json> {
    let code = "local a={...}; return vim.json.decode(dofile(a[1]).request(a[2]))";
    let v = nvim.exec_lua(
        code,
        vec![
            Value::from(helper.to_string_lossy().into_owned()),
            Value::from(req.to_string_lossy().into_owned()),
        ],
    )?;
    Ok(value_to_json(&v))
}

pub fn write_json_file(path: &Path, value: &impl serde::Serialize) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, serde_json::to_vec(value)?)?;
    Ok(())
}

pub fn helper_path() -> PathBuf {
    if let Ok(p) = std::env::var("ATOP_VI_HELPER") {
        return PathBuf::from(p);
    }
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.join("../atop/vi-request.lua")
}
