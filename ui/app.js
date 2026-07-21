const demo = {
  config: "albaz",
  provenance: { complete: true, search_limits: { max_nodes: 20000, max_depth: 180 }, database_sha256: "demo", scripts_revision: "demo" },
  reports: {
    none: { summary: { weighted_score: 10.4, weighted_categories: { board_value: 7.2, interaction_value: 1.5, follow_up_value: 1.7, survival_value: 0 }, complete_fraction: 1 }, hands: [{ hand: [73819701, 55273560, 95515789, 91152256, 91152256], score: 10.4, complete: true, categories: { board_value: 7.2, interaction_value: 1.5, follow_up_value: 1.7, survival_value: 0, total_score: 10.4 }, endboard: { monster: [73819701, 44146295], spell_trap: [17751597], hand: [55273560], grave: [] }, probability: 1 }] },
    ash: { summary: { weighted_score: 7.8, weighted_score_loss: 2.6, complete_fraction: 1 }, hands: [{ hand: [73819701, 55273560, 95515789, 91152256, 91152256], score: 7.8, baseline_score: 10.4, score_loss: 2.6, complete: true, categories: { board_value: 5.2, interaction_value: 1, follow_up_value: 1.6, survival_value: 0, total_score: 7.8 }, category_deltas: { board_value: 2, interaction_value: .5, follow_up_value: .1, survival_value: 0 }, endboard: { monster: [73819701], spell_trap: [], hand: [55273560, 95515789], grave: [] }, probability: 1 }] }
  }
};

let report = demo;
let cardNames = {};
const $ = (id) => document.getElementById(id);
const fmt = (value) => typeof value === "number" ? value.toFixed(2) : "—";
const formatCards = (hand) => hand.map((card) => `<span class="tag" title="${card}">${cardNames[card] || card}</span>`).join("");

