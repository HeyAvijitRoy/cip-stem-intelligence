// =========================================
// app.js
// =========================================
// Summary:
// - Loads the published index: /docs/data/processed/cip_stem_index.json
// - Searches by:
//   - CIP (2/4/6 digit, canonicalized)
//   - keyword (title/definition)
// - STEM-only filter
// - URL query params: ?q=...&stem=1
// =========================================

const INDEX_URL = "../data/processed/cip_stem_index.json";

const elQ = document.getElementById("q");
const elStem = document.getElementById("stemOnly");
const elClear = document.getElementById("btnClear");
const elStatus = document.getElementById("statusText");
const elMeta = document.getElementById("metaText");
const elResults = document.getElementById("results");

let INDEX = null;

// --- helpers ---
function canonicalCip(raw) {
  const s = (raw || "").trim().replace(/^[\[\(]+|[\]\)]+$/g, "");
  if (!s) return "";

  if (!s.includes(".")) {
    // 2-digit family
    if (/^\d{2}$/.test(s)) return `${s}.0000`;
    return s;
  }

  const [left, rightRaw] = s.split(".", 2);
  const left2 = left.trim();
  const right = (rightRaw || "").trim();

  if (/^\d{2}$/.test(left2) && /^\d{2}$/.test(right)) return `${left2}.${right}00`;      // 14.09 -> 14.0900
  if (/^\d{2}$/.test(left2) && /^\d{4}$/.test(right)) return `${left2}.${right}`;        // 14.0903 -> 14.0903
  if (/^\d{2}$/.test(left2) && /^\d{1,4}$/.test(right)) return `${left2}.${right.padStart(4, "0")}`;

  return s;
}

function tokenize(q) {
  return (q || "")
    .toLowerCase()
    .split(/\s+/)
    .map(t => t.trim())
    .filter(Boolean);
}

function setUrlState(q, stemOnly) {
  const url = new URL(window.location.href);
  if (q) url.searchParams.set("q", q);
  else url.searchParams.delete("q");

  if (stemOnly) url.searchParams.set("stem", "1");
  else url.searchParams.delete("stem");

  window.history.replaceState({}, "", url.toString());
}

function readUrlState() {
  const url = new URL(window.location.href);
  const q = url.searchParams.get("q") || "";
  const stem = url.searchParams.get("stem") === "1";
  return { q, stem };
}

function render(records, q, stemOnly) {
  if (!records || records.length === 0) {
    elResults.innerHTML = `<div class="small">No matches.</div>`;
    elStatus.textContent = `0 results`;
    setUrlState(q, stemOnly);
    return;
  }

  elStatus.textContent = `${records.length} result${records.length === 1 ? "" : "s"}`;
  setUrlState(q, stemOnly);

  const html = records.slice(0, 200).map(r => {
    const badge = r.stemEligible ? `<span class="badge stem">STEM</span>` : `<span class="badge">Non-STEM</span>`;
    const title = r.title || "(no title)";
    const def = r.definition || "(no definition available)";
    const source = r.ncesSourceUrl ? `NCES: ${r.ncesSourceUrl}` : "NCES: (missing)";
    return `
      <div class="card">
        <div class="cardTop">
          <div class="cip">${r.cip}</div>
          ${badge}
        </div>
        <div class="title">${title}</div>
        <div class="def">${def}</div>
        <div class="small">${source}</div>
      </div>
    `;
  }).join("");

  elResults.innerHTML = html + (records.length > 200 ? `<div class="small">Showing first 200 results…</div>` : "");
}

function searchIndex(q, stemOnly) {
  if (!INDEX) return [];

  const qTrim = (q || "").trim();
  const toks = tokenize(qTrim);

  // CIP intent? (if user types something like 14 / 14.09 / 14.0900)
  const asCip = canonicalCip(qTrim);
  const isCipQuery = !!asCip && (/^\d{2}\.\d{4}$/.test(asCip));

  const records = INDEX.records || [];

  let hits = records;

  if (stemOnly) {
    hits = hits.filter(r => r.stemEligible === true);
  }

  if (qTrim === "") return hits.slice(0, 50);

  if (isCipQuery) {
    // prefix match: "14.0000" should match anything starting with "14."
    const family = asCip.slice(0, 2);
    const roll4 = asCip.slice(0, 5); // "14.09"
    const exact = asCip;

    // if user entered 14 -> canonical is 14.0000 (family search)
    if (exact.endsWith(".0000")) {
      hits = hits.filter(r => (r.cip || "").startsWith(`${family}.`));
    }
    // if user entered 14.09 -> canonical is 14.0900 (4-digit rollup search)
    else if (exact.endsWith("00")) {
      hits = hits.filter(r => (r.cip || "").startsWith(`${roll4}`));
    }
    // else exact 6-digit
    else {
      hits = hits.filter(r => (r.cip || "") === exact);
    }

    return hits;
  }

  // keyword search (title + definition)
  hits = hits.filter(r => {
    const hay = `${r.title || ""} ${r.definition || ""}`.toLowerCase();
    return toks.every(t => hay.includes(t));
  });

  return hits;
}

// --- boot ---
async function loadIndex() {
  const res = await fetch(INDEX_URL, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load index: ${res.status}`);
  return await res.json();
}

function update() {
  const q = elQ.value;
  const stemOnly = elStem.checked;
  const hits = searchIndex(q, stemOnly);
  render(hits, q, stemOnly);
}

(async function init() {
  const state = readUrlState();
  elQ.value = state.q;
  elStem.checked = state.stem;

  try {
    INDEX = await loadIndex();
    elMeta.textContent = `Loaded: ${INDEX.meta?.record_count ?? "?"} records | Generated: ${INDEX.meta?.generated_utc ?? "?"}`;
    update();
  } catch (e) {
    elStatus.textContent = "Failed to load index (check console).";
    elResults.innerHTML = `<div class="small">${String(e)}</div>`;
  }

  elQ.addEventListener("input", () => update());
  elStem.addEventListener("change", () => update());
  elClear.addEventListener("click", () => {
    elQ.value = "";
    elStem.checked = false;
    update();
    elQ.focus();
  });
})();
