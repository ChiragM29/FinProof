// FinProof Forensic Command Center. Uses h(), pct(), pill(), signClass() and renderCard()
// from card-view.js and the locally bundled TradingView Lightweight Charts (v5 API).
// Everything is built with textContent, never innerHTML: posts and answers are untrusted text.

const LWC = window.LightweightCharts;
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const JSON_HEADERS = { "Content-Type": "application/json" };
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Made-up sample posts (SYNTHETIC), each with a real-looking header so auto-detection has work to do.
const SAMPLES = [
  { id: "sure-shot", label: "Telegram \"Sure Shot\"",
    text: "Forwarded from Fin Hype Calls (@FinHypeCalls)\nJune 2, 2025 9:42 AM\n🚀 SURE SHOT CALL 🚀\nBUY TATAMOTORS CMP 712 TGT 780/820 SL 690\n100% guaranteed profit. Join our VIP group before 3 pm!" },
  { id: "vip-upi", label: "Paid VIP + UPI",
    text: "[02/06/2025, 9:42 am] Stock Guru VIP: Join our VIP calls for just ₹999/month, pay to stockguru.calls@ybl\nBUY ITC CMP 418 TGT 460 SL 400" },
  { id: "hinglish", label: "Hinglish Forward",
    text: "03/02/25, 10:15 am - Rakesh Bhai: Bhai SBIN abhi le lo, operator ne bola hai big news coming. Paisa double pakka. Target 900, jaldi karo!" },
  { id: "educational", label: "\"Educational Only\" Call",
    text: "@MarketGyaanDaily · 10 Feb 2025\nFor educational purposes only, not SEBI registered.\nKOTAKBANK breakout, CMP 1930, target 2050, SL 1880" },
  { id: "history", label: "Source With History",
    text: "Forwarded from Demo Channel A (synthetic)\n4 Aug 2025\nICICIBANK looking bullish here, tgt 1500 sl 1350" },
  { id: "x-demo", label: "X post · \"leaked interview\"", link: true, text: "https://x.com/SureShotStockIN/status/1931000000000000001" },
  { id: "ig-demo", label: "Instagram reel · AI bot", link: true, text: "https://www.instagram.com/reel/FPdemoReel01/" },
  { id: "sadhna", label: "Sadhna Broadcast · BSE only", real: true,
    text: "18 Jul 2022 · SEBI case (REAL prices): Sadhna Broadcast, now Crystal Business System, BSE:CRYSTAL (scrip 540821), not listed on NSE. SEBI's interim order of 2 March 2023 says misleading YouTube videos promoted it in the second half of July 2022." },
];

const WHY = {
  guarantee: "Nobody can promise a return in the stock market. A promise of certain profit is a classic pressure line.",
  urgency: "Deadlines push readers to act before they can check who is behind the post.",
  big_promise: "Claims like \"paisa double\" or 10× gains are typical of hype posts.",
  insider: "Secret or insider news can't be checked by the reader, which is why it's used to create trust.",
  paid_group: "Paid groups ask for money before you can see the caller's record.",
  personal_upi: "Since 1 October 2025, SEBI-registered intermediaries collect payments through '@valid' UPI handles. A personal UPI ID is not one.",
  percent_promise: "Large promised returns are a common hype signal.",
  education_loophole: "Calling a post \"educational\" while naming a stock with price levels is a known way around SEBI's rules for unregistered tips.",
  volume_spike: "Unusual trading just before a post can come ahead of a pump, or from ordinary news or one large trade. FinProof shows the fact, not a verdict.",
  thin_trading: "Thinly traded stocks can be moved by a small group of traders.",
  run_up: "A sharp rise before the post means early movers may already be in.",
  fell_after: "The stock fell sharply after the post.",
  be_segment: "NSE uses the BE series for stocks under closer watch.",
  bz_segment: "NSE uses the BZ series for companies that have not met listing rules.",
  not_on_sebi_list: "Checked against FinProof's saved copy of SEBI's registered lists.",
  unverified_sebi_claim: "The post claims SEBI registration that FinProof could not confirm.",
  impersonation: "Fake clips borrow famous faces, regulators or AI-bot stories. FinProof flags the cue; it cannot verify the clip.",
  funnel: "Private channels and fixed-profit scripts move you away from public view.",
  missing_context: "A price call with no registration number and no word about risk.",
};
const MEDIA_CODES = new Set(["impersonation", "funnel", "missing_context"]);
const FLAG_NAMES = {
  impersonation: "Impersonation cue", funnel: "Scam funnel", missing_context: "Missing context", personal_upi: "Personal UPI handle",
  volume_spike: "Pre-post volume spike", paid_group: "Paid VIP group", guarantee: "Promise of certain profit",
};
const MARKET_CODES = new Set(["volume_spike", "thin_trading", "run_up", "fell_after", "be_segment", "bz_segment"]);
const CHECKS = 12; // checks behind the signal density bar
const GUARD_CITES = ["No-Advice Guard"];

const state = {
  card: null, claim: null, text: "", sample: null, range: 30, focus: null, chart: null, series: null, data: null,
  prompts: [], history: [], busy: false, user: null, journalSummary: null, sources: null, selectedChip: 0, deskView: "mentor",
  index: new Map(), url: null, health: null,
  // Clean default chart: candles, tip pin, volume and its 20D average. Everything else is one click away.
  ind: { sma20: false, ema50: false, vwap20: false, bollinger: false, levels: false, vol_avg20: false, rsi14: false, macd: false, atr14: false },
};

// ------------------------------------------------------------------ helpers
async function getJSON(url, options) {
  const r = await fetch(url, options);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.detail || `Request failed (${r.status})`), { status: r.status });
  return data;
}
const store = {
  get(k, fb) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : fb; } catch { return fb; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage blocked: memory only */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};
const fmt = (x, d = 2) => Number(x).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
function addDays(iso, n) { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
function idxAfter(rows, iso) { let lo = 0, hi = rows.length; while (lo < hi) { const m = (lo + hi) >> 1; if (rows[m].time < iso) lo = m + 1; else hi = m; } return Math.min(lo, rows.length - 1); }
function idxBefore(rows, iso) { let lo = 0, hi = rows.length; while (lo < hi) { const m = (lo + hi) >> 1; if (rows[m].time <= iso) lo = m + 1; else hi = m; } return Math.max(0, lo - 1); }
function niceDate(iso) { return new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }); }
function countUp(el, to, { decimals = 0, prefix = "", suffix = "", signed = false } = {}) {
  const show = (v) => { el.textContent = `${prefix}${signed && v >= 0 ? "+" : ""}${v.toFixed(decimals)}${suffix}`; };
  if (REDUCED || !Number.isFinite(to)) { show(to); return; }
  const t0 = performance.now(), dur = 700;
  const tick = (t) => { const k = Math.min(1, (t - t0) / dur); show(to * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(tick); };
  requestAnimationFrame(tick);
}
const icon = {
  shield: () => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("width", "14"); s.setAttribute("height", "14"); s.setAttribute("viewBox", "0 0 24 24");
    const p = document.createElementNS(s.namespaceURI, "path"); p.setAttribute("d", "M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5z"); p.setAttribute("fill", "none"); p.setAttribute("stroke", "#ef4444"); p.setAttribute("stroke-width", "2.2"); s.append(p); return s; },
  bigShield: () => { const s = icon.shield(); s.setAttribute("width", "26"); s.setAttribute("height", "26"); return s; },
};

// ------------------------------------------------------------------ scan pipeline
function stepsStart() {
  const steps = [...$$(".step")];
  $("#steps").hidden = false;
  steps.forEach((s) => s.classList.remove("run", "done"));
  let i = 0;
  steps[0].classList.add("run");
  const timer = setInterval(() => {            // visual progress while the request is in flight
    if (i >= steps.length - 1) return;
    steps[i].classList.replace("run", "done");
    i += 1;
    steps[i].classList.add("run");
  }, 100);
  return () => {                                // request finished: complete every step at once
    clearInterval(timer);
    steps.forEach((s) => { s.classList.remove("run"); s.classList.add("done"); });
  };
}

const LINK_RE = /^https?:\/\/\S+$/i;

