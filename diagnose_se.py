#!/usr/bin/env python3
"""Quick diagnostic: reads SE + GSC/SQR data and shows why SE matches may be missing."""
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

from one_search.ingest import norm_gsc, norm_sqr, norm_se
from one_search.merge import merge_gsc_sqr
from one_search.trigram import build_index
from one_search.match_se import match_se_keywords

ENV_FILE = "/Users/carlaklaasen/claude_code/.env"
REF_ID   = "1o526Qv4UzP_Qfe-cjrfvcA7jRUi6zUtd9Ecp2WPMIhQ"
REF_TAB  = "One Search "

def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def get_token(env):
    data = urllib.parse.urlencode({
        "client_id":     env["GOOGLE_CLIENT_ID"],
        "client_secret": env["GOOGLE_CLIENT_SECRET"],
        "refresh_token": env["GOOGLE_REFRESH_TOKEN"],
        "grant_type":    "refresh_token",
    }).encode()
    resp = json.loads(urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    ).read())
    return resp["access_token"]

def sheets_get(token, sheet_id, range_):
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
           f"/values/{urllib.parse.quote(range_, safe='!:')}"
           f"?valueRenderOption=UNFORMATTED_VALUE")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read()).get("values", [])

def raw_to_dicts(raw_rows):
    if not raw_rows:
        return [], []
    headers = [str(h) for h in raw_rows[0]]
    out = []
    for row in raw_rows[1:]:
        d = {h: (row[i] if i < len(row) else '') for i, h in enumerate(headers)}
        out.append(d)
    return headers, out

def read_source_config(token):
    raw = sheets_get(token, REF_ID, f"'{REF_TAB}'!A:D")
    _, rows = raw_to_dicts(raw)
    config = {}
    for r in rows:
        label = str(r.get('Export') or '').strip()
        if label:
            config[label] = {'doc_id': str(r.get('Doc ID') or '').strip(),
                             'sheet_tab': str(r.get('Sheet Tab') or '').strip()}
    return config

def main():
    env   = load_env()
    token = get_token(env)
    config = read_source_config(token)

    def read(label, range_suffix):
        c = config.get(label, {})
        if not c.get('doc_id'):
            print(f"  '{label}' not in config")
            return []
        raw = sheets_get(token, c['doc_id'], f"'{c['sheet_tab']}'!{range_suffix}")
        _, rows = raw_to_dicts(raw)
        return rows

    # ── Read SE raw and show column names
    se_raw = read('SE Ranking', 'A:Z')
    print(f"\nSE raw rows: {len(se_raw)}")
    if se_raw:
        print(f"SE columns: {list(se_raw[0].keys())}")
        print(f"SE sample row: {se_raw[0]}")

    # ── Normalize SE
    se_norm = norm_se(se_raw)
    print(f"\nSE after norm_se (pos ≤ 100): {len(se_norm)}")
    if se_norm:
        print(f"SE norm sample: {se_norm[0]}")
    else:
        print("  → ALL SE ROWS FILTERED OUT")
        # Show raw position values from first 5 rows
        for r in se_raw[:5]:
            print(f"  raw pos={r.get('Position')!r}  kw={str(list(r.values())[:1])}")
        return

    # ── Read GSC/SQR (small batch) and build unified index
    gsc_raw = read('GSC Export', 'A:Z')[:200]
    sqr_raw = read('Account Level SQR Report', 'A:V')[:200]
    gsc_norm = norm_gsc(gsc_raw)
    sqr_norm = norm_sqr(sqr_raw)
    unified  = merge_gsc_sqr(gsc_norm, sqr_norm)
    print(f"\nUnified rows (200-row sample): {len(unified)}")

    index = build_index(unified)
    print(f"Index: {len(index['uKeys'])} keys, {len(index['idx'])} trigrams")
    if index['uKeys']:
        print(f"Sample uKey: {index['uKeys'][0]!r}  uDisplay: {index['uDisplay'][0]!r}")

    # ── Match SE
    se_matches = match_se_keywords(se_norm[:200], index)
    print(f"\nSE matches (first 200 SE rows vs 200-row unified): {len(se_matches)}")
    if se_matches:
        print(f"Sample match: {se_matches[0]}")
    else:
        print("  → NO SE MATCHES — checking similarity scores manually")
        # Manual check: try first SE keyword against index
        from one_search.trigram import trigrams_arr, jaccard
        from one_search.normalize import normalize
        test_kw = se_norm[0]['norm_se_keyword']
        q_arr = trigrams_arr(test_kw)
        q_set = set(q_arr)
        scores = []
        for i, tg in enumerate(index['uTg']):
            s = jaccard(tg, q_set)
            if s > 0:
                scores.append((s, index['uDisplay'][i], index['uKeys'][i]))
        scores.sort(reverse=True)
        print(f"  SE kw={test_kw!r}  top matches:")
        for s, d, k in scores[:5]:
            print(f"    sim={s:.3f}  display={d!r}")

def check_column_names(token):
    """Compare SE match field names against actual Masterlist headers."""
    from run_onesearch import MASTER_ID, MASTER_TAB
    raw = sheets_get(token, MASTER_ID, f"'{MASTER_TAB}'!1:1")
    if not raw or not raw[0]:
        print("\nCould not read Masterlist headers")
        return
    hdrs = [str(h) for h in raw[0]]
    print(f"\nMasterlist has {len(hdrs)} columns")

    se_fields = ['Position SE Ranking', 'CPC SEO Q1 2026', 'Purchase intent']
    for f in se_fields:
        if f in hdrs:
            print(f"  ✓ '{f}' found at col {hdrs.index(f) + 1} ({chr(65 + hdrs.index(f))})")
        else:
            # fuzzy check
            close = [h for h in hdrs if f.lower()[:8] in h.lower()]
            print(f"  ✗ '{f}' NOT found — similar: {close[:3]}")

    # Check Volume Q1/Q4 for G computation
    for col in ['Volume Q1 2026', 'Volume Q4 2025', 'Average Search Volume',
                'Clics OneSearch Q1 2026']:
        mark = '✓' if col in hdrs else '✗'
        idx = hdrs.index(col) if col in hdrs else '?'
        letter = chr(65 + idx) if isinstance(idx, int) else '?'
        print(f"  {mark} '{col}' → col {idx+1 if isinstance(idx,int) else '?'} ({letter})")


if __name__ == "__main__":
    env = load_env()
    token = get_token(env)
    check_column_names(token)
    main()
