"use strict";
// open-foresight UI prototype. Reads the repo's JSON; computes nothing about the model.
// Level -> data mapping is a judgment and lives in regions.json.

const FILES = {
  weltlage: "../radar/snapshot/weltlage.json",
  wissen: "../radar/snapshot/wissensstand.json",
  briefing: "../domains/energy-transition/briefing.json",
  domain: "../domains/energy-transition/domain.json",
  regions: "regions.json",
  labels: "labels.en.json",
  params: "parameters.json",
  regional: "../radar/regional/regional.json",
  demo: "demo/future.json",
};
const REGIME_NAMES = {"-2": "much cheaper", "-1": "cheaper", "0": "neutral", "1": "more expensive", "2": "much more expensive"};
const COVERAGE = {full: "full data", proxy: "proxy data", gap: "GAP: no data"};

const S = {level: "germany", horizon: "2028", D: null, prov: [], open: new Set(), param: "auto", pal: "rg", when: "current"};
const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmt = (v, d = 1) => (v == null || Number.isNaN(Number(v)) ? "n/a" : Number(v).toLocaleString("en", {maximumFractionDigits: d}));

function tag(kind, file) {
  const text = {measured: "Measured", model: "Model output", judgment: "Judgment", gap: "GAP", inherited: "Inherited", illustrative: "Illustrative"}[kind];
  S.prov.push({kind: text, file});
  return `<span class="tag ${kind}" title="${esc(file)}">${text}</span>`;
}

async function load() {
  const out = {};
  await Promise.all(Object.entries(FILES).map(async ([k, url]) => {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    out[k] = await r.json();
  }));
  const geoFiles = {world: "geo/world.json", europe: "geo/europe.json", de: "geo/de_states.json"};
  out.geo = {};
  await Promise.all(Object.entries(geoFiles).map(async ([k, url]) => {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    out.geo[k] = await r.json();
  }));
  out.series = Object.fromEntries(out.wissen.reihen.map((r) => [r.id, r]));
  out.ind = Object.fromEntries(out.briefing.indicators.map((i) => [i.id, i]));
  out.drv = Object.fromEntries(out.briefing.drivers.map((d) => [d.id, d]));
  out.lv = Object.fromEntries(out.regions.levels.map((l) => [l.id, l]));
  return out;
}

// ---------- header and navigation ----------
function renderHeader() {
  const D = S.D, b = D.briefing;
  $("#question").textContent = b.domain.question;
  $("#stamp").textContent = `World model v${b.inputs.version} (${b.inputs.model_date}) · world state ${b.inputs.world_state_date} · radar ${b.inputs.radar_date}`;
  const chain = [];
  const order = ["global", "europe", "germany", "brandenburg", "berlin"];
  order.forEach((id, i) => {
    const l = D.lv[id];
    if (i) chain.push('<span class="sep" aria-hidden="true">▸</span>');
    chain.push(`<button class="crumb" type="button" data-level="${id}" aria-current="${id === S.level}">${esc(l.name)}<span class="cov">${COVERAGE[l.coverage]}</span></button>`);
  });
  $("#scale").innerHTML = chain.join("");
}

// ---------- charts ----------
function sparkline(points, unit) {
  const W = 300, H = 96, P = {l: 6, r: 6, t: 8, b: 16};
  const vals = points.map((p) => p.wert);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.1; lo -= pad; hi += pad;
  const x = (i) => P.l + (i * (W - P.l - P.r)) / Math.max(points.length - 1, 1);
  const y = (v) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.wert).toFixed(1)}`).join(" ");
  const last = points.length - 1;
  const hits = points.map((p, i) => {
    const w = (W - P.l - P.r) / Math.max(points.length - 1, 1);
    return `<rect class="hit" x="${(x(i) - w / 2).toFixed(1)}" y="0" width="${w.toFixed(1)}" height="${H}" data-i="${i}"></rect>`;
  }).join("");
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="Line chart of ${points.length} monthly values, from ${esc(points[0].t)} to ${esc(points[last].t)}" data-unit="${esc(unit)}" data-pts='${esc(JSON.stringify(points))}'>
    <line class="gl" x1="${P.l}" x2="${W - P.r}" y1="${H - P.b}" y2="${H - P.b}"/>
    <path class="ln" d="${d}"/>
    <circle class="dot" cx="${x(last).toFixed(1)}" cy="${y(points[last].wert).toFixed(1)}" r="4"/>
    <text x="${P.l}" y="${H - 3}">${esc(points[0].t)}</text>
    <text x="${W - P.r}" y="${H - 3}" text-anchor="end">${esc(points[last].t)}</text>
    <line class="cross" x1="0" x2="0" y1="${P.t}" y2="${H - P.b}" visibility="hidden"/>
    ${hits}</svg>`;
}

