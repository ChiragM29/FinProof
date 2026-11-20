// Decision test results for the facilitator. Uses h() from card-view.js.

const root = document.getElementById("results");
const KEY_NAME = "finproof-study-key";
let key = null;
try { key = sessionStorage.getItem(KEY_NAME); } catch { key = null; }

const share = (x) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);
const points = (x) => (x === null || x === undefined ? "–" : `${x >= 0 ? "+" : ""}${Math.round(x * 100)}`);
const ci = (c) => (c ? `${points(c[0])} to ${points(c[1])}` : "–");
const pval = (p) => (p === null || p === undefined ? "–" : p < 0.001 ? "< 0.001" : p.toFixed(3));

async function get(path) {
  const r = await fetch(path, { headers: key ? { "X-Study-Key": key } : {} });
  if (r.status === 401) {
    askKey();
    return null;
  }
  return r;
}

function askKey() {
  const input = h("input", { type: "text", placeholder: "Facilitator key", autocomplete: "off" });
  root.replaceChildren(h("form", { class: "card", onsubmit: (e) => {
    e.preventDefault();
    key = input.value.trim();
    try { sessionStorage.setItem(KEY_NAME, key); } catch { /* private window: keep it in memory */ }
    load();
  } }, h("h2", {}, "Facilitator key"), h("p", { class: "muted" }, "This server asks for a key before showing results."),
  input, h("button", { type: "submit", class: "primary wide" }, "Show results")));
}

async function load() {
  let info, res;
  try {
    info = await (await fetch("/api/study/info")).json();
    const r = await get("/api/study/results");
    if (!r) return;
    res = await r.json();
  } catch (err) {
    root.replaceChildren(h("div", { class: "error" }, `Could not load results: ${err}`));
    return;
  }
  root.replaceChildren(...render(info, res));
}

function metricRow(label, m, lowerIsBetter, raw = false) {
  if (!m) return "";
  const good = m.diff === null ? "" : (lowerIsBetter ? m.diff < 0 : m.diff > 0) ? "pos" : "neg";
  const val = (x) => (x === null || x === undefined ? "–" : raw ? Number(x).toFixed(3) : share(x));
  return h("tr", {},
    h("td", {}, label),
    h("td", { class: "num" }, val(m.no_card)),
    h("td", { class: "num" }, val(m.card)),
    h("td", { class: `num ${good}` }, m.diff === null ? "–" : raw ? `${m.diff >= 0 ? "+" : ""}${m.diff.toFixed(3)}` : `${points(m.diff)} pts`),
    h("td", { class: "num" }, raw ? (m.ci ? `${m.ci[0].toFixed(3)} to ${m.ci[1].toFixed(3)}` : "–") : ci(m.ci)),
    h("td", { class: "num" }, pval(m.p)),
    h("td", { class: "num" }, m.n));
}

function verdict(c) {
  if (c.met === null) return h("span", { class: "pending" }, "Not enough data yet");
  return c.met ? h("span", { class: "met" }, "Met") : h("span", { class: "not-met" }, "Not met");
}

