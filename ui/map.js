"use strict";
// Maps for the five levels. Outlines: ui/geo/ (Natural Earth, simplified).
// Two kinds of colour: DATA COVERAGE (default, where no per-region numbers exist) and COMPARISON of real per-region
// values (radar/regional/regional.json, fetched by radar/fetch_regional.py). A region without a value is hatched, never estimated.

const VIEWS = {
  global:      {file: "world",  lon: [-170, 190],  lat: [-58, 80],    ref: 0,    fs: 5.5,  label: "world"},
  europe:      {file: "europe", lon: [-12, 42],    lat: [34, 72],     ref: 53,   fs: 1.5,  label: "Europe"},
  germany:     {file: "de",     lon: [5.3, 15.6],  lat: [46.9, 55.3], ref: 51,   fs: 0.34, label: "Germany"},
  brandenburg: {file: "de",     lon: [10.9, 15.1], lat: [51.2, 53.7], ref: 52.4, fs: 0.12, label: "Brandenburg"},
  berlin:      {file: "de",     lon: [12.8, 14.0], lat: [52.25, 52.8], ref: 52.5, fs: 0.035, label: "Berlin"},
};
const MAP_LABELS = {
  global: [],
  europe: [{t: "Germany", lon: 10.3, lat: 51.2}],
  germany: [{t: "Brandenburg", lon: 13.55, lat: 53.0}, {t: "Berlin", lon: 13.4, lat: 52.5, dim: true, small: true}],
  brandenburg: [{t: "Brandenburg", lon: 12.6, lat: 52.2}, {t: "Berlin", lon: 13.4, lat: 52.5}],
  berlin: [{t: "Berlin", lon: 13.4, lat: 52.52}, {t: "Brandenburg", lon: 12.95, lat: 52.28}],
};
const MAP_LEGEND = {
  global: [["full", "The world model covers all of it"], ["full nav", "Europe: click to zoom in"]],
  europe: [["full nav", "Germany: full domain lens (click)"], ["neutral", "Other countries: no separate data (Eurozone series are aggregates)"]],
  germany: [["natl", "States: national data only, no state-level data"], ["gap nav", "Brandenburg and Berlin: in scope, GAP (click)"]],
  brandenburg: [["gap sel", "Brandenburg: GAP"], ["gap nav", "Berlin (click)"], ["neutral", "Other states"]],
  berlin: [["gap sel", "Berlin: GAP"], ["gap nav", "Brandenburg (click)"]],
};

function classify(level, name, props) {
  if (level === "global") {
    const eu = props.continent === "Europe" || name === "Turkey" || name === "Cyprus";
    return eu ? {cls: "full nav", nav: "europe", tip: "Europe: proxy data only. Click to zoom in."} : {cls: "full", tip: "Covered by the global scenarios; no regional data."};
  }
  if (level === "europe") {
    return name === "Germany" ? {cls: "full nav", nav: "germany", tip: "Germany: full domain lens. Click to open."} : {cls: "neutral", tip: "No separate data for this country."};
  }
  const own = {Berlin: "berlin", Brandenburg: "brandenburg"}[name];
  if (level === "germany") {
    return own ? {cls: "gap nav", nav: own, tip: `${name}: GAP, no state-level data. Click to open its data plan.`} : {cls: "natl", tip: `${name}: only national data exists, no state-level data.`};
  }
  if (own === level) return {cls: "gap sel", tip: `${name}: selected. GAP, no measured data.`};
  if (own) return {cls: "gap nav", nav: own, tip: `${name}: GAP. Click to open.`};
  return {cls: "neutral", tip: `${name}: no data.`};
}

// Full screen: the Fullscreen API on the map card. Changing the card's DOM would re-render and drop the fullscreen,
// so the button only toggles fullscreen and never re-renders.
function toggleFullscreen(el) {
  const doc = document;
  const current = doc.fullscreenElement || doc.webkitFullscreenElement;
  if (current) { (doc.exitFullscreen || doc.webkitExitFullscreen).call(doc); return; }
  const req = el.requestFullscreen || el.webkitRequestFullscreen;
  if (req) req.call(el).catch(() => {});
}
document.addEventListener("fullscreenchange", () => {
  const on = !!(document.fullscreenElement);
  document.querySelectorAll(".fs-btn").forEach((b) => { b.textContent = on ? "✕ Exit full screen" : "⛶ Full screen"; b.setAttribute("aria-label", on ? "Exit full screen" : "Show this map full screen"); });
});

