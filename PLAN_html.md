# OneSearch HTML Dashboard — How It Works

> This document explains the full journey from raw data to finished HTML dashboard: what each step does, who runs it and from where, how long it takes, and what it costs.

---

## Overview: two separate processes

The dashboard is the output of two distinct processes that run independently:

```
[Step 1 — Data pipeline]          [Step 2 — HTML build]
run_onesearch.py                   build_html_oikos.py
      │                                     │
      ├─ Reads: GSC, SQR, SE Ranking,       ├─ Reads: Masterlist (Google Sheets)
      │         Keyword Study, GA4           │          QS sheet (Google Sheets)
      │                                     │          Reference HTML template
      └─ Writes: Google Sheets Masterlist    └─ Writes: oikos_usa_onesearch_dashboard.html
                 (57-column, ~3,663 rows)                (~1,100 KB)
```

Step 1 runs once per reporting period when new source data is available. Step 2 runs any time you want to refresh the HTML output from the current state of the Masterlist.

---

## Step 1 — Populate the Masterlist (`run_onesearch.py`)

### What it does

Reads four data sources, fuzzy-matches them onto a unified keyword spine, and writes a 57-column enriched Masterlist to Google Sheets.

```
GSC Export           ─┐
SQR Report (Ads)     ─┤  normalize → merge → trigram index → match → write
SE Ranking           ─┤
Keyword Study        ─┤
GA4 Conversions      ─┘
```

See `one_search_skill/workflow.md` for the full architecture.

### Where to run it

**Terminal only** — this is a pure Python script with no Claude involvement.

```bash
cd /Users/carlaklaasen/claude_code/one_search
python3 run_onesearch.py

# Smaller test batch (faster):
python3 run_onesearch.py --max-rows 500
```

Claude Code (the CLI) can also call it via the Bash tool if you ask Claude to run the pipeline for you, but the script itself is plain Python.

### What you need before running

All source data for the current client must already be in the source config Google Sheet. For Oikos USA, the reference sheet is `1o526Qv4UzP_Qfe-cjrfvcA7jRUi6zUtd9Ecp2WPMIhQ`, tab `One Search`. Each row maps a source label (e.g. `GSC Export`) to the Google Sheet ID and tab that holds that data. The script reads this config first, then pulls every source from Sheets.

### Credentials

All credentials live in `/Users/carlaklaasen/claude_code/.env`:

| Key | Used for |
|-----|----------|
| `GOOGLE_CLIENT_ID` | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Google OAuth |
| `GOOGLE_REFRESH_TOKEN` | Google OAuth — exchanges for short-lived access token |
| `SE_RANKING_API_KEY` | SE Ranking API (volume enrichment at end of pipeline) |
| `Gemini_API_Key` | Taxonomy enrichment (separate script — see below) |

---

## Step 2 — Build the HTML (`build_html_oikos.py`)

### What it does

Reads the Masterlist and QS sheet from Google Sheets, injects all data into a reference HTML template, applies brand-specific patches, and outputs a self-contained single-file HTML dashboard.

The pipeline inside `build_html_oikos.py`:

```
1. Auth (Google OAuth)
2. Load brand-detection regex from reference sheet (col H, Oikos row)
3. Read Masterlist tab → build DATA array (37 fields × ~3,663 rows)
4. Build TAGS dict (taxonomy tags per keyword)
5. Compute territory stats (per-TOPICS aggregates for Deep Dive + Reco panels)
6. Read QS Google Sheet → build QS_CLASSIFIED array (161 rows)
7. Build SQR_ACTIVIA array from Masterlist (keywords with SEM clicks → 2,809 rows)
8. Load HTML reference template (activia_ca_onesearch_dashboard.html)
9. replace_block() → inject DATA, TAGS, QS_CLASSIFIED, SQR_ACTIVIA
10. apply_brand()   → replace Activia colors / brand names with Oikos equivalents
11. apply_english() → replace French UI labels with English
12. replace_territory_panel() → inject full Territory Deep Dive HTML
13. replace_recos_panel()     → inject data-driven Recommendations panel
14. patch_onesearch_js()      → fix brand filter, topic order, buildDonut, coverage targets
15. clean_embedded_docs()     → strip concatenated-template structural wrappers
16. truncate_after_last_script() → remove raw data artifact past last </script>
17. inject_brand_config()     → inject <script> block with OS_BRAND_REGEX, OS_TOPIC_ORDER etc.
18. inject_export_ui()        → inject Export/Import JSON commentary toolbar
19. Write output HTML
```

