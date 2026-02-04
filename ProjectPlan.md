# Project Plan — CIP STEM Overlay (Open Source)

## 1. Goal

Build an open-source, static web tool that overlays **DHS STEM eligibility** onto **NCES CIP definitions**, enabling:

- Search by CIP code / title / keywords
- STEM “eligible” flag + STEM-only filtering
- Versioned DHS list support (change tracking)
- Transparent validation, provenance, and auditability
- Hosting on GitHub + GitHub Pages
- Automated update pipeline (scheduled checks + PRs)

Non-goals (V1):
- Giving legal advice
- Replacing NCES’s official taxonomy tool
- Claiming STEM eligibility beyond the official DHS list

---

## 2. Target Users

Primary:
- Students researching STEM-eligible programs
- DSOs / advisors verifying CIP eligibility quickly
- Program designers evaluating CIP choices

Secondary:
- Researchers and analysts working with CIP/STEM datasets

---

## 3. Core Data Sources

### 3.1 NCES CIP Definitions (Authoritative for CIP descriptions)
- Used for:
  - CIP code hierarchy (2-digit / 4-digit / 6-digit)
  - Titles and descriptions
  - “Year/version” (e.g., CIP 2020)
- Implementation note:
  - We will store definitions locally for fast search and stable UX.

### 3.2 DHS STEM Designated Degree Program List (Authoritative for STEM OPT eligibility)
- Used for:
  - STEM eligibility flag (Yes/No)
  - Version tracking (list changes over time)
- Implementation note:
  - DHS publishes as PDF; our pipeline will parse and normalize into JSON.

---

## 4. Architecture Overview

### 4.1 Repository Components
1. **Data Pipeline (scripts/)**
   - Fetch sources (NCES + DHS)
   - Parse and normalize
   - Build merged “overlay” dataset
   - Generate diff reports between DHS versions
   - Validate data (format + completeness + sanity checks)

2. **Data Artifacts (data/)**
   - `cip_nces.json` (CIP code → title/description/hierarchy)
   - `stem_dhs_<version>.json` (CIP code → STEM eligible = true)
   - `overlay_latest.json` (merged view used by UI)
   - `diffs/<versionA>_to_<versionB>.json` (added/removed)

3. **Static Frontend (app/)**
   - Search + filters + details page
   - Client-side index for fast search
   - Hosted on GitHub Pages

4. **Automation (.github/workflows/)**
   - Scheduled update check
   - Rebuild dataset on changes
   - Run validations
   - Open PR with new data + diff report
   - Deploy Pages on merge to main

---

## 5. Data Model (V1)

### 5.1 CIP Definition Record (NCES)
Minimum fields for V1:
- `cip` (string, format: `NN.NNNN`)
- `cipYear` (e.g., 2020)
- `title`
- `description`
- `series2` (2-digit major group)
- `series4` (4-digit intermediate group)

### 5.2 DHS STEM Record
- `cip`
- `eligible` (true)
- `dhsListVersion` (e.g., `2024`)
- `sourcePdfUrl`
- `sourcePdfSha256` (for provenance)

### 5.3 Overlay Record (used by UI)
- `cip`, `title`, `description`, `cipYear`, `series2`, `series4`
- `stemEligible` (boolean)
- `stemSource` metadata:
  - list version
  - URL
  - hash
  - build timestamp

---

## 6. Update & Versioning Strategy

### 6.1 Update Frequency
- Scheduled check: weekly (GitHub Actions)
- Triggered rebuild:
  - if DHS PDF hash changes OR
  - if NCES dataset version changes (manual update in early versions)

### 6.2 Versioning Rules
- Each DHS list ingestion becomes a new artifact:
  - `stem_dhs_<YYYY>.json` (or `<YYYY-MM-DD>` if multiple releases per year)
- We track “latest”:
  - `overlay_latest.json`
- We generate diffs:
  - `diffs/<old>_to_<new>.json`
