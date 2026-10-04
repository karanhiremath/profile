const appEl = document.querySelector(".app");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const viewsEl = document.getElementById("views");
const tabsEl = document.getElementById("tabs");
const cardsEl = document.getElementById("cards");
const otelEl = document.getElementById("otel-cards");
const paneEl = document.getElementById("pane");
const paneCard = document.getElementById("pane-card");
const paneToggle = document.getElementById("pane-toggle");
const paneHint = document.getElementById("pane-hint");
const workersEl = document.getElementById("workers");
const termWrap = document.getElementById("term-wrap");
const termEl = document.getElementById("term");
const promptsEl = document.getElementById("prompts");
const bufferEl = document.getElementById("buffer-stream");
const bufferTitle = document.getElementById("buffer-title");
const dockEl = document.getElementById("dock");
const destBtn = document.getElementById("dest");
const destsEl = document.getElementById("dests");
const sheet = document.getElementById("sheet");
const talk = document.getElementById("talk");
const briefBtn = document.getElementById("brief");
const voiceModeBtn = document.getElementById("voice-mode");
const watchMeta = document.getElementById("watch-meta");
const ttyTitle = document.getElementById("tty-title");
const audioState = document.getElementById("audio-state");
const micDot = document.getElementById("mic-dot");
const meterEl = document.getElementById("meter");
const liveTranscript = document.getElementById("live-transcript");
const VIEWS = ["fleet", "otel", "pane"];

const WORK_DESTS = ["ao0", "ao1", "ao2", "ao3", "ao4", "infra0", "infra1", "infra2", "infra3", "infra4"];
const WORK_FAMILY = {
  ao0: "data",
  ao1: "model",
  ao2: "harness",
  ao3: "graph",
  ao4: "fleet",
  infra0: "infra",
  infra1: "infra",
  infra2: "infra",
  infra3: "infra",
  infra4: "infra",
};
const MIME_PREF = ["audio/mp4", "audio/aac", "audio/mp4;codecs=mp4a.40.2", "audio/webm;codecs=opus", "audio/webm"];
const HOLD_MS = 280;
const STREAM_RATE = 16000;
const VOICE_SILENCE_RMS = 0.018;
const VOICE_SILENCE_MS = 1100;
const VOICE_MIN_MS = 700;
const VOICE_MAX_MS = 18000;
const state = {
  dest: "cos",
  destLocked: false,
  target: "",
  lane: "",
  health: null,
  fleet: null,
  layers: null,
  agents: [],
  prompts: [],
  pane: "",
  paneFull: false,
  paneTarget: "",
  view: "pane",
  viewLocked: false,
  workers: [],
  buffer: null,
  prompt: null,
  otel: null,
  frameSeq: 0,
  activeLayer: "fleet",
  busy: false,
  recording: false,
  streaming: false,
  voiceMode: false,
  replySeq: 0,
};

let rec = null;
let chunks = [];
let recGen = 0;
let holdTimer = null;
let holdActive = false;
let player = null;
let lastAction = 0;
let streamSid = "";
let streamCtx = null;
let streamNode = null;
let term = null;
let fitAddon = null;
let lastFrameSeq = 0;
let streamSource = null;
let streamMic = null;
let chunkQueue = Promise.resolve();
let streamBytes = 0;
let streamStartedAt = 0;
let voiceHeard = false;
let voiceSilentSince = 0;
let voiceStopping = false;
let voiceMaxTimer = null;

function setStatus(msg) {
  if (statusEl) statusEl.textContent = msg || "";
}

function setTranscript(text) {
  const line = (text || "").trim();
  if (transcriptEl) transcriptEl.textContent = line ? line : "";
  if (liveTranscript) liveTranscript.textContent = line;
}

function setAudioHud(kind, detail) {
  if (micDot) {
    micDot.dataset.on = kind === "idle" ? "0" : "1";
    micDot.dataset.stream = kind === "stream" ? "1" : "0";
  }
  if (audioState) audioState.textContent = detail;
}

function paintMeter(level) {
  if (!meterEl || !meterEl.getContext) return;
  const ctx = meterEl.getContext("2d");
  const w = meterEl.width;
  const h = meterEl.height;
  ctx.fillStyle = "#243140";
  ctx.fillRect(0, 0, w, h);
  const bars = 12;
  const lit = Math.max(0, Math.min(bars, Math.round((level || 0) * bars)));
  for (let i = 0; i < bars; i += 1) {
    ctx.fillStyle = i < lit ? (i > 8 ? "#cd5244" : "#e5c843") : "#2f3b4e";
    ctx.fillRect(2 + i * 7, 2, 5, h - 4);
  }
}

function renderWatch() {
  const watch = state.paneTarget || watchTargetFor(state.dest);
  const inbox = !WORK_DESTS.includes(state.dest);
  const transport = (state.buffer && state.buffer.transport) || (inbox ? "inbox" : "tmux-input-buffer");
  if (watchMeta) {
    watchMeta.textContent = `watch ${watch} · ${transport} → ${destLabel(state.dest)}`;
  }
  if (ttyTitle) ttyTitle.textContent = `${watch} watch`;
  if (bufferTitle) bufferTitle.textContent = `${transport} → ${destLabel(state.dest)}`;
}

function watchTargetFor(dest) {
  const name = canonicalizeClientDest(dest);
  if (["brief", "this", "pi", "claude", "pm", "pl", "notes"].includes(name)) {
    return state.paneTarget || "cos:0.0";
  }
  return name.includes(":") ? name : `${name}:0.0`;
}

function renderBuffer(payload) {
  if (payload) state.buffer = payload;
  const text = (state.buffer && state.buffer.text) || "";
  if (bufferEl) bufferEl.textContent = text;
  renderWatch();
}