### Where to run it

**Terminal** — same as Step 1:

```bash
cd /Users/carlaklaasen/claude_code/one_search
python3 build_html_oikos.py
```

**Claude Code CLI** — you can also ask Claude to run it, which calls the script via the Bash tool.

### Per-client config block

At the top of `build_html_oikos.py`, a config section controls everything brand-specific. To use this for a different brand, duplicate the file (e.g. `build_html_silk.py`) and change:

```python
MASTER_ID   = '...'          # Masterlist Sheet ID for the new brand
MASTER_TAB  = 'Listing'      # tab name (usually 'Listing')
BRAND_NAME  = 'Silk USA'     # display name used throughout
PERIOD      = 'Q1 2026 vs Q4 2025'
PERIOD_P1   = 'Q1 2026'
PERIOD_P4   = 'Q4 2025'
BRAND_COLOR = '#...'         # primary brand hex
ACCENT_CLR  = '#...'         # secondary/lighter hex
LIGHT_BG    = '#...'         # very light background hex
QS_SHEET_ID = '...'          # Quality Score Google Sheet ID for this brand
OUTPUT_FILE = '...silk_usa_onesearch_dashboard.html'

TOPIC_ORDER      = []        # empty = auto-sort by volume; or list specific topics
COV_TARGET_BRAND   = 10      # coverage target % for branded territories
COV_TARGET_GENERIC = 3       # coverage target % for non-branded territories
BRAND_REGEX_NAME   = 'Silk'  # row to look up in the reference sheet for brand regex
```

The **brand-detection regex** (used to classify keywords as Brand vs Non-Brand in the dashboard filter) is loaded automatically from the reference sheet col H at build time. The `BRAND_REGEX_NAME` config controls which row to read.

---

## The `/onesearch-danone` Skill

### What it is

`/onesearch-danone` is a Claude Code skill (defined in `onesearch_danone_ca_english.md`). It is an AI-assisted workflow that can orchestrate the full process:

- Identifies the correct Masterlist and QS sheet IDs for the requested brand
- Calls `build_html_oikos.py` (or a brand-specific equivalent) via the terminal
- Handles validation, troubleshooting, and post-build checks

### Where to invoke it

**Claude Code CLI only** — skills run inside Claude Code sessions. You cannot invoke them directly from a terminal.

```
# In a Claude Code session (terminal or VS Code extension):
/onesearch-danone oikos
/onesearch-danone silk --period-current "Q2 2026"
```

The skill reads the brand registry from the reference sheet, sets the config, and calls the Python build script. For data pipeline runs (Step 1), it can call `run_onesearch.py` as well.

### Skill vs. direct script

| | Skill `/onesearch-danone` | Direct `python3 build_html_oikos.py` |
|--|--|--|
| Who uses it | Analyst wanting guided workflow | Developer who knows the config |
| Validation | Claude validates output, flags issues | No validation — inspect manually |
| Flexibility | Can adapt to missing data, ask questions | Fixed pipeline |
| Speed | Slower (LLM round-trips) | Faster (no LLM) |
| Token cost | Yes (see below) | Zero |

---

## Full end-to-end workflow — from raw data to HTML