async function runScan(text, { sample = null, posted_on = null, source = null, url = null } = {}) {
  text = (text || "").trim();
  if (!text || state.busy) return;
  state.busy = true;
  $("#scan-btn").disabled = true;
  $("#edit-pop").hidden = true;
  closeSamples();
  const done = stepsStart();
  const isLink = LINK_RE.test(text);
  try {
    if (!isLink && !url && !text.includes("\n") && text.length <= 40) {
      const hist = await fetch(`/api/price-history?q=${encodeURIComponent(text)}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
      if (hist) { done(); markScanned(); await showHistory(hist, text); return; }
    }
    const card = await getJSON("/api/analyze", { method: "POST", headers: JSON_HEADERS,
      body: JSON.stringify({ url: isLink ? text : url, text: isLink ? null : text, posted_on, source, sample: !!sample }) });
    done();
    if (card.status === "restricted") {          // the platform would not show the post: ask for the caption
      $("#try").hidden = true;
      showRestricted(card, sample);
      return;
    }
    markScanned();
    $("#restricted").hidden = true;
    state.card = card;
    state.text = text;
    state.url = isLink ? text : url;
    state.sample = sample;
    state.claim = card.claims.find((c) => !c.ambiguous && c.symbol) || null;
    state.history = [];
    state.selectedChip = 0;
    $$(".sample-item").forEach((d) => d.classList.toggle("active", d.dataset.id === sample));
    renderMeta();
    renderKpis();
    renderLabel();
    renderWho();
    renderXray();
    if (state.claim) { if (!(await setChart(state.claim.symbol, { card, claim: state.claim }))) clearChart("No price data could be loaded for this stock."); }
    else { const pick = ambiguousPicker(card); clearChart(pick ? "This post names a group of companies, not one stock." : NO_STOCK, pick); }
    auditorNote();  // async: fills the auditor tab in the background
    renderDesk();
    if ($("#rp-journal").hidden) selectRtab("desk");  // a new scan opens on the Desk Note unless the journal is open
    if (state.user) renderJournal();
    fitRight();
  } catch (err) {
    done();
    showRestricted({ message: `Could not scan this: ${err.message || err}`, platform_label: "", url: "" }, sample, true);
  } finally {
    setTimeout(() => { $("#steps").hidden = true; }, REDUCED ? 0 : 500);
    state.busy = false;
    $("#scan-btn").disabled = false;
  }
}

// Instagram/X often block automated reads: a quiet inline box keeps the link and asks for the caption.
function showRestricted(r, sample, plain = false) {
  const box = $("#restricted");
  const caption = h("textarea", { class: "rs-caption", rows: "3", placeholder: "Paste the post caption or what was said…", "aria-label": "Post caption" });
  const go = () => { const t = caption.value.trim(); if (t) runScan(t, { url: r.url || null, sample }); };
  box.replaceChildren(
    h("div", { class: "rs-head" }, r.platform_label ? h("span", { class: "plat" }, r.platform_label) : "",
      r.url ? h("span", { class: "rs-url", title: r.url }, r.url) : "",
      h("button", { type: "button", class: "rs-close", "aria-label": "Dismiss", onclick: () => { box.hidden = true; } }, "×")),
    h("p", {}, r.message),
    plain ? "" : caption,
    plain ? "" : h("div", { class: "rs-actions" }, h("button", { type: "button", class: "btn", onclick: go }, "Audit caption")));
  box.hidden = false;
  if (!plain) caption.focus();
}

function renderMeta() {
  if (state.card?.mode === "history") return renderHistoryMeta();
  const d = state.card.detected || {};
  const tag = (origin) => (origin === "user" ? " · edited" : origin === "fallback" ? " · fallback" : "");
  const item = (label, value, how) => h("span", { class: "mi", title: how || "" }, h("small", {}, label), h("b", {}, value));
  const link = state.card.post?.link;
  $("#meta-strip").replaceChildren(
    item("Date", `${niceDate(d.posted_on)}${d.posted_time ? `, ${d.posted_time} IST` : ""}${tag(d.date_origin)}`, d.date_how),
    item("Source", `${d.source}${tag(d.source_origin)}`, d.source_how),
    item("Ticker", d.tickers?.length ? state.card.claims.filter((c) => c.symbol && !c.ambiguous)
      .map((c) => `${c.symbol.replace(/^BSE:/, "")} · ${c.exchange || "NSE"}${c.found_in ? ` (found in: ${c.found_in})` : ""}`).join(", ") : "none found"),
    item("Platform", d.platform || "Text"),
    state.card.post?.provenance === "SYNTHETIC" ? pill("SYNTHETIC") : "",
    link && /^https?:\/\//.test(link) ? h("a", { class: "mi-link", href: link, target: "_blank", rel: "noopener noreferrer" }, "Open post ↗") : "",
    h("button", { type: "button", class: "edit-link", onclick: openEdit }, "Edit"));
}

function openEdit() {
  const d = state.card.detected;
  $("#edit-date").value = d.posted_on;
  $("#edit-source").value = d.source_origin === "fallback" ? "" : d.source;
  $("#edit-pop").hidden = false;
}

// ------------------------------------------------------------------ KPI cards (below the chart)
function kpi(title, bigNode, sub, { tip = "", prov = null, extraClass = "" } = {}) {
  return h("div", { class: `kpi glass fade-swap ${extraClass}` }, h("h4", {}, title, prov ? pill(prov) : ""), bigNode,
    h("p", { class: tip ? "tip" : "", "data-tip": tip || null, tabindex: tip ? "0" : null }, sub));
}

function renderKpis() {
  if (state.card?.mode === "history") return renderHistoryKpis();
  const c = state.card, claim = state.claim, s = c.sebi;
  const sebiMap = {
    registered: [s.name_matches === false ? "Number registered" : "Registered", s.name_matches === false ? "" : "green"],
    name_match: ["Possible match", ""], number_not_found: ["Number not on list", s.copy_complete ? "red" : ""],
    name_not_found: ["No SEBI number", ""], not_checked: ["Not checked", ""],
  };
  const [sebiText, sebiColor] = sebiMap[s.status] || ["Unknown", ""];
  const sebiBig = h("div", { class: "big small-big" }, h("span", { class: `pulse ${sebiColor}` }), sebiText);
  const sebiSub = s.list_size ? `${s.list_size.toLocaleString("en-IN")} names · saved ${s.copy_saved_on}` : "SEBI list not loaded";
  const sebiTip = [s.text, s.coverage_text].filter(Boolean).join(" ");

  const move = h("div", { class: "big" }, "—");
  let moveSub = "No stock found on NSE or BSE", moveTip = "";
  const after = claim?.after_post?.horizons?.["30"];
  if (after?.status === "scored") {
    move.className = `big ${after.excess_return >= 0 ? "pos" : "neg"}`;
    countUp(move, after.excess_return * 100, { decimals: 1, suffix: " pts", signed: true });
    moveSub = `${claim.symbol} ${pct(after.stock_return)} · Nifty ${pct(after.nifty_return)}`;
    moveTip = `30 days after the post. The claim ${after.worked ? "matched" : "did not match"} the market.`;
  } else if (claim) {
    move.textContent = "Pending";
    moveSub = "Under 30 days of data";
  }

  const m = claim?.market || {};
  const spike = m.spike_ratio;
  const vol = h("div", { class: `big ${spike >= 2.5 ? "neg" : ""}` }, "—");
  if (Number.isFinite(spike)) countUp(vol, spike, { decimals: 1, suffix: "×" });
  const volSub = Number.isFinite(spike) ? "3-day peak ÷ 20D avg" : "Not enough history";
  const volTip = Number.isFinite(spike) ? `Biggest volume of the 3 sessions before the post${m.spike_date ? ` (${m.spike_date})` : ""}, divided by the 20-session average. Flag at 2.5×.` : "";

  const n = c.warnings.length;
  const warn = h("div", { class: `big ${n ? "neg" : "pos"}` }, "0");
  countUp(warn, n);
  const kinds = { hype: 0, media: 0, upi: 0, market: 0, loophole: 0 };
  c.warnings.forEach((w) => {
    if (w.code === "personal_upi") kinds.upi += 1; else if (w.code === "education_loophole") kinds.loophole += 1;
    else if (MARKET_CODES.has(w.code)) kinds.market += 1; else if (MEDIA_CODES.has(w.code)) kinds.media += 1; else kinds.hype += 1;
  });
  const warnSub = Object.entries(kinds).filter(([, v]) => v).map(([k, v]) => `${k} ${v}`).join(" · ") || "No flags raised";
  const postProv = c.post?.provenance === "SYNTHETIC" ? "SYNTHETIC" : null;  // tag only when it differs from the section

  $("#kpis").replaceChildren(
    kpi("SEBI status", sebiBig, sebiSub, { tip: sebiTip }),
    kpi("30D vs. Nifty 50", move, moveSub, { tip: moveTip }),
    kpi("Pre-post volume", vol, volSub, { tip: volTip, extraClass: spike >= 2.5 ? "alert" : "" }),
    kpi("Warning signals", warn, warnSub, { prov: postProv, tip: postProv ? "Read from a made-up sample post." : "" }));
  [...$("#kpis").children].forEach((el, i) => { el.style.setProperty("--i", i); el.classList.add("rise"); });
}

// ------------------------------------------------------------------ chart + technical analysis suite
// Indicators come from the backend, computed locally from the cached OHLCV (no network, no CDN).
const INDICATORS = [
  { key: "sma20", label: "SMA 20", color: "#fbbf24" },
  { key: "ema50", label: "EMA 50", color: "#22d3ee" },
  { key: "vwap20", label: "VWAP (20D)", color: "#a78bfa" },
  { key: "bollinger", label: "Bollinger (20, 2)", color: "#94a3b8" },
  { key: "levels", label: "Key Levels", color: "#f472b6" },
  { key: "vol_avg20", label: "20D Vol Avg", color: "#e2e8f0" },
  { key: "rsi14", label: "RSI (14)", color: "#e879f9" },
  { key: "macd", label: "MACD (12, 26, 9)", color: "#38bdf8" },
  { key: "atr14", label: "ATR (14)", color: "#f59e0b" },
];
const CHART_FONT = "'JetBrains Mono Variable', ui-monospace, Consolas, monospace";
const VOL_CAP = 5;         // volume bars above 5x the 20D average are drawn capped (true value in the readout)
const PANE_EXTRA = 120;    // px added to the chart for each lower pane, so the candles never get squeezed
const LINE = { lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
const tkey = (t) => (typeof t === "string" ? t : typeof t === "number" ? new Date(t * 1000).toISOString().slice(0, 10)
  : t ? `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}` : null);
const fmtVol = (v) => (v >= 1e7 ? `${(v / 1e7).toFixed(2)} Cr` : v >= 1e5 ? `${(v / 1e5).toFixed(2)} L` : fmt(v, 0));

// ------------------------------------------------------------------ Light / Dark theme (light is the default)
function theme() { return document.documentElement.dataset.theme === "dark" ? "dark" : "light"; }
function chartTheme() {
  const light = theme() === "light";
  const line = light ? "#e2e8f0" : "#1e293b";
  return {
    chart: {
      layout: { background: { type: "solid", color: light ? "#ffffff" : "rgba(0,0,0,0)" }, textColor: light ? "#475569" : "#94a3b8",
        panes: { separatorColor: line, separatorHoverColor: "rgba(56,189,248,0.25)" } },
      grid: { vertLines: { color: light ? "rgba(100,116,139,0.12)" : "rgba(148,163,184,0.08)" }, horzLines: { color: light ? "rgba(100,116,139,0.12)" : "rgba(148,163,184,0.08)" } },
      rightPriceScale: { borderColor: line },
      timeScale: { borderColor: line },
    },
    candles: light ? { upColor: "#059669", downColor: "#e11d48", wickUpColor: "#059669", wickDownColor: "#e11d48" }
      : { upColor: "#10b981", downColor: "#f43f5e", wickUpColor: "#10b981", wickDownColor: "#f43f5e" },
    nifty: light ? "#334155" : "#f8fafc",
  };
}
function setTheme(name, { quiet = false } = {}) {
  document.documentElement.dataset.theme = name === "dark" ? "dark" : "light";
  if (!quiet) { try { localStorage.setItem("fp-theme", theme()); } catch { /* private window: the choice lasts for this page only */ } }
  $("#theme-btn").textContent = theme() === "light" ? "Dark" : "Light";
  $("#theme-btn").setAttribute("aria-pressed", String(theme() === "dark"));
  if (state.chart) {
    const t = chartTheme();
    state.chart.applyOptions(t.chart);
    state.series.candles.applyOptions(t.candles);
    state.series.nifty.applyOptions({ color: t.nifty });
  }
  queueThumbs?.();
}

// ------------------------------------------------------------------ Try FinProof: one click per feature, until the first scan
function markScanned() { $("#try").hidden = true; $("#view-workspace").classList.remove("no-scan"); }
function trySample(id) { const s = SAMPLES.find((x) => x.id === id); setScanText(s.text); return runScan(s.text, { sample: s.real ? null : s.id }); }
function tryText(text) { setScanText(text); return runScan(text); }
const TRY = [
  ["▶", "A YouTube video", "Who runs the channel, any SEBI number in the video or description, and which stocks it names.", () => tryText("https://www.youtube.com/watch?v=Z24rem3ma7E")],
  ["◎", "An Instagram reel", "A demo reel. If Instagram asks for a login, FinProof asks you to paste the caption.", () => trySample("ig-demo")],
  ["✉", "A WhatsApp forward", "A paid VIP tip with a personal UPI ID, judged line by line.", () => trySample("vip-upi")],
  ["§", "A real SEBI case on BSE", "Sadhna Broadcast: volume and price around the July 2022 YouTube promotion.", () => trySample("sadhna")],
  ["↗", "Price History", "Past prices for any Nifty 50 stock, with no tip attached. Here: Reliance.", () => tryText("RELIANCE")],
  ["⛨", "The refusal", "Ask the Claim Auditor the one question it never answers.", async () => { await trySample("vip-upi"); jumpTo("card-auditor"); if (state.prompts[0]) ask(state.prompts[0]); }],
];
function renderTry() {
  $("#try-grid").replaceChildren(...TRY.map(([icon, title, text, run]) => h("button", { type: "button", class: "glass try-card", onclick: run },
    h("span", { class: "try-ico", "aria-hidden": "true" }, icon), h("span", {}, h("b", {}, title), h("span", { class: "t" }, text)))));
}

function ensureChart() {
  if (state.chart || !LWC) return !!state.chart;
  const chart = LWC.createChart($("#chart"), {
    autoSize: true,
    ...chartTheme().chart,
    layout: { ...chartTheme().chart.layout, fontSize: 11, attributionLogo: true, fontFamily: CHART_FONT },
    timeScale: { ...chartTheme().chart.timeScale, rightOffset: 4 },
    crosshair: { mode: LWC.CrosshairMode.Normal },
  });
  const candles = chart.addSeries(LWC.CandlestickSeries, { ...chartTheme().candles, borderVisible: false });
  const nifty = chart.addSeries(LWC.LineSeries, { ...LINE, color: chartTheme().nifty, lineStyle: LWC.LineStyle.Dotted });
  const dashed = { ...LINE, lineStyle: LWC.LineStyle.Dashed };
  const overlays = {
    sma20: chart.addSeries(LWC.LineSeries, { ...LINE, color: "#fbbf24", lineWidth: 2 }),
    ema50: chart.addSeries(LWC.LineSeries, { ...LINE, color: "#22d3ee", lineWidth: 2 }),
    vwap20: chart.addSeries(LWC.LineSeries, { ...LINE, color: "#a78bfa", lineWidth: 2 }),
    bb_upper: chart.addSeries(LWC.LineSeries, { ...dashed, color: "rgba(148,163,184,0.55)" }),
    bb_lower: chart.addSeries(LWC.LineSeries, { ...dashed, color: "rgba(148,163,184,0.55)" }),
  };
  const volume = chart.addSeries(LWC.HistogramSeries, { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false }, 1);
  const volAvg = chart.addSeries(LWC.LineSeries, { ...dashed, color: "rgba(226,232,240,0.75)", priceFormat: { type: "volume" } }, 1);
  const markers = LWC.createSeriesMarkers(candles, []);
  chart.subscribeCrosshairMove((p) => showOhlc(p?.time ? tkey(p.time) : null));
  state.chart = chart;
  state.series = { candles, nifty, volume, volAvg, markers, overlays, levelLines: [], momentum: [] };
  setStretch();
  return true;
}

// No stock in the post: empty every series and price readout, so a chart from an earlier scan never stays on screen.
const NO_STOCK = "This post doesn't name a stock we could match on NSE or BSE.";
function clearChart(message = NO_STOCK, extra = null) {
  state.data = null;
  state.index = new Map();
  state.focus = null;
  const S = state.series;
  if (S) {
    [S.candles, S.nifty, S.volume, S.volAvg, ...Object.values(S.overlays)].forEach((s) => s.setData([]));
    S.markers.setMarkers([]);
    S.levelLines.forEach((l) => S.candles.removePriceLine(l));
    S.levelLines = [];
    S.momentum.forEach((s) => state.chart.removeSeries(s));
    S.momentum = [];
    while (state.chart.panes().length > 2) state.chart.removePane(state.chart.panes().length - 1);
  }
  $("#ohlc").replaceChildren(h("span", { class: "muted" }, "No stock found"));
  $("#ind-readout").replaceChildren();
  const prov = $(".legend-prov");
  if (prov) prov.textContent = "No price data";
  let empty = $("#chart-empty");
  if (!empty) { empty = h("div", { class: "chart-empty", id: "chart-empty", role: "status" }); $("#chart").append(empty); }
  empty.replaceChildren(h("p", {}, message), extra || "");
  empty.hidden = false;
  $("#tour-chart").classList.add("no-stock");
}

// A group name ("Tata", "Adani") could mean several companies: list them and let the reader pick. FinProof never guesses.
function ambiguousPicker(card) {
  const amb = (card.claims || []).filter((c) => c.ambiguous && c.candidates?.length);
  if (!amb.length) return null;
  return h("div", { class: "pick" }, ...amb.slice(0, 2).map((c) => h("div", { class: "pick-row" },
    h("p", { class: "small" }, `“${c.matched_text}” could mean ${c.candidates.length} listed companies${c.found_in ? ` (found in: ${c.found_in})` : ""}. Pick one to see its prices:`),
    h("div", { class: "pick-btns" }, ...c.candidates.slice(0, 12).map((sym) =>
      h("button", { type: "button", class: "btn ghost", onclick: () => pickStock(sym) }, sym))))));
}
async function pickStock(symbol) {
  await setChart(symbol, { card: state.card, claim: { symbol, direction: null }, pinLabel: "Post" });
}

async function setChart(symbol, { card = null, claim = null, pinDate = null, pinLabel = "Tip" } = {}) {
  if (!ensureChart()) return false;
  if ($("#chart-empty")) $("#chart-empty").hidden = true;
  $("#tour-chart").classList.remove("no-stock");
  const when = card ? card.post.posted_on : pinDate;
  let data;
  try { data = await getJSON(`/api/chart/${encodeURIComponent(symbol)}${when ? `?levels_before=${when}` : ""}`); } catch { return false; }
  state.data = data;
  state.index = new Map(data.candles.map((c, i) => [c.time, i]));
  const { candles, volume, markers } = state.series;
  candles.setData(data.candles);
  const spike = claim?.market?.flags?.includes("volume_spike") ? claim.market.spike_date : null;
  const avg = data.indicators?.vol_avg20 || [];
  volume.setData(data.volume.map((v, i) => {
    const cap = avg[i] ? avg[i] * VOL_CAP : null;
    return { time: v.time, value: cap ? Math.min(v.value, cap) : v.value,
      color: v.time === spike ? "#ef4444" : (v.ratio !== null && v.ratio >= data.spike_ratio ? "#f59e0b" : "rgba(139,152,171,0.35)") };
  }));
  const pins = [];
  if (when) {
    const bar = data.candles[idxAfter(data.candles, when)];
    const down = claim?.direction === "down";
    const who = card?.detected?.source && card.detected.source_origin !== "fallback" ? ` · ${card.detected.source}` : "";
    if (bar) pins.push({ time: bar.time, position: down ? "aboveBar" : "belowBar", color: "#38bdf8", shape: down ? "arrowDown" : "arrowUp", text: `${pinLabel}${who}` });
  }
  markers.setMarkers(pins);
  state.focus = when;
  applyIndicators();
  applyRange();
  showOhlc(null);
  $("#tour-chart").classList.remove("fade-swap"); void $("#tour-chart").offsetWidth; $("#tour-chart").classList.add("fade-swap");
  return true;
}

function lineData(key) {
  const d = state.data, arr = d?.indicators?.[key] || [];
  return d ? d.candles.flatMap((c, i) => (arr[i] === null || arr[i] === undefined ? [] : [{ time: c.time, value: arr[i] }])) : [];
}

function setStretch() {
  const panes = state.chart.panes();
  panes.forEach((p, i) => p.setStretchFactor(i === 0 ? 4 : i === 1 ? 1 : 1.25));
  $("#chart").style.setProperty("--xp", `${Math.max(0, panes.length - 2) * PANE_EXTRA}px`);
}

function applyIndicators() {
  if (!state.chart || !state.data) return;
  const S = state.series, on = state.ind, d = state.data;
  S.overlays.sma20.setData(on.sma20 ? lineData("sma20") : []);
  S.overlays.ema50.setData(on.ema50 ? lineData("ema50") : []);
  S.overlays.vwap20.setData(on.vwap20 ? lineData("vwap20") : []);
  S.overlays.bb_upper.setData(on.bollinger ? lineData("bb_upper") : []);
  S.overlays.bb_lower.setData(on.bollinger ? lineData("bb_lower") : []);
  S.volAvg.setData(on.vol_avg20 ? lineData("vol_avg20") : []);

  S.levelLines.forEach((l) => S.candles.removePriceLine(l));
  S.levelLines = [];
  if (on.levels && d.levels) {
    [["high_30d", "30D High", "#94a3b8"], ["low_30d", "30D Low", "#94a3b8"], ["high_52w", "52W High", "#f472b6"], ["low_52w", "52W Low", "#f472b6"]]
      .forEach(([k, title, color]) => {
        if (d.levels[k] === null || d.levels[k] === undefined) return;
        S.levelLines.push(S.candles.createPriceLine({ price: d.levels[k], color, lineWidth: 1, lineStyle: LWC.LineStyle.LargeDashed, axisLabelVisible: true, title }));
      });
  }

  // Lower momentum panes: rebuilt in a fixed order (RSI, then MACD) so their indexes never drift.
  S.momentum.forEach((s) => state.chart.removeSeries(s));
  S.momentum = [];
  while (state.chart.panes().length > 2) state.chart.removePane(state.chart.panes().length - 1);
  let pane = 2;
  if (on.rsi14) {
    const s = state.chart.addSeries(LWC.LineSeries, { ...LINE, color: "#e879f9", lineWidth: 2,
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) }, pane);
    s.setData(lineData("rsi14"));
    [70, 30].forEach((p) => s.createPriceLine({ price: p, color: "rgba(148,163,184,0.5)", lineWidth: 1, lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title: "" }));
    S.momentum.push(s);
    pane += 1;
  }
  if (on.macd) {
    const hist = state.chart.addSeries(LWC.HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane);
    const h = d.indicators.macd_hist;
    hist.setData(d.candles.flatMap((c, i) => {
      if (h[i] === null) return [];
      const growing = i > 0 && h[i - 1] !== null && Math.abs(h[i]) > Math.abs(h[i - 1]);
      const color = h[i] >= 0 ? (growing ? "rgba(16,185,129,0.85)" : "rgba(16,185,129,0.4)") : (growing ? "rgba(239,68,68,0.85)" : "rgba(239,68,68,0.4)");
      return [{ time: c.time, value: h[i], color }];
    }));
    const line = state.chart.addSeries(LWC.LineSeries, { ...LINE, color: "#38bdf8", lineWidth: 2 }, pane);
    const sig = state.chart.addSeries(LWC.LineSeries, { ...LINE, color: "#f59e0b" }, pane);
    line.setData(lineData("macd"));
    sig.setData(lineData("macd_signal"));
    S.momentum.push(hist, line, sig);
  }
  setStretch();
  renderIndBar();
}

function toggleIndicator(key) {
  state.ind[key] = !state.ind[key];
  applyIndicators();
  showOhlc(null);
  if (key === "rsi14" || key === "macd") requestAnimationFrame(applyRange);
}

function renderIndBar() {
  const bar = $("#ind-bar");
  const explain = state.data?.explain || {};
  const on = INDICATORS.filter((x) => state.ind[x.key]).length;
  const open = !!state.indOpen;
  bar.replaceChildren(h("button", { type: "button", class: `ind-toggle ${on ? "on" : ""}`, "aria-expanded": String(open), "aria-controls": "ind-pop",
      onclick: (e) => { e.stopPropagation(); state.indOpen = !open; renderIndBar(); } }, `Indicators (${INDICATORS.length})${on ? ` · ${on} on` : ""} ▾`),
    h("div", { class: "ind-pop", id: "ind-pop", hidden: open ? null : "", onclick: (e) => e.stopPropagation() },
    h("span", { class: "ind-label" }, "Indicators"),
    ...INDICATORS.map((x) => h("button", { type: "button", class: `ichip ${state.ind[x.key] ? "on" : ""}`, "aria-pressed": String(!!state.ind[x.key]),
      title: explain[x.key] || x.label, onclick: () => toggleIndicator(x.key) }, h("i", { style: `background:${x.color}` }), x.label)),
    h("button", { type: "button", class: "ichip help", "aria-expanded": String(!$("#ind-help").hidden), title: "What do these measure?",
      onclick: () => { $("#ind-help").hidden = !$("#ind-help").hidden; renderIndHelp(); renderIndBar(); } }, "?")));
  renderIndHelp();
}
document.addEventListener("click", () => { if (state.indOpen) { state.indOpen = false; renderIndBar(); } });

function renderIndHelp() {
  const box = $("#ind-help");
  if (box.hidden) return;
  const explain = state.data?.explain || {};
  const active = INDICATORS.filter((x) => state.ind[x.key]);
  const list = active.length ? active : INDICATORS;
  box.replaceChildren(h("b", {}, active.length ? "What the active indicators measure" : "What each indicator measures"),
    h("ul", {}, list.map((x) => h("li", {}, explain[x.key] || x.label))),
    h("p", { class: "small muted" }, "They describe past prices and volumes, to check a post's story. They are not signals to act on."));
}

function showOhlc(time) {
  const d = state.data;
  if (!d) return;
  // Without a crosshair: the last session before the post (what the Desk Note uses), else the latest session.
  const pre = state.focus ? idxAfter(d.candles, state.focus) - (d.candles[idxAfter(d.candles, state.focus)].time >= state.focus ? 1 : 0) : -1;
  const i = time && state.index.has(time) ? state.index.get(time) : pre >= 0 ? pre : d.candles.length - 1;
  const b = d.candles[i];
  const prev = d.candles[Math.max(0, i - 1)];
  const chg = (b.close / prev.close - 1) * 100;
  const cls = chg >= 0 ? "pos" : "neg";
  const prov = $(".legend-prov");
  if (prov) prov.textContent = `${d.exchange === "BSE" ? "BSE" : d.exchange === "INDEX" ? "NSE index" : "NSE"} · REAL`;
  $("#ohlc").replaceChildren(h("span", { class: "sym" }, d.label), d.exchange && d.exchange !== "INDEX" ? h("span", { class: "exch" }, d.exchange) : "",
    h("span", { class: "muted" }, d.company || ""),
    ...[["O", b.open], ["H", b.high], ["L", b.low], ["C", b.close]].map(([k, v]) => h("span", { class: cls }, h("b", {}, k), fmt(v))),
    h("span", { class: cls }, `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%`), h("span", { class: "muted" }, b.time));

  const ind = d.indicators || {}, on = state.ind, v = (k) => ind[k]?.[i];
  const vol = d.volume[i];
  const atr = v("atr14_pct");
  const parts = [on.atr14 ? h("span", { class: "atr-pill", title: d.explain?.atr14 || "ATR (14)" },
    atr != null ? `Avg Daily Swing: ±${(atr * 100).toFixed(1)}%` : "Avg Daily Swing: —") : "",
    h("span", {}, h("b", {}, "Vol "), fmtVol(vol.value),
    vol.ratio !== null && vol.ratio !== undefined ? h("em", { class: vol.ratio >= d.spike_ratio ? "hot" : "" }, ` ${vol.ratio.toFixed(1)}× 20D avg`) : "")];
  const add = (key, label, text) => { if (on[key] && text !== null) parts.push(h("span", {}, h("i", { style: `background:${INDICATORS.find((x) => x.key === key).color}` }), h("b", {}, `${label} `), text)); };
  add("sma20", "SMA20", v("sma20") != null ? fmt(v("sma20")) : null);
  add("ema50", "EMA50", v("ema50") != null ? fmt(v("ema50")) : null);
  add("vwap20", "VWAP", v("vwap20") != null ? `${fmt(v("vwap20"))} (${b.close >= v("vwap20") ? "+" : ""}${((b.close / v("vwap20") - 1) * 100).toFixed(1)}%)` : null);
  add("bollinger", "BB", v("bb_upper") != null ? `${fmt(v("bb_lower"))} – ${fmt(v("bb_upper"))}` : null);
  add("rsi14", "RSI14", v("rsi14") != null ? v("rsi14").toFixed(1) : null);
  add("macd", "MACD", v("macd") != null && v("macd_signal") != null ? `${v("macd").toFixed(2)} / ${v("macd_signal").toFixed(2)} (${v("macd_hist") >= 0 ? "+" : ""}${v("macd_hist").toFixed(2)})` : null);
  if (on.levels && d.levels?.high_30d != null) parts.push(h("span", { class: "muted" }, `Levels as of ${d.levels.as_of}`));
  $("#ind-readout").replaceChildren(...parts);
}

function applyRange() {
  const c = state.data?.candles;
  if (!c?.length) return;
  let from, to;
  if (state.focus) {
    const i = idxAfter(c, state.focus);
    from = Math.max(0, i - Math.max(5, Math.round(state.range * 0.35)));
    to = Math.max(i, idxBefore(c, addDays(state.focus, state.range)));
  } else {
    to = c.length - 1;
    from = idxAfter(c, addDays(c[to].time, -state.range));
  }
  state.chart.timeScale().setVisibleRange({ from: c[from].time, to: c[to].time });
  const line = state.series.nifty, d = state.data;
  if (!$("#nifty-toggle").checked || d.symbol === "^NSEI" || !d.nifty.length) { line.setData([]); return; }
  const anchor = state.focus || c[from].time;
  const k = c[idxBefore(c, anchor)].close / d.nifty[idxBefore(d.nifty, anchor)].value;
  line.setData(d.nifty.map((p) => ({ time: p.time, value: Math.round(p.value * k * 100) / 100 })));
}

// ------------------------------------------------------------------ Credibility X-Ray
// "Not proof a clip is fake" only makes sense for videos, reels and posts that borrow a famous name.
const clipNote = (c) => ["youtube", "instagram", "x"].includes(c.post?.kind) || (c.media?.codes || []).includes("impersonation");

function renderXray() {
  if (state.card?.mode === "history") return renderHistoryXray();
  const c = state.card;
  const box = $("#tour-xray");
  const raised = Math.min(CHECKS, c.warnings.length);
  const meter = h("div", { class: "meter", "aria-label": `${raised} of ${CHECKS} checks raised` },
    ...Array.from({ length: CHECKS }, (_, i) => h("span", { class: i < raised ? "on" : "", style: `--i:${i}` })));

  const chips = [];
  c.warnings.forEach((w, wi) => {
    const items = w.evidence?.length ? w.evidence : [w.code === "volume_spike" && state.claim?.market?.spike_ratio ? `volume ${state.claim.market.spike_ratio.toFixed(1)}×` : (FLAG_NAMES[w.code] || w.code.replace(/_/g, " "))];
    items.forEach((e) => chips.push({ w, wi, label: w.evidence?.length ? `“${e}”` : e }));
  });
  const why = h("div", { class: "why" });
  const showWhy = (k) => {
    state.selectedChip = k;
    const { w } = chips[k];
    why.replaceChildren(h("b", {}, w.text), " ", h("span", { class: "muted" }, WHY[w.code] || ""));
    chipRow.querySelectorAll(".qchip").forEach((el, j) => el.classList.toggle("sel", j === k));
  };
  const chipRow = h("div", { class: "qchips" }, chips.map((ch, k) => h("button", {
    type: "button", class: `qchip ${MARKET_CODES.has(ch.w.code) ? "mkt" : ""} ${MEDIA_CODES.has(ch.w.code) ? "media" : ""}`, onclick: () => showWhy(k) }, ch.label)));

  const md = c.media || { codes: [] };
  const mediaBlock = md.codes?.length ? h("div", { class: "media-flags" },
    h("div", { class: "mf-head" }, h("b", {}, md.title), clipNote(c) ? h("span", { class: "small muted" }, md.note) : ""),
    h("div", { class: "mf-list" }, md.codes.map((code) => h("span", { class: "mf" }, FLAG_NAMES[code] || code)))) : "";

  const tr = c.track_record || {};
  const recent = (tr.recent || []).filter((t) => t.horizons?.["30"]?.status === "scored");
  const max = Math.max(0.05, ...recent.map((t) => Math.abs(t.horizons["30"].excess_return)));
  const spark = recent.length ? h("div", { class: "spark", "aria-label": "Past tips against the Nifty 50" }, recent.map((t) => {
    const v = t.horizons["30"].excess_return;
    return h("i", { title: `${t.posted_on} ${t.symbol}: ${pct(v)} vs Nifty`,
      style: `height:${Math.max(4, (Math.abs(v) / max) * 60)}px;background:${t.horizons["30"].worked ? "#10b981" : "#ef4444"};opacity:.85` });
  })) : h("p", { class: "small muted" }, "No past tips from this source yet.");

  box.replaceChildren(
    h("h3", {}, "Credibility X-Ray", c.post?.provenance === "SYNTHETIC" ? pill("SYNTHETIC") : ""),
    mediaBlock,
    h("div", { class: "xray-grid" },
      h("div", {},
        h("div", { class: "small" }, h("b", {}, `${raised} of ${CHECKS} checks raised`), h("span", { class: "muted" }, " · signal count, not a stock rating")),
        meter,
        h("div", { class: "small", style: "margin:10px 0 6px" }, h("b", {}, "Flagged phrases")),
        chips.length ? chipRow : h("p", { class: "small muted" }, "Nothing flagged."),
        chips.length ? why : ""),
      h("div", {},
        h("div", { class: "small" }, h("b", {}, "Source record "), tr.provenance ? pill(tr.provenance) : ""),
        spark,
        h("p", { class: "small" }, tr.text || ""),
        recent.length ? h("p", { class: "small muted" }, `${recent.length} scored tip${recent.length === 1 ? "" : "s"} · 30D vs Nifty 50`) : "")),
    h("details", { class: "full" }, h("summary", {}, "Full card"), ...renderCard(c)));
  box.classList.remove("fade-swap"); void box.offsetWidth; box.classList.add("fade-swap");
  if (chips.length) showWhy(0);
}

// ------------------------------------------------------------------ Veteran's Desk Note
function promptButtons() {
  return state.prompts.map((p, i) => h("button", { type: "button", class: `pchip ${i === 0 ? "shield" : ""}`, onclick: () => ask(p) },
    i === 0 ? icon.shield() : "", p));
}

function renderDesk() {
  const v = state.card?.veteran;
  const box = $("#rp-desk");
  if (state.card?.mode === "history") return renderHistoryDesk();
  if (!v) { box.replaceChildren(h("p", { class: "muted" }, "Scan a tip to see the Desk Note.")); return; }
  const toggle = h("div", { class: "seg", role: "group", "aria-label": "Desk Note view" },
    ...[["mentor", "Beginner Mentor View"], ["raw", "Raw Forensic Signals"]].map(([k, label]) =>
      h("button", { type: "button", class: state.deskView === k ? "active" : "", "aria-pressed": String(state.deskView === k),
        onclick: () => { state.deskView = k; renderDesk(); } }, label)));
  const parts = [h("div", { class: "desk-head" }, h("h3", {}, "Veteran's Desk Note"), toggle)];
  if (state.deskView === "mentor") {
    const item = (x, good, i) => h("div", { class: `vitem ${good ? "good" : ""} rise`, style: `--i:${i}` }, h("b", {}, x.title), x.text,
      x.evidence?.length ? h("div", { class: "qs" }, x.evidence.map((e) => h("span", {}, `“${e}”`))) : "");
    const ctx = v.context;
    const mediaCodes = new Set(v.media?.codes || []);
    const media = v.wrong.filter((x) => mediaCodes.has(x.code) && x.code !== "volume_spike");
    const rest = v.wrong.filter((x) => !media.includes(x));
    parts.push(h("p", { class: "desk-voice" }, v.voice),
      h("p", { class: "desk-intro" }, v.intro),
      ctx ? h("div", { class: "desk-ctx rise" }, h("div", { class: "ctx-head" }, h("span", {}, `${ctx.title} · ${niceDate(ctx.as_of)}`), h("span", { class: "cite" }, "[Tech]")),
        h("ul", {}, ctx.facts.map((f) => h("li", {}, f.text))), h("p", {}, ctx.note)) : "",
      ...(media.length ? [h("h4", { class: "bad" }, v.media.title), ...media.map((x, i) => item(x, false, i)),
        clipNote(state.card) ? h("p", { class: "small muted" }, v.media.note) : ""] : []),
      h("h4", { class: "bad" }, "What is wrong here"),
      ...(rest.length ? rest.map((x, i) => item(x, false, i)) : [h("p", { class: "small muted" }, "Nothing else raised a flag.")]),
      h("h4", { class: "good" }, "How a pro checks it"),
      ...v.right.map((x, i) => item(x, true, i)));
  } else {
    parts.push(h("p", { class: "desk-voice" }, "The numbers behind the note."),
      ...v.raw.map((r) => h("div", { class: `raw-row ${r.flag ? "flag" : ""}` }, h("b", {}, r.label),
        h("span", {}, r.value, r.evidence?.length ? h("span", { class: "ev" }, "In the post: ", r.evidence.map((e) => `“${e}”`).join(", ")) : ""),
        pill(r.provenance))));
  }
  parts.push(h("p", { class: "desk-disc" }, v.disclaimer), h("div", { class: "desk-ask prompts" }, ...promptButtons()));
  box.replaceChildren(...parts);
  box.scrollTop = 0;
}

// ------------------------------------------------------------------ Signal or Noise label (the verdict, first)
// Who is this? The YouTube channel behind a video, from its public page (REAL; cached for offline use).
function renderWho() {
  const box = $("#who");
  const p = state.card?.mode === "history" ? null : state.card?.profile;
  if (!p) { box.hidden = true; return; }
  const row = (k, v) => (v ? h("div", { class: "who-row" }, h("span", { class: "who-k" }, k), h("span", { class: "who-v" }, v)) : "");
  const link = p.url ? h("a", { href: p.url, target: "_blank", rel: "noopener noreferrer" }, p.handle || "Open channel ↗") : p.handle;
  box.replaceChildren(
    h("div", { class: "who-head" }, h("h3", {}, "Who is this?"), pill("REAL"),
      h("span", { class: "small muted" }, p.status !== "ok" ? "Channel page not available" : p.from_cache ? `Saved copy from ${p.fetched_on}` : "Live from YouTube")),
    row("Channel", p.channel), row("Handle", link), row("Subscribers", p.subscribers), row("Videos", p.videos),
    row("This video", `${niceDate(p.video_date)}${p.video_date_how ? ` (${p.video_date_how})` : ""}`),
    p.about_lines?.length ? h("div", { class: "from-source" }, h("small", {}, "From the source: channel description"),
      ...p.about_lines.map((l) => h("p", {}, l))) : "");
  box.hidden = false;
}

function renderLabel() {
  const L = state.card?.label;
  const box = $("#signal-label");
  if (state.card?.mode === "history") {
    box.replaceChildren(h("div", { class: "nl-head" }, h("h2", {}, "Price History"), pill("REAL")),
      h("p", { class: "nl-note" }, state.card.history.note));
    box.hidden = false;
    return;
  }
  if (!L) { box.hidden = true; return; }
  const whyBtn = (text) => {
    const note = h("p", { class: "nl-why", hidden: "" }, text);
    const btn = h("button", { type: "button", class: "nl-why-btn", "aria-expanded": "false",
      onclick: () => { note.hidden = !note.hidden; btn.setAttribute("aria-expanded", String(!note.hidden)); } }, "why");
    return [btn, note];
  };
  const row = (l) => {
    const [btn, note] = l.why ? whyBtn(l.why) : ["", ""];
    return h("div", { class: `nl-row tone-${l.tone}` },
      h("span", { class: "nl-k" }, l.label),
      h("span", { class: "nl-v" }, l.value, l.evidence?.length ? h("span", { class: "nl-ev" }, l.evidence.map((e) => `“${e}”`).join(", ")) : ""),
      h("span", { class: "nl-tags" }, pill(l.provenance), btn), note);
  };
  const t = L.message_type;
  const [tBtn, tNote] = whyBtn(t.why);
  const reply = state.card.reply ? replyCard(state.card.reply) : "";
  box.replaceChildren(
    h("div", { class: "nl-head" }, h("h2", {}, L.title), h("span", { class: `nl-type tone-${t.tone}` }, t.value), pill(t.provenance), tBtn,
      state.card.reply ? h("button", { type: "button", class: "btn nl-reply", onclick: () => { reply.hidden = !reply.hidden; } }, "Reply card") : ""),
    tNote, reply,
    h("p", { class: "nl-note" }, L.note),
    h("div", { class: "nl-sec" }, L.right_before.title), ...L.right_before.lines.map(row),
    h("div", { class: "nl-sec" }, L.fair.title), ...L.fair.lines.map(row));
  box.hidden = false;
}

// ------------------------------------------------------------------ Price History mode (a bare ticker or company name)
// Past prices only: no post, so nothing to judge and no flags. ("Research" is a regulated term, so not that word.)
async function showHistory(card, text) {
  state.card = card;
  state.text = text;
  state.url = null;
  state.sample = null;
  state.claim = card.claims[0];
  state.history = [];
  $("#restricted").hidden = true;
  renderMeta();
  renderKpis();
  renderLabel();
  renderXray();
  await setChart(card.history.symbol, {});
  auditorNote();
  renderDesk();
  if ($("#rp-journal").hidden) selectRtab("desk");
  fitRight();
}

function historyFacts(hist) {
  return h("ul", { class: "facts hist-facts" }, hist.facts.map((f) => h("li", {}, f)));
}

function renderHistoryMeta() {
  const x = state.card.history;
  const item = (label, value) => h("span", { class: "mi" }, h("small", {}, label), h("b", {}, value));
  $("#meta-strip").replaceChildren(item("Mode", "Price History"), item("Ticker", `${x.label} · ${x.exchange}`),
    item("Company", x.company || "–"), x.nifty50 ? item("Index", "Nifty 50 constituent") : "", item("As of", niceDate(x.as_of)), pill("REAL"));
}

function renderHistoryKpis() {
  const x = state.card.history;
  const perf = x.performance || {};
  const tile = (title, big, sub) => h("div", { class: "kpi glass fade-swap" }, h("h4", {}, title), h("div", { class: "big" }, big), h("p", {}, sub));
  const p30 = perf["30 sessions"], p1y = perf["1 year (252 sessions)"];
  const pts = (q) => (q && q.nifty !== null ? `${((q.stock - q.nifty) * 100 >= 0 ? "+" : "")}${((q.stock - q.nifty) * 100).toFixed(1)} pts` : "Not enough data");
  $("#kpis").replaceChildren(
    tile("Last close", x.facts[0].match(/₹[\d,.]+/)?.[0] || "–", niceDate(x.as_of)),
    tile("30 sessions vs Nifty 50", pts(p30), p30 ? `${x.label} ${pct(p30.stock)} · Nifty ${pct(p30.nifty)}` : "Not enough data"),
    tile("1 year vs Nifty 50", pts(p1y), p1y ? `${x.label} ${pct(p1y.stock)} · Nifty ${pct(p1y.nifty)}` : "Not enough data"),
    tile("Warning signals", "None", "No post, so nothing to flag"));
}

function renderHistoryXray() {
  const x = state.card.history;
  $("#tour-xray").replaceChildren(h("h3", {}, "Price History", pill("REAL")),
    h("p", { class: "small muted" }, x.note), historyFacts(x));
}

function renderHistoryDesk() {
  const x = state.card.history;
  $("#rp-desk").replaceChildren(h("div", { class: "desk-head" }, h("h3", {}, "Price History")),
    h("p", { class: "desk-intro" }, `${x.label}${x.company ? ` (${x.company})` : ""} on ${x.exchange}. ${x.note}`),
    h("div", { class: "desk-ctx" }, h("div", { class: "ctx-head" }, h("span", {}, `Past prices · ${niceDate(x.as_of)}`), pill("REAL")), historyFacts(x)),
    h("p", { class: "desk-disc" }, state.card.disclaimer), h("div", { class: "desk-ask prompts" }, ...promptButtons()));
}

// ------------------------------------------------------------------ Nifty 50 search beside the scanner
async function loadNifty50() {
  try { state.n50 = (await getJSON("/api/nifty50")).companies || []; } catch { state.n50 = []; }
  renderN50("");
}
function renderN50(q) {
  const key = q.trim().toLowerCase();
  const rows = (state.n50 || []).filter((r) => !key || r.symbol.toLowerCase().includes(key) || r.name.toLowerCase().includes(key)).slice(0, 50);
  $("#n50-list").replaceChildren(...(rows.length ? rows.map((r) => h("button", { type: "button", role: "option", class: "sample-item n50-item",
    onclick: () => { closeSamples(); setScanText(r.symbol); runScan(r.symbol); } }, h("b", {}, r.symbol), h("span", {}, r.name))) : [h("p", { class: "small muted" }, "No match in the Nifty 50.")]));
}

// ------------------------------------------------------------------ Reply card for WhatsApp groups (facts only)
function replyCard(reply) {
  const box = h("div", { class: "reply-pop", hidden: "" });
  let lang = "en";
  const draw = () => {
    const text = reply.texts[lang];
    const area = h("textarea", { class: "reply-text", rows: "4", readonly: "", "aria-label": "Reply text" });
    area.value = text;
    const status = h("span", { class: "small muted" });
    box.replaceChildren(
      h("div", { class: "seg reply-langs", role: "group", "aria-label": "Reply language" }, ...Object.entries(reply.langs).map(([k, label]) =>
        h("button", { type: "button", class: k === lang ? "active" : "", onclick: () => { lang = k; draw(); } }, label))),
      area,
      h("div", { class: "reply-actions" },
        h("button", { type: "button", class: "btn", onclick: async () => {
          try { await navigator.clipboard.writeText(text); status.textContent = "Copied."; }
          catch { area.select(); document.execCommand("copy"); status.textContent = "Copied."; }
        } }, "Copy"), status),
      reply.checked[lang] ? "" : h("p", { class: "reply-check" }, "Needs a native-speaker check before use."));
  };
  draw();
  return box;
}

// ------------------------------------------------------------------ Signal Map (Sources tab): two separate axes
function signalMap(m) {
  const W = 520, H = 320, pad = 40, top = 12, bottom = H - pad;
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs, text) => { const e = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v)); if (text) e.textContent = text; return e; };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "smap", role: "img", "aria-label": "Signal Map of sources" });
  // Points sit inside an inner band, so they never cover the quadrant names along the top and bottom edges.
  const x = (v) => pad + 14 + v * (W - pad - 40), y = (v) => bottom - 22 - v * (bottom - top - 50);
  const mx = pad + (W - pad - 12) / 2, my = (top + bottom) / 2;
  svg.append(el("rect", { x: pad, y: top, width: W - pad - 12, height: bottom - top, class: "smap-bg" }),
    el("line", { x1: x(0.5), y1: top, x2: x(0.5), y2: bottom, class: "smap-mid" }),
    el("line", { x1: pad, y1: y(0.5), x2: W - 12, y2: y(0.5), class: "smap-mid" }),
    el("text", { x: (mx + W - 12) / 2, y: top + 15, class: "smap-q" }, "Right and fair"), el("text", { x: (pad + mx) / 2, y: top + 15, class: "smap-q" }, "Honest but wrong"),
    el("text", { x: (mx + W - 12) / 2, y: bottom - 6, class: "smap-q" }, "Right but unfair"), el("text", { x: (pad + mx) / 2, y: bottom - 6, class: "smap-q" }, "Wrong and unfair"),
    el("text", { x: (W + pad) / 2, y: H - 8, class: "smap-ax" }, "Were they right before? →"),
    el("text", { x: 12, y: my, class: "smap-ax", transform: `rotate(-90 12 ${my})` }, "Are they playing fair? →"));
  m.plotted.forEach((r) => {
    const cx = x(r.right), cy = y(r.fair), right = r.right > 0.62;
    svg.append(el("circle", { cx, cy, r: 7, class: `smap-dot ${r.provenance === "REAL" ? "real" : "synthetic"}` }),
      el("text", { x: right ? cx - 11 : cx + 11, y: cy + 4, class: "smap-lbl", "text-anchor": right ? "end" : "start" }, `${r.source_label} (${r.worked}/${r.scored})`));
  });
  return h("div", { class: "glass panel rise signal-map" }, h("h2", {}, "Signal Map"),
    h("p", { class: "small muted" }, m.note), svg,
    h("p", { class: "small" }, "Across: share of calls that beat the Nifty 50 at 30 days. Up: share of calls with no pump pattern in the prices."),
    m.plotted.length ? h("p", { class: "small muted" }, "Data: ", ...m.plotted.map((r) => [pill(r.provenance), ` ${r.source_label}  `])) : "",
    m.not_enough_history.length ? h("p", { class: "small muted" }, `Not enough history (under ${m.min_calls} scored calls): `,
      m.not_enough_history.map((r) => `${r.source_label} (${r.scored})`).join(", ")) : "");
}

// ------------------------------------------------------------------ Claim Auditor
function msg(node) { $("#msgs").append(node); requestAnimationFrame(() => { $("#msgs").scrollTop = $("#msgs").scrollHeight; }); return node; }
function cites(list) { return list?.length ? h("div", { class: "cites" }, list.map((c) => h("span", { class: "cite" }, `[${c}]`))) : ""; }

function auditorStatus() {
  const live = !!state.health?.network?.live;
  const ai = state.health?.ai?.enabled && state.health?.ai?.key_found;
  $("#aud-status").textContent = `${state.card?.detected?.tickers?.join(", ") || "No ticker"} · Hybrid`;
  $("#aud-dot").className = `dot-live ${live ? "on" : "cache"}`;
  $("#aud-status").parentElement.title = `${live ? "Live" : "Cache"} · ${ai ? `AI (${state.health.ai.model}) with local fallback` : "local engine"}`;
}

// After each scan: an opening brief from the local engine (instant, offline), in the same format as answers.
async function auditorNote() {
  $("#msgs").replaceChildren();
  auditorStatus();
  let a;
  try {
    a = await getJSON("/api/auditor", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ question: "overview", card: state.card }) });
  } catch { a = null; }
  if (a) msg(brief(a));
}

// One answer as a short brief: headline -> fact lines with evidence tags -> mentor's note.
function factList(lines) {
  return h("ul", { class: "facts" }, (lines || []).map((l) => h("li", {}, l.text,
    ...(l.cite || []).map((c) => h("span", { class: "cite inline" }, `[${c}]`)),
    l.evidence?.length ? h("span", { class: "ev" }, "In the post: ", l.evidence.map((e) => `“${e}”`).join(", ")) : "")));
}
function brief(a, ...extra) {
  return h("div", { class: "m bot" }, a.headline ? h("p", { class: "headline" }, a.headline) : "", factList(a.lines),
    a.mentor ? h("div", { class: "mentor" }, h("b", {}, "Mentor's note "), a.mentor) : "", ...extra);
}

function renderPrompts() { $("#prompts").replaceChildren(...promptButtons()); }

async function ask(question) {
  question = (question || "").trim();
  if (!question) return;
  selectRtab("auditor");
  msg(h("div", { class: "m user" }, question));
  const dots = msg(h("div", { class: "m bot" }, h("span", { class: "dots", "aria-label": "Checking" }, h("i"), h("i"), h("i"))));
  const started = performance.now();
  let a;
  try {
    a = await getJSON("/api/chat", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ message: question, card: state.card, history: state.history }) });
  } catch (err) {
    a = { refused: false, refusal: null, intent: "error", engine: "offline", headline: "The local server did not answer.", lines: [{ text: String(err.message || err), evidence: [], cite: [] }] };
  }
  const wait = REDUCED ? 0 : Math.max(0, 380 - (performance.now() - started));
  setTimeout(() => { dots.remove(); answer(a, question); }, wait);
}

function answer(a, question) {
  if (a.refused) {
    msg(h("div", { class: "m guard" },
      h("div", { class: "guard-head" }, icon.bigShield(), "No-Advice Guardrail"),
      h("p", { style: "margin:8px 0" }, h("b", {}, a.refusal)), factList(a.lines), cites(GUARD_CITES),
      a.mentor ? h("div", { class: "mentor" }, h("b", {}, "Mentor's note "), a.mentor) : ""));
  } else {
    msg(brief(a, a.engine === "ai" ? h("div", { class: "meta" }, `AI · ${a.model}`) : ""));
  }
  const said = a.engine === "ai" ? a.text : [a.refusal || a.headline, ...(a.lines || []).map((l) => l.text)].filter(Boolean).join("\n");
  state.history.push({ role: "user", content: question }, { role: "assistant", content: said });
  state.history = state.history.slice(-6);
}

// ------------------------------------------------------------------ Demo Investor + Noise Journal
const jKey = () => `finproof-journal:${state.user?.name}`;
const getJournal = () => store.get(jKey(), []);
const setJournal = (v) => { store.set(jKey(), v); state.journalSummary = null; };

async function login(user) {
  state.user = user;
  store.set("finproof-user", user);
  if (user.demo && !getJournal().length) {
    try { setJournal(await getJSON("/api/journal/demo-seed")); } catch { /* seed optional */ }
  }
  $("#login-dialog").close();
  updateInvestor();
  selectRtab("journal");
}
function logout() { state.user = null; store.del("finproof-user"); updateInvestor(); renderJournal(); }
function updateInvestor() {
  $("#investor-btn").textContent = state.user ? `● ${state.user.name}` : "Demo Investor";
  $("#investor-btn").classList.toggle("on", !!state.user);
}

function currentTip() {
  const c = state.claim;
  if (!c || !["up", "down"].includes(c.direction)) return null;
  return { symbol: c.symbol, direction: c.direction, posted_on: state.card.post.posted_on, source_label: state.card.detected?.source || "Unattributed Forward",
    note: state.card.summary.text, provenance: state.sample ? "SYNTHETIC" : "REAL" };
}

async function renderJournal() {
  const box = $("#rp-journal");
  const actions = $("#journal-actions");
  if (!state.user) {
    actions.replaceChildren(
      h("button", { type: "button", class: "btn", onclick: () => login({ name: "Demo Investor", demo: true }) }, "1-click Demo Investor"),
      h("button", { type: "button", class: "btn ghost", onclick: () => $("#login-dialog").showModal() }, "Use a name"));
    box.replaceChildren(h("p", { class: "small muted" }, "Keep a record of tips you skipped or saved for research, and see how they did against the Nifty 50 afterwards."));
    return;
  }
  const tip = currentTip();
  const log = (decision) => {
    const e = getJournal().filter((x) => !(x.symbol === tip.symbol && x.posted_on === tip.posted_on));
    setJournal([{ ...tip, decision }, ...e]);
    renderJournal();
  };
  const reset = async () => { try { setJournal(await getJSON("/api/journal/demo-seed")); } catch { setJournal([]); } renderJournal(); };
  actions.replaceChildren(h("span", { class: "small muted" }, "Logged in as ", h("b", {}, state.user.name)),
    state.user.demo ? h("button", { type: "button", class: "btn ghost", onclick: reset }, "Reset demo") : "",
    h("button", { type: "button", class: "btn ghost", onclick: logout }, "Log out"));
  const parts = [
    h("div", { class: "glass", style: "padding:10px;margin-bottom:10px" }, h("b", {}, "Log this tip"),
      tip ? [h("p", { class: "small muted", style: "margin:4px 0 8px" }, `${tip.symbol} · ${niceDate(tip.posted_on)} · ${tip.source_label}`),
        h("button", { type: "button", class: "btn", onclick: () => log("skipped") }, "Skipped after X-Ray"), " ",
        h("button", { type: "button", class: "btn ghost", onclick: () => log("research") }, "Saved for research")]
        : h("p", { class: "small muted" }, "Scan a tip that names a stock and a direction to log it."))];
  const entries = getJournal();
  const sum = h("div", {}, h("b", {}, "Your sources' record: 7 and 30 days later vs. Nifty 50"));
  parts.push(sum);
  box.replaceChildren(...parts);
  if (!entries.length) { sum.append(h("p", { class: "small muted" }, "No tips logged yet.")); return; }
  try {
    if (!state.journalSummary) state.journalSummary = await getJSON("/api/journal/summary", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ entries }) });
    const s = state.journalSummary;
    sum.append(h("p", { class: "small muted", style: "margin:4px 0" }, "Tips ", pill(s.provenance === "MIXED" ? "SYNTHETIC" : s.provenance || "REAL"),
      s.provenance === "MIXED" ? " + REAL" : "", " · prices ", pill(s.prices_provenance)));
    Object.values(s.groups).forEach((g) => sum.append(h("div", { class: "jstat" }, g.text)));
    sum.append(h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Posted"), h("th", {}, "Stock"), h("th", {}, "Decision"), h("th", { class: "num" }, "vs Nifty 7D"), h("th", { class: "num" }, "vs Nifty 30D"), h("th", {}, "Data"))),
      h("tbody", {}, s.rows.map((r) => h("tr", {}, h("td", {}, r.posted_on), h("td", {}, r.symbol), h("td", {}, r.decision_label),
        h("td", { class: `num ${signClass(r.vs_nifty_7d)}` }, r.vs_nifty_7d === null || r.vs_nifty_7d === undefined ? "Not enough data" : pct(r.vs_nifty_7d)),
        h("td", { class: `num ${signClass(r.vs_nifty_in_claimed_direction)}` }, r.status === "scored" ? pct(r.vs_nifty_in_claimed_direction) : "Not enough data"),
        h("td", {}, pill(r.provenance))))))));
    sum.append(h("p", { class: "small muted" }, "Looking back only: how each stock did over 30 days, in the direction the tip claimed."));
  } catch (err) {
    sum.append(h("p", { class: "small neg" }, String(err.message || err)));
  }
}

// The Desk, the Auditor and the Journal are separate cards that are always shown; nothing is hidden behind a tab.
function selectRtab(name) {
  ["desk", "auditor", "journal"].forEach((n) => { $(`#rp-${n}`).hidden = false; });
  if (name === "journal") renderJournal();
}
// Header links for the Auditor and the Journal open the Workspace and scroll to their card.
function jumpTo(id) {
  showView("workspace");
  requestAnimationFrame(() => $(`#${id}`)?.scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "start" }));
}

