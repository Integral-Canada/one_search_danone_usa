#!/usr/bin/env python3
"""
Fetch monthly search volumes (Oct 2025–Mar 2026) from SE Ranking for 14,273 keywords
and write them to columns I–N of the keyword study Google Sheet.

Sheet: 1kiOgeo5J66tAngETUGVv1CFX072g4rnDiWKLf6KP7co  rows 2–14274
Mode: fill-in — only fetches rows where column I is currently empty.
Batch size: 500 (confirmed safe; 1000 caused intermittent API errors)
"""
import json, time, urllib.request, urllib.parse, sys

# ── Config ────────────────────────────────────────────────────────────────────
SHEET_ID    = "1kiOgeo5J66tAngETUGVv1CFX072g4rnDiWKLf6KP7co"
SER_API_KEY = "c437b58f-5f66-7af2-b04f-cb20ef7f3358"
BATCH_SIZE  = 500
MONTHS      = ["2025-10-01","2025-11-01","2025-12-01","2026-01-01","2026-02-01","2026-03-01"]
ENV_FILE    = "/Users/carlaklaasen/claude_code/.env"

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

def sheets_get(token, range_):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{range_}?valueRenderOption=UNFORMATTED_VALUE"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read()).get("values", [])

def sheets_batch_update(token, data_ranges):
    """Write multiple ranges in one API call. data_ranges = list of (range_str, values)."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values:batchUpdate"
    payload = {
        "valueInputOption": "RAW",
        "data": [
            {"range": r, "majorDimension": "ROWS", "values": v}
            for r, v in data_ranges
        ]
    }
    body = json.dumps(payload).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
            return resp.get("totalUpdatedCells", 0)
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f"    Sheets write attempt {attempt+1} failed: {e} — waiting {wait}s", flush=True)
            time.sleep(wait)
    return 0

def ser_export(keywords_batch):
    """Call SE Ranking bulk export. Returns {keyword_lower: {month: volume}}."""
    url = "https://api.seranking.com/v1/keywords/export?source=us"
    body = json.dumps({"keywords": keywords_batch}).encode()
    req = urllib.request.Request(url, data=body,
        headers={"Authorization": f"Token {SER_API_KEY}", "Content-Type": "application/json"})
    backoff = [15, 30, 60, 120]
    for attempt in range(4):
        try:
            raw = urllib.request.urlopen(req, timeout=90).read()
            rows = json.loads(raw)
            if isinstance(rows, dict):
                print(f"    API error dict: {rows}", flush=True)
                time.sleep(backoff[attempt])
                continue
            if not isinstance(rows, list) or (rows and not isinstance(rows[0], dict)):
                print(f"    Unexpected response type: {type(rows)}, first item: {type(rows[0]) if rows else 'n/a'}", flush=True)
                time.sleep(backoff[attempt])
                continue
            result = {}
            for r in rows:
                if not r.get("is_data_found"): continue
                trend = r.get("history_trend") or {}
                if not isinstance(trend, dict): trend = {}
                result[r["keyword"].lower()] = {m: trend.get(m, 0) for m in MONTHS}
            return result
        except Exception as e:
            wait = backoff[attempt]
            print(f"    Attempt {attempt+1} failed: {e} — waiting {wait}s", flush=True)
            time.sleep(wait)
    return {}

def main():
    print("Loading credentials…", flush=True)
    env   = load_env()
    token = get_token(env)

    print("Reading keywords and existing volumes from sheet…", flush=True)
    kw_rows  = sheets_get(token, "A2:A14274")
    vol_rows = sheets_get(token, "I2:I14274")  # check column I for emptiness

    keywords = [r[0] if r else "" for r in kw_rows]
    total    = len(keywords)

    # Identify rows that still need data (column I is empty or missing)
    missing_indices = []
    for i, kw in enumerate(keywords):
        existing = vol_rows[i][0] if i < len(vol_rows) and vol_rows[i] else ""
        if kw and str(existing).strip() == "":
            missing_indices.append(i)

    print(f"  {total} keywords total, {len(missing_indices)} still need volumes", flush=True)

    if not missing_indices:
        print("All rows already have data. Nothing to do.", flush=True)
        return

    # ── Fetch volumes for missing keywords only ──────────────────────────────
    missing_kws   = [keywords[i] for i in missing_indices]
    batches_kw    = [missing_kws[i:i+BATCH_SIZE] for i in range(0, len(missing_kws), BATCH_SIZE)]
    batches_idx   = [missing_indices[i:i+BATCH_SIZE] for i in range(0, len(missing_indices), BATCH_SIZE)]

    print(f"\nFetching SE Ranking volumes: {len(batches_kw)} batches of up to {BATCH_SIZE}…", flush=True)

    vol_map = {}
    for i, (batch_kw, batch_idx) in enumerate(zip(batches_kw, batches_idx)):
        non_empty = [k for k in batch_kw if k]
        print(f"  Batch {i+1}/{len(batches_kw)}: {len(non_empty)} keywords…", end=" ", flush=True)
        if non_empty:
            result = ser_export(non_empty)
            vol_map.update(result)
            print(f"matched {len(result)}", flush=True)
        else:
            print("skipped (empty)", flush=True)
        if i < len(batches_kw) - 1:
            time.sleep(8)  # 8s between batches to avoid rate limiting

    print(f"\nTotal keywords fetched: {len(vol_map)}", flush=True)

    # ── Write results back — only update rows that were fetched ─────────────
    # Refresh token before writing
    token = get_token(env)

    # Group consecutive rows for efficient API calls
    # Build a dict: row_index → [oct, nov, dec, jan, feb, mar]
    updates = {}
    written = 0
    for idx in missing_indices:
        kw   = keywords[idx]
        data = vol_map.get(kw.lower(), {})
        if data:
            updates[idx] = [data.get(m, "") for m in MONTHS]
            written += 1

    print(f"Keywords with new data to write: {written}", flush=True)

    if not updates:
        print("No new data retrieved. All missing keywords returned no results.", flush=True)
        return

    # Write in contiguous chunks (group consecutive indices)
    sorted_indices = sorted(updates.keys())
    chunks = []
    chunk_start = sorted_indices[0]
    chunk_rows  = [updates[sorted_indices[0]]]

    for prev, curr in zip(sorted_indices, sorted_indices[1:]):
        if curr == prev + 1:
            chunk_rows.append(updates[curr])
        else:
            chunks.append((chunk_start, chunk_rows))
            chunk_start = curr
            chunk_rows  = [updates[curr]]
    chunks.append((chunk_start, chunk_rows))

    WRITE_CHUNK = 50  # ranges per batchUpdate call
    print(f"\nWriting {len(chunks)} contiguous range(s) in batches of {WRITE_CHUNK} to columns I–N…", flush=True)
    total_cells = 0

    for batch_start in range(0, len(chunks), WRITE_CHUNK):
        batch = chunks[batch_start:batch_start + WRITE_CHUNK]
        data_ranges = []
        for start_idx, rows in batch:
            row_start = start_idx + 2
            row_end   = row_start + len(rows) - 1
            data_ranges.append((f"I{row_start}:N{row_end}", rows))
        cells = sheets_batch_update(token, data_ranges)
        total_cells += cells
        last_range = data_ranges[-1][0]
        print(f"  Batch write {batch_start//WRITE_CHUNK + 1}: {len(data_ranges)} ranges → {cells} cells (up to {last_range})", flush=True)
        if batch_start + WRITE_CHUNK < len(chunks):
            time.sleep(2)  # brief pause between batchUpdate calls

    print(f"\nDone. {total_cells} cells updated.", flush=True)

if __name__ == "__main__":
    main()
