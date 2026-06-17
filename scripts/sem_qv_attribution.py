"""
sem_qv_attribution.py
---------------------
Calculates SEM Qualified Visits (QV SEM) per keyword using Thomas's methodology
and writes results to the Oikos USA OneSearch masterlist.

Methodology (Thomas Joachim, Jun 16 2026):
  1. For each landing page in the GA4 Google Ads session export:
     LP QV rate = sum(Key Events) / sum(Sessions)
  2. For each keyword+LP row:
     Attributed QV SEM = (row Sessions / LP total Sessions) × LP total Key Events
  3. Per keyword: sum attributed QV across all landing pages
  4. Write to masterlist column AC: Conversions SEM Q1 2026

Also writes SEM Recommendation tags (column BF) for BRAND keywords:
  - Exclude: SEO Coverage > 10% AND SEO Position <= 5 AND QV SEM = 0
  - Keep-Active: QV SEM > 0 AND SEO Coverage < 10%
  - Keep-Test: SEO Coverage > 10% AND QV SEM > 0

Sources:
  GA4 Ads export: 1Z6QO82Gc3itROgnvqhBP2aoGTf4pIO0WLD-Kkbofb1w
  Tab: Campagnes_Google Ads_Requête_Google Ads_associée_à_cette_session
  Masterlist: 1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU
  Tab: Listing
"""

import os, sys, json, re, time, urllib.request, urllib.parse
from collections import defaultdict

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GA4_ADS_FILE_ID  = "1Z6QO82Gc3itROgnvqhBP2aoGTf4pIO0WLD-Kkbofb1w"
GA4_ADS_TAB      = None   # resolved at runtime from sheet metadata (tab has non-breaking spaces)
MASTER_FILE_ID   = "1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU"
MASTER_TAB       = "Listing"

COL_AC_NAME      = "Conversions SEM Q1 2026"   # existing column, currently blank
COL_BF_NAME      = "SEM Recommendation"         # new column to add

SEO_COV_THRESHOLD  = 0.10   # 10%
SEO_POS_THRESHOLD  = 5      # position <= 5

# Known competitor brand terms that should never receive SEM Recommendation tags
# even if the masterlist has them incorrectly classified as BRAND territory.
# Fix the source (TOPICS column) with fix_topics.py; this is defense-in-depth.
COMPETITOR_BLOCKLIST = {
    'premier shakes',
    'fairlife core power elite',
    'fairlife core power',
    'fairlife',
    'core power elite',
    'core power',
}

# ---------------------------------------------------------------------------
# Auth (reuses .env pattern from run_onesearch.py)
# ---------------------------------------------------------------------------
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

def get_first_sheet_title(token, file_id):
    """Return the title of the first sheet tab (handles non-breaking spaces etc.)."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}?fields=sheets.properties"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req) as r:
        meta = json.load(r)
    return meta['sheets'][0]['properties']['title']

def get_sheet_props(token, file_id, tab_name):
    """Return (sheetId, columnCount) for the named tab."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}?fields=sheets.properties"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req) as r:
        meta = json.load(r)
    for sheet in meta['sheets']:
        if sheet['properties']['title'] == tab_name:
            gp = sheet['properties'].get('gridProperties', {})
            return sheet['properties']['sheetId'], gp.get('columnCount', 0)
    raise ValueError(f"Sheet tab '{tab_name}' not found in {file_id}")

