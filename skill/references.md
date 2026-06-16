# REFERENCES - COLUMNS

Use this document for clarification on how to populate each column in the [client] Masterlist: 

**Row anchor: one row per unique search term from GSC or SQR (query-anchored, NOT KS-anchored).
KS taxonomy (TOPICS/CATEGORY/SUB-CATEGORY/volumes) and SE Ranking data are enriched onto each row via trigram match.**

**Trigram matching direction:** Index is built on the ~1,240 unified GSC+SQR queries. KS keywords (14,273) and SE Ranking keywords are each iterated through this small index. Results are pivoted back to the unified queries (best KS match per query). This avoids OOM — building the index on KS produces an ~11.5× larger object.

---

## Identity & Classification (cols A–E)

1. (col = A) LANG: Language of the keyword — from Keyword Study match.
2. (col = B) KEYWORD: The actual search term from GSC (Top queries) or SQR (Search term). NOT the KS keyword.
3. (col = C) TOPICS: From Keyword Study — matched via trigram to the GSC/SQR search term.
4. (col = D) CATEGORY: From Keyword Study — matched via trigram to the GSC/SQR search term.
5. (col = E) SUB-CATEGORY: From Keyword Study — matched via trigram to the GSC/SQR search term.

## SE Ranking (cols F–G)

6. (col = F) POSITION SE RANKING: From SE Ranking — se_position
7. (col = G) AVERAGE SEARCH VOLUME: From SE Ranking — se_search_vol

## Search Volume by Period (cols H–I)

8. (col = H) VOLUME Q1 2026: Sum of Searches Jan 2026 + Feb 2026 + Mar 2026 — from Keyword Study
9. (col = I) VOLUME Q4 2025: Sum of Searches Oct 2025 + Nov 2025 + Dec 2025 — from Keyword Study

## OneSearch Coverage (cols J–K) — sheet formulas, do not write from workflow

10. (col = J) Coverage One Search Q1 2026: Clics OneSearch Q1 2026 divided by VOLUME Q1 2026 — **formula in Google Sheets, do not write**
11. (col = K) Coverage One Search Q4 2025: Clics OneSearch Q4 2025 divided by VOLUME Q4 2025 — **formula in Google Sheets, do not write**

## OneSearch Totals (cols L–O) — computed: SEO + SEM

12. (col = L) Clics OneSearch Q1 2026: **gsc_clicks_p1 + sqr_clicks_p1**
13. (col = M) Impressions OneSearch Q1 2026: **gsc_impr_p1 + sqr_impr_p1**
14. (col = N) Clics OneSearch Q4 2025: **gsc_clicks_p2 + sqr_clicks_p2**
15. (col = O) Impressions OneSearch Q4 2025: **gsc_impr_p2 + sqr_impr_p2**

## Clicks (cols P–S)

16. (col = P) Clics SEO Q1 2026: gsc_clicks_p1 — from gsc_exports_queries_oikos.csv
17. (col = Q) Clics SEM Q1 2026: sqr_clicks_p1 — from account_leve_sqr_report_oikos.csv
18. (col = R) Clics SEO Q4 2025: gsc_clicks_p2 — from gsc_exports_queries_oikos.csv
19. (col = S) Clics SEM Q4 2025: sqr_clicks_p2 — from account_leve_sqr_report_oikos.csv

## Impressions (cols T–W)

20. (col = T) Impr. SEO Q1 2026: gsc_impr_p1 — from gsc_exports_queries_oikos.csv
21. (col = U) Impr. SEM Q1 2026: sqr_impr_p1 — from account_leve_sqr_report_oikos.csv
22. (col = V) Impr. SEO Q4 2025: gsc_impr_p2 — from gsc_exports_queries_oikos.csv
23. (col = W) Impr. SEM Q4 2025: sqr_impr_p2 — from account_leve_sqr_report_oikos.csv

## CTR (cols X–AA)