```
┌─────────────────────────────────────────────────────────┐
│  ONE-TIME SETUP (per client, per period)                │
│                                                         │
│  1. Export data from source platforms                   │
│     ├─ GSC: Queries tab, comparison mode, download CSV  │
│     ├─ Google Ads: SQR report, comparison mode          │
│     ├─ SE Ranking: latest keyword export                │
│     └─ GA4: mikmak_checkout + mikmak_offline_store      │
│                                                         │
│  2. Upload CSVs to their respective Google Sheets       │
│     (reference sheet maps label → Sheet ID + tab)       │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 1 — Populate the Masterlist  (~5–8 min)           │
│                                                         │
│  python3 run_onesearch.py                               │
│                                                         │
│  ├─ Reads all 6 sources via Sheets API                  │
│  ├─ Normalizes + merges GSC × SQR                       │
│  ├─ Trigram-matches SE Ranking and Keyword Study        │
│  ├─ Pro-rata joins GA4 conversions                      │
│  ├─ Writes ~3,663 rows × 57 cols to Masterlist          │
│  └─ Calls SE Ranking API to fill blank volumes (col G)  │
│                                                         │
│  Human checkpoint:                                      │
│  Open KW Review tab → mark approved = YES for           │
│  borderline KS matches → re-run to write them           │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  OPTIONAL — Taxonomy enrichment  (~10–20 min)           │
│                                                         │
│  python3 run_taxonomy_enrichment.py --brand oikos-usa   │
│                                                         │
│  Reads keywords with empty TOPICS/CATEGORY/SUB-CATEGORY │
│  from the Masterlist, classifies them via Gemini 2.0    │
│  Flash Lite, writes results back to the sheet.          │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  STEP 2 — Build the HTML dashboard  (~30–60 sec)        │
│                                                         │
│  python3 build_html_oikos.py                            │
│                                                         │
│  ├─ Reads Masterlist (3,663 rows) + QS sheet (161 rows) │
│  ├─ Injects DATA, TAGS, QS, SQR into HTML template      │
│  ├─ Applies brand colors + English labels               │
│  ├─ Generates Territory Deep Dive + Recommendations     │
│  ├─ Patches JS (brand filter, topic order, coverage)    │
│  └─ Writes oikos_usa_onesearch_dashboard.html (~1.1 MB) │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  REVIEW — Open in Chrome                                │
│                                                         │
│  open one_search_html/oikos_usa_onesearch_dashboard.html│
│                                                         │
│  ├─ Territory Deep Dive: add analyst commentary in      │
│  │   the editable text boxes                            │
│  ├─ Recommendations: validate priorities                │
│  └─ Export: click "Export JSON" to save commentary,     │
│     "Import JSON" to restore it after a rebuild         │
└─────────────────────────────────────────────────────────┘
```

---

## Token cost, time, and runtime complexity

### Step 1 — `run_onesearch.py`

**Wall-clock time:** 5–8 minutes for Oikos USA (3,663 unified rows, 14,273 KS keywords)

| Phase | Complexity | Time estimate |
|-------|------------|---------------|
| Sheets API reads (6 sources) | O(rows per source) | ~30–60 s |
| Normalize all sources | O(R + K + SE + G) | ~5 s |
| Merge GSC × SQR | O(Q log Q) | < 1 s |
| Build trigram index on unified spine (Q ≈ 3,663) | O(Q × t), t ≈ 10 | < 1 s |
| SE Ranking match (SE ≈ 1,240 rows) | O(SE × top50 candidates) | ~5 s |
| KS match (K = 14,273 keywords × top50) | O(K × top50 × t) | ~60–90 s |
| Sheets API write (batch, 500-row chunks) | O(Q / 500) API calls | ~20–30 s |
| SE Ranking API enrichment (missing vol, ~500 calls) | O(missing_rows / 500) | ~60–120 s |

**Token cost:** Zero. No LLM is called by `run_onesearch.py`. All computation is Python.

**API costs:** SE Ranking API charges per keyword lookup. At 500 blank-volume keywords per run, this is ~1 API credit per keyword (SE Ranking pricing). Sheets API calls are free within Google's quota.

---

### Optional — `run_taxonomy_enrichment.py`

**Wall-clock time:** 10–30 minutes depending on how many keywords are unclassified.

**Token cost:** Uses Gemini 2.0 Flash Lite (free tier). If the free tier is exhausted, Gemini charges per 1,000 tokens. A typical enrichment batch of 500 keywords at ~30 tokens/keyword = ~15,000 input tokens. At Gemini free-tier rates: **$0**.

---

### Step 2 — `build_html_oikos.py`

**Wall-clock time:** 30–60 seconds

| Phase | Complexity | Time estimate |
|-------|------------|---------------|
| Sheets API reads (Masterlist + QS) | O(rows) | ~10–20 s |
| Build DATA + TAGS arrays | O(Q) | < 1 s |
| Compute territory stats | O(Q) | < 1 s |
| String substitutions on 8 MB template | O(template_size) | ~1–3 s |
| Write output HTML (~1.1 MB) | O(1) | < 1 s |

