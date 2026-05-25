// Frontend wiring: command search, confirm modal, SSE live run, downloads.
import { setActiveAgents, setAgentStatus, resetAgents } from "/static/viz.js";

const $ = (id) => document.getElementById(id);

const state = {
  commands: [],
  agents: [],
  selectedCmd: null,
  filtered: [],
  focusIdx: 0,
  jobId: null,
  eventSource: null,
};

// ---------- Bootstrap ----------
async function init() {
  const [c, a] = await Promise.all([
    fetch("/api/commands").then((r) => r.json()),
    fetch("/api/agents").then((r) => r.json()),
  ]);
  state.commands = c.commands;
  state.agents = a.agents;
  state.filtered = state.commands;

  renderQuickRow();
  bindSearch();
  bindModal();
  bindRunPanel();

  // Dispatch agents to viz module
  window.dispatchEvent(new CustomEvent("agents-loaded", { detail: state.agents }));
}

// ---------- Quick row of common commands ----------
function renderQuickRow() {
  const row = $("quickrow");
  const popular = ["audit", "page", "schema", "geo", "technical", "content", "local"];
  row.innerHTML = popular
    .map((k) => {
      const c = state.commands.find((x) => x.key === k);
      return c ? `<span class="qr-chip" data-cmd="${c.key}">/seo ${c.key}</span>` : "";
    })
    .join("");
  row.querySelectorAll(".qr-chip").forEach((chip) => {
    chip.addEventListener("click", () => openConfirm(chip.dataset.cmd));
  });
}

// ---------- Search bar + dropdown ----------
function bindSearch() {
  const input = $("searchInput");
  const dropdown = $("dropdown");
  const goBtn = $("searchGo");

  function renderDropdown(items, focusIdx = 0) {
    state.filtered = items;
    state.focusIdx = focusIdx;
    if (!items.length) {
      dropdown.hidden = true;
      return;
    }
    dropdown.hidden = false;
    dropdown.innerHTML = items
      .map(
        (c, i) => `
      <div class="dropdown-item ${i === focusIdx ? "focus" : ""}" data-cmd="${c.key}">
        <div class="di-head">
          <span class="di-cmd">/seo ${c.key}</span>
          <span class="di-label">${c.label}</span>
        </div>
        <div class="di-desc">${c.one_liner}</div>
      </div>`
      )
      .join("");
    dropdown.querySelectorAll(".dropdown-item").forEach((el) => {
      el.addEventListener("click", () => openConfirm(el.dataset.cmd));
      el.addEventListener("mouseenter", () => {
        state.focusIdx = state.filtered.findIndex((c) => c.key === el.dataset.cmd);
        dropdown.querySelectorAll(".dropdown-item").forEach((x, j) =>
          x.classList.toggle("focus", j === state.focusIdx)
        );
      });
    });
  }

  input.addEventListener("focus", () => renderDropdown(state.commands, 0));
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    const items = q
      ? state.commands.filter(
          (c) =>
            c.key.includes(q) ||
            c.label.toLowerCase().includes(q) ||
            c.one_liner.toLowerCase().includes(q)
        )
      : state.commands;
    renderDropdown(items, 0);
  });

  input.addEventListener("keydown", (e) => {
    if (!state.filtered.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      state.focusIdx = (state.focusIdx + 1) % state.filtered.length;
      renderDropdown(state.filtered, state.focusIdx);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      state.focusIdx = (state.focusIdx - 1 + state.filtered.length) % state.filtered.length;
      renderDropdown(state.filtered, state.focusIdx);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const chosen = state.filtered[state.focusIdx];
      if (chosen) openConfirm(chosen.key);
    } else if (e.key === "Escape") {
      dropdown.hidden = true;
      input.blur();
    }
  });

  document.addEventListener("click", (e) => {
    if (!$("searchWrap").contains(e.target)) dropdown.hidden = true;
  });

  goBtn.addEventListener("click", () => {
    const chosen = state.filtered[state.focusIdx] || state.commands[0];
    if (chosen) openConfirm(chosen.key);
  });
}

// ---------- Confirm modal ----------
function bindModal() {
  $("cancelConfirm").addEventListener("click", closeConfirm);
  $("startAudit").addEventListener("click", startAudit);
  $("urlInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") startAudit();
    if (e.key === "Escape") closeConfirm();
  });
}

function openConfirm(cmdKey) {
  const cmd = state.commands.find((c) => c.key === cmdKey);
  if (!cmd) return;
  state.selectedCmd = cmd;
  $("confirmCmd").textContent = `/seo ${cmd.key}`;
  $("urlInput").value = "";
  $("urlHint").textContent = cmd.one_liner;
  const checklist = $("checklist");
  const agentList = (cmd.agents || []).slice(0, 8);
  checklist.innerHTML = agentList
    .map((a) => `<li>${a}</li>`)
    .concat(["<li>Generate PDF report + Action Plan</li>"])
    .join("");
  $("confirmModal").hidden = false;
  setTimeout(() => $("urlInput").focus(), 80);
}

function closeConfirm() {
  $("confirmModal").hidden = true;
}