24. (col = X) CTR SEO Q1 2026: gsc_ctr_p1 — direct from gsc_exports_queries_oikos.csv
25. (col = Y) CTR SEM Q1 2026: **Computed** — sqr_clicks_p1 ÷ sqr_impr_p1 (not in SQR export)
26. (col = Z) CTR SEO Q4 2025: gsc_ctr_p2 — direct from gsc_exports_queries_oikos.csv
27. (col = AA) CTR SEM Q4 2025: **Computed** — sqr_clicks_p2 ÷ sqr_impr_p2 (not in SQR export)

## Conversions (cols AB–AE)

28. (col = AB) Conversions SEO Q1 2026 — **Connected.** GA4 page-level export filtered to `mikmak_checkout` events. Joined to keywords via SE Ranking landing page URL. Source label in config: `Conversions: Checkout`.
29. (col = AC) Conversions SEM Q1 2026 — **Connected.** GA4 page-level export filtered to `mikmak_click_offline_store` events. Source label in config: `Conversions: Click Offline Store`.
30. (col = AD) Conversions SEO Q4 2025 — **Not configured.** Add Q4 GA4 checkout export to source config as `Conversions: Checkout Q4 2025`.
31. (col = AE) Conversions SEM Q4 2025 — **Not configured.** Add Q4 GA4 offline store export to source config as `Conversions: Click Offline Store Q4 2025`.

## CPC / Spend (cols AF–AK)

32. (col = AF) CPC SEO Q1 2026: se_cpc — from SE Ranking (market estimate, not actual paid CPC)
33. (col = AG) CPC avg. SEM Q1 2026: **Computed** — sqr_cost_p1 ÷ sqr_clicks_p1 (col AH ÷ col Q)
34. (col = AH) Spent SEM Q1 2026: sqr_cost_p1 — from account_leve_sqr_report_oikos.csv
35. (col = AI) Cost SEO Q1 2026: ⚠️ **Computed: se_cpc × gsc_clicks_p1** — organic equivalent cost (SE Ranking CPC × SEO clicks Q1). Verify this interpretation before deploying.
36. (col = AJ) Spent SEM Q4 2025: sqr_cost_p2 — from account_leve_sqr_report_oikos.csv
37. (col = AK) Cost SEO Q4 2025: ⚠️ **Computed: se_cpc × gsc_clicks_p2** — organic equivalent cost (SE Ranking CPC × SEO clicks Q4). Verify this interpretation before deploying.

## Keyword Taxonomy (cols AL–AX) — from SE Ranking and Keyword Study

38. (col = AL) Purchase intent — SE Ranking: se_search_intent (SE Ranking column H)
39. (col = AM) Yogurt types — Keyword Study taxonomy
40. (col = AN) Taste — Keyword Study taxonomy
41. (col = AO) Packaging — Keyword Study taxonomy
42. (col = AP) Ingredient — Keyword Study taxonomy
43. (col = AQ) Brands — Keyword Study taxonomy
44. (col = AR) Retailer — Keyword Study taxonomy
45. (col = AS) Demography — Keyword Study taxonomy
46. (col = AT) Benefits — Keyword Study taxonomy
47. (col = AU) Testimonials — Keyword Study taxonomy
48. (col = AV) Bio — Keyword Study taxonomy
49. (col = AW) Moments — Keyword Study taxonomy
50. (col = AX) Recipes — Keyword Study taxonomy

> Note: col AY (col 51) is not used — gap between taxonomy cols (AX) and monthly volume cols (AZ).

## Monthly Search Volumes (cols AZ–BE) — from Keyword Study

51. (col = AZ) Searches: Oct 2025 — Keyword Study
52. (col = BA) Searches: Nov 2025 — Keyword Study
53. (col = BB) Searches: Dec 2025 — Keyword Study
54. (col = BC) Searches: Jan 2026 — Keyword Study
55. (col = BD) Searches: Feb 2026 — Keyword Study
56. (col = BE) Searches: Mar 2026 — Keyword Study
