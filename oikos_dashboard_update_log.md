# Oikos USA OneSearch Dashboard — Update Session Log
**Session date:** 2026-06-17
**Dashboard file:** `one_search/dashboards/oikos_usa_onesearch_dashboard.html`
**Goal:** Update dashboard with SEM QV data, brand SEM recommendations, restructured layout, integrated Top 15, glossary update, and SEO production plan integration.

---

## Source documents used this session

| Document | File ID / Path | Purpose |
|----------|---------------|---------|
| Feedback (meeting notes Thomas × Carla Jun 16) | `1T0i04hB72Ymf4FUHqubFGp_DKTYR91NY5BNZ5HLZ6ZY` | Decisions + methodology |
| Google Ads GA4 export Q1 2026 | `1Z6QO82Gc3itROgnvqhBP2aoGTf4pIO0WLD-Kkbofb1w` | SEM QV source data (tab: Campagnes_Google Ads_Requête_Google Ads_associée_à_cette_session) |
| SEO Production Plan 2026 | `13ZKd5UVG_OcvRS9Wri8c8XSbwqiCguiJBDvUuUN9hbg` | On-site + off-site Q2–Q4 actions (tabs: ON SITE (OIKOS) - Content Strategy, OFF SITE (OIKOS) - Content Strategy) |
| SEM examples folder | `1Bv54w5IWiPOyOnREPeaZetbCXjh0R7_6` | 4 brand SEM pause/keep recommendation sheets (Oikos Canada, Activia, Silk, ID) |
| Oikos USA masterlist | TBD — searching Drive | Source of truth for all keyword data |
| Dashboard HTML | `one_search/dashboards/oikos_usa_onesearch_dashboard.html` | Output file |

---

## Key decisions from feedback session (Jun 16 2026)

1. **Zero-demand keywords**: Delete from dataset (distorts coverage). Run SE Ranking API on blank rows first, then remove if still zero.
2. **SEM QV methodology**: Replicate SEO lead-attribution method using GA4 Google Ads session export. Keyword QV SEM = (keyword sessions / LP total sessions) × LP total Key Events. Sum across LPs if keyword hits multiple pages.
3. **SEM export requirement**: Thomas requesting client to re-export SQR with landing page column (for future QS analysis). Not blocking current work.
4. **Dashboard layout**: Remove right commentary column. Reintegrate commentary as inline copy.
5. **Expert section**: Move detailed keyword table to collapsible accordion. Not client-facing.
6. **Brand SEM strategy**: Target 80% impression share. Two levers: (a) add negatives for SEO-covered zero-QV-SEM keywords, (b) increase bids on high-QV keywords.
7. **Top 15**: Must combine SEO + SEM actions. Health territory deprioritized. PRODUCT is Q2 priority.

---

## SEM QV Calculation methodology

**Source:** GA4 Google Ads export columns:
- `Requête Google Ads associée à cette session` = search query (keyword)
- `Page de destination + chaîne de requête` = landing page
- `Sessions` = paid sessions per keyword+LP combination
- `Événements clés` = Key Events = mcmack checkout = Qualified Visits

**Formula:**
1. Group by LP → sum Sessions + sum Key Events per LP
2. LP QV rate = LP Key Events / LP Sessions
3. For each keyword row: Attributed QV SEM = (row Sessions / LP total Sessions) × LP total Key Events
4. Group by keyword → sum attributed QV across all LPs (confirmed: sum approach)

**Verification:** Total QV SEM summed across all keywords ≈ total Key Events in GA4 export.

---

## Brand SEM recommendation criteria (from Thomas's Canada sheets)

**Negative keyword candidates (Exclude from SEM):**
- Territory = BRAND
- SEO Coverage > 10%
- SEO Position ≤ 5
- QV SEM = 0

**Keep in SEM — Active conversions:**
- QV SEM > 0
- SEO Coverage < 10%

**Keep in SEM — Test before pausing:**
- SEO Coverage > 10%
- QV SEM > 0
- Monitor GSC organic clicks for 4 weeks before confirming pause

---

## Phase progress tracker

