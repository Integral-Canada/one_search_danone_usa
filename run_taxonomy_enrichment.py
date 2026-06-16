#!/usr/bin/env python3
"""
Standalone taxonomy enrichment for the Oikos USA masterlist.
Reads keywords from the Listing tab, classifies empty taxonomy columns
via Gemini 2.0 Flash Lite (free tier), and writes results back.

Run:
    python3 run_taxonomy_enrichment.py
    python3 run_taxonomy_enrichment.py --brand oikos-usa
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from one_search.enrich import enrich_taxonomy

ENV_FILE = "/Users/carlaklaasen/claude_code/.env"

CLIENTS = {
    'oikos-usa': {
        'master_id':  '1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU',
        'master_tab': 'Listing',
    },
}


def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--brand', default='oikos-usa')
    args = parser.parse_args()

    cfg = CLIENTS.get(args.brand)
    if not cfg:
        print(f"Unknown brand '{args.brand}'. Available: {list(CLIENTS)}")
        sys.exit(1)

    print(f"Taxonomy enrichment — {args.brand}", flush=True)
    print(f"  Sheet: {cfg['master_id'][:20]}…  Tab: {cfg['master_tab']}", flush=True)

    env           = load_env()
    anthropic_key = env.get('ANTHROPIC_API_KEY', '')
    if not anthropic_key:
        print("ERROR: ANTHROPIC_API_KEY not found in .env")
        sys.exit(1)

    token = get_token(env)
    print("  Token OK", flush=True)

    enrich_taxonomy(token, cfg['master_id'], cfg['master_tab'], anthropic_key)

    print("\nDone.", flush=True)


if __name__ == "__main__":
    main()