def expand_sheet_columns(token, file_id, sheet_id, add_count):
    """Append `add_count` new columns to the right of the sheet."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}:batchUpdate"
    body = json.dumps({
        'requests': [{
            'appendDimension': {
                'sheetId': sheet_id,
                'dimension': 'COLUMNS',
                'length': add_count
            }
        }]
    }).encode()
    req = urllib.request.Request(url, data=body, method='POST', headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    with urllib.request.urlopen(req) as r:
        return json.load(r)

def sheets_get(token, sheet_id, range_):
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
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

def sheets_update_range(token, sheet_id, range_, values):
    """Write a 2D array to a single range in one request."""
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/"
        f"{urllib.parse.quote(range_, safe=':!')}"
        f"?valueInputOption=RAW"
    )
    body = json.dumps({'range': range_, 'values': values}).encode()
    req = urllib.request.Request(url, data=body, method='PUT', headers={
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

def sheets_batch_update(token, sheet_id, data_ranges):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values:batchUpdate"
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
    """Convert 0-based column index to A1 notation letter(s)."""
    result = ''
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result

# ---------------------------------------------------------------------------
# Normalize keyword for matching
# ---------------------------------------------------------------------------
def normalize(s):
    s = s.lower().strip()
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s

# ---------------------------------------------------------------------------
# Step 1: Read & parse GA4 Ads export
# ---------------------------------------------------------------------------
def read_ga4_ads(token):
    """
    Returns list of dicts with keys:
      keyword, landing_page, sessions, key_events
    Skips metadata rows at top by scanning for the data header row.
    """
    print("Reading GA4 Ads export...")
    tab = get_first_sheet_title(token, GA4_ADS_FILE_ID)
    print(f"  Tab resolved: {repr(tab)}")
    raw = sheets_get(token, GA4_ADS_FILE_ID, f"'{tab}'!A1:L10000")
    if not raw:
        sys.exit("ERROR: GA4 Ads tab returned no data")

    # Find header row (look for 'Requête' or 'sessions' in first column)
    header_row_idx = None
    for i, row in enumerate(raw):
        if row and any('equ' in str(row[0]).lower() or 'session' in str(row[0]).lower()
                       or 'page de destination' in str(row[1] if len(row) > 1 else '').lower()
                       for _ in [1]):
            # Check if this looks like a real header row
            if len(row) >= 4 and 'session' in ' '.join(str(c).lower() for c in row):
                header_row_idx = i
                break

    if header_row_idx is None:
        # Fallback: look for row with 'Sessions' anywhere
        for i, row in enumerate(raw):
            joined = ' '.join(str(c) for c in row).lower()
            if 'sessions' in joined and ('page' in joined or 'requ' in joined):
                header_row_idx = i
                break

    if header_row_idx is None:
        sys.exit("ERROR: Could not find header row in GA4 Ads export")

    headers = [str(h).strip() for h in raw[header_row_idx]]
    print(f"  Header row at index {header_row_idx}: {headers[:6]}...")

    # Identify column positions
    def find_col(patterns):
        for p in patterns:
            for i, h in enumerate(headers):
                if p.lower() in h.lower():
                    return i
        return None

    col_kw  = find_col(['Requ', 'query', 'terme'])
    col_lp  = find_col(['page de destination', 'landing page', 'Page de destination'])
    col_ses = find_col(['Sessions'])
    col_qv  = find_col(['nements clés', 'key events', 'Key Events', 'Événements clés'])

    print(f"  Columns found — keyword:{col_kw}, landing_page:{col_lp}, sessions:{col_ses}, key_events:{col_qv}")
    if any(c is None for c in [col_kw, col_lp, col_ses, col_qv]):
        print(f"  All headers: {headers}")
        sys.exit("ERROR: Could not identify required columns in GA4 Ads export")

    rows = []
    for row in raw[header_row_idx + 1:]:
        if len(row) <= max(col_kw, col_lp, col_ses, col_qv):
            continue
        kw  = str(row[col_kw]).strip()
        lp  = str(row[col_lp]).strip()
        # Strip query strings from LP for cleaner matching
        lp_clean = lp.split('?')[0].rstrip('/')
        if not lp_clean:
            lp_clean = '/'
        try:
            ses = float(str(row[col_ses]).replace(',', '.').replace(' ', '') or 0)
            qv  = float(str(row[col_qv]).replace(',', '.').replace(' ', '') or 0)
        except ValueError:
            continue
        if not kw or kw.startswith('#'):
            continue
        rows.append({'keyword': kw, 'lp': lp_clean, 'sessions': ses, 'key_events': qv})

    print(f"  Parsed {len(rows)} GA4 rows")
    return rows

# ---------------------------------------------------------------------------
# Step 2: Calculate SEM QV per keyword (Thomas's methodology)
# ---------------------------------------------------------------------------
def calculate_sem_qv(ga4_rows):
    """
    Returns dict: normalized_keyword -> attributed_qv_sem (float)
    """
    # Aggregate per LP
    lp_totals = defaultdict(lambda: {'sessions': 0.0, 'key_events': 0.0})
    for row in ga4_rows:
        lp_totals[row['lp']]['sessions']   += row['sessions']
        lp_totals[row['lp']]['key_events'] += row['key_events']

    print(f"\nLP aggregation: {len(lp_totals)} unique landing pages")
    total_key_events = sum(v['key_events'] for v in lp_totals.values())
    print(f"Total key events in GA4 export: {total_key_events:.2f}")

    # LP QV rates
    lp_rates = {}
    for lp, totals in lp_totals.items():
        if totals['sessions'] > 0:
            lp_rates[lp] = totals['key_events'] / totals['sessions']
        else:
            lp_rates[lp] = 0.0

    # Attribute QV per keyword+LP, then sum per keyword
    kw_qv = defaultdict(float)
    for row in ga4_rows:
        lp = row['lp']
        lp_total_sessions = lp_totals[lp]['sessions']
        lp_total_qv = lp_totals[lp]['key_events']
        if lp_total_sessions > 0 and row['sessions'] > 0:
            attributed = (row['sessions'] / lp_total_sessions) * lp_total_qv
        else:
            attributed = 0.0
        kw_qv[normalize(row['keyword'])] += attributed

    total_attributed = sum(kw_qv.values())
    print(f"Total attributed QV SEM across all keywords: {total_attributed:.2f}")
    print(f"Verification delta vs GA4 total: {abs(total_attributed - total_key_events):.4f}")
    return dict(kw_qv)

# ---------------------------------------------------------------------------
# Step 3: Read masterlist
# ---------------------------------------------------------------------------
def read_masterlist(token):
    print("\nReading masterlist...")
    raw = sheets_get(token, MASTER_FILE_ID, f"'{MASTER_TAB}'!A1:BF5000")
    if not raw or len(raw) < 2:
        sys.exit("ERROR: Masterlist returned no data")

    headers = [str(h).strip() for h in raw[0]]
    print(f"  Masterlist: {len(raw)-1} data rows, {len(headers)} columns")
    print(f"  Last column: {headers[-1]}")

    # Find key column indices
    def col_idx(name):
        for i, h in enumerate(headers):
            if h.strip() == name.strip():
                return i
        return None

    idx = {
        'keyword':      col_idx('Keyword'),
        'topics':       col_idx('TOPICS'),
        'seo_pos':      col_idx('Position SE Ranking'),
        'vol':          col_idx('Average Search Volume'),
        'seo_clicks_p1': col_idx('Clics SEO Q1 2026'),
        'conv_sem_p1':  col_idx(COL_AC_NAME),
        'conv_seo_p1':  col_idx('Conversions SEO Q1 2026'),
        'sem_rec':      col_idx(COL_BF_NAME),   # may be None if column doesn't exist yet
    }
    print(f"  Column positions: {idx}")

    # Verify required columns exist
    for k in ['keyword', 'topics', 'seo_pos', 'vol', 'seo_clicks_p1', 'conv_sem_p1']:
        if idx[k] is None:
            sys.exit(f"ERROR: Could not find column '{k}' in masterlist headers")

    rows = []
    for i, row in enumerate(raw[1:], start=2):  # row 2 = first data row (1-indexed for Sheets)
        kw = str(row[idx['keyword']]).strip() if len(row) > idx['keyword'] else ''
        if not kw:
            continue
        rows.append({
            'row_num': i,
            'keyword': kw,
            'norm_kw': normalize(kw),
            'topics': str(row[idx['topics']]).strip() if len(row) > idx['topics'] else '',
            'seo_pos': str(row[idx['seo_pos']]).strip() if len(row) > idx['seo_pos'] else '',
            'vol': str(row[idx['vol']]).strip() if len(row) > idx['vol'] else '',
            'seo_clicks_p1': str(row[idx['seo_clicks_p1']]).strip() if len(row) > idx['seo_clicks_p1'] else '',
        })

    print(f"  Loaded {len(rows)} keyword rows from masterlist")
    return headers, idx, rows

# ---------------------------------------------------------------------------
# Step 4: Build SEM recommendation tags
# ---------------------------------------------------------------------------
def tag_sem_recommendation(row, qv_sem):
    """Return recommendation string for a BRAND keyword."""
    if row['topics'].upper() != 'BRAND':
        return ''
    # Skip known competitor terms regardless of TOPICS classification
    if normalize(row['keyword']) in COMPETITOR_BLOCKLIST:
        return ''

    # Parse SEO position
    try:
        seo_pos = float(row['seo_pos'])
    except (ValueError, TypeError):
        seo_pos = 999

    # Parse SEO coverage: SEO clicks / search volume
    try:
        seo_clicks = float(str(row['seo_clicks_p1']).replace('%', '').replace(',', ''))
        vol = float(str(row['vol']).replace(',', ''))
        seo_cov = seo_clicks / vol if vol > 0 else 0.0
    except (ValueError, TypeError):
        seo_cov = 0.0

    qv = qv_sem if qv_sem else 0.0

    if seo_cov > SEO_COV_THRESHOLD and seo_pos <= SEO_POS_THRESHOLD and qv == 0:
        return 'Exclude'
    elif qv > 0 and seo_cov < SEO_COV_THRESHOLD:
        return 'Keep-Active'
    elif qv > 0 and seo_cov >= SEO_COV_THRESHOLD:
        return 'Keep-Test'
    else:
        return ''

# ---------------------------------------------------------------------------
# Step 5: Write to masterlist
# ---------------------------------------------------------------------------
def write_to_masterlist(token, headers, idx, rows, kw_qv):
    print("\nPreparing writes...")

    # Determine column letters
    ac_col = col_letter(idx['conv_sem_p1'])

    # Check if BF column exists; if not, write header first
    bf_col_idx = idx.get('sem_rec')
    if bf_col_idx is None:
        bf_col_idx = len(headers)   # append after last column
    bf_col = col_letter(bf_col_idx)

    print(f"  Writing QV SEM to column {ac_col} ({COL_AC_NAME})")
    print(f"  Writing SEM Recommendation to column {bf_col} ({COL_BF_NAME})")

    # Build write data
    ac_updates = []   # [[value]] per row
    bf_updates = []   # [[value]] per row
    ac_ranges  = []
    bf_ranges  = []

    matched = 0
    unmatched = []

    for row in rows:
        qv = kw_qv.get(row['norm_kw'], None)
        if qv is not None:
            matched += 1

        qv_val = round(qv, 4) if qv else ''
        rec_val = tag_sem_recommendation(row, qv)

        r = row['row_num']
        ac_ranges.append({
            'range': f"'{MASTER_TAB}'!{ac_col}{r}",
            'values': [[qv_val]]
        })
        bf_ranges.append({
            'range': f"'{MASTER_TAB}'!{bf_col}{r}",
            'values': [[rec_val]]
        })

        if qv is None:
            unmatched.append(row['keyword'])

    print(f"  Keywords matched to GA4 data: {matched}/{len(rows)}")
    print(f"  Unmatched (will write blank): {len(unmatched)}")
    if unmatched[:5]:
        print(f"  Sample unmatched: {unmatched[:5]}")

    # Build contiguous column arrays (row_num 2..N)
    min_row = min(r['row_num'] for r in rows)   # should be 2
    max_row = max(r['row_num'] for r in rows)
    row_map = {r['row_num']: r for r in rows}

    ac_col_values = []  # [[val], [val], ...]
    bf_col_values = []
    for rn in range(min_row, max_row + 1):
        r = row_map.get(rn)
        if r is None:
            ac_col_values.append([''])
            bf_col_values.append([''])
        else:
            qv = kw_qv.get(r['norm_kw'], None)
            qv_val = round(qv, 4) if qv else ''
            rec_val = tag_sem_recommendation(r, qv)
            ac_col_values.append([qv_val])
            bf_col_values.append([rec_val])

    # Expand sheet if BF column doesn't exist yet
    if idx.get('sem_rec') is None:
        sheet_id, current_cols = get_sheet_props(token, MASTER_FILE_ID, MASTER_TAB)
        needed_cols = bf_col_idx + 1  # BF is index 57 (0-based), need at least 58 columns
        if current_cols < needed_cols:
            cols_to_add = needed_cols - current_cols
            print(f"\n  Expanding sheet from {current_cols} to {needed_cols} columns (+{cols_to_add})")
            expand_sheet_columns(token, MASTER_FILE_ID, sheet_id, cols_to_add)
        print(f"\n  Adding new column header: {bf_col}1 = '{COL_BF_NAME}'")
        sheets_update_range(token, MASTER_FILE_ID, f"'{MASTER_TAB}'!{bf_col}1", [[COL_BF_NAME]])

    # Write AC column in one shot
    ac_range = f"'{MASTER_TAB}'!{ac_col}{min_row}:{ac_col}{max_row}"
    print(f"\n  Writing {len(ac_col_values)} QV SEM values → {ac_range}...")
    sheets_update_range(token, MASTER_FILE_ID, ac_range, ac_col_values)
    print(f"  Done.")

    # Write BF column in one shot
    bf_range = f"'{MASTER_TAB}'!{bf_col}{min_row}:{bf_col}{max_row}"
    print(f"\n  Writing {len(bf_col_values)} SEM Recommendation tags → {bf_range}...")
    sheets_update_range(token, MASTER_FILE_ID, bf_range, bf_col_values)
    print(f"  Done.")

    return matched, len(unmatched)

# ---------------------------------------------------------------------------
# Verification summary
# ---------------------------------------------------------------------------
def print_summary(kw_qv, rows, matched):
    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)
    total_qv = sum(v for v in kw_qv.values())
    assigned_qv = sum(kw_qv.get(r['norm_kw'], 0) for r in rows if kw_qv.get(r['norm_kw']))
    print(f"Total QV SEM in GA4 export:           {total_qv:.2f}")
    print(f"Total QV SEM assigned to masterlist:  {assigned_qv:.2f}")
    print(f"Unassigned (keywords not in masterlist): {total_qv - assigned_qv:.2f}")
    print(f"Keywords matched:  {matched}")
    print(f"Keywords in masterlist: {len(rows)}")

    # Explicit check for anchor brand keyword
    anchor_terms = ['oikos', 'oikos greek yogurt', 'oikos yogurt']
    print(f"\nAnchor keyword audit:")
    for term in anchor_terms:
        norm = normalize(term)
        in_masterlist = any(r['norm_kw'] == norm for r in rows)
        qv_val = kw_qv.get(norm, None)
        in_ga4 = norm in kw_qv
        print(f"  '{term}': in_masterlist={in_masterlist}, in_ga4={in_ga4}, QV SEM={qv_val}")

    # Top 10 by QV SEM
    brand_recs = [(r['keyword'], kw_qv.get(r['norm_kw'], 0), tag_sem_recommendation(r, kw_qv.get(r['norm_kw'], 0)))
                  for r in rows if r['topics'].upper() == 'BRAND']
    brand_recs.sort(key=lambda x: -x[1])
    print(f"\nTop 10 BRAND keywords by QV SEM:")
    for kw, qv, rec in brand_recs[:10]:
        print(f"  {kw:<40} QV={qv:>8.2f}  Rec={rec}")

    # SEM Recommendation counts
    from collections import Counter
    rec_counts = Counter(tag_sem_recommendation(r, kw_qv.get(r['norm_kw'], 0)) for r in rows)
    print(f"\nSEM Recommendation distribution (BRAND keywords):")
    for label, count in sorted(rec_counts.items()):
        if label:
            print(f"  {label:<15}: {count}")
    print("="*60)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("="*60)
    print("SEM QV Attribution — Oikos USA OneSearch")
    print("="*60)

    env   = load_env()
    token = get_token(env)
    print("Authenticated ✓")

    ga4_rows = read_ga4_ads(token)
    kw_qv    = calculate_sem_qv(ga4_rows)
    headers, idx, rows = read_masterlist(token)
    matched, unmatched = write_to_masterlist(token, headers, idx, rows, kw_qv)
    print_summary(kw_qv, rows, matched)

    print("\nDone. Masterlist updated.")

if __name__ == '__main__':
    main()