**Token cost:** Zero. No LLM is called by `build_html_oikos.py`. Pure Python + Sheets API.

---

### `/onesearch-danone` skill (Claude-assisted)

When you invoke the skill in Claude Code, Claude itself is doing the orchestration:

| What Claude does | Token estimate |
|------------------|----------------|
| Read skill instructions + context | ~2,000–4,000 tokens |
| Read CLAUDE.md, memory files | ~2,000 tokens |
| Plan and validate (reasoning) | ~1,000–3,000 tokens |
| Call Bash tool to run script | minimal |
| Read script output, check for errors | ~500–2,000 tokens |
| Report results to you | ~500 tokens |

**Total per skill run:** roughly **5,000–12,000 tokens** depending on complexity and how many files Claude reads during troubleshooting.

At Claude Sonnet 4.6 pricing (~$3/MTok input, $15/MTok output), a single skill invocation costs approximately **$0.02–0.05**. If troubleshooting requires reading large HTML or Python files, this can rise.

The Python scripts themselves cost nothing in tokens — only the LLM session around them does.

---

## Running for a different brand

### Quickest path

1. Duplicate `build_html_oikos.py` → e.g. `build_html_silk.py`
2. Update the 12-line config block at the top (Sheet IDs, brand colors, brand name, BRAND_REGEX_NAME)
3. Run `python3 build_html_silk.py`

The brand-detection regex is loaded automatically from the reference sheet (col H, brand row matching `BRAND_REGEX_NAME`). You don't need to write a regex manually.

### What you must configure per brand

| Config key | What to change |
|------------|----------------|
| `MASTER_ID` | Masterlist Sheet ID |
| `MASTER_TAB` | Tab name (usually `Listing`) |
| `QS_SHEET_ID` | Quality Score sheet ID |
| `BRAND_NAME` | Display name (e.g. `"Silk USA"`) |
| `BRAND_COLOR` | Primary hex (e.g. `"#5b9a3c"`) |
| `ACCENT_CLR` | Secondary hex |
| `LIGHT_BG` | Very light background hex |
| `PERIOD_P1` | Current period label (e.g. `"Q2 2026"`) |
| `PERIOD_P4` | Comparison period label (e.g. `"Q1 2026"`) |
| `PERIOD` | Combined label (e.g. `"Q2 2026 vs Q1 2026"`) |
| `BRAND_REGEX_NAME` | Brand row label in the reference sheet (e.g. `"Silk"`) |
| `TOPIC_ORDER` | `[]` for auto-sort, or `['TOPIC_A', 'TOPIC_B', ...]` for fixed order |
| `COV_TARGET_BRAND` | Coverage target for brand territory (default `10`) |
| `COV_TARGET_GENERIC` | Coverage target for non-brand (default `3`) |
| `OUTPUT_FILE` | Output HTML path |

### If the brand has no regex in the reference sheet

Set `BRAND_REGEX_DEFAULT` to a simple pattern:
```python
BRAND_REGEX_DEFAULT = r'silk|silk almond|silk oat'
```
The build script uses this as fallback if the sheet lookup returns nothing.

---

## The reference HTML template

**Path:** `reference/activia_ca_onesearch_dashboard.html`

This is the source of the JS dashboard logic — all 6 tabs, all charts, all filter dropdowns. It was originally built for Activia Canada. The build script:

1. Injects Oikos data (replacing the Activia data arrays)
2. Patches brand colors, labels, and UI text
3. Replaces the Territory Deep Dive and Recommendations panels entirely
4. Fixes brand-specific JS (filter logic, topic order, coverage targets)
5. Strips the triple-doc artifact (the template was assembled from 3 HTML files)

**Do not edit the reference template directly** unless you intend to change the dashboard structure for all future brands. Changes to the template only affect new builds; they do not retroactively change already-generated HTML files.

---

## JSON commentary export/import

The dashboard includes an Export JSON / Import JSON toolbar (top-right corner). Every `<div contenteditable>` with a `data-field-id` attribute is saved in the export:

- **Export**: click "↓ Export JSON" → downloads `oikos_usa_commentary_YYYY-MM-DD.json`
- **Import**: click "↑ Import JSON" → re-populates all commentary fields from the JSON

