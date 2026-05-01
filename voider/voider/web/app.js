const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const statusEl = $("#status");
const inputEl = $("#input");
const formEl = $("#composer");
const modalRoot = $("#modal-root");

let ws;
let reconnectDelay = 1000;

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.addEventListener("open", () => {
    statusEl.textContent = "connected";
    statusEl.className = "status ok";
    reconnectDelay = 1000;
  });
  ws.addEventListener("close", () => {
    statusEl.textContent = "disconnected — retrying";
    statusEl.className = "status err";
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 10000);
  });
  ws.addEventListener("message", (e) => handleEvent(JSON.parse(e.data)));
}

function send(obj) { ws.send(JSON.stringify(obj)); }

function addMessage({ role, kind, text, head }) {
  const el = document.createElement("div");
  el.className = `msg ${role}` + (kind ? ` ${kind}` : "");
  if (role !== "tool" && role !== "reminder") {
    const r = document.createElement("div");
    r.className = "role";
    r.textContent = role;
    el.appendChild(r);
  }
  if (head) {
    const h = document.createElement("div");
    h.className = "head";
    h.textContent = head;
    el.appendChild(h);
  }
  const body = document.createElement("div");
  body.textContent = text ?? "";
  el.appendChild(body);
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return body;
}

function handleEvent(ev) {
  switch (ev.type) {
    case "assistant_text":
      addMessage({ role: "assistant", text: ev.content });
      break;
    case "tool_call":
      addMessage({
        role: "tool",
        head: `→ ${ev.tool}  (target: ${ev.target})`,
        text: ev.summary,
      });
      break;
    case "tool_result":
      addMessage({
        role: "tool",
        kind: ev.ok ? "" : "error",
        head: `${ev.ok ? "✓" : "✗"} ${ev.tool}`,
        text: truncate(ev.content, 1200),
      });
      break;
    case "tool_error":
      addMessage({ role: "tool", kind: "error", head: `✗ ${ev.tool}`, text: ev.error });
      break;
    case "tool_denied":
      addMessage({ role: "tool", kind: "denied", head: `denied: ${ev.tool}`, text: ev.decision });
      break;
    case "permission_request":
      showPermissionModal(ev);
      break;
    case "reminder_fired":
      addMessage({
        role: "reminder",
        head: "⏰ reminder",
        text: ev.text,
      });
      try { new Notification("voider reminder", { body: ev.text }); } catch (_) {}
      break;
    case "turn_done":
      break;
    case "error":
      addMessage({ role: "tool", kind: "error", head: "error", text: ev.error });
      break;
  }
}

function showPermissionModal(req) {
  const bg = document.createElement("div");
  bg.className = "modal-bg";

  const modal = document.createElement("div");
  modal.className = "modal";
  modal.innerHTML = `
    <h2>${req.tool}</h2>
    <div class="target">target: ${escapeHtml(req.target)}</div>
    <p>${escapeHtml(req.summary)}</p>
    <div class="args">${escapeHtml(JSON.stringify(req.arguments, null, 2))}</div>
    <div class="actions">
      <button data-d="allow_once">Allow once</button>
      <button data-d="allow_always">Allow always</button>
      <button class="secondary" data-d="deny_once">Deny once</button>
      <button class="danger" data-d="deny_always">Deny always</button>
    </div>
  `;
  bg.appendChild(modal);
  modalRoot.appendChild(bg);

  modal.querySelectorAll("button[data-d]").forEach((btn) => {
    btn.addEventListener("click", () => {
      send({
        type: "permission_response",
        request_id: req.request_id,
        decision: btn.dataset.d,
      });
      bg.remove();
    });
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function truncate(s, n) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + `\n…[truncated, ${s.length - n} more chars]` : s;
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = inputEl.value.trim();
  if (!v || ws.readyState !== WebSocket.OPEN) return;
  addMessage({ role: "user", text: v });
  send({ type: "user_message", content: v });
  inputEl.value = "";
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

if ("Notification" in window && Notification.permission === "default") {
  Notification.requestPermission();
}

connect();
