---
name: onesearch-danone
description: >
  Generates a self-contained interactive HTML One Search dashboard for a Danone USA brand
  (Oikos, International Delight, Happy Family, Activia, Silk, Too Good & Co., StoK, Light+Fit, and others).
  Reads data from Google Sheets or local CSV exports, calculates OneSearch KPIs and territory metrics,
  and generates the 6 dashboard tabs (Glossary, OneSearch Dashboard, Territory Deep Dive,
  Recommendations, Quality Score, SQR).
  Use when the user wants to create or update a One Search dashboard, mentions "/onesearch-danone",
  or asks to generate a Danone brand dashboard.
---

# One Search Danone USA — HTML Dashboard

This skill generates a complete, interactive One Search dashboard for Danone USA brands.

**HTML reference template:**
`/Users/carlaklaasen/claude_code/one_search/reference/activia_ca_onesearch_dashboard.html`

**Source of truth for all brand sheet IDs and project links:**
Google Sheet ID `1o526Qv4UzP_Qfe-cjrfvcA7jRUi6zUtd9Ecp2WPMIhQ`, tab: `One Search`

**Credentials:** Load from `/Users/carlaklaasen/claude_code/.env`

---

## Arguments

- `$ARGUMENTS` — The target brand slug. Examples: `oikos`, `activia`, `silk`, `id`, `too-good`, `stok`, `light-fit`

## Optional Flags

| Flag | Effect |
|------|--------|
| `--source [sheets\|local]` | Data source: `sheets` = read from Google Sheets API (default); `local` = read from local CSV files |
| `--data-path <path>` | Local CSV folder when `--source local` (default: `/Users/carlaklaasen/claude_code/one_search/imports/`) |
| `--period-current <Q>` | Current period label (e.g. `Q1 2026`; default: detected from data) |
| `--period-prev <Q>` | Previous period label (e.g. `Q4 2025`) |
| `--output <path>` | HTML output file (default: `/Users/carlaklaasen/claude_code/one_search/one_search_html/<brand>_onesearch_dashboard.html`) |
| `--no-sqr` | Skip the SQR tab (use when Q4 SQR data is unavailable) |

---

## PRODUCT CONTEXT

### Danone USA Brand Registry

| Brand | Slug | Masterlist Sheet ID |
|-------|------|---------------------|
| Oikos | `oikos` | `1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU` |
| International Delight | `id` | *(look up in tracker)* |
| Activia | `activia` | *(look up in tracker)* |
| Happy Family | `happy-family` | *(look up in tracker)* |

> For any brand without a Masterlist ID listed above, look it up in the tracker sheet (`1o526Qv4UzP_Qfe-cjrfvcA7jRUi6zUtd9Ecp2WPMIhQ`, tab `One Search`).

### Oikos — Google Sheet IDs (confirmed)

| Data Source | Sheet ID | Tab |
|-------------|----------|-----|
| Masterlist | `1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU` | `Listing` |
| GSC Export | `1XuMSoaKZ_-Tn_avwC0cdHTh1JwjJtSKyUxFVrtH1rQ0` | `Queries` |
| Quality Score | `1oDExKhwt5-HmMrJFv5U5hU35YCT-KV0XvsiAk4M2PfU` | `OIKOS` |
| SQR Report | `1_-RWWaeF9yfctjjzNfkxGGCb8ujzWFhm5bM24f9PZQU` | `OIKOS` |
| Keyword Study | `1kiOgeo5J66tAngETUGVv1CFX072g4rnDiWKLf6KP7co` | `Keyword study US` |
| SE Ranking | `1bqIGq7rDWmYx9OhBCibO694Szm5SB4hbYgBhdacSPUs` | `OIKOS` |
| GA4 Conv. — Offline Store | `1gU2Uy2GhNd4ipVPm-vm1vnoLkKMGvLuNL6JdBppWDDc` | *(first sheet)* |
| GA4 Conv. — Checkout | `1lNzDst7QjRNiBLgveZFczAj8DpDkSromjygHTWb2Aak` | *(first sheet)* |

### Standard Periods

- **Current (P1)**: current quarter (e.g. Q1 2026 = Jan 1 – Mar 31)
- **Previous (P2)**: previous quarter (e.g. Q4 2025 = Oct 1 – Dec 31)
- Always compare P1 vs. P2 across all metrics.

### Brand Color Palette

