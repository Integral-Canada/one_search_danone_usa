#!/usr/bin/env python3
"""
Classify blank TOPIC/CATEGORY/SUB-CATEGORY (+ taxonomy tag) cells in a brand's
Keyword Study sheet via Claude Haiku, writing directly to the KS sheet.

Deliberately NOT the Masterlist: run_pipeline.py clears and fully rebuilds the
Masterlist from source data (including a fresh KS match) on every run, so
enriching the Masterlist alone would be silently wiped out on the next real
pipeline run. The KS sheet is the durable source of truth.

Usage:
    python3 scripts/classify_ks_taxonomy.py --brand international-delight
    python3 scripts/classify_ks_taxonomy.py --brand silk
    python3 scripts/classify_ks_taxonomy.py --brand silk --limit 50   # test batch
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.utils import load_brand_config, load_env, get_token, sheets_get
from pipeline.enrich import (
    _build_system_message, _claude_classify, _taxonomy_cols, _col_letter, _sheets_write,
    CLAUDE_BATCH,
)
from run_pipeline import read_source_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--brand', required=True)
    parser.add_argument('--limit', type=int, default=None,
                         help='Only classify the first N blank rows (for a cheap test run)')
    args = parser.parse_args()

    cfg = load_brand_config(args.brand)
    env = load_env()
    token = get_token(env)
    anthropic_key = env.get('ANTHROPIC_API_KEY')
    if not anthropic_key:
        raise SystemExit('ANTHROPIC_API_KEY not found in .env')

    ref_id  = cfg['sheets']['ref_id']
    ref_tab = cfg['sheets']['ref_tab']
    ref_client = cfg['sheets'].get('ref_client', ref_tab)
    source_cfg = read_source_config(token, ref_id, ref_tab, ref_client)
    ks_cfg = source_cfg.get('Keyword study')
    if not ks_cfg:
        raise SystemExit(f"No 'Keyword study' row found in registry for {ref_client}")
    ks_id, ks_tab = ks_cfg['doc_id'], ks_cfg['sheet_tab']
    print(f"KS sheet: {ks_id} / '{ks_tab}'", flush=True)

    hdrs_raw = sheets_get(token, ks_id, f"'{ks_tab}'!1:1")
    if not hdrs_raw:
        raise SystemExit('Could not read KS headers')
    headers = [str(h) for h in hdrs_raw[0]]
    hdr_idx = {h: i for i, h in enumerate(headers)}
    print(f"  {len(headers)} columns: {headers}", flush=True)

    kw_idx = hdr_idx.get('Keyword')
    topic_idx = hdr_idx.get('TOPIC')
    if kw_idx is None or topic_idx is None:
        raise SystemExit(f"Missing Keyword/TOPIC column in headers: {headers}")

    tag_cols = [c for c in _taxonomy_cols(cfg) if c in hdr_idx]
    # Claude's response uses "TOPICS" (plural, matching the Masterlist column name);
    # the KS sheet's own column is "TOPIC" (singular) — map explicitly.
    write_cols = [('TOPIC', 'TOPICS'), ('CATEGORY', 'CATEGORY'), ('SUB-CATEGORY', 'SUB-CATEGORY')]
    write_cols += [(c, c) for c in tag_cols]
    write_cols = [(sheet_col, resp_key) for sheet_col, resp_key in write_cols if sheet_col in hdr_idx]

    system_message = _build_system_message(cfg)
    print(f"\nSystem message:\n{system_message}\n", flush=True)

    rows = []
    for start in range(2, 20000, 1000):
        chunk = sheets_get(token, ks_id, f"'{ks_tab}'!A{start}:Z{start + 999}")
        if not chunk:
            break
        for i, row in enumerate(chunk):
            rows.append((start + i, row))
    print(f"  {len(rows)} data rows read", flush=True)

    def cell(row, idx):
        return str(row[idx]).strip() if idx is not None and idx < len(row) else ''

    to_classify = []
    for sheet_row, row in rows:
        kw = cell(row, kw_idx)
        if not kw:
            continue
        if cell(row, topic_idx) != '':
            continue  # already classified — leave alone
        to_classify.append({'sheet_row': sheet_row, 'keyword': kw, 'TOPICS': '', 'CATEGORY': ''})

    if args.limit:
        to_classify = to_classify[:args.limit]

    print(f"  {len(to_classify)} rows need classification", flush=True)
    if not to_classify:
        print('Nothing to do.', flush=True)
        return

    classified_map = {}
    batches = [to_classify[i:i + CLAUDE_BATCH] for i in range(0, len(to_classify), CLAUDE_BATCH)]
    print(f"  Sending {len(batches)} batches to Claude ({CLAUDE_BATCH} keywords/batch)…", flush=True)
    for bi, batch in enumerate(batches):
        print(f"    Batch {bi + 1}/{len(batches)}: {len(batch)} keywords… ", end="", flush=True)
        try:
            results = _claude_classify(batch, anthropic_key, system_message)
        except Exception as e:
            print(f"FAILED: {e}", flush=True)
            continue
        for r in results:
            kw = str(r.get('keyword', '')).strip()
            if kw:
                classified_map[kw.lower()] = r
        print(f"{len(results)} classified", flush=True)
        if bi < len(batches) - 1:
            time.sleep(1)

    print(f"  Total classified: {len(classified_map)}", flush=True)

    updates = []
    unmatched = 0
    for item in to_classify:
        cls = classified_map.get(item['keyword'].lower())
        if not cls:
            unmatched += 1
            continue
        sheet_row = item['sheet_row']
        for sheet_col, resp_key in write_cols:
            new_val = str(cls.get(resp_key, '') or '')
            if new_val:
                col_ltr = _col_letter(hdr_idx[sheet_col])
                updates.append((f"'{ks_tab}'!{col_ltr}{sheet_row}", [[new_val]]))

    if unmatched:
        print(f"  Warning: {unmatched} rows had no matching Claude response (kept blank)", flush=True)

    print(f"  Writing {len(updates)} cells…", flush=True)
    total_cells = 0
    for i in range(0, len(updates), 50):
        total_cells += _sheets_write(token, ks_id, updates[i:i + 50])
        if i + 50 < len(updates):
            time.sleep(1)
    print(f"Done — {total_cells} cells updated.", flush=True)


if __name__ == '__main__':
    main()