function render(info, r) {
  const out = [];
  if (r.warnings.length) {
    out.push(h("div", { class: "card warn-banner" }, h("ul", { class: "plain" }, r.warnings.map((w) => h("li", {}, w)))));
  }

  out.push(h("div", { class: "card" },
    h("h2", {}, "Headline"),
    h("p", { class: "headline" }, r.headline)));

  const urls = info.participant_urls.length
    ? info.participant_urls.map((u) => h("div", {}, h("code", { class: "url" }, u)))
    : [h("div", { class: "muted" }, "No network address found.")];
  out.push(h("div", { class: "card" },
    h("h3", {}, "Running the test"),
    h("dl", { class: "kv" },
      h("dt", {}, "Tip set"), h("dd", {}, `${r.set}${r.practice ? " (practice, made-up posts)" : ""} · ${info.tips} tips · version ${r.digest}`),
      h("dt", {}, "People"), h("dd", {}, `${r.completed} finished, ${r.started} started`),
      h("dt", {}, "Groups"), h("dd", {}, Object.entries(r.groups).map(([g, n]) => `Group ${Number(g) + 1}: N = ${n}`).join(" · ")),
      h("dt", {}, "Answer log"), h("dd", {}, r.log_file),
      h("dt", {}, "Phones open"), h("dd", {}, ...urls)),
    h("p", { class: "small muted" }, "Phones can only connect if the server was started with --host 0.0.0.0 and Windows Firewall allows Python on private networks.")));

  const m = r.metrics;
  out.push(h("div", { class: "card" },
    h("h3", {}, "Main results (each person compared with themselves)"),
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Measure"), h("th", { class: "num" }, "Without card"), h("th", { class: "num" }, "With card"),
        h("th", { class: "num" }, "Difference"), h("th", { class: "num" }, "95% CI"), h("th", { class: "num" }, "p"), h("th", { class: "num" }, "People"))),
      h("tbody", {},
        metricRow("Would act on bad tips (lower is better)", m.bad_yes, true),
        metricRow("Would act on good tips", m.good_yes, false),
        metricRow("Right decisions", m.correct, false),
        metricRow("Good minus bad (telling them apart)", m.gap, false),
        metricRow("Calibration: Brier score of confidence vs outcome (lower is better)", m.brier, true, true)))),
    h("p", { class: "small muted" }, "Bad tip: the stock did worse than the Nifty 50 in the direction the post claimed, 30 days after posting. CI: bootstrap over people. p: paired sign-flip permutation test.")));

  if (r.preregistered) {
    out.push(h("div", { class: "card" },
      h("h3", {}, "Metrics fixed before any data"),
      h("ol", {}, r.preregistered.map((x) => h("li", {}, x.metric, h("span", { class: "small muted" }, ` (fixed ${x.fixed})`))))));
  }
  out.push(h("div", { class: "card" },
    h("h3", {}, "What we said in advance would count as success"),
    h("dl", { class: "kv" },
      h("dt", {}, verdict(r.criteria.h1)), h("dd", {}, r.criteria.h1.text),
      h("dt", {}, verdict(r.criteria.h2)), h("dd", {}, r.criteria.h2.text))));

  const fb = r.first_block;
  out.push(h("div", { class: "card" },
    h("h3", {}, "Check: first part only (different people, no carry-over)"),
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Measure"), h("th", { class: "num" }, "No card first"), h("th", { class: "num" }, "Card first"),
        h("th", { class: "num" }, "Difference"), h("th", { class: "num" }, "95% CI"), h("th", { class: "num" }, "p"), h("th", { class: "num" }, "People"))),
      h("tbody", {}, [["Would act on bad tips", fb.bad_yes], ["Would act on good tips", fb.good_yes]].map(([label, x]) =>
        h("tr", {}, h("td", {}, label), h("td", { class: "num" }, share(x.no_card)), h("td", { class: "num" }, share(x.card)),
          h("td", { class: "num" }, x.diff === null ? "–" : `${points(x.diff)} pts`), h("td", { class: "num" }, ci(x.ci)),
          h("td", { class: "num" }, pval(x.p)), h("td", { class: "num" }, `${x.n_no_card} / ${x.n_card}`)))))),
    h("p", { class: "small muted" }, `Median time per tip: ${r.seconds_per_tip.no_card ?? "–"} s without the card, ${r.seconds_per_tip.card ?? "–"} s with it.`)));

  out.push(h("div", { class: "card" },
    h("h3", {}, "Each tip"),
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Tip"), h("th", {}, "Set"), h("th", {}, "Outcome"), h("th", { class: "num" }, "vs Nifty, 30 days"),
        h("th", { class: "num" }, "Yes without card"), h("th", { class: "num" }, "Yes with card"))),
      h("tbody", {}, r.per_tip.map((t) => h("tr", {},
        h("td", {}, t.tip_id), h("td", {}, t.set), h("td", {}, t.label === "bad" ? "Bad" : "Good", t.clear ? "" : " (unclear)"),
        h("td", { class: `num ${t.outcome >= 0 ? "pos" : "neg"}` }, t.outcome === null ? "–" : `${points(t.outcome)} pts`),
        h("td", { class: "num" }, `${share(t.yes_no_card)} (${t.n_no_card})`),
        h("td", { class: "num" }, `${share(t.yes_card)} (${t.n_card})`))))))));

  out.push(h("div", { class: "toolbar" },
    h("button", { type: "button", class: "primary", onclick: exportCsv }, "Download answers (CSV)"),
    h("button", { type: "button", class: "chip", onclick: load }, "Refresh")));
  return out;
}

async function exportCsv() {
  const r = await get("/api/study/export.csv");
  if (!r || !r.ok) return;
  const url = URL.createObjectURL(await r.blob());
  const a = h("a", { href: url, download: "decision_test_answers.csv" });
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

load();
setInterval(() => { if (!document.hidden && !root.querySelector("form")) load(); }, 15000);
