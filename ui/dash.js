"use strict";
// Focus view of the map UI: the map is the dashboard. Beside it stand only the key number, the what-if switches
// and a guided tour. Everything else (scenario bars, bottleneck, indicators, series) opens with "All details".
// Every number in the tour is read from the loaded data at that step (briefing.json, whatif/data.js,
// ui/whatif_bundles.json, radar/regional/regional.json). Nothing is typed in by hand.
// Hash: #level/horizon/open/w=ID@k/tour=N opens stop N of the tour (for a talk: arrow keys or a presenter clicker).

const DASH = {full: false};
const T = {on: false, i: 0};

const DEAR = ["more expensive", "much more expensive"], CHEAP = ["much cheaper", "cheaper"];
const share = (br, h, names) => names.reduce((a, n) => a + br.scenarios.energy_price_mass[h][n], 0);
const today = () => (W.ok ? W.orig : S.D.briefing);
function shifts(h) {
  const B = today().scenarios.rows;
  return S.D.briefing.scenarios.rows.map((r) => {
    const a = B.find((x) => x.id === r.id).p_today[h];
    return {name: r.name, a, b: r.p_today[h], d: r.p_today[h] - a};
  }).sort((x, y) => y.d - x.d);
}
const moved = (h) => shifts(h).reduce((a, x) => a + Math.abs(x.d), 0) / 2;
const kNow = () => String(W.single.whatif.k_now);
const dearLine = (h) => `Dearer energy in ${h}: ${share(today(), h, DEAR)} % → <b>${share(S.D.briefing, h, DEAR)} %</b>.`;