function playAudio(audioB64, mime) {
  if (!audioB64) {
    maybeResumeVoice();
    return;
  }
  try {
    pausePlayer();
    player = new Audio(`data:${mime || "audio/mpeg"};base64,${audioB64}`);
    player.onended = () => maybeResumeVoice();
    player.onerror = () => maybeResumeVoice();
    player.play().catch(() => maybeResumeVoice());
  } catch (_) {
    maybeResumeVoice();
  }
}

function pausePlayer() {
  if (!player) return;
  try {
    player.onended = null;
    player.onerror = null;
    player.pause();
  } catch (_) {
    /* already down */
  }
  player = null;
}

function maybeResumeVoice() {
  if (!state.voiceMode || state.recording) return;
  setAudioHud("listen", "voice mode · listening");
  window.setTimeout(() => {
    if (state.voiceMode && !state.recording && !state.busy) startTalk();
  }, 400);
}

function setVoiceMode(on) {
  state.voiceMode = Boolean(on);
  if (voiceModeBtn) {
    voiceModeBtn.setAttribute("aria-pressed", state.voiceMode ? "true" : "false");
    voiceModeBtn.textContent = state.voiceMode ? "Voice on" : "Voice";
  }
  setAudioHud(state.voiceMode ? "listen" : "idle", state.voiceMode ? "voice mode on · Chief of Staff" : "mic idle · ink-2");
}

async function toggleVoiceMode() {
  if (state.voiceMode) {
    recGen += 1;
    if (state.recording) stopTalk();
    pausePlayer();
    setVoiceMode(false);
    talkIdleLabel();
    return;
  }
  setVoiceMode(true);
  try {
    const hello = await postJson("/tts", { text: "Chief of Staff is listening." });
    playAudio(hello.audio_b64, hello.mime);
  } catch (_) {
    maybeResumeVoice();
  }
}

async function getJson(url) {
  const resp = await fetch(url);
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = new Error(json.error || String(resp.status));
    err.status = resp.status;
    err.body = json;
    throw err;
  }
  return json;
}

async function postJson(url, body) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = new Error(json.error || String(resp.status));
    err.status = resp.status;
    err.body = json;
    throw err;
  }
  return json;
}