function seriesCard(id) {
  const D = S.D, r = D.series[id];
  if (!r) return `<div class="card"><h3>${esc(id)}</h3><div class="callout"><b>GAP</b> series not in the radar snapshot.</div></div>`;
  const label = D.labels.series[id] || r.titel;
  const pts = r.punkte;
  const last = pts[pts.length - 1];
  const rows = pts.map((p) => `<tr><td>${esc(p.t)}</td><td>${fmt(p.wert, 2)}</td></tr>`).join("");
  return `<div class="card">
    <div class="sc-head"><h3>${esc(label)}</h3>${tag("measured", `radar/snapshot/wissensstand.json (${id})`)}</div>
    <div class="big">${fmt(last.wert, 2)} <span class="muted" style="font-size:.8rem;font-weight:400">${esc(r.einheit)} · ${esc(last.t)}</span></div>
    ${sparkline(pts, r.einheit)}
    <details><summary>Table view</summary><table><thead><tr><th>Month</th><th>${esc(r.einheit)}</th></tr></thead><tbody>${rows}</tbody></table></details>
    <p class="kv">Source: <a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.quelleName)}</a></p></div>`;
}

// ---------- sections ----------
function introCard(l) {
  const gap = l.coverage === "gap";
  return `<section class="card intro ${gap ? "gap" : ""}">
    <div class="card-head"><h2>${esc(l.name)}</h2>${tag(gap ? "gap" : "judgment", gap ? "ui/regions.json" : "ui/regions.json (level mapping)")}</div>
    <p style="margin:0">${esc(l.blurb)}</p></section>`;
}

function scenariosCard(l) {
  const rows = S.D.briefing.scenarios.rows.slice().sort((a, b) => b.p_today[S.horizon] - a.p_today[S.horizon]);
  const max = Math.max(...rows.map((r) => Math.max(r.p_base[S.horizon], r.p_today[S.horizon])), 1);
  const hl = new Set(l.highlight_scenarios);
  const bars = rows.map((r) => {
    const b = r.p_base[S.horizon], t = r.p_today[S.horizon];
    const open = S.open.has(r.id);
    const detail = open ? `<div class="sc-detail"><div>${esc(r.short)}</div>
        <div class="regime">${Object.entries(r.regime).map(([k, v]) => `<span>${esc(k.replace(/_/g, " "))} ${v > 0 ? "+" : ""}${v}</span>`).join("")}</div>
        <table><thead><tr><th>Horizon</th><th>Base</th><th>Today</th></tr></thead><tbody>${["2028", "2032", "2040"].map((h) => `<tr><td>${h}</td><td>${r.p_base[h]}%</td><td>${r.p_today[h]}%</td></tr>`).join("")}</tbody></table>
        <p class="kv">Energy price: -2 much cheaper to +2 much more expensive. These two regime values are the ones the energy lens uses.</p></div>` : "";
    return `<div class="bar-row sc ${hl.has(r.id) ? "hl" : ""}" data-sc="${esc(r.id)}" role="button" tabindex="0" aria-expanded="${open}" title="${esc(r.id)}: base ${b}%, today ${t}%. Click for details.">
      <div class="bar-name">${esc(r.name)}<small>${esc(r.id)} · energy price ${REGIME_NAMES[r.regime.energy_price] ?? r.regime.energy_price}</small></div>
      <div class="bar-track"><i class="b" style="width:${(b / max) * 100}%"></i><i class="t" style="width:${(t / max) * 100}%"></i></div>
      <div class="bar-val">${b}% → ${t}%</div></div>${detail}`;
  }).join("");
  const mass = S.D.briefing.scenarios.energy_price_mass[S.horizon];
  const massCells = ["much cheaper", "cheaper", "neutral", "more expensive", "much more expensive"]
    .map((k) => `<div><b>${fmt(mass[k], 0)}%</b>${esc(k)}</div>`).join("");
  const horizons = ["2028", "2032", "2040"].map((h) => `<button type="button" data-h="${h}" aria-pressed="${h === S.horizon}">${h}</button>`).join("");
  return `<section class="card">
    <div class="card-head"><div><h2>World scenarios</h2><span class="muted">Probability by horizon, base model → today (after early-warning signals)</span></div>
      <div style="display:flex;gap:8px;align-items:center">${tag("model", "domains/energy-transition/briefing.json")}<div class="seg" role="group" aria-label="Horizon">${horizons}</div></div></div>
    <p class="legend"><span>Base model</span><span class="t">Today</span></p>
    <div class="bars">${bars}</div>
    <h3 style="margin-top:14px">Probability by energy-price regime, ${S.horizon}</h3>
    <div class="mass">${massCells}</div>
    ${l.id === "global" || l.id === "europe" ? '<p class="kv">The scenarios are global. This level does not change them.</p>' : ""}
    </section>`;
}

