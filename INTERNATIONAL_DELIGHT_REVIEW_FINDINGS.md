# International Delight — dashboard review findings & next actions

**Started:** 2026-10-04, in response to the client account lead's (the user's boss's) 7-point feedback on the published ID dashboard, plus his own hand-edited copy of the dashboard and a one-pager summary.
**Status:** Review/report only. Nothing has been changed in the ID Masterlist, config, or dashboard HTML as a result of this review. One shared-code change (the SE-Ranking-gap footnote, see below) has been made but not yet applied via a rebuild.

**Inputs reviewed:**
- Boss's edited copy: `international-delight_onesearch_dashboard_thomas` (Drive id `1y-f8i_ZXRwCJNrsslgCwOpmwxGbQOs3G`), 3.44 MB — compared structurally against git's `dashboards/international-delight/international-delight_onesearch_dashboard.html` (10.06 MB). **Not a bug-fixed rebuild** — it contains the exact same unfixed placeholder bugs as git's version (literal "Canadian Market," "2 070 priority keywords," "2 390 kw — Position SEO," uncorrected red `--brand-hover:#9A0017`). Per user instruction: his file wins on business/data-content disagreements; known template/technical bugs still get fixed via our pipeline, not copied from his file.
- One-pager: `InternationalDelight_OneSearch_OnePager.html` (Drive id `1UM4Zmf98kgP9Vqwa8w5QMise7037kG3d`) — used to directly confirm points 1 and 2 below in the account lead's own words.

---

## The 7 points, point by point

**1. Period covered.**
✅ Confirmed: Q2 2026 vs Q1 2026, both in the real data and the one-pager's own footer text ("Q2 2026 vs Q1 2026 · International Delight USA · October 2026"). No fix needed.

**2. Coverage definition (average monthly volume vs. 3x quarterly column).**
✅ Confirmed in code: `scripts/build_html_oikos.py` computes `cov = _cov(os_clicks, avg_volume)` where `avg_volume` sums the real `"Average Search Volume"` column. The 3x quarterly columns (`Volume Q1 2026`/`Volume Q4 2025`) are tracked separately but never used in the coverage calculation. No fix needed.