function pickMime() {
  if (typeof MediaRecorder === "undefined") return "";
  for (const type of MIME_PREF) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

function familyOf(id) {
  if (WORK_FAMILY[id]) return WORK_FAMILY[id];
  const lanes = (state.health && state.health.lanes) || [];
  const hit = lanes.find((lane) => lane.id === id || (lane.sessions || []).includes(id));
  return (hit && hit.family) || "";
}

function liveWorkers() {
  const fromFleet = ((state.fleet && state.fleet.lanes) || {}).work_live || [];
  const fromAgents = state.agents
    .map(agentId)
    .filter((id) => WORK_DESTS.includes(id));
  return [...new Set([...fromFleet, ...fromAgents])].filter((id) => WORK_DESTS.includes(id));
}

function agentId(agent) {
  if (!agent) return "";
  if (typeof agent === "string") return agent;
  return String(agent.id || agent.name || agent.dest || "");
}

const STATIC_DESTS = [
  { id: "cos", family: "herm-tui" },
  { id: "this", family: "pi" },
  { id: "pi", family: "pi" },
  { id: "claude", family: "claude" },
  { id: "pm", family: "herm-tui" },
  { id: "pl", family: "herm-tui" },
  { id: "notes", family: "herm-tui" },
  { id: "brief", family: "spoken" },
];

function destLabel(dest) {
  const name = canonicalizeClientDest(dest);
  return name === "cos" ? "COS" : name;
}

function canonicalizeClientDest(dest) {
  const raw = String(dest || "").trim();
  const head = raw.split(":")[0];
  const folded = head.toLowerCase().replace(/[\s._]+/g, "-");
  const letters = head.replace(/[^A-Za-z]/g, "");
  if (letters.toUpperCase() === "COS") return "cos";
  if (["cos", "caws", "coz", "kaws", "kos", "cosie", "cocie", "chief", "chief-of-staff", "c-o-s", "cos-voice"].includes(folded)) {
    return "cos";
  }
  return head.toLowerCase() || "cos";
}

function destList() {
  const rows = STATIC_DESTS.map((row) => ({ ...row, live: true }));
  const seen = new Set(rows.map((row) => row.id));
  for (const id of liveWorkers()) {
    if (seen.has(id)) continue;
    seen.add(id);
    rows.push({ id, family: familyOf(id) || "worker", live: true });
  }
  for (const agent of state.agents) {
    const id = agentId(agent);
    if (!id || seen.has(id) || id.startsWith("cos-") || id === "cosw") continue;
    seen.add(id);
    rows.push({
      id,
      family: agent.family || familyOf(id) || "agent",
      live: Boolean(agent.live || agent.online),
    });
  }
  return rows;
}

function applyDest(dest) {
  state.dest = canonicalizeClientDest(dest || "cos");
  destBtn.textContent = destLabel(state.dest);
  renderWatch();
}

function cardState(value) {
  return String(value || "idle").toLowerCase();
}

function synthesizeLayers(fleet, health) {
  const lanes = (fleet && fleet.lanes) || {};
  const workLive = new Set(lanes.work_live || []);
  const planLive = new Set(lanes.plan_live || []);
  const cos = (fleet && fleet.cos) || {};
  const jobs = (fleet && fleet.jobs) || {};
  const running = jobs.running || [];
  const counts = jobs.counts || {};
  const hosts = (fleet && fleet.hosts) || [];
  const jobLine = running.length
    ? running.map((job) => `${job.project || "job"} · ${job.summary || job.id || ""}`).join("\n")
    : `No running jobs. ${Object.keys(counts).length ? JSON.stringify(counts) : ""}`.trim();

  const planIds = [];
  for (let i = 0; i < 5; i += 1) planIds.push(`cos-ao${i}`);
  for (let i = 0; i < 5; i += 1) planIds.push(`cos-infra${i}`);

  return {
    ok: true,
    layers: [
      {
        id: "fleet",
        title: "Fleet",
        summary: (fleet && fleet.spoken) || "",
        cards: [
          { title: "Spoken brief", meta: (fleet && fleet.host) || "", state: "live", detail: (fleet && fleet.spoken) || "No brief yet" },
          { title: "Cos", meta: cos.herm_tui_live ? "herm-tui" : "inbox", state: cos.herm_tui_live ? "live" : (cos.tmux ? "blocked" : "offline"), detail: cos.note || "Cos state unknown" },
          { title: "Jobs", meta: `${running.length} running`, state: running.length ? "running" : "idle", detail: jobLine },
          { title: "WASM tunnel", meta: "Termix", state: "live", detail: (fleet && fleet.wasm_tunnel) || "termix :18787 → :8787" },
          { title: "Omarchy", meta: fleet && fleet.oma_online ? "peer" : "down", state: fleet && fleet.oma_online ? "online" : "offline", detail: fleet && fleet.oma_online ? "Omarchy peer is online." : "Omarchy peer is offline. Sandboxes are empty." },
        ],
      },
      {
        id: "work",
        title: "Work",
        summary: "do-lanes",
        cards: WORK_DESTS.map((id) => ({
          title: id,
          meta: familyOf(id) || ((health && health.lanes) || []).find((lane) => (lane.sessions || []).includes(id))?.family || "",
          state: workLive.has(id) ? "live" : "blocked",
          detail: workLive.has(id) ? "Live do-lane" : "Not attached",
        })),
      },
      {
        id: "plan",
        title: "Plan",
        summary: "think lanes · steer-inbox only",
        cards: planIds.map((id) => ({
          title: id,
          meta: id.startsWith("cos-infra") ? "infra think" : `think · ${familyOf(id.replace("cos-", "")) || "ao"}`,
          state: planLive.has(id) ? "live" : "idle",
          detail: "Preview / steer-inbox only. Not a live dest.",
        })),
      },
      {
        id: "infra",
        title: "Infra",
        summary: "silicon / fabric",
        cards: [
          ...WORK_DESTS.filter((id) => id.startsWith("infra")).map((id) => ({
            title: id,
            meta: "infra",
            state: workLive.has(id) ? "live" : "blocked",
            detail: workLive.has(id) ? "Infra do-lane live" : "Infra lane idle",
          })),
          {
            title: "Silicon / fabric",
            meta: (fleet && fleet.host) || "",
            state: "idle",
            detail: [
              fleet && fleet.wasm_tunnel,
              (fleet && fleet.blocked_send_keys || []).length ? `Blocked send-keys: ${(fleet.blocked_send_keys || []).join(", ")}` : "",
            ].filter(Boolean).join("\n") || "No fabric notes",
          },
        ],
      },
      {
        id: "hosts",
        title: "Hosts",
        summary: "tailnet",
        cards: hosts.length
          ? hosts.map((host) => ({
              title: host.name || "peer",
              meta: [host.os, host.role].filter(Boolean).join(" · "),
              state: host.online ? "online" : "offline",
              detail: host.online ? "Online on tailnet" : "Offline",
            }))
          : [{ title: "Tailnet", meta: "", state: "offline", detail: "No peers in snapshot" }],
      },
      {
        id: "graph",
        title: "Graph",
        summary: "gates",
        cards: [
          {
            title: "Send-keys gates",
            meta: "blocked",
            state: "blocked",
            detail: ((fleet && fleet.blocked_send_keys) || ["cos", "cos-*", "atop"]).join(", "),
          },
          ...running.map((job) => ({
            title: String(job.project || job.id || "job"),
            meta: "running",
            state: "running",
            detail: job.summary || "",
          })),
        ],
      },
    ],
    agents: [{ id: "cos", family: "inbox", live: true }, ...WORK_DESTS.filter((id) => workLive.has(id)).map((id) => ({ id, family: familyOf(id), live: true }))],
    prompts: [],
  };
}

function layerList() {
  const layers = (state.layers && state.layers.layers) || [];
  if (layers.length) return layers;
  return (synthesizeLayers(state.fleet, state.health).layers);
}

function appendCard(parent, card) {
  const el = document.createElement("article");
  el.className = "card";
  const top = document.createElement("div");
  top.className = "card-top";
  const copy = document.createElement("div");
  const title = document.createElement("h2");
  title.textContent = card.title || "card";
  const meta = document.createElement("p");
  meta.className = "meta";
  meta.textContent = card.meta || "";
  copy.append(title, meta);
  const pill = document.createElement("span");
  pill.className = "pill";
  const st = cardState(card.state);
  pill.dataset.state = st;
  pill.textContent = st;
  top.append(copy, pill);
  const detail = document.createElement("p");
  detail.className = "detail";
  detail.textContent = card.detail || "";
  el.append(top, detail);
  parent.appendChild(el);
}

function ensureTerm() {
  if (term || typeof Terminal === "undefined" || !termEl) return term;
  term = new Terminal({
    convertEol: true,
    disableStdin: true,
    cursorBlink: false,
    fontFamily: 'Monaco, "Liberation Mono", "Courier New", monospace',
    fontSize: 12,
    theme: {
      background: "#2f3b4e",
      foreground: "#eceff0",
      cursor: "#e5c843",
      selectionBackground: "#8347a6",
    },
  });
  if (typeof FitAddon !== "undefined") {
    const Ctor = FitAddon.FitAddon || FitAddon;
    fitAddon = new Ctor();
    term.loadAddon(fitAddon);
  }
  term.open(termEl);
  return term;
}

function writeFrame(frame) {
  if (!frame) return;
  if (frame.seq && frame.seq === state.frameSeq && term) return;
  state.frameSeq = frame.seq || 0;
  if (frame.plain || frame.text) state.pane = frame.plain || frame.text;
  else if (!frame.ok && frame.error) state.pane = String(frame.error);
  const t = ensureTerm();
  if (!t) {
    if (paneEl) paneEl.textContent = paneLines(state.pane, 0) || "idle";
    return;
  }
  t.reset();
  if (!frame.ok) {
    t.writeln(frame.error || "pane blocked");
    return;
  }
  t.write(frame.text || frame.plain || "");
  if (fitAddon) {
    try {
      fitAddon.fit();
    } catch (_) {
      /* layout not ready */
    }
  }
}

function renderViews() {
  if (appEl) appEl.dataset.view = state.view || "fleet";
  if (viewsEl) {
    viewsEl.querySelectorAll("[data-view]").forEach((btn) => {
      btn.setAttribute("aria-selected", btn.dataset.view === state.view ? "true" : "false");
    });
  }
  tabsEl.hidden = state.view !== "fleet";
  cardsEl.hidden = state.view !== "fleet";
  if (otelEl) otelEl.hidden = state.view !== "otel";
  if (workersEl) workersEl.hidden = state.view !== "pane";
  const hasTerm = state.view === "pane" && Boolean(ensureTerm());
  if (termWrap) termWrap.hidden = state.view !== "pane";
  if (paneEl) paneEl.hidden = state.view === "pane" && hasTerm;
  renderWatch();
  if (state.view === "pane") {
    state.paneFull = true;
    if (!hasTerm && paneEl) paneEl.textContent = paneLines(state.pane, 0) || "idle";
    if (fitAddon) {
      try {
        fitAddon.fit();
      } catch (_) {
        /* ignore */
      }
    }
  }
}

function renderOtel(payload) {
  if (!otelEl) return;
  const cards = (payload && payload.cards) || [];
  otelEl.replaceChildren();
  if (!cards.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No OTEL cards.";
    otelEl.appendChild(empty);
    return;
  }
  cards.forEach((card) => appendCard(otelEl, card));
}

function renderWorkers() {
  if (!workersEl) return;
  workersEl.replaceChildren();
  const current = state.paneTarget || "";
  (state.workers || []).forEach((row) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "worker-chip";
    const active = row.target === current || row.id === current.split(":")[0];
    btn.dataset.active = active ? "1" : "0";
    btn.textContent = row.live ? row.id : `${row.id} · down`;
    btn.disabled = !row.live;
    btn.addEventListener("click", () => {
      applyDest(row.id);
      state.destLocked = true;
      selectView("pane", row.target || `${row.id}:0.0`);
    });
    workersEl.appendChild(btn);
  });
}

