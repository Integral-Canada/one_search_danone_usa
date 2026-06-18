"""
strip_commentary.py
Remove all commentary/notes infrastructure from the Oikos USA OneSearch dashboard.

Removes:
  1. Commentary CSS block (toolbar styles + contenteditable rules)
  2. Commentary toolbar <div>
  3. Inline _commentaryInitField calls in SQR and recoBody JS
  4. The commentary IIFE <script> block
"""

import re, os

DASH = '/Users/carlaklaasen/claude_code/one_search/dashboards/oikos_usa_onesearch_dashboard.html'

with open(DASH, encoding='utf-8') as f:
    html = f.read()

before = len(html)

# ── 1. Remove the commentary CSS block ────────────────────────────────────────
# Targets the entire <style> block that contains only commentary rules.
# Pattern: from the comment line through the two [contenteditable] lines.
css_block = (
    r'\n/\* Commentary toolbar.*?'
    r'\[contenteditable\]\[data-is-placeholder\]\{[^\n]*\}\n'
)
html, n1 = re.subn(css_block, '\n', html, flags=re.DOTALL)
print(f'CSS block removed: {n1} match(es)')

# ── 2. Remove the commentary toolbar <div> ────────────────────────────────────
toolbar_block = (
    r'\n<div id="commentary-toolbar">.*?</div>\n'
)
html, n2 = re.subn(toolbar_block, '\n', html, flags=re.DOTALL)
print(f'Toolbar div removed: {n2} match(es)')

# ── 3. Remove inline _commentaryInitField calls ───────────────────────────────
# Pattern: a line that is only whitespace + that call
init_call = r'\n[ \t]*if\(window\._commentaryInitField\) window\._commentaryInitField\(el\);'
html, n3 = re.subn(init_call, '', html)
print(f'_commentaryInitField calls removed: {n3} match(es)')

# ── 4. Remove the commentary IIFE <script> block ─────────────────────────────
# Targets <script>\n(function(){...})();\n</script> that contains _defaults/_store
iife_block = r'\n<script>\n\(function\(\)\{.*?\}\)\(\);\n</script>\n'
html, n4 = re.subn(iife_block, '\n', html, flags=re.DOTALL)
print(f'Commentary IIFE script removed: {n4} match(es)')

# ── Sanity check ─────────────────────────────────────────────────────────────
remaining = [ln for ln in html.split('\n')
             if 'commentary' in ln.lower() or '_commentaryInitField' in ln]
if remaining:
    print(f'\nWARNING — remaining commentary references ({len(remaining)} lines):')
    for ln in remaining[:10]:
        print('  ', ln[:120])
else:
    print('\nAll commentary references removed.')

after = len(html)
print(f'\nFile size: {before:,} → {after:,} chars (removed {before-after:,})')

with open(DASH, 'w', encoding='utf-8') as f:
    f.write(html)
print('Written.')
