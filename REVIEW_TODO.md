# OneSearch review — consolidated TODO

**Status as of 2026-10-04: nothing below has been actioned.** This is a planning list only. Full detail/evidence for each item lives in `INTERNATIONAL_DELIGHT_REVIEW_FINDINGS.md`, `SILK_REVIEW_FINDINGS.md`, and `ACTIVIA_DASHBOARD_PORTBACK_TRACKER.md`.

---

## Blocked on user/boss input (do first — these gate other items)
- [ ] Decide the SEM QV methodology question (fast caveat-label vs. slower click-capped rework) — affects ID, Silk, and Activia equally since it's shared code.
- [ ] Decide, once the `normalize()` bug (below) is fixed and "silk 官网" splits apart, whether CJK-market navigational traffic should count toward Silk's US BRAND coverage metric at all.

## International Delight
- [ ] Register missing Q1 2026 GA4 conversion sources (Checkout, Click Offline Store) in the source registry, then re-run ingestion — fixes SEO QV showing 0/"NEW" everywhere in the previous period.
- [ ] Fix cosmetic percent-formatting bug on 4 Masterlist columns (Clics/Impr. SEO/SEM Q1 2026 display as e.g. "246900%") — safe, no data impact, Sheets cell-format change only.
- [ ] Rebuild dashboard once the above + the shared fixes below are ready (hero chips, colors, orphaned-data truncation, SE-gap asterisk footnote, export button + input-box removal).

## Silk
- [ ] Fix `pipeline/normalize.py::normalize()` so it stops stripping non-Latin-script characters (strip punctuation/symbols only) — highest-value item, real bug, currently merges "silk 官网" (CJK brand-nav traffic) with the unrelated English query "silk" into one row that drives Silk's single biggest territory-coverage loss (BRAND, -15.4pp). Needs testing against the fuzzy-matching step that also depends on `normalize()`.
- [ ] Re-run Silk's ingestion after the `normalize()` fix to split "silk 官网" back into its real separate rows.
- [ ] Register missing Q1 2026 GA4 conversion sources (Checkout, Click Offline Store) for Silk, then re-run ingestion — same SEO-QV-previous-period fix as ID.
- [ ] Rebuild dashboard once the above + shared fixes are ready.

## Shared code fixes (apply once, benefit every brand)
- [ ] **Export button + input-box removal** — strip `inject_export_ui()` and every `contenteditable="true"` box (exec-summary, per-territory analyst-notes boxes, top-15-prioritization box) from `scripts/build_html_oikos.py`. Confirmed scope with user (image review, 2026-10-04): the dark "Add analyst notes…" boxes are exactly what's meant. Code not yet written. Applies to ID, Silk, **and Activia's already-built dashboard**.
- [ ] SE-Ranking volume-gap asterisk/footnote — **already implemented**, just needs each brand rebuilt to take effect (ID, Silk, Activia, Oikos).
- [ ] Add a hard-stop/warning when a brand's previous-period GA4 source isn't registered (currently silently logs and skips) — same class as the existing GSC-403-hard-stop rule. Not yet written.
- [ ] After the `normalize()` fix above, audit Oikos/ID/Activia's real Masterlist data for the same non-ASCII collision pattern before assuming it's Silk-only.

## Activia-specific (from the port-back tracker — needs verifying against Activia's real data, not yet checked)
- [ ] Apply the export-button + input-box removal (above) to Activia's dashboard.
- [ ] Verify Activia's own source registry has previous-period ("...Q1 2026") rows for every GA4 conversion source it uses — if not, same silent "everything shows NEW" problem likely exists.
- [ ] Rebuild Activia's dashboard to pick up the SE-Ranking-gap asterisk footnote (already implemented, just not applied yet).
- [ ] Quick scan of Activia's real GSC query data for non-ASCII characters, to see if the same `normalize()` collision risk applies before/after that fix lands.
- [ ] (Disclosure only, no fix needed) Caveat Activia's SEM QV numbers the same way as ID/Silk if/when presenting — QV can exceed clicks by design, not a bug.

## Not yet started
- [ ] Oikos review (not requested yet — only ID and Silk were asked for this pass).