async function selectView(view, dest) {
  const next = VIEWS.includes(view) ? view : "fleet";
  state.viewLocked = true;
  state.view = next;
  if (dest) {
    applyDest(canonicalizeClientDest(dest));
    state.destLocked = true;
  }
  renderViews();
  try {
    const chosen = dest || state.paneTarget || watchTargetFor(state.dest);
    const snap = await postJson("/view", {
      view: next,
      dest: canonicalizeClientDest(dest || state.dest),
      target: chosen,
    });
    applySnapshot(snap);
    const pane = snap.pane_target || "";
    setStatus(pane ? `session ${destLabel(state.dest)} · ${pane}` : `view ${snap.view || next}`);
  } catch (err) {
    setStatus(`view ${next}: ${err.message}`);
  }
}

function renderTabs() {
  const layers = layerList();
  if (!layers.some((layer) => layer.id === state.activeLayer) && layers[0]) {
    state.activeLayer = layers[0].id;
  }
  tabsEl.replaceChildren();
  layers.forEach((layer) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tab";
    btn.role = "tab";
    btn.dataset.id = layer.id;
    btn.textContent = layer.title || layer.id;
    btn.setAttribute("aria-selected", layer.id === state.activeLayer ? "true" : "false");
    btn.addEventListener("click", () => {
      state.activeLayer = layer.id;
      renderTabs();
      renderCards();
    });
    tabsEl.appendChild(btn);
  });
}

function renderCards() {
  const layers = layerList();
  const layer = layers.find((item) => item.id === state.activeLayer) || layers[0];
  cardsEl.replaceChildren();
  if (!layer) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No layer snapshot yet.";
    cardsEl.appendChild(empty);
    return;
  }
  const cards = layer.cards || [];
  if (!cards.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = layer.summary || "Empty layer.";
    cardsEl.appendChild(empty);
    return;
  }
  cards.forEach((card) => appendCard(cardsEl, card));
}

function paneLines(text, limit) {
  const lines = String(text || "").replace(/\s+$/, "").split(/\r?\n/);
  if (!limit || lines.length <= limit) return lines.join("\n") || "idle";
  return lines.slice(-limit).join("\n");
}

function renderPane() {
  paneCard.dataset.open = state.paneFull || state.view === "pane" ? "1" : "0";
  const hint = state.view === "pane"
    ? (state.paneTarget || "worker")
    : (state.paneFull ? "full" : "preview");
  paneHint.textContent = hint;
  if (state.view !== "pane") {
    paneEl.textContent = paneLines(state.pane, state.paneFull ? 0 : 8) || "idle";
  }
}

function normalizeChoices(item) {
  if (!item) return [];
  if (typeof item === "string") return item ? [{ key: item, label: item }] : [];
  if (item.key || item.label) {
    const key = String(item.key || item.id || "");
    return key ? [{ key, label: String(item.label || item.key || item.id) }] : [];
  }
  const opts = item.options || [];
  return opts.flatMap((opt) => normalizeChoices(opt)).filter((opt) => opt.key);
}