// ------------------------------------------------------------------ other views
const FAILURES = [
  ["\"paisa double pakka\"", "\"pakka\" (Hinglish for \"for sure\") matched the listed company Pakka Ltd", "Hinglish and Kannada filler words are ignored"],
  ["Song lyrics: \"Music video\", \"West\"", "A capitalised word that starts one company name was read as a stock", "A single word counts only if it is a company's full short name or a known nickname"],
  ["\"Adani stocks are falling\"", "Read as Adani Enterprises, though Adani is a group of listed companies", "Group names are shown as ambiguous and not scored"],
  ["A 2025 tip naming TATAMOTORS", "The symbol no longer exists after the 2025 demerger", "NSE's symbol-change file maps it to TMPV"],
  ["\"Don't touch SBIN, target 100\"", "The named price made it look like a rise call", "Any negation stops FinProof from guessing a direction"],
  ["KOTAKBANK post quoting ₹1,930 (Feb 2025)", "Price history is split-adjusted (about ₹386), so levels were off by 5×", "The post's prices are rescaled before comparing"],
  ["\"pay 98xxxxxx01@paytm\"", "\"98x\" in a masked number was read as a \"10x\"-style promise", "The pattern now needs a whole word"],
  ["ITC, 28 May 2025", "32× its usual volume with no hype at all", "Known limit: volume alone can't tell a pump from a large one-off trade"],
  ["SEBI check", "Our first saved copy stopped at SEBI's first page: 25 of 2,404 research analysts", "Every page of both lists is now saved (2,395 of 2,404 analysts, 1,092 of 1,095 advisers), and the check looks for a registration number first"],
];