| Brand | Brand Color |
|-------|-------------|
| Activia | `#B8001C` (Danone red) |
| Oikos | `#1A3C6E` (Oikos blue) |
| International Delight | `#E65100` (ID orange) |
| Happy Family | `#4CAF50` (Happy Family green) |

---

## WORKFLOW

```
STEP 1  COLLECT DATA       → Google Sheets API (default) or local CSV files
STEP 2  CALCULATE METRICS  → Aggregate KPIs, territories, QS, SQR from Masterlist
STEP 3  PREPARE JS         → Structure const DATA, QS_CLASSIFIED, SQR_DATA arrays
STEP 4  GENERATE HTML      → Start from reference template; adapt per brand
STEP 5  INJECT DATA        → Replace JS data blocks; hardcode territory/KPI HTML
STEP 6  VALIDATE           → Verify all 6 tabs, KPIs, charts, filters
```

---

## STEP 1 — DATA COLLECTION

### 1.0 Prompt user for data source

At the start of any run, if `--source` is not specified, ask:

```
Data source for [brand]:
  [1] Google Sheets (reads live data via API — recommended)
  [2] Local CSV files (reads from /imports/ folder)
Enter 1 or 2:
```

Proceed with the chosen method throughout all steps.

### 1.1 Identify available data

**Option A — Google Sheets (default):**
```python
# Sheet IDs are loaded from the tracker or the brand config above.
# All reads go through the Sheets API using credentials from .env.
sheet_ids = {
    "masterlist":    "1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU",
    "gsc":           "1XuMSoaKZ_-Tn_avwC0cdHTh1JwjJtSKyUxFVrtH1rQ0",
    "quality_score": "1oDExKhwt5-HmMrJFv5U5hU35YCT-KV0XvsiAk4M2PfU",
    "sqr":           "1_-RWWaeF9yfctjjzNfkxGGCb8ujzWFhm5bM24f9PZQU",
    "keyword_study": "1kiOgeo5J66tAngETUGVv1CFX072g4rnDiWKLf6KP7co",
    "se_ranking":    "1bqIGq7rDWmYx9OhBCibO694Szm5SB4hbYgBhdacSPUs",
    "ga4_offline":   "1gU2Uy2GhNd4ipVPm-vm1vnoLkKMGvLuNL6JdBppWDDc",
    "ga4_checkout":  "1lNzDst7QjRNiBLgveZFczAj8DpDkSromjygHTWb2Aak",
}
```

**Option B — Local CSV:**
```bash
ls "/Users/carlaklaasen/claude_code/one_search/imports/" | grep -i <brand>
```
Expected files:
- `account_level_sqr_report_<brand>.csv`
- `quality_report_<brand>.csv`
- `gsc_export_queries_<brand>.csv`
- `gsc_export_pages_<brand>.csv` *(leading space in filename — sanitize on read)*
- `ga4_<brand>_conversions_mikmak_checkout.csv`
- `ga4_<brand>_conversions_mikmak_click_offline_store.csv`
- `se_ranking_<month>_<brand>.csv`

### 1.2 Read data — Python code (both options)

