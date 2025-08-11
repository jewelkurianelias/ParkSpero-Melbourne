// main/static/js/predictions.js
(function () {
  const ENDPOINT = "/api/v1/predictions/";
  const ids = {
    UNOCCUPIED: "count-unoccupied",
    VACATE_15M: "count-vacate-15",
    VACATE_30M: "count-vacate-30",
    VACATE_60M: "count-vacate-60",
    OCCUPIED_GT_60M: "count-gt60",
    PERMIT_PARKING: "count-permit",
  };
  let refreshTimer = null;

  async function fetchPredictions() {
    const res = await fetch(ENDPOINT, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  function setCounts(counts) {
    Object.entries(ids).forEach(([key, elId]) => {
      const el = document.getElementById(elId);
      if (el) el.textContent = counts[key] ?? 0;
    });
  }

  function humanETA(item) {
    if (item.status.toLowerCase() === "unoccupied") return "—";
    if (item.allowed_minutes == null) return "> 60 min";
    const remaining = Math.max(0, Math.round(item.allowed_minutes - item.minutes_elapsed));
    return `${remaining} min`;
  }

  function setUpdated(genIso, ttl) {
    const el = document.getElementById("pred-updated");
    if (!el) return;
    const gen = new Date(genIso);
    const now = new Date();
    const age = Math.max(0, Math.round((now - gen) / 1000));
    const stale = age > (ttl * 3);
    el.textContent = `Updated ${age}s ago${stale ? " (stale)" : ""}`;
  }

  function setTable(items) {
    const tbody = document.querySelector("#pred-table tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    // (optional) sort by ETA ascending, unoccupied first
    items.sort((a, b) => {
      const aEta = a.allowed_minutes == null ? 9999 : Math.max(0, a.allowed_minutes - a.minutes_elapsed);
      const bEta = b.allowed_minutes == null ? 9999 : Math.max(0, b.allowed_minutes - b.minutes_elapsed);
      return a.classification === "UNOCCUPIED" && b.classification !== "UNOCCUPIED" ? -1
           : b.classification === "UNOCCUPIED" && a.classification !== "UNOCCUPIED" ? 1
           : aEta - bEta;
    });
    const rows = items.slice(0, 500).map(it => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${it.street ?? ""}</td>
        <td>${it.kerbsideid ?? ""}</td>
        <td>${it.status}</td>
        <td>${it.classification}</td>
        <td>${humanETA(it)}</td>
        <td>${it.restriction_code ?? ""}</td>
      `;
      return tr;
    });
    rows.forEach(r => tbody.appendChild(r));
  }

  async function refreshOnce() {
    try {
      const data = await fetchPredictions();
      setCounts(data.counts || {});
      setTable(data.items || []);
      setUpdated(data.generated_at, data.ttl || 60);
      scheduleNext(data.ttl || 60);
    } catch (e) {
      console.error("Predictions fetch failed:", e);
      // retry in 30s on error
      scheduleNext(30);
    }
  }

  function scheduleNext(ttl) {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshOnce, ttl * 1000);
  }

  document.addEventListener("DOMContentLoaded", refreshOnce);
})();
