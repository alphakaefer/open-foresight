// Interactive view of the open-foresight world state.
// Every number comes from window.FORESIGHT_DATA, built from the repo by build_data.py. What-if results were computed
// by the repo's own engine (one indicator flipped at a time, per k); this file only looks them up and sums them.
(function () {
  const D = window.FORESIGHT_DATA;
  const app = document.getElementById("app");
  if (!D) { app.textContent = "No data: run  python3 -B whatif/build_data.py  from the repo root first."; return; }

  const w = D.weltlage, b = D.briefing, WI = D.whatif, KOP = D.model.treiber_kopplung;
  const byId = (xs) => Object.fromEntries(xs.map((x) => [x.id, x]));
  const enS = byId(D.en.szenarien), enA = byId(D.en.anzeichen), enT = byId(D.en.treiber);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const H = w.horizonte;
  const fmtDate = (s) => (s ? s.replace("T", " ").replace(/:\d\d(\.\d+)?Z$/, " UTC") : "–");
  const gaps = new Set(w.luecken ?? []);
  const scen = w.szenarien.map((s) => ({ ...s, nameEn: enS[s.id]?.name ?? s.name, shortEn: enS[s.id]?.kurz ?? s.kurz,
    plainEn: enS[s.id]?.einfach ?? s.einfach, thesisEn: enS[s.id]?.these ?? s.these }));
  const scenById = byId(scen);
  const ind = byId(w.anzeichen);
  const kKeys = WI.k_values.map(String);

  // Display configuration (design, not model data)
  // energy_price regime -2..+2 -> label, as an ordered list (object keys like "-2" would be re-ordered by JavaScript)
  const REGIME_ORDER = [[-2, "much cheaper"], [-1, "cheaper"], [0, "neutral"], [1, "more expensive"], [2, "much more expensive"]];
  const REGIME_LABEL = Object.fromEntries(REGIME_ORDER.map(([v, l]) => [String(v), l]));
  const TOP_MOVERS = 3;

  // --- state, mirrored in the URL hash so a demo state can be shared and the back button works
  const st = { h: H[0], selected: null, whatif: null, k: String(WI.k_now) };
  function readHash() {
    const q = new URLSearchParams(location.hash.slice(1));
    st.h = H.includes(q.get("h")) ? q.get("h") : H[0];
    st.whatif = WI.results[q.get("w")] ? q.get("w") : null;
    st.k = kKeys.includes(q.get("k")) ? q.get("k") : String(WI.k_now);
    st.selected = scenById[q.get("s")] ? q.get("s") : null;
  }
  function writeHash() {
    const q = new URLSearchParams({ h: st.h });
    if (st.whatif) q.set("w", st.whatif);
    if (st.k !== String(WI.k_now)) q.set("k", st.k);
    if (st.selected) q.set("s", st.selected);
    const next = "#" + q.toString();
    if (location.hash !== next) history.pushState(null, "", next);
  }

  const current = () => (st.whatif ? WI.results[st.whatif].by_k[st.k]
    : { p: Object.fromEntries(scen.map((s) => [s.id, s.p_tag])), signals: w.signale ?? [] });
  const meanCoupling = (drivers, sid) => {
    const v = drivers.map((t) => KOP[t]?.[sid]).filter((x) => x !== undefined);
    return v.length ? v.reduce((a, c) => a + c, 0) / v.length : 0;
  };

  function bar(id, h, cur, max) {
    const today = scenById[id].p_tag[h], v = cur.p[id][h], d = v - today;
    const boost = cur.signals?.[0]?.boost?.[id];
    const tip = st.whatif
      ? `${scenById[id].nameEn}, ${h}: ${today}% today → ${v}% in this what-if${boost !== undefined ? ` (boost ${boost})` : ""}`
      : `${scenById[id].nameEn}, ${h}: ${v}% (start ${scenById[id].p_basis[h]}%)` +
        (scenById[id].spanne?.[h] ? `; a model revision could move it to ${scenById[id].spanne[h][0]}–${scenById[id].spanne[h][1]}%` : "");
    return `<div class="bar" title="${esc(tip)}"><span class="track">
        <span class="fill" style="width:${(100 * v) / max}%"></span>
        ${st.whatif ? `<span class="ghost" style="left:${(100 * today) / max}%"></span>` : ""}
      </span><b>${v}%</b><span class="d ${d > 0 ? "up" : d < 0 ? "down" : ""}">${st.whatif && d ? (d > 0 ? "+" : "") + d : ""}</span></div>`;
  }

  function whyItMoved(cur) {
    const s0 = cur.signals?.[0];
    if (!s0) return "";
    const rows = scen.map((s) => ({ id: s.id, d: cur.p[s.id][st.h] - s.p_tag[st.h], boost: s0.boost[s.id], c: meanCoupling(s0.drivers, s.id) }));
    const up = rows.filter((r) => r.d > 0).sort((a, z) => z.d - a.d).slice(0, TOP_MOVERS);
    const down = rows.filter((r) => r.d < 0).sort((a, z) => a.d - z.d).slice(0, TOP_MOVERS);
    const li = (r) => `<li><b>${esc(scenById[r.id].nameEn)}</b> <span class="sub">${esc(r.id)}</span>
      ${r.d > 0 ? "+" : ""}${r.d} pts · coupling ${esc(r.c.toFixed(3))} → boost ${esc(r.boost)}</li>`;
    return `<div class="why"><div><h4>Gains most in ${esc(st.h)}</h4><ul>${up.map(li).join("") || "<li class=\"sub\">none</li>"}</ul></div>
      <div><h4>Loses most in ${esc(st.h)}</h4><ul>${down.map(li).join("") || "<li class=\"sub\">none</li>"}</ul></div></div>
      <div class="sub">How it works: boost = exp(k × direction × strength × coupling). Each probability is multiplied by its boost,
      then all are rescaled to 100. A scenario with boost 1 can still lose a little, only because others grew.</div>`;
  }

  function render() {
    const cur = current();
    const order = [...scen].sort((a, z) => cur.p[z.id][st.h] - cur.p[a.id][st.h]);
    const max = Math.max(...scen.map((s) => Math.max(s.p_tag[st.h], cur.p[s.id][st.h])));
    let html = `<h1>open-foresight: world state</h1>
    <div class="meta">Last computed ${esc(fmtDate(w.stand))} · data as of ${esc(fmtDate(w.radar_stand))} ·
    model v${esc(w.basis.version)} (${esc(w.basis.stand)}) · model reaction to a signal (damping k) = ${esc(D.model.k)}</div>`;

    html += `<div aria-live="polite">`;
    if (st.whatif) {
      const r = WI.results[st.whatif], s0 = cur.signals[0];
      html += `<div class="note hypo"><b>HYPOTHETICAL – not a forecast.</b> What if <b>${esc(enA[st.whatif]?.text)}</b> (${esc(st.whatif)})
        switched <b>${esc(r.switch_to)}</b>?${s0 ? ` It ${s0.direction === "bestaetigend" ? "confirms" : "contradicts"}
        ${s0.drivers.map((t) => `<b>${esc(enT[t]?.name ?? t)}</b> (${esc(t)})`).join(", ")} with strength ${esc(s0.strength)}.` : ""}
        Computed by the model's engine with k = ${esc(st.k)}. <button data-act="reset">Back to today</button>${whyItMoved(cur)}</div>`;
    } else if ((w.signale ?? []).length === 0) {
      html += `<div class="note"><b>No indicator has changed since the base model of ${esc(w.basis.stand)}.</b>
      Today's probabilities are the expert starting values. Try a <b>What if?</b> on an indicator below.</div>`;
    }
    html += `</div>`;

    html += `<div class="controls"><span class="lbl">Horizon</span>${H.map((h) =>
      `<button data-h="${esc(h)}" aria-pressed="${st.h === h}">${esc(h)}</button>`).join("")}
      <span class="lbl" style="margin-left:18px">Reaction to a signal</span>
      <select data-act="k" aria-label="Reaction to a signal (damping k)">${WI.k_values.map((k) =>
        `<option value="${k}" ${String(k) === st.k ? "selected" : ""}>${k}${k === WI.k_now ? " (model)" : ""}</option>`).join("")}</select>
      ${!st.whatif && st.k !== String(WI.k_now) ? `<span class="sub">k only scales indicator changes. Today none has changed, so the
        numbers stay the same at every k. Use a <b>What if?</b> below to see k work.</span>` : ""}</div>`;

    html += `<div class="grid"><div><h2>Scenarios in ${esc(st.h)} ${st.whatif ? "– what-if vs today (grey line)" : "– probability today"}</h2>
      <table class="scen"><tbody>`;
    for (const s of order)
      html += `<tr data-s="${esc(s.id)}" class="${st.selected === s.id ? "sel" : ""}" tabindex="0" aria-selected="${st.selected === s.id}">
        <td><b>${esc(s.nameEn)}</b> <span class="sub">${esc(s.id)}</span><div class="sub">${esc(s.shortEn)}</div></td>
        <td class="barcell">${bar(s.id, st.h, cur, max)}</td></tr>`;
    html += `</tbody></table><div class="sub">Click a scenario for details. Each horizon sums to 100%.</div></div>`;
    html += `<aside class="panel">${st.selected ? detail(st.selected, cur)
      : `<p class="sub">Select a scenario to see what it means, its regime and its indicators.</p>`}</aside></div>`;

    html += indicatorsTable() + energy(cur);
    html += `<footer>Data: ${D.source.repo_files.map(esc).join(", ")}. What-ifs: ${esc(D.source.whatif_engine)}.
      Rebuild with <code>python3 -B whatif/build_data.py</code>. Starting probabilities, couplings and rules are judgments by
      the model author; the model has not yet been checked against real outcomes.</footer>`;
    app.innerHTML = html;
  }

  function indicatorsTable() {
    const closer = { ja: "closer than 3 months ago", nein: "further than 3 months ago", gleich: "same as 3 months ago" };
    let html = `<h2>Early-warning indicators</h2><table><thead><tr><th>Indicator</th><th>Today</th><th>Latest value</th>
      <th>Threshold</th><th>Distance</th><th>What if?</th></tr></thead><tbody>`;
    for (const a of w.anzeichen) {
      const z = a.zuletzt, r = WI.results[a.id];
      const status = a.art === "aussage" ? `<span class="tag">statement – for human review</span>`
        : a.status_jetzt == null || gaps.has(a.id) ? `<span class="tag">data gap</span>`
        : a.status_jetzt ? `<span class="tag on">ON</span>` : `<span class="tag">off</span>`;
      const latest = z ? `${z.wert} <span class="sub">(${esc(z.t)})</span>` : a.art === "aussage" ? `${(a.treffer ?? []).length} news hit(s)` : "–";
      const btn = r ? `<button data-w="${esc(a.id)}" aria-pressed="${st.whatif === a.id}">switch ${esc(r.switch_to)}</button>`
        : `<span class="sub">${esc(WI.skipped[a.id] ?? (a.art === "aussage" ? "statements never move a probability" : "–"))}</span>`;
      html += `<tr class="${st.whatif === a.id ? "sel" : ""}"><td>${esc(enA[a.id]?.text ?? a.text)} <span class="sub">${esc(a.id)}</span></td>
        <td>${status}${st.whatif === a.id ? `<div class="sub">what-if: ${esc(r.switch_to)}</div>` : ""}</td>
        <td class="num">${latest}</td><td class="num">${a.schwelle ?? "–"}${a.abstand_stufe ? `<div class="sub">next level ${esc(a.abstand_stufe)}</div>` : ""}</td>
        <td class="num">${a.abstand ?? "–"}${a.naeher ? `<div class="sub">${esc(closer[a.naeher] ?? a.naeher)}</div>` : ""}</td><td>${btn}</td></tr>`;
    }
    return html + `</tbody></table><div class="sub">Distance ≤ 0 means the threshold is reached. "What if?" flips one indicator at a
      time; the model's engine computed every result in advance.</div>`;
  }

  function detail(id, cur) {
    const s = scenById[id], rg = s.regime ?? {};
    const sign = (v) => (v > 0 ? "+" : "") + v;
    const link = (aid, role) => {
      const a = ind[aid]; if (!a) return "";
      const on = a.art === "aussage" ? "statement" : a.status_jetzt == null ? "data gap" : a.status_jetzt ? "ON" : "off";
      return `<li>${esc(enA[aid]?.text ?? a.text)} <span class="sub">${esc(aid)} · ${role} · ${on}</span></li>`;
    };
    return `<h3>${esc(s.nameEn)} <span class="sub">${esc(id)}</span></h3>
      <p>${esc(s.plainEn)}</p><p class="sub">${esc(s.thesisEn)}</p>
      <table class="mini"><tr><th>Horizon</th><th>Start</th><th>Today</th>${st.whatif ? "<th>What-if</th>" : ""}<th>Revision range</th></tr>
      ${H.map((h) => `<tr><td>${esc(h)}</td><td class="num">${s.p_basis[h]}%</td><td class="num">${s.p_tag[h]}%</td>
        ${st.whatif ? `<td class="num"><b>${cur.p[id][h]}%</b></td>` : ""}
        <td class="num">${s.spanne?.[h] ? `${s.spanne[h][0]}–${s.spanne[h][1]}%` : "–"}</td></tr>`).join("")}</table>
      <h4>Regime (−2 … +2)</h4><div class="regime">${Object.entries(rg).map(([k, v]) => `<span class="tag">${esc(k.replace(/_/g, " "))} ${esc(sign(v))}</span>`).join(" ")}</div>
      <h4>Indicators</h4><ul>${[...(s.anzeichen ?? []).map((a) => link(a, "supports")), ...(s.gegenzeichen ?? []).map((a) => link(a, "contradicts"))].join("")
        || `<li class="sub">none linked to this scenario directly; it moves through the drivers it is coupled to</li>`}</ul>
      <p class="sub">Starting values, regime and links are judgments by the model author.</p>`;
  }

  function energy(cur) {
    if (!b) return "";
    // Probability per energy-price level = sum of scenario probabilities with that regime (same rule as domains/lens.py)
    const sum = (src) => {
      const m = {};
      for (const s of scen) { const l = REGIME_LABEL[String(s.regime?.energy_price)] ?? String(s.regime?.energy_price); m[l] = (m[l] ?? 0) + src[s.id][st.h]; }
      return m;
    };
    const today = sum(Object.fromEntries(scen.map((s) => [s.id, s.p_tag]))), now = st.whatif ? sum(cur.p) : today;
    const known = REGIME_ORDER.map(([, l]) => l);
    const levels = known.filter((l) => l in today).concat(Object.keys(today).filter((l) => !known.includes(l)));
    const max = Math.max(...levels.map((l) => Math.max(today[l], now[l])));
    const bn = b.bottleneck;
    let h = `<h2>Energy transition in Germany – ${esc(st.h)}</h2><div class="meta">${esc(b.domain.question)}</div>
      <table><thead><tr><th>Energy price level</th><th>${st.whatif ? "What-if vs today (grey line)" : "Probability today"}</th></tr></thead><tbody>`;
    for (const l of levels) {
      const d = now[l] - today[l];
      h += `<tr><td>${esc(l)}</td><td class="barcell"><div class="bar" title="${esc(`${l}, ${st.h}: ${now[l]}%${st.whatif ? ` (today ${today[l]}%)` : ""}`)}">
        <span class="track"><span class="fill" style="width:${(100 * now[l]) / max}%"></span>${st.whatif ? `<span class="ghost" style="left:${(100 * today[l]) / max}%"></span>` : ""}</span>
        <b>${now[l]}%</b><span class="d ${d > 0 ? "up" : d < 0 ? "down" : ""}">${st.whatif && d ? (d > 0 ? "+" : "") + d : ""}</span></div></td></tr>`;
    }
    h += `</tbody></table><div class="note"><b>Binding bottleneck: ${esc(bn.binding_bottleneck)}.</b> Improving it by 50% raises usable output by
      ${esc(bn.marginal_gain[0].gain_percent)}% (next: ${esc(bn.marginal_gain[1].label)}, ${esc(bn.marginal_gain[1].gain_percent)}%). Axis states are <b>judgments</b>.</div>`;
    for (const e of b.bottleneck_evidence ?? []) if (!e.source) h += `<div class="note"><b>Source GAP</b> (${esc(e.for_axis)}): ${esc(e.source_status)}</div>`;
    return h;
  }

  // --- events
  app.addEventListener("click", (e) => {
    const t = e.target.closest("[data-h],[data-w],[data-s],[data-act]");
    if (!t) return;
    if (t.dataset.h) st.h = t.dataset.h;
    else if (t.dataset.w) { st.whatif = st.whatif === t.dataset.w ? null : t.dataset.w; window.scrollTo({ top: 0, behavior: "smooth" }); }
    else if (t.dataset.s) st.selected = st.selected === t.dataset.s ? null : t.dataset.s;
    else if (t.dataset.act === "reset") st.whatif = null;  // keep the chosen k
    else return;
    writeHash(); render();
  });
  app.addEventListener("change", (e) => { if (e.target.dataset.act === "k") { st.k = e.target.value; writeHash(); render(); } });
  app.addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && e.target.dataset.s) { e.preventDefault(); e.target.click(); } });
  window.addEventListener("popstate", () => { readHash(); render(); });
  readHash();
  render();
})();
