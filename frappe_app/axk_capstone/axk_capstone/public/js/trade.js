/* AXK Trade role screens: Overview, Cooperative, Inspector, Buyer, Lot detail.
 * Vanilla DOM. Everything from the server is inserted with textContent. */
(function () {
  "use strict";

  var root = document.getElementById("xt-trade");
  if (!root) return;
  var PAGE = root.getAttribute("data-page");
  var main = document.getElementById("xt-main");
  var API = "/api/method/axk_capstone.trade_api.";
  var EXPLORER = "https://stellar.expert/explorer/testnet";
  var META = { reject_reasons: [] };

  // ---------------------------------------------------------------- helpers
  var nf = new Intl.NumberFormat("en-US");
  var nf1 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
  function rwf(v) { return v == null ? "—" : nf.format(Math.round(v)) + " RWF"; }
  function kg(v) { return v == null ? "—" : nf.format(Math.round(v)) + " kg"; }
  function short(h, n) { return h ? h.slice(0, n || 8) + "…" + h.slice(-6) : "—"; }
  function when(s) {
    if (!s || s === "None") return "—";
    var d = new Date(s.replace(" ", "T"));
    return isNaN(d) ? s : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  }

  function el(tag, props) {
    var n = document.createElement(tag);
    var kids = Array.prototype.slice.call(arguments, 2);
    Object.keys(props || {}).forEach(function (k) {
      var v = props[k];
      if (v === undefined || v === null || v === false) return;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k === "on") Object.keys(v).forEach(function (ev) { n.addEventListener(ev, v[ev]); });
      else n.setAttribute(k, v === true ? "" : v);
    });
    (function add(list) {
      list.forEach(function (kid) {
        if (kid == null || kid === false) return;
        if (Array.isArray(kid)) add(kid);
        else n.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
      });
    })(kids);
    return n;
  }

  function csrf() {
    var t = window.frappe && window.frappe.csrf_token;
    return t && t !== "None" ? t : null;
  }

  function serverMessage(j, status) {
    try {
      if (j && j._server_messages) {
        return JSON.parse(j._server_messages).map(function (m) {
          try { return JSON.parse(m).message; } catch (e) { return m; }
        }).join(" ").replace(/<[^>]+>/g, "");
      }
      if (j && j.exception) return String(j.exception).split(":").slice(-1)[0].trim();
    } catch (e) { /* fall through */ }
    return "Request failed (" + status + ")";
  }

  function api(method, params, post) {
    var url = API + method;
    var opts = { headers: { Accept: "application/json" } };
    if (post) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      if (csrf()) opts.headers["X-Frappe-CSRF-Token"] = csrf();
      opts.body = JSON.stringify(params || {});
    } else if (params) {
      url += "?" + new URLSearchParams(params);
    }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(serverMessage(j, r.status));
        return j.message;
      });
    });
  }

  // The standalone runner (scripts/server.py) reports network "offline-simulation": nothing
  // is sent to Stellar there, so the screens must not say they are signing on-chain.
  function isSim() { return META && META.network === "offline-simulation"; }

  var busy = document.getElementById("xt-busy");
  function withBusy(title, text, promise) {
    if (isSim()) { title = "Simulating (offline)"; text = "Offline simulation: nothing is sent to Stellar. Run make run-frappe for real testnet transactions."; }
    document.getElementById("xt-busy-title").textContent = title;
    document.getElementById("xt-busy-text").textContent = text;
    busy.hidden = false;
    return promise.finally(function () { busy.hidden = true; });
  }

  var toastT;
  function toast(msg, isError, link) {
    var t = document.getElementById("xt-toast");
    t.replaceChildren(document.createTextNode(msg));
    if (link) { t.append(" "); t.append(el("a", { href: link.href, target: link.external ? "_blank" : null, rel: "noopener", text: link.text })); }
    t.className = "xt-toast" + (isError ? " error" : "");
    t.hidden = false;
    clearTimeout(toastT);
    toastT = setTimeout(function () { t.hidden = true; }, isError ? 9000 : 6000);
  }

  var STATUS = {
    Registered: ["registered", "○", "Awaiting inspection"],
    Approved: ["approved", "✓", "Inspected · passed"],
    Rejected: ["rejected", "✕", "Inspected · rejected"],
    Funded: ["funded", "◷", "In escrow"],
    "In Transit": ["in-transit", "🚚", "In transit"],
    "At Port": ["at-port", "⚓", "At port / terminal"],
    Settled: ["settled", "●", "Settled"],
    Refunded: ["refunded", "↩", "Refunded"],
  };
  function pill(status) {
    var s = STATUS[status] || ["registered", "○", status];
    return el("span", { class: "xt-pill " + s[0] }, el("span", { "aria-hidden": "true", text: s[1] }), s[2]);
  }

  function tile(label, value, note) {
    return el("div", { class: "xt-tile" },
      el("div", { class: "xt-tile-label", text: label }),
      el("div", { class: "xt-tile-value", text: value }),
      note ? el("div", { class: "xt-tile-note", text: note }) : null);
  }

  function head(title, sub, right) {
    return el("div", { class: "xt-head" }, el("div", {}, el("h1", { text: title }), sub ? el("p", { text: sub }) : null), right || null);
  }

  function lotLink(r) { return "/trade/lot?name=" + encodeURIComponent(r.name); }
  function shareLink(r) { return location.origin + "/trace/lot?ref=" + encodeURIComponent(r.lot_ref); }

  function personaBar(p, extra) {
    if (!p) return el("div");
    if (p.loading) return el("div", { class: "xt-persona" }, el("div", { class: "xt-avatar xt-skel", "aria-hidden": "true" }),
      el("div", { class: "xt-persona-who" }, el("div", { class: "xt-skel xt-skel-line" }), el("div", { class: "xt-skel xt-skel-line short" })),
      el("span", { class: "xt-sr", text: "Loading wallet" }));
    var initials = p.name.split(/\s+/).slice(0, 2).map(function (w) { return w[0]; }).join("").toUpperCase();
    return el("div", { class: "xt-persona" },
      el("div", { class: "xt-avatar", "aria-hidden": "true", text: initials }),
      el("div", { class: "xt-persona-who" },
        el("b", { text: "Acting as " + p.name }),
        el("span", {}, p.role + " · ", el("a", { href: EXPLORER + "/account/" + p.address, target: "_blank", rel: "noopener", class: "xt-mono", text: short(p.address, 6) }))),
      p.rwf != null ? el("div", { class: "xt-persona-bal" }, el("b", { text: rwf(p.rwf) }), el("span", { text: "wallet balance" })) : null,
      extra || null);
  }

  function table(headers, rows, onRow, emptyText) {
    if (!rows.length) return el("div", { class: "xt-empty", text: emptyText || "Nothing here yet." });
    return el("div", { class: "xt-table-wrap" }, el("table", { class: "xt-table" },
      el("thead", {}, el("tr", {}, headers.map(function (h) { return el("th", { class: h.num ? "num" : null, text: h.label }); }))),
      el("tbody", {}, rows.map(function (r) {
        var tr = el("tr", { class: onRow ? "clickable" : null },
          headers.map(function (h) {
            var v = h.get(r);
            return el("td", { class: h.num ? "num" : null }, v instanceof Node ? v : (v == null ? "—" : String(v)));
          }));
        if (onRow) tr.addEventListener("click", function (e) { if (!e.target.closest("a,button")) onRow(r); });
        return tr;
      }))));
  }

  function field(label, control, hint) {
    return el("div", { class: "xt-field" }, el("label", { for: control.id || null, text: label }), control, hint ? el("small", { text: hint }) : null);
  }
  function input(id, attrs) { return el("input", Object.assign({ id: id, class: "xt-input" }, attrs || {})); }

  // A group of radio "chips": one choice from a short list. Returns the group node with a
  // .value getter/setter so forms can read it like any other control.
  function chips(name, label, options, value) {
    var group = el("div", { class: "xt-chips", role: "radiogroup", "aria-label": label });
    options.forEach(function (o) {
      var radio = el("input", { type: "radio", name: name, value: o, checked: o === value ? true : null });
      group.append(el("label", { class: "xt-chip" }, radio, el("span", { text: o })));
    });
    Object.defineProperty(group, "value", {
      get: function () { var c = group.querySelector("input:checked"); return c ? c.value : ""; },
      set: function (v) { group.querySelectorAll("input").forEach(function (i) { i.checked = i.value === v; }); },
    });
    return group;
  }
  function chipField(label, group, hint) {
    return el("div", { class: "xt-field" }, el("span", { class: "xt-field-label", text: label }), group, hint ? el("small", { text: hint }) : null);
  }

  // replaceChildren() would print a literal "null" for an absent optional node; drop them.
  function setMain() { main.replaceChildren.apply(main, Array.prototype.filter.call(arguments, Boolean)); }

  function txToast(prefix, lot, stepIndex) {
    var s = lot.steps[stepIndex];
    toast(prefix, false, s && s.url ? { href: s.url, text: "View transaction ↗", external: true } : null);
  }

  function fail(e) { toast(e.message || String(e), true); }

  // Personas carry live wallet balances (a Stellar call each), so the page renders from the
  // lot data first and redraws once balances arrive.
  var PERSONAS = null;
  function personasFallback() {
    return [
      { key: "coop", name: "Cooperative", role: "Cooperative" },
      { key: "inspector", name: "Inspector", role: "Inspector" },
      { key: "logistics", name: "Logistics Carrier", role: "Logistics" },
      { key: "port", name: "Port / Terminal", role: "Port / Terminal" },
      { key: "buyer", name: "Buyer", role: "Buyer" }
    ].map(function (p) { return Object.assign({ address: "", rwf: null, loading: true }, p); });
  }

  // ---------------------------------------------------------------- overview
  function renderOverview(data, personas) {
    var lots = data.lots, c = data.counts;
    var P = {}; personas.forEach(function (p) { P[p.key] = p; });

    var roles = [
      { href: "/trade/coop", icon: "🌱", title: "Cooperative", who: P.coop, items: ["Register a lot and commit its record on-chain", "Track inspection, escrow and payment", "See what members were paid"],
        count: (c.Registered || 0), countLabel: "awaiting inspection" },
      { href: "/trade/inspect", icon: "🔎", title: "Inspector", who: P.inspector, items: ["Work through the inspection queue", "Record grade, weight and moisture", "Sign pass or reject on-chain, once"],
        count: (c.Registered || 0), countLabel: "lots in your queue" },
      { href: "/trade/logistics", icon: "🚚", title: "Logistics", who: P.logistics, items: ["Assign carrier, driver and vehicle plate", "Record container seal & issue waybill", "Track transit along trade corridors"],
        count: (c.Funded || 0) + (c.Approved || 0), countLabel: "ready for transport" },
      { href: "/trade/port", icon: "⚓", title: "Port / Terminal", who: P.port, items: ["Gate-in verification and customs check", "Verify container seal against waybill", "Confirm port receipt for buyer settlement"],
        count: (c["In Transit"] || 0), countLabel: "in transit to port" },
      { href: "/trade/buy", icon: "🛒", title: "Buyer", who: P.buyer, items: ["Browse lots that passed inspection", "Lock payment in escrow for the cooperative", "Confirm delivery to release and settle"],
        count: (c.Approved || 0) + (c.Funded || 0) + (c["In Transit"] || 0) + (c["At Port"] || 0), countLabel: "active or for sale" },
    ];

    setMain(
      head("Verified trade, settled on-chain",
        "A cooperative registers a lot, an independent inspector signs it off, payment is locked in escrow, logistics seals & tracks the container, port verifies clearance, and delivery releases & splits payment to members."),
      el("div", { class: "xt-grid-3", style: "grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))" }, roles.map(function (r) {
        return el("a", { class: "xt-card xt-role", href: r.href },
          el("div", { class: "xt-role-top" }, el("div", { class: "xt-role-icon", "aria-hidden": "true", text: r.icon }),
            el("div", {}, el("h2", { text: r.title }), el("p", { style: "font-size:12px", text: r.who ? r.who.name : "" }))),
          el("ul", {}, r.items.map(function (i) { return el("li", { text: i }); })),
          el("div", { class: "xt-role-foot" }, el("span", {}, el("b", { text: String(r.count) }), " " + r.countLabel), el("span", { text: "Open →" })));
      })),
      el("div", { class: "xt-card xt-section-gap" },
        el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Lifecycle" }), el("p", { text: isSim() ? "Sample lots in the offline simulation, by stage." : "Live lots on Stellar testnet, by stage." }))),
        el("div", { class: "xt-flow" },
          flowStep(c.Registered || 0, "Registered", "waiting for inspection"),
          flowStep((c.Approved || 0) + (c.Rejected || 0) + (c.Funded || 0) + (c["In Transit"] || 0) + (c["At Port"] || 0) + (c.Settled || 0), "Inspected", (c.Rejected || 0) + " rejected"),
          flowStep(c.Funded || 0, "In escrow", "payment locked"),
          flowStep(c["In Transit"] || 0, "In transit", "carrier custody & seal"),
          flowStep(c["At Port"] || 0, "At port", "customs & gate cleared"),
          flowStep(c.Settled || 0, "Settled", "released, split & attested"))),
      el("div", { class: "xt-card xt-section-gap" },
        el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Recent activity" }), el("p", { text: "Open a lot for its on-chain timeline." }))),
        table([
          { label: "Lot", get: function (r) { return el("a", { href: lotLink(r), text: r.lot_ref }); } },
          { label: "Commodity", get: function (r) { return r.commodity; } },
          { label: "Quantity", num: true, get: function (r) { return kg(r.inspected_quantity_kg || r.quantity_kg); } },
          { label: "Status", get: function (r) { return pill(r.status); } },
          { label: "Last change", get: function (r) { return when(r.modified); } },
        ], lots.slice(0, 10), function (r) { location.href = lotLink(r); }, "No live lots yet. Start as the Cooperative and register one.")));
  }
  function flowStep(n, label, sub) {
    return el("div", { class: "xt-flow-step" }, el("b", { text: String(n) }), el("span", { text: label }), el("small", { text: sub }));
  }

  // ---------------------------------------------------------------- cooperative
  function renderCoop(data, personas) {
    var me = personas.filter(function (p) { return p.key === "coop"; })[0];
    var lots = data.lots;
    var count = function (s) { return lots.filter(function (l) { return l.status === s; }).length; };
    var settledValue = lots.filter(function (l) { return l.status === "Settled"; }).reduce(function (a, l) { return a + (l.amount_rwf || 0); }, 0);

    var commodity = chips("f-commodity", "Commodity", data.commodities, data.commodities[0]);
    var grade = chips("f-grade", "Declared grade", data.grades, "A");
    var qty = input("f-qty", { type: "number", min: "1", max: "100000", step: "1", value: "3850", required: true, inputmode: "numeric" });
    var variety = input("f-variety", { placeholder: "e.g. Bourbon Mayaguez 139", maxlength: "60" });
    var origin = input("f-origin", { value: "Huye, Southern Province", required: true, maxlength: "80" });
    var harvest = input("f-harvest", { type: "date", value: new Date().toISOString().slice(0, 10) });
    var submit = el("button", { class: "xt-btn block", type: "submit", text: "Register lot on-chain" });

    var form = el("form", { class: "xt-form", on: { submit: function (e) {
      e.preventDefault();
      submit.disabled = true;
      withBusy("Registering the lot", "The cooperative signs a commitment to this lot record in the lot registry on Stellar testnet.",
        api("register_lot", { commodity: commodity.value, quantity_kg: qty.value, declared_grade: grade.value,
          origin: origin.value, variety: variety.value, harvest_date: harvest.value }, true))
        .then(function (lot) { txToast("Registered " + lot.lot_ref + ". It is now in the inspector's queue.", lot, 0); return refresh(); })
        .catch(fail).finally(function () { submit.disabled = false; });
    } } },
      chipField("Commodity", commodity),
      chipField("Declared grade", grade),
      el("div", { class: "xt-row" }, field("Quantity (kg)", qty), field("Harvest date", harvest)),
      field("Origin", origin),
      field("Variety", variety, "Optional"),
      el("p", { class: "xt-note", text: "Only a SHA-256 digest of this record goes on-chain. The record itself stays here, so a buyer can check it later without the ledger holding your data." }),
      submit);

    var nextStep = { Registered: "Waiting for an inspector", Approved: "Listed for buyers", Rejected: "Rejected; re-register after fixing",
      Funded: "Buyer paid into escrow; deliver the lot", Settled: "Paid and split to members", Refunded: "Buyer refunded" };

    setMain(
      head("Cooperative", "Register lots, follow them through inspection and escrow, and see what members were paid."),
      personaBar(me),
      el("div", { class: "xt-tiles" },
        tile("Lots registered", String(lots.length)),
        tile("Awaiting inspection", String(count("Registered"))),
        tile("Listed for sale", String(count("Approved"))),
        tile("In escrow", String(count("Funded"))),
        tile("Settled value", rwf(settledValue), "split 40 / 40 / 20")),
      el("div", { class: "xt-grid-2" },
        el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Register a lot" }), el("p", { text: "Declare what you are selling." }))), form),
        el("div", { class: "xt-card" },
          el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "My lots" }), el("p", { text: "Newest first. Open a lot for its payment-proof chain." }))),
          table([
            { label: "Lot", get: function (r) { return el("a", { href: lotLink(r), text: r.lot_ref }); } },
            { label: "Commodity", get: function (r) { return r.commodity; } },
            { label: "Qty", num: true, get: function (r) { return kg(r.inspected_quantity_kg || r.quantity_kg); } },
            { label: "Status", get: function (r) { return pill(r.status); } },
            { label: "Next", get: function (r) { return r.status === "Rejected" && r.reject_reason ? r.reject_reason : (nextStep[r.status] || ""); } },
          ], lots, function (r) { location.href = lotLink(r); }, "No lots yet. Register your first lot with the form."))));
  }

  // ---------------------------------------------------------------- inspector
  var selectedForInspection = null;
  function renderInspect(data, personas) {
    var me = personas.filter(function (p) { return p.key === "inspector"; })[0];
    // Oldest first: the lot that has waited longest is inspected next.
    var queue = data.lots.filter(function (l) { return l.status === "Registered"; })
      .sort(function (a, b) { return (a.registered_at || "").localeCompare(b.registered_at || ""); });
    var done = data.lots.filter(function (l) { return l.inspected_at && l.inspected_at !== "None"; });
    if (!queue.some(function (l) { return l.name === selectedForInspection; })) selectedForInspection = queue.length ? queue[0].name : null;
    var current = queue.filter(function (l) { return l.name === selectedForInspection; })[0];
    var passedCount = done.filter(function (l) { return l.passed; }).length;

    var queueCards = queue.length ? el("div", { class: "xt-lotcards" }, queue.map(function (l, i) {
      return el("button", { type: "button", class: "xt-lotcard" + (l.name === selectedForInspection ? " active" : ""), "aria-pressed": l.name === selectedForInspection ? "true" : "false",
        on: { click: function () { selectedForInspection = l.name; renderInspect(data, personas); } } },
        el("div", { class: "xt-lotcard-top" }, el("div", {}, el("h3", { text: (i + 1) + ". " + l.commodity }), el("div", { class: "xt-lotcard-ref", text: l.lot_ref })), pill(l.status)),
        el("dl", {}, el("dt", { text: "Declared" }), el("dd", { text: "Grade " + l.declared_grade + " · " + kg(l.quantity_kg) }),
          el("dt", { text: "Origin" }), el("dd", { text: l.origin }),
          el("dt", { text: "Waiting since" }), el("dd", { text: when(l.registered_at) })));
    })) : el("div", { class: "xt-empty", text: "The queue is empty. New lots appear here when a cooperative registers them." });

    setMain(
      head("Inspector", "Examine registered lots and sign one inspection per lot. A pass lists the lot for buyers; a rejection is permanent and needs a reason.",
        el("p", { class: "xt-kbd-hint" }, "Keys: ", el("kbd", { text: "j" }), " / ", el("kbd", { text: "k" }), " move · ", el("kbd", { text: "a" }), " pass · ", el("kbd", { text: "r" }), " reject")),
      personaBar(me),
      el("div", { class: "xt-tiles" },
        tile("In your queue", String(queue.length), queue.length ? "oldest first" : null),
        tile("Passed", String(passedCount)),
        tile("Rejected", String(done.length - passedCount))),
      el("div", { class: "xt-grid-2b" },
        el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Inspection queue" }), el("p", { text: "Pick a lot to inspect." }))), queueCards),
        current ? inspectionForm(current) : el("div", { class: "xt-card" }, el("div", { class: "xt-empty", text: "Nothing to inspect right now." }))),
      el("div", { class: "xt-card xt-section-gap" },
        el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Your inspections" }), el("p", { text: "Signed on-chain; these cannot be changed." }))),
        table([
          { label: "Lot", get: function (r) { return el("a", { href: lotLink(r), text: r.lot_ref }); } },
          { label: "Commodity", get: function (r) { return r.commodity; } },
          { label: "Grade", get: function (r) { return r.inspected_grade; } },
          { label: "Measured", num: true, get: function (r) { return kg(r.inspected_quantity_kg); } },
          { label: "Moisture", num: true, get: function (r) { return r.moisture_pct != null ? nf1.format(r.moisture_pct) + "%" : "—"; } },
          { label: "Result", get: function (r) { return pill(r.passed ? "Approved" : "Rejected"); } },
          { label: "Reason", get: function (r) { return r.passed ? "" : (r.reject_reason || ""); } },
          { label: "Signed", get: function (r) { return when(r.inspected_at); } },
        ], done, function (r) { location.href = lotLink(r); }, "You have not signed any inspections yet.")));

    inspectKeys.queue = queue;
    inspectKeys.rerender = function () { renderInspect(data, personas); };
  }

  function inspectionForm(l) {
    var grade = chips("i-grade", "Measured grade", ["A", "B", "C"], l.declared_grade);
    var qty = input("i-qty", { type: "number", min: "1", step: "1", value: String(Math.round(l.quantity_kg)), required: true, inputmode: "numeric" });
    var moisture = input("i-moist", { type: "number", min: "0", max: "40", step: "0.1", value: "11.8", inputmode: "decimal" });
    var notes = el("textarea", { id: "i-notes", class: "xt-input", maxlength: "500", placeholder: "Sampling method, defects, anything a buyer should know" });
    var decision = chips("i-decision", "Decision", ["Pass", "Reject"], "Pass");
    decision.classList.add("xt-decision");
    var reason = chips("i-reason", "Rejection reason", META.reject_reasons || [], null);
    var reasonField = chipField("Rejection reason (required)", reason, "Structured reasons make rejections comparable across inspectors.");
    var submit = el("button", { class: "xt-btn block", type: "submit" });
    var sync = function () {
      var isPass = decision.value === "Pass";
      submit.textContent = isPass ? "Sign: pass" : "Sign: reject";
      submit.className = "xt-btn block" + (isPass ? "" : " danger");
      reasonField.hidden = isPass;
    };
    decision.addEventListener("change", sync); sync();
    inspectKeys.decide = function (v) { decision.value = v; sync(); submit.focus(); };

    var form = el("form", { class: "xt-form", on: { submit: function (e) {
      e.preventDefault();
      var ok = decision.value === "Pass";
      if (!ok && !reason.value) { toast("Choose a rejection reason first.", true); return; }
      if (!ok && !window.confirm("Reject " + l.lot_ref + " for “" + reason.value + "”? A rejection is permanent and stays on the ledger.")) return;
      submit.disabled = true;
      withBusy("Signing the inspection", "Your inspection is recorded against the lot in the registry. This can only happen once.",
        api("inspect_lot", { name: l.name, passed: ok ? 1 : 0, grade: grade.value, quantity_kg: qty.value, moisture_pct: moisture.value,
          notes: notes.value, reject_reason: ok ? null : reason.value }, true))
        .then(function (lot) { txToast(lot.lot_ref + (ok ? " passed. It is now listed for buyers." : " rejected."), lot, 1); return refresh(); })
        .catch(fail).finally(function () { submit.disabled = false; });
    } } },
      el("dl", { class: "xt-kv" },
        el("dt", { text: "Lot" }), el("dd", { class: "xt-mono", text: l.lot_ref }),
        el("dt", { text: "Cooperative" }), el("dd", { text: l.cooperative_name }),
        el("dt", { text: "Declared" }), el("dd", { text: l.commodity + " · grade " + l.declared_grade + " · " + kg(l.quantity_kg) }),
        el("dt", { text: "Origin" }), el("dd", { text: l.origin })),
      chipField("Measured grade", grade),
      el("div", { class: "xt-row" }, field("Measured quantity (kg)", qty), field("Moisture (%)", moisture)),
      field("Notes", notes, "Hashed into the report digest; not written to the ledger in plain text."),
      chipField("Decision", decision),
      reasonField,
      submit);

    return el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Inspect " + l.commodity }), el("p", { text: "What you measure is what the buyer will rely on." }))), form);
  }

  var inspectKeys = { queue: [], rerender: null, decide: null };
  document.addEventListener("keydown", function (e) {
    if (PAGE !== "inspect" || e.metaKey || e.ctrlKey || e.altKey) return;
    var t = e.target;
    if (t && t.closest && t.closest("input:not([type=radio]),textarea,[contenteditable]")) return;
    var q = inspectKeys.queue, i = q.findIndex(function (l) { return l.name === selectedForInspection; });
    if ((e.key === "j" || e.key === "k") && q.length) {
      e.preventDefault();
      i = e.key === "j" ? Math.min(q.length - 1, i + 1) : Math.max(0, i - 1);
      selectedForInspection = q[i].name;
      inspectKeys.rerender();
    } else if (e.key === "a" && inspectKeys.decide) { e.preventDefault(); inspectKeys.decide("Pass"); }
    else if (e.key === "r" && inspectKeys.decide) { e.preventDefault(); inspectKeys.decide("Reject"); }
  });

  // ---------------------------------------------------------------- logistics
  var selectedForDispatch = null;
  function renderLogistics(data, personas) {
    var me = personas.filter(function (p) { return p.key === "logistics"; })[0];
    var readyQueue = data.lots.filter(function (l) { return l.status === "Funded" || l.status === "Approved"; });
    var inTransit = data.lots.filter(function (l) { return l.status === "In Transit"; });
    var delivered = data.lots.filter(function (l) { return l.status === "At Port" || l.status === "Settled"; });

    if (!readyQueue.some(function (l) { return l.name === selectedForDispatch; })) {
      selectedForDispatch = readyQueue.length ? readyQueue[0].name : null;
    }
    var current = readyQueue.filter(function (l) { return l.name === selectedForDispatch; })[0];

    var queueCards = readyQueue.length ? el("div", { class: "xt-lotcards" }, readyQueue.map(function (l, i) {
      return el("button", { type: "button", class: "xt-lotcard" + (l.name === selectedForDispatch ? " active" : ""),
        on: { click: function () { selectedForDispatch = l.name; renderLogistics(data, personas); } } },
        el("div", { class: "xt-lotcard-top" }, el("div", {}, el("h3", { text: (i + 1) + ". " + l.commodity }), el("div", { class: "xt-lotcard-ref", text: l.lot_ref })), pill(l.status)),
        el("dl", {},
          el("dt", { text: "Quantity" }), el("dd", { text: kg(l.inspected_quantity_kg || l.quantity_kg) }),
          el("dt", { text: "Origin" }), el("dd", { text: l.origin }),
          el("dt", { text: "Cooperative" }), el("dd", { text: l.cooperative_name })));
    })) : el("div", { class: "xt-empty", text: "No lots awaiting dispatch. Lots appear here once approved or funded in escrow." });

    setMain(
      head("Logistics & Transport", "Take custody of verified goods, seal transport containers, issue cryptographic waybills, and track transit across trade corridors."),
      personaBar(me),
      el("div", { class: "xt-tiles" },
        tile("Awaiting dispatch", String(readyQueue.length)),
        tile("In transit", String(inTransit.length), "carrier custody"),
        tile("Arrived at port", String(delivered.length), "customs & gate-in cleared")),
      el("div", { class: "xt-grid-2b" },
        el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Dispatch queue" }), el("p", { text: "Select a lot to assign transport and seal." }))), queueCards),
        current ? dispatchForm(current) : el("div", { class: "xt-card" }, el("div", { class: "xt-empty", text: "Pick a lot from the queue to dispatch." }))),
      el("div", { class: "xt-card xt-section-gap" },
        el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Active transit & custody log" }), el("p", { text: "Real-time carrier custody, tamper-evident seals and waybill digests." }))),
        table([
          { label: "Lot", get: function (r) { return el("a", { href: lotLink(r), text: r.lot_ref }); } },
          { label: "Commodity", get: function (r) { return r.commodity; } },
          { label: "Carrier & Driver", get: function (r) { return (r.carrier_name || "—") + (r.driver_name ? " (" + r.driver_name + ")" : ""); } },
          { label: "Plate & Seal", get: function (r) { return (r.vehicle_plate || "—") + " · Seal " + (r.seal_number || "—"); } },
          { label: "Destination", get: function (r) { return r.destination_port || "—"; } },
          { label: "Dispatched", get: function (r) { return when(r.dispatched_at); } },
          { label: "Status", get: function (r) { return pill(r.status); } },
        ], inTransit.concat(delivered), function (r) { location.href = lotLink(r); }, "No shipments dispatched yet.")));
  }

  function dispatchForm(l) {
    var carrier = input("disp-carrier", { value: "Swift Freight Logistics (Rwanda)", required: true });
    var driver = input("disp-driver", { value: "Jean Bosco Nzeyimana", required: true });
    var plate = input("disp-plate", { value: "RAD 482B", required: true, maxlength: "12" });
    var seal = input("disp-seal", { value: "RW-SEAL-" + Math.floor(100000 + Math.random() * 900000), required: true, maxlength: "24" });
    var ports = ["Kigali Logistics Platform", "Goma Inland Port", "Mombasa Port Corridor", "Dar es Salaam Port Corridor"];
    var port = chips("disp-port", "Destination Port / Terminal", ports, ports[0]);
    var submit = el("button", { class: "xt-btn block", type: "submit", text: "Seal container & dispatch on-chain" });

    var form = el("form", { class: "xt-form", on: { submit: function (e) {
      e.preventDefault();
      submit.disabled = true;
      withBusy("Signing custody waybill", "The carrier issues an immutable waybill and commits the seal number on-chain.",
        api("dispatch_logistics", { name: l.name, carrier_name: carrier.value, driver_name: driver.value,
          vehicle_plate: plate.value, seal_number: seal.value, destination_port: port.value }, true))
        .then(function (lot) { txToast("Dispatched " + lot.lot_ref + " under seal " + seal.value + ".", lot, 3); return refresh(); })
        .catch(fail).finally(function () { submit.disabled = false; });
    } } },
      el("dl", { class: "xt-kv" },
        el("dt", { text: "Lot" }), el("dd", { class: "xt-mono", text: l.lot_ref }),
        el("dt", { text: "Commodity" }), el("dd", { text: l.commodity + " · " + kg(l.inspected_quantity_kg || l.quantity_kg) }),
        el("dt", { text: "Origin" }), el("dd", { text: l.origin })),
      field("Carrier company", carrier),
      el("div", { class: "xt-row" }, field("Driver name", driver), field("Vehicle plate", plate)),
      field("Tamper seal number", seal, "Applied at loading; will be verified byte-for-byte upon arrival at port."),
      chipField("Destination Port / Terminal", port),
      submit);

    return el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Dispatch " + l.lot_ref }), el("p", { text: "Assign transport carrier and issue waybill." }))), form);
  }

  // ---------------------------------------------------------------- port / terminal
  var selectedForPort = null;
  function renderPort(data, personas) {
    var me = personas.filter(function (p) { return p.key === "port"; })[0];
    var inTransitQueue = data.lots.filter(function (l) { return l.status === "In Transit"; });
    var atPort = data.lots.filter(function (l) { return l.status === "At Port"; });
    var settled = data.lots.filter(function (l) { return l.status === "Settled"; });

    if (!inTransitQueue.some(function (l) { return l.name === selectedForPort; })) {
      selectedForPort = inTransitQueue.length ? inTransitQueue[0].name : null;
    }
    var current = inTransitQueue.filter(function (l) { return l.name === selectedForPort; })[0];

    var queueCards = inTransitQueue.length ? el("div", { class: "xt-lotcards" }, inTransitQueue.map(function (l, i) {
      return el("button", { type: "button", class: "xt-lotcard" + (l.name === selectedForPort ? " active" : ""),
        on: { click: function () { selectedForPort = l.name; renderPort(data, personas); } } },
        el("div", { class: "xt-lotcard-top" }, el("div", {}, el("h3", { text: (i + 1) + ". " + l.commodity }), el("div", { class: "xt-lotcard-ref", text: l.lot_ref })), pill(l.status)),
        el("dl", {},
          el("dt", { text: "Carrier" }), el("dd", { text: l.carrier_name || "—" }),
          el("dt", { text: "Vehicle / Seal" }), el("dd", { text: (l.vehicle_plate || "—") + " · Seal " + (l.seal_number || "—") }),
          el("dt", { text: "Destination" }), el("dd", { text: l.destination_port || "—" }),
          el("dt", { text: "Dispatched" }), el("dd", { text: when(l.dispatched_at) })));
    })) : el("div", { class: "xt-empty", text: "No shipments currently in transit to port. Dispatch lots from Logistics first." });

    setMain(
      head("Port / Terminal", "Receive cross-border shipments, verify container seal integrity against waybills, record customs clearance, and stage goods for delivery."),
      personaBar(me),
      el("div", { class: "xt-tiles" },
        tile("Inbound expected", String(inTransitQueue.length)),
        tile("Cleared at port", String(atPort.length), "ready for delivery receipt"),
        tile("Released / settled", String(settled.length))),
      el("div", { class: "xt-grid-2b" },
        el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Inbound arrivals" }), el("p", { text: "Select an incoming shipment for gate-in inspection." }))), queueCards),
        current ? portArrivalForm(current) : el("div", { class: "xt-card" }, el("div", { class: "xt-empty", text: "Select an in-transit shipment to clear." }))),
      el("div", { class: "xt-card xt-section-gap" },
        el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Terminal inventory & customs clearances" }), el("p", { text: "Shipments cleared at gate-in with verified seals." }))),
        table([
          { label: "Lot", get: function (r) { return el("a", { href: lotLink(r), text: r.lot_ref }); } },
          { label: "Commodity", get: function (r) { return r.commodity; } },
          { label: "Port Terminal", get: function (r) { return r.port_name || "—"; } },
          { label: "Container ID", get: function (r) { return r.container_id || "—"; } },
          { label: "Customs Ref", get: function (r) { return r.customs_ref || "—"; } },
          { label: "Seal Check", get: function (r) { return r.seal_verified ? check(true, "Intact (" + r.seal_number + ")") : "—"; } },
          { label: "Arrived", get: function (r) { return when(r.port_received_at); } },
          { label: "Status", get: function (r) { return pill(r.status); } },
        ], atPort.concat(settled), function (r) { location.href = lotLink(r); }, "No cargo received at terminal yet.")));
  }

  function portArrivalForm(l) {
    var port = chips("port-name", "Port / Terminal facility", ["Kigali Logistics Platform", "Goma Inland Port", "Mombasa Port Terminal"], l.destination_port || "Kigali Logistics Platform");
    var container = input("port-container", { value: "MSKU-" + Math.floor(1000000 + Math.random() * 9000000), required: true });
    var customs = input("port-customs", { value: "RW-CUST-2026-" + Math.floor(1000 + Math.random() * 9000), required: true });
    var sealInput = input("port-seal", { value: l.seal_number || "", required: true });
    var submit = el("button", { class: "xt-btn block", type: "submit", text: "Verify seal & clear gate-in on-chain" });

    var form = el("form", { class: "xt-form", on: { submit: function (e) {
      e.preventDefault();
      if (sealInput.value.trim().toLowerCase() !== (l.seal_number || "").trim().toLowerCase()) {
        toast("Tamper Alert: Entered seal (" + sealInput.value + ") does not match manifest seal (" + l.seal_number + ")!", true);
        return;
      }
      submit.disabled = true;
      withBusy("Recording port arrival", "Verifying container seal integrity and recording customs clearance on-chain.",
        api("receive_port", { name: l.name, port_name: port.value, container_id: container.value,
          customs_ref: customs.value, seal_number: sealInput.value }, true))
        .then(function (lot) { txToast("Cleared " + lot.lot_ref + " at " + port.value + ". Ready for buyer delivery confirmation.", lot, 4); return refresh(); })
        .catch(fail).finally(function () { submit.disabled = false; });
    } } },
      el("dl", { class: "xt-kv" },
        el("dt", { text: "Lot" }), el("dd", { class: "xt-mono", text: l.lot_ref }),
        el("dt", { text: "Carrier" }), el("dd", { text: (l.carrier_name || "—") + " · " + (l.driver_name || "") }),
        el("dt", { text: "Vehicle plate" }), el("dd", { text: l.vehicle_plate || "—" }),
        el("dt", { text: "Expected seal" }), el("dd", { class: "xt-mono", style: "font-weight:700;color:var(--brand)", text: l.seal_number || "—" })),
      chipField("Port / Terminal", port),
      el("div", { class: "xt-row" }, field("Container ID", container), field("Customs entry ref", customs)),
      field("Inspected seal number at gate", sealInput, "Must match manifested seal number to guarantee no cargo tampering in transit."),
      submit);

    return el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Gate-in & Customs: " + l.lot_ref }), el("p", { text: "Inspect container and confirm seal integrity." }))), form);
  }

  // ---------------------------------------------------------------- buyer
  function renderBuy(data, personas) {
    var me = personas.filter(function (p) { return p.key === "buyer"; })[0];
    var market = data.lots.filter(function (l) { return l.status === "Approved"; });
    var mine = data.lots.filter(function (l) { return ["Funded", "In Transit", "At Port", "Settled", "Refunded"].indexOf(l.status) >= 0; });

    var topUp = el("button", { class: "xt-btn ghost small", type: "button", text: "Top up 500,000 RWF (testnet)", on: { click: function () {
      withBusy("Topping up", "The test RWF issuer pays the buyer. Testnet only; this token has no value.",
        api("top_up_buyer", { amount_rwf: 500000 }, true))
        .then(function () { toast("Added 500,000 test RWF to the buyer's wallet."); return refresh(); }).catch(fail);
    } } });

    var cards = market.length ? el("div", { class: "xt-lotcards" }, market.map(function (l) {
      return el("div", { class: "xt-lotcard", style: "cursor:default" },
        el("div", { class: "xt-lotcard-top" }, el("div", {}, el("h3", { text: l.commodity }), el("div", { class: "xt-lotcard-ref", text: l.lot_ref })), pill(l.status)),
        el("div", { class: "xt-verified", text: "✓ Inspected by " + (l.inspector_name || "an authorised inspector") }),
        el("dl", {},
          el("dt", { text: "Grade" }), el("dd", { text: l.inspected_grade + (l.inspected_grade !== l.declared_grade ? " (declared " + l.declared_grade + ")" : "") }),
          el("dt", { text: "Measured" }), el("dd", { text: kg(l.inspected_quantity_kg) }),
          el("dt", { text: "Moisture" }), el("dd", { text: l.moisture_pct != null ? nf1.format(l.moisture_pct) + "%" : "—" }),
          el("dt", { text: "Seller" }), el("dd", { text: l.cooperative_name }),
          el("dt", { text: "Origin" }), el("dd", { text: l.origin })),
        el("div", { style: "display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:auto" },
          el("div", {}, el("div", { class: "xt-tile-note", text: "Suggested price" }), el("div", { class: "xt-price", text: rwf(l.price_rwf) })),
          el("button", { class: "xt-btn small", type: "button", text: "Pay into escrow", on: { click: function () { fundDialog(l, me); } } })),
        el("div", { style: "display:flex;gap:12px;flex-wrap:wrap;font-size:12px" },
          el("a", { href: lotLink(l), text: "Inspection & record →" }),
          el("a", { href: shareLink(l), target: "_blank", rel: "noopener", text: "Public verification page ↗" })));
    })) : el("div", { class: "xt-empty", text: "No inspected lots are for sale right now." });

    setMain(
      head("Buyer", "Buy only what an inspector has signed off. Your payment waits in escrow and goes to the cooperative when you confirm delivery."),
      personaBar(me, topUp),
      el("div", { class: "xt-tiles" },
        tile("Inspected lots for sale", String(market.length)),
        tile("Active shipments", String(mine.filter(function (l) { return l.status === "Funded" || l.status === "In Transit" || l.status === "At Port"; }).length)),
        tile("Settled purchases", String(mine.filter(function (l) { return l.status === "Settled"; }).length))),
      el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Inspected lots for sale" }), el("p", { text: "Uninspected and rejected lots never appear here, and the escrow contract refuses them anyway." }))), cards),
      el("div", { class: "xt-card xt-section-gap" },
        el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "My purchases" }), el("p", { text: "Confirm delivery once the goods arrive. That releases escrow, pays members and attests the trade." }))),
        table([
          { label: "Lot", get: function (r) { return el("a", { href: lotLink(r), text: r.lot_ref }); } },
          { label: "Commodity", get: function (r) { return r.commodity; } },
          { label: "Amount", num: true, get: function (r) { return rwf(r.amount_rwf); } },
          { label: "Status", get: function (r) { return pill(r.status); } },
          { label: "", get: function (r) {
            if (r.status === "At Port" || r.status === "In Transit" || r.status === "Funded") {
              return el("button", {
                class: "xt-btn small" + (r.status === "At Port" ? "" : " ghost"),
                type: "button",
                text: r.status === "At Port" ? "Confirm delivery (at port)" : "Confirm delivery",
                on: { click: function () { confirmDelivery(r); } }
              });
            }
            return el("span", { style: "display:inline-flex;gap:10px" },
              el("button", { class: "xt-btn ghost small", type: "button", text: "Download record", on: { click: function () { downloadRecord(r.name); } } }),
              el("button", { class: "xt-btn ghost small", type: "button", text: "Copy share link", on: { click: function () { copyShare(r); } } }));
          } },
        ], mine, function (r) { location.href = lotLink(r); }, "No purchases yet. Pay into escrow for an inspected lot above.")));
  }

  function fundDialog(l, me) {
    var amount = input("d-amount", { type: "number", min: "1", step: "1", value: String(l.price_rwf), required: true, inputmode: "numeric" });
    var dlg = el("dialog", { class: "xt-dialog", "aria-labelledby": "d-title" });
    var cancel = el("button", { class: "xt-btn ghost", type: "button", text: "Cancel", on: { click: function () { dlg.close(); } } });
    var go = el("button", { class: "xt-btn", type: "submit", text: "Sign and pay into escrow" });
    dlg.append(el("form", { method: "dialog", on: { submit: function (e) {
      e.preventDefault();
      if (me && me.rwf != null && Number(amount.value) > me.rwf) { toast("The buyer's wallet holds " + rwf(me.rwf) + ". Top up first.", true); return; }
      dlg.close();
      withBusy("Paying into escrow", "Buyer and AXK verifier both sign. The escrow asks the lot registry who owns this inspected lot and fixes them as the payee.",
        api("fund_lot", { name: l.name, amount_rwf: amount.value }, true))
        .then(function (lot) { txToast(rwf(lot.amount_rwf) + " is in escrow for " + lot.lot_ref + ".", lot, 2); return refresh(); })
        .catch(fail);
    } } },
      el("h2", { id: "d-title", text: "Pay into escrow" }),
      el("p", { text: l.commodity + " · " + kg(l.inspected_quantity_kg) + " · grade " + l.inspected_grade + " from " + l.cooperative_name + "." }),
      field("Amount (RWF)", amount, "Held by the escrow contract until you confirm delivery. Refundable to you after 30 days if never released."),
      el("div", { class: "xt-dialog-actions" }, cancel, go)));
    root.append(dlg);
    dlg.addEventListener("close", function () { dlg.remove(); });
    dlg.showModal();
    amount.focus();
  }

  function confirmDelivery(r) {
    if (!window.confirm("Confirm that " + r.lot_ref + " was delivered? This releases " + rwf(r.amount_rwf) + " to the cooperative.")) return;
    withBusy("Settling the trade", "Four transactions: release escrow, record the 40/40/20 split, pay members, and attest the settled trade. About half a minute.",
      api("confirm_delivery", { name: r.name }, true))
      .then(function (lot) { txToast("Settled " + lot.lot_ref + ". Members paid and the trade is attested.", lot, 6); return refresh(); })
      .catch(fail);
  }

  // Verified record: the three committed records, their digests, the on-chain ids and
  // every transaction, in one JSON file a buyer can hand to their own compliance team.
  function downloadRecord(name) {
    api("lot", { name: name }).then(function (l) {
      var out = {
        schema: "axk.verified-record/1",
        generated_at: new Date().toISOString(),
        network: isSim() ? "offline-simulation (not on-chain)" : "stellar-testnet",
        lot_ref: l.lot_ref, status: l.status, chain_lot_id: l.chain_lot_id,
        public_verification: shareLink(l),
        lot: { record: safeJSON(l.lot_record), sha256: l.lot_digest },
        inspection: l.report_record ? { record: safeJSON(l.report_record), sha256: l.report_digest } : null,
        settlement: l.settlement_record ? { record: safeJSON(l.settlement_record), sha256: l.attest_digest } : null,
        contracts: l.contracts,
        transactions: l.steps.filter(function (s) { return s.tx; }).map(function (s) { return { step: s.label, tx: s.tx, url: s.url }; }),
        how_to_verify: "sha256 of each record's canonical JSON must equal its digest; the lot digest is checkable with the lot registry's matches(lot_id, digest), the settlement digest with the attestation registry's matches(trade_id, digest).",
      };
      var blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
      var a = el("a", { href: URL.createObjectURL(blob), download: l.lot_ref + "-verified-record.json" });
      document.body.append(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    }).catch(fail);
  }
  function safeJSON(s) { try { return JSON.parse(s); } catch (e) { return s; } }

  function copyShare(r) {
    var link = shareLink(r);
    (navigator.clipboard ? navigator.clipboard.writeText(link) : Promise.reject()).then(function () {
      toast("Share link copied. It opens a read-only verification page, no login needed.", false, { href: link, text: "Open ↗", external: true });
    }, function () { window.prompt("Copy this verification link:", link); });
  }

  // ---------------------------------------------------------------- lot detail
  function renderLot(l) {
    var failedInspection = l.inspect_tx && !l.passed;
    var steps = el("ol", { class: "xt-steps" }, l.steps.map(function (s, i) {
      var done = !!s.tx;
      var bad = i === 1 && failedInspection;
      return el("li", { class: "xt-step" + (done ? (bad ? " failed" : " done") : "") },
        el("div", { class: "xt-step-dot", "aria-hidden": "true", text: done ? (bad ? "✕" : "✓") : String(i + 1) }),
        el("div", { class: "xt-step-body" }, el("b", { text: s.label }),
          done ? el("div", {}, s.url
              ? el("a", { href: s.url, target: "_blank", rel: "noopener", text: short(s.tx, 10) + " ↗" })
              : el("span", { class: "xt-mono", text: short(s.tx, 10) + " · simulated" }),
            s.at && s.at !== "None" ? " · " + when(s.at) : "")
            : el("div", { text: "Not yet" })));
    }));

    var verifyOut = el("div", { "aria-live": "polite" });
    var verifyBtn = el("button", { class: "xt-btn ghost small", type: "button", text: isSim() ? "Check records (local hashes)" : "Check records against the chain", on: { click: function () {
      verifyBtn.disabled = true;
      Promise.all([
        hashIn(l.lot_record),
        l.waybill_record ? hashIn(l.waybill_record) : Promise.resolve(null),
        l.port_receipt_record ? hashIn(l.port_receipt_record) : Promise.resolve(null),
        l.settlement_record ? hashIn(l.settlement_record) : Promise.resolve(null),
        api("verify_lot", { name: l.name }, true)
      ]).then(function (res) {
        var lines = [check(res[0] === l.lot_digest && res[4].lot_record, isSim() ? "Lot record hashes to its stored digest" : "Lot record hashes to the digest the cooperative registered on-chain")];
        if (l.waybill_record) lines.push(check(res[1] === l.waybill_digest && res[4].waybill_record, isSim() ? "Waybill record hashes to its stored digest" : "Waybill record matches the on-chain dispatch attestation"));
        if (l.port_receipt_record) lines.push(check(res[2] === l.port_receipt_digest && res[4].port_receipt_record, isSim() ? "Port receipt hashes to its stored digest" : "Port receipt matches the on-chain clearance attestation"));
        if (l.settlement_record) lines.push(check(res[3] === l.attest_digest && res[4].settlement_record, isSim() ? "Settlement record hashes to its stored digest" : "Settlement record matches the on-chain attestation"));
        verifyOut.replaceChildren.apply(verifyOut, lines);
      }).catch(fail).finally(function () { verifyBtn.disabled = false; });
    } } });

    setMain(
      el("div", { class: "xt-crumb" }, el("a", { href: "/trade", text: "Overview" }), " / Lot"),
      head(l.lot_ref, l.commodity + (l.variety ? " · " + l.variety : "") + " · " + l.origin,
        el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap" }, pill(l.status),
          el("a", { class: "xt-btn ghost small", href: shareLink(l), target: "_blank", rel: "noopener", text: "Public page ↗" }),
          el("button", { class: "xt-btn ghost small", type: "button", text: "Download record", on: { click: function () { downloadRecord(l.name); } } }))),
      l.last_error ? el("p", { class: "xt-note error", text: "Last attempt failed: " + l.last_error }) : null,
      el("div", { class: "xt-grid-2" },
        el("div", {},
          el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: isSim() ? "Timeline (simulated)" : "On-chain timeline" }), el("p", { text: isSim() ? "Offline simulation: these steps were not sent to Stellar." : "Each step links back to the prior custody, inspection and escrow transactions." }))), steps),
          el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("h2", { text: "Parties & Custody" })),
            el("dl", { class: "xt-kv" },
              el("dt", { text: "Cooperative" }), el("dd", {}, l.cooperative_name || "—", " ", acct(l.cooperative_account)),
              el("dt", { text: "Inspector" }), el("dd", {}, l.inspector_name || "—", " ", acct(l.inspector_account)),
              l.carrier_name ? el("dt", { text: "Carrier" }) : null, l.carrier_name ? el("dd", {}, l.carrier_name, l.driver_name ? " · " + l.driver_name : "", l.vehicle_plate ? " (" + l.vehicle_plate + ")" : "") : null,
              l.port_name ? el("dt", { text: "Port Terminal" }) : null, l.port_name ? el("dd", {}, l.port_name, l.container_id ? " · " + l.container_id : "") : null,
              el("dt", { text: "Buyer" }), el("dd", {}, l.buyer_name || "—", " ", acct(l.buyer_account))))),
        el("div", {},
          el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("h2", { text: "Lot & Transport" })),
            el("dl", { class: "xt-kv" },
              el("dt", { text: "Declared" }), el("dd", { text: "Grade " + l.declared_grade + " · " + kg(l.quantity_kg) }),
              el("dt", { text: "Inspected" }), el("dd", { text: l.inspect_tx ? ("Grade " + l.inspected_grade + " · " + kg(l.inspected_quantity_kg) + (l.moisture_pct != null ? " · " + nf1.format(l.moisture_pct) + "% moisture" : "")) : "Not yet" }),
              l.seal_number ? el("dt", { text: "Seal number" }) : null, l.seal_number ? el("dd", { class: "xt-mono", text: l.seal_number + (l.seal_verified ? " (verified intact ✓)" : "") }) : null,
              l.destination_port ? el("dt", { text: "Destination" }) : null, l.destination_port ? el("dd", { text: l.destination_port }) : null,
              l.reject_reason ? el("dt", { text: "Rejected for" }) : null, l.reject_reason ? el("dd", { text: l.reject_reason }) : null,
              el("dt", { text: "Escrow" }), el("dd", { text: l.amount_rwf ? rwf(l.amount_rwf) : "—" }),
              el("dt", { text: isSim() ? "Lot id (simulated)" : "On-chain lot id" }), el("dd", { class: "xt-mono", text: l.chain_lot_id || "—" }),
              l.inspection_notes ? el("dt", { text: "Inspector notes" }) : null, l.inspection_notes ? el("dd", { text: l.inspection_notes }) : null)),
          el("div", { class: "xt-card" },
            el("div", { class: "xt-card-head" }, el("div", {}, el("h2", { text: "Records and digests" }), el("p", { text: isSim() ? "Offline simulation: your browser re-hashes the records and compares them with the stored digests. Nothing is checked on-chain." : "Only the digests are on-chain. Your browser re-hashes the records; the contracts confirm the match." })), verifyBtn),
            verifyOut,
            recordBlock("Lot record", l.lot_record, l.lot_digest),
            l.report_record ? recordBlock("Inspection report", l.report_record, l.report_digest) : null,
            l.waybill_record ? recordBlock("Logistics waybill", l.waybill_record, l.waybill_digest) : null,
            l.port_receipt_record ? recordBlock("Port arrival receipt", l.port_receipt_record, l.port_receipt_digest) : null,
            l.settlement_record ? recordBlock("Settlement record", l.settlement_record, l.attest_digest) : null),
          el("div", { class: "xt-card" }, el("div", { class: "xt-card-head" }, el("h2", { text: "Contracts" })),
            el("dl", { class: "xt-kv" }, Object.keys(l.contracts).filter(function (k) { return l.contracts[k]; }).map(function (k) {
              return [el("dt", { text: k[0].toUpperCase() + k.slice(1) }), el("dd", {}, el("a", { class: "xt-mono", href: l.explorer + "/contract/" + l.contracts[k], target: "_blank", rel: "noopener", text: short(l.contracts[k], 8) + " ↗" }))];
            }))))));
  }
  function acct(a) { return a ? el("a", { class: "xt-mono", href: EXPLORER + "/account/" + a, target: "_blank", rel: "noopener", text: "(" + short(a, 4) + ")" }) : null; }
  function recordBlock(label, record, digest) {
    return el("div", { class: "xt-field", style: "margin-top:12px" }, el("span", { class: "xt-field-label", text: label }),
      el("div", { class: "xt-record", text: record || "—" }), el("small", { class: "xt-mono", text: "sha256 " + (digest || "—") }));
  }
  function check(ok, text) { return el("div", { class: "xt-check " + (ok ? "ok" : "bad"), text: (ok ? "✓ " : "✕ ") + text }); }
  function hashIn(text) {
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)).then(function (b) {
      return Array.from(new Uint8Array(b)).map(function (x) { return x.toString(16).padStart(2, "0"); }).join("");
    });
  }

  // ---------------------------------------------------------------- boot
  function navCounts(data) {
    var c = data.counts;
    var badge = {
      inspect: c.Registered || 0,
      logistics: (c.Funded || 0) + (c.Approved || 0),
      port: c["In Transit"] || 0,
      buy: (c.Approved || 0) + (c.Funded || 0) + (c["In Transit"] || 0) + (c["At Port"] || 0)
    };
    Object.keys(badge).forEach(function (k) {
      var tab = root.querySelector('.xt-tab[data-tab="' + k + '"]');
      if (!tab) return;
      var old = tab.querySelector(".xt-tab-count"); if (old) old.remove();
      if (badge[k]) tab.append(el("span", { class: "xt-tab-count", "aria-label": badge[k] + " waiting", text: String(badge[k]) }));
    });
  }

  function refresh() {
    if (PAGE === "lot") {
      var name = new URLSearchParams(location.search).get("name");
      if (!name) { setMain(el("div", { class: "xt-empty", text: "No lot chosen." })); return Promise.resolve(); }
      return Promise.all([api("lot", { name: name }), api("overview")]).then(function (r) { META = r[1]; navCounts(r[1]); renderLot(r[0]); });
    }
    var draw = function (data, personas) {
      if (PAGE === "overview") renderOverview(data, personas);
      else if (PAGE === "coop") renderCoop(data, personas);
      else if (PAGE === "inspect") renderInspect(data, personas);
      else if (PAGE === "logistics") renderLogistics(data, personas);
      else if (PAGE === "port") renderPort(data, personas);
      else if (PAGE === "buy") renderBuy(data, personas);
    };
    var personasP = api("personas");
    return api("overview").then(function (data) {
      META = data;
      navCounts(data);
      draw(data, PERSONAS || personasFallback());
      return personasP.then(function (p) {
        PERSONAS = p;
        // Redraw only if nothing is mid-edit, so a balance update never wipes a half-typed form.
        var editing = document.activeElement && main.contains(document.activeElement) && /INPUT|TEXTAREA/.test(document.activeElement.tagName);
        if (!editing) draw(data, p);
      });
    });
  }

  refresh().catch(function (e) {
    if (/sign in/i.test(e.message)) {
      var back = location.pathname + location.search;
      setMain(el("div", { class: "xt-card xt-signin" },
        el("h2", { text: "Sign in to use the trade screens" }),
        el("p", { text: "These screens sign real Stellar testnet transactions, so they need an account. Anyone can still verify a lot or browse the chain explorer without one." }),
        el("div", { class: "xt-signin-actions" },
          el("a", { class: "xt-btn", href: "/login?redirect-to=" + encodeURIComponent(back), text: "Sign in" }),
          el("a", { class: "xt-btn ghost", href: "/trace", text: "Verify a lot" }),
          el("a", { class: "xt-btn ghost", href: "/chain", text: "Chain explorer" }))));
      return;
    }
    setMain(el("div", { class: "xt-card" }, el("p", { class: "xt-note error", text: e.message })));
  });
})();
