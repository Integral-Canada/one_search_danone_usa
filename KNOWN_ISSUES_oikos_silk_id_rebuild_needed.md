# Known issues — Oikos / Silk / International Delight need a rebuild + re-run

**Found:** 2026-10-03, while onboarding Activia USA and validating its dashboard build.
**Status:** Fixes for the root causes are already implemented on this branch (`sem-qv-p2-and-conv-label-fix`). Oikos, Silk, and International Delight have **not** been rebuilt/re-run against these fixes yet — explicitly put on hold per user direction (2026-10-03) while other work continues. This file is the reminder to come back to it.

---

## 1. Dashboard HTML rebuild needed (fast, safe — no live client data touched)

All three brands' currently-published dashboard HTML files were built from the same broken `examples/activia_ca_onesearch_dashboard.html` reference template and carry two bugs, now fixed in `scripts/build_html.py` / `scripts/build_html_oikos.py`:

- **Fabricated hero-chip numbers.** The template had literal stale Activia-Canada placeholder text ("Canadian Market", "2 070 priority keywords", "2 390 kw — Position SEO", "693 keywords — Quality Score", "SQR data coming soon", a stale "April 2026" date) that was never replaced with real per-brand data for ANY brand before today. Fixed by computing real values (`HERO_TOTAL_KW`, `HERO_POS_SEO_KW`, live QS count, `MARKET_LABEL`) in `build_html.py`'s `main()` before `apply_brand()` runs.
- **~15,000-line orphaned dead data block.** The raw template has a large duplicate/orphaned copy of real Activia Canada SQR/SEM data (French text, `CAN_EDP_ACTIVIA_...` campaign IDs) sitting with no enclosing `<script>` tag, trailing after the last real `</script>` all the way to EOF. `truncate_after_last_script()` already existed to strip exactly this, but ran too late in the pipeline (after later steps appended new script blocks past the dead content, so "the last `</script>`" no longer pointed to the right place). Fixed by calling it immediately after loading the template, before any other processing step.

**Confirmed present in all three existing files** (checked directly, read-only, via a dedicated audit agent on 2026-10-03):

| Brand | File | Size | Last built |
|---|---|---|---|
| Oikos USA | `dashboards/oikos-usa/oikos-usa_onesearch_dashboard.html` | ~5.95 MB | 2026-10-01 |
| Silk | `dashboards/silk/silk_onesearch_dashboard.html` | ~8.35 MB | 2026-10-01 |
| International Delight | `dashboards/international-delight/international-delight_onesearch_dashboard.html` | ~9.59 MB | 2026-10-01 |

Compare to Activia's rebuilt-and-fixed file: 963 KB.

**Fix:** re-run `python3 build_dashboard.py --brand <handle>` for each of `oikos-usa`, `silk`, `international-delight`. This only reads each brand's already-populated Masterlist Google Sheet — it does not touch live client data, so this part is low-risk and can be done independently of item 2 below.

---

## 2. Masterlist pipeline re-run needed (slower, touches live client Google Sheets)

Separate, more serious finding: `pipeline/ingest_ga4.py`'s `norm_ga4_rows()` / `_normalize_path()` (and `pipeline/ingest.py`'s `norm_se()`) had a `.rstrip('/')` bug — `'/'.rstrip('/')` produces `''`, not `'/'`, so **every homepage conversion row (bare `/` or `/?query-string`) was silently dropped** by the `if not path: continue` check in every caller. Fixed via `_normalize_path()` (preserves the homepage root instead of collapsing it to empty).

This was flagged early in the Activia onboarding as a theoretical risk for the other three brands but never actually verified against their real data — verified today (2026-10-03) by sampling each brand's real, current GA4 Ads export directly:

| Brand | Missing key events (homepage rows) | % of real total | Last known pipeline run |
|---|---|---|---|
| International Delight | 6,755 | 4.63% | 2026-09-23 (predates fix) |
| Oikos USA | 513 | 3.90% | no `logs/pipeline_oikos-usa_*.log` found — can't confirm ingestion date |
| Silk | 243 | 0.43% | 2026-09-24 (predates fix) |

All three real export shapes confirmed to contain the vulnerable row shape — this is not theoretical, it's present in their live data right now. Their live Masterlist "Listing" tabs are very likely undercounting homepage SEO/SEM conversions by these amounts.

**Fix:** re-run `python3 run_pipeline.py --brand <handle>` for each of `oikos-usa`, `silk`, `international-delight` to regenerate correct homepage conversion totals, **then** rebuild the dashboard again afterward so it reflects the corrected numbers (item 1's rebuild is necessary either way, but should happen again after this fix for these three brands specifically).

**Priority order:** International Delight (highest exposure) → Oikos (unconfirmed ingestion date, treat as stale) → Silk (smallest but still real, confirmed, nonzero loss).

---

## Do NOT do until the user explicitly says go
Per explicit user direction on 2026-10-03: hold off on both the dashboard rebuilds and the pipeline re-runs for these three brands for now. This file exists so the next session picks this back up instead of losing track of it.
