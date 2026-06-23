"use strict";

let providers = [];

function toast(message, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = "toast show" + (isError ? " error" : "");
  setTimeout(() => (el.className = "toast"), 2600);
}

function setMode(mode) {
  document.getElementById("mode").value = mode;
  document.querySelectorAll("#mode-toggle button").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === mode)
  );
  document.getElementById("manual-output-field").style.display =
    mode === "MANUAL" ? "flex" : "none";
}

function setManualOutput(out) {
  document.getElementById("manual_output").value = out;
  document.querySelectorAll("#manual-toggle button").forEach((b) =>
    b.classList.toggle("active", b.dataset.out === out)
  );
}

function tierLabel(p) {
  if (p.tier === "free") return "free";
  if (p.tier === "free-key") return "free · key required";
  return "paid · key required";
}

function renderProviderOptions(selectedId) {
  const sel = document.getElementById("provider");
  sel.innerHTML = providers
    .map((p) => `<option value="${p.id}">${p.name} (${tierLabel(p)})</option>`)
    .join("");
  if (selectedId) sel.value = selectedId;
  updateProviderHints();
}

function updateProviderHints() {
  const id = document.getElementById("provider").value;
  const p = providers.find((x) => x.id === id);
  if (!p) return;
  document.getElementById("provider-hint").textContent =
    `${tierLabel(p)} · ${p.homepage}`;
  document.getElementById("zone-hint").textContent =
    `${p.zone_hint} (e.g. ${p.zones.slice(0, 4).join(", ")})`;
  const warn = document.getElementById("key-warning");
  if (p.requires_key) {
    warn.style.display = "block";
    warn.textContent = `This provider needs ${p.needs_token_env} set in your .env file.`;
  } else {
    warn.style.display = "none";
  }
}

async function loadProviders() {
  const res = await fetch("/api/providers");
  if (res.status === 401) { window.location = "/login"; return; }
  providers = await res.json();
}

async function loadSettings() {
  const res = await fetch("/api/settings");
  if (res.status === 401) { window.location = "/login"; return; }
  const s = await res.json();

  renderProviderOptions(s.provider);
  document.getElementById("zone").value = s.zone;
  document.getElementById("poll_interval").value = s.poll_interval;
  document.getElementById("switch_price").value = s.switch_price;
  document.getElementById("threshold").value = s.threshold;
  document.getElementById("hysteresis_seconds").value = s.hysteresis_seconds;
  document.getElementById("gpio_high").value = s.gpio_high;
  document.getElementById("gpio_low").value = s.gpio_low;
  document.getElementById("retention_value").value = s.retention_value;
  document.getElementById("retention_unit").value = s.retention_unit;
  setMode(s.mode);
  setManualOutput(s.manual_output);
}

function collectPayload() {
  return {
    provider: document.getElementById("provider").value,
    zone: document.getElementById("zone").value,
    poll_interval: Number(document.getElementById("poll_interval").value),
    switch_price: Number(document.getElementById("switch_price").value),
    threshold: Number(document.getElementById("threshold").value),
    hysteresis_seconds: Number(document.getElementById("hysteresis_seconds").value),
    gpio_high: Number(document.getElementById("gpio_high").value),
    gpio_low: Number(document.getElementById("gpio_low").value),
    mode: document.getElementById("mode").value,
    manual_output: document.getElementById("manual_output").value,
    retention_value: Number(document.getElementById("retention_value").value),
    retention_unit: document.getElementById("retention_unit").value,
  };
}

async function saveSettings(evt) {
  evt.preventDefault();
  const payload = collectPayload();
  try {
    const res = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.status === 401) { window.location = "/login"; return; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      toast("Save failed: " + (err.detail || res.status), true);
      return;
    }
    toast("Settings saved");
  } catch (e) {
    toast("Network error: " + e.message, true);
  }
}

function init() {
  document.querySelectorAll("#mode-toggle button").forEach((b) =>
    b.addEventListener("click", () => setMode(b.dataset.mode))
  );
  document.querySelectorAll("#manual-toggle button").forEach((b) =>
    b.addEventListener("click", () => setManualOutput(b.dataset.out))
  );
  document.getElementById("provider").addEventListener("change", updateProviderHints);
  document.getElementById("settings-form").addEventListener("submit", saveSettings);
  document.getElementById("reload-btn").addEventListener("click", loadSettings);

  // Burger menu toggle
  const burger = document.getElementById("burger");
  const nav = document.getElementById("nav");
  if (burger && nav) {
    burger.addEventListener("click", () => {
      burger.classList.toggle("active");
      nav.classList.toggle("mobile-open");
    });
    document.addEventListener("click", (e) => {
      if (!burger.contains(e.target) && !nav.contains(e.target)) {
        burger.classList.remove("active");
        nav.classList.remove("mobile-open");
      }
    });
  }

  loadProviders().then(loadSettings);
}

init();
