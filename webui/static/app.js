const RING_LEN = 2 * Math.PI * 140;

const el = (id) => document.getElementById(id);
const ui = {
  time: el("time"),
  hint: el("hint"),
  ring: el("ring"),
  pill: el("status-pill"),
  statusText: el("status-text"),
  start: el("btn-start"),
  pause: el("btn-pause"),
  stop: el("btn-stop"),
  duration: el("duration"),
  apply: el("btn-apply"),
  appsChips: el("apps-chips"),
  sitesChips: el("sites-chips"),
  appsCount: el("apps-count"),
  sitesCount: el("sites-count"),
  appsForm: el("apps-form"),
  sitesForm: el("sites-form"),
  appsInput: el("apps-input"),
  sitesInput: el("sites-input"),
  strict: el("strict"),
  preview: el("btn-preview"),
  events: el("events"),
  eventsCount: el("events-count"),
  mApps: el("m-apps"),
  mWeb: el("m-web"),
  mMin: el("m-min"),
  toast: el("toast"),
};

let state = null;
let renderedLists = { apps: "", sites: "", events: "" };
let durationTouched = false;

/* ------------------------------------------------------------------ helpers */
function toast(message, isError = false) {
  ui.toast.textContent = message;
  ui.toast.classList.toggle("error", isError);
  ui.toast.classList.add("show");
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => ui.toast.classList.remove("show"), 3600);
}

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `请求失败 (${res.status})`);
  if (data.state) render(data.state);
  return data;
}