function showView(name) {
  $$(".tab[data-view]").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  ["workspace", "sources", "study", "failures"].forEach((v) => { $(`#view-${v}`).hidden = v !== name; });
  if (name === "sources") loadSources();
  if (name === "study") loadStudy();
  if (name === "failures") loadFailures();
  if (name === "workspace" && state.chart) requestAnimationFrame(applyRange);
}

async function loadSources() {
  const v = $("#view-sources");
  v.replaceChildren(h("div", { class: "glass panel" }, h("p", { class: "muted" }, "Scoring tips against NSE prices…")));
  try {
    state.sources = state.sources || await getJSON("/api/sources");
    state.signalMap = state.signalMap || await getJSON("/api/signal-map").catch(() => null);
    const detail = h("div", { class: "glass panel" }, h("p", { class: "muted" }, "Pick a source to see each tip against the Nifty 50."));
    v.replaceChildren(h("div", { class: "view-grid" },
      h("div", { class: "glass panel rise" }, h("h2", {}, "Sources & track records"),
        h("p", { class: "small muted" }, "Each tip is scored 30 days after posting: it matched its claim if the stock beat the Nifty 50 in the claimed direction. Fewer than 10 scored tips: no percentage."),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", {}, "Source"), h("th", {}, "Data"), h("th", { class: "num" }, "Scored"), h("th", { class: "num" }, "Matched claim"), h("th", { class: "num" }, "Avg vs Nifty"))),
          h("tbody", {}, state.sources.map((r) => h("tr", { class: "click", onclick: () => loadSource(r.source_id, detail) },
            h("td", {}, r.source_label), h("td", {}, pill(r.provenance)), h("td", { class: "num" }, r.scored),
            h("td", { class: "num" }, r.enough_history ? `${r.worked} of ${r.scored} (${Math.round(r.hit_rate * 100)}%)` : "not enough history"),
            h("td", { class: `num ${signClass(r.avg_excess_return)}` }, r.enough_history ? pct(r.avg_excess_return) : "–"))))))),
      detail), state.signalMap ? signalMap(state.signalMap) : "");
  } catch (err) {
    v.replaceChildren(h("div", { class: "glass panel neg" }, String(err.message || err)));
  }
}

