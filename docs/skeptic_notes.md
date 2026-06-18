# Skeptic Notes — OneSearch Pipeline Rewrite

**Reviewer:** Senior engineer, adversarial pass  
**Date:** 2026-06-18  
**Scope:** All existing pipeline files read in full; new rewrite files (brands/oikos-usa/config.json, pipeline/utils.py, pipeline/sem_qv.py, pipeline/validate.py, run_pipeline.py, scripts/build_html.py, build_dashboard.py) not yet written — notes flag what they MUST handle based on evidence from the current code.

---

## [pipeline/ingest.py — norm_gsc()] — GSC date column names hardcoded as date strings

Risk level: HIGH  
Line/section: Lines 12–26 (`norm_gsc`)  
Issue: Column names `'1/1/26 - 3/31/26 Clicks'`, `'10/1/25 - 12/31/25 Clicks'`, etc. are literal date strings. When a new client has different period dates (e.g. a French Canadian export uses `'1/1/26 - 3/31/26 Clics'`) or when Oikos Q2 arrives with `'4/1/26 - 6/30/26 Clicks'`, `norm_gsc` silently returns all zeros for every row — the function gets `None` from every `.get()` call, `clean_num(None)` returns 0.0, and every row is discarded by the `if c1 == 0 and c2 == 0` guard. The pipeline continues with an empty GSC array and produces a masterlist with no organic click data. No exception is raised, no warning is logged.  
Suggestion: The new `config.json` must supply `gsc_col_p1_clicks`, `gsc_col_p2_clicks`, etc. The new `ingest.py` (or `pipeline/utils.py`) must take these column names as parameters. On startup, log a sample of actual column names found in the first GSC row vs the expected names, and `sys.exit` if none match.

---

## [pipeline/ingest.py — norm_gsc()] — French GSC column name drift (Clics vs Clicks)

Risk level: HIGH  
Line/section: Lines 12–26  
Issue: The current code exclusively uses `'Clicks'` (English). A French GSC export would use `'Clics'`. If a French client is run, all GSC data silently produces zeros (same failure mode as above). The `norm_sqr` function uses `'Clicks'` and `'Clicks (Compare to)'` — the French SQR uses `'Clics'` and `'Clics (comparer à)'`. Both fail silently.  
Suggestion: The new `config.json` must carry per-language column name overrides, or the ingest layer must try both variants and log which was used.

---

## [pipeline/normalize.py — clean_num()] — Ambiguous comma handling on values like "1,5"

Risk level: MEDIUM  
Line/section: Lines 19–23  
Issue: The disambiguation logic treats a comma with no period as a French decimal: `"1,5"` → `1.5`. But `"1,500"` (a legitimate NA thousands-separated integer) also has no period, so it becomes `1.5` instead of `1500`. This is the documented trade-off, but the comment does not acknowledge the edge case. In practice, SQR costs like `"1,234"` would silently produce `1.234` instead of `1234`. The correct rule would be: if comma is followed by exactly 3 digits with no other comma, it's likely a thousands sep — but the current code doesn't check this.  
Suggestion: Add explicit unit tests for `"1,234"` (→ 1234), `"1,5"` (→ 1.5), `"1 234,56"` (→ 1234.56), `"32,395"` (→ 32395). Document the known ambiguity range and the policy decision. Add a validation step that logs a warning if any SQR cost value comes out below 1.0 — a real-world CPC below $0.01 would flag accidental decimal treatment.

---

## [pipeline/normalize.py — clean_num()] — Does not handle French non-breaking space (U+00A0) in all positions

Risk level: MEDIUM  
Line/section: Line 18  
Issue: The code strips `\xa0` (non-breaking space) and regular space. However, some GA4 exports use thin space (U+2009) or en-space (U+2002) as thousands separators. The `replace(' ', '')` call only strips one specific Unicode space; others would remain, causing `float()` to raise `ValueError` → silently returning 0.0. This is especially likely for GA4 session counts and key event counts.  
Suggestion: Replace the multi-`replace` with `re.sub(r'[\s    ]+', '', s)` before the comma/period disambiguation.

---

## [pipeline/ingest.py — norm_se()] — BOM handling is single-key forward-scan only