// ---------- the tour ----------
// share of dearer energy for a what-if case at a given reaction strength k, without switching the page to it
function dearAt(id, k, h) {
  const c = wiCase(id), p = c && c.byK[k] && c.byK[k].p;
  return p ? DEAR.reduce((a, n) => a + wiMass(today().scenarios.rows, p)[h][n], 0) : null;
}
const range = (xs) => { const a = Math.round(Math.min(...xs) * 100), b = Math.round(Math.max(...xs) * 100); return a === b ? `${a} %` : `${a}–${b} %`; };
const STEPS = [
  {title: "Energy prices in the world model", set: {level: "global", param: "regime_dear", h: "2028"},
    text: () => `${S.D.briefing.scenarios.rows.length} world scenarios, each with its own energy prices. Today <b>${share(S.D.briefing, "2028", DEAR)} %</b> of the probability lies in worlds where energy gets dearer by 2028.`},
  {title: "Measured: Germany, Brandenburg, Berlin", set: {level: "germany", param: "c-mastr-wind-mw", h: "2028"},
    need: () => !!(S.D.regional?.datasets?.mastr_wind_mw?.values?.Brandenburg && S.D.regional?.datasets?.mastr_pv_roof_mw?.values?.Berlin),
    text: () => {
      const w = S.D.regional.datasets.mastr_wind_mw.values, roof = S.D.regional.datasets.mastr_pv_roof_mw.values.Berlin;
      const rank = Object.values(w).filter((x) => x.v > w.Brandenburg.v).length + 1, n = Object.keys(w).length;
      const peak = S.D.regional.local?.berlin_peak_load?.punkte?.slice(-1)[0];
      return `The colours are measured: wind power in operation per state. Brandenburg runs <b>${fmt(w.Brandenburg.v, 0)} MW</b>, rank ${rank} of ${n}. Berlin has ${w.Berlin ? `${fmt(w.Berlin.v, 0)} MW of wind but ` : ""}${fmt(roof.v, 0)} MW of solar on buildings${peak ? `; its peak load (medium and low voltage) was ${fmt(peak.wert, 0)} MW in ${esc(peak.t)}` : ""}.`;
    }},
  {title: "The bottleneck is not generation", set: {level: "germany", param: "c-mastr-pv", h: "2028"},
    need: () => !!S.D.briefing.bottleneck?.marginal_gain?.length,
    text: () => {
      const g = S.D.briefing.bottleneck.marginal_gain.slice().sort((a, b) => b.gain_percent - a.gain_percent);
      const gen = g.find((x) => x.axis === "generation");
      return `What limits usable electricity is <b>${esc(g[0].label.split(" (")[0].toLowerCase())}</b>. One step better there adds <b>+${fmt(g[0].gain_percent, 1)} %</b> usable output${gen ? `, one step more generation only +${fmt(gen.gain_percent, 1)} %` : ""}. The axis states are judgments.`;
    }},
  {title: "One signal: an oil shock", set: {level: "global", param: "regime_dear", h: "2032", w: "A05"},
    text: () => {
      const strong = dearAt("A05", "0.5", "2032");
      return `Suppose: <i>${esc(wiIndText("A05"))}</i>. ${dearLine("2032")} How strongly the model reacts to a signal is a judgment (${kNow()}).${strong !== null ? ` Try the switch “Reaction to a signal”: at 0.5 the same shock gives ${strong} %.` : ""}`;
    }},
  {title: "Extreme cases: dearer or cheaper", set: {level: "global", param: "regime_dear", h: "2032", w: "bundle:stress"},
    text: () => {
      const cheap = wiCase("bundle:relief") ? dearAt("bundle:relief", kNow(), "2032") : null, strong = dearAt("bundle:stress", "0.5", "2032");
      return `${wiCase("bundle:stress").ids.length} early-warning signals switch at once. ${dearLine("2032")}${cheap !== null ? ` If all signals point the other way: ${cheap} %.` : ""}${strong !== null ? ` With a strong reaction (0.5): ${strong} %.` : ""} The model does not know how likely it is that all of them happen together.`;
    }},
  {title: "Would the model have warned?", set: {level: "global", param: "regime_dear", h: "2032"}, chart: "history",
    need: () => !!S.D.history?.rows?.length,
    text: () => {
      const H = S.D.history, before = (ev) => H.rows.filter((r) => r.t < ev.t).slice(-4).map((r) => r.p);
      const s = H.score.holdout;
      return `Energy prices cannot be checked against history yet, so we tested the same engine on German industry. In the year before each crisis it said: ${H.events.map((ev) => `${ev.t.slice(0, 4)} ${range(before(ev))}`).join(", ")}, hardly different from its fixed starting value of ${Math.round(H.prior * 100)} %. From ${s.from.slice(0, 4)} on it was no better than that fixed value. Read the model as a map of possible worlds and of signals to watch, not as a forecast.`;
    }},
];
const kOf = (st) => (st.k || (W.ok ? kNow() : ""));
const steps = () => STEPS.filter((st) => (!st.need || st.need()) && (!st.set.w || (W.ok && wiCase(st.set.w)?.byK[kOf(st.set)])));

function tourGo(i) {
  const all = steps();
  if (!all.length) return;
  T.on = true;
  T.i = Math.max(0, Math.min(all.length - 1, i));
  const st = all[T.i].set;
  S.level = st.level; S.horizon = st.h; S.param = st.param; S.when = "current"; S.open.clear();
  if (W.ok) { W.id = st.w || ""; W.k = kOf(st); }
  render();
  const d = document.querySelector(".dash");
  if (d) scrollTo(0, Math.max(0, d.getBoundingClientRect().top + scrollY - 8));
}
function tourEnd() { T.on = false; if (W.ok) { W.id = ""; W.k = kNow(); } render(); }
function tourInit() {
  const m = /tour=(\d+)/.exec(location.hash);
  if (m) tourGo(+m[1] - 1);
}
const tourHash = () => (T.on ? `/tour=${T.i + 1}` : "");