async function loadSource(id, box) {
  const d = await getJSON(`/api/sources/${encodeURIComponent(id)}`);
  const scored = d.tips.filter((t) => t.horizons["30"].status === "scored");
  const max = Math.max(0.05, ...scored.map((t) => Math.abs(t.horizons["30"].excess_return)));
  box.replaceChildren(h("h2", {}, d.record.source_label, " ", pill(d.record.provenance)),
    h("p", { class: "small" }, d.record.enough_history ? `${d.record.worked} of ${d.record.scored} tips matched their claim · average ${pct(d.record.avg_excess_return)} vs the Nifty 50`
      : `Only ${d.record.scored} scored tips: too few for a percentage.`),
    h("div", { class: "spark", style: "height:90px" }, scored.map((t) => h("i", { title: `${t.posted_on} ${t.symbol}: ${pct(t.horizons["30"].excess_return)} vs Nifty`,
      style: `height:${Math.max(4, (Math.abs(t.horizons["30"].excess_return) / max) * 86)}px;background:${t.horizons["30"].worked ? "#10b981" : "#ef4444"}` }))),
    h("p", { class: "small muted" }, "Click a tip to see it on the chart."),
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Posted"), h("th", {}, "Stock"), h("th", {}, "Claimed"), h("th", { class: "num" }, "vs Nifty 30D"), h("th", {}, "Result"))),
      h("tbody", {}, d.tips.map((t) => { const r = t.horizons["30"]; return h("tr", { class: "click", onclick: async () => { showView("workspace"); await setChart(t.symbol, { pinDate: t.posted_on, pinLabel: d.record.source_label }); } },
        h("td", {}, t.posted_on), h("td", {}, t.symbol), h("td", {}, t.direction === "up" ? "rise" : "fall"),
        h("td", { class: `num ${signClass(r.excess_return)}` }, pct(r.excess_return)), h("td", {}, r.status !== "scored" ? r.status : r.worked ? "Matched" : "Did not match")); })))));
}

