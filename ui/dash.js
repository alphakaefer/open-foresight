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
const STEPS = [
  {title: "Energy prices in the world model", set: {level: "global", param: "regime_dear", h: "2028"},
    text: () => `${S.D.briefing.scenarios.rows.length} world scenarios, each with its own energy prices. Today <b>${share(S.D.briefing, "2028", DEAR)} %</b> of the probability lies in worlds where energy gets dearer by 2028.`},
  {title: "Germany, measured", set: {level: "germany", param: "c-mastr-wind", h: "2028"},
    need: () => !!S.D.regional?.datasets?.mastr_wind,
    text: () => {
      const v = S.D.regional.datasets.mastr_wind.values, top = Object.entries(v).sort((a, b) => b[1].v - a[1].v)[0];
      const one = (n) => (v[n] ? `${n} ${fmt(v[n].v, 0)}` : `${n}: no value`);
      return `The colours are measured data: wind turbines in operation per state. Most in <b>${esc(top[0])}</b> (${fmt(top[1].v, 0)}), ${one("Brandenburg")}, ${one("Berlin")}.`;
    }},
  {title: "The bottleneck is not generation", set: {level: "germany", param: "c-mastr-pv", h: "2028"},
    need: () => !!S.D.briefing.bottleneck?.marginal_gain?.length,
    text: () => {
      const g = S.D.briefing.bottleneck.marginal_gain.slice().sort((a, b) => b.gain_percent - a.gain_percent);
      const gen = g.find((x) => x.axis === "generation");
      return `What limits usable electricity is <b>${esc(g[0].label.split(" (")[0].toLowerCase())}</b>. One step better there adds <b>+${fmt(g[0].gain_percent, 1)} %</b> usable output${gen ? `, one step more generation only +${fmt(gen.gain_percent, 1)} %` : ""}. The axis states are judgments.`;
    }},
  {title: "One signal: an oil shock", set: {level: "global", param: "regime_dear", h: "2032", w: "A05"},
    text: () => `Suppose: <i>${esc(wiIndText("A05"))}</i>. The engine moves <b>${fmt(moved("2032"), 0)} pp</b> of probability. ${dearLine("2032")}`},
  {title: "How much should one signal count?", set: {level: "global", param: "regime_dear", h: "2032", w: "A05", k: "0.5"},
    text: () => `The model damps every signal (k = ${kNow()}). With k = 0.5 the same oil shock moves <b>${fmt(moved("2032"), 0)} pp</b>. ${dearLine("2032")} The damping is a judgment.`},
  {title: "Extreme case: everything turns dearer", set: {level: "global", param: "regime_dear", h: "2032", w: "bundle:stress"},
    text: () => {
      const s = shifts("2032"), up = s[0], dn = s[s.length - 1];
      return `${wiCase("bundle:stress").ids.length} early-warning signals switch at once. ${dearLine("2032")} ${esc(up.name)} ${up.a} → ${up.b} %, ${esc(dn.name)} ${dn.a} → ${dn.b} %.`;
    }},
  {title: "Same case, weaker damping", set: {level: "global", param: "regime_dear", h: "2032", w: "bundle:stress", k: "0.5"},
    text: () => `With k = 0.5 the signals move <b>${fmt(moved("2032"), 0)} pp</b>. ${dearLine("2032")} Signals that point the same way add up. The model does not know how likely it is that all of them happen together.`},
  {title: "Extreme case: everything turns cheaper", set: {level: "global", param: "regime_dear", h: "2032", w: "bundle:relief"},
    text: () => {
      const up = shifts("2032")[0];
      return `${wiCase("bundle:relief").ids.length} signals point the other way. ${dearLine("2032")} ${esc(up.name)} ${up.a} → ${up.b} %.`;
    }},
  {title: "What foresight does with this", set: {level: "global", param: "regime_dear", h: "2032"},
    need: () => !!wiCase("bundle:stress"),
    text: () => {
      const c = wiCase("bundle:stress"), off = c.ids.filter((id) => c.switchTo[id] === "on").length;
      const oe2 = (W.single.en.treiber || []).find((t) => t.id === "OE2");
      return `${off === c.ids.length ? `All ${off}` : `${off} of the ${c.ids.length}`} stress signals are off today. These are the signals to watch: as soon as one switches in the data, the engine moves the probabilities.${oe2 ? ` Blind spot: <i>${esc(oe2.name)}</i> has no indicator yet, so nothing here can warn of it.` : ""}`;
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
      <p class="muted">${all.length} stops through scenarios, extreme cases and what-ifs.</p>
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
  return `<div class="dash ${tint ? "dear-map" : ""}" style="--dear-fill:color-mix(in srgb,var(--crit) ${dear}%,var(--card))"><div class="dash-tour">${tourCard()}</div><div class="dash-map">${mapCard(S.level)}</div><div class="dash-panel">${panelCard()}</div></div>
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
