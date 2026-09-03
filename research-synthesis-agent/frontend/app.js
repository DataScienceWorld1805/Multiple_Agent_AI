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
let lastReport = null;

const STAGE_HINTS = [
  "Elaborando el plan de investigación…",
  "Consultando fuentes web, literatura y base interna…",
  "Sintetizando hallazgos y construyendo citas…",
];

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) throw new Error("health failed");
    const data = await res.json();
    configHint.textContent = `Entorno · modelo ${data.llm_provider}/${data.llm_model} · búsqueda ${data.search_provider} · papers ${data.papers_provider}`;
  } catch {
    configHint.textContent =
      "Servicio no disponible. Ejecute: python -m src.api";
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

function stripMarkdownLite(text) {
  return String(text || "")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/\*(.*?)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[(\d+)\]/g, "[$1]")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

function renderReport(job) {
  const report = job.report;
  if (!report) return;

  lastMarkdown = report.markdown || "";
  lastReport = report;
  document.getElementById("report-query").textContent = report.query || job.query;
  document.getElementById("executive-summary").innerHTML = linkCitations(
    report.executive_summary || ""
  );

  const sectionsRoot = document.getElementById("sections");
  sectionsRoot.innerHTML = (report.sections || [])
    .map(
      (section, index) => `
      <article class="section-item">
        <p class="section-meta">Subpregunta ${escapeHtml(section.subquestion_id || String(index + 1))}</p>
        <h4>${escapeHtml(section.title || "")}</h4>
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
      return `<li id="cite-${cite.number}">[${cite.number}] ${url}<span class="source-tag">${type}</span></li>`;
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
            <div class="section-meta">Fuentes asignadas: ${(sq.assigned_sources || []).map(escapeHtml).join(", ")}</div>
          </li>`
          )
          .join("")}
      </ul>`;
  } else {
    planView.innerHTML = "<p class='section-meta'>Plan no disponible.</p>";
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
            ${escapeHtml(r.subquestion_id)} · estado ${escapeHtml(r.status)} ·
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

function exportReportPdf(report) {
  const jspdfNS = window.jspdf;
  if (!jspdfNS || !jspdfNS.jsPDF) {
    throw new Error("No se pudo cargar jsPDF. Revisa la conexión e inténtalo de nuevo.");
  }

  const doc = new jspdfNS.jsPDF({
    unit: "mm",
    format: "a4",
    orientation: "portrait",
  });

  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const marginX = 18;
  const marginTop = 18;
  const marginBottom = 18;
  const maxWidth = pageWidth - marginX * 2;
  let y = marginTop;

  const ensureSpace = (needed) => {
    if (y + needed <= pageHeight - marginBottom) return;
    doc.addPage();
    y = marginTop;
  };

  const writeParagraph = (text, options = {}) => {
    const {
      size = 11,
      style = "normal",
      color = [20, 20, 20],
      lineHeight = 6,
      gapAfter = 3,
      indent = 0,
    } = options;
    const clean = stripMarkdownLite(text);
    if (!clean) return;

    doc.setFont("helvetica", style);
    doc.setFontSize(size);
    doc.setTextColor(color[0], color[1], color[2]);
    const lines = doc.splitTextToSize(clean, maxWidth - indent);
    for (const line of lines) {
      ensureSpace(lineHeight);
      doc.text(line, marginX + indent, y);
      y += lineHeight;
    }
    y += gapAfter;
  };

  const writeHeading = (text, level = 1) => {
    const sizes = { 1: 18, 2: 14, 3: 12 };
    const gaps = { 1: 5, 2: 4, 3: 3 };
    ensureSpace(sizes[level] * 0.5 + 8);
    if (level > 1 && y > marginTop + 2) y += 2;
    writeParagraph(text, {
      size: sizes[level] || 12,
      style: "bold",
      color: [15, 15, 15],
      lineHeight: level === 1 ? 8 : 7,
      gapAfter: gaps[level] || 3,
    });
  };

  writeHeading("Informe de síntesis", 1);
  writeParagraph(report.query || lastQuery || "Consulta", {
    size: 12,
    style: "bold",
    color: [30, 30, 30],
    lineHeight: 6.5,
    gapAfter: 6,
  });

  writeHeading("1. Resumen ejecutivo", 2);
  writeParagraph(report.executive_summary || "Sin resumen.");

  writeHeading("2. Hallazgos", 2);
  const sections = report.sections || [];
  if (!sections.length) {
    writeParagraph("No hay secciones disponibles.");
  } else {
    sections.forEach((section, index) => {
      writeHeading(`${index + 1}. ${section.title || "Sección"}`, 3);
      if (section.subquestion_id) {
        writeParagraph(`Subpregunta: ${section.subquestion_id}`, {
          size: 9,
          color: [80, 80, 80],
          lineHeight: 5,
          gapAfter: 2,
        });
      }
      writeParagraph(section.content || "");
    });
  }

  const contradictions = report.contradictions || [];
  if (contradictions.length) {
    writeHeading("3. Contradicciones", 2);
    contradictions.forEach((item) => {
      writeParagraph(`${item.topic || "Tema"}: ${item.description || ""}`, {
        indent: 2,
      });
    });
  }

  const limitations = report.limitations || [];
  if (limitations.length) {
    writeHeading(contradictions.length ? "4. Limitaciones" : "3. Limitaciones", 2);
    limitations.forEach((item) => {
      writeParagraph(`• ${item}`, { indent: 1, gapAfter: 2 });
    });
  }

  const citations = report.citations || [];
  if (citations.length) {
    const n =
      2 +
      (contradictions.length ? 1 : 0) +
      (limitations.length ? 1 : 0) +
      1;
    writeHeading(`${n}. Referencias`, 2);
    citations.forEach((cite) => {
      const type = cite.source_type ? ` (${cite.source_type})` : "";
      const url = cite.url ? ` — ${cite.url}` : "";
      writeParagraph(`[${cite.number}] ${cite.title || "Sin título"}${type}${url}`, {
        size: 9.5,
        lineHeight: 5,
        gapAfter: 2.5,
        indent: 1,
      });
    });
  }

  const total = doc.getNumberOfPages();
  for (let i = 1; i <= total; i += 1) {
    doc.setPage(i);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(110, 110, 110);
    doc.text(`Página ${i} de ${total}`, pageWidth / 2, pageHeight - 8, {
      align: "center",
    });
  }

  doc.save("research-report.pdf");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryEl.value.trim();
  if (query.length < 3) return;

  lastQuery = query;
  hidePanels();
  setBusy(true);
  statusPanel.hidden = false;
  statusLabel.textContent = "Consulta en cola";
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
    statusLabel.textContent = "Investigación en curso";
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

document.getElementById("download-pdf").addEventListener("click", () => {
  if (!lastReport) return;
  const pdfBtn = document.getElementById("download-pdf");
  pdfBtn.disabled = true;
  try {
    exportReportPdf(lastReport);
  } catch (err) {
    showError(err.message || String(err));
    errorPanel.hidden = false;
  } finally {
    pdfBtn.disabled = false;
  }
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