```python
import os, json
import pandas as pd
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv("/Users/carlaklaasen/claude_code/.env")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")

def get_sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)

def read_sheet(sheet_id: str, tab: str, skip_rows: int = 1) -> pd.DataFrame:
    """Read a Google Sheet tab into a DataFrame."""
    svc = get_sheets_service()
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=tab
    ).execute()
    values = result.get("values", [])
    if not values:
        return pd.DataFrame()
    headers = values[skip_rows - 1]
    rows = values[skip_rows:]
    # Pad short rows to header length
    rows = [r + [""] * (len(headers) - len(r)) for r in rows]
    return pd.DataFrame(rows, columns=headers)

def read_local(path: str, skip_rows: int = 1, **kwargs) -> pd.DataFrame:
    """Read a local CSV, stripping leading/trailing spaces from the path."""
    return pd.read_csv(path.strip(), skiprows=skip_rows, **kwargs)

# ── Usage ──────────────────────────────────────────────────────────────────
USE_SHEETS = True  # False → local CSV

if USE_SHEETS:
    masterlist  = read_sheet(sheet_ids["masterlist"],    "Listing",          skip_rows=1)
    gsc         = read_sheet(sheet_ids["gsc"],           "Queries",          skip_rows=1)
    sqr         = read_sheet(sheet_ids["sqr"],           "OIKOS",            skip_rows=2)
    qs_report   = read_sheet(sheet_ids["quality_score"], "OIKOS",            skip_rows=3)
    se_ranking  = read_sheet(sheet_ids["se_ranking"],    "OIKOS",            skip_rows=1)
    kw_study    = read_sheet(sheet_ids["keyword_study"], "Keyword study US", skip_rows=1)
    ga4_offline = read_sheet(sheet_ids["ga4_offline"],   "Sheet1",           skip_rows=9)
    ga4_checkout= read_sheet(sheet_ids["ga4_checkout"],  "Sheet1",           skip_rows=9)
else:
    DATA_PATH = "/Users/carlaklaasen/claude_code/one_search/imports/"
    masterlist  = read_local(DATA_PATH + "MASTERLIST - Oikos OneSearch - Listing.csv")
    gsc         = read_local(DATA_PATH + "gsc_export_queries_oikos.csv",          skip_rows=1)
    sqr         = read_local(DATA_PATH + "account_level_sqr_report_oikos.csv",    skip_rows=2)
    qs_report   = read_local(DATA_PATH + "quality_report_oikos.csv",              skip_rows=3)
    se_ranking  = read_local(DATA_PATH + "se_ranking_april_oikos.csv",            skip_rows=1)
    ga4_checkout= read_local(DATA_PATH + "ga4_oikos_conversions_mikmak_checkout.csv", skip_rows=9)
    ga4_offline = read_local(DATA_PATH + "ga4_oikos_conversions_mikmak_click_offline_store.csv.csv", skip_rows=9)
```

### 1.3 Source Data Column Headers (validated against live sheets)

**Masterlist — Listing tab** (Google Sheet `1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU`):

| Col | Column name in sheet | Notes |
|-----|----------------------|-------|
| A | `LANG` | EN / FR / New |
| B | `Keyword` | |
| C | `TOPICS` | Often blank — needs KS match |
| D | `CATEGORY` | Often blank |
| E | `SUB-CATEGORY` | Often blank |
| F | `Position SE Ranking` | |
| G | `Average Search Volume` | |
| H | `Volume Q1 2026` | Sum of Jan–Mar 2026 monthly volumes from KS |
| I | `Volume Q4 2025` | Sum of Oct–Dec 2025 monthly volumes from KS |
| J | `Coverage One Search Q1 2026` | Formula: `Clics OneSearch Q1 / Volume Q1` (decimal) |
| K | `Coverage One Search Q4 2025` | Formula: `Clics OneSearch Q4 / Volume Q4` (decimal) |
| L | `Clics OneSearch Q1 2026` | = SEO + SEM clicks P1 |
| M | `Impressions OneSearch Q1 2026` | = SEO + SEM impr. P1 |
| N | `Clics OneSearch Q4 2025` | |
| O | `Impressions OneSearch Q4 2025` | |
| P | `Clics SEO Q1 2026` | From GSC |
| Q | `Clics SEM Q1 2026` | From SQR |
| R | `Clics SEO Q4 2025` | ⚠️ May be formatted as `%` in sheet — raw number is `R/100` |
| S | `Clics SEM Q4 2025` | 0 if Q4 SQR unavailable |
| T | `Impr. SEO Q1 2026` | |
| U | `Impr. SEM Q1 2026` | |
| V | `Impr. SEO Q4 2025` | |
| W | `Impr. SEM Q4 2025` | |
| X | `CTR SEO Q1 2026` | As `"6%"` string — parse to float |
| Y | `CTR SEM Q1 2026` | Computed: Q / U |
| Z | `CTR SEO Q4 2025` | |
| AA | `CTR SEM Q4 2025` | Computed: S / W |
| AB | `Conversions SEO Q1 2026` | From GA4 (URL-matched) |
| AC | `Conversions SEM Q1 2026` | From GA4 MikMak (checkout + offline store) |
| AD | `Conversions SEO Q4 2025` | TBD |
| AE | `Conversions SEM Q4 2025` | TBD |
| AF | `CPC SEO Q1 2026` | From SE Ranking → `CPC` |
| AG | `CPC avg. SEM Q1 2026` | Computed: AH / Q |
| AH | `Spent SEM Q1 2026` | From SQR → `Cost` |
| AI | `Cost SEO Q1 2026` | ⚠️ Computed: `AF × P` — verify before deploying |
| AJ | `Spent SEM Q4 2025` | |
| AK | `Cost SEO Q4 2025` | ⚠️ Computed: `AF × R` |
| AL | `Purchase intent` | From SE Ranking `Search intent` |
| AM | `Questions` | From Keyword Study |
| AN | `Yogurt types` | From Keyword Study |
| AO | `Taste` | From Keyword Study |
| AP | `Packaging` | From Keyword Study |
| AQ | `Ingredient` | From Keyword Study |
| AR | `Brands` | From Keyword Study |
| AS | `Retailer` | From Keyword Study |
| AT | `Demography` | From Keyword Study |
| AU | `Benefits` | From Keyword Study |
| AV | `Testimonials` | From Keyword Study |
| AW | `Bio` | From Keyword Study |
| AX | `Moments` | From Keyword Study |
| AY | `Recipes` | From Keyword Study |
| AZ | `Searches: Oct 2025` | Monthly volume from KS |
| BA | `Searches: Nov 2025` | |
| BB | `Searches: Dec 2025` | |
| BC | `Searches: Jan 2026` | |
| BD | `Searches: Feb 2026` | |
| BE | `Searches: Mar 2026` | |