function scenarios() { return Object.entries(report.reports || {}); }
function rows() {
  const byHand = new Map();
  scenarios().forEach(([name, data]) => (data.hands || []).forEach((row) => {
    const key = JSON.stringify(row.hand);
    if (!byHand.has(key)) byHand.set(key, { hand: row.hand, scenarios: {} });
    byHand.get(key).scenarios[name] = row;
  }));
  return [...byHand.values()];
}
function renderSummary() {
  $("deck-name").textContent = report.config || "Resilience report";
  const p = report.provenance || {};
  $("provenance").textContent = `${p.complete ? "complete" : "provisional"} · ${p.database_sha256 || "no checksum"} · ${p.scripts_revision || "no script revision"}`;
  $("scenario-summary").innerHTML = scenarios().map(([name, data]) => `<article class="scenario-card"><span class="label">${name === "none" ? "NO INTERRUPTION" : name.toUpperCase()}</span><strong>${fmt(data.summary?.weighted_score)}</strong><small>${data.summary?.weighted_score_loss == null ? "ceiling" : `−${fmt(data.summary.weighted_score_loss)} score loss`}</small></article>`).join("");
}
function renderHands(selected = 0) {
  const list = rows(); $("hand-count").textContent = list.length;
  $("hand-list").innerHTML = list.map((item, index) => `<button class="hand-button ${index === selected ? "active" : ""}" data-index="${index}"><em>${fmt(item.scenarios.none?.score)}</em><strong>Hand ${index + 1}</strong><span>${formatCards(item.hand)}</span></button>`).join("");
  document.querySelectorAll(".hand-button").forEach((button) => button.addEventListener("click", () => { renderHands(Number(button.dataset.index)); renderDetail(Number(button.dataset.index)); }));
}
function metric(label, value) { return `<div class="metric"><label>${label}</label><strong>${fmt(value)}</strong></div>`; }
function renderDetail(index = 0) {
  const item = rows()[index]; if (!item) return;
  $("selected-hand").innerHTML = formatCards(item.hand); const baseline = item.scenarios.none; $("selected-status").textContent = baseline?.complete ? "complete" : "provisional";
  const categories = baseline?.categories || {}; $("metric-grid").innerHTML = metric("CEILING", baseline?.score) + metric("BOARD", categories.board_value) + metric("INTERACTION", categories.interaction_value) + metric("FOLLOW-UP", categories.follow_up_value);
  $("scenario-detail").innerHTML = Object.entries(item.scenarios).map(([name, row]) => { const loss = row.score_loss; const c = row.categories || {}; const total = c.total_score || row.score || 1; return `<article class="scenario-row"><div class="scenario-title"><strong>${name === "none" ? "Uninterrupted ceiling" : name}</strong><span class="${loss > 0 ? "loss" : "safe"}">${loss > 0 ? `−${fmt(loss)}` : fmt(row.score)}</span></div><div class="bar"><i class="board" style="width:${(c.board_value / total) * 100}%"></i><i class="interaction" style="width:${(c.interaction_value / total) * 100}%"></i><i class="followup" style="width:${(c.follow_up_value / total) * 100}%"></i><i class="survival" style="width:${(c.survival_value / total) * 100}%"></i></div><small>Score ${fmt(row.score)} · board ${fmt(c.board_value)} · interaction ${fmt(c.interaction_value)} · follow-up ${fmt(c.follow_up_value)}</small></article>`; }).join("");
  const row = item.scenarios.none || Object.values(item.scenarios)[0];
  const endboard = row?.endboard || {};
  const zones = Object.entries(endboard).filter(([, zoneCards]) => Array.isArray(zoneCards) && zoneCards.length).map(([zone, zoneCards]) => `<p><strong>${zone}</strong><br>${formatCards(zoneCards)}</p>`).join("") || `<p>No endboard data in this report.</p>`;
  const history = row?.actions || row?.action_history || row?.observation?.action_history || [];
  const timeline = history.length ? history.map((action, step) => `<span class="step">${step + 1}. ${action}</span>`).join("") : `<p>No action timeline in this report. Generate a trace-enriched report to inspect steps.</p>`;
  const extenders = Object.entries(row?.extender_marginals || {}).map(([card, value]) => `<div class="extender"><span>Card ${card}</span><strong>+${fmt(value.score_delta)}</strong></div>`).join("") || `<p>No extender counterfactuals in this report.</p>`;
  $("state-detail").innerHTML = `<article class="state-card"><h3>END BOARD / STATE</h3>${zones}</article><article class="state-card"><h3>ACTION TIMELINE</h3><div class="timeline">${timeline}</div></article><article class="state-card"><h3>EXTENDER MARGINAL VALUE</h3>${extenders}</article>`;
}
async function resolveCardNames() {
  const ids = new Set();
  rows().forEach((item) => { item.hand.forEach((card) => ids.add(card)); Object.values(item.scenarios).forEach((scenario) => Object.values(scenario.endboard || {}).flat().forEach((card) => ids.add(card))); });
  if (!ids.size) return;
  try { const response = await fetch(`/api/card-names?ids=${[...ids].join("&ids=")}`); if (response.ok) cardNames = { ...cardNames, ...(await response.json()) }; } catch (_) { /* static file mode: IDs remain available */ }
}
async function render() { await resolveCardNames(); renderSummary(); renderHands(0); renderDetail(0); }
$("report-input").addEventListener("change", (event) => { const file = event.target.files[0]; if (!file) return; const reader = new FileReader(); reader.onload = () => { try { report = JSON.parse(reader.result); $("status").textContent = `Loaded ${file.name}`; render(); } catch { $("status").textContent = "Could not parse report"; } }; reader.readAsText(file); });
$("run-button").addEventListener("click", async () => {
  const button = $("run-button"); button.disabled = true; $("status").textContent = "Running bounded exact analysis…";
  try {
    const response = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
      interruption: $("run-interruption").value, hands: Number($("run-hands").value), max_nodes: Number($("run-nodes").value), max_depth: Number($("run-depth").value), extenders: $("run-extenders").checked
    }) });
    const payload = await response.json(); if (!response.ok) throw new Error(payload.error || "analysis failed");
    report = payload; $("status").textContent = "Fresh report loaded"; render();
  } catch (error) { $("status").textContent = error.message; } finally { button.disabled = false; }
});
render();
