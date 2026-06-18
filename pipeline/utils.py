"""Shared utilities for the OneSearch pipeline.

Functions here are used by run_pipeline.py, enrich.py, sem_qv.py, and
build_html.py. Centralises helpers that were previously duplicated across
run_onesearch.py, enrich.py, and sem_qv_attribution.py.
"""
import json
import os
import re
import urllib.parse
import urllib.request


# ── Brand config loading ───────────────────────────────────────────────────────

_BRANDS_DIR = os.path.join(os.path.dirname(__file__), '..', 'brands')


def load_brand_config(handle: str) -> dict:
    """Load brands/<handle>/config.json merged with brands/defaults.json.

    Keys in config.json take precedence over defaults.json. Top-level dict
    keys are merged shallowly; nested dicts are NOT deep-merged (use explicit
    keys in config.json if you need to override a nested default).
    """
    defaults_path = os.path.join(_BRANDS_DIR, 'defaults.json')
    brand_path = os.path.join(_BRANDS_DIR, handle, 'config.json')

    if not os.path.exists(brand_path):
        raise FileNotFoundError(
            f"Brand config not found: {brand_path}\n"
            f"Create brands/{handle}/config.json to use this brand handle."
        )

    defaults = {}
    if os.path.exists(defaults_path):
        with open(defaults_path, encoding='utf-8') as f:
            defaults = json.load(f)

    with open(brand_path, encoding='utf-8') as f:
        brand = json.load(f)

    merged = {**defaults, **brand}
    return merged


def load_content(handle: str) -> dict:
    """Load brands/<handle>/content.json. Returns empty structure if missing."""
    path = os.path.join(_BRANDS_DIR, handle, 'content.json')
    if not os.path.exists(path):
        return {'recommendations': [], 'commentary': {}}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ── .env loading ─────────────────────────────────────────────────────────────

def load_env(env_file: str = None) -> dict:
    """Load key=value pairs from .env file. Searches up from this file's directory."""
    if env_file is None:
        # Walk up from pipeline/ to find .env
        candidate = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
        if os.path.exists(candidate):
            env_file = candidate
        else:
            # Fallback: same directory as the calling script
            candidate2 = os.path.join(os.path.dirname(__file__), '..', '.env')
            env_file = candidate2

    env = {}
    if not os.path.exists(env_file):
        raise FileNotFoundError(f".env not found at {env_file}")

    with open(env_file, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ── Google OAuth2 token ───────────────────────────────────────────────────────

def get_token(env: dict) -> str:
    """Exchange refresh token for a short-lived access token."""
    # Prefer token file (handles expiry + refresh automatically) if available
    token_file = env.get('GOOGLE_TOKEN_FILE')
    if token_file and os.path.exists(token_file):
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            creds = Credentials.from_authorized_user_file(token_file)
            if not creds.valid and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return creds.token
        except ImportError:
            pass  # fall through to manual refresh below

    data = urllib.parse.urlencode({
        'client_id':     env['GOOGLE_CLIENT_ID'],
        'client_secret': env['GOOGLE_CLIENT_SECRET'],
        'refresh_token': env['GOOGLE_REFRESH_TOKEN'],
        'grant_type':    'refresh_token',
    }).encode()
    resp = json.loads(urllib.request.urlopen(
        urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    ).read())
    if 'access_token' not in resp:
        raise RuntimeError(f"Token refresh failed: {resp}")
    return resp['access_token']


# ── Google Sheets API helpers ─────────────────────────────────────────────────

def sheets_get(token: str, sheet_id: str, range_: str,
               render: str = 'UNFORMATTED_VALUE') -> list:
    """GET a range from Google Sheets. Returns list-of-lists or [] on 400."""
    url = (f'https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}'
           f'/values/{urllib.parse.quote(range_, safe="!:")}'
           f'?valueRenderOption={render}')
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read()).get('values', [])
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return []
        raise


def sheets_batch_update(token: str, sheet_id: str, updates: list,
                        value_input: str = 'USER_ENTERED') -> dict:
    """Write multiple ranges to Google Sheets in one batchUpdate call.

    updates: list of (range_str, values) tuples where values is a list-of-lists.
    """
    body = {
        'valueInputOption': value_input,
        'data': [{'range': r, 'values': v} for r, v in updates],
    }
    url = (f'https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}'
           f'/values:batchUpdate')
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    for attempt in range(3):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except Exception as exc:
            if attempt == 2:
                raise
            import time
            print(f"  Write attempt {attempt+1} failed: {exc} — retry in 15s", flush=True)
            time.sleep(15)


def sheets_clear(token: str, sheet_id: str, range_: str) -> None:
    """Clear a range in Google Sheets."""
    url = (f'https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}'
           f'/values/{urllib.parse.quote(range_, safe="!:")}:clear')
    req = urllib.request.Request(url, data=b'{}', headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    urllib.request.urlopen(req, timeout=60)


# ── Column utilities ──────────────────────────────────────────────────────────

def col_letter(n: int) -> str:
    """Convert 1-based column index to spreadsheet letter (1→A, 27→AA)."""
    result = ''
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def col_index(letter: str) -> int:
    """Convert spreadsheet column letter to 1-based index (A→1, AA→27)."""
    result = 0
    for ch in letter.upper():
        result = result * 26 + (ord(ch) - 64)
    return result


# ── Number parsing (re-export from normalize for single-import convenience) ──

from .normalize import clean_num, parse_pct, normalize  # noqa: F401