function driversCard(l) {
  const items = l.drivers.map((id) => S.D.drv[id]).filter(Boolean);
  if (!items.length) return "";
  const li = items.map((d) => `<li><strong>${esc(d.name)}</strong> <span class="kv">${esc(d.id)} · ${esc(d.type)}</span>
    <div>${esc(d.status_2026 || "")}</div></li>`).join("");
  return `<section class="card"><div class="card-head"><h2>Drivers that matter here</h2>${tag("judgment", "domains/energy-transition/domain.json (world_links)")}</div>
    <ul class="list">${li}</ul></section>`;
}

function indicatorsCard(l) {
  const items = l.indicators.map((id) => S.D.ind[id]).filter(Boolean);
  if (!items.length) return "";
  const li = items.map((i) => {
    const on = i.active_today;
    const changed = i.active_today !== i.active_at_base;
    const lat = i.latest ? `${fmt(i.latest.wert, 2)} (${esc(i.latest.t)})` : "n/a";
    return `<li><span class="chip ${on ? "on" : "off"}">${on ? "▲ active today" : "○ not active"}</span>
      ${changed ? '<span class="chip on">changed since base</span>' : ""}
      <strong>${esc(i.text)}</strong>
      <div class="kv">${esc(i.id)} · series ${esc(i.series)} · latest ${lat} · rule <code>${esc(i.rule)}</code></div></li>`;
  }).join("");
  return `<section class="card"><div class="card-head"><div><h2>Early-warning indicators</h2><span class="muted">Testable rules on data series. A status change moves scenario probabilities.</span></div>${tag("model", "domains/energy-transition/briefing.json")}</div>
    <ul class="list">${li}</ul></section>`;
}

function seriesSection(l) {
  if (!l.series.length) return "";
  return `<section><div class="card-head" style="margin:0 0 8px"><h2>Radar series</h2><span class="muted">Monthly values. Hover a chart for exact values.</span></div>
    <div class="grid2">${l.series.map(seriesCard).join("")}</div></section>`;
}

function bottleneckCard() {
  const dom = S.D.domain.bottleneck_model, bn = S.D.briefing.bottleneck;
  const rows = dom.axes.slice().sort((a, b) => a.state_2026 - b.state_2026).map((a) => {
    const bind = a.id === bn.binding_bottleneck;
    return `<div class="axis-row ${bind ? "bind" : ""}"><div>${esc(a.label)}${bind ? " · binding" : ""}</div>
      <div class="axis-track"><i style="width:${a.state_2026 * 100}%"></i></div><div class="bar-val">${fmt(a.state_2026, 2)}</div></div>`;
  }).join("");
  const gains = bn.marginal_gain.map((g) => `<tr><td>${esc(g.label)}</td><td>${fmt(g.from, 2)} → ${fmt(g.to, 2)}</td><td>+${fmt(g.gain_percent, 1)}%</td></tr>`).join("");
  const ev = S.D.briefing.bottleneck_evidence.map((e) => `<div class="callout" style="margin-top:10px">${esc(e.source_status)}<br><span class="muted">${esc(e.text)}</span></div>`).join("");
  return `<section class="card"><div class="card-head"><div><h2>Bottleneck: what limits usable electricity</h2>
    <span class="muted">Usable output ${fmt(bn.usability_ces, 2)} (strong-complements model) vs ${fmt(bn.usability_linear, 2)} (simple average). The weakest part dominates.</span></div>${tag("judgment", "domains/energy-transition/domain.json (axis states)")}</div>
    ${rows}
    ${whatIf(dom, bn)}
    <h3 style="margin-top:14px">What improving each axis by one step would add</h3>
    <table><thead><tr><th>Axis</th><th>Step</th><th>Usable output</th></tr></thead><tbody>${gains}</tbody></table>
    ${ev}</section>`;
}

