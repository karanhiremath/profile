// After Pi (or any Node client) writes openai-codex credentials, align Hermes
// and ~/.codex to the same grant. ChatGPT refresh tokens are single-use.
// Never logs credential values. Must not crash the host process.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const syncScript = process.env.CODEX_GRANT_SYNC || path.join(here, "codex_grant_sync.py");
const python = process.env.CODEX_GRANT_PYTHON || "python3";

function isAuthStore(filePath) {
  const resolved = String(filePath || "");
  if (!resolved.endsWith("auth.json")) return false;
  return resolved.includes(`${path.sep}.pi${path.sep}`)
    || resolved.includes(`${path.sep}.codex${path.sep}`)
    || resolved.includes(`${path.sep}.hermes${path.sep}`);
}

function adopt() {
  if (process.env.HERMES_CODEX_GRANT_ISOLATE === "1") return;
  if (process.env.CODEX_GRANT_SYNCING === "1") return;
  if (!fs.existsSync(syncScript)) return;
  try {
    spawnSync(python, [syncScript, "adopt"], {
      stdio: "ignore",
      timeout: 15_000,
      env: { ...process.env, CODEX_GRANT_SYNCING: "1" },
    });
  } catch {
    // never fail the host client
  }
}

function wrap(fn) {
  return function wrapped(file, ...rest) {
    const result = fn.call(this, file, ...rest);
    if (isAuthStore(file)) adopt();
    return result;
  };
}

function wrapRename(fn) {
  return function wrapped(from, to, ...rest) {
    const result = fn.call(this, from, to, ...rest);
    if (isAuthStore(to)) adopt();
    return result;
  };
}

try {
  fs.writeFileSync = wrap(fs.writeFileSync);
  fs.renameSync = wrapRename(fs.renameSync);
  if (fs.promises?.writeFile) {
    const orig = fs.promises.writeFile.bind(fs.promises);
    fs.promises.writeFile = async function writeFile(file, data, opts) {
      const result = await orig(file, data, opts);
      if (isAuthStore(file)) adopt();
      return result;
    };
  }
  if (fs.promises?.rename) {
    const orig = fs.promises.rename.bind(fs.promises);
    fs.promises.rename = async function rename(from, to) {
      const result = await orig(from, to);
      if (isAuthStore(to)) adopt();
      return result;
    };
  }
} catch {
  // ignore
}