Risk level: MEDIUM  
Line/section: Lines 102–103  
Issue: `next((k for k in j if k.replace('﻿', '') == 'Keyword'), 'Keyword')` scans all keys of the first dict and returns the first key that, after stripping the BOM character (U+FEFF), equals `'Keyword'`. This works for the SE Ranking CSV BOM case. However: (1) if the BOM appears somewhere mid-string rather than as the first character only, `replace` still strips it globally, which could match a false key; (2) if the SE Ranking export format changes and the keyword column is named `'Mot clé'` (French), the scan fails and silently falls back to `'Keyword'`, returning empty strings for every row. (3) The BOM strip only uses the specific `'﻿'` (U+FEFF) character literal — if the file has a different BOM variant it won't be caught.  
Suggestion: Normalize all dict keys at ingest time: `{k.replace('﻿', '').strip(): v for k, v in row.items()}`. Add `'Mot clé'` and `'Mots-clés'` to a candidates list. Log a warning if the keyword column resolves via BOM strip rather than direct match.

---

## [pipeline/ingest.py — norm_ks()] — Monthly search volume columns hardcoded to 6 specific month strings

Risk level: HIGH  
Line/section: Lines 88–93  
Issue: `'Searches: Oct 2025'` through `'Searches: Mar 2026'` are hardcoded. When this pipeline runs for Q2 2026 (next quarter), the new months will be `Apr/May/Jun 2026` and the old columns won't exist. `j.get('Searches: Oct 2025')` returns `None`, `None or ''` becomes `''`, and all volume data silently drops to zero. The Average Search Volume calculation in `run_onesearch.py` lines 514–517 (`vol_p1 + vol_p2`) then computes 0 for everything, breaking Coverage gauges in the HTML dashboard.  
Suggestion: The new `config.json` must specify the 6 month keys. `norm_ks` must accept them as parameters. Failing to find a single month column should log a warning listing which months were found vs expected.

---

## [run_onesearch.py — _run()] — ARRAYFORMULA column letters hardcoded (J, K, AI, AK)

Risk level: HIGH  
Line/section: Lines 319–324  
Issue: The ARRAYFORMULA cells `J2`, `K2`, `AI2`, `AK2` and the formula strings referencing `L2:L`, `N2:N`, `P2:P`, `R2:R`, `AF2:AF` are hardcoded. These reference specific column positions in the Masterlist. If any new column is inserted before column J (Coverage) or before column AF (CPC SEO), the formulas will silently compute against wrong data. When porting to Activia-CA or any French masterlist, the column order could differ. The formula strings also embed `B2:B` and `G2:G` as hardcoded references.  
Suggestion: The formula cells and their contents must be derived from the masterlist header position map, not hardcoded. The new `config.json` should list which masterlist column names feed each formula, and the new `run_pipeline.py` must resolve the column letters dynamically using the header read before writing.

---

## [run_onesearch.py — _run()] — HEADER_CORRECTIONS is hardcoded to specific year strings

Risk level: MEDIUM  
Line/section: Lines 94–103  
Issue: `HEADER_CORRECTIONS` maps 2024 → 2025 and Jan 2025 → Jan 2026 header strings. These are Oikos-specific and will be wrong for any other client. In the rewrite, if this dict is moved to `brands/oikos-usa/config.json` but the new pipeline fails to load or apply it, old headers won't be corrected and data will land in wrong columns without any error.  
Suggestion: Move to `config.json`. The pipeline must validate after applying corrections that the resulting headers match the expected set. If a correction target key doesn't appear in the sheet headers, log it as a warning (don't silently skip).

---

## [run_onesearch.py — build_row()] — COLUMN_ALIASES lookup is O(n×m) and order-dependent

Risk level: LOW  
Line/section: Lines 261–273  
Issue: For every header column with a blank value, the function iterates all alias pairs. With 57 columns × 7 aliases this is negligible performance-wise, but the logic has a subtle bug: if a pipeline key appears as the value in TWO alias pairs, the first match wins and the second is silently ignored. Currently this doesn't cause a bug but the pattern is fragile for expansion.  
Suggestion: Pre-invert the alias map once (`sheet_col → pipeline_key`) and use a single dict lookup. Move the alias map to `config.json` under an `aliases` key.

---

## [run_onesearch.py — _run()] — GA4 conversion column names hardcoded: "Conversions SEM Q1 2026" mislabeled as SEM when it's actually MikMak Checkout (SEO)

Risk level: HIGH  
Line/section: Lines 536–541  
Issue: The `_conv_maps` list maps:
- `'Conversions SEO Q1 2026'` ← `checkout_map` (MikMak checkout = SEO attribution) ✓
- `'Conversions SEM Q1 2026'` ← `offline_map` (offline store = SEM attribution)

This appears correct. BUT `sem_qv_attribution.py` line 39 writes to `"Conversions SEM Q1 2026"` (column AC) as the QV SEM result, OVERWRITING whatever `run_onesearch.py` wrote to that column from the offline_map. The two scripts conflict on column AC with no reconciliation logic. After `run_onesearch.py` runs, column AC contains pro-rata offline click conversions. After `sem_qv_attribution.py` runs, column AC is overwritten with Thomas's QV SEM methodology values. These are different numbers and there is no guard preventing the wrong one from persisting depending on run order.  
Suggestion: Decide which methodology owns column AC. The new `pipeline/sem_qv.py` must either replace the pro-rata offline map entirely, or write to a separate column. Document the column ownership explicitly in `config.json`.

