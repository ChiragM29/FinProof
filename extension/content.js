// Shows the FinProof card above a YouTube video's description.
// Built with textContent only, inside a shadow root so YouTube's styles don't leak in.

(() => {
  const HOST_ID = "finproof-card-host";
  let currentId = null;

  const css = `
    :host { all: initial; }
    .box { font: 14px/1.45 Roboto, Arial, sans-serif; color: var(--fp-text); background: var(--fp-bg);
      border: 1px solid var(--fp-border); border-radius: 12px; padding: 12px 14px; margin: 12px 0; }
    .box { --fp-text:#0f0f0f; --fp-muted:#606060; --fp-bg:#f8f9fb; --fp-border:#e3e5e8; --fp-warn:#a4400f;
      --fp-warn-bg:#fdeee4; --fp-good:#0f7b5f; --fp-good-bg:#e3f4ee; --fp-real:#0f7b5f; --fp-syn:#7a4cc2; }
    .dark { --fp-text:#f1f1f1; --fp-muted:#aaa; --fp-bg:#1f1f1f; --fp-border:#3a3a3a; --fp-warn:#f19a64;
      --fp-warn-bg:#3a2418; --fp-good:#4cc79f; --fp-good-bg:#16302a; --fp-real:#4cc79f; --fp-syn:#b394ec; }
    .head { display:flex; align-items:center; gap:10px; cursor:pointer; }
    .brand { font-weight:800; }
    .count { font-weight:700; border-radius:999px; padding:1px 10px; }
    .count.warn { background:var(--fp-warn-bg); color:var(--fp-warn); }
    .count.ok { background:var(--fp-good-bg); color:var(--fp-good); }
    .toggle { margin-left:auto; color:var(--fp-muted); font-size:12px; }
    .body { margin-top:10px; display:grid; gap:10px; }
    .body[hidden] { display:none; }
    h4 { margin:0 0 4px; font-size:13px; }
    p { margin:0; }
    ul { margin:0; padding-left:18px; }
    li { margin:2px 0; }
    .ev { color:var(--fp-muted); font-size:12px; }
    .muted { color:var(--fp-muted); font-size:12px; }
    .pos { color:var(--fp-good); } .neg { color:var(--fp-warn); }
    .pill { font-size:10px; font-weight:700; border:1px solid; border-radius:4px; padding:0 5px; margin-left:4px; }
    .REAL { color:var(--fp-real); } .SYNTHETIC { color:var(--fp-syn); }
  `;

  function h(tag, attrs = {}, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    }
    for (const k of kids.flat()) if (k != null && k !== false && k !== "") el.append(k instanceof Node ? k : String(k));
    return el;
  }
  const pct = (x) => (x == null ? "–" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`);
  const pill = (p) => h("span", { class: `pill ${p}` }, p);

  function videoId() {
    const u = new URL(location.href);
    if (u.pathname === "/watch") return u.searchParams.get("v");
    const m = u.pathname.match(/^\/shorts\/([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  }

  function anchor() {
    return document.querySelector("ytd-watch-metadata #above-the-fold")
      || document.querySelector("#above-the-fold")
      || document.querySelector("ytd-reel-video-renderer[is-active] #overlay")
      || null;
  }

  function host() {
    let el = document.getElementById(HOST_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = HOST_ID;
      el.attachShadow({ mode: "open" });
    }
    const a = anchor();
    if (a && el.parentElement !== a.parentElement) a.parentElement.insertBefore(el, a.nextSibling);
    return el;
  }

  function render(content) {
    const el = host();
    const dark = document.documentElement.hasAttribute("dark");
    el.shadowRoot.replaceChildren(h("style", {}, css), h("div", { class: `box${dark ? " dark" : ""}` }, content));
  }

  function cardView(c) {
    const n = c.summary.warning_count;
    const body = h("div", { class: "body", hidden: n === 0 ? "" : null });
    const toggle = h("span", { class: "toggle" }, n === 0 ? "Show details" : "Hide details");
    const head = h("div", { class: "head", onclick: () => {
      body.hidden = !body.hidden;
      toggle.textContent = body.hidden ? "Show details" : "Hide details";
    } },
      h("span", { class: "brand" }, "FinProof"),
      h("span", { class: `count ${n ? "warn" : "ok"}` }, c.summary.text),
      toggle);

    if (c.warnings.length) {
      body.append(h("div", {}, h("h4", {}, "Warning signs"),
        h("ul", {}, c.warnings.map((w) => h("li", {}, w.text,
          w.evidence ? h("div", { class: "ev" }, "In the video: ", w.evidence.map((e) => `“${e}”`).join(", ")) : "")))));
    }
    const tr = c.track_record;
    body.append(h("div", {}, h("h4", {}, "This channel's past tips", tr.provenance ? pill(tr.provenance) : ""), h("p", {}, tr.text)));
    const stocks = c.claims.filter((x) => !x.ambiguous).slice(0, 4);
    if (stocks.length) {
      body.append(h("div", {}, h("h4", {}, "Stocks mentioned"),
        h("ul", {}, stocks.map((s) => {
          const r = s.after_post?.horizons?.["30"];
          return h("li", {}, h("strong", {}, s.symbol), ` · ${s.direction_text}`,
            r && r.status === "scored"
              ? h("div", { class: "ev" }, "30 days after this video: stock ", h("span", { class: r.stock_return >= 0 ? "pos" : "neg" }, pct(r.stock_return)),
                  ", Nifty 50 ", pct(r.nifty_return), " ", pill("REAL"))
              : "");
        }))));
    } else {
      body.append(h("p", { class: "muted" }, c.no_stock_text || "No NSE-listed company found."));
    }
    body.append(h("div", {}, h("h4", {}, "SEBI registration"), h("p", {}, c.sebi.text), h("p", { class: "muted" }, c.sebi.coverage_text)));
    body.append(h("p", { class: "muted" }, c.disclaimer));
    return [head, body];
  }

  async function check() {
    const id = videoId();
    if (!id) {
      document.getElementById(HOST_ID)?.remove();
      currentId = null;
      return;
    }
    if (id === currentId) return;
    currentId = id;
    // Wait for YouTube to draw the title area.
    for (let i = 0; i < 20 && !anchor(); i++) await new Promise((r) => setTimeout(r, 300));
    if (!anchor()) return;
    render([h("span", { class: "brand" }, "FinProof"), " ", h("span", { class: "muted" }, "Checking this video…")]);
    const res = await chrome.runtime.sendMessage({ type: "finproof-card", videoId: id });
    if (id !== currentId) return; // user moved on
    if (res?.disabled) return document.getElementById(HOST_ID)?.remove();
    if (res?.error) return render([h("span", { class: "brand" }, "FinProof"), " ", h("span", { class: "muted" }, res.error)]);
    render(cardView(res.card));
  }

  document.addEventListener("yt-navigate-finish", check);
  check();
})();