function fmt(seconds) {
  const total = Math.max(0, Math.round(seconds));
  const m = String(Math.floor(total / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return `${m}:${s}`;
}

/* ------------------------------------------------------------------- render */
function renderChips(container, items, kind) {
  container.innerHTML = "";
  if (!items.length) {
    const hint = document.createElement("div");
    hint.className = "empty-chip";
    hint.textContent = kind === "apps" ? "白名单为空：不会关闭任何程序" : "白名单为空：不会拦截任何网站";
    container.appendChild(hint);
    return;
  }
  for (const item of items) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.append(document.createTextNode(item));
    const btn = document.createElement("button");
    btn.type = "button";
    btn.title = "移除";
    btn.textContent = "×";
    btn.addEventListener("click", () => removeItem(kind, item));
    chip.appendChild(btn);
    container.appendChild(chip);
  }
}

function renderEvents(events) {
  ui.events.innerHTML = "";
  ui.eventsCount.textContent = events.length;
  if (!events.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "还没有事件，开始一次专注试试";
    ui.events.appendChild(li);
    return;
  }
  for (const item of events) {
    const li = document.createElement("li");
    li.className = `kind-${item.kind}`;
    const dot = document.createElement("span");
    dot.className = "dot";
    const time = document.createElement("time");
    time.textContent = item.time;
    const text = document.createElement("span");
    text.className = "text";
    text.textContent = item.text;
    li.append(dot, time, text);
    ui.events.appendChild(li);
  }
}

function render(next) {
  state = next;
  const running = next.state === "running";
  const paused = next.state === "paused";
  const finished = next.state === "finished";
  const idle = next.state === "idle" || finished;

  ui.time.textContent = fmt(next.remaining_seconds);
  const ratio = next.total_seconds ? next.remaining_seconds / next.total_seconds : 0;
  ui.ring.style.strokeDashoffset = String(RING_LEN * (1 - ratio));

  ui.pill.classList.toggle("running", running);
  ui.statusText.textContent = running
    ? `专注中 · ${next.config.whitelist_apps.length} 应用 / ${next.config.whitelist_websites.length} 网站`
    : paused
    ? "已暂停 · 代理已还原"
    : finished
    ? "本轮已完成"
    : "准备就绪";

  ui.hint.textContent = running
    ? "空格暂停 · Esc 结束"
    : paused
    ? "空格继续"
    : finished
    ? "按空格再来一轮"
    : "按空格开始专注";

  ui.start.disabled = !idle;
  ui.pause.disabled = idle;
  ui.pause.textContent = paused ? "继续" : "暂停";
  ui.stop.disabled = idle;
  ui.duration.disabled = !idle;
  ui.apply.disabled = !idle;

  ui.mApps.textContent = next.blocked_apps;
  ui.mWeb.textContent = next.blocked_websites;
  ui.mMin.textContent = next.stats.total_minutes;

  if (!durationTouched) ui.duration.value = next.config.focus_duration;
  ui.strict.checked = next.config.strict_mode;

  const appsKey = next.config.whitelist_apps.join("|");
  if (appsKey !== renderedLists.apps) {
    renderedLists.apps = appsKey;
    renderChips(ui.appsChips, next.config.whitelist_apps, "apps");
    ui.appsCount.textContent = next.config.whitelist_apps.length;
  }

  const sitesKey = next.config.whitelist_websites.join("|");
  if (sitesKey !== renderedLists.sites) {
    renderedLists.sites = sitesKey;
    renderChips(ui.sitesChips, next.config.whitelist_websites, "sites");
    ui.sitesCount.textContent = next.config.whitelist_websites.length;
  }

  const eventsKey = next.events.map((e) => e.time + e.text).join("|");
  if (eventsKey !== renderedLists.events) {
    renderedLists.events = eventsKey;
    renderEvents(next.events);
  }
}

/* ------------------------------------------------------------------ actions */
async function startSession() {
  const minutes = Number(ui.duration.value) || 25;
  try {
    await post("/api/start", { minutes });
    toast(`专注开始，${minutes} 分钟后结束`);
  } catch (err) {
    toast(err.message, true);
  }
}

async function togglePause() {
  if (!state) return;
  try {
    if (state.state === "running") await post("/api/pause");
    else if (state.state === "paused") await post("/api/resume");
  } catch (err) {
    toast(err.message, true);
  }
}

async function stopSession() {
  try {
    await post("/api/stop");
    toast("已结束专注，系统代理已还原");
  } catch (err) {
    toast(err.message, true);
  }
}

async function saveConfig(patch, quiet = false) {
  try {
    await post("/api/config", patch);
    if (!quiet) toast("已保存");
  } catch (err) {
    toast(err.message, true);
  }
}

function addItem(kind) {
  const input = kind === "apps" ? ui.appsInput : ui.sitesInput;
  const value = input.value.trim();
  if (!value || !state) return;
  const key = kind === "apps" ? "whitelist_apps" : "whitelist_websites";
  const list = [...state.config[key]];
  if (list.some((item) => item.toLowerCase() === value.toLowerCase())) {
    toast("已经在白名单里了");
    input.value = "";
    return;
  }
  list.push(value);
  input.value = "";
  saveConfig({ [key]: list }, true).then(() => toast(`已添加 ${value}`));
}

function removeItem(kind, value) {
  if (!state) return;
  const key = kind === "apps" ? "whitelist_apps" : "whitelist_websites";
  const list = state.config[key].filter((item) => item !== value);
  saveConfig({ [key]: list }, true).then(() => toast(`已移除 ${value}`));
}

/* -------------------------------------------------------------------- wiring */
ui.start.addEventListener("click", () => {
  durationTouched = false;
  startSession();
});
ui.pause.addEventListener("click", togglePause);
ui.stop.addEventListener("click", stopSession);

ui.apply.addEventListener("click", () => {
  const minutes = Number(ui.duration.value);
  if (!minutes || minutes <= 0) return toast("请输入大于 0 的分钟数", true);
  durationTouched = false;
  saveConfig({ focus_duration: minutes });
});

ui.appsForm.addEventListener("submit", (e) => {
  e.preventDefault();
  addItem("apps");
});
ui.sitesForm.addEventListener("submit", (e) => {
  e.preventDefault();
  addItem("sites");
});

ui.strict.addEventListener("change", () => {
  saveConfig({ strict_mode: ui.strict.checked }, true).then(() =>
    toast(ui.strict.checked ? "严格模式已开启" : "严格模式已关闭")
  );
});

ui.preview.addEventListener("click", async () => {
  try {
    const res = await fetch("/api/preview");
    const data = await res.json();
    const apps = data.apps || [];
    toast(apps.length ? `点开始后会关闭：${apps.join("、")}` : "当前没有会被关闭的程序，放心开始");
  } catch (err) {
    toast(err.message, true);
  }
});

ui.duration.addEventListener("input", () => {
  durationTouched = true;
});
ui.duration.addEventListener("blur", () => {
  if (!state) return;
  ui.duration.value = ui.duration.value || state.config.focus_duration;
  durationTouched = false;
});

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  if (e.code === "Space") {
    e.preventDefault();
    if (!state) return;
    if (state.state === "idle") startSession();
    else togglePause();
  } else if (e.code === "Escape") {
    if (state && state.state !== "idle") stopSession();
  }
});

/* --------------------------------------------------------------- data stream */
function connect() {
  const source = new EventSource("/api/events");
  source.onmessage = (event) => {
    try {
      render(JSON.parse(event.data));
    } catch (err) {
      console.error(err);
    }
  };
  source.onerror = () => {
    source.close();
    setTimeout(connect, 1500);
  };
}

connect();