---

## [scripts/sem_qv_attribution.py — read_masterlist()] — Reads only to column BF but masterlist may already have BF filled by prior run

Risk level: MEDIUM  
Line/section: Lines 328, 350  
Issue: `sheets_get(token, MASTER_FILE_ID, f"'{MASTER_TAB}'!A1:BF5000")` reads to column BF. Column BF is `SEM Recommendation` — the very column this script writes. If the script has run before, BF already has data. The script re-calculates and overwrites unconditionally (correct behavior), but the read range misses any columns added AFTER BF in a future expansion. The known issue from the 48-bug list is that the current masterlist read range misses column BF itself on first run (before the column is created, BF doesn't exist, so the range returns one column fewer). The script's `col_idx('SEM Recommendation')` returns `None`, `bf_col_idx = len(headers)` appends it — but if the header row was already written by a previous run, `len(headers)` could be wrong.  
Suggestion: Always read `!A1:BG5000` (one column beyond BF) to detect whether BF already exists. If `sem_rec` column is found at index > 57 (unexpected position), warn before writing.

---

## [scripts/sem_qv_attribution.py — read_ga4_ads()] — Header detection is a fragile heuristic

Risk level: HIGH  
Line/section: Lines 218–235  
Issue: The header-row finder uses:
```python
if row and any('equ' in str(row[0]).lower() or 'session' in str(row[0]).lower()
               or 'page de destination' in str(row[1] if len(row) > 1 else '').lower()
               for _ in [1]):
    if len(row) >= 4 and 'session' in ' '.join(str(c).lower() for c in row):
```
The `for _ in [1]` idiom iterates once over `[1]` and `_` is never used — this is dead code that adds confusion. The real check is an `any()` over a single-element list `[1]` which always iterates once. The `or` inside the `any()` short-circuits on the first truthy condition per row but the conditions are not cleanly guarded against rows that have random words matching. For example, a metadata row with a campaign name containing "session" would trigger a false header match. The fallback (lines 229–232) is safer but also runs `'sessions' in joined and ('page' in joined or 'requ' in joined)` which could match a data row for a session URL like `/product/page/sessions-offer`.  
Suggestion: Require the header row to contain a specific set of 3+ recognized column names simultaneously (e.g. `'Requête'` AND `'Sessions'` AND `'Événements clés'`). Log the index of the detected header row for auditing.

---

## [scripts/sem_qv_attribution.py — calculate_sem_qv()] — normalize() diverges from pipeline's normalize()

Risk level: HIGH  
Line/section: Lines 194–198 (sem_qv_attribution's own `normalize()`), vs `pipeline/normalize.py` lines 4–9  
Issue: `sem_qv_attribution.py` defines its own local `normalize()`:
```python
def normalize(s):
    s = s.lower().strip()
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s
```
This is DIFFERENT from `pipeline/normalize.py`:
```python
s = re.sub(r'[^a-z0-9 ]', '', s)
```
The key difference: `\w` includes Unicode word characters (accented letters, underscore), while `[a-z0-9 ]` strips them. A keyword like `"greek yogurt"` normalizes identically in both, but any keyword containing an apostrophe (e.g. `"men's protein"`) or accented character would normalize differently. The QV SEM matching uses `row['norm_kw']` (normalized by pipeline's `normalize()`) to look up `kw_qv` keys (normalized by sem_qv_attribution's `normalize()`). Keywords with apostrophes, dashes, or special characters will fail to match, silently assigning 0 QV SEM instead of the correct value.  
Suggestion: The new `pipeline/sem_qv.py` must import and use `pipeline.normalize.normalize` exclusively. Delete the local copy.

---

## [scripts/sem_qv_attribution.py — write_to_masterlist()] — sheets_update_range() uses valueInputOption=RAW for QV SEM float values

Risk level: MEDIUM  
Line/section: Lines 142–161  
Issue: `sheets_update_range` always uses `?valueInputOption=RAW`. Writing a float like `0.7823` in RAW mode stores it as a raw value, which is correct. But the SEM Recommendation strings (`'Exclude'`, `'Keep-Active'`, `'Keep-Test'`) also go through the same function with RAW mode. This is fine for strings. The risk is the opposite: if a QV SEM value comes out as a Python `int` (e.g. `round(qv, 4)` when qv == 0 returns `0` but `round(0, 4)` returns `0` not `''`) — the code guards this with `qv_val = round(qv, 4) if qv else ''`, but `if qv` is `False` when qv == 0.0, so keywords in GA4 with attributed QV of exactly 0.0 get `''` written — correct. Keywords NOT in GA4 also get `''` — correct. The edge case is qv = 0.0001 (rounds to 0.0001, truthy) vs qv = 0.00001 (rounds to 0.0, falsy after `round(..., 4)` → becomes `''`). Keywords with true but sub-0.0001 QV SEM are silently zeroed.  
Suggestion: Use `round(qv, 2)` not `round(qv, 4)` to match meaningful precision, or use `qv_val = round(qv, 2) if qv is not None else ''` (checking for `None` not falsiness).

---

## [scripts/build_html_oikos.py — _n()] — Does not handle French number format from masterlist

Risk level: HIGH  
Line/section: Lines 570–577  
Issue: `_n()` does:
```python
f = float(str(v).replace(',', '.').strip())
```
This handles `"1,5"` → `1.5` (French decimal). But it does NOT strip space thousands separators before conversion. A value like `"32 395"` (French thousands) becomes `float("32 395")` which raises `ValueError` → returns `default=0`. Masterlist values written by `run_onesearch.py` are Python floats/ints stored directly (no formatting), so this is currently safe. But if a user ever manually edits a cell with French formatting, or if UNFORMATTED_VALUE is not used consistently, `_n()` will silently zero the value. More critically: `sem_qv_attribution.py` writes QV SEM as `round(qv, 4)` — a float — so no French formatting risk there. But the QS sheet (`QS_SHEET_ID`) is read with `sheets_get` which uses `UNFORMATTED_VALUE`, so numeric values come back as Python numbers not strings, and `_n()` gets an int/float as input, which `str(v).replace(',', '.')` handles fine. Risk is MEDIUM in current state but HIGH once French clients are added.  
Suggestion: Add space stripping to `_n()`: `str(v).replace('\xa0','').replace(' ','').replace(',','.')`. This matches the pattern in `normalize.py`'s `clean_num()`. Better: just import `clean_num` from `pipeline.normalize` instead of reimplementing.

---

## [scripts/build_html_oikos.py — build_data()] — spend_p1/spend_p4 detection checks only the first row

Risk level: MEDIUM  
Line/section: Lines 607–608  
Issue:
```python
spend_p1 = next((c for c in SPEND_P1 if any(c in r for r in rows[:1])), None)
```
`rows[:1]` is a list containing only the first row dict. If the first row has missing data and doesn't include the spend column (because it was a keyword with no SEM data), `spend_p1` will be `None` and `dr[31]` will be 0 for ALL rows including rows that do have spend data. The correct check is against the header row, not a data row.  
Suggestion: Replace with `spend_p1 = next((c for c in SPEND_P1 if c in headers_set), None)` where `headers_set` is built from the header row read at the top of `read_masterlist()`.

---

## [scripts/build_html_oikos.py — apply_brand()] — String substitutions are order-dependent and fragile for new brands

Risk level: HIGH  
Line/section: Lines 1575–1603  
Issue: `apply_brand()` does a series of `html.replace()` calls that assume specific Activia-template strings. These include:
- `'Activia'` → `'Oikos'` (line 1583): will also replace `'Activia'` inside JavaScript comments, CSS class names containing the word, or data values
- Color hex substitutions (`'#8b0000'` → brand color): these work only if the template uses those exact hex values — any case variation (`'#8B0000'`) would be missed
- `"'#B8001C'"` → `f"'{BRAND_COLOR}'"`: this is a bare string match inside JavaScript and will fail if the template uses double quotes, spaces, or the value is in a CSS property

The entire `apply_brand()` / `apply_english()` / `patch_onesearch_js()` chain is a chain of brittle find-and-replace operations. Any template update that changes one of these strings (even a whitespace change) silently produces broken HTML with no error.  
Suggestion: The new `scripts/build_html.py` must use a proper placeholder-based injection strategy. The template should have explicitly named substitution markers (`<!-- OS_BRAND_NAME -->`, `<!-- OS_BRAND_COLOR -->`) rather than relying on matching Activia-specific strings. All string substitutions should log how many replacements they made; zero replacements on an expected substitution should be a WARNING or ERROR.

---

## [scripts/build_html_oikos.py — replace_block()] — Regex for JS block replacement does not handle nested brackets

Risk level: MEDIUM  
Line/section: Lines 1557–1572  
Issue: The regex `(?:const|var)\s+VARNAME\s*=\s*(?:\[[\s\S]*?\]|\{[\s\S]*?\});` uses non-greedy `*?` for bracket content. If the JS block contains nested arrays `[[1,2],[3,4]]` or nested objects `{a: {b: 1}}`, the non-greedy match will stop at the FIRST `]` or `}` encountered, producing a partial match and corrupting the replacement. Example: `const DATA = [[1,2],[3,4]];` — the regex matches `const DATA = [[1,2]` as the variable block, leaving `,[3,4]];` as a trailing fragment.  
Suggestion: Write the DATA block once as a `<script>` injection after a clearly delimited placeholder comment (`<!-- OS_DATA_INJECT -->`) in the template, rather than regex-replacing existing JS variable declarations. Alternatively, use a properly bracket-aware parser.

---

## [scripts/build_html_oikos.py — MASTER_ID / MASTER_TAB] — Hardcoded sheet IDs remain in the HTML builder

Risk level: HIGH  
Line/section: Lines 22–24  
Issue: `MASTER_ID = '1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU'` and `MASTER_TAB = 'Listing'` are hardcoded at the top of `build_html_oikos.py`. This is precisely the bug class the rewrite is meant to fix. The new `scripts/build_html.py` must accept these from `brands/oikos-usa/config.json`. If the new script hardcodes them again, the multi-brand rewrite fails on its primary objective.  
Suggestion: The new `scripts/build_html.py` must read all sheet IDs, tab names, period labels, brand colors, and territory definitions from the config file passed as a CLI argument. Zero hardcoded Oikos values.

---

## [scripts/build_html_oikos.py — OS_RECO_FILTER / OS_RECO_MERGE_GROUPS / TERRITORY_DEFINITIONS] — Commentary and filter config not persisted across rebuilds

Risk level: HIGH  
Line/section: Lines 133–207  
Issue: `OS_RECO_FILTER`, `OS_RECO_MERGE_GROUPS`, and `TERRITORY_DEFINITIONS` are hardcoded Python dicts in the script. When the analyst rebuilds the HTML (e.g. after the next pipeline run), they must manually re-add any changes made to these dicts — or they are silently wiped. The same issue applies to `RECO_TINY_THRESHOLD` (line 125) and `COV_TARGET_BRAND`/`COV_TARGET_GENERIC` (lines 115–116). This was listed as a known issue (#48 in the 48-bug list) but is worth flagging explicitly: the new `brands/oikos-usa/content.json` must own all of this data, and the build script must read it from there on every run.  
Suggestion: Move `OS_RECO_FILTER`, `OS_RECO_MERGE_GROUPS`, `TERRITORY_DEFINITIONS`, thresholds, and period labels entirely into `content.json`. The new `scripts/build_html.py` must never have client-specific dicts hardcoded. On first run for a new brand, generate a starter `content.json` with empty dicts and warn the analyst to fill them.

---

## [pipeline/enrich.py — enrich_volumes()] — Writes `avg * 3` as synthetic quarterly volume regardless of actual quarter length

Risk level: MEDIUM  
Line/section: Lines 188–190  
Issue: When SE Ranking API returns average monthly volume, the script back-fills `Volume Q1 2026 = avg * 3` and `Volume Q4 2025 = avg * 3`. This is documented as a "3-month proxy" but it assumes both periods are exactly 3 months. If a future client uses a different period (e.g. a 4-month comparison or a single-month report), the synthetic quarterly volumes will be wrong, silently inflating the Average Search Volume calculation in `run_onesearch.py` (which divides by 6).  
Suggestion: The new `config.json` should specify `period_p1_months: 3` and `period_p2_months: 3`. The enrich step must multiply by the configured period length, not hardcode 3.

---

## [pipeline/enrich.py — _read_all_rows()] — Reads to column BE but masterlist may extend to BF or beyond

Risk level: MEDIUM  
Line/section: Line 82  
Issue: `_sheets_get(token, sheet_id, f"'{tab}'!A{start}:BE{start + 999}")` reads only to column BE (column 57). After `sem_qv_attribution.py` runs, column BF (`SEM Recommendation`) exists. Any enrich step that reads masterlist rows and needs to inspect column BF will miss it. Currently `enrich_volumes` doesn't need BF, but `enrich_taxonomy` might need to check the SEM Recommendation column to skip competitor keywords from re-classification. More importantly, if the masterlist grows beyond BF in the future, this read range will silently truncate the row.  
Suggestion: Read to a wider range (`BH` or `ZZ`) or read to the known last column dynamically from the header row.

---

## [pipeline/enrich.py — _claude_classify()] — Model ID `claude-haiku-4-5-20251001` is hardcoded and non-standard

Risk level: MEDIUM  
Line/section: Line 23  
Issue: `CLAUDE_MODEL = "claude-haiku-4-5-20251001"` — this model ID format (`4-5-20251001`) is not a recognized Anthropic stable model ID pattern. Standard IDs are `claude-3-5-haiku-20241022` or similar. If this is a typo, the API will return a 400 error. Currently the error is caught by the `except urllib.error.HTTPError` block and logged but not raised — the taxonomy enrichment silently produces no results for every batch, and the pipeline reports `0 cells updated` with no further diagnostic.  
Suggestion: The model ID should come from `config.json` or a central constants file. On first API call, validate that the response does not contain an `{"error": {"type": "invalid_request_error"}}` before proceeding with the batch loop.

---

## [pipeline/enrich.py — _claude_classify()] — Rate limiting is not handled for Claude API

Risk level: MEDIUM  
Line/section: Lines 258–276  
Issue: The retry loop sleeps 15s on HTTP 529 (overloaded) but uses the same `time.sleep(10)` for all other errors including 429 (rate limit). The Anthropic rate limit response includes a `retry-after` header that specifies the exact wait time. Ignoring it means the script may retry too quickly (getting another 429) or wait too long (wasting time). With 50 keywords per batch and potentially hundreds of batches, this could compound.  
Suggestion: Extract the `retry-after` header from 429 responses: `wait = int(e.headers.get('retry-after', 60))`. For 529 overload, exponential backoff is more appropriate than linear.

---

## [pipeline/match_ks.py — match_ks_keywords()] — Best KS match overwrites previous if score is strictly greater, but ties go to first seen

Risk level: LOW  
Line/section: Lines 47–49  
Issue: `if k not in best_ks or bs > best_ks[k]['sim']` — ties (same Jaccard score) are resolved by keeping the first KS keyword encountered, which depends on iteration order of the 14,273-row KS list. For exact duplicates in the KS (two different keywords that both have Jaccard 1.0 with a unified row), the first one wins arbitrarily. This is deterministic but undocumented.  
Suggestion: Document the tie-breaking rule. If the KS is sorted consistently, this is fine. Add a `--debug-matches` flag to the new `run_pipeline.py` that logs any ties for investigation.

---

## [pipeline/ingest_ga4.py — ga4_from_raw()] — events_col falls back to using key `''` (empty string) if no events column is found

Risk level: HIGH  
Line/section: Lines 64, 43  
Issue: In `norm_ga4_rows`, if `events_col` is `None` after the header scan (no recognized events column name found), line 43 uses:
```python
events = clean_num(row.get(events_col or '', 0))
```
`row.get('')` returns `None` (no key is an empty string), so `clean_num(None)` → `clean_num(0)` → `0.0`. Every row silently has 0 events. The function returns an empty dict `{}`. The pipeline proceeds with zero GA4 conversions. No warning is logged.  
Suggestion: If `path_col` is found but `events_col` is `None`, raise a warning immediately: `print(f"WARNING: GA4 events column not found. Available columns: {list(row.keys())[:10]}")`. Return `{}` only after logging. The new `pipeline/validate.py` should check that GA4 maps are non-empty before the write step.

---

## [run_onesearch.py — GA4 URL inference] — Slug-word matching uses `normalize()` which strips hyphens, creating false overlaps

Risk level: MEDIUM  
Line/section: Lines 553–556  
Issue:
```python
def _slug_words(url_path):
    p = re.sub(r'^/(en-us|fr-ca|en-ca|fr-fr)/', '/', url_path)
    p = re.sub(r'^/(products?|yogurt|category|blog|recipes?)/', '/', p)
    return set(normalize(p.strip('/').replace('-', ' ').replace('/', ' ')).split())
```
`normalize()` strips all non-alphanumeric characters. So `"/triple-zero-pro"` becomes `"triple zero pro"` → `{'triple', 'zero', 'pro'}`. A keyword `"triple zero protein shake"` also has words `{'triple', 'zero', 'pro...'}`. But `normalize("pro")` = `"pro"` and `normalize("protein")` = `"protein"` — these won't overlap, so this specific case is fine. The real risk is short slugs: `"/greek"` becomes `{'greek'}`, and a single-word slug will match any keyword containing `'greek'` with score 1/max(len_kw, 1) which could meet the 0.5 threshold for a short keyword. The `len(kw_words) < 2` guard (line 565) helps but only for single-word keywords.  
Suggestion: Require overlap score ≥ 0.6 (not 0.5) for inferred GA4 URL matches, or require `overlap >= 2` even for short slugs. Log all inferred URL matches with their score for manual review.

---

## [run_onesearch.py — _run()] — Token is refreshed mid-pipeline but the refresh can fail silently

Risk level: MEDIUM  
Line/section: Lines 658–659, 720, 758  
Issue: `token = get_token(env)` is called three times during the pipeline run (before write, before formula write, before enrichment). `get_token()` makes an HTTP call with no retry logic and no timeout — `urllib.request.urlopen(req)` with no timeout. If the Google OAuth endpoint is momentarily unavailable, this raises an unhandled exception that propagates up and kills the pipeline mid-write, leaving the masterlist in a partially-written state (data rows written, ARRAYFORMULA cells not yet cleared).  
Suggestion: Add retry logic with exponential backoff to `get_token()`. Add a timeout (e.g. 30s). Consider wrapping the token refresh in a try/except that retries 3 times before aborting.

---

## [run_onesearch.py — _run()] — Log file Tee class replaces sys.stdout but sys.stderr still goes to terminal only

Risk level: LOW  
Line/section: Lines 334–345  
Issue: The `_Tee` class only wraps `sys.stdout`. Any exception tracebacks, which Python writes to `sys.stderr`, will appear on the terminal but NOT in the log file. If the pipeline crashes mid-run, the log file will show all output up to the crash but not the traceback itself, making post-mortem debugging harder.  
Suggestion: Also tee `sys.stderr` in the `_Tee` setup: `sys.stderr = _Tee(sys.__stderr__, _log_fh)`. Restore both in the `_log_fh.close()` block.

---

## [scripts/build_html_oikos.py — inject_reco_filter()] — Silently skips injection if template anchor strings change

Risk level: MEDIUM  
Line/section: Lines 1444–1448, 1466–1469  
Issue: Both injection points check for exact anchor strings and print a WARNING if not found, but continue execution anyway. The result is an HTML file where `RECO_STATUS` is not injected — the recommendations table renders but all rows default to 'active' with no filtering. The dashboard is delivered to the client with invisible bugs (all filtered rows visible).  
Suggestion: Change these from `print('  WARNING: ...')` to `raise RuntimeError(...)` so the build fails loudly rather than producing silently incorrect output. Or at minimum: count total `'data-status='` occurrences in the final HTML and warn if < expected count.

---

## [scripts/build_html_oikos.py — build_sqr_data() — CPC Q4 is always 0]

Risk level: MEDIUM  
Line/section: Line 551  
Issue: The SQR_ACTIVIA row has 25 fields. Field `[21]` (CPC_Q4) is hardcoded to `0`:
```python
0,        # [21] CPC_Q4
```
There is no `CPC avg. SEM Q4 2025` or similar column being read. The `cpc_q1` is correctly calculated from `CPC avg. SEM Q1 2026` / `CPC moy. SEM Q1 2026`, but Q4 CPC is silently zeroed. The SQR tab in the HTML dashboard will show Q4 CPC as 0 for every keyword, which is misleading.  
Suggestion: Add `cpc_q4 = _n(r.get('CPC avg. SEM Q4 2025') or r.get('CPC moy. SEM Q4 2025', 0))` and use it at position [21]. If the column doesn't exist in the masterlist, it returns 0 via `_n()` — the behavior is the same as now, but the intent is explicit and future masterlist additions will work automatically.

---

## [New file — brands/oikos-usa/config.json] — Missing: GA4 Ads sheet ID and tab name for sem_qv

Risk level: HIGH  
Line/section: N/A — file not yet written  
Issue: `sem_qv_attribution.py` currently hardcodes `GA4_ADS_FILE_ID = "1Z6QO82Gc3itROgnvqhBP2aoGTf4pIO0WLD-Kkbofb1w"` and resolves the tab name at runtime by reading the first sheet. If `brands/oikos-usa/config.json` doesn't include this sheet ID and the tab name (or the runtime resolution approach), the new `pipeline/sem_qv.py` will either hardcode it (reintroducing the bug) or fail to find the source.  
Suggestion: config.json must include a `"ga4_ads": {"sheet_id": "...", "tab": null}` entry where `null` triggers runtime tab resolution. Document the `null` convention in the config schema.

---

## [New file — pipeline/validate.py] — No existing validation layer means the new one has no baseline to test against

Risk level: MEDIUM  
Line/section: N/A — file not yet written  
Issue: There is currently zero validation between pipeline steps. The new `validate.py` will be the first. The risk is that it will be written conservatively (only failing on `None` data) and will miss the silent-zero cases that are the real production bugs. For example: a run where all 1,240 unified rows have `Average Search Volume = 0` (because GSC date columns drifted) would currently produce a masterlist that looks complete but has zeroed Coverage columns — this is not an exception, it's just wrong data.  
Suggestion: `validate.py` must include statistical sanity checks, not just null checks:
- GSC row count must be > 100 (empty = column name mismatch)
- SQR row count must be > 50
- At least 60% of unified rows must have `Average Search Volume > 0`
- At least 10% of unified rows must have `Clics SEO Q1 2026 > 0`
- GA4 checkout_map and offline_map must each have > 5 entries
- SE rows must have > 100 entries
- sem_qv dict (if run) must sum to > 0

---

## [New file — pipeline/utils.py] — Risk of re-duplicating Sheets helpers already in run_onesearch.py and enrich.py

Risk level: MEDIUM  
Line/section: N/A — file not yet written  
Issue: `run_onesearch.py` and `pipeline/enrich.py` and `scripts/sem_qv_attribution.py` all define their own versions of `sheets_get`, `sheets_batch_update`, `_col_letter`, `load_env`, `get_token`. If `pipeline/utils.py` is created but the existing files are not refactored to import from it, there will be four divergent implementations of the same helpers. The version in `sem_qv_attribution.py` uses `sheets_update_range` (PUT, single range) while `run_onesearch.py` uses `sheets_batch_update` (POST, multiple ranges). These are genuinely different APIs but easy to confuse.  
Suggestion: The new `pipeline/utils.py` must be imported by ALL callers — not just new files. The old files must be refactored. Leaving parallel implementations is worse than not having utils.py at all.

---

## [pipeline/enrich.py — _ser_fetch() and _ser_fetch_monthly()] — Same SE Ranking API called twice in sequence, both hitting 500-keyword batches

Risk level: MEDIUM  
Line/section: Lines 93–119, 279–305  
Issue: `enrich_volumes` and `enrich_monthly_volumes` both call the SE Ranking API with the same keyword lists, making two full passes through the API. The API endpoint (`https://api.seranking.com/v1/keywords/export?source=us`) is the same for both calls. The responses contain monthly volume data (`history_trend`) in both calls — the first call already has the monthly data but discards it (it only extracts the average). This doubles API cost and time for no benefit.  
Suggestion: Call the SE Ranking API once, extract both the average and the per-month breakdown in a single pass. The new `pipeline/utils.py` SE Ranking helper should return `{keyword: {avg: float, monthly: {month: int}}}`.

---

## [All files — .env file path hardcoded as absolute path to one user's machine]

Risk level: HIGH  
Line/section: `run_onesearch.py` line 34, `scripts/build_html_oikos.py` line 21  
Issue: `ENV_FILE = "/Users/carlaklaasen/claude_code/.env"` — this is an absolute path to one person's machine. If the pipeline is run from any other user account, Docker container, CI environment, or even a renamed home directory, the path will not resolve and `load_env()` will crash with `FileNotFoundError`. There is no fallback to environment variables or relative path.  
Suggestion: The new `run_pipeline.py` must use: `os.environ.get('ONESEARCH_ENV_FILE')` first, then fall back to a path relative to the repo root (`os.path.join(os.path.dirname(__file__), '..', '.env')`), then fail with a clear error. Never use an absolute path with a username.

---

## [scripts/sem_qv_attribution.py — normalize()] — `\w` matches underscore, which is not present in keyword text but could cause issues with special tokens

Risk level: LOW  
Line/section: Line 197  
Issue: `re.sub(r'[^\w\s]', '', s)` keeps underscores (`\w` includes `_`). While keywords don't typically contain underscores, GA4 query strings (if accidentally included) might. More importantly, keeping `\w` means accented French characters (é, è, à) survive normalization in sem_qv_attribution but are stripped in pipeline/normalize.py. See the HIGH-risk normalize divergence note above — this is the root cause.  
Suggestion: See note on normalize divergence above. Use a single shared normalize function.

---

## [scripts/build_html_oikos.py — _fmt_num()] — Returns string but callers may pass the result to arithmetic

Risk level: LOW  
Line/section: Lines 655–664  
Issue: `_fmt_num()` returns a string (`'1.4K'`, `'32M'`, `'999'`). The function is only called in f-strings for display. However, `_fmt_cov()` at line 696 takes a float `v` and does `float(v) * 100`. If someone accidentally passes a `_fmt_num()` result to `_fmt_cov()`, `float('1.4K')` raises ValueError → unhandled, crashing the build. The functions have similar signatures and sit near each other, creating a copy-paste trap.  
Suggestion: Type-annotate both functions. Add a `# returns: str (display only, not arithmetic-safe)` comment to `_fmt_num`.

---

*End of skeptic notes. Total issues: 28. Critical path items for the rewrite: ingest.py parameterization (HIGH ×3), normalize() divergence between sem_qv_attribution and pipeline (HIGH), column AC conflict between run_onesearch and sem_qv (HIGH), config.json completeness requirements (HIGH ×4), validate.py statistical sanity checks (MEDIUM), utils.py import consolidation (MEDIUM).*
