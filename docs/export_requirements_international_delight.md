# Export Requirements — International Delight USA

Period: Q1 2026 (January 1 – March 31, 2026) vs. Q4 2025 (October 1 – December 31, 2025) — matches the header row already set on the destination Masterlist.

## Still needed (none of these exist yet for ID)

1. GSC exports for Q1 vs Q4
   - Export 1 name: `gsc_export_queries_international_delight.csv`
   - Export 2 name: `gsc_export_pages_international_delight.csv`
2. Google Ads Quality Score Report
   - Name: `quality_report_international_delight.csv`
3. Google Ads Account-level Search Query Report
   - Name: `account_level_sqr_report_international_delight.csv`
4. SE Ranking export for the most recent complete month (use whatever month is current when you pull this — it's only used for average search volume)
   - Name: `se_ranking_<month>_international_delight.csv`
5. GA4 conversion exports — filtered to the same two Mikmak events used for Oikos
   - **Verify first**: confirm International Delight actually uses Mikmak (shoppable media / where-to-buy) — it's a different product category (coffee creamer vs. yogurt) and may use a different retail-media platform or different event names.
   - If confirmed: page-level exports for `mikmak_checkout` and `mikmak_click_offline_store`, one per period (Q1 2026 + Q4 2025 — Oikos was missing the Q4 file, don't repeat that gap)
6. GA4 landing-page session exports, one per period (`Page_de_destination` reports)
7. GA4 Google Ads Sessions export — **new as of Q1 2026, required for the SEM QV methodology**
   - Tab name pattern: `Campagnes Google Ads: Requête Google Ads associée à cette session`
   - Required columns: search query, landing page + query string, `Sessions`, `Événements clés` (Key Events = Qualified Visits)
   - Feeds `pipeline/sem_qv.py` for LP-rate attribution — same as Oikos's `ga4_ads_file_id`

## Already confirmed

- **Keyword Study**: `International Delight US - Keyword Study`
  - Sheet ID: `17XunXHg5N0xygZlkd_2wVk7-iZbpzsoJPo2CdgUiXxg`
  - Tab: `Keyword study - US`
  - Note: two other ID keyword study sheets exist in Drive (a Nov 2025 dated version and a March 2026 copy) — this is the one confirmed as canonical; the others are stale/working copies, not sources.
- **Output Masterlist**: `MASTERLIST - INTERNATIONAL DELIGHT OneSearch`
  - Sheet ID: `1bVEwAdCn4NoAfsdN__hm4LO6lhGEnRE-aMH_WS3Jo14`
  - Tab: `Listing`
  - Header row already exists but was copied from the Oikos template — `Yogurt types` and other Oikos-specific taxonomy tag columns will need renaming once the ID territory taxonomy is drafted.
- **Non-branded regex**: already registered in the shared source-config sheet (`DANONE USA - Overview` tab), column `International Delight`.

## Outstanding manual step

The shared source-config sheet (Sheet ID `1o526Qv4UzP_Qfe-cjrfvcA7jRUi6zUtd9Ecp2WPMIhQ`, tab `One Search `) already has a row block for International Delight, but every export cell in it (GSC Export, Quality Report, Account Level SQR Report, Keyword study, SE Ranking, Conversions ×2, Landing page ×2, Google Ads Data) is still blank. As each export above is pulled, its Sheet ID + tab needs to be added to that row block — `run_pipeline.py --brand international-delight` reads from there at runtime, it doesn't read `config.json` for these.
