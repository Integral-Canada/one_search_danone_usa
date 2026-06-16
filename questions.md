# Open Questions — OneSearch Oikos USA

## SEM-only keyword rows: separate tab or keep in main listing?

**Context (2026-05-08):** After the full pipeline run, ~2,300–2,400 rows in the Masterlist are SEM/SQR-origin only — keywords from paid search query reports that have never appeared in organic rankings. For these rows, Position SE Ranking and Average Search Volume are structurally blank (not a data error).

**Question:** Should these rows be filtered to a separate tab (e.g. `Listing - SEM Only`) to keep the main Listing tab focused on keywords with organic presence, or should they remain in the main tab with the sparse fields accepted as-is?

**Decision:** Keep as-is for now (confirmed 2026-05-08).

---

## MikMak conversion distribution logic — SEO vs SEM click share

**Context (2026-05-08):** Both MikMak events (Checkout and Click Offline Store) fire on the website regardless of whether the visitor came from organic or paid traffic. The current pipeline distributes both conversion types using **SEO click share only** (`Clics SEO Q1 2026`), meaning SEM-only keywords can never receive any conversions, and the split into `Conversions SEO Q1` / `Conversions SEM Q1` columns does not reflect actual traffic source.

**Design question:** Should conversions be distributed by:
1. SEO clicks only (current) — assigns all MikMak value to organic-presence keywords
2. SEM clicks for Click Offline Store, SEO clicks for Checkout — closer to channel attribution but still approximate
3. Total OS clicks (SEO + SEM combined) — treats conversions as channel-agnostic and distributes by overall keyword presence

The column names `Conversions SEO Q1 2026` / `Conversions SEM Q1 2026` were inherited from the Activia template and don't accurately describe MikMak events, which are not channel-specific.

**Blocked by:** The GA4 export issue (see below) must be resolved first before this is worth re-evaluating.

---

## MM Offline Store conversions showing zero — GA4 export issue

**Context (2026-05-08):** The OneSearch Dashboard splits conversions into two MikMak columns: MM Checkout (SEO, `r[25]`) and MM Offline Store (SEM, `r[26]`). MM Checkout shows 21.1k QV but MM Offline Store shows — for all rows.

**Root cause identified:** The GA4 source sheet for "Conversions: Click Offline Store" (doc `1gU2Uy2GhNd4ipVPm-vm1vnoLkKMGvLuNL6JdBppWDDc`) contains the same generic pages export as the Checkout sheet (identical page paths, views, event counts) but the `Événements clés` / Key Events column is 0 for virtually every row. Only `/render` has 764 key events, which doesn't match any keyword landing page URLs. The event filter for `mikmak_click_offline_store` was not applied when the export was created.

**Two possible causes:**
1. The GA4 export was done without filtering to the `mikmak_click_offline_store` key event — needs to be re-exported with the correct filter
2. The `mikmak_click_offline_store` event is not configured as a key event in GA4 at all (meaning this conversion type has no data)

**Next step:** Check in GA4 whether `mikmak_click_offline_store` is registered as a key event. If yes, re-export the report filtered to that event and update the reference sheet. If no, the column has no data to populate.

---
