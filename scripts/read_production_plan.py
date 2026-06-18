"""
read_production_plan.py
-----------------------
Read the Oikos USA 2026 SEO Production Plan Google Sheet and print
structured content for Phase F dashboard integration.

Sheet: 2026 - SEO Production Plan - DANONE USA - On Site - Oikos
ID: 13ZKd5UVG_OcvRS9Wri8c8XSbwqiCguiJBDvUuUN9hbg
Tabs: ON SITE (OIKOS) - Content Strategy
      OFF SITE (OIKOS) - Content Strategy
"""

import os, sys, json, time, urllib.request, urllib.parse

PLAN_FILE_ID = "13ZKd5UVG_OcvRS9Wri8c8XSbwqiCguiJBDvUuUN9hbg"
ON_SITE_TAB  = "ON SITE (OIKOS) - Content Strategy"
OFF_SITE_TAB = "OFF SITE (OIKOS) - Content Strategy"

def load_env():
    env = {}
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
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

def get_sheet_names(token, file_id):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{file_id}?fields=sheets.properties.title"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    return [s['properties']['title'] for s in data.get('sheets', [])]

def main():
    env = load_env()
    token = get_token(env)
    print("Authenticated ✓")

    # List available sheet tabs
    tabs = get_sheet_names(token, PLAN_FILE_ID)
    print(f"\nAvailable tabs ({len(tabs)}):")
    for t in tabs:
        print(f"  - {repr(t)}")

    # Find matching tabs (fuzzy)
    on_site_tab  = next((t for t in tabs if 'ON SITE'  in t.upper() and 'OIKOS' in t.upper()), None)
    off_site_tab = next((t for t in tabs if 'OFF SITE' in t.upper() and 'OIKOS' in t.upper()), None)

    print(f"\nOn-site tab:  {repr(on_site_tab)}")
    print(f"Off-site tab: {repr(off_site_tab)}")

    for label, tab in [('ON SITE', on_site_tab), ('OFF SITE', off_site_tab)]:
        if not tab:
            print(f"\n{label}: tab not found")
            continue
        print(f"\n{'='*60}")
        print(f"{label} TAB: {repr(tab)}")
        print('='*60)
        rows = sheets_get(token, PLAN_FILE_ID, f"'{tab}'!A1:Z200")
        if not rows:
            print("  (empty)")
            continue
        print(f"  {len(rows)} rows, up to {max(len(r) for r in rows)} cols")
        print()
        for i, row in enumerate(rows[:80]):
            if any(cell.strip() for cell in row):
                cells = [str(c)[:60] for c in row]
                print(f"  Row {i+1:>3}: {' | '.join(cells)}")

if __name__ == '__main__':
    main()