function renderPrompts(items, prompt) {
  const current = prompt || (Array.isArray(items) ? items.find((row) => row && (row.options || row.key)) : null) || null;
  state.prompt = current;
  state.prompts = current ? [current] : [];
  promptsEl.replaceChildren();
  const target = (current && current.target) || "";
  const destName = canonicalizeClientDest(target || state.dest);
  if (!current || !WORK_DESTS.includes(destName)) {
    promptsEl.hidden = true;
    syncIslandInset();
    return;
  }
  const choices = normalizeChoices(current);
  if (!choices.length) {
    promptsEl.hidden = true;
    syncIslandInset();
    return;
  }
  promptsEl.hidden = false;
  if (current.title) {
    const title = document.createElement("p");
    title.className = "prompt-title";
    title.textContent = current.title;
    promptsEl.appendChild(title);
  }
  const list = document.createElement("div");
  list.className = "prompt-choices";
  choices.forEach((item) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pick";
    btn.dataset.key = item.key;
    btn.textContent = item.label;
    const hint = document.createElement("small");
    hint.textContent = item.key;
    btn.appendChild(hint);
    btn.addEventListener("click", () => pickKey(item.key));
    list.appendChild(btn);
  });
  promptsEl.appendChild(list);
  syncIslandInset();
}

function renderDests() {
  destsEl.replaceChildren();
  destList().forEach((row) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "dest-row";
    btn.dataset.active = row.id === state.dest ? "1" : "0";
    const label = document.createElement("span");
    label.textContent = destLabel(row.id);
    const meta = document.createElement("small");
    const family = row.id === "cos" ? "Chief of Staff" : row.family;
    meta.textContent = `${family}${row.live ? " · live" : ""}`;
    btn.append(label, meta);
    btn.addEventListener("click", () => selectDest(row.id));
    destsEl.appendChild(btn);
  });
}

function openSheet() {
  renderDests();
  sheet.hidden = false;
}

function closeSheet() {
  sheet.hidden = true;
}

async function selectDest(dest) {
  const name = canonicalizeClientDest(dest);
  applyDest(name);
  state.destLocked = true;
  closeSheet();
  renderDests();
  const watch = watchTargetFor(name);
  try {
    const snap = await postJson("/view", {
      view: state.view === "fleet" || state.view === "otel" ? state.view : "pane",
      dest: name,
      target: watch,
    });
    applySnapshot(snap);
    if (!["cos", "this", "pi", "brief", "claude", "pm", "pl", "notes"].includes(name)) {
      await postJson("/focus", { session: name }).catch(() => ({}));
    }
    setStatus(`session ${destLabel(name)} · ${snap.pane_target || watch}`);
  } catch (err) {
    setStatus(`session ${name}: ${err.message}`);
  }
}

async function pickKey(key) {
  setStatus(`pick ${key}…`);
  try {
    const body = { key };
    if (state.prompt && state.prompt.target) body.target = state.prompt.target;
    else if (WORK_DESTS.includes(state.dest)) body.target = state.target || `${state.dest}:0.0`;
    await postJson("/pick", body);
    setStatus(`picked ${key}`);
  } catch (err) {
    setStatus(`pick error: ${err.message}`);
  }
}

function applyLayersPayload(payload) {
  if (!payload || !payload.layers) return;
  state.layers = payload;
  if (Array.isArray(payload.agents)) state.agents = payload.agents;
  if (Array.isArray(payload.prompts) && payload.prompts.length && !state.prompt) {
    renderPrompts(payload.prompts);
  }
  renderTabs();
  renderCards();
}

function applyFleet(fleet) {
  state.fleet = fleet;
  if (Array.isArray(fleet.agents)) state.agents = fleet.agents;
  if (!state.layers || state.layers.synthetic) {
    const synthesized = synthesizeLayers(fleet, state.health);
    synthesized.synthetic = true;
    state.layers = synthesized;
    state.agents = synthesized.agents;
  }
  renderTabs();
  renderCards();
  renderDests();
}

function applySnapshot(data) {
  if (!data) return;
  if (!state.destLocked && data.dest) applyDest(data.dest);
  if (data.target) state.target = data.target;
  if (data.lane) state.lane = data.lane;
  if (data.view && (!state.viewLocked || data.view === state.view)) state.view = data.view;
  if (data.pane_target) state.paneTarget = data.pane_target;
  if (Array.isArray(data.workers)) state.workers = data.workers;
  if (state.recording && data.last_partial) setTranscript(data.last_partial);
  else if (data.last_transcript) setTranscript(data.last_transcript);
  if (typeof data.pane === "string") state.pane = data.pane;
  else if (data.pane && data.pane.text) state.pane = data.pane.text;
  if (data.otel) {
    state.otel = data.otel;
    renderOtel(data.otel);
  }
  if (data.frame) writeFrame(data.frame);
  renderViews();
  renderWorkers();
  renderWatch();
  renderPane();
  if (data.buffer) renderBuffer(data.buffer);
  if (data.prompt || Array.isArray(data.prompts)) renderPrompts(data.prompts, data.prompt);
  if (data.layers) applyLayersPayload({ layers: data.layers, agents: data.agents || state.agents });
  const replySeq = Number(data.reply_seq || 0);
  if (replySeq && replySeq !== state.replySeq) {
    state.replySeq = replySeq;
    if (!state.busy && !state.recording) {
      getJson(`/reply?id=${encodeURIComponent(data.reply_id || "")}`)
        .then((reply) => {
          if (reply && reply.audio_b64) playAudio(reply.audio_b64, reply.mime);
        })
        .catch(() => {});
    }
  }
  if (!state.busy && data.last_brief && state.activeLayer === "fleet") {
    /* keep the one-line status as the latest steer/brief, not a dump */
  }
}