> ⚠️ **Known data issue:** Column R (`Clics SEO Q4 2025`) in the live Oikos sheet is formatted as a percentage in Google Sheets, showing values like `898300%` instead of `8983`. When reading via API, the raw value will be correct — only the display is wrong. Verify after each pipeline run.

**GSC Queries tab** (Google Sheet `1XuMSoaKZ_-Tn_avwC0cdHTh1JwjJtSKyUxFVrtH1rQ0`, tab `Queries`):
```
Top queries | <P1 dates> Clicks | <P2 dates> Clicks | <P1> Impressions | <P2> Impressions |
<P1> CTR | <P2> CTR | <P1> Position | <P2> Position
```

**SQR Report tab** (tab `OIKOS`, 2-row header — skip 2):
```
Account name | Customer ID | Campaign | Search term | Search terms match type |
Search keyword | Search keyword match type |
Clicks | Clicks (Compare to) | Clicks (Change) | Clicks (Change %) |
Currency code | Cost | Cost (Compare to) | Cost (Change) | Cost (Change %) |
Impr. | Impr. (Compare to) | Impr. (Change) | Impr. (Change %) | Campaign Type
```
> Note: Single comparison file — P1 in base columns, P2 in `(Compare to)` columns.

**Quality Score Report** (tab `OIKOS`, 3-row header — skip 3):
```
Keyword status | Keyword | Campaign | Quality Score | Landing page exp. | Ad relevance | Exp. CTR
```
> ⚠️ This export repeats the 7-column block three times horizontally (21 columns total). Parse all three repetitions and deduplicate by keyword.

**GA4 Conversion exports** (9-row header — skip 9):
```
Page path and screen class | Views | Active users | Views per active user |
Average engagement duration per active user | Event count | Key events | Total revenue
```
> Conversions = `Key events` column. Match to keywords via URL path mapping from SE Ranking.

**SE Ranking export:**
```
Keyword | Difficulty | Position | Previous position | Position Serp Features |
Search vol. | Search intent | SERP features | Competition | CPC | URL |
Traffic | Traffic share | Traffic cost
```

---

## STEP 2 — CALCULATE METRICS

All calculations operate on the Masterlist `Listing` tab as the unified data spine.

### 2.1 Global KPIs (OneSearch Dashboard tab)

| Metric | Calculation | Source column(s) |
|--------|-------------|-----------------|
| Search Volume P1 | Sum of `Average Search Volume × 3` across all rows | Col G × 3 (SE Ranking monthly avg × 3 months) |
| Search Volume P2 | Same method for previous period | Col G × 3 |
| OneSearch Clicks P1 | Sum of `Clics OneSearch Q1 2026` | Col L (= P + Q) |
| OneSearch Clicks P2 | Sum of `Clics OneSearch Q4 2025` | Col N |
| SEO Clicks P1 | Sum of `Clics SEO Q1 2026` | Col P |
| SEM Clicks P1 | Sum of `Clics SEM Q1 2026` | Col Q |
| Coverage % | Keywords with SEO position ≤ 20 OR SEM impressions > 0 / total keywords | SE Ranking + SQR |
| Conversions P1 | Sum of `Conversions SEM Q1 2026` (+ SEO if available) | Col AC (+ AB) |
| Spend SEM P1 | Sum of `Spent SEM Q1 2026` | Col AH |

**Variation**: always `(P1 - P2) / P2 × 100`