function tourCard() {
  const all = steps();
  if (!all.length) return "";
  if (!T.on) {
    return `<section class="card tour"><h2>Guided tour</h2>
      <p class="muted">${all.length} stops: world scenarios, measured data, what-ifs, and a look back at what the model would have said.</p>
      <button class="btn primary" type="button" data-tour="start">Start the tour ›</button></section>`;
  }
  const st = all[T.i], last = T.i === all.length - 1;
  const dots = all.map((s, i) => `<button type="button" class="dot ${i === T.i ? "on" : ""}" data-tour-go="${i}" aria-label="Stop ${i + 1}: ${esc(s.title)}" aria-current="${i === T.i}"></button>`).join("");
  return `<section class="card tour on" aria-live="polite">
    <div class="tour-top"><span class="kv">Stop ${T.i + 1} of ${all.length}</span><div class="dots">${dots}</div></div>
    <h2>${esc(st.title)}</h2>
    <p>${st.text()}</p>
    <div class="tour-nav"><button class="btn" type="button" data-tour="prev" ${T.i ? "" : "disabled"}>‹ Back</button>
      <button class="btn primary" type="button" data-tour="${last ? "end" : "next"}">${last ? "Finish" : "Next ›"}</button>
      <button class="btn quiet" type="button" data-tour="end">End tour</button></div></section>`;
}