function debounceAction() {
  const now = Date.now();
  if (now - lastAction < 180) return false;
  lastAction = now;
  return true;
}

function talkIdleLabel() {
  talk.dataset.on = "0";
  talk.dataset.stream = "0";
  talk.setAttribute("aria-pressed", "false");
  talk.textContent = state.voiceMode ? "Listening · tap send" : "Hold to talk";
  setAudioHud(state.voiceMode ? "listen" : "idle", state.voiceMode ? "voice mode · Chief of Staff" : "mic idle · ink-2");
  paintMeter(0);
}

function talkRecLabel(streaming) {
  talk.dataset.on = "1";
  talk.dataset.stream = streaming ? "1" : "0";
  talk.setAttribute("aria-pressed", "true");
  talk.textContent = streaming ? "Streaming · release" : "Listening · tap send";
  setAudioHud(streaming ? "stream" : "listen", streaming ? "capturing · ink-2 websocket" : "capturing · upload fallback");
}

function downsample(float32, fromRate, toRate) {
  if (fromRate === toRate) return float32;
  const ratio = fromRate / toRate;
  const n = Math.max(1, Math.round(float32.length / ratio));
  const out = new Float32Array(n);
  for (let i = 0; i < n; i += 1) {
    const idx = i * ratio;
    const lo = Math.floor(idx);
    const hi = Math.min(lo + 1, float32.length - 1);
    const frac = idx - lo;
    out[i] = float32[lo] * (1 - frac) + float32[hi] * frac;
  }
  return out;
}

function floatToPcm16(float32) {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, float32[i]));
    out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return out;
}

function enqueueChunk(sid, pcm) {
  if (!sid || !pcm.byteLength) return;
  streamBytes += pcm.byteLength;
  chunkQueue = chunkQueue
    .then(() =>
      fetch("/stt/chunk", {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-STT-Session": sid,
        },
        body: pcm,
      }).then((resp) => resp.json().catch(() => ({})))
    )
    .then((json) => {
      if (json && json.partial) setTranscript(json.partial);
      const held = streamStartedAt ? ((Date.now() - streamStartedAt) / 1000).toFixed(1) : "0.0";
      setAudioHud("stream", `capturing · ink-2 · ${held}s · ${Math.round(streamBytes / 1024)}k → ${state.dest}`);
      setStatus(`streaming ink-2 · ${held}s · ${Math.round(streamBytes / 1024)}k`);
    })
    .catch(() => {});
}

function tearStreamGraph() {
  try {
    if (streamNode) streamNode.disconnect();
  } catch (_) {
    /* already down */
  }
  try {
    if (streamSource) streamSource.disconnect();
  } catch (_) {
    /* already down */
  }
  if (streamMic) streamMic.getTracks().forEach((track) => track.stop());
  if (streamCtx && streamCtx.state !== "closed") streamCtx.close().catch(() => {});
  streamNode = null;
  streamSource = null;
  streamMic = null;
  streamCtx = null;
}

async function startStreamTalk(gen) {
  const opened = await fetch("/stt/open", { method: "POST" }).then((resp) => resp.json().catch(() => ({})));
  if (!opened.ok || !opened.session) {
    const err = new Error(opened.error || "stt open failed");
    err.fallback = true;
    throw err;
  }
  if (gen !== recGen) {
    fetch("/stt/abort", { method: "POST", headers: { "X-STT-Session": opened.session } }).catch(() => {});
    return false;
  }
  const mic = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
  });
  if (gen !== recGen) {
    mic.getTracks().forEach((track) => track.stop());
    fetch("/stt/abort", { method: "POST", headers: { "X-STT-Session": opened.session } }).catch(() => {});
    return false;
  }
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) {
    mic.getTracks().forEach((track) => track.stop());
    const err = new Error("AudioContext missing");
    err.fallback = true;
    throw err;
  }
  const ctx = new Ctx();
  await ctx.resume();
  const source = ctx.createMediaStreamSource(mic);
  const node = ctx.createScriptProcessor(2048, 1, 1);
  const mute = ctx.createGain();
  mute.gain.value = 0;
  streamSid = opened.session;
  streamCtx = ctx;
  streamNode = node;
  streamSource = source;
  streamMic = mic;
  streamBytes = 0;
  streamStartedAt = Date.now();
  chunkQueue = Promise.resolve();
  node.onaudioprocess = (event) => {
    if (streamSid !== opened.session) return;
    const input = event.inputBuffer.getChannelData(0);
    let sum = 0;
    for (let i = 0; i < input.length; i += 1) sum += input[i] * input[i];
    const rms = Math.sqrt(sum / input.length);
    paintMeter(Math.min(1, rms * 6));
    considerVoiceVad(rms);
    const resampled = downsample(input, ctx.sampleRate, STREAM_RATE);
    enqueueChunk(opened.session, floatToPcm16(resampled).buffer);
  };
  source.connect(node);
  node.connect(mute);
  mute.connect(ctx.destination);
  state.recording = true;
  state.streaming = true;
  armVoiceTurn();
  talkRecLabel(true);
  setStatus(state.voiceMode ? "voice mode · ink-2" : "streaming ink-2 · hold");
  return true;
}

async function startUploadTalk(gen) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });
  if (gen !== recGen) {
    stream.getTracks().forEach((track) => track.stop());
    return false;
  }
  chunks = [];
  const mime = pickMime();
  rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
  rec.ondataavailable = (event) => {
    if (event.data && event.data.size) chunks.push(event.data);
  };
  rec.start(250);
  state.recording = true;
  state.streaming = false;
  armVoiceTurn();
  talkRecLabel(false);
  setStatus(state.voiceMode ? "voice mode · upload fallback" : "listening · upload on release");
  return true;
}

