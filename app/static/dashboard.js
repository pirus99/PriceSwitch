"use strict";

const REFRESH_MS = 5000;

function fmtAge(seconds) {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

function setBadge(el, text, cls) {
  el.textContent = text;
  el.className = `badge ${cls}`;
}

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    if (res.status === 401) { window.location = "/login"; return; }
    const s = await res.json();

    // Mode
    setBadge(document.getElementById("mode-badge"), s.mode, s.mode.toLowerCase());
    document.getElementById("manual-sub").textContent =
      s.mode === "MANUAL" ? `Manual selection active` : "Automatic price control";

    // Output
    const out = s.output || "NONE";
    const led = document.getElementById("output-led");
    led.className = "led " + (out === "LOW" ? "on-low" : out === "HIGH" ? "on-high" : "off");
    const outBadge = document.getElementById("output-badge");
    setBadge(outBadge, out, out.toLowerCase());
    document.getElementById("sim-note").textContent =
      s.simulated ? "GPIO simulated (no Pi hardware)" : "";

    // Price
    document.getElementById("price").textContent =
      s.price === null || s.price === undefined ? "—" : s.price.toFixed(2);
    document.getElementById("price-unit").textContent = s.unit || "";
    let meta = [];
    if (s.stale) meta.push("stale");
    if (s.fallback) meta.push("fallback");
    document.getElementById("price-meta").textContent =
      `Updated ${fmtTime(s.last_poll)}${meta.length ? " · " + meta.join(", ") : ""}`;

    // Age
    document.getElementById("age").textContent = fmtAge(s.price_age_seconds);
    document.getElementById("provider-zone").textContent =
      `${s.provider || "—"} · zone ${s.zone || "—"}`;

    // Error
    const errCard = document.getElementById("error-card");
    if (s.error) {
      errCard.style.display = "block";
      document.getElementById("error-text").textContent = s.error;
    } else {
      errCard.style.display = "none";
    }
  } catch (e) {
    console.error("status refresh failed", e);
  }
}

async function refreshLog() {
  try {
    const res = await fetch("/api/events?limit=100");
    if (res.status === 401) { window.location = "/login"; return; }
    const events = await res.json();
    const body = document.getElementById("log-body");
    if (!events.length) {
      body.innerHTML = '<tr><td colspan="5" class="muted">No switch events yet.</td></tr>';
      return;
    }
    body.innerHTML = events
      .map((ev) => {
        const cls = ev.state === "LOW" ? "low" : ev.state === "HIGH" ? "high" : "none";
        const price = ev.price === null || ev.price === undefined ? "—" : ev.price.toFixed(2);
        return `<tr>
          <td>${fmtTime(ev.ts)}</td>
          <td><span class="badge ${cls}">${ev.state}</span></td>
          <td>${price}</td>
          <td>${ev.mode}</td>
          <td class="muted">${ev.reason || ""}</td>
        </tr>`;
      })
      .join("");
  } catch (e) {
    console.error("log refresh failed", e);
  }
}

function tick() {
  refreshStatus();
  refreshLog();
}

tick();
setInterval(tick, REFRESH_MS);

// Burger menu toggle
const burger = document.getElementById("burger");
const nav = document.getElementById("nav");
if (burger && nav) {
  burger.addEventListener("click", () => {
    burger.classList.toggle("active");
    nav.classList.toggle("mobile-open");
  });
  // Close menu when clicking outside
  document.addEventListener("click", (e) => {
    if (!burger.contains(e.target) && !nav.contains(e.target)) {
      burger.classList.remove("active");
      nav.classList.remove("mobile-open");
    }
  });
}
