# OneSearch Pipeline — Project Setup

This project builds a **OneSearch Masterlist** for a client in Google Sheets.
It combines SEO (Google Search Console) and SEM (Google Ads) data across two periods,
then enriches each keyword with Keyword Study taxonomy and SE Ranking data.

**The pipeline is a pure Python package.** All computation runs locally in `one_search/`.
Google Sheets is used only for reads and writes via the Sheets API.

---

## How to start a session

At the start of any session, ask the user:

> "Which project are we working on, and do you have new source files to load or are we continuing from the last run?"

Then check which inputs below are already present vs. still needed. Only ask for what's missing.

---

## Current project — Oikos USA

| Setting | Value |
|---|---|
| Client | Oikos USA |
| Period 1 | Q1 2026 (Jan 1 – Mar 31, 2026) |
| Period 2 | Q4 2025 (Oct 1 – Dec 31, 2025) |
| Masterlist Sheet ID | `1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU` |
| Masterlist tab | `Listing` |
| KW Review tab | `KW Review` |
| Keyword Study Sheet ID | `1rTdi4cLDiFUdQHH8hj4V1GIQb8iKToKXRgFHlQcVHEI` |
| Keyword Study tab | `Keyword study US` |
| Reference Sheet ID | `16-h0rmI-5fx0RVXfxbVOIjcrGugkvY3vH31JWgRLqLg` *(updated 2026-08-20 — dedicated registry sheet, one tab per brand)* |

**Local source files (already downloaded):**

| Source | File |
|---|---|
| GSC queries export | `gsc_export_queries_oikos.csv` |
| GSC pages export | `gsc_export_pages_oikos.csv` |
| Google Ads SQR report | `account_level_sqr_report_oikos.csv` |
| SE Ranking export | `se_ranking_april_oikos.csv` |
| GA4 conversions (checkout) | `ga4_oikos_conversions_mikmak_checkout.csv` |
| GA4 conversions (store) | `ga4_oikos_conversions_mikmak_click_offline_store.csv.csv` |
| Google Ads quality report | `quality_report_oikos.csv` |

---

## Intake form for a new project

If starting a new client, ask for these inputs before doing anything else:

```
Client name:
Period 1 label (e.g. "Q1 2026") and date range:
Period 2 label (e.g. "Q4 2025") and date range:

Masterlist Google Sheet ID:
Masterlist tab name:

Keyword Study Google Sheet ID:
Keyword Study tab name:

GSC queries CSV  (exported from Google Search Console, comparison mode P1 vs P2):
Google Ads SQR CSV  (account-level search term report, comparison mode P1 vs P2):
SE Ranking CSV  (most recent month, all keywords):

Optional:
  GA4 conversions CSV  (SEO organic — filter: mikmak_checkout + mikmak_click_offline_store)
  Google Ads quality report CSV
```

Once collected: drop the CSVs into the project folder and update the config section above.

---

## Source data format requirements

### GSC CSV
- Row 1: column headers
- Required columns: `Top queries`, `[P1 range] Clicks`, `[P2 range] Clicks`, `[P1 range] Impressions`, `[P2 range] Impressions`, `[P1 range] CTR`, `[P2 range] CTR`, `[P1 range] Position`, `[P2 range] Position`
- Number format: comma = thousands separator (`1,234` = 1234)

### SQR CSV
- Row 1: report title/date range (skip when reading)
- Row 2: column headers (`Account name`, `Search term`, `Clicks`, `Cost`, etc.)
- Required columns: `Search term`, `Search keyword`, `Clicks`, `Clicks (Compare to)`, `Cost`, `Cost (Compare to)`, `Impr.`, `Impr. (Compare to)`
- Number format: space = thousands separator (`32 395` = 32395), comma = decimal (`135507,64` = 135507.64)
- **Read with `skip_rows=1`** to jump past the title row

### SE Ranking CSV
- Row 1: column headers
- Required columns: `Keyword`, `Position`, `Search vol.`, `CPC`, `Search intent`
- Only rows with `Position ≤ 100` are kept (others are filtered in `ingest.norm_se()`)

### Keyword Study (Google Sheets only — no local CSV)
- Required columns: `Keyword`, `LANG`, `TOPIC`, `CATEGORY`, `SUB-CATEGORY`
- Taxonomy columns: `Yogurt types`, `Taste`, `Packaging`, `Ingredient`, `Brands`, `Retailer`, `Demography`, `Benefits`, `Testimonials`, `Bio`, `Moments`, `Recipes`
- Monthly volume columns: `Searches: Oct 2025` through `Searches: Mar 2026`

