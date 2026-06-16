#!/usr/bin/env python3
"""
20-row smoke test. Reads local CSV files, runs the full pipeline up to SE matching.
KS matching is skipped (Keyword Study is in Google Sheets only).
Run from the one_search/ project root:  python sample_test.py
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from pipeline.ingest import norm_gsc, norm_sqr, norm_se
from pipeline.merge import merge_gsc_sqr
from pipeline.format_rows import format_base_rows
from pipeline.trigram import build_index
from pipeline.match_se import match_se_keywords

SAMPLE_SIZE = 20


def read_csv(path: str, skip_rows: int = 0) -> list:
    with open(path, encoding='utf-8-sig') as f:
        for _ in range(skip_rows):
            next(f)
        return list(csv.DictReader(f))


def fmt(d: dict) -> str:
    return '  ' + '\n  '.join(f"{k}: {v}" for k, v in list(d.items())[:8])


# ── Load samples ──────────────────────────────────────────────────────────────
gsc_raw = read_csv('gsc_export_queries_oikos.csv')[:SAMPLE_SIZE]
sqr_raw = read_csv('account_level_sqr_report_oikos.csv', skip_rows=1)[:SAMPLE_SIZE]
se_raw  = read_csv('se_ranking_april_oikos.csv')[:SAMPLE_SIZE]

print(f"Loaded: {len(gsc_raw)} GSC rows, {len(sqr_raw)} SQR rows, {len(se_raw)} SE rows\n")

# ── Normalize ─────────────────────────────────────────────────────────────────
print("=== norm_gsc ===")
gsc_norm = norm_gsc(gsc_raw)
print(f"  {len(gsc_norm)}/{len(gsc_raw)} rows kept (zero-click rows dropped)")
if gsc_norm:
    r = gsc_norm[0]
    print(f"  [{r['norm_query']}]  clicks_p1={r['gsc_clicks_p1']}  impr_p1={r['gsc_impr_p1']}  pos_p1={r['gsc_pos_p1']}")

print("\n=== norm_sqr ===")
sqr_norm = norm_sqr(sqr_raw)
print(f"  {len(sqr_norm)}/{len(sqr_raw)} rows kept (zero-click rows dropped)")
if sqr_norm:
    r = sqr_norm[0]
    print(f"  [{r['norm_term']}]  clicks_p1={r['sqr_clicks_p1']}  cost_p1={r['sqr_cost_p1']}  impr_p1={r['sqr_impr_p1']}")

print("\n=== norm_se ===")
se_norm = norm_se(se_raw)
print(f"  {len(se_norm)}/{len(se_raw)} rows kept (pos > 50 dropped)")
if se_norm:
    r = se_norm[0]
    print(f"  [{r['norm_se_keyword']}]  pos={r['se_position']}  vol={r['se_search_vol']}  cpc={r['se_cpc']}")

# ── Merge ─────────────────────────────────────────────────────────────────────
print("\n=== merge_gsc_sqr ===")
unified = merge_gsc_sqr(gsc_norm, sqr_norm)
print(f"  Unified rows: {len(unified)}")
if unified:
    r = unified[0]
    print(f"  [{r['unified_key']}]  gsc_clicks_p1={r['gsc_clicks_p1']}  sqr_clicks_p1={r['sqr_clicks_p1']}")
    gsc_only = sum(1 for x in unified if x.get('sqr_clicks_p1', 0) == 0)
    sqr_only = sum(1 for x in unified if x.get('gsc_clicks_p1', 0) == 0)
    both     = len(unified) - gsc_only - sqr_only
    print(f"  GSC-only: {gsc_only}  SQR-only: {sqr_only}  Both: {both}")

# ── Format base rows ──────────────────────────────────────────────────────────
print("\n=== format_base_rows ===")
base = format_base_rows(unified)
print(f"  {len(base)} rows formatted")
if base:
    r = base[0]
    print(f"  Keyword: {r['Keyword']}")
    print(f"  Clics OneSearch Q1 2026: {r['Clics OneSearch Q1 2026']}")
    print(f"  CTR SEO Q1 2026: {r['CTR SEO Q1 2026']}")
    print(f"  CPC avg. SEM Q1 2026: {r['CPC avg. SEM Q1 2026']}")

# ── Trigram index ─────────────────────────────────────────────────────────────
print("\n=== build_index ===")
index = build_index(unified)
print(f"  {len(index['uKeys'])} keys, {len(index['idx'])} trigrams in index")

# ── SE match ──────────────────────────────────────────────────────────────────
print("\n=== match_se_keywords (threshold=0.50) ===")
se_matches = match_se_keywords(se_norm, index)
print(f"  {len(se_matches)} SE matches found")
for m in se_matches[:5]:
    print(f"  Keyword: {m['Keyword']!r:30s}  pos={m['Position SE Ranking']}  vol={m['Average Search Volume']}  intent={m['Purchase intent']}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SAMPLE TEST COMPLETE")
print(f"  GSC rows normalized:   {len(gsc_norm)}")
print(f"  SQR rows normalized:   {len(sqr_norm)}")
print(f"  SE rows (pos ≤ 50):    {len(se_norm)}")
print(f"  Unified rows:          {len(unified)}")
print(f"  Base rows formatted:   {len(base)}")
print(f"  SE matches:            {len(se_matches)}")
