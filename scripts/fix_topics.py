"""
fix_topics.py
-------------
One-time patch: update TOPICS column in Oikos USA masterlist for misclassified keywords.

Changes TOPICS from BRAND to COMPETITOR for known competitor brand terms
that were incorrectly classified in the keyword spine.

Run once before re-running sem_qv_attribution.py.
"""

import os, sys, json, time, urllib.request, urllib.parse
from collections import defaultdict

MASTER_FILE_ID = "1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU"
MASTER_TAB     = "Listing"

# Keywords to reclassify from BRAND → COMPETITOR (case-insensitive exact match)
COMPETITOR_KEYWORDS = {
    'premier shakes',
    'fairlife core power elite',
    'fairlife core power',
    'fairlife',
    'core power elite',
    'core power',
}

def load_env():
    env = {}
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
    env_path = os.path.abspath(env_path)
    if not os.path.exists(env_path):
        sys.exit(f"ERROR: .env not found at {env_path}")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env

def get_token(env):
    payload = urllib.parse.urlencode({
        'client_id':     env['GOOGLE_CLIENT_ID'],
        'client_secret': env['GOOGLE_CLIENT_SECRET'],
        'refresh_token': env['GOOGLE_REFRESH_TOKEN'],
        'grant_type':    'refresh_token',
    }).encode()
    req = urllib.request.Request(
        env.get('GOOGLE_TOKEN_URI', 'https://oauth2.googleapis.com/token'),
        data=payload, method='POST'
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)['access_token']

def sheets_get(token, file_id, range_):
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}/values/"
        f"{urllib.parse.quote(range_, safe=':!')}"
    )
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req) as r:
                return json.load(r).get('values', [])
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)

def sheets_batch_update(token, file_id, data_ranges):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}/values:batchUpdate"
    body = json.dumps({
        'valueInputOption': 'RAW',
        'data': data_ranges
    }).encode()
    req = urllib.request.Request(url, data=body, method='POST', headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)

def col_letter(n):
    result = ''
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result

def main():
    print("="*60)
    print("fix_topics.py — Patch competitor TOPICS in masterlist")
    print("="*60)

    env   = load_env()
    token = get_token(env)
    print("Authenticated ✓")

    print(f"\nReading masterlist '{MASTER_TAB}'...")
    raw = sheets_get(token, MASTER_FILE_ID, f"'{MASTER_TAB}'!A1:BF5000")
    if not raw or len(raw) < 2:
        sys.exit("ERROR: Masterlist returned no data")

    headers = [str(h).strip() for h in raw[0]]

    # Find Keyword and TOPICS column indices
    kw_col_idx = next((i for i, h in enumerate(headers) if h.strip() == 'Keyword'), None)
    topics_col_idx = next((i for i, h in enumerate(headers) if h.strip() == 'TOPICS'), None)

    if kw_col_idx is None:
        sys.exit("ERROR: 'Keyword' column not found in masterlist")
    if topics_col_idx is None:
        sys.exit("ERROR: 'TOPICS' column not found in masterlist")

    topics_col = col_letter(topics_col_idx)
    print(f"  Keyword column: {col_letter(kw_col_idx)} (index {kw_col_idx})")
    print(f"  TOPICS column:  {topics_col} (index {topics_col_idx})")
    print(f"  Total rows: {len(raw)-1}")

    # Find rows to patch
    patches = []
    for i, row in enumerate(raw[1:], start=2):  # row 2 = first data row
        kw = str(row[kw_col_idx]).strip() if len(row) > kw_col_idx else ''
        topics = str(row[topics_col_idx]).strip() if len(row) > topics_col_idx else ''
        if kw.lower() in COMPETITOR_KEYWORDS:
            patches.append({
                'row': i,
                'keyword': kw,
                'old_topics': topics,
                'range': f"'{MASTER_TAB}'!{topics_col}{i}",
            })

    if not patches:
        print("\nNo matching competitor keywords found in masterlist.")
        print("Either already fixed, or keywords not present in this spine.")
        return

    print(f"\nFound {len(patches)} rows to patch:")
    for p in patches:
        print(f"  Row {p['row']:>4}: '{p['keyword']}' — TOPICS: '{p['old_topics']}' → 'COMPETITOR'")

    # Confirm before writing
    print(f"\nWriting COMPETITOR to {len(patches)} TOPICS cells...")
    data_ranges = [
        {'range': p['range'], 'values': [['COMPETITOR']]}
        for p in patches
    ]
    sheets_batch_update(token, MASTER_FILE_ID, data_ranges)
    print("Done. Re-run sem_qv_attribution.py to regenerate AC and BF columns.")
    print("="*60)

if __name__ == '__main__':
    main()