async function loadStudy() {
  const v = $("#view-study");
  let info = { set: "?", practice: true, tips: 0, ready: false, problems: [], participant_urls: [] };
  try { info = await getJSON("/api/study/info"); } catch { /* shown as unknown */ }
  v.replaceChildren(h("div", { class: "view-grid" },
    h("div", { class: "glass panel rise" }, h("h2", {}, "Decision Study"),
      h("p", {}, "Does the card help people avoid bad tips without losing trust in good ones? A counterbalanced test measures it."),
      h("dl", { class: "kv" }, h("dt", {}, "Tip set"), h("dd", {}, info.set, " ", pill(info.practice ? "SYNTHETIC" : "REAL"), ` · ${info.tips} tips`),
        h("dt", {}, "Status"), h("dd", {}, info.ready ? "Ready" : `Not ready: ${info.problems.join(" ")}`),
        h("dt", {}, "Phones open"), h("dd", {}, ...(info.participant_urls.length ? info.participant_urls.map((u) => h("div", {}, h("code", { class: "url" }, u))) : ["–"]))),
      h("p", {}, h("a", { class: "btn", href: "study.html", target: "_blank", rel: "noopener", style: "text-decoration:none" }, "Open participant page"), " ",
        h("a", { class: "btn ghost", href: "results.html", target: "_blank", rel: "noopener", style: "text-decoration:none" }, "Live results (facilitator)"))),
    h("div", { class: "glass panel rise", style: "--i:1" }, h("h2", {}, "How the test works"),
      h("ul", { class: "small" },
        h("li", {}, "12 past tips: 6 that beat the Nifty 50 over 30 days, 6 that did not."),
        h("li", {}, "Each person sees 6 with the FinProof card and 6 without; 4 groups rotate which half and which comes first."),
        h("li", {}, "Cards in the test show only what was known before the post: no outcomes leak."),
        h("li", {}, "Success decided in advance: fewer bad tips acted on (95% CI below 0), and trust in good tips not down by more than 10 points."),
        h("li", {}, "Bootstrap 95% CI and paired permutation p-value, recomputed from the answer log.")))));
}