// ---------- parameters (energy layers) ----------
const SCOPE_CHAIN = {global: ["global"], europe: ["euro_area"], germany: ["germany"], brandenburg: ["brandenburg", "germany"], berlin: ["berlin", "germany"]};

function yearAgo(t) { const [y, m] = t.split("-"); return `${+y - 1}-${m}`; }

// Reads a parameter's current value from the loaded data. Returns null for gaps.
const FUTURE_YEAR = "2032";
function D_demo_model(p) { return S.D.demo.model[p.id]?.value ?? null; }
function paramValue(p) {
  const D = S.D;
  if (S.when === "future" && p.kind === "series") {
    const f = D.demo.series[p.id], r = D.series[p.series], pts = r.punkte, last = pts[pts.length - 1];
    if (!f) return null;
    const pct = !/%/.test(p.unit), change = pct ? ((f.value - last.wert) / last.wert) * 100 : f.value - last.wert;
    return {value: f.value, display: fmt(f.value, 2), unit: p.unit, when: `future ${FUTURE_YEAR} (illustrative)`, change, changeUnit: pct ? "%" : " pp",
      ref: "vs latest measured value", points: null, file: "ui/demo/future.json (illustrative, not data)"};
  }
  if (p.kind === "series") {
    const r = D.series[p.series];
    if (!r) return null;
    const pts = r.punkte, last = pts[pts.length - 1], prev = pts.find((q) => q.t === yearAgo(last.t));
    const pct = !/%/.test(p.unit);
    const change = prev ? (pct ? ((last.wert - prev.wert) / prev.wert) * 100 : last.wert - prev.wert) : null;
    return {value: last.wert, display: fmt(last.wert, 2), unit: p.unit, when: last.t, change, changeUnit: pct ? "%" : " pp", ref: "vs 12 months earlier", points: pts, url: r.url, source: r.quelleName, file: `radar/snapshot/wissensstand.json (${p.series})`};
  }
  if (p.kind === "regional") {  // one region's value from radar/regional/regional.json
    const ds = D.regional?.datasets?.[p.dataset], r = ds?.values?.[p.key];
    if (!r) return null;
    return {value: r.v, display: fmt(r.v, 0), unit: p.unit || ds.unit, when: r.p, change: null, changeUnit: "",
      ref: r.n != null ? `${fmt(r.n, 0)} units` : "", points: null, url: ds.url, source: ds.source, file: `radar/regional/regional.json (${p.dataset})`};
  }
  if (p.kind === "local") {  // a yearly series from the "local" part of regional.json
    const r = D.regional?.local?.[p.local];
    if (!r || !r.punkte?.length) return null;
    const pts = r.punkte, last = pts[pts.length - 1], prev = pts[pts.length - 2];
    return {value: last.wert, display: fmt(last.wert, 0), unit: p.unit || r.einheit, when: last.t,
      change: prev ? ((last.wert - prev.wert) / prev.wert) * 100 : null, changeUnit: "%", ref: prev ? `vs ${prev.t}` : "",
      points: pts, url: r.url, source: r.quelleName, file: `radar/regional/regional.json (local.${p.local})`};
  }
  if (p.kind === "model") {
    const rows = S.D.briefing.scenarios.rows, src = "domains/energy-transition/briefing.json (scenario rows)";
    const sum = (key, h) => rows.filter((r) => r.regime.energy_price > 0).reduce((a, r) => a + r[key][h], 0);
    if (S.when === "future") {
      const f = D_demo_model(p), today = sum("p_today", FUTURE_YEAR);
      return {value: f, display: fmt(f, 0) + "%", unit: `illustrative, ${FUTURE_YEAR}`, when: `future ${FUTURE_YEAR}`, change: f - today, changeUnit: " pp",
        ref: "vs today's view (illustrative)", points: null, file: "ui/demo/future.json (illustrative, not data)"};
    }
    const today = sum("p_today", S.horizon);
    const wi = typeof wiActive === "function" && wiActive();
    return {value: today, display: fmt(today, 0) + "%", unit: `${wi ? "HYPOTHETICAL what-if" : "today's view"}, ${S.horizon} horizon`, when: "current", change: null,
      ref: wi ? "engine-computed what-if, not a forecast" : "latest world state (2026-11-07)", points: null, file: wi ? "whatif/data.js (engine what-if)" : src};
  }
  return null;
}

