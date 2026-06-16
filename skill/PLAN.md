# One Search Project Plan — [CLIENT]

## Objective

Build and populate the **[CLIENT] OneSearch Masterlist** in Google Sheets. The masterlist combines SEO (Google Search Console) and SEM (Google Ads) data to measure combined "OneSearch" keyword coverage across two comparable periods (Period 1 vs Period 2).

---

## Project Config (fill in per client)

| | |
|---|---|
| Client | [CLIENT NAME] |
| Period 1 (current) | e.g. Q1 2026: Jan 1 – Mar 31, 2026 |
| Period 2 (comparison) | e.g. Q4 2025: Oct 1 – Dec 31, 2025 |
| Google Drive Folder | [Drive folder URL] |
| Masterlist Sheet ID | [Google Sheet ID] |
| Masterlist Tab | `Listing` |
| Keyword Study Sheet ID | [Google Sheet ID] |
| Keyword Study Tab | e.g. `Keyword study [MARKET]` |

---

## Source Data (generic)

| Type | Source Platform | Export Name Convention | Contains |
|---|---|---|---|
| SEO — Queries | Google Search Console | `gsc_export_queries_[client].csv` | Clicks, Impressions, CTR, Position — per query, Period 1 vs Period 2 |
| SEO — Pages | Google Search Console | `gsc_export_pages_[client].csv` | Same metrics per page |
| SEM — Search Terms | Google Ads SQR | `account_level_sqr_report_[client].csv` | Search term, Clicks, Cost, Impressions — Period 1 vs Period 2 |
| SEM — Quality | Google Ads | `quality_report_[client].csv` | Keyword Quality Score, Landing Page Exp., Ad Relevance, Exp. CTR |
| Rank & Volume | SE Ranking (most recent month) | `se_ranking_[month]_[client].csv` | Position, Average Search Volume, CPC, Traffic |
| Keyword Taxonomy | Google Sheets — Keyword Study | Sheet ID + tab per client | Topics, Category, Sub-Category, monthly search volumes, classification labels |

---

## Masterlist Column Map

### Identity & Classification (cols A–E)
| Col | Field | Source |
|---|---|---|
| A | LANG | Keyword Study |
| B | KEYWORD | Keyword Study |
| C | TOPICS | Keyword Study |
| D | CATEGORY | Keyword Study |
| E | SUB-CATEGORY | Keyword Study |

### SE Ranking (cols F–G)
| Col | Field | Source column |
|---|---|---|
| F | Position SE Ranking | SE Ranking export → `Position` |
| G | Average Search Volume | SE Ranking export → `Search vol.` |

### Search Volume by Period (cols H–I)
| Col | Field | Source |
|---|---|---|
| H | Volume Period 1 | SE Ranking `Average Search Volume` × 3 (monthly avg × 3 months in quarter) |
| I | Volume Period 2 | SE Ranking `Average Search Volume` × 3 |

### OneSearch Coverage (cols J–K) — auto-computed in Sheets
| Col | Field | Formula |
|---|---|---|
| J | Coverage OneSearch Period 1 | Keywords with (SEO pos ≤ 20 OR SEM impr > 0) / total keywords × 100 |
| K | Coverage OneSearch Period 2 | Same formula for P2 |

> Coverage is a **share of keywords actively captured**, not a clicks-to-volume ratio. SEO Coverage = pos ≤ 20 / total. SEM Coverage = SEM impr > 0 / total. OneSearch Coverage = either condition met / total.

### OneSearch Totals (cols L–O)
| Col | Field | Derivation |
|---|---|---|
| L | Clics OneSearch Period 1 | SEO Clicks P1 + SEM Clicks P1 |
| M | Impressions OneSearch Period 1 | SEO Impr. P1 + SEM Impr. P1 |
| N | Clics OneSearch Period 2 | SEO Clicks P2 + SEM Clicks P2 |
| O | Impressions OneSearch Period 2 | SEO Impr. P2 + SEM Impr. P2 |

### Clicks (cols P–S)
| Col | Field | Source column |
|---|---|---|
| P | Clics SEO Period 1 | GSC queries → `[P1 date range] Clicks` |
| Q | Clics SEM Period 1 | SQR report → `Clicks` (P1) |
| R | Clics SEO Period 2 | GSC queries → `[P2 date range] Clicks` |
| S | Clics SEM Period 2 | SQR report → `Clicks (Compare to)` (P2) |

### Impressions (cols T–W)
| Col | Field | Source column |
|---|---|---|
| T | Impr. SEO Period 1 | GSC queries → `[P1 date range] Impressions` |
| U | Impr. SEM Period 1 | SQR report → `Impr.` (P1) |
| V | Impr. SEO Period 2 | GSC queries → `[P2 date range] Impressions` |
| W | Impr. SEM Period 2 | SQR report → `Impr. (Compare to)` (P2) |

### CTR (cols X–AA)
| Col | Field | Source / Derivation |
|---|---|---|
| X | CTR SEO Period 1 | GSC queries → `[P1 date range] CTR` |
| Y | CTR SEM Period 1 | Computed: SEM Clicks P1 / SEM Impr. P1 ⚠️ |
| Z | CTR SEO Period 2 | GSC queries → `[P2 date range] CTR` |
| AA | CTR SEM Period 2 | Computed: SEM Clicks P2 / SEM Impr. P2 ⚠️ |

> ⚠️ CTR SEM is not in the SQR export — must be computed.