function loadFailures() {
  $("#view-failures").replaceChildren(h("div", { class: "view-grid" },
    h("div", { class: "glass panel rise" }, h("h2", {}, "Failure cases found on real data"),
      h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Input"), h("th", {}, "What went wrong"), h("th", {}, "What we did"))),
        h("tbody", {}, FAILURES.map(([a, b, c]) => h("tr", {}, h("td", {}, a), h("td", { style: "white-space:normal" }, b), h("td", { style: "white-space:normal" }, c))))))),
    h("div", { class: "glass panel rise", style: "--i:1" }, h("h2", {}, "Real vs synthetic data"),
      h("ul", { class: "provenance" },
        h("li", {}, pill("REAL"), " NSE daily prices and volumes, cached for offline use"),
        h("li", {}, pill("REAL"), " NSE equity list and symbol-change file"),
        h("li", {}, pill("REAL"), " SEBI research analyst and investment adviser lists (3,487 names, saved 21 Nov 2026)"),
        h("li", {}, pill("SYNTHETIC"), " Sample posts on the workspace"),
        h("li", {}, pill("SYNTHETIC"), " 34 demo tips from three demo channels (outcomes use real prices)"),
        h("li", {}, pill("SYNTHETIC"), " 12 practice posts for the decision study"),
        h("li", {}, pill("SYNTHETIC"), " 4 Demo Investor journal entries")))));
}