### 2.2 Coverage Calculation

Coverage is a **share of keywords actively captured** across the search territory:

```
OneSearch Coverage = keywords with (SEO pos ≤ 20 OR SEM impressions > 0) / total keywords × 100
SEO Coverage       = keywords with SEO pos ≤ 20 / total keywords × 100
SEM Coverage       = keywords with SEM impressions > 0 / total keywords × 100
```

A keyword is counted once per channel it is active on. A keyword active on both channels contributes to both SEO and SEM coverage without duplication in OneSearch Coverage.

### 2.3 Quality Score — Data Structure

Parse the Quality Score report (triple-column format → deduplicate by keyword). Join to Masterlist on keyword to get TOPICS/CATEGORY for the `TOPIC`/`CAT`/`SUB` fields.

Format of the `QS_CLASSIFIED` array injected into JS:
```javascript
// [KW, MATCH, CAMP, ADGR, STATUS, URL, QS, LP_EXP, CTR_ATT, PERT, IMPR, CLICS, COUT, CPC, CONV, TOPIC, CAT, SUB]
const QS_CLASSIFIED = [
  ["oikos triple zero", "Exact match", "USA_EDP_OIKOS_BAUPPC2026_...", "Brand",
   "Enabled", "https://www.oikos.com/all-products/triple-zero/",
   7, "Above average", "Above average", "Relevant",
   160372, 27632, 84430.01, 3.06, 0.0, "PRODUCT", "Brand", "Oikos triple zero"],
  // ...
];
```

JS indices:
```javascript
var I = {KW:0, MATCH:1, CAMP:2, ADGR:3, STATUS:4, URL:5, QS:6, LP:7,
         CTR_ATT:8, PERT:9, IMPR:10, CLICS:11, COUT:12, CPC:13, CONV:14,
         TOPIC:15, CAT:16, SUB:17};
```

LP_EXP values: `"Above average"`, `"Average"`, `"Below average"`, `"Not available"`
STATUS values: `"Enabled"`, `"Paused"`, `"Not eligible"`

### 2.4 Territories — Grouping by TOPICS

Group Masterlist rows by the `TOPICS` column (col C). For Oikos (Q1 2026), the confirmed topics are:
`PRODUCTS` · `EATING BETTER` · `RECIPES` · `HEALTH` · `CONSUMER HABITS`

> ⚠️ Most rows currently have blank TOPICS because the keyword study match is incomplete. Only aggregate territory metrics for rows where TOPICS is populated. Flag the coverage gap in the dashboard notes.

For each territory, calculate from the Masterlist:
```python
territory_data = {
    "name": "PRODUCTS",
    "keywords_count": len(rows_in_topic),
    "volume_p1": sum(col_H for rows_in_topic),
    "volume_p2": sum(col_I for rows_in_topic),
    "onesearch_clicks_p1": sum(col_L),
    "onesearch_clicks_p2": sum(col_N),
    "seo_clicks_p1": sum(col_P),
    "seo_clicks_p2": sum(col_R),     # ⚠️ parse % bug if reading from sheet display
    "sem_clicks_p1": sum(col_Q),
    "sem_clicks_p2": sum(col_S),
    "coverage_p1": sum(col_L) / sum(col_H) if sum(col_H) > 0 else 0,
    "conv_sem_p1": sum(col_AC),
    "top5_keywords": sorted(rows_in_topic, key=lambda r: r["col_L"], reverse=True)[:5]
}
```

### 2.5 SQR — Structure for SQR Tab

Source: the SQR report (P1 in base columns, P2 in `(Compare to)` columns).

```javascript
var SQR_DATA = [
  // [query, match_type, campaign, keyword,
  //  impr_p1, impr_p2, impr_diff, impr_pct,
  //  clicks_p1, clicks_p2, clicks_diff, clicks_pct,
  //  cost_p1, cost_p2, cost_diff, cost_pct,
  //  cpc_p1, cpc_p2, cpc_diff, cpc_pct]
  ["oikos protein shake", "Exact match", "USA_EDP_OIKOS_..._TitanBrand...",
   "oikos protein shake",
   136437, 0, 136437, null,
   32395, 0, 32395, null,
   135507.64, 0, 135507.64, null,
   4.18, 0, 4.18, null],
  // ...
];
```
> Q4 SQR data is unavailable for Oikos (P2 columns = 0 for all rows). Use `--no-sqr` or display P1 only with a disclaimer.

