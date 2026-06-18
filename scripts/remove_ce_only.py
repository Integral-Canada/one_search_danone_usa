"""
remove_ce_only.py
Remove every <div contenteditable="true"> from the Oikos dashboard.
Touches NOTHING else — no JS functions, no toolbar, no CSS.
"""
import re

DASH = '/Users/carlaklaasen/claude_code/one_search/dashboards/oikos_usa_onesearch_dashboard.html'

with open(DASH, encoding='utf-8') as f:
    html = f.read()

before = html.count('contenteditable="true"')
print(f'Before: {before} contenteditable="true" occurrences')

# ── 1. Static HTML: multi-line and single-line empty contenteditable divs ────
# These are all empty (></div>), so [\s\S]*? stops at the first ></div>
html, n1 = re.subn(
    r'<div contenteditable="true"[\s\S]*?></div>',
    '',
    html
)
print(f'  HTML divs removed: {n1}')

# ── 2. JS string blocks in SQR and renderRecommendations ─────────────────────
# Pattern: one or more lines of  \n    +'<div contenteditable...  through  +'></div>'
html, n2 = re.subn(
    r"\n[ \t]+\+'<div contenteditable=\"true\"'[\s\S]*?\+'></div>'",
    '',
    html
)
print(f'  JS string blocks removed: {n2}')

after = html.count('contenteditable="true"')
print(f'After:  {after} contenteditable="true" occurrences remaining')

if after > 0:
    for i, line in enumerate(html.split('\n'), 1):
        if 'contenteditable="true"' in line:
            print(f'  STILL PRESENT line {i}: {line[:120]}')

with open(DASH, 'w', encoding='utf-8') as f:
    f.write(html)
print('Done.')