- Each dataset build produces a `build_manifest.json` containing:
  - timestamp
  - source URLs
  - source hashes
  - record counts
  - validation results

---

## 7. Validation & Verification

### 7.1 Automated Validation (required for every build)
Rules:
- CIP format must match: `^\d{2}\.\d{4}$`
- No duplicates in NCES CIP list
- No duplicates in DHS STEM list
- All DHS STEM CIP codes must exist in NCES CIP definitions:
  - If not, fail build OR flag as `missingDefinition` (decision: fail in V1)
- Record count sanity checks:
  - STEM list count must be > 0
  - Large unexpected swings should fail build unless explicitly approved
- Overlay completeness:
  - every NCES CIP must have stemEligible boolean (default false)
- Diff integrity:
  - added/removed counts consistent with set operations

### 7.2 Human Verification (release checklist)
- Confirm DHS source URL still points to official PDF
- Confirm hash recorded in manifest
- Review generated diff report before merging PR

---

## 8. Milestones & Deliverables

### Milestone 0 — Repo Setup (Day 0)
Deliverables:
- Repo structure created
- README placeholder
- ProjectPlan.md committed
- License selected (MIT recommended)
- Basic GitHub Pages config scaffold

Acceptance:
- Repo builds with a placeholder site

---

### Milestone 1 — Data Pipeline V1 (NCES + DHS → JSON) (Week 1)
Deliverables:
- `scripts/fetch_dhs.py` downloads latest DHS STEM list PDF
- `scripts/parse_dhs.py` extracts CIP codes + titles
- `scripts/fetch_nces.py` obtains CIP definitions (CIP 2020)
- `scripts/build_overlay.py` merges NCES + DHS → `overlay_latest.json`
- `scripts/validate.py` runs all checks
- `data/processed/*` outputs produced

Acceptance:
- Overlay file generated locally
- Validation passes cleanly
- Manifest generated with hashes and counts

---

### Milestone 2 — Static UI V1 (Week 2)
Deliverables:
- Basic UI:
  - Search box (CIP code/title)
  - STEM-only toggle
  - Filters by 2-digit series
  - CIP detail view with:
    - definition
    - STEM status
    - source metadata (version + hash)
    - link to NCES entry
- Client-side search index
- UI consumes `overlay_latest.json`

Acceptance:
- Deployed on GitHub Pages
- Search works and STEM filter works
- Details page shows provenance metadata

---

### Milestone 3 — Automation + PR Updates (Week 3)
Deliverables:
- GitHub Actions scheduled workflow:
  - download DHS PDF
  - compute hash
  - if changed: rebuild datasets + diff + manifest
  - run validation
  - create PR with changes
- Deploy workflow:
  - deploy Pages on merge

Acceptance:
- A simulated change triggers a PR with updated data artifacts
- Build fails if validation fails

---

### Milestone 4 — Version History + Diffs (Week 4)
Deliverables:
- Store multiple DHS versions
- Generate diffs automatically
- UI filter:
  - “Added in latest update”
- “Changelog” page listing:
  - version → added/removed counts

Acceptance:
- Diff report produced and shown in UI
- Users can see what changed between versions

---

## 9. Tech Stack Recommendation

### Data scripts
- Python 3.11+
- Libraries (final list after implementation choice):
  - `requests`
  - `pdfplumber` (or camelot/tabula fallback)
  - `pydantic` (optional for schema validation)

### Frontend
- Vite + React (or Astro; decision later)
- Search index:
  - MiniSearch or FlexSearch

### Hosting
- GitHub Pages (static deploy)
- GitHub Actions (scheduled updates + deploy)

---

## 10. Governance & Open Source

### License
- MIT (simple and permissive)

### Contribution policy
- Add `CONTRIBUTING.md`
- Add Issue templates:
  - Data parsing issue
  - DHS update detected
  - UI feature request
  - CIP definition mismatch

### Disclaimer (required)
- “Not legal advice”
- “Authoritative source is DHS STEM list + what appears on I-20”

---
