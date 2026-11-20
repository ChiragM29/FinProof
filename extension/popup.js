const DEFAULTS = { backend: "http://localhost:8000", enabled: true };
const enabled = document.getElementById("enabled");
const backend = document.getElementById("backend");

chrome.storage.sync.get(DEFAULTS).then((s) => {
  enabled.checked = s.enabled;
  backend.value = s.backend;
});
enabled.addEventListener("change", () => chrome.storage.sync.set({ enabled: enabled.checked }));
backend.addEventListener("change", () => chrome.storage.sync.set({ backend: backend.value.trim().replace(/\/$/, "") }));