function paramsForLevel(level) {
  const P = S.D.params.params, chain = SCOPE_CHAIN[level];
  const own = P.filter((p) => p.scope === chain[0]);
  const inherited = chain.slice(1).flatMap((sc) => P.filter((p) => p.scope === sc));
  return {own, inherited};
}

// Does this parameter apply to a map feature? Euro-area aggregates are not drawn per country on purpose:
// the repository has no list of members, and inventing one would be a claim the data does not make.
function paramAppliesTo(p, level, name) {
  if (!p || p.kind === "gap") return false;
  if (p.scope === "global") return true;
  if (p.scope === "germany") return level === "global" || level === "europe" ? name === "Germany" : true;
  if (p.scope === "brandenburg" || p.scope === "berlin") return name === S.D.lv[p.scope].name;
  return false;
}

function mini(points) {
  const pts = points.slice(-24), vals = pts.map((q) => q.wert);
  let lo = Math.min(...vals), hi = Math.max(...vals); if (lo === hi) { lo -= 1; hi += 1; }
  const d = pts.map((q, i) => `${i ? "L" : "M"}${((i * 100) / Math.max(pts.length - 1, 1)).toFixed(1)},${(22 - ((q.wert - lo) / (hi - lo)) * 20).toFixed(1)}`).join(" ");
  return `<svg class="mini" viewBox="0 0 100 24" aria-hidden="true"><path d="${d}"/></svg>`;
}

function arrow(c) { return c == null ? "" : c > 0.05 ? "▲" : c < -0.05 ? "▼" : "■"; }
function chg(v) { return v.change == null ? "" : `${arrow(v.change)} ${v.change > 0 ? "+" : ""}${fmt(v.change, 1)}${v.changeUnit}`; }

function readout(p, level) {
  const sc = S.D.params.scopes[p.scope];
  if (p.kind === "gap") {
    return `<div class="readout gap"><div class="ro-top">${tag("gap", "ui/parameters.json")}<span class="ro-scope">${esc(sc)}</span></div>
      <strong>${esc(p.label)}</strong><div class="ro-note"><b>GAP</b> no data in this repository. Needs: ${esc(p.needs)}.</div></div>`;
  }
  const v = paramValue(p);
  if (!v) return `<div class="readout gap"><strong>${esc(p.label)}</strong><div class="ro-note"><b>GAP</b> series missing from the snapshot.</div></div>`;
  const regional = level === "brandenburg" || level === "berlin";
  let where = `Applies to: ${esc(sc)}.`;
  if (p.scope === "euro_area") where += " Not drawn per country.";
  if (regional && p.scope !== level) where = `${esc(sc)} value. <b>None for ${esc(S.D.lv[level].name)}.</b>`;
  const kind = S.when === "future" && (p.kind === "series" || p.kind === "model") ? "illustrative" : p.kind === "model" ? "model" : "measured";
  return `<div class="readout"><div class="ro-top">${tag(kind, v.file)}<span class="ro-scope">${esc(sc)}</span></div>
    <strong>${esc(p.label)}</strong>
    <div class="ro-val"><span class="big">${esc(v.display)}</span> <span class="muted">${esc(v.unit)} · ${esc(v.when)}</span></div>
    <div class="ro-chg">${esc(chg(v))} <span class="muted">${esc(v.ref)}</span></div>
    ${v.points ? mini(v.points) : ""}
    <div class="ro-note">${where}</div>${p.caution ? `<div class="ro-note caution">Check: ${esc(p.caution)}</div>` : ""}</div>`;
}