---

## STEP 3 — PREPARE JS DATA

```python
import json

# ── Build QS_CLASSIFIED ────────────────────────────────────────────────────
qs_rows = []
for _, row in qs_deduped.iterrows():         # qs_deduped = parsed quality report
    ml_row = masterlist[masterlist["Keyword"] == row["kw"]]
    topic  = ml_row["TOPICS"].values[0]   if len(ml_row) else "UNCLASSIFIED"
    cat    = ml_row["CATEGORY"].values[0] if len(ml_row) else "UNCLASSIFIED"
    sub    = ml_row["SUB-CATEGORY"].values[0] if len(ml_row) else "UNCLASSIFIED"
    qs_rows.append([
        row["kw"], row["match"], row["campaign"], row["adgroup"],
        row["status"], row["url"], int(row["qs"]) if row["qs"].isdigit() else 0,
        row["lp"], row["ctr_att"], row["relevance"],
        int(row["impr"]), int(row["clicks"]), float(row["cost"]),
        float(row["cpc"]), 0.0,   # conversions — not in QS export
        topic, cat, sub
    ])

qs_js = f"const QS_CLASSIFIED = {json.dumps(qs_rows, ensure_ascii=False)};"

# ── Build SQR_DATA ─────────────────────────────────────────────────────────
sqr_js = f"var SQR_DATA = {json.dumps(sqr_rows, ensure_ascii=False)};"

# ── Build const DATA (main keyword dataset for charts) ─────────────────────
# Each row: [keyword, TOPICS, CATEGORY, SUB-CATEGORY,
#            se_pos, avg_vol, vol_p1, vol_p2,
#            coverage_p1, coverage_p2,
#            os_clicks_p1, os_impr_p1, os_clicks_p2, os_impr_p2,
#            seo_clicks_p1, sem_clicks_p1, seo_clicks_p2, sem_clicks_p2,
#            seo_impr_p1, sem_impr_p1, seo_impr_p2, sem_impr_p2,
#            ctr_seo_p1, ctr_sem_p1, ctr_seo_p2, ctr_sem_p2,
#            conv_seo_p1, conv_sem_p1, conv_seo_p2, conv_sem_p2,
#            cpc_seo, cpc_sem_p1, spend_sem_p1, cost_seo_p1,
#            spend_sem_p2, cost_seo_p2, lang]
data_js = f"const DATA = {json.dumps(data_rows, ensure_ascii=False)};"
```

### JS Blocks to Inject in the HTML

Locate these blocks inside a `<script>` tag:
```html
<!-- === DATA INJECTION START === -->
var QS_CLASSIFIED = [...];
var TERRITORY_DATA = [...];
var SQR_DATA = [...];
var KPI_SUMMARY = {...};
const DATA = [...];
<!-- === DATA INJECTION END === -->
```

| Variable | Type | Drives |
|----------|------|--------|
| `var QS_CLASSIFIED` | Array of arrays | Quality Score tab — table, filters, distribution chart |
| `var TERRITORY_DATA` | Array of objects | Territory Deep Dive tab — performance tables, top keywords |
| `var SQR_DATA` | Array of arrays | SQR tab — table, filters, sorting, pagination |
| `var KPI_SUMMARY` | Object | OneSearch Dashboard tab — KPI cards, gauge values |
| `const DATA` | Array of arrays | Interactive charts — matrix/bubble, donuts, keyword browser |

> **Note on current Activia template:** The reference HTML at `/reference/activia_ca_onesearch_dashboard.html` has territory tables and KPI cards as hardcoded HTML rather than JS-driven. When building a new brand dashboard, add the `DATA INJECTION` markers to the template and wire the JS variables to the rendering functions so territory and KPI data can be injected programmatically.

---

## STEP 4 — GENERATE HTML

### 4.1 Start from the reference template

**ALWAYS start from the reference HTML.** Never regenerate from scratch — the template contains 35,000+ lines of finalized CSS, interactive JS, and visual components.

```python
REFERENCE_PATH = "/Users/carlaklaasen/claude_code/one_search/reference/activia_ca_onesearch_dashboard.html"

with open(REFERENCE_PATH, "r", encoding="utf-8") as f:
    html = f.read()
```

### 4.2 Per-Brand Adaptations

