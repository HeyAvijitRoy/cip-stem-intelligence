// =========================================
// search.js
// =========================================
// Summary:
// - Pure query engine on top of the in-memory index
// - Supports:
//   - CIP exact match: "14.0900"
//   - CIP prefix/family match: "14" or "14.09"
//   - Title keyword match: "computer engineering"
// - Filters:
//   - STEM-only
// - Sorting:
//   - CIP ascending (default)
// =========================================

import { normalizeText, normalizeCipInput } from "./loadIndex.js";

export function buildQueryEngine(records) {
  const byCip = new Map(records.map((r) => [r.cipNorm, r]));

  function matchCipPrefix(record, userInputRaw) {
    const raw = (userInputRaw || "").trim();
    if (!raw) return false;

    // If user types "14" -> match cipFamily
    if (/^\d{2}$/.test(raw)) {
      return record.cipFamily === raw;
    }

    // If user types "14.09" -> match prefix "14.09" against record.cip "14.0900"
    if (/^\d{2}\.\d{2}$/.test(raw)) {
      return record.cipNorm.startsWith(raw);
    }

    return false;
  }

  function search({
    q = "",
    stemOnly = false,
    limit = 50
  } = {}) {
    const query = (q || "").trim();
    const qText = normalizeText(query);
    const qCipCanon = normalizeCipInput(query);

    let results = [];

    // 1) Exact CIP match wins
    if (qCipCanon && byCip.has(qCipCanon)) {
      const rec = byCip.get(qCipCanon);
      if (!stemOnly || rec.stemEligible) {
        results = [rec];
      } else {
        results = [];
      }
      return results;
    }

    // 2) Otherwise scan (still fast — ~2.7k records)
    for (const r of records) {
      if (stemOnly && !r.stemEligible) continue;

      let ok = false;

      // CIP family/prefix matching for inputs like "14" or "14.09"
      if (matchCipPrefix(r, query)) ok = true;

      // Title keyword matching
      if (!ok && qText) {
        // Simple contains — we can evolve later to token scoring
        if (r.titleNorm.includes(qText)) ok = true;
      }

      // If user typed a canonical CIP but it wasn't found exact,
      // still allow prefix match by first 4 digits like "14.0900" -> "14.09"
      if (!ok && qCipCanon) {
        const prefix4 = qCipCanon.slice(0, 5); // "14.09"
        if (r.cipNorm.startsWith(prefix4)) ok = true;
      }

      if (ok) results.push(r);

      if (results.length >= limit) break;
    }

    // Stable sort by CIP
    results.sort((a, b) => (a.cipNorm < b.cipNorm ? -1 : a.cipNorm > b.cipNorm ? 1 : 0));

    return results;
  }

  return { search };
}
