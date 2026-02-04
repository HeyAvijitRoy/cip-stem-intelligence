// =========================================
// loadIndex.js
// =========================================
// Summary:
// - Loads the frontend index JSON (cip_stem_index.json)
// - Adds a few derived fields for faster search
// - Returns { meta, records } ready for query engine usage
// =========================================

export function normalizeText(s) {
  return (s || "")
    .toString()
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

export function normalizeCipInput(cip) {
  // Accepts: "14", "14.09", "14.0900"
  // Returns canonical "XX.XXXX" or "" if not parseable
  const raw = (cip || "").toString().trim();
  if (!raw) return "";

  // Remove brackets/parentheses if user pastes those
  const cleaned = raw.replace(/[\[\]\(\)]/g, "");

  if (/^\d{2}$/.test(cleaned)) {
    return `${cleaned}.0000`;
  }

  if (/^\d{2}\.\d{2}$/.test(cleaned)) {
    const [a, b] = cleaned.split(".");
    return `${a}.${b}00`;
  }

  if (/^\d{2}\.\d{4}$/.test(cleaned)) {
    return cleaned;
  }

  // If "14.9" or "14.903" etc, try to pad right side
  const m = cleaned.match(/^(\d{2})\.(\d{1,4})$/);
  if (m) {
    const left = m[1];
    const right = m[2].padStart(4, "0");
    return `${left}.${right}`;
  }

  return "";
}

export async function loadIndex({ path = "data/processed/cip_stem_index.json" } = {}) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load index: ${res.status} ${res.statusText}`);
  }

  const json = await res.json();
  const records = (json.records || []).map((r) => {
    const titleNorm = normalizeText(r.title);
    return {
      ...r,
      cipNorm: r.cip,             // already canonical
      cipFamily: r.cipFamily || r.cip.split(".")[0],
      titleNorm,
    };
  });

  return { meta: json.meta || {}, records };
}