| Element | Where in HTML | Change to |
|---------|---------------|-----------|
| `<title>` | Line ~6 | `OneSearch Dashboard - [Brand] USA` |
| H1 title | `<h1>` in hero | `One Search Dashboard — [Brand]` |
| Subtitle | `.subtitle` | `Digitad × [Brand] · One Search · [Month Year]` |
| Brand CSS variable | `:root { --brand: ... }` | Brand color from palette table |
| Period labels | `"Q1 2026"`, `"Q4 2025"` throughout | Replace with actual periods |
| `const QS_CLASSIFIED` | Line ~1736 | Replace array with new brand data |
| `var SQR_DATA` | Line ~9426 | Replace array with new brand data |
| `const DATA` | Line ~14443 | Replace array with new brand data |
| Territory HTML blocks | Lines ~581–1380 | Replace 6 territory blocks with brand-specific HTML |
| KPI card values | Static numbers throughout | Replace with computed values |

### 4.3 Static Elements Requiring Manual Content

These sections are narrative prose — populate after data calculations:
- **Territory Deep Dive**: Wins, Attention Points, Actions & Next Steps per territory
- **One Search Recommendations**: 3 levels — Immediate / Short Term / Medium Term
- **Introduction & Glossary**: Hero chips, coverage formula explanation

---

## STEP 5 — DATA INJECTION

### 5.1 Locate injectable JS blocks

```bash
grep -n "const QS_CLASSIFIED\|var SQR_DATA\|const DATA" \
  "/Users/carlaklaasen/claude_code/one_search/reference/activia_ca_onesearch_dashboard.html" | head -10
```

Expected output:
```
1736:const QS_CLASSIFIED = [
4342:var SQR_ACTIVIA = [      ← legacy name; also check for var SQR_DATA
9426:var SQR_DATA=[
14443:const DATA = [
```

### 5.2 Replace JS arrays with Python

```python
import re

def replace_js_var(html: str, var_pattern: str, new_js: str) -> str:
    pattern = rf'{var_pattern}\s*=\s*\[.*?\];'
    return re.sub(pattern, new_js, html, flags=re.DOTALL)

html = replace_js_var(html, r'const QS_CLASSIFIED', qs_js)
html = replace_js_var(html, r'var SQR_DATA',         sqr_js)
html = replace_js_var(html, r'const DATA',           data_js)
```

### 5.3 Hardcode territory HTML and KPI cards

Territory blocks and KPI card values are **not driven by JS** — they are static HTML with numbers written directly. Replace each territory block comment-to-comment:

```python
# Example: Replace Territory 1 block
old_block = re.search(
    r'<!-- ={20} TERRITORY 1.*?<!-- ={20} TERRITORY 2',
    html, re.DOTALL
).group(0)

new_block = f"""<!-- ===================== TERRITORY 1: PRODUCTS ===================== -->
<div class="territory-block">
  ... [hardcoded HTML with computed P1/P2 values] ...
</div>
<!-- ===================== TERRITORY 2: ..."""

html = html.replace(old_block, new_block)
```

### 5.4 Write output

```python
OUTPUT_PATH = f"/Users/carlaklaasen/claude_code/one_search/one_search_html/oikos_onesearch_dashboard.html"
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Written: {OUTPUT_PATH} ({len(html):,} bytes)")
```

---

## STEP 6 — VALIDATION

### Tab 1 — Introduction & Glossary
- [ ] Title and subtitle correct (brand + period)
- [ ] Hero chips current (keyword count, period, KPIs)
- [ ] Coverage formula explanation visible

### Tab 2 — OneSearch Dashboard
- [ ] KPI cards show computed values + Q-over-Q variations (▲/▼)
- [ ] SVG gauges render (4 circular gauges)
- [ ] Donut charts render (Clicks by Territory, Coverage by Channel, Conversions)
- [ ] Matrix/Bubble chart renders with tooltip on hover
- [ ] SQR-Only Keywords table visible

### Tab 3 — Territory Deep Dive
- [ ] 5 territory blocks present (PRODUCTS, EATING BETTER, RECIPES, HEALTH, CONSUMER HABITS)
- [ ] Performance tables show P1/P2 with ▲/▼ variations
- [ ] Top 5 keywords chips visible per territory
- [ ] SEO/SEM analysis prose filled in

### Tab 4 — One Search Recommendations
- [ ] 3 priority levels (Immediate / Short Term / Medium Term)
- [ ] Each recommendation has: context, problem, SEO action, SEM action, estimated gain

