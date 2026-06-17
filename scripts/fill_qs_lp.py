"""
Fill empty LP (field index 5) in QS_DATA for keywords with no landing page.

Strategy:
  1. For keywords whose campaign has other keywords with LPs → use that campaign's most common LP
  2. For BlackConquestingGoogleEXT_YES (Chobani variants) → /all-products/oikos-protein-shakes
  3. For FusionBrandGoogleEXT_YES (Oikos Fusion brand) → /all-products/fusion
"""
import json, re
from collections import Counter, defaultdict

DASH = '/Users/carlaklaasen/claude_code/one_search/dashboards/oikos_usa_onesearch_dashboard.html'

# Hard-coded LP overrides for campaigns with no LP data in QS_DATA
CAMP_LP_OVERRIDE = {
    'BlackConquestingGoogleEXT_YES': '/all-products/oikos-protein-shakes',
    'FusionBrandGoogleEXT_YES':      '/all-products/fusion',
}

with open(DASH, encoding='utf-8') as f:
    html = f.read()

qs_match = re.search(r'(const QS_DATA = )(\[.*?\]);', html, re.DOTALL)
qs = json.loads(qs_match.group(2))

# Build campaign → most-common LP from keywords that already have LPs
camp_lps = defaultdict(list)
for r in qs:
    if r[5] and r[5] not in ('', '(not set)'):
        camp_lps[r[2]].append(r[5])
camp_default = {camp: Counter(lps).most_common(1)[0][0] for camp, lps in camp_lps.items()}

filled = 0
for r in qs:
    if r[5] not in ('', '(not set)'):
        continue
    camp = r[2]
    lp = camp_default.get(camp)
    if not lp:
        # Try override by campaign suffix
        for suffix, override_lp in CAMP_LP_OVERRIDE.items():
            if suffix in camp:
                lp = override_lp
                break
    if lp:
        r[5] = lp
        filled += 1
        print(f'  Filled: {r[0]:<50} → {lp}')
    else:
        print(f'  SKIPPED (no inference): {r[0]}')

print(f'\nFilled {filled} keywords. Remaining empty: {sum(1 for r in qs if r[5] in ("", "(not set)"))}')

# Replace QS_DATA in HTML
new_qs = json.dumps(qs, ensure_ascii=False, separators=(',', ':'))
new_html = html[:qs_match.start(2)] + new_qs + html[qs_match.end(2):]

with open(DASH, 'w', encoding='utf-8') as f:
    f.write(new_html)
print('Dashboard updated.')