function paramTile(p, inherited) {
  const on = S.eff === p.id, v = p.kind === "gap" ? null : paramValue(p);
  const body = p.kind === "gap"
    ? `<span class="t-val muted">GAP</span>`
    : v ? `<span class="t-val">${esc(v.display)}<small> ${esc(v.unit.replace(/ \(.*/, ""))}</small></span><span class="t-chg">${esc(chg(v))}</span>` : "";
  return `<button type="button" class="tile ${on ? "on" : ""} ${inherited ? "inh" : ""} ${p.kind === "gap" ? "gapt" : ""}" data-param="${esc(p.id)}" aria-pressed="${on}"
    title="${esc(p.label)}${inherited ? " (inherited from " + esc(S.D.params.scopes[p.scope]) + ")" : ""}">
    <span class="t-name">${esc(p.short)}</span>${body}</button>`;
}

function paramSelect() {
  const sc = S.D.params.scopes, P = S.D.params.params, groups = {};
  P.forEach((p) => (groups[p.scope] ||= []).push(p));
  const opt = (p) => `<option value="${esc(p.id)}" ${S.eff === p.id ? "selected" : ""}>${esc(p.label)}${p.kind === "gap" ? " (GAP)" : ""}</option>`;
  const order = ["global", "euro_area", "germany", "brandenburg", "berlin"];
  return `<label class="paramsel">Parameter
    <select id="param" aria-label="Map parameter"><option value="coverage" ${S.eff === "coverage" ? "selected" : ""}>Data coverage</option>
    ${compareGroup()}${order.filter((k) => groups[k]).map((k) => `<optgroup label="${esc(sc[k])}">${groups[k].map(opt).join("")}</optgroup>`).join("")}</select></label>`;
}

// ---------- comparison of sub-regions (choropleth) ----------
const LEVEL_DEFAULT = {global: "c-wb-res", europe: "c-es-res", germany: "c-mastr-wind", brandenburg: "c-mastr-wind-mw", berlin: "c-mastr-roof-mw"};
const GEO_KIND = {global: "country", europe: "country", germany: "state", brandenburg: "state", berlin: "state"};
// Colour classes run from the lowest to the highest values. "good" says which end is favourable.
const PALETTES = {
  rg:  {name: "Red to green", bad2good: ["#d73027", "#fc8d59", "#fee08b", "#91cf60", "#1a9850"]},
  cvd: {name: "Colour-blind safe", bad2good: ["#ca0020", "#f4a582", "#f7f7f7", "#92c5de", "#0571b0"]},
};
const SEQ = ["#deebf7", "#9ecae1", "#6baed6", "#3182bd", "#08519c"];

function compareApplicable(c, level) { return (c.levels || []).includes(level) && S.D.regional.datasets[c.dataset]?.geo === GEO_KIND[level]; }
function compareList(level) {
  const home = level === "brandenburg" || level === "berlin" ? "germany" : level;
  return S.D.params.compare.filter((c) => compareApplicable(c, level)).sort((a, b) => (b.home === home) - (a.home === home));
}
function compareGroup() {
  const list = compareList(S.level);
  if (!list.length) return "";
  return `<optgroup label="Compare sub-regions at this level">${list.map((c) => `<option value="${esc(c.id)}" ${S.eff === c.id ? "selected" : ""}>${esc(S.D.regional.datasets[c.dataset].label)}</option>`).join("")}</optgroup>`;
}
// "auto" and parameters that cannot be compared at this level resolve to the level's default comparison.
function effectiveId(level) {
  const D = S.D;
  const cmp = D.params.compare.find((c) => c.id === S.param);
  if (S.param === "coverage") return "coverage";
  if (S.param === "auto" || (cmp && !compareApplicable(cmp, level))) return LEVEL_DEFAULT[level];
  return S.param;
}
function findParam(id) { return S.D.params.compare.find((c) => c.id === id) || S.D.params.params.find((p) => p.id === id) || null; }