function clearVoiceTimers() {
  if (voiceMaxTimer) {
    clearTimeout(voiceMaxTimer);
    voiceMaxTimer = null;
  }
}

function armVoiceTurn() {
  clearVoiceTimers();
  voiceHeard = false;
  voiceSilentSince = Date.now();
  voiceStopping = false;
  if (!state.voiceMode) return;
  voiceMaxTimer = window.setTimeout(() => {
    if (state.voiceMode && state.recording) requestVoiceStop();
  }, VOICE_MAX_MS);
}

function considerVoiceVad(rms) {
  if (!state.voiceMode || !state.recording || voiceStopping) return;
  const now = Date.now();
  const held = streamStartedAt ? now - streamStartedAt : 0;
  if (rms > VOICE_SILENCE_RMS) {
    voiceHeard = true;
    voiceSilentSince = now;
  }
  if (held > VOICE_MAX_MS) {
    requestVoiceStop();
    return;
  }
  if (voiceHeard && held > VOICE_MIN_MS && now - voiceSilentSince > VOICE_SILENCE_MS) {
    requestVoiceStop();
  }
}

function requestVoiceStop() {
  if (!state.recording || voiceStopping) return;
  voiceStopping = true;
  stopTalk();
}

async function startTalk() {
  if (state.recording || state.busy) return;
  pausePlayer();
  const gen = ++recGen;
  state.busy = true;
  setStatus(state.voiceMode ? "voice mode · listening…" : "mic…");
  try {
    try {
      const streamed = await startStreamTalk(gen);
      if (!streamed && gen === recGen && !state.recording) {
        setStatus("stream skipped · upload fallback");
        await startUploadTalk(gen);
      }
    } catch (err) {
      if (err && err.fallback === false) throw err;
      setStatus("stream open failed · upload fallback");
      await startUploadTalk(gen);
    }
  } catch (err) {
    state.busy = false;
    talkIdleLabel();
    setStatus(`mic error: ${err.message || err}`);
    maybeResumeVoice();
    return;
  }
  state.busy = false;
  if (gen !== recGen && !state.recording) {
    talkIdleLabel();
    maybeResumeVoice();
  }
}

async function steerTranscript(text, sttJson) {
  const spokenHint = sttJson && sttJson.mode === "stream-while-hold" ? "stream-while-hold" : "";
  setTranscript(text);
  if (!text) {
    state.busy = false;
    setStatus("empty transcript");
    maybeResumeVoice();
    return;
  }
  setStatus(`steer → ${state.dest}${spokenHint ? ` · ${spokenHint}` : ""}`);
  const steered = await postJson("/steer", {
    text,
    dest: state.dest,
    target: state.target || undefined,
  });
  if (steered.dest) applyDest(steered.dest);
  if (steered.buffer) renderBuffer(steered.buffer);
  if (steered.prompt || Array.isArray(steered.prompts)) renderPrompts(steered.prompts, steered.prompt);
  playAudio(steered.audio_b64, steered.mime);
  if (steered.reply_seq) state.replySeq = Number(steered.reply_seq);
  const spoken = steered.spoken || text;
  setStatus(steered.ok ? `sent → ${destLabel(steered.dest || state.dest)}` : `steer error: ${steered.error || "failed"}`);
  if (spoken && spoken !== text) setTranscript(`${text} · ${spoken}`);
}

async function stopStreamTalk() {
  const sid = streamSid;
  streamSid = "";
  tearStreamGraph();
  talkIdleLabel();
  if (!sid) {
    state.recording = false;
    state.streaming = false;
    state.busy = false;
    maybeResumeVoice();
    return;
  }
  setStatus("finalizing ink-2…");
  try {
    await chunkQueue;
    const stt = await fetch("/stt/finalize", {
      method: "POST",
      headers: { "X-STT-Session": sid },
    });
    const sttJson = await stt.json().catch(() => ({}));
    if (!sttJson.ok) {
      state.busy = false;
      setStatus(`STT error: ${sttJson.error || stt.status}`);
      maybeResumeVoice();
      return;
    }
    await steerTranscript(String(sttJson.transcript || "").trim(), sttJson);
  } catch (err) {
    setStatus(`steer error: ${err.message || err}`);
    maybeResumeVoice();
  } finally {
    state.busy = false;
    state.streaming = false;
  }
}

async function stopUploadTalk() {
  if (!rec) {
    state.recording = false;
    state.busy = false;
    talkIdleLabel();
    return;
  }
  const recorder = rec;
  rec = null;
  talkIdleLabel();
  setStatus("transcribing…");
  let blob;
  try {
    blob = await new Promise((resolve, reject) => {
      recorder.onerror = () => reject(new Error("recorder error"));
      recorder.onstop = () => {
        resolve(new Blob(chunks, { type: recorder.mimeType || "audio/mp4" }));
      };
      try {
        recorder.stop();
      } catch (err) {
        reject(err);
      }
      recorder.stream.getTracks().forEach((track) => track.stop());
    });
  } catch (err) {
    state.busy = false;
    setStatus(`record error: ${err.message || err}`);
    maybeResumeVoice();
    return;
  }
  if (!blob || blob.size < 64) {
    state.busy = false;
    setStatus("empty take · hold to talk");
    maybeResumeVoice();
    return;
  }
  try {
    const stt = await fetch("/stt", {
      method: "POST",
      headers: { "Content-Type": blob.type || "audio/mp4" },
      body: blob,
    });
    const sttJson = await stt.json().catch(() => ({}));
    if (!sttJson.ok) {
      state.busy = false;
      setStatus(`STT error: ${sttJson.error || stt.status}`);
      maybeResumeVoice();
      return;
    }
    await steerTranscript(String(sttJson.transcript || "").trim(), sttJson);
  } catch (err) {
    setStatus(`steer error: ${err.message || err}`);
    maybeResumeVoice();
  } finally {
    state.busy = false;
  }
}