This allows analyst notes to survive a rebuild. Workflow:
1. Build HTML → add commentary → export JSON
2. Rebuild HTML (after masterlist update) → import JSON → commentary restored

The JSON file is a flat key-value map of `{field-id: text}` plus a `_meta` header with brand and export date.

---

## Known Issue: Search Demand = 0 in SQR Detail by Keyword

### What the column shows and where it comes from

The **Search Demand** column in the SQR – Detail by Keyword table (`renderSQR()` in the template JS) reads from:

- `r[5]` = `Volume Q1 2026` (masterlist column H) — 3-month total, populated only when the Keyword Study match succeeds (≥ 0.65 Jaccard similarity)
- Fallback: `r[4] * 3` = `Average Search Volume × 3`, used when `r[5]` is blank

`Average Search Volume` (col G) itself has two sources:
1. KS match → computed as `(Vol Q1 + Vol Q4) / 6`
2. SE Ranking API enrichment (`enrich_volumes` in `enrich.py`) → fills G for rows where KS failed but the keyword has OS clicks

**The problem:** rows enriched only via the SE Ranking API (no KS match) have `Average Search Volume` populated but `Volume Q1` and `Volume Q4` both blank. Without the fallback these rows render as 0 in the Demand column even though they have SEO or SEM clicks — an obviously incorrect picture.

A temporary display fix (multiply `r[4] × 3` as a proxy) was applied in `patch_onesearch_js()` in `build_html_oikos.py`. This surfaces an approximate value rather than zero, but the root issue is upstream in the data pipeline.

---

### Solution options

**Option 1 — Fix the pipeline so Volume Q1/Q4 are always populated (recommended)**

When `enrich_volumes()` in `enrich.py` fetches a monthly average from the SE Ranking API and writes it to `Average Search Volume` (col G), it should also write `avg × 3` to `Volume Q1` (col H) and `Volume Q4` (col I).

- **Pros:** Single fix at the data layer. The masterlist is consistent — every row with Average Search Volume also has the quarterly breakdown. All downstream consumers (HTML, future exports, formulas) benefit automatically. No display approximation needed.
- **Cons:** The `avg × 3` values for H and I are estimated (same number for both periods, no true seasonality split). They should be treated as a fill-in, not real KS data. This is already the case for the `r[4] × 3` display fix — the master fix just moves it to the right place.
- **Status:** `enrich.py` updated to do this (2026-05-11). Takes effect on the next `run_onesearch.py` run.

**Option 2 — Filter zero-demand rows out of the HTML build**

In `build_sqr_data()` or `renderSQR()`, skip rows where `Average Search Volume = 0` and `Volume Q1 = 0`.

- **Pros:** Removes visually broken rows from the dashboard immediately, no pipeline re-run needed.
- **Cons:** Misleading. A keyword with 0 measured search volume and real SEM clicks is a legitimate finding (SEM-only coverage, niche query, brand keyword). Hiding it obscures actionable data. The zero is a *data gap*, not a signal that the keyword has no demand. Analysts would lose visibility on ~500+ rows.
- **Not recommended** as the primary fix.

**Option 3 — Run a secondary SE Ranking API call during the HTML build**

In `build_html_oikos.py`, after reading the Masterlist, identify rows with blank Volume Q1 and non-zero clicks, call the SE Ranking API in real time to fetch volumes, and use those values when constructing the DATA array.

- **Pros:** The HTML always has complete volume data regardless of the pipeline state.
- **Cons:** Adds a live external API call to the HTML build step (currently zero API calls, just a Sheets read). Increases build time significantly for large datasets. Introduces a new failure point (API timeout, rate limit, credit cost) into a step that is otherwise pure and fast. Creates divergence between the masterlist and the HTML data — the same keyword could show different demand in the sheet vs. the dashboard.
- **Not recommended.** Volume enrichment belongs in the pipeline (Option 1), not the HTML build.

**Recommended approach:** Option 1 only. Fix the data at the source so the masterlist is always consistent. The `r[4] × 3` display fallback in `patch_onesearch_js()` can remain as a safety net for edge cases, but it should rarely fire once the pipeline fix propagates.