// ---------- look back: the model's forecast against what happened (ui/history.json) ----------
async function dashLoad(D) {
  try { const r = await fetch("history.json"); if (r.ok) D.history = await r.json(); } catch (e) { /* the last stop is optional */ }
}
const qIndex = (t, t0) => ((+t.slice(0, 4) - +t0.slice(0, 4)) * 12 + (+t.slice(5, 7) - +t0.slice(5, 7))) / 3;
function historyCard() {
  const H = S.D.history, R = H.rows, n = R.length, narrow = matchMedia("(max-width:640px)").matches;
  const Wd = narrow ? 360 : 720, Ht = narrow ? 240 : 300, P = {l: 42, r: 10, t: 42, b: 24}, top = 0.6;
  const x = (i) => P.l + (i * (Wd - P.l - P.r)) / (n - 1), y = (v) => P.t + (1 - v / top) * (Ht - P.t - P.b);
  const step = (Wd - P.l - P.r) / (n - 1);
  // event labels: next to their line, inside the chart, never on top of another label or of another event's line;
  // a label goes one row higher only when the row below has no room (lines run from their own label down)
  const lab = H.events.map((e) => ({ex: x(qIndex(e.t, R[0].t)), text: `${e.label} ${e.t.slice(0, 4)}`}));
  lab.forEach((L) => { L.w = L.text.length * 6.6; });
  for (const L of lab) {
    search: for (let row = 0; row < 4; row++) {
      for (const a of ["middle", "end", "start"]) {
        const tx = a === "middle" ? L.ex : a === "end" ? L.ex - 4 : L.ex + 4, x0 = a === "middle" ? tx - L.w / 2 : a === "end" ? tx - L.w : tx, x1 = x0 + L.w;
        if (x0 < 2 || x1 > Wd - 2) continue;
        if (lab.some((o) => o !== L && o.row === row && x0 < o.x1 + 8 && x1 > o.x0 - 8)) continue;
        if (lab.some((o) => o !== L && o.ex > x0 - 3 && o.ex < x1 + 3 && (o.row === undefined || o.row >= row))) continue;
        Object.assign(L, {row, a, tx, x0, x1});
        break search;
      }
    }
    if (L.row === undefined) Object.assign(L, {row: 0, a: "middle", tx: L.ex, x0: L.ex, x1: L.ex});
  }
  P.t = 26 + 16 * (Math.max(...lab.map((L) => L.row)) + 1);
  const ev = lab.map((L) => {
    const ty = P.t - 10 - L.row * 16;
    return `<line class="h-ev" x1="${L.ex.toFixed(1)}" x2="${L.ex.toFixed(1)}" y1="${ty + 4}" y2="${Ht - P.b}"/><text class="h-evl" x="${L.tx.toFixed(1)}" y="${ty}" text-anchor="${L.a}">${esc(L.text)}</text>`;
  }).join("");
  const bands = R.map((r, i) => (r.y ? `<rect class="h-band" x="${(x(i) - step / 2).toFixed(1)}" y="${P.t}" width="${step.toFixed(1)}" height="${Ht - P.t - P.b}"/>` : "")).join("");
  const grid = [0, 0.2, 0.4, 0.6].map((v) => `<line class="h-grid" x1="${P.l}" x2="${Wd - P.r}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"/><text x="${P.l - 6}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${v * 100} %</text>`).join("");
  const years = R.filter((r) => r.t.endsWith("-03") && +r.t.slice(0, 4) % 5 === 0).map((r) => `<text x="${x(R.indexOf(r)).toFixed(1)}" y="${Ht - 6}" text-anchor="middle">${r.t.slice(0, 4)}</text>`).join("");
  const line = R.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(r.p).toFixed(1)}`).join(" ");
  const hits = R.map((r, i) => `<rect class="h-hit" x="${(x(i) - step / 2).toFixed(1)}" y="${P.t}" width="${step.toFixed(1)}" height="${Ht - P.t - P.b}" data-tip="${esc(r.t)}: model ${Math.round(r.p * 100)} % · industry 12 months later ${r.y ? "lower" : "not lower"}"/>`).join("");
  const sc = H.score.holdout, b = sc.brier, f4 = (v) => fmt(v, 3);
  const table = R.map((r) => `<tr><td>${esc(r.t)}</td><td>${Math.round(r.p * 100)} %</td><td>${r.y ? "lower" : "not lower"}</td></tr>`).join("");
  return `<section class="card hist">
    <div class="card-head"><div><h2>Did the model see the downturns coming?</h2><span class="muted">German industry, every quarter since ${R[0].t.slice(0, 4)}, computed only with data known at the time</span></div>${tag("model", "ui/history.json (ui/build_history.py, loop/check.py)")}</div>
    <svg class="h-svg" viewBox="0 0 ${Wd} ${Ht}" role="img" aria-label="Line chart: the model's chance of a downturn of German industry per quarter, ${esc(R[0].t)} to ${esc(R[n - 1].t)}, between ${Math.round(Math.min(...R.map((r) => r.p)) * 100)} and ${Math.round(Math.max(...R.map((r) => r.p)) * 100)} %, against a fixed starting value of ${Math.round(H.prior * 100)} %. Shaded quarters: industry was lower 12 months later.">
      ${bands}${grid}${years}
      <line class="h-prior" x1="${P.l}" x2="${Wd - P.r}" y1="${y(H.prior).toFixed(1)}" y2="${y(H.prior).toFixed(1)}"/>
      ${ev}<path class="h-ln" d="${line}"/>
      <line class="h-cross" x1="0" x2="0" y1="${P.t}" y2="${Ht - P.b}" visibility="hidden"/>${hits}</svg>
    <div class="h-leg"><span><i class="k-ln"></i>Model: chance of a downturn</span><span><i class="k-prior"></i>Fixed starting value ${Math.round(H.prior * 100)} %</span><span><i class="k-band"></i>Industry was lower 12 months later</span></div>
    <div class="h-score"><span class="kv">Error score ${sc.from.slice(0, 4)}–${sc.to.slice(0, 4)}, lower is better</span>
      <div><b>${f4(b.variant)}</b><span>model</span></div><div><b>${f4(b.prior_only)}</b><span>fixed ${Math.round(H.prior * 100)} %</span></div><div><b>${f4(b.baseline)}</b><span>past frequency</span></div></div>
    <details><summary>Values as a table</summary><table class="h-table"><thead><tr><th>Quarter</th><th>Model</th><th>Industry 12 months later</th></tr></thead><tbody>${table}</tbody></table></details>
  </section>`;
}
document.addEventListener("mousemove", (e) => {
  const hit = e.target.closest(".h-hit"), cross = document.querySelector(".h-cross");
  if (!cross) return;
  if (!hit) { cross.setAttribute("visibility", "hidden"); return; }
  const cx = +hit.getAttribute("x") + +hit.getAttribute("width") / 2;
  cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
  const tip = document.getElementById("tip");
  if (tip) { tip.textContent = hit.dataset.tip; tip.hidden = false; tip.style.left = Math.min(e.clientX + 14, innerWidth - 260) + "px"; tip.style.top = e.clientY + 14 + "px"; }
});

// ---------- key number and switches ----------
function panelCard() {
  const h = S.horizon, now = S.D.briefing, wi = typeof wiActive === "function" && wiActive();
  const m = now.scenarios.energy_price_mass[h];
  const seg = [["much cheaper", "var(--good)"], ["cheaper", "color-mix(in srgb,var(--good) 50%,var(--card))"], ["neutral", "var(--base)"],
    ["more expensive", "color-mix(in srgb,var(--crit) 55%,var(--card))"], ["much more expensive", "var(--crit)"]];
  const bar = seg.map(([n, c]) => (m[n] ? `<i style="width:${m[n]}%;background:${c}" title="${esc(n)}: ${m[n]} %"></i>` : "")).join("");
  const dear = share(now, h, DEAR), cheap = share(now, h, CHEAP), neutral = m.neutral;
  const hz = ["2028", "2032", "2040"].map((x) => `<button type="button" data-h="${x}" aria-pressed="${x === h}">${x}</button>`).join("");
  return `<section class="card panel ${wi ? "hypo" : ""}">
    <div class="kn-head"><h2>Chance of dearer energy</h2>${tag("model", wi ? "whatif/data.js, ui/whatif_bundles.json (engine what-if)" : "domains/energy-transition/briefing.json")}</div>
    <div class="seg" role="group" aria-label="Horizon">${hz}</div>
    <div class="kn-val"><b class="big">${dear} %</b><span class="muted">${wi ? `today ${share(today(), h, DEAR)} % · <b class="hypo-tag">what-if</b>` : `in ${h}`}</span></div>
    <div class="regbar" role="img" aria-label="Energy prices in ${h}: cheaper ${cheap} %, neutral ${neutral} %, dearer ${dear} %">${bar}</div>
    <div class="regleg"><span>cheaper ${cheap} %</span><span>neutral ${neutral} %</span><span>dearer ${dear} %</span></div>
    ${W.ok ? `<h3>What if …?</h3>${whatifControls()}` : ""}
  </section>`;
}

function dashLayout() {
  document.body.classList.toggle("focus", !DASH.full);
  // The model is global: on the world map every country gets the same tint, stronger the higher the chance of dearer energy.
  const dear = share(S.D.briefing, S.horizon, DEAR), tint = S.eff === "regime_dear" || S.param === "regime_dear";
  return `<div class="dash ${tint ? "dear-map" : ""}" style="--dear-fill:color-mix(in srgb,var(--crit) ${dear}%,var(--card))"><div class="dash-tour">${tourCard()}</div><div class="dash-map">${T.on && steps()[T.i]?.chart === "history" ? historyCard() : mapCard(S.level)}</div><div class="dash-panel">${panelCard()}</div></div>
    <div class="dash-more"><button class="btn" type="button" data-full aria-expanded="${DASH.full}">${DASH.full ? "Hide the details ▴" : "All details ▾"}</button></div>`;
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-tour]"), g = e.target.closest("[data-tour-go]"), f = e.target.closest("[data-full]");
  if (g) return tourGo(+g.dataset.tourGo);
  if (t) {
    const a = t.dataset.tour;
    if (a === "start") tourGo(0);
    else if (a === "next") tourGo(T.i + 1);
    else if (a === "prev") tourGo(T.i - 1);
    else tourEnd();
    return;
  }
  if (f) {
    DASH.full = !DASH.full;
    const y = scrollY; render(); scrollTo(0, y);
    if (DASH.full) document.querySelector(".dash-more")?.scrollIntoView({behavior: "smooth", block: "start"});
  }
});
document.addEventListener("keydown", (e) => {
  if (!T.on || e.altKey || e.ctrlKey || e.metaKey || e.target.closest("input, select, textarea")) return;
  if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); tourGo(T.i + 1); }
  else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); tourGo(T.i - 1); }
  else if (e.key === "Escape") tourEnd();
});
