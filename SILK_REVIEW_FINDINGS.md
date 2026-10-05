# Silk — dashboard review findings & next actions

**Started:** 2026-10-04, same methodology as `INTERNATIONAL_DELIGHT_REVIEW_FINDINGS.md`, in response to the same 7-point feedback (points 1, 2, 6, 7 are Silk-specific or Silk's version of a shared point; 3, 4, 5 mirror ID's investigation).
**Status:** Review/report only. Nothing has been changed in the Silk Masterlist, config, or dashboard HTML. One shared-code change (the SE-Ranking-gap footnote) was already made for both brands, not yet applied via rebuild.

**Inputs reviewed:**
- Boss's edited copy: `silk_onesearch_dashboard_thomas` (Drive id `1c6TTVYnQictl-STt3G5zJxQvcn8KO0Fb`), 2.85 MB — compared against git's `dashboards/silk/silk_onesearch_dashboard.html` (8.76 MB). **Same pattern as ID: not a bug-fixed rebuild** — identical unfixed placeholder bugs present (Canadian Market, stale hero numbers, uncorrected red `--brand-hover:#9A0017`). Business/data content from his file wins on disagreement; known template/technical bugs still get fixed via our pipeline.
- One-pager: `Silk_OneSearch_OnePager.html` (Drive id `16PxOZkgRI6-nqz5hMDa7FFA51eO7zepw`) — confirms period (Q2 2026 vs Q1 2026) and coverage definition ((SEO+SEM clicks)/avg monthly volume), same as ID. 2,858 keywords, 8 territories, overall coverage 3.2%→2.4% (-0.8pp). BRAND territory: 58.2%→42.8% (-15.4pp) — the single biggest territory loss, see point 4.

---

## The 7 points, Silk's version

**1. Period covered.** ✅ Confirmed Q2 2026 vs Q1 2026. No fix needed.

**2. Coverage definition.** ✅ Confirmed — same code path as ID, average monthly volume is the denominator, not the 3x quarterly column. No fix needed.

**3. Search volume gaps.**
- *Clicks > volume:* 143 keywords, 11,125 clicks (boss said 142/11.1K — within 1 row). "silk protein milk" 250 vol vs 592 clicks confirmed exact. Mostly literal "silk X" product terms where GSC/SQR clicks roll up close query variants into one bucket. Same as ID — needs human judgment, not a fix.
- *Zero/blank volume with real clicks:* 993 keywords, 21,277 clicks (30.7% — boss said 990/21.2K/31%, matches). **Important: this bucket is a mix of two different things for Silk** — most rows are the same ordinary SE-Ranking-indexing-lag class as ID (new/niche terms like "silk kids," "silk cold foam"), but the single worst offender, **"silk 官网" at 13,025 clicks, is not a volume-lag case at all — it's a real merge bug, see point 4.**
- **Recommended fix:** the asterisk/footnote feature already built for ID applies here too (shared code) — will auto-flag both sub-cases once Silk is rebuilt. But "silk 官网" needs the real fix below, not just a footnote.

