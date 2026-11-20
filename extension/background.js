// Fetches cards from the FinProof backend. The content script cannot call
// localhost itself under YouTube's page rules, so it asks this worker.

const DEFAULTS = { backend: "http://localhost:8000", enabled: true };

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type !== "finproof-card" || !/^[A-Za-z0-9_-]{11}$/.test(msg.videoId || "")) return false;
  (async () => {
    const s = await settings();
    if (!s.enabled) return reply({ disabled: true });
    try {
      const r = await fetch(`${s.backend}/api/youtube/${msg.videoId}`);
      const data = await r.json();
      reply(r.ok ? { card: data } : { error: data.detail || `Backend error ${r.status}` });
    } catch {
      reply({ error: "FinProof backend is not running. Start it, then reload this page." });
    }
  })();
  return true; // keep the channel open for the async reply
});