### Conversions (cols AB–AE)
| Col | Field | Source |
|---|---|---|
| AB | Conversions SEO Period 1 | TBD (GA4 or additional export) |
| AC | Conversions SEM Period 1 | Google Ads conversion export — filter to `mikmak_checkout` + `mikmak_click_offline_store` |
| AD | Conversions SEO Period 2 | TBD |
| AE | Conversions SEM Period 2 | Google Ads conversion export — filter to `mikmak_checkout` + `mikmak_click_offline_store` |

> **Paid conversion actions (SEM):** `mikmak_checkout` and `mikmak_click_offline_store`. These are **not in the SQR report** — a separate Google Ads conversion export by search term / keyword is required.

### Cost / CPC (cols AF–AK)
| Col | Field | Source / Derivation |
|---|---|---|
| AF | CPC SEO Period 1 | SE Ranking export → `CPC` |
| AG | CPC avg. SEM Period 1 | Computed: Cost P1 / Clicks P1 ⚠️ |
| AH | Spend SEM Period 1 | SQR report → `Cost` (P1) |
| AI | Cost SEO Period 1 | ⚠️ Computed: `se_cpc × gsc_clicks_p1` — verify before deploying |
| AJ | Spend SEM Period 2 | SQR report → `Cost (Compare to)` (P2) |
| AK | Cost SEO Period 2 | ⚠️ Computed: `se_cpc × gsc_clicks_p2` — verify before deploying |

> ⚠️ CPC SEM (AG), CTR SEM (Y, AA), and Cost SEO (AI, AK) must be computed. AI/AK formula needs verification before deploying.

### Keyword Taxonomy (cols AL–AX) — from SE Ranking and Keyword Study

| Col | Field | Source |
|---|---|---|
| AL | Purchase intent | SE Ranking → `se_search_intent` |
| AM | Yogurt types | Keyword Study taxonomy |
| AN | Taste | Keyword Study taxonomy |
| AO | Packaging | Keyword Study taxonomy |
| AP | Ingredient | Keyword Study taxonomy |
| AQ | Brands | Keyword Study taxonomy |
| AR | Retailer | Keyword Study taxonomy |
| AS | Demography | Keyword Study taxonomy |
| AT | Benefits | Keyword Study taxonomy |
| AU | Testimonials | Keyword Study taxonomy |
| AV | Bio | Keyword Study taxonomy |
| AW | Moments | Keyword Study taxonomy |
| AX | Recipes | Keyword Study taxonomy |
| AY | *(unused — gap col)* | — |

### Monthly Search Volumes (cols AZ–BE) — from Keyword Study

| Col | Field |
|---|---|
| AZ | Searches: Oct 2025 |
| BA | Searches: Nov 2025 |
| BB | Searches: Dec 2025 |
| BC | Searches: Jan 2026 |
| BD | Searches: Feb 2026 |
| BE | Searches: Mar 2026 |


---

## Implementation — Python Pipeline (operational as of Apr 2026)

The n8n workflow was abandoned after OOM crashes on the 14,273-KS trigram matching step. All computation now runs in the `one_search/` Python package. Entry point: `run_onesearch.py`.

**Last run (Oikos USA, 2026-05-04):** 3,663 unified rows · 709 SE matches · 956 KS auto-matched · 329 GA4 conversion hits · 1,212 volumes filled via SE Ranking API.

### Run the pipeline

```bash
cd /Users/carlaklaasen/claude_code/one_search
python3 run_onesearch.py
python3 run_onesearch.py --max-rows 500   # smaller test batch
```

### Pipeline steps (Python)

1. Read source config from Google Sheets (resolves labels → doc IDs)
2. Read all sources from Google Sheets: GSC, SQR, SE Ranking, Keyword Study, GA4 ×2
3. Normalize each source (`ingest.norm_gsc/sqr/se/ks`)
4. Merge GSC + SQR → unified spine (~3,663 rows): filter clicks > 1, dedup, full outer join
5. Build trigram index on unified spine (built once, reused for SE + KS matching)
6. Match SE Ranking → unified rows (sim ≥ 0.50): attaches col F, G, AF, AL
7. Match Keyword Study → unified rows (sim ≥ 0.65 auto / 0.50–0.65 review): attaches cols A, C–E, H–I, AM–AX, AZ–BE
8. Join GA4 conversions via SE Ranking URL path → cols AB, AC
9. Write Masterlist (Listing tab), KW review tabs, ARRAYFORMULA cells (J, K, AI, AK)
10. Post-write: SE Ranking API fills missing search volume in col G

### Open items

| Item | Status |
|---|---|
| Q4 SEM data (cols S, W, AA, AJ) | Blank — re-export SQR with Q4 2025 as comparison period |
| Q4 GA4 conversions (cols AD, AE) | Not configured — add Q4 GA4 files to source config |
| SE Ranking threshold | Currently 0.50 — review report recommends raising to 0.60 |
| SE Ranking position fallback | No GSC fallback for blank col F |
| PMax filter | `norm_sqr()` does not exclude Performance Max campaigns |
| Quality Score | Quality report is read but not written to Masterlist |

### QA checklist (run after each pipeline run)

- [ ] Spot-check 10–15 keywords against raw source sheets
- [ ] Verify OneSearch totals = SEO + SEM for sampled rows
- [ ] Check `logs/` for any write errors or blank-col warnings
- [ ] Review `5 < Cos < 0.65` tab for borderline matches requiring approval