**4. "silk 官网" — the headline finding. This is a real pipeline bug, not a business judgment call.**
Confirmed exact numbers (13,025 clicks Q2, 18,271 Q1, blank volume, 100% SEO). But the live GSC query itself only has 10,181 clicks (Q2) — the Masterlist row is inflated beyond the literal query.
**Root cause confirmed:** `pipeline/normalize.py::normalize()` strips ALL non-ASCII characters (`re.sub(r'[^a-z0-9 ]', '', s)`). This means "silk 官网", "silk官网", and every other CJK-brand-nav variant (~10,407 combined Q2 clicks) **and the separate, legitimate bare English query "silk"** (2,301 Q2 clicks) all normalize to the identical key "silk" and get silently merged into one Masterlist row. 10,407 + 2,301 ≈ 12,708 ≈ the row's 13,025.
**Country breakdown (pulled live from GSC, not in the pipeline's own schema) is the smoking gun:** for the "silk 官网" query alone, only ~20% of clicks are from the USA — the rest is China, Hong Kong, Taiwan, Singapore, Japan, Korea. The bare "silk" query, by contrast, is ~70% USA. So this one Masterlist row blends real international (non-US-market) brand-navigational traffic with real US brand traffic, merged by a normalization bug — not a scraper, not fake traffic, just wrongly bucketed.
**Why this matters:** this single row is called out in the one-pager itself as the main driver of BRAND territory's -15.4pp coverage drop, the biggest territory loss on the whole dashboard.
**Recommended fix (two parts):**
  - *Code fix (shared, affects every brand):* `normalize()` should stop stripping all non-Latin script characters — strip punctuation/symbols only, preserve letters from any script, so "官网"-containing queries stop colliding with unrelated ASCII keywords. This needs testing against the fuzzy-matching step that also depends on `normalize()` before shipping, since it's shared code used by every brand's pipeline run.
  - *Re-run required:* once fixed, Silk's Masterlist needs re-ingestion so "silk 官网" splits back into its real separate rows.
  - *Business decision after the fix (not mine to make):* once split, should the CJK-market navigational row even count toward a US-market BRAND coverage metric? That's a call for the client side, informed by the country breakdown above.
**Not yet actioned** — this touches live Masterlist data via a re-run, so it's a "say go" item. **Flagged in `ACTIVIA_DASHBOARD_PORTBACK_TRACKER.md`** — every other brand's Masterlist should be checked for the same collision pattern (any keyword containing non-ASCII characters) before assuming this is Silk-only.

**5. SEM QV attribution.**
Counts confirmed exactly: of 282 keywords with ≥10 SEM clicks, QV > clicks on 52, QV = 0 on 69. Same shared mechanism as ID (`pipeline/sem_qv.py` — landing-page-pooled GA4-session attribution, never capped at the keyword's own click count). Same recommendation as ID: fast/safe caveat-label option now, methodology rework as a separate project if the business needs click-capped keyword-level QV. Side note: none of Silk's 3 logged pipeline runs show `run_sem_qv()` actually completing cleanly (two predate GA4 Ads config, one crashed on API 401s) — yet the sheet has real QV values, meaning it was run standalone at some point outside the logged runs. Not a blocker, just means there's no clean log trail for exactly when/how the current numbers were produced.

**6. SEO QV = 0 in previous period.**
Confirmed same root cause as ID: blank for all 2,863 rows despite 1,213 rows having real Q1 SEO clicks. Pipeline log confirms the same "not configured, skipping" pattern for Checkout/Click-Offline-Store Q1 2026 GA4 sources — never registered for Silk either. (Contrast: SEM QV's own Q1 column IS populated, since that comes from the separate GA4-Ads-Compare-export mechanism, not the SEO conversions registry — so it's specifically the SEO-side previous-period sources missing.) Same concrete fix as ID: register the missing registry rows, re-run ingestion.

**7. Keyword list Excel file.**
Same naming mismatch as ID: no `Recommandation_Pause_SEM_Produit_Silk.xlsx` exists. Found `Recommandation_Pause_SEM_Brand_Silk.xlsx` instead (local Downloads copy + Drive id `18t_K6-9q0baHV8stN_T3OQjc3f6BBbHl`, plus a near-duplicate re-upload not yet looked at). A much larger Canada counterpart exists under a different owner (Alix Fruchet) — do not conflate. Pending confirmation from the user/boss on which file he meant, same as ID.

---

## Outstanding / not yet done
- Fix `pipeline/normalize.py`'s Unicode-stripping bug (point 4) and re-run Silk's ingestion — **highest-value pending item**, not yet actioned, needs user go-ahead (touches live data, shared code).
- Register missing Q1 2026 GA4 conversion sources for Silk and re-run (point 6) — not yet actioned.
- Confirm Excel filename with the boss (point 7) — blocked on user input, same question as ID.
- Rebuild Silk's dashboard with all known fixes (hero chips, colors, orphaned-data truncation, SE-gap footnote, export-button + input-box removal, once rebuilt) — on hold, review-only per user instruction.
- Audit Oikos/ID/Activia Masterlists for the same non-ASCII normalize() collision pattern before assuming it's Silk-only.
