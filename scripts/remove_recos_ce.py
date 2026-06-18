"""Remove the 15 contenteditable boxes from panel-recos (one at a time by field-id)."""
DASH = '/Users/carlaklaasen/claude_code/one_search/dashboards/oikos_usa_onesearch_dashboard.html'

FIELD_IDS = [
    'detail-rec-competitor',
    'detail-rec-generic',
    'detail-rec-health',
    'detail-rec-source-of-protein',
    'detail-rec-consumer-habits',
    'detail-rec-recipe',
    'detail-rec-product',
    'detail-rec-brand',
    'detail-rec-other',
    'detail-rec-sem-negatives',
    'detail-rec-sem-is',
    'detail-rec-sem-keeptest',
    'detail-rec-qs',
    'detail-rec-sem-cadence',
    'detail-rec-spine',
]

ONBLUR_SUFFIX = """ onfocus="this.style.borderColor='#1a7aad';this.style.background='#fff';" onblur="this.style.borderColor='#ccc';this.style.background='#f8f9fb';"></div>"""

with open(DASH, encoding='utf-8') as f:
    html = f.read()

removed = 0
for fid in FIELD_IDS:
    prefix = f'<div contenteditable="true" data-field-id="{fid}"'
    start = html.find(prefix)
    if start == -1:
        print(f'  NOT FOUND: {fid}')
        continue
    end = html.find(ONBLUR_SUFFIX, start)
    if end == -1:
        print(f'  END NOT FOUND: {fid}')
        continue
    end += len(ONBLUR_SUFFIX)
    html = html[:start] + html[end:]
    removed += 1
    print(f'  Removed: {fid}')

remaining = html.count('contenteditable="true"')
print(f'\nRemoved {removed}/15. Remaining contenteditable="true": {remaining}')

with open(DASH, 'w', encoding='utf-8') as f:
    f.write(html)
print('Done.')
