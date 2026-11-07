"use strict";
// What-if switches for the map UI. Looks up engine-computed results; computes no model maths itself.
//   single switches: ../whatif/data.js (window.FORESIGHT_DATA, built by whatif/build_data.py)
//   extreme cases:   whatif_bundles.json (built by ui/build_bundles.py)
// While a what-if is active, S.D.briefing is replaced by a copy whose p_today holds the hypothetical probabilities,
// so the scenario bars, the energy-price shares and the model value on the map all show that case.
// The only arithmetic here is summing scenario probabilities per energy-price regime (same rule as domains/lens.py),
// and it is checked against briefing.json for today's values before anything is offered.

const W = {ok: false, why: "", id: "", k: null, bundles: null, single: null, orig: null};
const WI_HORIZONS = ["2028", "2032", "2040"];
const WI_REGIMES = {"-2": "much cheaper", "-1": "cheaper", "0": "neutral", "1": "more expensive", "2": "much more expensive"};
const BUNDLE_TEXT = {
  stress: {name: "Extreme case: everything that makes energy dearer", short: "stress case"},
  relief: {name: "Extreme case: everything that makes energy cheaper", short: "relief case"},
};

function wiMass(rows, p) {
  const m = {};
  for (const h of WI_HORIZONS) {
    m[h] = Object.fromEntries(Object.values(WI_REGIMES).map((n) => [n, 0]));
    for (const r of rows) m[h][WI_REGIMES[String(Math.round(r.regime.energy_price))]] += p[r.id][h];
  }
  return m;
}

async function wiLoad(D) {
  W.orig = D.briefing;
  const F = window.FORESIGHT_DATA;
  if (!F) { W.why = "whatif/data.js not found"; return; }
  if (F.weltlage.stand !== D.briefing.inputs.world_state_date) { W.why = `what-if data is for ${F.weltlage.stand}, the page for ${D.briefing.inputs.world_state_date}`; return; }
  const rows = D.briefing.scenarios.rows, today = Object.fromEntries(F.weltlage.szenarien.map((s) => [s.id, s.p_tag]));
  const same = rows.every((r) => WI_HORIZONS.every((h) => today[r.id] && today[r.id][h] === r.p_today[h]));
  const mass = wiMass(rows, today);
  const massOk = WI_HORIZONS.every((h) => Object.entries(D.briefing.scenarios.energy_price_mass[h]).every(([n, v]) => mass[h][n] === v));
  if (!same || !massOk) { W.why = "check failed: what-if data and briefing.json disagree on today's values"; return; }
  W.single = F;
  W.k = String(F.whatif.k_now);
  try { const r = await fetch("whatif_bundles.json"); if (r.ok) { const b = await r.json(); if (b.world_state === F.weltlage.stand) W.bundles = b; } } catch (e) { /* extreme cases optional */ }
  W.ok = true;
}

function wiCase(id) {
  if (!id) return null;
  if (id.startsWith("bundle:")) {
    const b = W.bundles && W.bundles.bundles[id.slice(7)];
    return b ? {kind: "bundle", key: id.slice(7), ids: b.ids, switchTo: b.switch_to, byK: b.by_k} : null;
  }
  const r = W.single.whatif.results[id];
  return r ? {kind: "single", ids: [id], switchTo: {[id]: r.switch_to}, byK: r.by_k} : null;
}

// Swap in the hypothetical briefing (or restore today's). Called at the start of every render().
function wiApply() {
  if (!W.ok) return;
  const c = wiCase(W.id), B = W.orig;
  if (!c || !c.byK[W.k]) { W.id = ""; S.D.briefing = B; return; }
  const p = c.byK[W.k].p;
  const rows = B.scenarios.rows.map((r) => ({...r, p_today: {...p[r.id]}}));
  S.D.briefing = {...B, scenarios: {...B.scenarios, rows, energy_price_mass: wiMass(B.scenarios.rows, p)}};
}
const wiActive = () => W.ok && !!W.id;
const wiLabel = () => (wiActive() ? "What-if" : "Today");

function wiIndText(id) {
  const t = (W.single.en.anzeichen.find((a) => a.id === id) || {}).text || id;
  return t;
}

// The switches alone (case, damping k, back to today). Used by the what-if card and by the focus view (ui/dash.js).
function whatifControls() {
  const F = W.single, res = F.whatif.results;
  const opt = (v, label) => `<option value="${esc(v)}" ${W.id === v ? "selected" : ""}>${esc(label)}</option>`;
  const singles = Object.keys(res).sort().map((id) => opt(id, `${id} ${res[id].switch_to === "on" ? "switches on" : "switches off"}: ${wiIndText(id)}`)).join("");
  const bundles = W.bundles ? Object.keys(W.bundles.bundles).map((k) => opt("bundle:" + k, `${BUNDLE_TEXT[k].name} (${W.bundles.bundles[k].ids.length} at once)`)).join("") : "";
  const ks = F.whatif.k_values.map((k) => `<option value="${k}" ${String(k) === W.k ? "selected" : ""}>${k}${k === F.whatif.k_now ? " (model)" : ""}</option>`).join("");
  return `<div class="mb-row">
      <label class="paramsel">Case <select id="wif-case"><option value="">Today (no what-if)</option>${bundles ? `<optgroup label="Extreme cases">${bundles}</optgroup>` : ""}<optgroup label="One indicator">${singles}</optgroup></select></label>
      <label class="paramsel">Damping k <select id="wif-k" ${wiActive() ? "" : "disabled"}>${ks}</select></label>
      ${wiActive() ? '<button class="btn" type="button" id="wif-reset">Back to today</button>' : ""}
    </div>`;
}