| Phase | Description | Status | Notes |
|-------|-------------|--------|-------|
| Pre-flight | Find masterlist file ID | ✅ Done | ID: 1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU |
| Pre-flight | Check .env | ✅ Done | Keys confirmed. SHEET_ID in .env = SEO plan, not masterlist |
| Phase 1 | Read SEO production plan | ✅ Done | 104 Oikos rows extracted. Q2: protein shakes, yogurt, remix pages. Q3-Q4: recipes (banana bread, pancakes, brownies, cheesecake, bars). Off-site: 6 guest posts May-July 2026. |
| Phase 2A | Calculate SEM QV | ✅ Done | Script: `one_search/scripts/sem_qv_attribution.py`. GA4 tab has non-breaking spaces (\xa0) — handled via `get_first_sheet_title()`. |
| Phase 2B | Write QV SEM to masterlist | ✅ Done | Col AC: 1,863 keywords populated. Col BF: added as new column (sheet expanded from 57 to 58 cols). |
| Phase 2C | Verify totals | ✅ Done | Total QV SEM: 1,338. Attribution delta: 0.0. 70 QVs unassigned (keywords not in masterlist — flagged for spine expansion). |
| Phase 3 | Tag SEM recommendations in masterlist | ✅ Done | 17 Exclude, 61 Keep-Active, 8 Keep-Test. All in col BF. BRAND territory only (by design). |
| Phase 4A | HTML: SEM QV methodology in Glossary | ✅ Done | New section "SEM Qualified Visit (QV) Methodology" with 4-step formula grid + Q1 2026 result callout. |
| Phase 4B | HTML: QV SEM glossary table rows | ✅ Done | Added QV SEO and QV SEM rows to Metrics Glossary table. |
| Phase 4C | HTML: Cosmetic fixes | ✅ Done | "Canadian Market" → "US Market" (chip + glossary table). "Oikos USA US" → "Oikos USA" (exec summary heading). |
| Phase 5 | HTML: Clear placeholder commentary from editable boxes | ✅ Done | 6 boxes cleared. Toolbar kept. Boxes left blank for new notes. |
| Phase 6 | HTML: Expert accordion + Brand SEM dropdown | ✅ Done | Brand SEM Campaign Optimization accordion with 3-panel summary, criteria table, impression share callout. Expert view (analyst-only, collapsed) inside the accordion. |
| Phase 7 | HTML: Top 15 rewrite (SEO+SEM) | ✅ Done | 15 integrated SEO+SEM actions with channel badges (SEO/SEM/BOTH), territory tags, timeline/priority tags, detail text. Replaces the old Top 9 bullet list. |
| Post-session | Update README | ⏳ Pending | |
| Post-session | Save memory — skill/script/masterlist updates needed | ⏳ Pending | |
| Post-session | Launch critical review agent | ⏳ Pending | |

## Script produced this session

- **`one_search/scripts/sem_qv_attribution.py`** — Full SEM QV attribution + masterlist write
  - Reads GA4 Ads export (handles \xa0 non-breaking spaces in tab name)
  - Calculates LP-rate attribution per Thomas's methodology
  - Writes col AC (QV SEM) + col BF (SEM Recommendation)
  - Expands sheet if column count insufficient
  - Prints verification summary

## Masterlist changes (2026-06-17)

- Column AC (`Conversions SEM Q1 2026`): populated with Thomas-methodology QV SEM values for 1,863 keywords
- Column BF (`SEM Recommendation`): new column added — Exclude/Keep-Active/Keep-Test for BRAND territory keywords
- Sheet expanded from 57 to 58 columns

## Dashboard changes (2026-06-17)

- `oikos_usa_onesearch_dashboard.html` — 15,186 lines (was 14,852)
- Glossary tab: new SEM QV Methodology section, 2 new glossary table rows, US Market fix
- Recommendations tab: Top 15 integrated actions, Brand SEM Campaign Optimization accordion, Expert accordion

---

## Post-session: automation updates required

After Oikos dashboard is shipped, the following must be updated:

### 1. Global OneSearch skill (SKILL.md / workflow.md)
- Add `Google_Ads_Data` as a **required export** for all future OneSearch dashboards
- Tab name pattern: `Campagnes_Google Ads_Requête_Google Ads_associée_à_cette_session`
- Required columns: search query, landing page, sessions, key events
- Period: must match the primary reporting period (e.g. Q1 = Jan–Mar)
- Masterlist registry entry pattern: `BRAND | Google_Ads_Data_[PERIOD] | [FILE_ID] | [TAB_NAME]`

### 2. Python HTML generation scripts
- Add processing step: GA4 data → SEM QV calculation → masterlist QV SEM column
- The LP-attribution logic (step 2A formula above) should be a reusable function
- HTML generation should read QV SEM from masterlist and populate:
  - SEM QV column in recommendations table
  - SEM QV KPI cards in OneSearch Dashboard tab
  - Brand SEM dropdown data (negative KW list + keep list)

### 3. Masterlist template
- Add standard column: `QV SEM (Q1 YYYY)` after existing `QV SEO (Q1 YYYY)`
- Add standard column: `SEM Recommendation` (values: Exclude / Keep-Active / Keep-Test / blank)

### 4. README updates (one_search/README.md and sub-READMEs)
- Document new Google Ads data source requirement
- Document SEM QV methodology
- Update export_requirements docs to include Google Ads GA4 session export
- Update the brand registry / masterlist schema diagram

---

## Blocking items (external — not completable this session)

- New SQR from client with landing page column (Thomas requesting via Alex)
- 4 GA4 files Thomas generating from Canada project (for SEM QV method validation)
- Brand impression share current IS metric (not yet in available data)

---

*Log last updated: 2026-06-17 — Pre-flight in progress*
