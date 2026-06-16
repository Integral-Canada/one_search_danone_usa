#!/usr/bin/env python3
"""
Patch commentary notes from a JSON export back into the HTML dashboard.

For each field-id in the JSON with non-empty text:
  - finds the matching contenteditable div in the HTML
  - replaces its placeholder text with the analyst commentary
  - removes the data-is-placeholder attribute (if present)
  - the nearby <ul> AI-bullet list is a SIBLING element and is never touched,
    so both the analyst commentary AND the AI bullets appear in the final HTML

For field-ids NOT in the JSON (left blank):
  - leaves the div exactly as-is

Run:
    python3 patch_commentary.py commentary.json
    python3 patch_commentary.py commentary.json --html one_search_html/oikos_usa_onesearch_dashboard.html
    python3 patch_commentary.py commentary.json --out one_search_html/oikos_usa_onesearch_dashboard_annotated.html
"""
import argparse
import html as _html_escape
import json
import os
import re
import sys


DEFAULT_HTML = os.path.join(
    os.path.dirname(__file__),
    'one_search_html', 'oikos_usa_onesearch_dashboard.html',
)


def patch_field(html_text, field_id, commentary_text):
    """Replace the inner content of a contenteditable div with field_id.

    Matches:
      <div ... data-field-id="FIELD_ID" ... data-is-placeholder="1">ANYTHING</div>
    or:
      <div ... data-field-id="FIELD_ID" ...>ANYTHING</div>

    and replaces ANYTHING with the escaped commentary text, removing
    data-is-placeholder if present.
    """
    escaped = _html_escape.escape(commentary_text)

    # Match the opening tag (may span no newlines — all one line in the generated HTML)
    # then capture content up to the closing </div>
    pattern = (
        r'(<div\b[^>]*\bdata-field-id="' + re.escape(field_id) + r'"[^>]*?)'
        r'(\s+data-is-placeholder="[^"]*")?'   # optional placeholder attribute
        r'([^>]*>)'                              # rest of opening tag
        r'([\s\S]*?)'                            # current content
        r'(</div>)'                              # closing tag
    )

    def _replacer(m):
        opening_before_attr = m.group(1)
        # group 2 = data-is-placeholder attr (drop it)
        rest_of_tag        = m.group(3)
        # group 4 = old content (replace)
        closing            = m.group(5)
        return opening_before_attr + rest_of_tag + escaped + closing

    new_html, count = re.subn(pattern, _replacer, html_text, count=1)
    return new_html, count


def main():
    parser = argparse.ArgumentParser(
        description='Patch commentary JSON into the OneSearch HTML dashboard.')
    parser.add_argument('json_file', help='Path to the exported commentary JSON file')
    parser.add_argument('--html', default=DEFAULT_HTML,
                        help=f'HTML file to patch (default: {DEFAULT_HTML})')
    parser.add_argument('--out', default=None,
                        help='Output path (default: overwrite --html in-place)')
    args = parser.parse_args()

    # ── Load JSON ────────────────────────────────────────────────────────────────
    with open(args.json_file, encoding='utf-8') as f:
        data = json.load(f)

    fields = {k: v for k, v in data.items()
              if not k.startswith('_') and isinstance(v, str) and v.strip()}

    if not fields:
        print('No filled commentary fields found in JSON — nothing to patch.')
        sys.exit(0)

    print(f'Commentary fields to apply: {len(fields)}')
    for fid, text in fields.items():
        print(f'  [{fid}] {text[:72]}{"…" if len(text) > 72 else ""}')

    # ── Load HTML ────────────────────────────────────────────────────────────────
    if not os.path.exists(args.html):
        print(f'\nERROR: HTML file not found: {args.html}')
        sys.exit(1)

    with open(args.html, encoding='utf-8') as f:
        html = f.read()

    print(f'\nHTML loaded: {len(html):,} chars from {args.html}')

    # ── Apply patches ────────────────────────────────────────────────────────────
    patched = 0
    not_found = []
    for field_id, text in fields.items():
        html, count = patch_field(html, field_id, text)
        if count:
            patched += 1
            print(f'  ✓ Patched [{field_id}]')
        else:
            not_found.append(field_id)
            print(f'  ✗ Not found in HTML: [{field_id}]')

    # ── Write output ─────────────────────────────────────────────────────────────
    out_path = args.out or args.html
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f'\nDone: {patched}/{len(fields)} fields patched → {out_path}')
    if not_found:
        print(f'  Not matched: {not_found}')
        print('  (field-ids must exactly match data-field-id values in the HTML)')


if __name__ == '__main__':
    main()