function buildCompare(P, level, geo) {
  const ds = S.D.regional.datasets[P.dataset];
  const values = S.when === "future" ? S.D.demo.regional[P.dataset] || {} : ds.values;
  const keyOf = (f) => (ds.geo === "state" ? f.properties.name : f.properties.iso);
  const rows = [];
  for (const f of geo.features) {
    const key = keyOf(f), e = values[key];
    if (e) rows.push({key, name: f.properties.name, v: e.v, p: e.p});
  }
  const vals = rows.map((r) => r.v).sort((a, b) => a - b), n = vals.length;
  const th = [1, 2, 3, 4].map((k) => vals[Math.floor((k * n) / 5)]);        // quantile class edges, ties stay together
  const cls = (v) => th.filter((t) => v >= t).length;
  const pal = P.good === "neutral" ? SEQ : (PALETTES[S.pal] || PALETTES.rg).bad2good;
  const colors = P.good === "low" ? pal.slice().reverse() : pal;
  rows.forEach((r) => { r.c = cls(r.v); r.color = colors[r.c]; });
  const ranked = rows.slice().sort((a, b) => b.v - a.v);
  ranked.forEach((r, i) => (r.rank = i + 1));
  const counts = [0, 1, 2, 3, 4].map((c) => rows.filter((r) => r.c === c).length);
  return {ds, rows, byKey: Object.fromEntries(rows.map((r) => [r.key, r])), ranked, th, colors, counts, min: vals[0], max: vals[n - 1], n, median: vals[Math.floor(n / 2)]};
}
function vfmt(v, unit) { return `${fmt(v, Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2)} ${unit}`; }

function compareLegend(P, C) {
  const lo = (i) => (i === 0 ? C.min : C.th[i - 1]), hi = (i) => (i === 4 ? C.max : C.th[i]);
  const items = [0, 1, 2, 3, 4].map((i) => `<span><i class="sw" style="background:${C.colors[i]}"></i>${esc(fmt(lo(i), 2))} to ${esc(fmt(hi(i), 2))} <small>(${C.counts[i]})</small></span>`).join("");
  const fav = S.pal === "cvd" ? "Blue" : "Green";
  const meaning = P.good === "high" ? `${fav} = higher is more favourable` : P.good === "low" ? `${fav} = lower is more favourable` : "No good or bad judgment: darker = more";
  const pals = P.good === "neutral" ? "" : Object.entries(PALETTES).map(([k, v]) => `<button type="button" data-pal="${k}" aria-pressed="${S.pal === k}">${esc(v.name)}</button>`).join("");
  return `<div class="cmplegend"><div class="cl-row"><strong>${esc(C.ds.unit)}</strong> ${items}<span><i class="sw nodata"></i>no data</span></div>
    <div class="cl-row"><span class="muted">${esc(meaning)}. Five equal-sized groups by rank.</span>${pals ? `<div class="seg" role="group" aria-label="Palette">${pals}</div>` : ""}</div></div>`;
}

function compareSide(P, C, level) {
  const sel = {brandenburg: "Brandenburg", berlin: "Berlin"}[level];
  const me = sel && C.byKey[sel];
  const top = C.ranked[0], bot = C.ranked[C.n - 1];
  const periods = [...new Set(C.rows.map((r) => r.p))].sort();
  const per = periods.length > 1 ? `${periods[0]} to ${periods[periods.length - 1]}` : periods[0];
  const list = C.ranked.map((r) => `<li class="rk ${sel === r.name ? "me" : ""}" data-key="${esc(r.key)}" title="${esc(r.name)}: ${esc(vfmt(r.v, C.ds.unit))} (${esc(r.p)})">
    <span class="rk-n">${r.rank}</span><span class="rk-name">${esc(r.name)}</span>
    <span class="rk-bar"><i style="width:${Math.max(2, ((r.v - Math.min(0, C.min)) / (C.max - Math.min(0, C.min))) * 100)}%;background:${r.color}"></i></span>
    <span class="rk-v">${esc(fmt(r.v, Math.abs(r.v) >= 100 ? 0 : 2))}</span></li>`).join("");
  return `<div class="cmpside"><div class="readout static">
      <div class="ro-top">${S.when === "future" ? tag("illustrative", "ui/demo/future.json (not data)") : tag("measured", `radar/regional/regional.json (${P.dataset})`)}<span class="ro-scope">${C.n} regions · ${esc(per)}</span></div>
      <strong>${esc(C.ds.label)}</strong>
      <div class="ro-note">Highest: <b>${esc(top.name)}</b> ${esc(vfmt(top.v, C.ds.unit))}<br>Lowest: <b>${esc(bot.name)}</b> ${esc(vfmt(bot.v, C.ds.unit))}<br>Median: ${esc(vfmt(C.median, C.ds.unit))}</div>
      ${me ? `<div class="ro-note me"><b>${esc(sel)}</b>: ${esc(vfmt(me.v, C.ds.unit))}, rank ${me.rank} of ${C.n} (1 = highest)</div>` : sel ? `<div class="ro-note"><b>${esc(sel)}</b> has no value in this dataset.</div>` : ""}
      ${P.caution ? `<div class="ro-note caution">Check: ${esc(P.caution)}</div>` : ""}
      <div class="ro-note">Source: <a href="${esc(C.ds.url)}" target="_blank" rel="noopener">${esc(C.ds.source)}</a></div></div>
    <ol class="ranklist" aria-label="Regions ranked by value">${list}</ol></div>`;
}