### Tab 5 — Quality Score
- [ ] KPI cards calculated from `QS_CLASSIFIED` (avg QS, % above 7, total impressions)
- [ ] Bar chart (QS 1–10 distribution) renders
- [ ] LP Experience distribution visible
- [ ] Filterable, paginated table works (Topic, Category, Status, QS range, text search)

### Tab 6 — SQR
- [ ] Table shows all columns (Query, Match, Campaign, Impr, Clicks, CPC, Cost)
- [ ] P1 values displayed (P2 = 0 with disclaimer if Q4 SQR unavailable)
- [ ] Filters functional (Campaign, Match Type)
- [ ] Column sorting works
- [ ] Pagination correct (50 rows/page)

---

## HTML STRUCTURE — QUICK REFERENCE

### Navigation (6 tabs)

```html
<nav class="tab-nav">
  <button class="tab-btn active" onclick="switchTab('glossaire', this)">Introduction & Glossary</button>
  <button class="tab-btn" onclick="switchTab('onesearch', this)">OneSearch Dashboard</button>
  <button class="tab-btn" onclick="switchTab('territory', this)">Territory Deep Dive</button>
  <button class="tab-btn" onclick="switchTab('recos', this)">One Search Recommendations</button>
  <button class="tab-btn" onclick="switchTab('qualityscore', this)">Quality Score</button>
  <button class="tab-btn" onclick="switchTab('sqr', this)">SQR</button>
</nav>
```

### CSS — Key Variables

```css
:root {
  --brand: #1A3C6E;   /* Update per brand */
  --green: #16A34A;
  --orange: #EA580C;
  --blue: #1D4ED8;
  --bg: #F9FAFB;
  --card: #FFFFFF;
  --border: #E5E7EB;
  --text: #111827;
}
```

### Chart Components

```javascript
// Gauge SVG — 4 circular gauges on OneSearch Dashboard tab
function renderGauge(containerId, value, maxValue, label, variation) { ... }

// Donut — Clicks by Territory, Coverage by Channel, Conversions
function renderDonut(canvasId, data, colors) { ... }

// Matrix/Bubble — SEO Clicks (X) vs SEM Clicks (Y), radius = conversions
// Driven by const DATA — requires TOPICS to be populated
function renderMatrix(canvasId, territories) { ... }
```

---

## OUTPUT FILES

| File | Path |
|------|------|
| HTML Dashboard | `/Users/carlaklaasen/claude_code/one_search/one_search_html/<brand>_onesearch_dashboard.html` |
| Reference Template | `/Users/carlaklaasen/claude_code/one_search/reference/activia_ca_onesearch_dashboard.html` |

---

## IMPLEMENTATION NOTES

- **Self-contained**: No external dependencies (no CDN, no fetch). All data and code inline.
- **Google Fonts Poppins**: Only external dependency — acceptable for browser viewing.
- **File size**: Final HTML is typically 5–8 MB. Normal.
- **Vanilla JS only**: No React, Vue, or D3. Maintain this constraint.
- **Pagination**: SQR and QS tables require client-side pagination (50 rows/page).
- **Periods**: Period labels must be consistent everywhere in the file — use find-replace after injection.
- **TOPICS gap**: If most keywords lack TOPICS, the matrix/bubble chart will be empty. Add a note in the Territory Deep Dive tab and log the gap count.
- **Q4 SQR**: If unavailable, set all P2 SQR values to 0 and add a visible disclaimer in the SQR tab header.
- **Google API auth**: Uses service account from `GOOGLE_SERVICE_ACCOUNT_FILE` in `.env`. Falls back to OAuth2 if service account lacks sheet access.

## PLAN.md ALIGNMENT (verified 2026-05)

**This skill is the authority.** If there is a conflict between this skill and `one_search_skill/PLAN.md`, PLAN.md must be updated to match.

Verified alignment:
- Column mapping (A–BE) ✅
- Coverage = binary share of keywords captured (pos ≤ 20 or SEM active) ✅
- Search Volume = Average Search Volume × 3 ✅
- CTR SEM and CPC SEM are computed, not in exports ✅
- Cost SEO = CPC × GSC clicks ⚠️ (marked for verification in both)
- Conversions SEM = GA4 MikMak (checkout + offline store) ✅
- Pipeline entry point: `run_onesearch.py` ✅

## FINAL REMINDER

The deliverable is a **single self-contained HTML file**. The recipient opens it in a browser with no server dependency. Everything — CSS, JS, data, charts — must be inline.