// ---------- Start audit + SSE stream ----------
async function startAudit() {
  let url = $("urlInput").value.trim();
  if (!url) {
    $("urlHint").textContent = "Please enter a URL.";
    $("urlInput").focus();
    return;
  }
  if (!/^https?:\/\//.test(url)) url = "https://" + url;
  closeConfirm();

  resetAgents();
  $("runUrl").textContent = url;
  $("runCmdLabel").textContent = `/seo ${state.selectedCmd.key} — ${state.selectedCmd.label}`;
  $("eventList").innerHTML = "";
  $("runSummary").hidden = true;
  $("stopBtn").disabled = false;
  $("closeRun").hidden = true;
  $("runPanel").hidden = false;

  try {
    const r = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, command: state.selectedCmd.key }),
    });
    if (!r.ok) throw new Error(`POST /api/audit ${r.status}`);
    const { job_id } = await r.json();
    state.jobId = job_id;
    openStream(job_id);
  } catch (e) {
    appendEvent({ agent: "orchestrator", status: "error", msg: e.message });
  }
}

function openStream(jobId) {
  if (state.eventSource) state.eventSource.close();
  const es = new EventSource(`/api/jobs/${jobId}/stream`);
  state.eventSource = es;
  es.onmessage = (m) => {
    if (!m.data) return;
    let ev;
    try {
      ev = JSON.parse(m.data);
    } catch {
      return;
    }
    if (ev._terminal) {
      es.close();
      state.eventSource = null;
      onTerminal(ev.status);
      return;
    }
    appendEvent(ev);
    handleAgentStatus(ev);
  };
  es.onerror = () => {
    appendEvent({
      agent: "orchestrator",
      status: "warn",
      msg: "stream interrupted — will retry"
    });
  };
}

function appendEvent(ev) {
  const ul = $("eventList");
  const li = document.createElement("li");
  li.innerHTML = `
    <span class="evt-status ${ev.status || ""}"></span>
    <span class="evt-agent">${ev.agent || "—"}</span>
    <span class="evt-msg">${escapeHtml(ev.msg || "")}</span>
  `;
  ul.appendChild(li);
  ul.scrollTop = ul.scrollHeight;
}

function handleAgentStatus(ev) {
  if (!ev.agent) return;
  setAgentStatus(ev.agent, ev.status);
  if (ev.status === "start") setActiveAgents([ev.agent]);
}

async function onTerminal(status) {
  $("stopBtn").disabled = true;
  $("closeRun").hidden = false;
  if (status === "done" && state.jobId) {
    try {
      const summary = await fetch(`/api/jobs/${state.jobId}/summary`).then((r) => r.json());
      renderSummary(summary);
    } catch {}
  } else if (status === "cancelled") {
    appendEvent({ agent: "orchestrator", status: "warn", msg: "Audit cancelled by user." });
  } else {
    appendEvent({ agent: "orchestrator", status: "error", msg: `Job ended: ${status}` });
  }
}

function renderSummary(summary) {
  if (!summary || typeof summary.overall === "undefined") return;
  $("scoreValue").textContent = summary.overall;
  const cats = summary.scores || {};
  const weights = summary.weights || {};
  const order = [
    ["technical", "Technical"],
    ["content", "Content"],
    ["onpage", "On-Page"],
    ["schema", "Schema"],
    ["performance", "Performance"],
    ["ai_readiness", "AI Readiness"],
    ["images", "Images"],
  ];
  const grid = $("catGrid");
  grid.innerHTML = order
    .map(([k, label]) => {
      const v = cats[k];
      const w = weights[k] || 0;
      if (v < 0 || v === undefined) {
        return `
        <div class="cat-row">
          <div class="cat-name">${label} <span style="opacity:0.5">(${w}%)</span></div>
          <div class="cat-score na">not measured</div>
        </div>`;
      }
      const color =
        v >= 80 ? "var(--success)" : v >= 50 ? "var(--accent)" : "var(--fail)";
      return `
      <div class="cat-row">
        <div class="cat-name">${label} <span style="opacity:0.5">(${w}%)</span></div>
        <div class="cat-score">${v}<span style="font-size:11px;color:var(--text-muted);font-weight:500;"> /100</span></div>
        <div class="cat-bar"><div class="cat-bar-fill" style="width:${v}%;background:${color}"></div></div>
      </div>`;
    })
    .join("");

  $("downloadPdf").href = `/api/jobs/${state.jobId}/report.pdf`;
  $("downloadMd").href = `/api/jobs/${state.jobId}/report.md`;
  $("runSummary").hidden = false;
}

// ---------- Run panel ----------
function bindRunPanel() {
  $("stopBtn").addEventListener("click", async () => {
    if (!state.jobId) return;
    $("stopBtn").disabled = true;
    try {
      await fetch(`/api/jobs/${state.jobId}/stop`, { method: "POST" });
      appendEvent({ agent: "orchestrator", status: "warn", msg: "Stop signal sent..." });
    } catch (e) {
      appendEvent({ agent: "orchestrator", status: "error", msg: e.message });
    }
  });
  $("closeRun").addEventListener("click", () => {
    $("runPanel").hidden = true;
    if (state.eventSource) state.eventSource.close();
    state.eventSource = null;
    state.jobId = null;
    resetAgents();
  });
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

init();