const ces = (xs, rho) => Math.pow(xs.reduce((a, x) => a + Math.pow(x, rho), 0) / xs.length, 1 / rho);
function whatIf(dom, bn) {
  const check = ces(dom.axes.map((a) => a.state_2026), dom.rho);
  const ok = Math.abs(check - bn.usability_ces) < 0.001;
  const sl = dom.axes.map((a) => `<label class="wi"><span>${esc(a.label)}</span>
    <input type="range" class="wi-in" data-axis="${esc(a.id)}" data-base="${a.state_2026}" min="0.05" max="1.5" step="0.05" value="${a.state_2026}" aria-label="${esc(a.label)}">
    <output>${fmt(a.state_2026, 2)}</output></label>`).join("");
  return `<h3 style="margin-top:14px">What-if: move the sliders</h3>
    <p class="kv">Axis states are judgments. This is an exploration, not a forecast. Formula: usable output = (mean of x<sup>ρ</sup>)<sup>1/ρ</sup>, ρ = ${dom.rho}.</p>
    ${sl}
    <div class="wi-out"><span>Usable output: <b class="big" id="wi-val">${fmt(check, 3)}</b></span>
      <span id="wi-delta" class="muted">no change vs published ${fmt(bn.usability_ces, 3)}</span>
      <button class="btn" type="button" id="wi-reset">Reset</button></div>
    ${ok ? "" : `<div class="callout" style="margin-top:8px"><b>Check failed</b> the in-page formula gives ${fmt(check, 4)}, the published value is ${fmt(bn.usability_ces, 4)}.</div>`}`;
}
function updateWhatIf() {
  const ins = [...document.querySelectorAll(".wi-in")];
  if (!ins.length) return;
  const rho = S.D.domain.bottleneck_model.rho, base = S.D.briefing.bottleneck.usability_ces;
  ins.forEach((i) => (i.nextElementSibling.textContent = fmt(i.value, 2)));
  const u = ces(ins.map((i) => +i.value), rho), d = ((u - base) / base) * 100;
  $("#wi-val").textContent = fmt(u, 3);
  $("#wi-delta").textContent = Math.abs(d) < 0.05 ? `no change vs published ${fmt(base, 3)}` : `${d > 0 ? "+" : ""}${fmt(d, 1)}% vs published ${fmt(base, 3)}`;
}

function gapCard(l) {
  const D = S.D, p = D.lv[l.inherits_from];
  const plan = l.data_plan.map((t) => `<li>${esc(t)}</li>`).join("");
  const bn = D.briefing.bottleneck, rs = D.series["energy-charts-erneuerbare"];
  const rsl = rs.punkte[rs.punkte.length - 1];
  return `<section class="card"><div class="card-head"><h2>Data plan for ${esc(l.name)}</h2>${tag("gap", "ui/regions.json (data_plan)")}</div>
    <div class="callout"><b>GAP</b> No measured value exists for ${esc(l.name)} in this repository. The list below says what to add, in order.</div>
    <ol style="margin:12px 0 0;padding-left:20px;display:grid;gap:6px">${plan}</ol></section>
    <section class="card"><div class="card-head"><div><h2>Context inherited from ${esc(p.name)}</h2><span class="muted">Not measured for ${esc(l.name)}. Shown only as background.</span></div>${tag("inherited", "domains/energy-transition/briefing.json")}</div>
    <ul class="list">
      <li><strong>Binding bottleneck (Germany): ${esc(bn.binding_bottleneck)}.</strong> <span class="muted">A judgment about Germany as a whole. Whether it holds for ${esc(l.name)} is unknown.</span></li>
      <li><strong>Renewable share of electricity, Germany: ${fmt(rsl.wert, 1)}% (${esc(rsl.t)}).</strong> <span class="muted">National figure.</span></li>
    </ul></section>`;
}

function render() {
  S.prov = [];
  const l = S.D.lv[S.level];
  renderHeader();
  const parts = [introCard(l), mapCard(S.level)];
  if (l.coverage === "gap") parts.push(gapCard(l));
  else {
    parts.push(scenariosCard(l));
    if (l.bottleneck) parts.push(bottleneckCard());
    parts.push(indicatorsCard(l), driversCard(l), seriesSection(l));
    parts.push(`<section class="card"><div class="card-head"><h2>Watchlist: what to improve next</h2>${tag("judgment", "domains/energy-transition/domain.json (open_tasks)")}</div>
      <ul class="list">${S.D.briefing.open_tasks.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
      <p class="kv">Option scoring (permitting reform, storage subsidies, flexible tariffs) is not part of this repository yet.</p></section>`);
  }
  $("#main").innerHTML = parts.join("");
  const seen = new Set();
  $("#prov-body").innerHTML = S.prov.filter((p) => !seen.has(p.kind + p.file) && seen.add(p.kind + p.file))
    .map((p) => `<div class="prov-item"><span class="tag ${p.kind.toLowerCase().split(" ")[0]}">${esc(p.kind)}</span> <code>${esc(p.file)}</code></div>`).join("");
  history.replaceState(null, "", `#${S.level}/${S.horizon}${S.open.size ? "/" + [...S.open].join(",") : ""}`);
}