function compareBar(level) {
  const list = compareList(level);
  if (!list.length) return "";
  const chips = list.map((c) => `<button type="button" data-param="${esc(c.id)}" aria-pressed="${S.eff === c.id}" title="${esc(S.D.regional.datasets[c.dataset].label)}">${esc(c.short)}</button>`).join("");
  return `<div class="cmpbar"><span class="muted">Compare ${level === "global" || level === "europe" ? "countries" : "German states"} by</span><div class="seg" role="group" aria-label="Comparison parameter">${chips}</div></div>`;
}

// Control bar drawn on top of the map: region, parameter, and time (current or a future horizon).
function controlsBar(level) {
  const D = S.D;
  const chips = ["global", "europe", "germany", "brandenburg", "berlin"]
    .map((id) => `<button type="button" data-level="${id}" aria-pressed="${id === level}">${esc(D.lv[id].name)}</button>`).join("");
  const when = `<div class="when" role="radiogroup" aria-label="Time">
      <label><input type="radio" name="when" value="current" ${S.when === "current" ? "checked" : ""}> Current</label>
      <label><input type="radio" name="when" value="future" ${S.when === "future" ? "checked" : ""}> Future</label>
    </div>`;
  return `<div class="mapbar"><div class="mb-row"><div class="seg" role="group" aria-label="Region">${chips}</div>${paramSelect()}${when}</div>${compareBar(level)}</div>`;
}