**3. Search volume gaps.**
- *Clicks > volume* (66 keywords, 6,877 of 44,754 clicks — exact match to boss's count): confirmed via real Masterlist read. Root cause: GSC/SQR clicks roll up multiple close-variant real search queries into one keyword bucket, while SE Ranking's volume reflects only that single literal string (e.g. "paris hilton creamer": 182 vol vs 1,033 clicks, confirmed exact). Not a bug — needs human judgment, not a technical fix.
- *Zero/blank volume with real clicks* (1,127 keywords, 8,669 clicks, ~19.4% — matches boss's "~19%"): confirmed via the real pipeline log (`logs/pipeline_international-delight_2026-09-23_23-05-46.log`) — SE Ranking's API simply returned no data for these (1,034 of 2,161 rows needing volume got data; 1,127 didn't). These are overwhelmingly very recent launch/collab terms (Paris Hilton flavor, cotton candy cold foam, raspberry champagne, sweet and spicy) that SE Ranking's index hasn't caught up to yet. Known class of SE-Ranking-coverage-gap, not a bug.
- **Fix implemented 2026-10-04:** per user request, both scenarios above are now automatically flagged on the dashboard with a red `*` next to the keyword in the Top-Keywords table, plus one explanatory footnote per territory panel (shared code, `build_html_oikos.py::build_territory_panel()` — see `ACTIVIA_DASHBOARD_PORTBACK_TRACKER.md` item 4). Not yet applied to ID's live dashboard — requires a rebuild, which is on hold.

**4. SEM qualified visits (QV) attribution.**
Counts confirmed exactly against real data: of 294 keywords with ≥10 SEM clicks (Q2 2026), QV > SEM clicks on 108, QV = 0 on 28.
Mechanism traced in `pipeline/sem_qv.py::calculate_qv_sem()`: QV is a landing-page-pooled conversion rate computed from **GA4 sessions** (a different system than "SEM clicks," which comes from the Google Ads SQR export) — `attributed_QV = (keyword's share of LP sessions) × (LP's total GA4 key_events)`. It is never capped at that keyword's own click count, so QV > clicks is possible by design whenever GA4 session counts and Ads click counts diverge for a keyword (a common, expected divergence between two different measurement systems). QV = 0 cases likely reflect a GA4 query-text match failure for that keyword/landing page, not necessarily zero real conversions.
**This blocks the pause test as the boss said.** Recommended options (business decision, not yet actioned):
  - *Fast/safe (recommended):* add a confidence/caveat label to QV output noting it's page-attributed, not click-capped, and exclude flagged keywords from pause-test eligibility until the business accepts or rejects this methodology.
  - *Slower:* rework attribution to match GA4 sessions to a keyword by query text only (no LP pooling) — a real methodology change to shared pipeline code affecting every brand, not a quick fix.
**This is shared pipeline code — flagged in `ACTIVIA_DASHBOARD_PORTBACK_TRACKER.md` as applying to Activia too.**

**5. SEO QV = 0 in the previous period (every keyword shows "NEW").**
Confirmed: `Conversions SEO Q1 2026` is 0/blank for all 2,407 rows, with zero exceptions — even on massive-click rows. Root cause confirmed directly from the pipeline log: the previous-period ("...Q1 2026") GA4 conversion exports for "Checkout" and "Click Offline Store" were never registered in the source registry for this brand — only current-period rows exist. The pipeline silently skips (`GA4 '...': not configured, skipping`) rather than hard-stopping or flagging it on the dashboard — same class of problem as the existing GSC-403-hard-stop rule.
**Concrete fix available, not yet actioned (touches live registry + requires a pipeline re-run):** register the missing previous-period GA4 conversion sources for International Delight in the source registry, then re-run ingestion. Also recommended: add a hard-stop/warning so a missing previous-period source surfaces visibly instead of silently rendering "NEW" everywhere.
**Flagged in `ACTIVIA_DASHBOARD_PORTBACK_TRACKER.md`** — worth verifying Activia's own registry has previous-period rows for every GA4 conversion source it uses.

**6. Silk brand keyword "silk 官网" (Silk-specific).**
Not applicable to International Delight — deferred to the Silk review pass.

**7. Keyword list Excel files (pause test, direct exclusion, QV to validate).**
No file named exactly `Recommandation_Pause_SEM_Produit_ID.xlsx` exists locally or in Drive. What exists is `Recommandation_Pause_SEM_Brand_ID.xlsx` ("Brand," not "Produit") — found both locally (`~/Downloads/`) and in Drive (file id `15jhrhh0sfJv-K8qWHXJDgKfqXTcCTcsV`, modified 2026-06-17) and as a native Sheet (id `1noT2xq9RD80qAbAX1WmSoUQq6nXa6_lBgdngMVmnAig`). A Canada counterpart exists under a different owner — do not conflate. **Pending confirmation from the user/boss on which file he actually meant** before opening/validating its contents.

---

## Bonus finding (not one of the 7)
Four columns in the live Masterlist ("Clics SEO Q1 2026", "Clics SEM Q1 2026", "Impr. SEO Q1 2026", "Impr. SEM Q1 2026") are formatted as **percent** instead of number in the Google Sheet — a real value like 2,469 displays as "246900%" to anyone opening the raw sheet. Underlying values are correct; this is purely a cell-display bug. Cheap, safe fix (Sheets API cell-format change, no data touched) — offered to the user, not yet actioned pending their go-ahead.

---

## Outstanding / not yet done
- Rebuild ID's dashboard with all known fixes (hero chips, colors, orphaned-data truncation, SE-gap footnote, export-button + input-box removal) — **on hold**, review-only for now per user instruction.
- Register missing Q1 2026 GA4 conversion sources for ID and re-run ingestion (point 5) — **on hold**, not yet actioned.
- Confirm Excel filename with the boss (point 7) — **blocked on user input**.
- Fix the percent-formatting cosmetic bug — **offered, not yet actioned**, pending user go-ahead.
- Silk feedback review (point 6, plus Silk's own version of points 1–5, 7) — in progress, see `SILK_REVIEW_FINDINGS.md` once created.