// ------------------------------------------------------------------ wiring + start
$("#scan-form").addEventListener("submit", (e) => { e.preventDefault(); runScan($("#scan-input").value); });
$("#scan-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#scan-form").requestSubmit(); } });
// The scanner grows with the pasted post (up to SCAN_MAX px), so multi-line forwards are never clipped.
const SCAN_MAX = 150;
function growScan({ top = false } = {}) {
  const el = $("#scan-input");
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, SCAN_MAX)}px`;
  el.classList.toggle("overflowing", el.scrollHeight > SCAN_MAX);
  if (top) el.scrollTop = 0;
}
function setScanText(text) { $("#scan-input").value = text; growScan({ top: true }); }
$("#scan-input").addEventListener("input", () => growScan());
addEventListener("resize", () => growScan());
$("#edit-apply").addEventListener("click", () => runScan(state.text, { sample: state.sample, url: state.url, posted_on: $("#edit-date").value || null, source: $("#edit-source").value.trim() || null }));
$("#edit-cancel").addEventListener("click", () => { $("#edit-pop").hidden = true; });
$("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#ask-input").value; $("#ask-input").value = ""; ask(q); });
$$("[data-range]").forEach((b) => b.addEventListener("click", () => { $$("[data-range]").forEach((x) => x.classList.toggle("active", x === b)); state.range = Number(b.dataset.range); applyRange(); }));
$("#nifty-toggle").addEventListener("change", applyRange);
$$(".tab").forEach((b) => b.addEventListener("click", () => (b.dataset.jump ? jumpTo(b.dataset.jump) : showView(b.dataset.view))));
$$(".rtab").forEach((b) => b.addEventListener("click", () => selectRtab(b.dataset.rtab)));
$("#investor-btn").addEventListener("click", () => { if (state.user) { renderJournal(); jumpTo("card-journal"); } else login({ name: "Demo Investor", demo: true }); });
$("#login-cancel").addEventListener("click", () => $("#login-dialog").close());
$("#demo-login").addEventListener("click", () => login({ name: "Demo Investor", demo: true }));
$("#name-login").addEventListener("click", () => { const n = $("#login-name").value.trim().slice(0, 40); if (n) login({ name: n, demo: false }); });
$("#theme-btn").addEventListener("click", () => setTheme(theme() === "light" ? "dark" : "light"));
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSamples(); });
addEventListener("resize", fitRight);

// Right column: from where it starts down to the bottom of the screen, so the chat input is always visible.
function fitRight() {
  const top = $("#tour-auditor").getBoundingClientRect().top + scrollY;
  document.documentElement.style.setProperty("--right-h", `${Math.max(480, innerHeight - top - 12)}px`);
}
// Samples ▾: the made-up demo posts and links, grouped in one popover instead of a row of buttons.
function closeSamples() {
  $("#samples-pop").hidden = true; $("#samples-btn").setAttribute("aria-expanded", "false");
  $("#n50-pop").hidden = true; $("#n50-btn").setAttribute("aria-expanded", "false");
}
function renderSamples() {
  const item = (s) => h("button", { type: "button", role: "menuitem", class: "sample-item", "data-id": s.id,
    onclick: () => { setScanText(s.text); runScan(s.text, { sample: s.real ? null : s.id }); } }, s.label);
  $("#samples-pop").replaceChildren(h("div", { class: "sp-head" }, "Demo samples ", pill("SYNTHETIC")),
    h("div", { class: "sp-group" }, "Posts"), ...SAMPLES.filter((s) => !s.link && !s.real).map(item),
    h("div", { class: "sp-group" }, "Links (cached)"), ...SAMPLES.filter((s) => s.link).map(item),
    h("div", { class: "sp-group sp-real" }, "Real SEBI case ", pill("REAL")), ...SAMPLES.filter((s) => s.real).map(item));
}
$("#samples-btn").addEventListener("click", (e) => {
  e.stopPropagation();
  const open = $("#samples-pop").hidden;
  $("#samples-pop").hidden = !open;
  $("#samples-btn").setAttribute("aria-expanded", String(open));
});
document.addEventListener("click", (e) => { if (!e.target.closest(".samples-wrap")) closeSamples(); });
$("#n50-btn").addEventListener("click", (e) => {
  e.stopPropagation();
  const open = $("#n50-pop").hidden;
  closeSamples();
  $("#n50-pop").hidden = !open;
  $("#n50-btn").setAttribute("aria-expanded", String(open));
  if (open) { $("#n50-q").value = ""; renderN50(""); $("#n50-q").focus(); }
});
$("#n50-q").addEventListener("input", (e) => renderN50(e.target.value));
renderSamples();
renderJournal();

// Header status: HYBRID · LIVE when the network answers, HYBRID · CACHE when it does not.
async function refreshStatus() {
  try {
    state.health = await getJSON("/api/health");
    const live = !!state.health.network?.live;
    $("#st-mode").textContent = `// ${state.health.network?.label || "HYBRID"}`;
    $("#st-mode").className = `sp ${live ? "ok" : "amber"}`;
  } catch {
    $("#st-mode").textContent = "// SERVER OFFLINE";
    $("#st-mode").className = "sp amber";
  }
  if (state.card) auditorStatus();
}
setInterval(refreshStatus, 30000);

(async function start() {
  await refreshStatus();
  try { state.prompts = await getJSON("/api/auditor/prompts"); } catch { state.prompts = []; }
  loadNifty50();
  renderPrompts();
  fitRight();
  state.user = store.get("finproof-user", null);
  updateInvestor();
  renderJournal();
  renderTry();
  setTheme(theme(), { quiet: true });
})();

// ------------------------------------------------------------------ T.R.U.C.E. look (visual only)
// Segmented controls get a thumb that slides to the selected option; panels get a glow that follows
// the pointer; buttons get a ripple from where they were pressed. Delete this block to undo.
const THUMB_GROUPS = [".tabs", ".rtabs", "#rp-desk .seg", '.seg[aria-label="Chart window"]'];
let thumbFrame = 0;
function syncThumbs() {
  thumbFrame = 0;
  THUMB_GROUPS.forEach((sel) => $$(sel).forEach((g) => {
    const b = [...g.children].find((x) => x.tagName === "BUTTON" && x.classList.contains("active"));
    if (!b || !b.offsetWidth) { g.classList.remove("has-thumb"); return; }
    g.style.setProperty("--th-x", `${b.offsetLeft}px`);
    g.style.setProperty("--th-y", `${b.offsetTop}px`);
    g.style.setProperty("--th-w", `${b.offsetWidth}px`);
    g.style.setProperty("--th-h", `${b.offsetHeight}px`);
    g.classList.add("has-thumb");
  }));
}
const queueThumbs = () => { if (!thumbFrame) thumbFrame = requestAnimationFrame(syncThumbs); };
new MutationObserver(queueThumbs).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class", "hidden"] });
addEventListener("resize", queueThumbs);
document.fonts?.ready.then(() => { queueThumbs(); state.chart?.applyOptions({ layout: { fontFamily: CHART_FONT } }); });
let glowFrame = 0;
document.addEventListener("pointermove", (e) => {
  if (glowFrame) return;
  const { clientX, clientY, target } = e;
  glowFrame = requestAnimationFrame(() => {
    glowFrame = 0;
    const panel = target instanceof Element ? target.closest(".glass") : null;
    if (!panel) return;
    const box = panel.getBoundingClientRect();
    panel.style.setProperty("--mx", `${clientX - box.left}px`);
    panel.style.setProperty("--my", `${clientY - box.top}px`);
  });
}, { passive: true });
document.addEventListener("pointerdown", (e) => {
  const btn = e.target instanceof Element ? e.target.closest(".scan-btn, .btn-tour, .btn, .pill-btn, .samples-btn, .ask button") : null;
  if (!btn || REDUCED) return;
  const box = btn.getBoundingClientRect();
  const dot = h("span", { class: "ts-ripple-dot", "aria-hidden": "true", style: `left:${e.clientX - box.left}px;top:${e.clientY - box.top}px` });
  btn.append(dot);
  setTimeout(() => dot.remove(), 600);
}, { passive: true });