// ---------- events ----------
document.addEventListener("click", (e) => {
  const c = e.target.closest("[data-level]"), h = e.target.closest("[data-h]");
  const pl = e.target.closest("[data-pal]");
  if (pl) { S.pal = pl.dataset.pal; const y = scrollY; render(); scrollTo(0, y); return; }
  const pt = e.target.closest("[data-param]");
  if (pt) { S.param = S.param === pt.dataset.param ? "coverage" : pt.dataset.param; const y = scrollY; render(); scrollTo(0, y); return; }
  const sc = e.target.closest("[data-sc]");
  if (sc) { const id = sc.dataset.sc; S.open.has(id) ? S.open.delete(id) : S.open.add(id); const y = scrollY; render(); scrollTo(0, y); return; }
  if (e.target.closest("#wi-reset")) { document.querySelectorAll(".wi-in").forEach((i) => (i.value = i.dataset.base)); updateWhatIf(); return; }
  if (c) { S.level = c.dataset.level; render(); scrollTo(0, 0); $("#main").focus({preventScroll: true}); }
  if (h) { S.horizon = h.dataset.h; render(); }
});
$("#prov-open").onclick = () => ($("#prov").hidden = false);
$("#prov-close").onclick = () => ($("#prov").hidden = true);
$("#theme").onclick = () => {
  const cur = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.documentElement.dataset.theme = cur === "dark" ? "light" : "dark";
};
document.addEventListener("change", (e) => {
  const t = e.target, y = scrollY;
  if (t.id === "param") S.param = t.value;
  else if (t.name === "when") S.when = t.value;
  else return;
  render(); scrollTo(0, y);
});
document.addEventListener("input", (e) => { if (e.target.classList.contains("wi-in")) updateWhatIf(); });
document.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && e.target.matches("[data-sc], .reg[data-level]")) { e.preventDefault(); e.target.dispatchEvent(new MouseEvent("click", {bubbles: true})); }
});
document.addEventListener("mouseover", (e) => {
  const k = e.target.closest("[data-key]");
  document.querySelectorAll(".hl").forEach((n) => n.classList.remove("hl"));
  if (k) document.querySelectorAll(`[data-key="${CSS.escape(k.dataset.key)}"]`).forEach((n) => n.classList.add("hl"));
});
const tip = $("#tip");
document.addEventListener("mousemove", (e) => {
  const reg = e.target.closest(".reg[data-tip]");
  if (reg) { tip.textContent = reg.dataset.tip; tip.hidden = false; tip.style.left = Math.min(e.clientX + 14, innerWidth - 260) + "px"; tip.style.top = e.clientY + 14 + "px"; return; }
  const hit = e.target.closest(".hit");
  if (!hit) { tip.hidden = true; document.querySelectorAll(".cross").forEach((c) => c.setAttribute("visibility", "hidden")); return; }
  const svg = hit.closest("svg"), pts = JSON.parse(svg.dataset.pts), p = pts[+hit.dataset.i];
  tip.innerHTML = `<strong>${esc(p.t)}</strong>: ${fmt(p.wert, 2)} ${esc(svg.dataset.unit)}`;
  tip.hidden = false; tip.style.left = Math.min(e.clientX + 14, innerWidth - 200) + "px"; tip.style.top = e.clientY + 14 + "px";
  const cx = +hit.getAttribute("x") + +hit.getAttribute("width") / 2, ln = svg.querySelector(".cross");
  ln.setAttribute("x1", cx); ln.setAttribute("x2", cx); ln.setAttribute("visibility", "visible");
});

(async () => {
  try {
    S.D = await load();
    const [lv, hz, open] = location.hash.slice(1).split("/");
    (open || "").split(",").filter(Boolean).forEach((id) => S.open.add(id));
    if (S.D.lv[lv]) S.level = lv;
    if (["2028", "2032", "2040"].includes(hz)) S.horizon = hz;
    render();
  } catch (err) {
    $("#main").innerHTML = `<div class="err"><strong>Could not load data.</strong><br>${esc(err.message)}<br>Start the server from the repository root with <code>make ui</code> and open <code>http://localhost:8000/ui/</code>.</div>`;
  }
})();
