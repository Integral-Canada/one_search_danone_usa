#!/usr/bin/env python3
"""
OneSearch Dashboard Builder — outer entry point.

Runs the validation layer, then builds the HTML dashboard.
Use --finalize to bake content.json into static HTML (no JSON loader in output).

Usage:
    python3 build_dashboard.py --brand oikos-usa
    python3 build_dashboard.py --brand oikos-usa --finalize
    python3 build_dashboard.py --brand oikos-usa --skip-validation
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from pipeline.utils import load_brand_config, load_env, get_token, sheets_get
from pipeline.validate import validate_masterlist


def raw_to_dicts(raw_values: list) -> tuple:
    if not raw_values:
        return [], []
    headers = [str(h) for h in raw_values[0]]
    rows = []
    for row in raw_values[1:]:
        d = {headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))}
        rows.append(d)
    return headers, rows


def load_content(brand_key: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), 'brands', brand_key, 'content.json')
    if not os.path.isfile(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def bake_content(brand_key: str, html_path: str) -> None:
    """Replace the dynamic content.json loader in HTML with static inlined content.

    When --finalize is set, the dashboard has no dependency on an external JSON file —
    all recommendation cards and commentary are baked directly into the HTML.
    """
    content = load_content(brand_key)
    if not content:
        print('  --finalize: no content.json found — skipping bake', flush=True)
        return

    with open(html_path, encoding='utf-8') as f:
        html = f.read()

    recos   = content.get('recommendations', [])
    comment = content.get('commentary', {})

    # Inline recommendations as a JS variable
    recos_js   = f'const CONTENT_RECOS = {json.dumps(recos, ensure_ascii=False, indent=2)};'
    comment_js = f'const CONTENT_COMMENTARY = {json.dumps(comment, ensure_ascii=False, indent=2)};'
    static_block = f'\n<script id="os-content-static">\n{recos_js}\n{comment_js}\n</script>\n'

    # Remove any dynamic fetch() loader for content.json
    import re
    html = re.sub(
        r'fetch\s*\(\s*[\'"].*?content\.json[\'"][\s\S]*?\.catch\s*\([^)]*\)\s*;',
        '',
        html,
    )
    # Remove <script src="...content.json..."> tags if any
    html = re.sub(r'<script[^>]*content\.json[^>]*></script>', '', html)

    # Inject static block right before </head>
    if '<!-- OS_CONTENT_STATIC -->' in html:
        html = html.replace('<!-- OS_CONTENT_STATIC -->', static_block, 1)
    else:
        html = html.replace('</head>', static_block + '</head>', 1)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'  --finalize: {len(recos)} reco cards + commentary baked into HTML', flush=True)


def run_build_html(brand_key: str) -> int:
    """Run scripts/build_html.py as a subprocess. Returns exit code."""
    script = os.path.join(os.path.dirname(__file__), 'scripts', 'build_html.py')
    if not os.path.isfile(script):
        print(f'ERROR: build_html.py not found at {script}', flush=True)
        return 1
    result = subprocess.run(
        [sys.executable, script, '--brand', brand_key],
        cwd=os.path.dirname(__file__),
    )
    return result.returncode


def resolve_output_path(brand_key: str) -> str:
    """Derive the output HTML path that build_html.py writes to."""
    dashboards_dir = os.path.join(os.path.dirname(__file__), 'dashboards', brand_key)
    return os.path.join(dashboards_dir, f'{brand_key.replace("/", "-")}_onesearch_dashboard.html')


def main() -> None:
    parser = argparse.ArgumentParser(description='OneSearch Dashboard Builder')
    parser.add_argument('--brand',           default='oikos-usa', help='Brand handle')
    parser.add_argument('--finalize',        action='store_true',
                        help='Bake content.json into static HTML (no dynamic loader)')
    parser.add_argument('--skip-validation', action='store_true',
                        help='Skip Masterlist validation step')
    args = parser.parse_args()
    brand_key = args.brand

    print('=' * 64, flush=True)
    print(f'build_dashboard.py  brand={brand_key}', flush=True)
    print('=' * 64, flush=True)

    cfg = load_brand_config(brand_key)
    sheets_cfg = cfg.get('sheets', {})
    master_id  = sheets_cfg.get('master_id')
    master_tab = sheets_cfg.get('master_tab', 'Listing')

    # ── Step 1: Validate Masterlist ─────────────────────────────────────────
    if args.skip_validation:
        print('\nStep 1: Validation skipped (--skip-validation)', flush=True)
    else:
        print('\nStep 1: Validating Masterlist…', flush=True)
        if not master_id:
            print('  WARNING: master_id not in config — skipping validation', flush=True)
        else:
            try:
                env   = load_env()
                token = get_token(env)
                raw   = sheets_get(token, master_id, f"'{master_tab}'!A1:BF")
                if raw:
                    headers, rows = raw_to_dicts(raw)
                    ok, report    = validate_masterlist(rows, headers, cfg)
                    print(report, flush=True)
                    if not ok:
                        print('\nValidation FAILED — fix blocking issues before building dashboard.', flush=True)
                        print('Run with --skip-validation to bypass (not recommended).', flush=True)
                        sys.exit(1)
                else:
                    print('  WARNING: Could not read Masterlist — skipping validation', flush=True)
            except Exception as exc:
                print(f'  WARNING: Validation error ({exc}) — proceeding anyway', flush=True)

    # ── Step 2: Build HTML ──────────────────────────────────────────────────
    print('\nStep 2: Building HTML dashboard…', flush=True)
    exit_code = run_build_html(brand_key)
    if exit_code != 0:
        print(f'\nERROR: build_html.py exited with code {exit_code}', flush=True)
        sys.exit(exit_code)

    output_path = resolve_output_path(brand_key)

    # ── Step 3: Bake content.json (--finalize) ──────────────────────────────
    if args.finalize:
        print('\nStep 3: Baking content.json into static HTML (--finalize)…', flush=True)
        if os.path.isfile(output_path):
            bake_content(brand_key, output_path)
        else:
            print(f'  WARNING: output file not found at {output_path}', flush=True)
    else:
        print('\nStep 3: --finalize not set — content.json will be loaded dynamically', flush=True)

    # ── Done ────────────────────────────────────────────────────────────────
    print('\n' + '=' * 64, flush=True)
    if os.path.isfile(output_path):
        size_kb = os.path.getsize(output_path) / 1024
        print(f'Done.  Output: {output_path}', flush=True)
        print(f'       Size  : {size_kb:.0f} KB', flush=True)
        print(f'       Open  : open "{output_path}"', flush=True)
    else:
        print(f'Done (output path not confirmed: {output_path})', flush=True)
    print('=' * 64, flush=True)


if __name__ == '__main__':
    main()