function mapCard(level) {
  const D = S.D;
  S.eff = effectiveId(level);
  let P = S.eff === "coverage" ? null : findParam(S.eff);
  let cmpNote = "";
  if (P && P.kind === "compare" && !compareApplicable(P, level)) { cmpNote = "This comparison is not available at this level."; P = null; }
  const cmp = !!(P && P.kind === "compare");
  // Brandenburg and Berlin have no sub-regions in this repository: compare them with the other German states.
  const v = cmp && (level === "brandenburg" || level === "berlin") ? {...VIEWS.germany, label: VIEWS[level].label} : VIEWS[level];
  const labelKey = cmp && GEO_KIND[level] === "state" ? "germany" : level;
  const k = Math.cos((v.ref * Math.PI) / 180);
  const W = (v.lon[1] - v.lon[0]) * k, H = v.lat[1] - v.lat[0];
  const X = (lon) => ((lon - v.lon[0]) * k).toFixed(3), Y = (lat) => (v.lat[1] - lat).toFixed(3);
  const geo = D.geo[v.file];
  const C = cmp ? buildCompare(P, level, geo) : null;
  const paths = [];
  for (const f of geo.features) {
    const name = f.properties.name, c = classify(level, name, f.properties);
    const polys = f.geometry.coordinates;
    let inView = false, d = "";
    for (const poly of polys) {
      for (const ring of poly) {
        d += "M" + ring.map(([lon, lat]) => {
          if (lon > v.lon[0] - 1 && lon < v.lon[1] + 1 && lat > v.lat[0] - 1 && lat < v.lat[1] + 1) inView = true;
          return X(lon) + "," + Y(lat);
        }).join("L") + "Z";
      }
    }
    if (!inView) continue;
    let cls = c.cls, tip = c.tip, style = "", key = "";
    const nav0 = c.nav;
    if (cmp) {
      key = C.ds.geo === "state" ? name : f.properties.iso;
      const row = C.byKey[key];
      const selSt = {brandenburg: "Brandenburg", berlin: "Berlin"}[level] === name;
      cls = "cmp " + (nav0 ? "nav " : "") + (selSt ? "sel " : "") + (row ? "" : "nodata");
      tip = row ? `${name}: ${vfmt(row.v, C.ds.unit)} (${row.p}). Rank ${row.rank} of ${C.n}, 1 = highest.${nav0 ? " Click to open." : ""}` : `${name}: no value in this dataset.`;
      style = row ? ` style="fill:${row.color}"` : "";
    } else if (P) {
      const hit = paramAppliesTo(P, level, name);
      cls = (c.nav ? "nav " : "") + (c.cls.includes("sel") ? "sel " : "") + (hit ? "metric" : "dim");
      if (hit) tip = `${name}: ${P.label} applies here (${D.params.scopes[P.scope]}).`;
    }
    const nav = nav0 ? ` data-level="${nav0}" tabindex="0" role="button" aria-label="${esc(tip)}"` : "";
    paths.push(`<path class="reg ${cls}"${style} d="${d}" data-tip="${esc(tip)}"${key ? ` data-key="${esc(key)}"` : ""}${nav}/>`);
  }
  const labels = (MAP_LABELS[labelKey] || []).map((l) =>
    `<text class="mlabel ${l.dim ? "dim" : ""}" x="${X(l.lon)}" y="${Y(l.lat)}" font-size="${v.fs * (l.small ? 0.7 : 1)}" text-anchor="middle">${esc(l.t)}</text>`).join("");
  const ps = (W / 70).toFixed(3);
  const defs = `<defs><pattern id="nodata" width="${ps}" height="${ps}" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="${ps}" height="${ps}" fill="var(--grid)"/><line x1="0" y1="0" x2="0" y2="${ps}" stroke="var(--muted)" stroke-opacity=".55" stroke-width="${(ps * 0.28).toFixed(3)}"/></pattern></defs>`;
  const legendItems = P && !cmp ? [["metric", `Where "${P.short}" applies`], ["dim", "Not covered by this parameter"]] : MAP_LEGEND[level];
  const legend = cmp ? compareLegend(P, C) : `<p class="maplegend">${legendItems.map(([cls, text]) => `<span><i class="sw reg ${cls}"></i>${esc(text)}</span>`).join("")}</p>`;
  const parent = D.lv[level].parent;
  const zoomOut = parent ? `<button class="btn" type="button" data-level="${parent}">Zoom out to ${esc(D.lv[parent].name)}</button>` : "";
  const {own, inherited} = paramsForLevel(level);
  const tiles = own.map((p) => paramTile(p, false)).join("") + inherited.map((p) => paramTile(p, true)).join("");
  const bar = controlsBar(level);
  const svg = `<svg class="map" viewBox="0 0 ${W.toFixed(3)} ${H.toFixed(3)}" role="group" aria-label="Map of ${esc(v.label)}" preserveAspectRatio="xMidYMid meet">${defs}${paths.join("")}${labels}</svg>`;
  const body = cmp
    ? `<div class="cmpgrid"><div class="mapframe">${bar}${svg}${legend}</div>${compareSide(P, C, level)}</div>`
    : `<div class="mapbox mapframe">${bar}${svg}${P ? readout(P, level) : ""}</div>${legend}`;
  const sub = level === "brandenburg" || level === "berlin" ? "No sub-regions exist in this repository, so the state is compared with the other German states." : "";
  return `<section class="card"><div class="card-head"><div><h2>Map: ${esc(D.lv[level].name)}</h2>
    <span class="muted">${cmp ? "Colour compares the sub-regions on the chosen parameter." : "Pick a comparison or a single parameter."} ${esc(sub)} ${esc(cmpNote)}</span></div>
    <div style="display:flex;gap:8px;align-items:center">${tag("judgment", "ui/parameters.json, ui/regions.json")}${zoomOut}<button class="btn fs-btn" type="button" data-fullscreen aria-label="Show this map full screen">⛶ Full screen</button></div></div>
    ${body}
    <div class="tiles" role="group" aria-label="Energy parameters (single values)">${tiles}</div>
    <p class="kv">Tiles: single national or aggregate values, with change over 12 months (the probability tile compares today with the base model). Dashed tiles are inherited. Outlines: Natural Earth, simplified (ui/geo/SOURCES.md). Small countries missing from the simplified outlines are not drawn or ranked.</p></section>`;
}