async function stopTalk() {
  recGen += 1;
  holdActive = false;
  clearVoiceTimers();
  const streaming = state.streaming;
  state.recording = false;
  if (streaming) {
    await stopStreamTalk();
    return;
  }
  await stopUploadTalk();
}

function toggleTalk() {
  if (state.recording) stopTalk();
  else startTalk();
}

function onTalkPointerDown(event) {
  event.preventDefault();
  if (event.pointerType === "mouse" && event.button !== 0) return;
  try {
    talk.setPointerCapture(event.pointerId);
  } catch (_) {
    /* older WebKit */
  }
  holdActive = false;
  clearTimeout(holdTimer);
  holdTimer = setTimeout(() => {
    holdActive = true;
    if (!state.recording) startTalk();
  }, HOLD_MS);
}

function onTalkPointerUp(event) {
  event.preventDefault();
  clearTimeout(holdTimer);
  holdTimer = null;
  try {
    talk.releasePointerCapture(event.pointerId);
  } catch (_) {
    /* already released */
  }
  if (!debounceAction()) return;
  if (holdActive) {
    holdActive = false;
    if (state.recording) stopTalk();
    return;
  }
  toggleTalk();
}

function onTalkLost() {
  clearTimeout(holdTimer);
  holdTimer = null;
  if (holdActive && state.recording) {
    holdActive = false;
    stopTalk();
  }
}

async function runBrief() {
  if (state.busy || state.recording) return;
  state.busy = true;
  setStatus("brief…");
  try {
    const json = await postJson("/brief", {});
    playAudio(json.audio_b64, json.mime);
    if (json.spoken) {
      setTranscript(json.spoken);
      if (state.fleet) state.fleet.spoken = json.spoken;
      if (state.layers && state.layers.synthetic) applyFleet(state.fleet);
    }
    setStatus("brief ready");
  } catch (err) {
    setStatus(`brief error: ${err.message || err}`);
  } finally {
    state.busy = false;
  }
}

async function boot() {
  setStatus("connecting…");
  const health = await getJson("/health").catch((err) => ({ ok: false, error: err.message }));
  state.health = health;
  if (health.dest) applyDest(health.dest);
  if (health.target) state.target = health.target;
  if (health.lane) state.lane = health.lane;
  if (health.view) state.view = health.view;
  if (health.pane_target) state.paneTarget = health.pane_target;
  renderViews();
  setStatus(
    health.ok
      ? `listen ${health.listen} · ${health.stt_mode || "stt"} ${health.stt_model || ""} · cartesia ${health.cartesia_key}`
      : `health: ${health.error || "down"}`
  );

  const fleet = await getJson("/fleet").catch(() => null);
  if (fleet) applyFleet(fleet);

  try {
    const layers = await getJson("/layers");
    applyLayersPayload(layers);
  } catch (_) {
    const synthesized = synthesizeLayers(state.fleet || {}, state.health);
    synthesized.synthetic = true;
    state.layers = synthesized;
    state.agents = synthesized.agents;
    renderTabs();
    renderCards();
  }

  const params = new URLSearchParams(window.location.search);
  const wantView = params.get("view") || "pane";
  await selectView(wantView, params.get("dest") || params.get("target") || "cos:0.0");
  setAudioHud("idle", "mic idle · ink-2");
  paintMeter(0);
  syncIslandInset();

  const events = new EventSource("/events");
  events.onmessage = (event) => {
    try {
      applySnapshot(JSON.parse(event.data));
    } catch (_) {
      /* ignore a bad frame */
    }
  };
  events.onerror = () => {
    if (!state.busy && !state.recording) setStatus("SSE reconnecting…");
  };
}

talk.addEventListener("pointerdown", onTalkPointerDown);
talk.addEventListener("pointerup", onTalkPointerUp);
talk.addEventListener("pointercancel", onTalkLost);
talk.addEventListener("lostpointercapture", onTalkLost);
talk.addEventListener("contextmenu", (event) => event.preventDefault());
talk.addEventListener("click", (event) => event.preventDefault());
briefBtn.addEventListener("click", () => runBrief());
if (voiceModeBtn) voiceModeBtn.addEventListener("click", () => toggleVoiceMode());
destBtn.addEventListener("click", () => (sheet.hidden ? openSheet() : closeSheet()));
document.getElementById("sheet-backdrop").addEventListener("click", closeSheet);
if (viewsEl) {
  viewsEl.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => selectView(btn.dataset.view || "fleet"));
  });
}
if (paneToggle) {
  paneToggle.addEventListener("click", () => {
    selectView("pane", state.paneTarget || "cos:0.0");
  });
}
function syncIslandInset() {
  const root = document.documentElement;
  const vv = window.visualViewport;
  let overlay = 0;
  if (vv) overlay = Math.max(0, window.innerHeight - (vv.height + vv.offsetTop));
  const mobile = window.matchMedia("(pointer: coarse), (max-width: 820px)").matches;
  const comet = /Comet|Perplexity/i.test(navigator.userAgent || "");
  if (comet && overlay < 80) overlay = 80;
  else if (mobile && overlay < 52) overlay = 56;
  root.style.setProperty("--browser-island", `${Math.round(overlay)}px`);
  if (dockEl) {
    root.style.setProperty("--island-space", `${Math.ceil(dockEl.getBoundingClientRect().height)}px`);
  }
  if (state.view === "pane" && fitAddon) {
    try {
      fitAddon.fit();
    } catch (_) {
      /* ignore */
    }
  }
}

window.addEventListener("resize", syncIslandInset);
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", syncIslandInset);
  window.visualViewport.addEventListener("scroll", syncIslandInset);
}

boot().catch((err) => setStatus(String(err)));
syncIslandInset();
