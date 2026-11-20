// Shared card drawing for the dashboard and the decision test. Every element is built
// with textContent, never innerHTML, because titles and messages come from untrusted posts.

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const pct = (x) => (x === null || x === undefined ? "–" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`);
const signClass = (x) => (x === null || x === undefined ? "" : x >= 0 ? "pos" : "neg");
const pill = (p) => h("span", { class: `pill ${p}` }, p);
const money = (x) => `₹${Number(x).toLocaleString("en-IN")}`;

function renderCard(c) {
  const n = c.summary.warning_count;
  const post = c.post;
  const head = h("div", { class: "card" },
    h("div", { class: "summary" },
      h("div", { class: `count ${n ? "warn" : "ok"}` }, n),
      h("div", {},
        h("h2", {}, c.summary.text),
        h("div", { class: "post-meta" },
          post.kind === "youtube" ? [h("span", { class: "quote" }, `“${post.title || "Untitled video"}”`), ` · ${post.channel || "unknown channel"} · `] : "",
          `Posted ${post.posted_on} (${post.posted_on_note})`,
          post.kind === "youtube" ? ` · transcript ${post.transcript}` : "")))
  );

  const warn = h("div", { class: "card" }, h("h3", {}, "Warning signs"),
    c.warnings.length
      ? h("ul", { class: "warnings" }, c.warnings.map((w) =>
          h("li", {}, w.text, w.evidence ? h("span", { class: "ev" }, "In the post: ", w.evidence.map((e) => `“${e}”`).join(", ")) : "")))
      : h("div", { class: "fine" }, "None of the warning signs we check for were found."));

  const sebi = h("div", { class: "card" }, h("h3", {}, "SEBI registration"),
    h("p", {}, c.sebi.text),
    c.sebi.registered_name ? h("p", { class: "small" }, "Name on SEBI's list: ", h("span", { class: "quote" }, c.sebi.registered_name)) : "",
    h("p", { class: "small muted" }, c.sebi.coverage_text),
    c.payments ? h("p", { class: "small" }, c.payments.text, " ",
      h("span", { class: "ev" }, "In the post: ", c.payments.upi_ids.map((u) => `“${u.id}”`).join(", "))) : "");

  const claims = h("div", { class: "card" }, h("h3", {}, "What the post claims"),
    c.claims.length ? c.claims.map(renderClaim) : h("p", { class: "muted" }, c.no_stock_text));

  const tr = c.track_record;
  const track = h("div", { class: "card" },
    h("h3", {}, "Track record of this source ", tr.provenance ? pill(tr.provenance) : ""),
    h("p", {}, tr.text),
    tr.recent && tr.recent.length ? tipTable(tr.recent) : "");

  const prov = h("div", { class: "card" }, h("h3", {}, "Data used"),
    h("ul", { class: "provenance" }, c.data_provenance.map((d) => h("li", {}, pill(d.provenance), " ", d.what, h("span", { class: "muted" }, ` · ${d.source}`)))),
    h("p", { class: "small muted" }, c.disclaimer));

  return [head, warn, claims, sebi, track, prov];
}

function renderClaim(cl) {
  const head = h("div", { class: "stock-head" },
    h("span", { class: "sym" }, cl.symbol || `“${cl.matched_text}”`),
    cl.company ? h("span", { class: "muted" }, cl.company) : "",
    cl.renamed_from ? h("span", { class: "tag" }, `posted as ${cl.renamed_from}, renamed on NSE`) : "",
    cl.mentions > 1 ? h("span", { class: "tag" }, `${cl.mentions} mentions`) : "");
  const facts = [];
  facts.push(cl.direction_text);
  if (cl.expected_prices.length) facts.push(`Prices named in the post: ${cl.expected_prices.map(money).join(", ")}.`);
  if (cl.stop_loss) facts.push(`Stop-loss named: ${money(cl.stop_loss)}.`);
  if (cl.price_at_post) facts.push(`Price quoted at posting: ${money(cl.price_at_post)}.`);
  const body = [h("p", {}, facts.join(" "))];
  if (cl.direction_note) body.push(h("p", { class: "small muted" }, cl.direction_note));
  if (cl.price_scale_note) body.push(h("p", { class: "small muted" }, cl.price_scale_note));
  if (cl.note) body.push(h("p", { class: "small muted" }, cl.note, " Possible matches: ", cl.candidates.join(", ")));
  if (cl.after_post) body.push(afterPost(cl.after_post));
  return h("div", { class: "stock" }, head, ...body);
}

function afterPost(a) {
  const rows = Object.values(a.horizons).map((r) =>
    h("tr", {},
      h("td", {}, `${r.days} days`),
      r.status === "scored"
        ? [h("td", { class: `num ${signClass(r.stock_return)}` }, pct(r.stock_return)),
           h("td", { class: `num ${signClass(r.nifty_return)}` }, pct(r.nifty_return)),
           h("td", { class: `num ${signClass(r.excess_return)}` }, pct(r.excess_return)),
           h("td", {}, r.worked ? "Matched the claim" : "Did not match")]
        : [h("td", { colspan: 4, class: "muted" }, r.status === "pending" ? "Not enough time has passed yet" : "No price data")]));
  let reached = "";
  if (a.expected_price_reached === true) reached = `The first price named in the post was reached after ${a.days_to_expected_price} days.`;
  else if (a.expected_price_reached === false) reached = "The first price named in the post was not reached within 90 days.";
  return h("div", {},
    h("p", { class: "small" }, h("strong", {}, "What happened after this post "), pill("REAL")),
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "After"), h("th", { class: "num" }, "Stock"), h("th", { class: "num" }, "Nifty 50"),
        h("th", { class: "num" }, "Difference"), h("th", {}, "Versus the claim"))),
      h("tbody", {}, rows))),
    reached ? h("p", { class: "small" }, reached) : "");
}

function tipTable(tips) {
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", {}, "Posted"), h("th", {}, "Stock"), h("th", {}, "Claimed"),
      h("th", { class: "num" }, "Stock, 30 days"), h("th", { class: "num" }, "vs Nifty"), h("th", {}, "Result"))),
    h("tbody", {}, tips.map((t) => {
      const r = t.horizons["30"];
      return h("tr", {},
        h("td", {}, t.posted_on), h("td", {}, t.symbol), h("td", {}, t.direction === "up" ? "rise" : "fall"),
        h("td", { class: `num ${signClass(r.stock_return)}` }, pct(r.stock_return)),
        h("td", { class: `num ${signClass(r.excess_return)}` }, pct(r.excess_return)),
        h("td", {}, r.status !== "scored" ? r.status : r.worked ? "Matched" : "Did not match"));
    }))));
}


// Short card, like the one the extension shows under a YouTube video. Used in the decision test.
function renderCompactCard(c) {
  const n = c.summary.warning_count;
  const box = h("div", { class: "card compact-card" },
    h("div", { class: "compact-head" },
      h("span", { class: "logo" }, "FinProof"),
      h("span", { class: `count-pill ${n ? "warn" : "ok"}` }, c.summary.text)));
  if (c.post.as_of_text) box.append(h("p", { class: "small muted" }, c.post.as_of_text));
  if (c.warnings.length) {
    box.append(h("h4", {}, "Warning signs"),
      h("ul", { class: "warnings" }, c.warnings.map((w) =>
        h("li", {}, w.text, w.evidence ? h("span", { class: "ev" }, "In the post: ", w.evidence.map((e) => `“${e}”`).join(", ")) : ""))));
  }
  const tr = c.track_record;
  box.append(h("h4", {}, "This source's past tips ", tr.provenance ? pill(tr.provenance) : ""), h("p", {}, tr.text));
  const stocks = c.claims.filter((x) => !x.ambiguous).slice(0, 4);
  if (stocks.length) {
    box.append(h("h4", {}, "Stocks mentioned"),
      h("ul", { class: "plain" }, stocks.map((s) =>
        h("li", {}, h("strong", {}, s.symbol), s.company ? ` (${s.company})` : "", ` · ${s.direction_text}`))));
  }
  box.append(h("h4", {}, "SEBI registration"), h("p", {}, c.sebi.text));
  box.append(h("p", { class: "small muted" }, c.disclaimer));
  return box;
}
