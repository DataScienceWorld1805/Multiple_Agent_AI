const form = document.getElementById("research-form");
const queryEl = document.getElementById("query");
const submitBtn = document.getElementById("submit-btn");
const statusPanel = document.getElementById("status-panel");
const statusLabel = document.getElementById("status-label");
const statusMeta = document.getElementById("status-meta");
const reportEl = document.getElementById("report");
const errorPanel = document.getElementById("error-panel");
const errorMessage = document.getElementById("error-message");
const configHint = document.getElementById("config-hint");

let pollTimer = null;
let lastMarkdown = "";
let lastQuery = "";

const STAGE_HINTS = [
  "El orquestador descompone la pregunta…",
  "Workers consultan web, papers y KB…",
  "El sintetizador arma el informe citado…",
];

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error("health failed");
    const data = await res.json();
    configHint.textContent = `LLM: ${data.llm_provider} · ${data.llm_model} · search: ${data.search_provider} · papers: ${data.papers_provider}`;
  } catch {
    configHint.textContent = "API no disponible. Arranca con: python -m src.api";
  }
}

function setBusy(busy) {
  submitBtn.disabled = busy;
  queryEl.disabled = busy;
}

function hidePanels() {
  reportEl.hidden = true;
  errorPanel.hidden = true;
  statusPanel.hidden = true;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function linkCitations(text) {
  const safe = escapeHtml(text);
  return safe.replace(/\[(\d+)\]/g, '<a class="citation-link" href="#cite-$1">[$1]</a>');
}

function renderReport(job) {
  const report = job.report;
  if (!report) return;

  lastMarkdown = report.markdown || "";
  document.getElementById("report-query").textContent = report.query || job.query;
  document.getElementById("executive-summary").innerHTML = linkCitations(
    report.executive_summary || ""
  );

  const sectionsRoot = document.getElementById("sections");
  sectionsRoot.innerHTML = (report.sections || [])
    .map(
      (section) => `
      <article class="section-item">
        <p class="section-meta">${escapeHtml(section.subquestion_id || "")}</p>
        <h3>${escapeHtml(section.title || "")}</h3>
        <p>${linkCitations(section.content || "")}</p>
      </article>`
    )
    .join("");

  const contradictions = report.contradictions || [];
  const contradictionsBlock = document.getElementById("contradictions-block");
  contradictionsBlock.hidden = contradictions.length === 0;
  document.getElementById("contradictions").innerHTML = contradictions
    .map(
      (item) =>
        `<li><strong>${escapeHtml(item.topic)}</strong> — ${escapeHtml(item.description)}</li>`
    )
    .join("");

  const limitations = report.limitations || [];
  const limitationsBlock = document.getElementById("limitations-block");
  limitationsBlock.hidden = limitations.length === 0;
  document.getElementById("limitations").innerHTML = limitations
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");

  const citations = report.citations || [];
  const citationsBlock = document.getElementById("citations-block");
  citationsBlock.hidden = citations.length === 0;
  document.getElementById("citations").innerHTML = citations
    .map((cite) => {
      const title = escapeHtml(cite.title || "Sin título");
      const type = escapeHtml(cite.source_type || "");
      const url = cite.url
        ? `<a class="citation-link" href="${escapeHtml(cite.url)}" target="_blank" rel="noopener noreferrer">${title}</a>`
        : title;
      return `<li id="cite-${cite.number}">[${cite.number}] ${url} <span class="badge">${type}</span></li>`;
    })
    .join("");

  const planView = document.getElementById("plan-view");
  if (job.plan?.subquestions?.length) {
    planView.innerHTML = `
      <ul class="plan-list">
        ${job.plan.subquestions
          .map(
            (sq) => `
          <li>
            <span class="badge">${escapeHtml(sq.id)}</span>
            ${escapeHtml(sq.question)}
            <div class="section-meta">Fuentes: ${(sq.assigned_sources || []).map(escapeHtml).join(", ")}</div>
          </li>`
          )
          .join("")}
      </ul>`;
  } else {
    planView.innerHTML = "<p class='section-meta'>Sin plan disponible.</p>";
  }

  const resultsView = document.getElementById("results-view");
  if (job.results_summary?.length) {
    resultsView.innerHTML = `
      <ul class="worker-list">
        ${job.results_summary
          .map(
            (r) => `
          <li>
            <span class="badge">${escapeHtml(r.researcher_type)}</span>
            ${escapeHtml(r.subquestion_id)} · ${escapeHtml(r.status)} ·
            ${r.findings_count} hallazgos · ${Math.round(r.duration_ms)} ms
            ${r.error_message ? `<div class="section-meta">${escapeHtml(r.error_message)}</div>` : ""}
          </li>`
          )
          .join("")}
      </ul>`;
  } else {
    resultsView.innerHTML = "";
  }

  reportEl.hidden = false;
  reportEl.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showError(message) {
  errorMessage.textContent = message || "Error desconocido";
  errorPanel.hidden = false;
  errorPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function pollJob(jobId) {
  let hintIndex = 0;
  const hintTimer = setInterval(() => {
    hintIndex = (hintIndex + 1) % STAGE_HINTS.length;
    if (!statusPanel.hidden) {
      statusMeta.textContent = STAGE_HINTS[hintIndex];
    }
  }, 4500);

  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/research/${jobId}`);
      if (!res.ok) throw new Error(`Estado ${res.status}`);
      const job = await res.json();
      statusLabel.textContent = job.stage || job.status;
      if (job.status === "done") {
        clearInterval(hintTimer);
        stopPolling();
        setBusy(false);
        statusPanel.hidden = true;
        renderReport(job);
      } else if (job.status === "failed") {
        clearInterval(hintTimer);
        stopPolling();
        setBusy(false);
        statusPanel.hidden = true;
        showError(job.error || "La investigación falló.");
      }
    } catch (err) {
      clearInterval(hintTimer);
      stopPolling();
      setBusy(false);
      statusPanel.hidden = true;
      showError(err.message || String(err));
    }
  }, 1500);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryEl.value.trim();
  if (query.length < 3) return;

  lastQuery = query;
  hidePanels();
  setBusy(true);
  statusPanel.hidden = false;
  statusLabel.textContent = "En cola…";
  statusMeta.textContent = STAGE_HINTS[0];

  try {
    const res = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `Error ${res.status}`);
    }
    const data = await res.json();
    statusLabel.textContent = "Investigando…";
    await pollJob(data.job_id);
  } catch (err) {
    setBusy(false);
    statusPanel.hidden = true;
    showError(err.message || String(err));
  }
});

document.getElementById("download-md").addEventListener("click", () => {
  if (!lastMarkdown) return;
  const blob = new Blob([lastMarkdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "research-report.md";
  a.click();
  URL.revokeObjectURL(url);
});

document.getElementById("new-research").addEventListener("click", () => {
  hidePanels();
  queryEl.focus();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

document.getElementById("retry-btn").addEventListener("click", () => {
  if (lastQuery) queryEl.value = lastQuery;
  hidePanels();
  form.requestSubmit();
});

loadHealth();