---

## Pipeline overview

```
1. Read & normalize sources
   norm_gsc()  →  norm_sqr()  →  norm_se()  →  norm_ks()

2. Merge GSC + SQR
   merge_gsc_sqr()           — filter clicks > 1, dedup, full outer join
   format_base_rows()        — shape to Masterlist column headers
   → Write Listing tab (append)

3. SE Ranking enrichment
   trigram.build_index()     — n=3 index on ~1,240 unified rows (built ONCE)
   match_se_keywords()       — iterate SE rows, sim ≥ 0.50
   → Update cols F G AF AL in Masterlist
   → Write ARRAYFORMULA to AI2, AK2

4. Keyword Study enrichment
   match_ks_keywords()       — iterate 14,273 KS rows through same index
                             — pre-filter: skip KS keywords with 0 shared trigrams
                             — top-50 candidate cap per keyword
   sim ≥ 0.65 → update cols A C D E H I AM–AX AZ–BE in Masterlist
   sim < 0.65 → write to KW Review tab

5. Human review
   User fills approved = YES in KW Review tab
   Script re-reads and writes KS cols for approved rows
```

---

## Python module reference (`one_search/`)

| Module | Function(s) | Does |
|---|---|---|
| `normalize.py` | `normalize()`, `clean_num()`, `parse_pct()` | Text and number normalization (handles NA + French number formats) |
| `trigram.py` | `trigrams_arr()`, `jaccard()`, `build_index()` | n=3 trigram index and Jaccard similarity |
| `ingest.py` | `norm_gsc()`, `norm_sqr()`, `norm_ks()`, `norm_se()` | Raw CSV/sheet rows → standard internal field names |
| `merge.py` | `merge_gsc_sqr()` | Filter → dedup → full outer join GSC ∪ SQR |
| `format_rows.py` | `format_base_rows()` | Unified rows → Masterlist column names |
| `match_se.py` | `match_se_keywords()` | SE Ranking → Masterlist (threshold 0.50) |
| `match_ks.py` | `match_ks_keywords()` | KS → Masterlist (split at 0.65); returns `(high_conf_rows, review_rows)` |

---

## Entry point

`run_pipeline.py` — **current entry point** (multi-brand rewrite, since 2026-06-18). Config-driven via `brands/<handle>/config.json` — reads all sources from Google Sheets, runs the full pipeline, writes to the Masterlist, runs SEM QV attribution, then calls the SE Ranking API to fill in missing search volumes. Run with:

```bash
python3 run_pipeline.py --brand oikos-usa
python3 run_pipeline.py --brand oikos-usa --max-rows 500   # smaller test batch
```

Follow with `python3 build_dashboard.py --brand oikos-usa` to build the HTML dashboard.

A timestamped log is written to `logs/` on each run.

**Deprecated:** `run_onesearch.py` (Apr 2026) was the original single-brand, Oikos-only entry point. It's kept for reference only — do not run it. It hardcodes the `.env` path, GSC/KS column names, and Masterlist column letters, none of which `run_pipeline.py` does.

---

## How to run a quick check

```bash
python3 sample_test.py
```

This runs 20 rows from each local CSV through steps 1–3 without touching Google Sheets.
Use it to verify the pipeline is working after any changes.

---

## Key decisions (do not change without flagging)

- **Click threshold:** keep rows with > 1 click in either period (not > 0, not ≥ 1). This eliminates noise without losing real data.
- **Merge direction:** index built on the ~1,240 unified queries, NOT on 14,273 KS keywords. Building on KS caused OOM — the unified index is 11.5× smaller.
- **Top-50 cap:** KS matching ranks candidates by shared trigram count and checks only the top 50. The best Jaccard match is almost always in the top 50 by count. Accuracy loss is negligible.
- **Similarity thresholds:** ≥ 0.65 = auto-write to Masterlist; 0.50–0.65 = human review; < 0.50 = unmatched.
- **SEM conversions:** NOT in the SQR report. Need a separate Google Ads conversion export filtered to `mikmak_checkout` and `mikmak_click_offline_store`.
- **SQR number format:** French-style (`space` = thousands, `comma` = decimal). `clean_num()` handles both formats automatically.
- **SQR CSV:** has a title row before headers — read with `skip_rows=1`.
