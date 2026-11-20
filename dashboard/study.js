// Decision test, participant side. One screen at a time:
// intro -> part 1 (6 tips) -> part 2 (6 tips) -> thank you.
// Uses h() and renderCompactCard() from card-view.js.

const main = document.getElementById("study");
const PLATFORM = { telegram: "Telegram", whatsapp: "WhatsApp forward", youtube: "YouTube", instagram: "Instagram", x: "X", other: "Post" };
const state = { plan: null, steps: [], at: 0, background: {} };

let onKey = null; // keyboard shortcuts for the current screen

document.addEventListener("keydown", (e) => {
  if (onKey && !e.ctrlKey && !e.metaKey && !e.altKey) onKey(e.key.toLowerCase(), e);
});

function show(...nodes) {
  onKey = null;
  main.replaceChildren(...nodes);
  window.scrollTo(0, 0);
}

function fail(message) {
  show(h("div", { class: "card" }, h("h2", {}, "Sorry, something went wrong"), h("p", {}, message)));
}

async function postJSON(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, status: r.status, data };
}

function fmtDate(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function choiceRow(options, onPick) {
  const row = h("div", { class: "choices" });
  row.press = {};
  for (const [value, label] of options) {
    const b = h("button", { type: "button", class: "choice", onclick: () => {
      if (b.disabled) return;
      row.querySelectorAll(".choice").forEach((x) => x.classList.toggle("selected", x === b));
      onPick(value);
    } }, label);
    row.press[value] = () => b.click();
    row.append(b);
  }
  return row;
}

// ------------------------------------------------------------------ intro
async function init() {
  let info;
  try {
    info = await (await fetch("/api/study/info")).json();
  } catch {
    return fail("Can't reach the FinProof server. Check that you're on the same Wi-Fi as the laptop running it.");
  }
  if (info.practice) document.getElementById("practice-banner").hidden = false;
  if (!info.ready) return fail(`The test isn't ready yet. ${info.problems.join(" ")}`);
  showIntro(info.tips);
}

function showIntro(total) {
  const question = (key, label, options) => h("div", { class: "q" },
    h("p", { class: "q-label" }, label),
    choiceRow(options, (v) => { state.background[key] = v; }));
  const start = h("button", { type: "button", class: "primary wide", onclick: begin }, "Start");
  show(h("div", { class: "card" },
    h("h2", {}, "Would you act on these stock tips?"),
    h("p", {}, `You'll see ${total} stock tips like the ones shared on YouTube, Telegram and WhatsApp. For each one, say whether you would act on it, as if it were your own money.`),
    h("p", {}, "For some tips you'll also see a FinProof card with extra information about the source and the post. Use it if you find it helpful."),
    h("p", { class: "small muted" }, "About 5 minutes. Taking part is voluntary and you can stop at any time. We don't ask for your name: we save only your answers and how long each one took."),
    h("h3", {}, "Two quick questions (optional)"),
    question("invests", "Do you trade or own stocks yourself?", [["regularly", "Yes, regularly"], ["sometimes", "Sometimes"], ["not_yet", "Not yet"]]),
    question("sees_tips", "How often do you see stock tips on social media?", [["daily", "Daily"], ["weekly", "Weekly"], ["rarely", "Rarely"], ["never", "Never"]]),
    start));
}

async function begin(e) {
  e.target.disabled = true;
  e.target.textContent = "Starting…";
  const res = await postJSON("/api/study/start", { background: state.background }).catch(() => null);
  if (!res || !res.ok) return fail(res?.data?.detail || "Could not start the test.");
  state.plan = res.data;
  let number = 0;
  res.data.blocks.forEach((block, i) => {
    state.steps.push({ kind: "block", index: i, condition: block.condition, count: block.tips.length });
    for (const tip of block.tips) state.steps.push({ kind: "tip", condition: block.condition, tip, number: ++number });
  });
  state.steps.push({ kind: "done" });
  next();
}

function next() {
  const step = state.steps[state.at++];
  if (step.kind === "block") return showBlock(step);
  if (step.kind === "tip") return showTip(step);
  return showDone();
}

// ------------------------------------------------------------------ parts
function showBlock(step) {
  const withCard = step.condition === "card";
  show(h("div", { class: "card" },
    h("p", { class: "small muted" }, `Part ${step.index + 1} of ${state.plan.blocks.length}`),
    h("h2", {}, withCard ? "Tips with a FinProof card" : "Tips on their own"),
    h("p", {}, withCard
      ? `The next ${step.count} tips each come with a FinProof card. It only uses information that was available when the tip was posted.`
      : `For the next ${step.count} tips, decide using only the post itself.`),
    h("button", { type: "button", class: "primary wide", onclick: next }, "Continue")));
  onKey = (k) => { if (k === "enter") next(); };
}

function showTip(step) {
  const t = step.tip;
  const shownAt = performance.now();
  let answer = null;
  let ms = 0;

  const status = h("p", { class: "small muted status" });
  const sureRow = choiceRow([[1, "Not sure"], [2, "Fairly sure"], [3, "Very sure"]], (v) => submit(v));
  const sure = h("div", { class: "q", hidden: "" }, h("p", { class: "q-label" }, "How sure are you?"), sureRow);
  const decideRow = choiceRow([["yes", "Yes, I would act on it"], ["no", "No"]], (v) => {
    answer = v;
    ms = Math.round(performance.now() - shownAt);
    sure.hidden = false;
    sure.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  const decide = h("div", { class: "q" }, h("p", { class: "q-label" }, "Would you act on this tip?"), decideRow);
  let sent = false;

  async function submit(confidence) {
    if (sent) return;
    sent = true;
    main.querySelectorAll(".choice").forEach((b) => (b.disabled = true));
    status.textContent = "Saving…";
    const res = await postJSON("/api/study/answer", {
      participant_id: state.plan.participant_id, tip_id: t.tip_id, answer, confidence, ms,
    }).catch(() => null);
    if (res && (res.ok || res.status === 409)) return next();
    sent = false;
    status.replaceChildren("Couldn't save this answer. ",
      h("button", { type: "button", class: "chip", onclick: () => submit(confidence) }, "Try again"));
  }

  const post = h("div", { class: "post" },
    h("div", { class: "post-meta" }, `${PLATFORM[t.platform] || "Post"} · ${t.source_label} · ${fmtDate(t.posted_on)}`),
    t.title ? h("div", { class: "post-title" }, t.title) : "",
    h("div", { class: "post-text" }, t.text));

  const total = state.plan.total;
  show(
    h("div", { class: "progress" },
      h("span", {}, `Tip ${step.number} of ${total}`),
      h("div", { class: "bar" }, h("div", { class: "fill", style: `width:${((step.number - 1) / total) * 100}%` }))),
    post,
    step.condition === "card" ? renderCompactCard(t.card) : "",
    h("div", { class: "card" }, decide, sure, status,
      h("p", { class: "small muted keys" }, "Keyboard: Y or N, then 1, 2 or 3.")));
  onKey = (k) => {
    if (k === "y") decideRow.press.yes();
    else if (k === "n") decideRow.press.no();
    else if (answer && ["1", "2", "3"].includes(k)) sureRow.press[Number(k)]();
  };
}

async function showDone() {
  show(h("div", { class: "card" },
    h("h2", {}, "Thank you!"),
    h("p", {}, "Your answers are saved."),
    h("p", {}, "Please don't discuss the tips with people who haven't taken part yet, so their answers stay their own.")));
  await postJSON("/api/study/finish", { participant_id: state.plan.participant_id }).catch(() => null);
}

init();