function whatifCard(controls = true) {
  if (!W.ok) return W.why ? `<section class="card"><div class="callout"><b>What-if not available</b> ${esc(W.why)}</div></section>` : "";
  const F = W.single;
  let body = `<p class="kv" style="margin:8px 0 0">Today no indicator has changed since the base model, so today's probabilities are the expert starting values. Pick a case to see how the engine would move them.</p>`;
  if (wiActive()) {
    const c = wiCase(W.id), h = S.horizon, B = W.orig, now = S.D.briefing;
    const d = B.scenarios.rows.map((r) => ({r, d: now.scenarios.rows.find((x) => x.id === r.id).p_today[h] - r.p_today[h]})).sort((a, b) => b.d - a.d);
    const moved = d.reduce((a, x) => a + Math.abs(x.d), 0) / 2;
    const dear = (br) => ["more expensive", "much more expensive"].reduce((a, n) => a + br.scenarios.energy_price_mass[h][n], 0);
    const li = (x) => `<li><b>${esc(x.r.name)}</b> <span class="muted">${x.r.p_today[h]}% → ${x.r.p_today[h] + x.d}%</span></li>`;
    const up = d.filter((x) => x.d > 0).slice(0, 3), down = d.filter((x) => x.d < 0).slice(-3).reverse();
    const switched = c.ids.map((id) => `<li><code>${esc(id)}</code> ${c.switchTo[id] === "on" ? "on" : "off"}: ${esc(wiIndText(id))}</li>`).join("");
    body = `<div class="demo-banner" style="margin-top:12px"><b>HYPOTHETICAL.</b> ${c.kind === "bundle" ? `${c.ids.length} early-warning indicators switched at once` : `Indicator ${esc(c.ids[0])} switched ${c.switchTo[c.ids[0]]}`}, damping k = ${esc(W.k)}. Not observed data, not a forecast. Scenario bars, energy-price shares and the model value on the map show this case; the map colours stay measured data.</div>
      <div class="wif-sum">
        <div><span class="kv">Moved in ${h}</span><b class="big">${fmt(moved, 0)} pp</b><span class="kv">of scenario probability</span></div>
        <div><span class="kv">Chance of dearer energy, ${h}</span><b class="big">${dear(B)}% → ${dear(now)}%</b><span class="kv">scenarios with energy price above neutral</span></div>
      </div>
      <div class="grid2" style="margin-top:10px"><div><h3>Gains</h3><ul class="list">${up.map(li).join("") || "<li class='muted'>nothing</li>"}</ul></div>
        <div><h3>Loses</h3><ul class="list">${down.map(li).join("") || "<li class='muted'>nothing</li>"}</ul></div></div>
      <details style="margin-top:8px"><summary>${c.kind === "bundle" ? "Which indicators are switched, and by which rule" : "The indicator"}</summary><ul>${switched}</ul>
        ${c.kind === "bundle" ? `<p class="kv">Rule: every indicator whose single what-if raises (stress) or lowers (relief) the chance of dearer energy in ${esc(W.bundles.rule_horizon)} at the model's k. The model treats each signal on its own; it does not know how likely it is that all of them happen together.</p>` : ""}</details>`;
  }
  const skipped = Object.entries(F.whatif.skipped).map(([id, why]) => `${id} (${why})`).join(", ");
  return `<section class="card wif ${wiActive() ? "on" : ""}" id="whatif">
    <div class="card-head"><div><h2>What if …?</h2><span class="muted">Switch early-warning indicators hypothetically. Every case was computed by the engine in advance.</span></div>${tag("model", "whatif/data.js, ui/whatif_bundles.json (engine/tagesstand.py aus_status)")}</div>
    ${controls ? whatifControls() : ""}
    ${body}
    <p class="kv" style="margin-top:10px">Not simulated: ${esc(skipped)}.</p></section>`;
}

document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.id !== "wif-case" && t.id !== "wif-k") return;
  if (t.id === "wif-case") W.id = t.value; else W.k = t.value;
  const y = scrollY; render(); scrollTo(0, y);
});
document.addEventListener("click", (e) => {
  if (!e.target.closest("#wif-reset")) return;
  W.id = ""; const y = scrollY; render(); scrollTo(0, y);
});
