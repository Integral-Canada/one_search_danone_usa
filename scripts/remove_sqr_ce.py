"""Remove 3 JS-generated contenteditable blocks from the SQR renderSqrInsights() function."""
DASH = '/Users/carlaklaasen/claude_code/one_search/dashboards/oikos_usa_onesearch_dashboard.html'

CE_START = "    +'<div contenteditable=\"true\"'"
CE_END   = "    +'></div>'"

FIELD_IDS = [
    'sqr-insights-wasted',
    'sqr-insights-regression',
    'sqr-insights-rising',
]

with open(DASH, encoding='utf-8') as f:
    html = f.read()

removed = 0
for fid in FIELD_IDS:
    anchor = f'    +\' data-field-id="{fid}"\''
    # Find the CE_START immediately before this anchor
    anchor_pos = html.find(anchor)
    if anchor_pos == -1:
        print(f'  ANCHOR NOT FOUND: {fid}')
        continue
    # Walk back to find CE_START on the preceding line
    start = html.rfind(CE_START, 0, anchor_pos)
    if start == -1:
        print(f'  CE_START NOT FOUND before: {fid}')
        continue
    # Find CE_END after anchor
    end = html.find(CE_END, anchor_pos)
    if end == -1:
        print(f'  CE_END NOT FOUND after: {fid}')
        continue
    end += len(CE_END)
    # Include the trailing newline
    if html[end:end+1] == '\n':
        end += 1
    html = html[:start] + html[end:]
    removed += 1
    print(f'  Removed: {fid}')

remaining = html.count('contenteditable="true"')
print(f'\nRemoved {removed}/3 SQR blocks. Remaining contenteditable="true": {remaining}')

with open(DASH, 'w', encoding='utf-8') as f:
    f.write(html)
print('Done.')
