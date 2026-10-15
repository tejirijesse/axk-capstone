/* AXK Chain Explorer: live Stellar testnet flow, hash-chain verifier, synthetic ledger history.
 * Plain SVG, no chart library. Labels from data are inserted with textContent only. */
(function () {
  "use strict";

  const API = "/api/method/axk_capstone.api.";
  const SVG = "http://www.w3.org/2000/svg";
  const ZERO = "0".repeat(64);
  const root = document.getElementById("xt-chain");
  if (!root) return;

  const state = { live: null, overview: null, lot: null, tampered: null, tamperNote: "", tables: {} };

  // ---------- helpers ----------
  const css = (name) => getComputedStyle(root).getPropertyValue(name).trim();
  const nf = new Intl.NumberFormat("en-US");
  const nf1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
  const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 2 });
  const rwf = (v) => nf.format(Math.round(v)) + " RWF";
  const short = (h, n) => (h ? h.slice(0, n || 10) + "…" + h.slice(-6) : "—");

  function el(tag, props, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (v !== undefined && v !== null) n.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null) n.append(kid instanceof Node ? kid : document.createTextNode(kid));
    return n;
  }
  function s(tag, attrs, ...kids) {
    const n = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== undefined && v !== null) n.setAttribute(k, v);
    for (const kid of kids.flat()) if (kid != null) n.append(kid);
    return n;
  }
  function stext(attrs, str) { const t = s("text", attrs); t.textContent = str; return t; }

  async function get(method, params) {
    const q = params ? "?" + new URLSearchParams(params) : "";
    const r = await fetch(API + method + q, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(method + " " + r.status);
    return (await r.json()).message;
  }

  async function sha256(str) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  // ---------- tooltip ----------
  const tip = document.getElementById("cx-tooltip");
  function showTip(evt, value, label, rows) {
    tip.replaceChildren(el("div", { class: "tv", text: value }), el("div", { class: "tl", text: label }));
    for (const r of rows || []) {
      tip.append(el("div", { class: "row" }, el("i", { class: "key", style: "background:" + r.color }), el("span", { text: r.text })));
    }
    tip.hidden = false;
    let x, y;
    if (evt.type === "focus") {
      const b = evt.target.getBoundingClientRect();
      x = b.right; y = b.top;
    } else { x = evt.clientX; y = evt.clientY; }
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - w - 8, x + 12) + "px";
    tip.style.top = Math.max(8, y - h - 12) + "px";
  }
  const hideTip = () => { tip.hidden = true; };
  function hoverable(g, fn) {
    g.setAttribute("class", "cx-hit");
    g.setAttribute("tabindex", "0");
    g.addEventListener("pointermove", fn);
    g.addEventListener("focus", fn);
    g.addEventListener("pointerleave", hideTip);
    g.addEventListener("blur", hideTip);
  }

  function tile(label, value, note) {
    return el("div", { class: "cx-tile" },
      el("div", { class: "cx-tile-label", text: label }),
      el("div", { class: "cx-tile-value", text: value }),
      note ? el("div", { class: "cx-tile-note", text: note }) : null);
  }

  function legend(items) {
    return el("div", { class: "cx-legend" },
      items.map((i) => el("span", {}, el("i", { style: "background:" + i.color }), i.label)));
  }

  function tableFrom(headers, rows) {
    return el("table", { class: "cx-table" },
      el("thead", {}, el("tr", {}, headers.map((h, i) => el("th", { class: i ? "num" : "", text: h })))),
      el("tbody", {}, rows.map((r) => el("tr", {}, r.map((c, i) => el("td", { class: i ? "num" : "", text: c }))))));
  }

  // ---------- 1. live testnet ----------
  function kindColors() {
    return {
      "Token issued": css("--neutral-fill"),
      "Escrow funded": css("--series-1"),
      "Escrow released": css("--series-3"),
      "Split payout": css("--series-2"),
      Transfer: css("--neutral-fill"),
    };
  }

  function renderLive() {
    const d = state.live;
    const tiles = document.getElementById("live-tiles");
    const table = document.getElementById("live-table");
    const flowBox = document.getElementById("live-flow");
    if (!d || d.error) {
      const msg = d && d.error ? d.error : "Reading Stellar testnet…";
      tiles.replaceChildren(tile("Stellar testnet", "—", msg));
      flowBox.replaceChildren(el("div", { class: "cx-empty", text: msg }));
      return;
    }
    const ev = d.events;
    const sum = (k) => ev.filter((e) => e.kind === k).reduce((a, e) => a + e.amount, 0);
    const count = (k) => ev.filter((e) => e.kind === k).length;
    const funded = sum("Escrow funded"), released = sum("Escrow released");
    tiles.replaceChildren(
      tile("Latest ledger", nf.format(d.latest_ledger), "Stellar testnet"),
      tile("Escrows funded", nf.format(count("Escrow funded")), rwf(funded)),
      tile("Escrows released", nf.format(count("Escrow released")), rwf(released)),
      tile("Held in escrow", rwf(funded - released), "funded, not yet released"),
      tile("Split payouts", nf.format(count("Split payout")), rwf(sum("Split payout"))),
    );
    document.getElementById("live-meta").textContent =
      ev.length + " token events since ledger " + nf.format(d.window_start_ledger) + ". Newest first.";

    const colors = kindColors();
    const rows = ev.slice().reverse().map((e) => el("tr", {},
      el("td", { text: new Date(e.time).toLocaleString() }),
      el("td", {}, el("span", { class: "cx-kind" }, el("i", { style: "background:" + colors[e.kind] }), e.kind)),
      el("td", { text: e.from.name + " → " + e.to.name }),
      el("td", { class: "num", text: nf.format(e.amount) }),
      el("td", { class: "num", text: nf.format(e.ledger) }),
      el("td", {}, el("a", { href: e.tx_url, target: "_blank", rel: "noopener", text: short(e.tx, 8) }))));
    table.replaceChildren(
      el("thead", {}, el("tr", {}, ["Time", "Event", "From → To", "RWF", "Ledger", "Transaction"].map((h, i) =>
        el("th", { class: i === 3 || i === 4 ? "num" : "", text: h })))),
      el("tbody", {}, rows));

    renderFlow(flowBox, ev, funded, released);
    renderVerifications(d);
  }

  function renderVerifications(d) {
    const rows = d.verifications || [];
    const table = document.getElementById("verif-table");
    const summary = document.getElementById("verif-summary");
    const reg = rows.filter((r) => r.kind === "Lot registered").length;
    const passed = rows.filter((r) => r.passed === true).length;
    const failed = rows.filter((r) => r.passed === false).length;
    const waiting = Math.max(0, reg - passed - failed);
    summary.replaceChildren(
      el("span", { class: "cx-vs" }, el("b", { text: nf.format(reg) }), " registered"),
      el("span", { class: "cx-vs good" }, el("b", { text: "✓ " + nf.format(passed) }), " passed"),
      el("span", { class: "cx-vs bad" }, el("b", { text: "✕ " + nf.format(failed) }), " rejected"),
      el("span", { class: "cx-vs" }, el("b", { text: "○ " + nf.format(waiting) }), " awaiting inspection"),
      d.registry_url ? el("a", { href: d.registry_url, target: "_blank", rel: "noopener", class: "cx-vs-link", text: "Lot registry contract ↗" }) : null);
    if (!rows.length) { table.replaceChildren(); summary.append(el("div", { class: "cx-empty", text: "No lot registry activity in the RPC window yet." })); return; }
    table.replaceChildren(
      el("thead", {}, el("tr", {}, ["Time", "Event", "Lot", "Signed by", "Result", "Transaction"].map((h) => el("th", { text: h })))),
      el("tbody", {}, rows.slice().reverse().map((r) => el("tr", {},
        el("td", { text: new Date(r.time).toLocaleString() }),
        el("td", { text: r.kind }),
        el("td", {}, r.lot_ref ? el("a", { href: "/trace/lot?ref=" + encodeURIComponent(r.lot_ref), text: r.lot_ref }) : el("span", { class: "cx-mono", text: short(r.lot_id, 8) })),
        el("td", { text: r.actor.name }),
        el("td", {}, r.passed === null ? "" : el("span", { class: r.passed ? "cx-result pass" : "cx-result fail", text: r.passed ? "✓ passed" : "✕ rejected" })),
        el("td", {}, el("a", { href: r.tx_url, target: "_blank", rel: "noopener", text: short(r.tx, 8) }))))));
  }

  function renderFlow(box, ev, funded, released) {
    const payouts = {};
    ev.filter((x) => x.kind === "Split payout").forEach((e) => {
      const name = e.to.key === "coop" ? "Cooperative share" : e.to.name;
      payouts[name] = (payouts[name] || 0) + e.amount;
    });
    const held = Math.max(0, funded - released);
    if (!funded) { box.replaceChildren(el("div", { class: "cx-empty", text: "No escrow activity in the RPC window yet." })); return; }

    const W = Math.max(560, box.clientWidth || 800), H = 300, nodeW = 12, pad = 10, top = 16;
    const usable = H - top - 16;
    const cols = [0, 0.3, 0.6, 1].map((f) => 8 + f * (W - 8 - nodeW - 150));
    const scale = (v) => (v / funded) * (usable - pad * 3);

    const nodes = [];
    function place(col, items) {
      let y = top;
      items.forEach((it) => {
        if (it.v <= 0) return;
        const h = Math.max(2, scale(it.v));
        nodes.push(Object.assign({}, it, { x: cols[col], y, h }));
        y += h + pad;
      });
    }
    place(0, [{ id: "buyer", name: "Buyer", v: funded }]);
    place(1, [{ id: "escrow", name: "Escrow contracts", v: funded }]);
    place(2, [{ id: "coop", name: "Cooperative", v: released }, { id: "held", name: "Held in escrow", v: held, pending: true }]);
    place(3, Object.entries(payouts).map(([k, v]) => ({ id: "p:" + k, name: k, v })));
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const out = {}, inn = {};
    const links = [["buyer", "escrow", funded], ["escrow", "coop", released], ["escrow", "held", held]]
      .concat(Object.entries(payouts).map(([k, v]) => ["coop", "p:" + k, v]))
      .filter((l) => l[2] > 0 && byId[l[0]] && byId[l[1]]);

    const svg = s("svg", { viewBox: "0 0 " + W + " " + H });
    const ribbon = css("--series-1");
    links.forEach(([a, b, v]) => {
      const A = byId[a], B = byId[b], h = scale(v);
      const y0 = A.y + (out[a] || 0), y1 = B.y + (inn[b] || 0);
      out[a] = (out[a] || 0) + h; inn[b] = (inn[b] || 0) + h;
      const x0 = A.x + nodeW, x1 = B.x, mx = (x0 + x1) / 2;
      const d = "M" + x0 + "," + y0 + " C" + mx + "," + y0 + " " + mx + "," + y1 + " " + x1 + "," + y1 +
        " L" + x1 + "," + (y1 + h) + " C" + mx + "," + (y1 + h) + " " + mx + "," + (y0 + h) + " " + x0 + "," + (y0 + h) + " Z";
      const g = s("g", {});
      g.append(s("path", { d, class: "cx-mark", fill: B.pending ? "none" : ribbon, "fill-opacity": 0.18,
        stroke: B.pending ? css("--text-muted") : "none", "stroke-dasharray": B.pending ? "4 3" : null }));
      hoverable(g, (e) => showTip(e, rwf(v), A.name + " → " + B.name));
      svg.append(g);
    });
    nodes.forEach((n) => {
      svg.append(s("rect", { x: n.x, y: n.y, width: nodeW, height: n.h, rx: 3,
        fill: n.pending ? "none" : css("--brand"), stroke: n.pending ? css("--text-muted") : "none",
        "stroke-dasharray": n.pending ? "3 2" : null }));
      const tx = n.x + nodeW + 6, ty = n.y + Math.min(n.h / 2, 14);
      svg.append(stext({ x: tx, y: ty, "font-size": 12, "font-weight": 600, fill: css("--text-primary"), "dominant-baseline": "middle" }, n.name));
      svg.append(stext({ x: tx, y: ty + 15, "font-size": 11, fill: css("--text-secondary"), "dominant-baseline": "middle" }, rwf(n.v)));
    });
    box.replaceChildren(svg);
  }

  // ---------- 2. hash chain ----------
  const pretty = (t) => (t || "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

  async function loadLot(name) {
    state.lot = await get("lot_chain", { lot: name });
    state.tampered = null;
    document.getElementById("btn-reset").hidden = true;
    renderChain(null);
  }

  function renderChain(results) {
    const lot = state.lot.lot, events = state.lot.events;
    const list = document.getElementById("chain-list");
    const summary = document.getElementById("chain-summary");
    const brokenAt = results ? results.findIndex((r) => !r.ok) : -1;

    summary.replaceChildren(el("span", { text: lot.name + " · " + lot.commodity_type + " · " + lot.cooperative_name + " · " + events.length + " events" }));
    if (results) {
      summary.append(brokenAt === -1
        ? el("span", { class: "cx-status good", text: "✓ All " + events.length + " hashes recomputed and linked" })
        : el("span", { class: "cx-status bad", text: "✕ Chain broken at event " + (brokenAt + 1) + ": " + (events.length - brokenAt) + " events can no longer be trusted" }));
    }

    list.replaceChildren(...events.map((e, i) => {
      const r = results && results[i];
      const cls = ["cx-event", r ? (r.ok ? "ok" : "broken") : "", state.tampered === i ? "tampered" : ""].join(" ");
      const hashes = el("div", { class: "cx-hashes" },
        el("span", { text: "prev       " + short(e.prev_hash, 16) }),
        el("span", { text: "stored     " + short(e.event_hash, 16) }));
      if (r) hashes.append(el("span", { class: r.hashOk ? "" : "bad", text: "recomputed " + short(r.computed, 16) + (r.hashOk ? " ✓" : "  ≠ stored") }));
      if (r && !r.linkOk && !r.afterBreak) hashes.append(el("span", { class: "bad", text: "prev_hash does not match the event before it" }));
      if (r && r.afterBreak) hashes.append(el("span", { class: "bad", text: "unverifiable: an earlier event failed" }));
      const anchor = e.anchor_chain === "xahau" ? "anchored (synthetic Xahau ref " + short(e.xrpl_tx_hash, 6) + ")" : "off-chain";
      const mark = e.result === "pass" ? "✓ " : e.result === "fail" ? "✕ " : "◐ ";
      return el("li", { class: cls },
        el("div", { class: "cx-node", text: String(e.sequence_no) }),
        el("div", { class: "cx-event-body" },
          el("div", { class: "cx-event-top" },
            el("b", { text: pretty(e.seed_event_type) }),
            el("span", { class: "cx-result " + e.result, text: mark + e.result })),
          el("div", { class: "cx-event-meta", text: e.confirmed_at + " · " + e.actor_name + " (" + e.verifier_role + ") · " + e.location + " · " + anchor }),
          state.tampered === i ? el("div", { class: "cx-event-meta", style: "color:var(--critical-text)", text: "Tampered: " + state.tamperNote }) : null,
          hashes));
    }));
  }

  async function verify() {
    const evs = state.lot.events;
    const results = [];
    let prevComputed = ZERO, broken = false;
    for (const e of evs) {
      const computed = await sha256(e.prev_hash + e.canonical_payload + e.evidence_hash);
      const hashOk = computed === e.event_hash;
      const linkOk = e.prev_hash === prevComputed;
      const ok = !broken && hashOk && linkOk;
      results.push({ computed, hashOk, linkOk, ok, afterBreak: broken });
      if (!ok) broken = true;
      prevComputed = computed;
    }
    renderChain(results);
  }

  function tamper() {
    const evs = state.lot.events;
    const i = Math.max(1, Math.floor(evs.length / 2) - 1);
    const e = evs[i];
    const m = e.canonical_payload.match(/"qty":(-?[\d.]+)/);
    if (m) {
      const before = Number(m[1]), after = before + 500;
      e.canonical_payload = e.canonical_payload.replace(m[0], '"qty":' + after);
      state.tamperNote = "measured quantity changed from " + nf.format(before) + " kg to " + nf.format(after) + " kg";
    } else {
      e.canonical_payload = e.canonical_payload.replace('"result":"pass"', '"result":"fail"');
      state.tamperNote = "inspection result edited";
    }
    state.tampered = i;
    document.getElementById("btn-reset").hidden = false;
    verify();
  }

  // ---------- 3. synthetic history ----------
  function renderHistory() {
    const t = state.overview.tiles;
    document.getElementById("hist-tiles").replaceChildren(
      tile("Lots", nf.format(t.lots), nf.format(t.lots_anchored) + " anchored"),
      tile("Verification events", nf.format(t.events), nf.format(t.events_anchored) + " anchored"),
      tile("Hash chains intact", nf.format(t.chains_intact) + " / " + nf.format(t.lots), "linked from genesis"),
      tile("Escrows released", nf.format(t.escrows_released) + " / " + nf.format(t.escrows)),
      tile("Settled volume", usd.format(t.settled_usd), "synthetic"),
    );
    renderMonthly(); renderCompletion(); renderEscrow(); renderShare();
  }

  function axisY(svg, x0, x1, yScale, max, ticks, fmt) {
    for (let i = 0; i <= ticks; i++) {
      const v = (max / ticks) * i, y = yScale(v);
      svg.append(s("line", { x1: x0, x2: x1, y1: y, y2: y, stroke: i ? css("--grid") : css("--axis"), "stroke-width": 1 }));
      svg.append(stext({ x: x0 - 6, y, "font-size": 11, fill: css("--text-muted"), "text-anchor": "end", "dominant-baseline": "middle" }, fmt(v)));
    }
  }

  function niceMax(v) {
    const p = Math.pow(10, Math.floor(Math.log10(v))), n = v / p;
    const steps = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
    return steps.find((st) => n <= st) * p;
  }

  function renderMonthly() {
    const box = document.getElementById("chart-monthly");
    // Fill months with no events so the time axis stays even.
    const byMonth = Object.fromEntries(state.overview.monthly.map((m) => [m.month, m]));
    const first = state.overview.monthly[0].month, last = state.overview.monthly[state.overview.monthly.length - 1].month;
    const data = [];
    for (let [y, mo] = first.split("-").map(Number); ; mo === 12 ? (y++, mo = 1) : mo++) {
      const key = y + "-" + String(mo).padStart(2, "0");
      data.push(byMonth[key] || { month: key, anchored: 0, offchain: 0 });
      if (key === last) break;
    }
    const cA = css("--series-1"), cO = css("--neutral-fill");
    const W = Math.max(520, box.clientWidth || 900), H = 240, L = 40, R = 8, T = 10, B = 26;
    const max = niceMax(Math.max(...data.map((m) => m.anchored + m.offchain)));
    const y = (v) => T + (H - T - B) * (1 - v / max);
    const step = (W - L - R) / data.length, bw = Math.max(2, step - 2);
    const svg = s("svg", { viewBox: "0 0 " + W + " " + H });
    axisY(svg, L, W - R, y, max, 4, (v) => nf.format(v));
    data.forEach((m, i) => {
      const x = L + i * step + 1, g = s("g", {});
      const ya = y(m.anchored), yo = y(m.anchored + m.offchain);
      const r = Math.min(2, bw / 2);
      if (m.anchored) g.append(s("rect", { class: "cx-mark", x, y: ya, width: bw, height: y(0) - ya, fill: cA, rx: m.offchain ? 0 : r }));
      if (m.offchain) g.append(s("rect", { class: "cx-mark", x, y: yo, width: bw, height: Math.max(0, ya - yo - (m.anchored ? 2 : 0)), fill: cO, rx: r }));
      g.append(s("rect", { x: L + i * step, y: T, width: step, height: H - T - B, fill: "transparent" }));
      hoverable(g, (e) => showTip(e, nf.format(m.anchored + m.offchain) + " events", m.month,
        [{ color: cA, text: nf.format(m.anchored) + " anchored on Xahau" }, { color: cO, text: nf.format(m.offchain) + " off-chain" }]));
      svg.append(g);
      if (m.month.endsWith("-01")) svg.append(stext({ x: x + bw / 2, y: H - 8, "font-size": 11, fill: css("--text-muted"), "text-anchor": "middle" }, m.month.slice(0, 4)));
    });
    box.replaceChildren(legend([{ color: cA, label: "Anchored on Xahau" }, { color: cO, label: "Hash-chained, off-chain" }]), svg);
    state.tables["chart-monthly"] = () => tableFrom(["Month", "Anchored", "Off-chain", "Total"],
      data.map((m) => [m.month, nf.format(m.anchored), nf.format(m.offchain), nf.format(m.anchored + m.offchain)]));
  }

  function renderCompletion() {
    const box = document.getElementById("chart-completion");
    const data = state.overview.completion;
    const c = css("--series-1");
    const W = Math.max(320, box.clientWidth || 480), rowH = 44, L = 124, R = 64, H = data.length * rowH + 8;
    const max = niceMax(Math.max(...data.map((d) => d.hours)));
    const x = (v) => L + (W - L - R) * (v / max);
    const svg = s("svg", { viewBox: "0 0 " + W + " " + H });
    svg.append(s("line", { x1: L, x2: L, y1: 0, y2: H, stroke: css("--axis") }));
    data.forEach((d, i) => {
      const y = 8 + i * rowH, bh = 20, g = s("g", {});
      const w = Math.max(4, x(d.hours) - L);
      g.append(s("path", { class: "cx-mark", fill: c,
        d: "M" + L + "," + y + " h" + (w - 4) + " a4,4 0 0 1 4,4 v" + (bh - 8) + " a4,4 0 0 1 -4,4 h" + (-(w - 4)) + " Z" }));
      g.append(s("rect", { x: 0, y: y - 8, width: W, height: rowH - 4, fill: "transparent" }));
      hoverable(g, (e) => showTip(e, nf1.format(d.hours) + " h", d.label, [{ color: c, text: nf.format(d.n) + " settled orders" }]));
      svg.append(g);
      svg.append(stext({ x: L - 8, y: y + bh / 2, "font-size": 12, fill: css("--text-secondary"), "text-anchor": "end", "dominant-baseline": "middle" }, d.label));
      svg.append(stext({ x: L + w + 6, y: y + bh / 2, "font-size": 12, "font-weight": 600, fill: css("--text-primary"), "dominant-baseline": "middle" }, nf1.format(d.hours) + " h"));
    });
    box.replaceChildren(svg);
    state.tables["chart-completion"] = () => tableFrom(["Channel", "Mean hours", "Orders"], data.map((d) => [d.label, nf1.format(d.hours), nf.format(d.n)]));
  }

  function renderEscrow() {
    const box = document.getElementById("chart-escrow");
    const st = state.overview.escrow_status;
    const W = Math.max(320, box.clientWidth || 480), H = 230;
    const neutral = css("--text-secondary");
    const gap = 34, bw = Math.min(150, (W - 8 - 2 * gap) / 3), bh = 46;
    const colX = [4, 4 + bw + gap, W - 4 - bw];
    const rowY = [4, (H - bh) / 2, H - bh - 4];
    const nodes = {
      Pending: { c: 0, r: 1, label: "Created", icon: "○", color: neutral },
      Locked: { c: 1, r: 1, label: "Funded", icon: "◷", color: neutral },
      Released: { c: 2, r: 0, label: "Released", icon: "✓", color: css("--good") },
      Disputed: { c: 2, r: 1, label: "Disputed", icon: "!", color: css("--critical") },
      Cancelled: { c: 2, r: 2, label: "Refunded", icon: "↩", color: css("--serious") },
    };
    const P = (k) => ({ x: colX[nodes[k].c], y: rowY[nodes[k].r] });
    const svg = s("svg", { viewBox: "0 0 " + W + " " + H });
    svg.append(s("defs", {}, s("marker", { id: "cx-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" },
      s("path", { d: "M0,0 L10,5 L0,10 z", fill: css("--axis") }))));
    [["Pending", "Locked"], ["Locked", "Released"], ["Locked", "Disputed"], ["Locked", "Cancelled"]].forEach(([a, b]) => {
      const A = P(a), B = P(b);
      const x0 = A.x + bw, y0 = A.y + bh / 2, x1 = B.x - 2, y1 = B.y + bh / 2, mx = (x0 + x1) / 2;
      svg.append(s("path", { d: "M" + x0 + "," + y0 + " C" + mx + "," + y0 + " " + mx + "," + y1 + " " + x1 + "," + y1,
        fill: "none", stroke: css("--axis"), "stroke-width": 2, "marker-end": "url(#cx-arrow)" }));
    });
    Object.entries(nodes).forEach(([k, n]) => {
      const p = P(k), g = s("g", {}), count = st[k] || 0;
      g.append(s("rect", { class: "cx-mark", x: p.x, y: p.y, width: bw, height: bh, rx: 8, fill: css("--surface-1"), stroke: n.color, "stroke-width": 2 }));
      g.append(stext({ x: p.x + 12, y: p.y + 19, "font-size": 12, "font-weight": 600, fill: css("--text-primary") }, n.icon + "  " + n.label));
      g.append(stext({ x: p.x + 12, y: p.y + 36, "font-size": 12, fill: css("--text-secondary") }, nf.format(count) + (count === 1 ? " escrow" : " escrows")));
      hoverable(g, (e) => showTip(e, nf.format(count) + " escrows", n.label));
      svg.append(g);
    });
    box.replaceChildren(svg);
  }

  function renderShare() {
    const box = document.getElementById("chart-share");
    const groups = state.overview.channel_groups, data = state.overview.share;
    const colors = groups.map((_, i) => css("--series-" + (i + 1)));
    const W = Math.max(520, box.clientWidth || 900), rowH = 34, L = 44, R = 8, H = data.length * rowH + 4;
    const svg = s("svg", { viewBox: "0 0 " + W + " " + H });
    data.forEach((row, ri) => {
      const total = groups.reduce((a, g) => a + (row[g] || 0), 0);
      const y = 2 + ri * rowH, bh = rowH - 10;
      let x = L;
      svg.append(stext({ x: L - 8, y: y + bh / 2, "font-size": 12, fill: css("--text-secondary"), "text-anchor": "end", "dominant-baseline": "middle" }, row.year));
      const segs = groups.map((g, gi) => ({ g, gi, v: row[g] || 0 })).filter((q) => q.v);
      segs.forEach((q, si) => {
        const full = (W - L - R) * (q.v / total), w = Math.max(1, full - (si < segs.length - 1 ? 2 : 0));
        const g = s("g", {});
        g.append(s("rect", { class: "cx-mark", x, y, width: w, height: bh, fill: colors[q.gi], rx: si === segs.length - 1 ? 4 : 0 }));
        const pct = Math.round((q.v / total) * 100);
        if (w > 38) g.append(stext({ x: x + 6, y: y + bh / 2, "font-size": 11, "font-weight": 600, fill: "#0b0b0b", "dominant-baseline": "middle" }, pct + "%"));
        hoverable(g, (e) => showTip(e, pct + "%", q.g + ", " + row.year, [{ color: colors[q.gi], text: nf.format(q.v) + " of " + nf.format(total) + " settled orders" }]));
        svg.append(g);
        x += full;
      });
    });
    box.replaceChildren(legend(groups.map((g, i) => ({ color: colors[i], label: g }))), svg);
    state.tables["chart-share"] = () => tableFrom(["Year"].concat(groups, ["Total"]),
      data.map((r) => [r.year].concat(groups.map((g) => nf.format(r[g] || 0)), [nf.format(groups.reduce((a, g) => a + (r[g] || 0), 0))])));
  }

  // ---------- wiring ----------
  root.addEventListener("click", (e) => {
    const b = e.target.closest("[data-table]");
    if (!b) return;
    const id = b.getAttribute("data-table"), existing = document.getElementById(id + "-table");
    if (existing) { existing.remove(); b.textContent = "Show table"; return; }
    const mk = state.tables[id];
    if (!mk) return;
    b.after(el("div", { class: "cx-table-wrap", id: id + "-table" }, mk()));
    b.textContent = "Hide table";
  });
  document.getElementById("btn-verify").addEventListener("click", verify);
  document.getElementById("btn-tamper").addEventListener("click", tamper);
  document.getElementById("btn-reset").addEventListener("click", () => loadLot(state.lot.lot.name).then(verify));
  const picker = document.getElementById("lot-picker");
  picker.addEventListener("change", (e) => loadLot(e.target.value).then(verify));

  let resizeT;
  const rerender = () => { if (state.overview) renderHistory(); if (state.live) renderLive(); };
  window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(rerender, 150); });

  renderLive();
  get("ledger_overview").then((d) => {
    if (d.available === false) {
      // Optional dataset not installed: keep the live sections, explain the missing ones.
      ["chain-h", "hist-h"].forEach((id) => {
        const sec = document.querySelector('section[aria-labelledby="' + id + '"]');
        if (!sec) return;
        const head = sec.querySelector(".cx-section-head");
        sec.replaceChildren(head, el("div", { class: "cx-card" }, el("div", { class: "cx-empty" },
          d.reason + " The live Stellar sections above work without it. See " + d.docs + " to add it.")));
      });
      return;
    }
    state.overview = d;
    renderHistory();
    picker.replaceChildren(...d.lots.map((l) => el("option", { value: l.name, text: l.name + " · " + l.commodity + " · " + l.events + " events" })));
    if (d.lots.length) loadLot(d.lots[0].name).then(verify);
  }).catch((e) => { document.getElementById("hist-tiles").replaceChildren(tile("Ledger", "—", e.message)); });
  get("live_chain").then((d) => { state.live = d; renderLive(); })
    .catch((e) => { state.live = { error: e.message }; renderLive(); });
})();
