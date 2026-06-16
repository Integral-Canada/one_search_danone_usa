#!/usr/bin/env python3
"""
Build the OneSearch HTML dashboard for Oikos USA.
Reads the Masterlist 'Listing' tab from Google Sheets, converts rows to
DATA + TAGS JavaScript variables, and injects them into the reference HTML
template (reference/activia_ca_onesearch_dashboard.html).

Run:
    python3 build_html_oikos.py
"""
import html as _html_escape
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

# ── Config ─────────────────────────────────────────────────────────────────────
ENV_FILE    = "/Users/carlaklaasen/claude_code/.env"
MASTER_ID   = '1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU'
MASTER_TAB  = 'Listing'
BRAND_NAME  = 'Oikos USA'
PERIOD      = 'Q1 2026 vs Q4 2025'
BRAND_COLOR = '#004f79'    # Oikos deep navy-teal
ACCENT_CLR  = '#1a7aad'    # lighter accent
LIGHT_BG    = '#f0f6fb'    # very light blue background
PERIOD_P1   = 'Q1 2026'
PERIOD_P4   = 'Q4 2025'
TERRITORY_COLORS = [
    '#1565c0', '#2e7d32', '#e65100', '#6a1b9a',
    '#0277bd', '#558b2f', '#c62828', '#4527a0',
    '#00695c', '#f57f17', '#37474f', '#00838f',
]
TEMPLATE    = os.path.join(os.path.dirname(__file__), 'reference',
                            'activia_ca_onesearch_dashboard.html')
OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), 'one_search_html')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'oikos_usa_onesearch_dashboard.html')

# ── Per-client config (change these for each client) ────────────────────────
# TOPIC_ORDER: display order for Coverage by Topics gauges.
# Empty list = auto-sort by volume descending.
TOPIC_ORDER = []

# TERRITORY_TOPICS: ordered list of TOPICS values to show in Core Search Territories widget.
# Must match the TOPICS values in the masterlist exactly (case-sensitive).
# Empty list = all unique TOPICS auto-sorted alphabetically.
TERRITORY_TOPICS = [
    'BRAND',
    'COMPETITOR',
    'CONSUMER HABITS',
    'GENERIC',
    'HEALTH',
    'OTHER',
    'PRODUCT',
    'RECIPE',
    'SOURCE OF PROTEIN',
]

# TERRITORY_DEFINITIONS: human-readable description for each territory.
# Used to generate the Keyword Classification Guide in the glossary tab.
# Keys must match TERRITORY_TOPICS values exactly (case-sensitive).
# Each entry: { 'desc': str, 'intent': str, 'examples': [str, ...] }
# Leave empty ({}) to auto-generate without descriptions (territories still listed).
TERRITORY_DEFINITIONS = {
    'BRAND': {
        'desc':    'Keywords that explicitly name the Oikos brand, product lines (Triple Zero, Pro, Fusion, Remix), or brand variants (misspellings, parent company). The highest-intent territory — users already know the brand.',
        'intent':  'Branded / Navigational',
        'examples': ['oikos', 'oikos triple zero', 'oikos pro drinkable', 'oikos protein shake', 'oikos flip'],
    },
    'PRODUCT': {
        'desc':    'Generic product-type keywords — protein shakes, Greek yogurt, drinkable yogurt — where Oikos is a natural answer but the brand is not mentioned. Captures shoppers in product discovery or comparison mode.',
        'intent':  'Commercial / Transactional',
        'examples': ['protein shake', 'high protein Greek yogurt', 'drinkable yogurt', 'ready-to-drink protein', 'protein drink'],
    },
    'COMPETITOR': {
        'desc':    'Keywords that name competing products or brands (Core Power, Premier Protein, Chobani, Fairlife). Oikos can capture switcher traffic and conquest clicks via SEM on these terms.',
        'intent':  'Competitive / Conquest',
        'examples': ['core power protein shake', 'premier protein shake', 'fairlife core power', 'chobani high protein'],
    },
    'GENERIC': {
        'desc':    'Broad, non-branded category queries about protein drinks, protein shakes, or yogurt with no specific brand intent. High volume, high competition. Entry-point for new-to-category consumers.',
        'intent':  'Informational / Top-of-funnel',
        'examples': ['protein shake', 'best protein drink', 'RTD protein shake', 'protein snack', 'high protein snack'],
    },
    'HEALTH': {
        'desc':    'Health, diet, and nutrition queries — GLP-1 diets, weight loss, high-protein nutrition — where Oikos protein content is a relevant answer. Growing territory driven by GLP-1 medication trends.',
        'intent':  'Informational / Health-driven',
        'examples': ['GLP-1 snacks', 'high protein diet plan', 'weight loss protein', 'GLP-1 foods', 'healthy protein shake'],
    },
    'SOURCE OF PROTEIN': {
        'desc':    'Functional protein-source queries tied to fitness and muscle goals (muscle gain, muscle building, bulking). Often searched by gym-goers and fitness-focused consumers evaluating protein sources.',
        'intent':  'Informational / Fitness-driven',
        'examples': ['protein for muscle gain', 'protein for muscle building', 'protein for muscle mass', 'muscle building protein'],
    },
    'RECIPE': {
        'desc':    'Recipe and meal-prep queries that use Greek yogurt or protein shakes as an ingredient. Supports content SEO and positions Oikos as a versatile kitchen staple beyond direct consumption.',
        'intent':  'Informational / Content',
        'examples': ['Greek yogurt recipe', 'protein shake recipe', 'baking with Greek yogurt', 'protein smoothie recipe', 'yogurt cake'],
    },
    'CONSUMER HABITS': {
        'desc':    'Occasion and lifestyle queries (breakfast, snack, meal prep, sports) that frame protein consumption as part of a daily routine. Useful for editorial content targeting habit-formation moments.',
        'intent':  'Informational / Lifestyle',
        'examples': ['high protein breakfast', 'protein snack', 'protein meal prep', 'post-workout protein meal'],
    },
    'OTHER': {
        'desc':    'Miscellaneous queries including brand misspellings, customer service, promotions, and coupons. Low strategic priority but useful for brand monitoring and defensive coverage.',
        'intent':  'Mixed / Miscellaneous',
        'examples': ['oikos coupon', 'oikos customer service', 'oikos promo code'],
    },
}

# Coverage targets (%) used for gauge colour thresholds and recommendations.
COV_TARGET_BRAND   = 10   # branded territory target
COV_TARGET_GENERIC = 3    # non-branded territory target

# ── Recommendation table filter config ───────────────────────────────────────
# Sub-categories with fewer than this many keywords are auto-grouped into a
# per-territory "Low-volume sub-categories" row to reduce table noise.
# Set to 0 to disable auto-grouping.
OS_RECO_TINY_THRESHOLD = 3

# Maps reco field-id slug → status. Field-id is built as:
#   'reco-json-' + (territory + '-' + subcat).lower().replace(/[^a-z0-9]+/g,'-')
# Status values:
#   'active'      — show normally (default if not listed)
#   'priority'    — show with orange ★ PRIORITY badge
#   'long-term'   — show with grey LONG-TERM badge (dimmed), hidden in "Active" view
#   'remove'      — hidden in all views except "All"
#   'merge:KEY'   — accumulate into a RECO_MERGE_GROUPS group row
# Leave empty ({}) to show all rows with no filtering.
OS_RECO_FILTER = {
    # HIGH PRIORITY
    'reco-json-drink-protein-drink':            'priority',
    'reco-json-drink-chocolate-protein-drink':  'priority',
    # LONG-TERM INFORMATIONAL
    'reco-json-nutrition-glp-1-snacks':         'long-term',
    'reco-json-recipe-glp-1-recipes':           'long-term',
    'reco-json-snack-protein-snacks':           'long-term',
    'reco-json-meal-protein-meal':              'long-term',
    # MERGE: muscle-exercise cluster
    'reco-json-source-of-protein-protein-for-muscle-mass':     'merge:muscle-exercise',
    'reco-json-source-of-protein-protein-for-muscle-gain':     'merge:muscle-exercise',
    'reco-json-source-of-protein-protein-for-muscle-building': 'merge:muscle-exercise',
    'reco-json-source-of-protein-protein-for-muscle-growth':   'merge:muscle-exercise',
    'reco-json-drink-muscle-gain-drink':                       'merge:muscle-exercise',
    'reco-json-drink-muscle-building-protein-drink':           'merge:muscle-exercise',
    # REMOVE — competitor brands
    'reco-json-competitor-core-power-protein-drinkable': 'remove',
    'reco-json-competitor-core-power-protein':           'remove',
    'reco-json-competitor-core-power-drinkable':         'remove',
    'reco-json-competitor-core-power-protein-milk':      'remove',
    'reco-json-competitor-core-power-nutrition':         'remove',
    'reco-json-competitor-core-power-protein-shake':     'remove',
    'reco-json-competitor-premier-protein-nutrition':    'remove',
    'reco-json-competitor-premier-protein-shake':        'remove',
    'reco-json-competitor-premier-protein-drinkable':    'remove',
    'reco-json-competitor-premier-protein-milkshake':    'remove',
    'reco-json-competitor-premier-protein-liquid':       'remove',
    'reco-json-competitor-premier-protein-energy-drink': 'remove',
    'reco-json-competitor-premier-one-shake':            'remove',
    'reco-json-competitor-competing-protein-product':    'remove',
    # REMOVE — irrelevant drink types
    'reco-json-drink-premium-shake':                'remove',
    'reco-json-drink-vanilla-protein':              'remove',
    'reco-json-drink-supplement-shake':             'remove',
    'reco-json-drink-fresh-protein-shake':          'remove',
    'reco-json-drink-natural-protein-shake':        'remove',
    'reco-json-drink-weight-gain-shake':            'remove',
    'reco-json-drink-bodybuilding-shake':           'remove',
    'reco-json-drink-weight-and-muscle-gain-shake': 'remove',
    'reco-json-drink-bulking-shake':                'remove',
    'reco-json-drink-protein-milk':                 'remove',
    'reco-json-drink-protein-milkshake':            'remove',
    'reco-json-supplement-mass-gainer':             'remove',
    # REMOVE — nutrition
    'reco-json-nutrition-protein-products':     'remove',
    'reco-json-nutrition-diet-recommendations': 'remove',
    'reco-json-nutrition-glp-1-diet-plan':      'remove',
    'reco-json-nutrition-glp-1-foods':          'remove',
    # REMOVE — health
    'reco-json-health-glp-1-medication':        'remove',
    'reco-json-health-weight-loss-medication':  'remove',
    # REMOVE — source of protein (non-relevant)
    'reco-json-source-of-protein-protein-for-bulking':     'remove',
    'reco-json-source-of-protein-protein-for-lean-muscle': 'remove',
    # REMOVE — retailer
    'reco-json-retailer-protein-shake-shop': 'remove',
    'reco-json-retailer-purchase-location':  'remove',
    # REMOVE — misc
    'reco-json-yogurt-oikos-oro': 'remove',
}

# Merged group definitions — one row is rendered per key, aggregating all
# sub-categories that map to 'merge:KEY' in OS_RECO_FILTER above.
OS_RECO_MERGE_GROUPS = {
    'muscle-exercise': {
        'cat':          'SOURCE OF PROTEIN / DRINK',
        'subcat':       'Muscle building & exercise protein',
        'note':         '<strong>Long-term SEO strategy</strong> — Align with Oikos protein shake and yogurt narrative. '
                        'Keywords cover muscle gain, muscle building, and exercise protein (Source of Protein + Drink). '
                        'Low priority now; develop informational content as Oikos fitness positioning matures.',
        'channel':      'SEO',
        'channelClass': 'channel-seo',
    },
}

# Brand-detection regex: keywords matching this are classified as "Brand".
# Loaded from the reference sheet below; BRAND_REGEX_DEFAULT is used as
# fallback if the sheet lookup fails.
BRAND_REGEX_SHEET_ID = '1o526Qv4UzP_Qfe-cjrfvcA7jRUi6zUtd9Ecp2WPMIhQ'
BRAND_REGEX_TAB      = 'DANONE USA - Overview'
BRAND_REGEX_NAME     = 'Oikos'   # match this value in column A of the sheet
BRAND_REGEX_DEFAULT  = r'oikos|triple zero'  # plain fallback

# ── DATA array column layout (indices 0-36, match reference HTML JS) ───────────
# Each tuple: (array_index, masterlist_column_header)
# Indices 7 & 8 (Coverage) are computed from clicks/volume, not read from sheet.
# Indices 31 & 33 (SEM Spend) try multiple column name variants.
DATA_MAP = [
    (0,  'Keyword'),
    (1,  'TOPICS'),
    (2,  'CATEGORY'),
    (3,  'SUB-CATEGORY'),
    (4,  'Average Search Volume'),
    (5,  'Volume Q1 2026'),
    (6,  'Volume Q4 2025'),
    # 7 = Coverage OneSearch Q1  (computed)
    # 8 = Coverage OneSearch Q4  (computed)
    (9,  'Clics OneSearch Q1 2026'),
    (10, 'Impressions OneSearch Q1 2026'),
    (11, 'Clics OneSearch Q4 2025'),
    (12, 'Impressions OneSearch Q4 2025'),
    (13, 'Clics SEO Q1 2026'),
    (14, 'Clics SEM Q1 2026'),
    (15, 'Clics SEO Q4 2025'),
    (16, 'Clics SEM Q4 2025'),
    (17, 'Impr. SEO Q1 2026'),
    (18, 'Impr. SEM Q1 2026'),
    (19, 'Impr. SEO Q4 2025'),
    (20, 'Impr. SEM Q4 2025'),
    (21, 'CTR SEO Q1 2026'),
    (22, 'CTR SEM Q1 2026'),
    (23, 'CTR SEO Q4 2025'),
    (24, 'CTR SEM Q4 2025'),
    (25, 'Conversions SEO Q1 2026'),
    (26, 'Conversions SEM Q1 2026'),
    (27, 'Conversions SEO Q4 2025'),
    (28, 'Conversions SEM Q4 2025'),
    (29, 'CPC SEO Q1 2026'),
    (30, 'CPC moy. SEM Q1 2026'),
    # 31 = SEM Spend Q1  (computed from multiple name variants below)
    (32, 'Cost SEO Q1 2026'),
    # 33 = SEM Spend Q4  (computed from multiple name variants below)
    (34, 'Cost SEO Q4 2025'),
    (35, 'Position SE Ranking'),  # was 'Purchase intent' — SE Ranking position populates Pos. SEO column in dashboard
    (36, 'LANG'),
]
STRING_INDICES = {0, 1, 2, 3, 36}

SPEND_P1 = ['Dépense SEM Q1 2026', 'Spend SEM Q1 2026', 'Cost SEM Q1 2026']
SPEND_P4 = ['Dépense SEM Q4 2025', 'Spend SEM Q4 2025', 'Cost SEM Q4 2025']

TAXONOMY_TAGS = [
    'Questions', 'Yogurt types', 'Taste', 'Packaging', 'Ingredient',
    'Brands', 'Retailer', 'Demography', 'Benefits', 'Testimonials',
    'Bio', 'Moments', 'Recipes',
]


# ── Google Sheets helpers ───────────────────────────────────────────────────────

def load_env():
    env = {}
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_token(env):
    data = urllib.parse.urlencode({
        'client_id':     env['GOOGLE_CLIENT_ID'],
        'client_secret': env['GOOGLE_CLIENT_SECRET'],
        'refresh_token': env['GOOGLE_REFRESH_TOKEN'],
        'grant_type':    'refresh_token',
    }).encode()
    resp = json.loads(urllib.request.urlopen(
        urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    ).read())
    return resp['access_token']


def sheets_get(token, sheet_id, range_):
    url = (f'https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}'
           f'/values/{urllib.parse.quote(range_, safe="!:")}'
           f'?valueRenderOption=UNFORMATTED_VALUE')
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read()).get('values', [])
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return None
        raise


QS_SHEET_ID = '1RDgH021qO2VLIOIxBuq0_R7COVXTAHrScYsx6R1xvRc'


def load_brand_regex(token):
    """Read brand-detection regex from reference sheet col H for BRAND_REGEX_NAME.
    Returns the regex string, or BRAND_REGEX_DEFAULT if not found."""
    try:
        raw = sheets_get(token, BRAND_REGEX_SHEET_ID, f"'{BRAND_REGEX_TAB}'!A:H")
        if not raw:
            raise ValueError('empty response')
        for row in raw:
            if len(row) >= 1 and str(row[0]).strip().lower() == BRAND_REGEX_NAME.lower():
                if len(row) >= 8 and str(row[7]).strip():
                    regex = str(row[7]).strip()
                    print(f'  Brand regex loaded from sheet ({len(regex)} chars)', flush=True)
                    return regex
        print(f'  WARNING: brand regex not found for "{BRAND_REGEX_NAME}" — using default', flush=True)
    except Exception as exc:
        print(f'  WARNING: could not load brand regex ({exc}) — using default', flush=True)
    return BRAND_REGEX_DEFAULT


def load_qs_data(token, rows):
    """Load QS data from Google Sheet and return JS array string for QS_CLASSIFIED.

    QS_CLASSIFIED row format (18 fields):
      [0]KW [1]MATCH [2]CAMP [3]ADGR [4]STATUS [5]URL [6]QS [7]LP [8]CTR_ATT
      [9]PERT [10]IMPR [11]CLICS [12]COUT [13]CPC [14]CONV [15]TOPIC [16]CAT [17]SUB
    """
    raw = sheets_get(token, QS_SHEET_ID, 'A1:G10000')
    if not raw:
        return 'const QS_CLASSIFIED = [];'

    # Build keyword → topic/cat lookup from masterlist rows
    kw_lookup = {}
    for r in rows:
        kw = str(r.get('Keyword', '')).strip().lower()
        if kw:
            kw_lookup[kw] = {
                'topic': str(r.get('TOPICS', '')).strip(),
                'cat':   str(r.get('CATEGORY', '')).strip(),
                'sub':   str(r.get('SUB-CATEGORY', '')).strip(),
            }

    def _qs_int(v):
        s = str(v).strip().lstrip()
        if s == '--' or s == '':
            return 0
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return 0

    def _match_type(kw_raw):
        """Infer match type from bracket notation."""
        k = str(kw_raw).strip()
        if k.startswith('[') and k.endswith(']'):
            return 'Exact'
        if k.startswith('"') and k.endswith('"'):
            return 'Phrase'
        return 'Broad'

    def _clean_kw(kw_raw):
        return str(kw_raw).strip().strip('[]"').strip()

    qs_rows = []
    for r in raw[2:]:   # skip header rows 1-2
        if not r or len(r) < 2:
            continue
        if str(r[1]).strip() in ('', 'Search keyword report', 'Keyword'):
            continue
        kw_raw = str(r[1]).strip()
        kw     = _clean_kw(kw_raw)
        camp   = str(r[2]).strip() if len(r) > 2 else ''
        qs     = _qs_int(r[3] if len(r) > 3 else '')
        lp     = str(r[4]).strip() if len(r) > 4 else ''
        pert   = str(r[5]).strip() if len(r) > 5 else ''
        ctr_at = str(r[6]).strip() if len(r) > 6 else ''
        status = str(r[0]).strip() if r else 'Enabled'
        match  = _match_type(kw_raw)

        meta = kw_lookup.get(kw.lower(), {})
        qs_rows.append([
            kw,           # [0] KW
            match,        # [1] MATCH
            camp,         # [2] CAMP
            '',           # [3] ADGR
            status,       # [4] STATUS
            '',           # [5] URL
            qs,           # [6] QS
            lp,           # [7] LP
            ctr_at,       # [8] CTR_ATT
            pert,         # [9] PERT
            0,            # [10] IMPR
            0,            # [11] CLICS
            0,            # [12] COUT
            0,            # [13] CPC
            0,            # [14] CONV
            meta.get('topic', ''),  # [15] TOPIC
            meta.get('cat', ''),    # [16] CAT
            meta.get('sub', ''),    # [17] SUB
        ])

    lines = ['const QS_CLASSIFIED = [']
    for i, row in enumerate(qs_rows):
        comma = ',' if i < len(qs_rows) - 1 else ''
        lines.append('  [' + ','.join(_js_val(v) for v in row) + ']' + comma)
    lines.append('];')
    return '\n'.join(lines)


def build_taxonomy_glossary_html(rows):
    """Generate the Keyword Classification Guide HTML section for the glossary tab.

    Uses TERRITORY_TOPICS for ordering and TERRITORY_DEFINITIONS for descriptions.
    Falls back gracefully if a territory has no entry in TERRITORY_DEFINITIONS.
    Injects into the template via the <!-- TAXONOMY_GLOSSARY --> placeholder.
    """
    from collections import defaultdict

    # Build topic order: use TERRITORY_TOPICS if defined, else sorted from data
    order = TERRITORY_TOPICS if TERRITORY_TOPICS else sorted({
        str(r.get('TOPICS', '')).strip() for r in rows if r.get('TOPICS', '').strip()
    })

    # Intent colour map
    INTENT_COLORS = {
        'Branded / Navigational':       ('#004f79', '#e8f4f9'),
        'Commercial / Transactional':   ('#1b5e20', '#f1f8f1'),
        'Competitive / Conquest':       ('#b71c1c', '#fff5f5'),
        'Informational / Top-of-funnel':('#e65100', '#fff8f0'),
        'Informational / Health-driven':('#4a148c', '#f5f0fb'),
        'Informational / Fitness-driven':('#01579b','#e8f4fc'),
        'Informational / Content':      ('#33691e', '#f6faf0'),
        'Informational / Lifestyle':    ('#006064', '#e0f7fa'),
        'Mixed / Miscellaneous':        ('#546e7a', '#f4f6f7'),
    }

    cards = []
    for i, topic in enumerate(order, 1):
        defn   = TERRITORY_DEFINITIONS.get(topic, {})
        desc   = defn.get('desc', 'Keywords grouped under this territory in the OneSearch taxonomy.')
        intent = defn.get('intent', '')
        exs    = defn.get('examples', [])

        ic, ibg = INTENT_COLORS.get(intent, ('#555', '#f4f4f4'))

        badge = (f'<span style="font-size:9px;font-weight:700;text-transform:uppercase;'
                 f'letter-spacing:.06em;padding:2px 8px;border-radius:3px;'
                 f'background:{ibg};color:{ic};border:1px solid {ic}33;">'
                 f'{intent}</span>') if intent else ''

        ex_html = ''
        if exs:
            ex_html = ('<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:4px;">'
                       + ''.join(f'<span style="font-size:10px;background:#f0f0f0;color:#555;'
                                 f'padding:2px 7px;border-radius:3px;font-style:italic;">{e}</span>'
                                 for e in exs)
                       + '</div>')

        cards.append(
            f'<div style="background:#fff;border:1px solid #e8e8e8;border-radius:8px;'
            f'padding:14px 16px;display:flex;gap:14px;align-items:flex-start;">'
            f'<div style="min-width:28px;height:28px;border-radius:50%;background:#004f79;'
            f'color:#fff;font-size:12px;font-weight:700;display:flex;align-items:center;'
            f'justify-content:center;flex-shrink:0;">{i}</div>'
            f'<div style="flex:1;">'
            f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px;">'
            f'<strong style="font-size:12px;color:#004f79;letter-spacing:.02em;">{topic}</strong>'
            f'{badge}</div>'
            f'<div style="font-size:11px;color:#444;line-height:1.6;">{desc}</div>'
            f'{ex_html}'
            f'</div></div>'
        )

    inner = '\n'.join(cards)
    return (
        '<div class="g-section-title">Keyword Classification Guide</div>\n'
        '<div style="padding:16px 24px 8px;">\n'
        '<p style="font-size:11px;color:#888;line-height:1.5;margin:0 0 14px;">Each keyword in the OneSearch study is classified into a <strong>territory</strong> '
        '(TOPICS), a <strong>category</strong>, and a <strong>sub-category</strong>. '
        'The territory is the primary filter used throughout the dashboard.</p>\n'
        '<div style="display:flex;flex-direction:column;gap:10px;">\n'
        + inner
        + '\n</div>\n</div>\n'
    )


def build_sqr_data(rows):
    """Build SQR_ACTIVIA JS array from masterlist rows (rows with any SEM clicks).

    SQR_ACTIVIA row format (25 fields):
      [0]KW [1]CAMP [2]ADGR [3]MATCH [4]STATUS [5]IMPR_Q1 [6]CLICS_Q1 [7]COUT_Q1
      [8]? [9]CONV_Q1 [10]? [11]CTR_Q1 [12]CPC_Q1 [13]CPA_Q1 [14]IMPR_Q4
      [15]CLICS_Q4 [16]COUT_Q4 [17]? [18]CONV_Q4 [19]? [20]CTR_Q4 [21]CPC_Q4
      [22]CPA_Q4 [23]OSTOPIC [24]CAT
    """
    sqr_rows = []
    for r in rows:
        sem_q1 = _n(r.get('Clics SEM Q1 2026', 0))
        sem_q4 = _n(r.get('Clics SEM Q4 2025', 0))
        if sem_q1 <= 0 and sem_q4 <= 0:
            continue
        kw      = _s(r.get('Keyword', ''))
        camp    = _s(r.get('TOPICS', ''))      # use TOPICS as campaign proxy
        impr_q1 = _n(r.get('Impr. SEM Q1 2026', 0))
        cout_q1 = _n(r.get('Cost SEM Q1 2026') or r.get('Coût SEM Q1 2026', 0))
        conv_q1 = _n(r.get('Conversions SEM Q1 2026', 0))
        ctr_q1  = _n(r.get('CTR SEM Q1 2026', 0))
        cpc_q1  = _n(r.get('CPC moy. SEM Q1 2026', 0))
        cpa_q1  = cout_q1 / conv_q1 if conv_q1 > 0 else 0
        impr_q4 = _n(r.get('Impr. SEM Q4 2025', 0))
        cout_q4 = _n(r.get('Cost SEM Q4 2025') or r.get('Coût SEM Q4 2025', 0))
        conv_q4 = _n(r.get('Conversions SEM Q4 2025', 0))
        ctr_q4  = _n(r.get('CTR SEM Q4 2025', 0))
        cpa_q4  = cout_q4 / conv_q4 if conv_q4 > 0 else 0
        topic   = _s(r.get('TOPICS', ''))
        cat     = _s(r.get('CATEGORY', ''))

        sqr_rows.append([
            kw,       # [0] KW
            camp,     # [1] CAMP
            '',       # [2] ADGR
            '',       # [3] MATCH
            '',       # [4] STATUS
            impr_q1,  # [5] IMPR_Q1
            sem_q1,   # [6] CLICS_Q1
            cout_q1,  # [7] COUT_Q1
            0,        # [8]
            conv_q1,  # [9] CONV_Q1
            0,        # [10]
            ctr_q1,   # [11] CTR_Q1
            cpc_q1,   # [12] CPC_Q1
            cpa_q1,   # [13] CPA_Q1
            impr_q4,  # [14] IMPR_Q4
            sem_q4,   # [15] CLICS_Q4
            cout_q4,  # [16] COUT_Q4
            0,        # [17]
            conv_q4,  # [18] CONV_Q4
            0,        # [19]
            ctr_q4,   # [20] CTR_Q4
            0,        # [21] CPC_Q4
            cpa_q4,   # [22] CPA_Q4
            topic,    # [23] OSTOPIC
            cat,      # [24] CAT
        ])

    sqr_rows.sort(key=lambda x: x[6], reverse=True)   # sort by SEM clicks Q1 desc

    lines = ['var SQR_ACTIVIA = [']
    for i, row in enumerate(sqr_rows):
        comma = ',' if i < len(sqr_rows) - 1 else ''
        lines.append('  [' + ','.join(_js_val(v) for v in row) + ']' + comma)
    lines.append('];')
    return '\n'.join(lines)


# ── Data extraction ─────────────────────────────────────────────────────────────

def _n(v, default=0):
    if v == '' or v is None:
        return default
    try:
        f = float(str(v).replace(',', '.').strip())
        return default if (f != f) else f  # NaN guard
    except (ValueError, TypeError):
        return default


def _s(v, default=''):
    v2 = str(v).strip() if v is not None else ''
    return v2 if v2 else default


def read_masterlist(token):
    hdr_raw = sheets_get(token, MASTER_ID, f"'{MASTER_TAB}'!1:1")
    if not hdr_raw:
        raise ValueError('Cannot read masterlist headers')
    headers = [str(h) for h in hdr_raw[0]]
    print(f'  {len(headers)} columns', flush=True)

    rows = []
    for start in range(2, 20000, 1000):
        chunk = sheets_get(token, MASTER_ID, f"'{MASTER_TAB}'!A{start}:BE{start+999}")
        if chunk is None or chunk == []:
            break
        for row in chunk:
            while len(row) < len(headers):
                row.append('')
            rows.append({h: row[i] for i, h in enumerate(headers)})

    print(f'  {len(rows)} rows', flush=True)
    return headers, rows


def build_data(rows):
    spend_p1 = next((c for c in SPEND_P1 if any(c in r for r in rows[:1])), None)
    spend_p4 = next((c for c in SPEND_P4 if any(c in r for r in rows[:1])), None)

    data_rows = []
    for row in rows:
        kw = _s(row.get('Keyword', ''))
        if not kw:
            continue

        avg_vol     = _n(row.get('Average Search Volume', 0))
        clics_os_p1 = _n(row.get('Clics OneSearch Q1 2026', 0))
        clics_os_p4 = _n(row.get('Clics OneSearch Q4 2025', 0))
        cov_p1 = round(clics_os_p1 / avg_vol, 4) if avg_vol > 0 else 0
        cov_p4 = round(clics_os_p4 / avg_vol, 4) if avg_vol > 0 else 0

        dr = [0] * 37
        for idx, col in DATA_MAP:
            val = row.get(col, '')
            dr[idx] = _s(val) if idx in STRING_INDICES else _n(val)

        dr[7]  = cov_p1
        dr[8]  = cov_p4
        dr[31] = _n(row.get(spend_p1, 0)) if spend_p1 else 0
        dr[33] = _n(row.get(spend_p4, 0)) if spend_p4 else 0

        data_rows.append(dr)

    return data_rows


def build_tags(rows):
    tags = {}
    for row in rows:
        kw = _s(row.get('Keyword', ''))
        if not kw:
            continue
        tag_dict = {}
        for col in TAXONOMY_TAGS:
            val = _s(row.get(col, ''))
            if val and val.lower() not in ('no', 'n/a', '0', 'false'):
                tag_dict[col] = val
        if tag_dict:
            tags[kw] = tag_dict
    return tags


# ── Territory helpers ──────────────────────────────────────────────────────────

def _fmt_num(n):
    n = float(n)
    if n >= 1_000_000:
        return f'{n/1_000_000:.1f}M'
    if n >= 10_000:
        return f'{n/1_000:.0f}K'
    if n >= 1_000:
        return f'{n/1_000:.1f}K'
    return str(int(n))


def _fmt_pct(v):
    return f'{float(v)*100:.1f}%'


def _delta_pct(q4, q1):
    if q4 == 0:
        return '<span style="color:#2e7d32;font-weight:600">NEW</span>' if q1 > 0 else '<span style="color:#888">—</span>'
    d = (q1 - q4) / q4 * 100
    c = '#2e7d32' if d >= 0 else '#c62828'
    s = '+' if d >= 0 else ''
    return f'<span style="color:{c};font-weight:600">{s}{d:.0f}%</span>'


def _delta_pp(cov4, cov1):
    d = (cov1 - cov4) * 100
    c = '#2e7d32' if d >= 0 else '#c62828'
    s = '+' if d >= 0 else ''
    return f'<span style="color:{c};font-weight:600">{s}{d:.1f}pp</span>'


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:40]


def _cov(clicks, volume):
    return clicks / volume if volume > 0 else 0.0


def _fmt_cov(v):
    """Format coverage ratio as plain percentage. Values >100% are valid data
    (SEM broad-match clicks exceed SE Ranking vol estimate) and are shown as-is."""
    pct = float(v) * 100
    return f'{pct:.1f}%'


def compute_territory_stats(rows):
    sample = rows[0] if rows else {}
    spend_p1 = next((c for c in SPEND_P1 if c in sample), None)
    spend_p4 = next((c for c in SPEND_P4 if c in sample), None)

    stats = defaultdict(lambda: {
        'count': 0,
        'volume_q1': 0.0, 'volume_q4': 0.0, 'avg_volume': 0.0,
        'os_clicks_q1': 0.0, 'os_clicks_q4': 0.0,
        'seo_clicks_q1': 0.0, 'seo_clicks_q4': 0.0,
        'sem_clicks_q1': 0.0, 'sem_clicks_q4': 0.0,
        'conv_seo_q1': 0.0, 'conv_seo_q4': 0.0,
        'conv_sem_q1': 0.0, 'conv_sem_q4': 0.0,
        'spend_q1': 0.0, 'spend_q4': 0.0,
        'top_kws': [],
    })

    for row in rows:
        topic = _s(row.get('TOPICS', ''))
        kw    = _s(row.get('Keyword', ''))
        if not topic or not kw:
            continue
        s = stats[topic]
        s['count'] += 1
        s['volume_q1']    += _n(row.get('Volume Q1 2026', 0))
        s['volume_q4']    += _n(row.get('Volume Q4 2025', 0))
        s['avg_volume']   += _n(row.get('Average Search Volume', 0))
        os_q1 = _n(row.get('Clics OneSearch Q1 2026', 0))
        os_q4 = _n(row.get('Clics OneSearch Q4 2025', 0))
        seo_q1 = _n(row.get('Clics SEO Q1 2026', 0))
        seo_q4 = _n(row.get('Clics SEO Q4 2025', 0))
        sem_q1 = _n(row.get('Clics SEM Q1 2026', 0))
        sem_q4 = _n(row.get('Clics SEM Q4 2025', 0))
        s['os_clicks_q1']  += os_q1
        s['os_clicks_q4']  += os_q4
        s['seo_clicks_q1'] += seo_q1
        s['seo_clicks_q4'] += seo_q4
        s['sem_clicks_q1'] += sem_q1
        s['sem_clicks_q4'] += sem_q4
        s['conv_seo_q1']   += _n(row.get('Conversions SEO Q1 2026', 0))
        s['conv_seo_q4']   += _n(row.get('Conversions SEO Q4 2025', 0))
        s['conv_sem_q1']   += _n(row.get('Conversions SEM Q1 2026', 0))
        s['conv_sem_q4']   += _n(row.get('Conversions SEM Q4 2025', 0))
        if spend_p1:
            s['spend_q1'] += _n(row.get(spend_p1, 0))
        if spend_p4:
            s['spend_q4'] += _n(row.get(spend_p4, 0))
        s['top_kws'].append({
            'kw': kw, 'os_q1': os_q1, 'os_q4': os_q4,
            'avg_vol': _n(row.get('Average Search Volume', 0)),
            'seo_q1': seo_q1, 'sem_q1': sem_q1,
        })

    for s in stats.values():
        s['top_kws'].sort(key=lambda x: x['os_q1'], reverse=True)
        s['top_kws'] = s['top_kws'][:8]

    return dict(stats)


_SEO_CLR  = '#2e7d32'
_SEM_CLR  = '#1565c0'
_SEO_LITE = '#f1f8f1'
_SEM_LITE = '#eaf0fb'


def _bullets_html(items):
    if not items:
        return '<li style="color:#aaa;font-style:italic;">No data available for this period.</li>'
    return ''.join(
        f'<li style="margin-bottom:4px;line-height:1.45;">{item}</li>'
        for item in items
    )


def _q1_seo_bullets(topic, s):
    items = []
    seo_q1, seo_q4 = s['seo_clicks_q1'], s['seo_clicks_q4']
    if seo_q1 > 0:
        if seo_q4 > 0:
            d = (seo_q1 - seo_q4) / seo_q4 * 100
            sign = '+' if d >= 0 else ''
            items.append(f'SEO clicks {sign}{d:.0f}% QoQ — {_fmt_num(seo_q1)} clicks in {PERIOD_P1}')
        else:
            items.append(f'SEO clicks: {_fmt_num(seo_q1)} in {PERIOD_P1} (new this quarter)')
    else:
        items.append(f'No SEO click data recorded in {PERIOD_P1}')
    cov  = _cov(s['os_clicks_q1'], s['avg_volume'])
    cov4 = _cov(s['os_clicks_q4'], s['avg_volume'])
    if s['avg_volume'] > 0:
        dp = (cov - cov4) * 100
        sign = '+' if dp >= 0 else ''
        items.append(f'OneSearch coverage: {_fmt_pct(cov)} ({sign}{dp:.1f}pp vs {PERIOD_P4})')
    if s['conv_seo_q1'] > 0:
        items.append(f'{s["conv_seo_q1"]:.0f} MikMak Checkout conversions in {PERIOD_P1}')
    top_seo = sorted(s['top_kws'], key=lambda x: x['seo_q1'], reverse=True)
    if top_seo and top_seo[0]['seo_q1'] > 0:
        kd = top_seo[0]
        items.append(f'Top organic driver: "{kd["kw"]}" — {_fmt_num(kd["seo_q1"])} clicks')
    return items


def _q1_sem_bullets(topic, s):
    items = []
    if s['spend_q1'] > 0:
        items.append(f'SEM investment: ${s["spend_q1"]:,.0f} in {PERIOD_P1}')
        if s['sem_clicks_q1'] > 0:
            cpc = s['spend_q1'] / s['sem_clicks_q1']
            items.append(f'Avg CPC ${cpc:.2f} — {_fmt_num(s["sem_clicks_q1"])} paid clicks')
    elif s['sem_clicks_q1'] > 0:
        items.append(f'SEM clicks: {_fmt_num(s["sem_clicks_q1"])} in {PERIOD_P1}')
    else:
        items.append(f'No paid investment recorded for {PERIOD_P1}')
    if s['sem_clicks_q4'] > 0 and s['sem_clicks_q1'] > 0:
        d = (s['sem_clicks_q1'] - s['sem_clicks_q4']) / s['sem_clicks_q4'] * 100
        sign = '+' if d >= 0 else ''
        items.append(f'Paid clicks {sign}{d:.0f}% QoQ vs {PERIOD_P4}')
    if s['conv_sem_q1'] > 0:
        items.append(f'{s["conv_sem_q1"]:.0f} MikMak Click Offline Store conversions in {PERIOD_P1}')
    top_sem = sorted(s['top_kws'], key=lambda x: x['sem_q1'], reverse=True)
    if top_sem and top_sem[0]['sem_q1'] > 0:
        kd = top_sem[0]
        items.append(f'Top paid driver: "{kd["kw"]}" — {_fmt_num(kd["sem_q1"])} clicks')
    return items


def _q2_seo_bullets(topic, s):
    items = []
    cov  = _cov(s['os_clicks_q1'], s['avg_volume'])
    cov4 = _cov(s['os_clicks_q4'], s['avg_volume'])
    if cov < 0.03:
        items.append(f'Coverage gap ({_fmt_pct(cov)}) — priority content opportunity in {topic}')
        items.append(f'Target high-volume uncovered terms ({_fmt_num(s["avg_volume"])} monthly searches in territory)')
    else:
        items.append(f'Maintain momentum ({_fmt_pct(cov)} coverage) — refresh top-performing pages')
    if s['seo_clicks_q4'] > 0 and s['seo_clicks_q1'] > 0:
        d = (s['seo_clicks_q1'] - s['seo_clicks_q4']) / s['seo_clicks_q4'] * 100
        if d > 10:
            items.append(f'Capitalize on strong Q1 organic growth (+{d:.0f}%) — scale content production')
        elif d < -10:
            items.append(f'Investigate Q1 decline ({d:.0f}%) — audit page quality and content depth')
    low = [k for k in s['top_kws']
           if _cov(k['os_q1'], k['avg_vol']) < 0.05 and k['avg_vol'] > 500]
    if low:
        kd = low[0]
        items.append(f'Coverage opportunity: "{kd["kw"]}" ({_fmt_num(kd["avg_vol"])}/mo, '
                     f'{_fmt_pct(_cov(kd["os_q1"], kd["avg_vol"]))} coverage)')
    items.append(f'Monitor AI Overview impact on CTR for {topic.lower()} queries')
    return items


def _q2_sem_bullets(topic, s):
    items = []
    if s['sem_clicks_q1'] > 0 and s['spend_q1'] > 0:
        cpc = s['spend_q1'] / s['sem_clicks_q1']
        if cpc > 3.0:
            items.append(f'Review bid strategy — CPC ${cpc:.2f} above benchmark; test Smart Bidding')
        else:
            items.append(f'Efficient CPC (${cpc:.2f}) — evaluate budget expansion for Q2 scale')
        if s['sem_clicks_q4'] > 0:
            d = (s['sem_clicks_q1'] - s['sem_clicks_q4']) / s['sem_clicks_q4'] * 100
            if d > 0:
                items.append(f'Paid volume growing (+{d:.0f}% QoQ) — prioritize impression share expansion')
    elif s['sem_clicks_q1'] == 0:
        cov = _cov(s['os_clicks_q1'], s['avg_volume'])
        if s['avg_volume'] > 1000:
            items.append(f'Untapped paid opportunity — {_fmt_num(s["avg_volume"])} monthly searches, '
                         f'{_fmt_pct(cov)} organic coverage only')
        items.append(f'Evaluate first paid entry into {topic.lower()} for Q2')
    if s['conv_sem_q1'] == 0 and s['spend_q1'] > 0:
        items.append('No conversions tracked in Q1 — verify tagging before scaling Q2 budgets')
    items.append('Align Q2 ad groups with top-converting search terms from Q1 learnings')
    return items


def _action_card(title, color, lite_bg, items, field_id, placeholder):
    blist = _bullets_html(items)
    return (
        f'<div style="background:#fff;border:1px solid {color}30;border-radius:8px;'
        f'padding:14px 16px;display:flex;flex-direction:column;gap:10px;">'
        f'<h4 style="font-size:11px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.08em;color:{color};margin:0;padding-bottom:8px;'
        f'border-bottom:1px solid {color}20;">{title}</h4>'
        f'<ul style="list-style:disc;padding-left:16px;margin:0;font-size:11px;'
        f'line-height:1.5;color:#444;">{blist}</ul>'
        f'<div contenteditable="true" data-field-id="{field_id}" data-placeholder="{_html_escape.escape(placeholder)}"'
        f' style="min-height:54px;font-size:11px;line-height:1.5;color:#444;'
        f'border:1px dashed #555;border-radius:5px;padding:7px 9px;'
        f'background:{lite_bg};outline:none;margin-top:2px;"'
        f' onfocus="this.style.borderColor=\'{ACCENT_CLR}\';this.style.background=\'#fff\';"'
        f' onblur="this.style.borderColor=\'#555\';this.style.background=\'{lite_bg}\';"'
        f'>{placeholder}</div>'
        f'</div>'
    )


def _agg_q1_seo_bullets(sorted_t, total_seo_q1, total_seo_q4):
    items = []
    if total_seo_q4 > 0:
        d = (total_seo_q1 - total_seo_q4) / total_seo_q4 * 100
        sign = '+' if d >= 0 else ''
        items.append(f'SEO clicks {sign}{d:.0f}% QoQ — {_fmt_num(total_seo_q1)} clicks in {PERIOD_P1}')
    elif total_seo_q1 > 0:
        items.append(f'{_fmt_num(total_seo_q1)} SEO clicks in {PERIOD_P1}')
    top3_seo = sorted(sorted_t, key=lambda x: x[1]['seo_clicks_q1'], reverse=True)[:3]
    for t, s in top3_seo:
        if s['seo_clicks_q1'] > 0:
            items.append(f'{t}: {_fmt_num(s["seo_clicks_q1"])} SEO clicks '
                         f'({_fmt_cov(_cov(s["os_clicks_q1"], s["avg_volume"]))} coverage)')
    no_seo = [t for t, s in sorted_t if s['seo_clicks_q1'] == 0 and s['avg_volume'] > 500]
    if no_seo:
        items.append(f'Zero SEO clicks in: {", ".join(no_seo[:3])} — content gap')
    return items


def _agg_q1_sem_bullets(sorted_t, total_sem_q1, total_sem_q4):
    items = []
    if total_sem_q4 > 0 and total_sem_q1 > 0:
        d = (total_sem_q1 - total_sem_q4) / total_sem_q4 * 100
        sign = '+' if d >= 0 else ''
        items.append(f'SEM clicks {sign}{d:.0f}% QoQ — {_fmt_num(total_sem_q1)} clicks in {PERIOD_P1}')
    elif total_sem_q1 > 0:
        items.append(f'{_fmt_num(total_sem_q1)} paid clicks in {PERIOD_P1}')
    top3_sem = sorted(sorted_t, key=lambda x: x[1]['sem_clicks_q1'], reverse=True)[:3]
    for t, s in top3_sem:
        if s['sem_clicks_q1'] > 0:
            items.append(f'{t}: {_fmt_num(s["sem_clicks_q1"])} SEM clicks')
    no_sem = [t for t, s in sorted_t if s['sem_clicks_q1'] == 0 and s['avg_volume'] > 500]
    if no_sem:
        items.append(f'No paid presence: {", ".join(no_sem[:3])} — evaluate entry')
    return items


def _agg_q2_seo_bullets(sorted_t):
    items = []
    gap = [(t, s) for t, s in sorted_t if _cov(s['os_clicks_q1'], s['avg_volume']) < 0.03]
    if gap:
        items.append(f'Close coverage gaps (&lt;3%) in: {", ".join(t for t, _ in gap[:3])}')
    growing = [(t, s) for t, s in sorted_t
               if s['seo_clicks_q4'] > 0
               and (s['seo_clicks_q1'] - s['seo_clicks_q4']) / s['seo_clicks_q4'] > 0.15]
    if growing:
        items.append(f'Scale content in high-growth territories: {", ".join(t for t, _ in growing[:3])}')
    high_vol_low_cov = [(t, s) for t, s in sorted_t
                        if s['avg_volume'] > 10000 and _cov(s['os_clicks_q1'], s['avg_volume']) < 0.05]
    if high_vol_low_cov:
        items.append(f'High-volume, low-coverage: {", ".join(t for t, _ in high_vol_low_cov[:3])} — content priority')
    items.append('Monitor AI Overview impact on CTR for high-impression territories')
    return items


def _agg_q2_sem_bullets(sorted_t, total_sem_q1, total_sem_q4):
    items = []
    if total_sem_q4 > 0 and total_sem_q1 > 0:
        d = (total_sem_q1 - total_sem_q4) / total_sem_q4 * 100
        if d < -10:
            items.append(f'SEM volume declined {d:.0f}% QoQ — review impression share and budget allocation')
        elif d > 10:
            items.append(f'SEM momentum (+{d:.0f}% QoQ) — expand coverage in gap territories')
    no_sem_high_vol = [(t, s) for t, s in sorted_t
                       if s['sem_clicks_q1'] == 0 and s['avg_volume'] > 5000]
    if no_sem_high_vol:
        items.append(f'Untapped paid potential: {", ".join(t for t, _ in no_sem_high_vol[:3])}')
    items.append('Align Q2 ad groups with top-converting Q1 search terms')
    items.append('Evaluate Smart Bidding expansion in top-spend territories')
    return items


def build_territory_panel(territory_stats):
    sorted_t = sorted(territory_stats.items(),
                      key=lambda x: x[1]['os_clicks_q1'], reverse=True)

    total_kws      = sum(s['count'] for _, s in sorted_t)
    total_os_q1    = sum(s['os_clicks_q1'] for _, s in sorted_t)
    total_os_q4    = sum(s['os_clicks_q4'] for _, s in sorted_t)
    total_vol      = sum(s['avg_volume'] for _, s in sorted_t)
    total_vol_q1   = sum(s['volume_q1'] for _, s in sorted_t)
    total_vol_q4   = sum(s['volume_q4'] for _, s in sorted_t)
    total_seo_q1   = sum(s['seo_clicks_q1'] for _, s in sorted_t)
    total_seo_q4   = sum(s['seo_clicks_q4'] for _, s in sorted_t)
    total_sem_q1   = sum(s['sem_clicks_q1'] for _, s in sorted_t)
    total_sem_q4   = sum(s['sem_clicks_q4'] for _, s in sorted_t)
    total_cov_q1   = _cov(total_os_q1, total_vol)
    total_cov_q4   = _cov(total_os_q4, total_vol)
    n_territories  = len(sorted_t)

    # OS clicks Q1 vs Q4 delta
    os_delta_str = _delta_pct(total_os_q4, total_os_q1)
    cov_delta_str = _delta_pp(total_cov_q4, total_cov_q1)

    # Top SEO territory
    top_seo = max(sorted_t, key=lambda x: x[1]['seo_clicks_q1'], default=(None, {'seo_clicks_q1': 0}))
    # Top SEM territory
    top_sem = max(sorted_t, key=lambda x: x[1]['sem_clicks_q1'], default=(None, {'sem_clicks_q1': 0}))
    # Coverage gap territories (below 3%)
    gap_territories = [(t, s) for t, s in sorted_t if _cov(s['os_clicks_q1'], s['avg_volume']) < 0.03]

    H = _html_escape.escape

    # Build aggregate action cards for exec summary
    agg_card_q1_seo = _action_card(
        'Q1 2026 — SEO Actions', _SEO_CLR, _SEO_LITE,
        _agg_q1_seo_bullets(sorted_t, total_seo_q1, total_seo_q4),
        'us-q1-seo', 'Add US-level Q1 SEO analyst notes…'
    )
    agg_card_q1_sem = _action_card(
        'Q1 2026 — SEM Actions', _SEM_CLR, _SEM_LITE,
        _agg_q1_sem_bullets(sorted_t, total_sem_q1, total_sem_q4),
        'us-q1-sem', 'Add US-level Q1 SEM analyst notes…'
    )
    agg_card_q2_seo = _action_card(
        'Q2 2026 Pipeline — SEO', _SEO_CLR, _SEO_LITE,
        _agg_q2_seo_bullets(sorted_t),
        'us-q2-seo', 'Add US-level Q2 SEO pipeline notes…'
    )
    agg_card_q2_sem = _action_card(
        'Q2 2026 Pipeline — SEM', _SEM_CLR, _SEM_LITE,
        _agg_q2_sem_bullets(sorted_t, total_sem_q1, total_sem_q4),
        'us-q2-sem', 'Add US-level Q2 SEM pipeline notes…'
    )

    # Build Q2 priority bullets
    q2_bullets = []
    if gap_territories:
        gap_names = ', '.join(H(t) for t, _ in gap_territories[:3])
        q2_bullets.append(f'Close coverage gaps (&lt;3%) in: {gap_names}')
    if total_seo_q4 > 0:
        seo_d = (total_seo_q1 - total_seo_q4) / total_seo_q4 * 100
        if seo_d > 5:
            q2_bullets.append(f'Capitalize on SEO momentum (+{seo_d:.0f}% QoQ) — scale content production')
        elif seo_d < -5:
            q2_bullets.append(f'Investigate SEO decline ({seo_d:.0f}% QoQ) — audit page quality and refresh top-landing pages')
    if total_sem_q1 > 0 and total_seo_q1 > 0:
        q2_bullets.append('Evaluate SEM impression share recovery in top coverage-gap territories')
    q2_bullets.append('Complete taxonomy enrichment to classify untagged keywords')
    q2_blist = _bullets_html(q2_bullets)

    parts = []

    # ── Header ──────────────────────────────────────────────────────────────────
    parts.append(f'''
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:1280px;margin:0 auto;">

<!-- digitad logo bar -->
<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 24px 6px;border-bottom:1px solid rgba(0,0,0,0.06);">
  <div style="display:flex;align-items:center;gap:10px;">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 49.91 95.65" width="16" height="30"><polygon points="0 0 0 25.55 49.91 47.83 49.91 22.27 0 0" fill="{BRAND_COLOR}"/><polygon points="0 95.65 49.91 73.38 49.91 47.83 0 70.1 0 95.65" fill="{BRAND_COLOR}"/></svg>
    <span style="font-family:'Poppins',sans-serif;font-weight:700;font-size:14px;color:{BRAND_COLOR};">digitad</span>
  </div>
  <span style="font-size:12px;color:#666;">{BRAND_NAME}</span>
</div>

<!-- hero -->
<div style="background:linear-gradient(135deg,{BRAND_COLOR} 0%,{ACCENT_CLR} 100%);color:#fff;padding:24px 32px;border-radius:12px;margin:14px 24px 20px;text-align:center;">
  <div style="font-size:10px;text-transform:uppercase;letter-spacing:.15em;opacity:.7;margin-bottom:4px;">OneSearch — Territory Deep Dive</div>
  <h1 style="font-size:22px;font-weight:700;margin:0 0 4px;">{H(BRAND_NAME)} — Core Search Territories</h1>
  <div style="font-size:12px;opacity:.8;">{PERIOD} · Performance &amp; Strategic Analysis</div>
  <div style="display:flex;justify-content:center;gap:10px;margin-top:12px;flex-wrap:wrap;">
    <span style="background:rgba(255,255,255,.15);padding:5px 12px;border-radius:16px;font-size:11px;font-weight:600;">{total_kws:,} keywords classified</span>
    <span style="background:rgba(255,255,255,.15);padding:5px 12px;border-radius:16px;font-size:11px;font-weight:600;">{n_territories} territories</span>
    <span style="background:rgba(255,255,255,.15);padding:5px 12px;border-radius:16px;font-size:11px;font-weight:600;">{_fmt_cov(total_cov_q1)} avg coverage</span>
  </div>
</div>

<!-- Executive summary — single US-level narrative -->
<div style="background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:20px 24px;margin:0 24px 20px;border-left:4px solid {BRAND_COLOR};">
  <h2 style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:{BRAND_COLOR};margin:0 0 14px;">Executive Summary — {H(BRAND_NAME)} US ({PERIOD})</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
    <div>
      <div style="font-size:9px;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px;">AI Draft — US aggregate signals</div>
      <!-- KPI row -->
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;">
        <div style="background:{LIGHT_BG};border-radius:6px;padding:8px 10px;text-align:center;">
          <div style="font-size:9px;color:#888;text-transform:uppercase;margin-bottom:2px;">OS Clicks {PERIOD_P1}</div>
          <div style="font-size:16px;font-weight:700;color:{BRAND_COLOR};">{_fmt_num(total_os_q1)}</div>
          <div style="font-size:10px;">{os_delta_str} vs {PERIOD_P4}</div>
        </div>
        <div style="background:{LIGHT_BG};border-radius:6px;padding:8px 10px;text-align:center;">
          <div style="font-size:9px;color:#888;text-transform:uppercase;margin-bottom:2px;">Search Volume</div>
          <div style="font-size:16px;font-weight:700;color:{BRAND_COLOR};">{_fmt_num(total_vol_q1)}</div>
          <div style="font-size:10px;">{_delta_pct(total_vol_q4, total_vol_q1)} vs {PERIOD_P4}</div>
        </div>
        <div style="background:{LIGHT_BG};border-radius:6px;padding:8px 10px;text-align:center;">
          <div style="font-size:9px;color:#888;text-transform:uppercase;margin-bottom:2px;">OS Coverage</div>
          <div style="font-size:16px;font-weight:700;color:{BRAND_COLOR};">{_fmt_cov(total_cov_q1)}</div>
          <div style="font-size:10px;">{cov_delta_str} vs {PERIOD_P4}</div>
        </div>
      </div>
      <!-- Narrative -->
      <p style="font-size:12px;line-height:1.6;color:#444;margin:0 0 10px;">
        Across {n_territories} territories and {total_kws:,} classified keywords, {H(BRAND_NAME)} delivered
        {_fmt_num(total_os_q1)} OneSearch clicks in {PERIOD_P1} — {os_delta_str} vs {PERIOD_P4} —
        at {_fmt_cov(total_cov_q1)} average coverage ({cov_delta_str} QoQ).
      </p>
      <div style="font-size:9px;font-weight:700;color:#2e7d32;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">SEO Highlights</div>
      <p style="font-size:11px;line-height:1.5;color:#444;margin:0 0 8px;">
        {_fmt_num(total_seo_q1)} SEO clicks in {PERIOD_P1} ({_delta_pct(total_seo_q4, total_seo_q1)} QoQ).
        Top SEO territory: <strong>{H(top_seo[0]) if top_seo[0] else "—"}</strong>
        ({_fmt_num(top_seo[1]["seo_clicks_q1"])} clicks).
      </p>
      <div style="font-size:9px;font-weight:700;color:#1565c0;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">SEM Highlights</div>
      <p style="font-size:11px;line-height:1.5;color:#444;margin:0 0 10px;">
        {_fmt_num(total_sem_q1)} paid clicks in {PERIOD_P1} ({_delta_pct(total_sem_q4, total_sem_q1)} QoQ).
        Top SEM territory: <strong>{H(top_sem[0]) if top_sem[0] else "—"}</strong>
        ({_fmt_num(top_sem[1]["sem_clicks_q1"])} clicks).
      </p>
      <div style="font-size:9px;font-weight:700;color:{BRAND_COLOR};text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">Q2 2026 Priorities</div>
      <ul style="list-style:disc;padding-left:16px;margin:0;font-size:11px;line-height:1.5;color:#444;">{q2_blist}</ul>
    </div>
    <div>
      <div style="font-size:9px;font-weight:700;color:{ACCENT_CLR};text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px;">&#9999; Analyst Commentary — click to edit</div>
      <div contenteditable="true" data-field-id="exec-summary" data-placeholder="Click to add your executive summary..."
           style="min-height:120px;font-size:12px;line-height:1.6;color:#e0e0e0;border:1px dashed #555;border-radius:6px;padding:8px 10px;background:#3a3a3a;outline:none;"
           onfocus="this.style.borderColor='{ACCENT_CLR}';this.style.background='#fff';"
           onblur="this.style.borderColor='#555';this.style.background='{LIGHT_BG}';"
           >Click to add your executive summary...</div>
    </div>
  </div>
  <!-- US-level action cards (SEO + SEM × Q1 + Q2) -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px;">
    {agg_card_q1_seo}
    {agg_card_q1_sem}
    {agg_card_q2_seo}
    {agg_card_q2_sem}
  </div>
</div>
''')

    # ── Territory sections ───────────────────────────────────────────────────────
    for i, (topic, s) in enumerate(sorted_t):
        color = TERRITORY_COLORS[i % len(TERRITORY_COLORS)]
        slug  = _slug(topic)
        cov_q1 = _cov(s['os_clicks_q1'], s['avg_volume'])
        cov_q4 = _cov(s['os_clicks_q4'], s['avg_volume'])
        total_conv_q1 = s['conv_seo_q1'] + s['conv_sem_q1']
        total_conv_q4 = s['conv_seo_q4'] + s['conv_sem_q4']

        top_rows = ''
        for kd in s['top_kws']:
            kw_cov = _cov(kd['os_q1'], kd['avg_vol'])
            top_rows += (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:5px 8px;font-size:11px;">{H(kd["kw"])}</td>'
                f'<td style="padding:5px 8px;text-align:right;font-size:11px;color:#888;">{_fmt_num(kd["avg_vol"])}</td>'
                f'<td style="padding:5px 8px;text-align:right;font-size:11px;font-weight:600;">{_fmt_num(kd["os_q1"])}</td>'
                f'<td style="padding:5px 8px;text-align:right;font-size:11px;">{_fmt_cov(kw_cov)}</td>'
                f'<td style="padding:5px 8px;text-align:right;font-size:11px;color:#2e7d32;">{_fmt_num(kd["seo_q1"])}</td>'
                f'<td style="padding:5px 8px;text-align:right;font-size:11px;color:#1565c0;">{_fmt_num(kd["sem_q1"])}</td>'
                f'</tr>'
            )

        card_q1_seo = _action_card(
            f'Q1 2026 — SEO Actions', _SEO_CLR, _SEO_LITE,
            _q1_seo_bullets(topic, s), f'q1-seo-{slug}',
            f'Add analyst notes for Q1 SEO — {H(topic)}…'
        )
        card_q1_sem = _action_card(
            f'Q1 2026 — SEM Actions', _SEM_CLR, _SEM_LITE,
            _q1_sem_bullets(topic, s), f'q1-sem-{slug}',
            f'Add analyst notes for Q1 SEM — {H(topic)}…'
        )
        card_q2_seo = _action_card(
            f'Q2 2026 Pipeline — SEO', _SEO_CLR, _SEO_LITE,
            _q2_seo_bullets(topic, s), f'q2-seo-{slug}',
            f'Add Q2 SEO pipeline notes — {H(topic)}…'
        )
        card_q2_sem = _action_card(
            f'Q2 2026 Pipeline — SEM', _SEM_CLR, _SEM_LITE,
            _q2_sem_bullets(topic, s), f'q2-sem-{slug}',
            f'Add Q2 SEM pipeline notes — {H(topic)}…'
        )

        os_evo   = _delta_pct(s['os_clicks_q4'],  s['os_clicks_q1'])
        seo_evo  = _delta_pct(s['seo_clicks_q4'], s['seo_clicks_q1'])
        sem_evo  = _delta_pct(s['sem_clicks_q4'], s['sem_clicks_q1'])
        cov_evo  = _delta_pp(cov_q4, cov_q1)
        conv_evo = _delta_pct(total_conv_q4, total_conv_q1)

        def _perf_row(label, q4, q1, evo, indent=False, fmt=_fmt_num):
            pad = '&nbsp;&nbsp;&nbsp;' if indent else ''
            v4 = q4 if isinstance(q4, str) else fmt(q4)
            v1 = q1 if isinstance(q1, str) else fmt(q1)
            return (
                f'<tr style="border-bottom:1px solid #f0f0f0;">'
                f'<td style="padding:6px 10px;font-size:11px;">{pad}{label}</td>'
                f'<td style="padding:6px 10px;text-align:right;font-size:11px;color:#888;">{v4}</td>'
                f'<td style="padding:6px 10px;text-align:right;font-size:11px;font-weight:600;">{v1}</td>'
                f'<td style="padding:6px 10px;text-align:right;font-size:11px;">{evo}</td>'
                f'</tr>'
            )

        parts.append(f'''
<!-- ===== {H(topic)} ===== -->
<div style="background:#fff;border-radius:10px;box-shadow:0 2px 6px rgba(0,0,0,.08);margin:0 24px 20px;overflow:hidden;">
  <!-- Header -->
  <div style="background:{color};padding:14px 20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
    <div>
      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:rgba(255,255,255,.7);">Territory {i+1}</div>
      <h2 style="font-size:18px;font-weight:700;color:#fff;margin:0;">{H(topic)}</h2>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <div style="background:rgba(255,255,255,.2);border-radius:8px;padding:6px 10px;text-align:center;">
        <div style="font-size:9px;color:rgba(255,255,255,.8);text-transform:uppercase;">Keywords</div>
        <div style="font-size:16px;font-weight:700;color:#fff;">{s["count"]}</div>
      </div>
      <div style="background:rgba(255,255,255,.2);border-radius:8px;padding:6px 10px;text-align:center;">
        <div style="font-size:9px;color:rgba(255,255,255,.8);text-transform:uppercase;">Avg Search Vol</div>
        <div style="font-size:16px;font-weight:700;color:#fff;">{_fmt_num(s["avg_volume"])}</div>
      </div>
      <div style="background:rgba(255,255,255,.2);border-radius:8px;padding:6px 10px;text-align:center;">
        <div style="font-size:9px;color:rgba(255,255,255,.8);text-transform:uppercase;">Coverage {PERIOD_P1}</div>
        <div style="font-size:16px;font-weight:700;color:#fff;">{_fmt_cov(cov_q1)}</div>
      </div>
    </div>
  </div>
  <!-- Performance Table -->
  <div style="padding:16px 20px 8px;">
    <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:16px;">
      <thead>
        <tr style="background:#f8f8f8;">
          <th style="padding:7px 10px;text-align:left;border-bottom:2px solid #ddd;font-weight:600;">Metric</th>
          <th style="padding:7px 10px;text-align:right;border-bottom:2px solid #ddd;font-weight:600;">{PERIOD_P4}</th>
          <th style="padding:7px 10px;text-align:right;border-bottom:2px solid #ddd;font-weight:600;">{PERIOD_P1}</th>
          <th style="padding:7px 10px;text-align:right;border-bottom:2px solid #ddd;font-weight:600;">Delta</th>
        </tr>
      </thead>
      <tbody>
        {_perf_row('Search Volume',    s['avg_volume'],      s['avg_volume'],      '—')}
        {_perf_row('OS Clicks',        s['os_clicks_q4'],   s['os_clicks_q1'],   os_evo)}
        {_perf_row('SEO Clicks',       s['seo_clicks_q4'],  s['seo_clicks_q1'],  seo_evo,  indent=True)}
        {_perf_row('SEM Clicks',       s['sem_clicks_q4'],  s['sem_clicks_q1'],  sem_evo,  indent=True)}
        {_perf_row('OS Coverage',      _fmt_cov(cov_q4),    _fmt_cov(cov_q1),    cov_evo, indent=False)}
        {_perf_row('MikMak Checkout',  total_conv_q4,       total_conv_q1,       conv_evo)}
      </tbody>
    </table>
  </div>
  <!-- Top Keywords -->
  <div style="padding:0 20px 12px;">
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#666;margin-bottom:6px;">Top Keywords by OS Clicks — {PERIOD_P1}</div>
    <table style="width:100%;border-collapse:collapse;font-size:11px;">
      <thead>
        <tr style="background:#f8f8f8;">
          <th style="padding:5px 8px;text-align:left;font-weight:600;">Keyword</th>
          <th style="padding:5px 8px;text-align:right;font-weight:600;">Avg Vol</th>
          <th style="padding:5px 8px;text-align:right;font-weight:600;">OS Clicks</th>
          <th style="padding:5px 8px;text-align:right;font-weight:600;">Coverage</th>
          <th style="padding:5px 8px;text-align:right;font-weight:600;color:#2e7d32;">SEO</th>
          <th style="padding:5px 8px;text-align:right;font-weight:600;color:#1565c0;">SEM</th>
        </tr>
      </thead>
      <tbody>{top_rows}</tbody>
    </table>
  </div>
</div>
''')

    parts.append('</div><!-- /territory-container -->')
    return '\n'.join(parts)


_JSON_EXPORT_CSS = f'''<style>
/* Commentary toolbar — bottom-right so it never overlaps the dashboard header */
#commentary-toolbar{{position:fixed;bottom:20px;right:20px;z-index:99999;background:rgba(255,255,255,.97);border:1px solid #ddd;border-radius:8px;padding:6px 12px;display:flex;align-items:center;gap:8px;box-shadow:0 2px 12px rgba(0,0,0,.15);font-family:-apple-system,sans-serif;font-size:11px;}}
#commentary-toolbar button,#commentary-toolbar label{{cursor:pointer;padding:4px 10px;border-radius:5px;font-size:11px;font-weight:600;border:none;background:{BRAND_COLOR};color:#fff;display:inline-flex;align-items:center;gap:3px;}}
#commentary-toolbar .imp-btn{{background:{LIGHT_BG};color:{BRAND_COLOR};border:1px solid #b0c4d8;}}
#commentary-toolbar input[type=file]{{display:none;}}
#commentary-toolbar .badge{{font-size:10px;color:#888;}}
#commentary-toolbar .tb-label{{font-size:10px;font-weight:600;color:{BRAND_COLOR};letter-spacing:.04em;}}
[contenteditable][data-placeholder]{{transition:border-color .15s,background .15s;}}
[contenteditable][data-is-placeholder]{{color:#aaa !important;font-style:italic;}}
/* CSS floating tooltips — title attr unreliable in Chrome */
.has-tip{{position:relative;}}
.has-tip::after{{content:attr(data-tooltip);display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:#1a1a2e;color:#fff;font-size:10px;line-height:1.4;padding:5px 8px;border-radius:5px;white-space:normal;max-width:220px;text-align:left;z-index:100000;pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,.25);}}
.has-tip::before{{content:'';display:none;position:absolute;bottom:calc(100% + 1px);left:50%;transform:translateX(-50%);border:5px solid transparent;border-top-color:#1a1a2e;z-index:100000;pointer-events:none;}}
.has-tip:hover::after,.has-tip:hover::before{{display:block;}}
/* Downward tooltip variant — for use inside table headers where upward is clipped */
.th-tip{{position:relative;display:inline-block;cursor:help;color:#aaa;font-size:10px;margin-left:3px;vertical-align:middle;}}
.th-tip::after{{content:attr(data-tooltip);display:none;position:fixed;background:#1a1a2e;color:#fff;font-size:10px;line-height:1.5;padding:6px 10px;border-radius:5px;white-space:normal;width:220px;text-align:left;z-index:999999;pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,.3);}}
.th-tip:hover::after{{display:block;top:var(--tt-y);left:var(--tt-x);}}
</style>'''

_JSON_EXPORT_HTML = '''<div id="commentary-toolbar">
  <span class="tb-label">NOTES</span>
  <span class="badge" id="edit-count"></span>
  <button onclick="exportCommentary()">&#8595; Export</button>
  <label class="imp-btn">&#8593; Import<input type="file" accept=".json" onchange="importCommentary(event)"></label>
</div>'''

_JSON_EXPORT_JS = f'''<script>
(function(){{
  /* Commentary store — keyed by data-field-id.
     Uses an in-memory object so export works regardless of tab visibility
     (innerText returns '' for display:none elements in Chrome). */
  var _store = {{}};
  var LS_KEY = 'os_commentary_{re.sub(r"[^a-z0-9]", "_", BRAND_NAME.lower())}';

  /* Restore from localStorage on load */
  try {{ var _ls = localStorage.getItem(LS_KEY); if(_ls) _store = JSON.parse(_ls); }} catch(e){{}}

  function _saveLS(){{ try{{ localStorage.setItem(LS_KEY, JSON.stringify(_store)); }}catch(e){{}} }}

  function countFilled(){{
    var total = document.querySelectorAll('[contenteditable][data-field-id]').length;
    var n = Object.keys(_store).length;
    var b = document.getElementById('edit-count');
    if(b) b.textContent = n + '/' + total + ' notes';
  }}

  function initField(el){{
    var fid = el.getAttribute('data-field-id');
    var ph  = el.getAttribute('data-placeholder') || '';
    /* If we have saved content for this field, restore it */
    if(_store[fid]){{
      el.textContent = _store[fid];
      el.removeAttribute('data-is-placeholder');
    }} else {{
      el.setAttribute('data-is-placeholder','1');
      el.textContent = ph;
    }}
    /* Clear placeholder on first focus */
    el.addEventListener('focus', function(){{
      if(el.getAttribute('data-is-placeholder') === '1'){{
        el.textContent = '';
        el.removeAttribute('data-is-placeholder');
      }}
    }});
    /* Restore placeholder if left empty */
    el.addEventListener('blur', function(){{
      if(!el.textContent.trim()){{
        el.textContent = ph;
        el.setAttribute('data-is-placeholder','1');
        delete _store[fid];
        _saveLS(); countFilled();
      }}
    }});
    /* Save to store on every keystroke */
    el.addEventListener('input', function(){{
      el.removeAttribute('data-is-placeholder');
      var t = el.textContent.trim();
      if(t) _store[fid] = t; else delete _store[fid];
      _saveLS(); countFilled();
    }});
  }}

  function initAll(){{
    document.querySelectorAll('[contenteditable][data-field-id]').forEach(initField);
    countFilled();
  }}

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAll);
  else setTimeout(initAll, 150);

  window._commentaryInitField = initField;

  window.exportCommentary = function(){{
    var data = {{_meta:{{brand:{json.dumps(BRAND_NAME)},period:{json.dumps(PERIOD)},exported:new Date().toISOString()}}}};
    Object.assign(data, _store);
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{{type:'application/json'}}));
    a.download = '{re.sub(r"[^a-z0-9]+", "_", BRAND_NAME.lower())}_commentary_'+new Date().toISOString().slice(0,10)+'.json';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }};

  window.importCommentary = function(ev){{
    var file = ev.target.files[0]; if(!file) return;
    var r = new FileReader();
    r.onload = function(e){{
      try{{
        var d = JSON.parse(e.target.result); var n = 0;
        Object.keys(d).forEach(function(k){{
          if(k.startsWith('_')) return;
          _store[k] = d[k];
          var el = document.querySelector('[data-field-id="'+k+'"]');
          if(el){{
            el.textContent = d[k];
            el.removeAttribute('data-is-placeholder');
            el.style.borderStyle = 'solid';
            el.style.borderColor = '{ACCENT_CLR}';
            n++;
          }}
        }});
        _saveLS(); countFilled();
        alert('Imported '+n+' fields.');
      }} catch(err){{ alert('Error: '+err.message); }}
    }};
    r.readAsText(file); ev.target.value = '';
  }};
}})();
// th-tip: position:fixed tooltips for table headers (upward tooltip clipped by table overflow)
document.querySelectorAll('.th-tip').forEach(function(el){{
  el.addEventListener('mousemove', function(e){{
    el.style.setProperty('--tt-x', (e.clientX + 12) + 'px');
    el.style.setProperty('--tt-y', (e.clientY + 14) + 'px');
  }});
}});
</script>'''


def inject_reco_filter(html):
    """Inject RECO_STATUS, RECO_MERGE_GROUPS, filter tabs, and row-status rendering.

    Reads OS_RECO_FILTER and OS_RECO_MERGE_GROUPS from module-level config.
    Safe to call with empty dicts — all rows will show as 'active'.

    For new brands: define OS_RECO_FILTER and OS_RECO_MERGE_GROUPS at the top
    of the brand-specific build script, then call this function in the pipeline.
    """
    import json as _json

    # Serialize Python dicts → JS object literals
    reco_status_js = 'const RECO_STATUS = ' + _json.dumps(OS_RECO_FILTER, indent=4) + ';'

    merge_groups_entries = []
    for key, cfg in OS_RECO_MERGE_GROUPS.items():
        entry = (
            f'    {_json.dumps(key)}: {{\n'
            f'      cat:    {_json.dumps(cfg["cat"])},\n'
            f'      subcat: {_json.dumps(cfg["subcat"])},\n'
            f'      note:   {_json.dumps(cfg["note"])},\n'
            f'      channel: {_json.dumps(cfg["channel"])},\n'
            f'      channelClass: {_json.dumps(cfg["channelClass"])},\n'
            f'    }}'
        )
        merge_groups_entries.append(entry)
    merge_groups_js = 'const RECO_MERGE_GROUPS = {\n' + ',\n'.join(merge_groups_entries) + '\n  };'

    accum_js = (
        'const _mergeAccum = {};\n'
        '  Object.keys(RECO_MERGE_GROUPS).forEach(function(gk) {\n'
        '    _mergeAccum[gk] = {vol:0,clics_seo:0,clics_sem:0,ca:0,vol_p:0,clics_p:0,ca_p:0,kw_count:0,kws:[]};\n'
        '  });\n'
        f'  const RECO_TINY_THRESHOLD = {OS_RECO_TINY_THRESHOLD};\n'
        '  const _tinyAccum = {};'
    )

    config_block = (
        '  // ── RECO_STATUS: per-brand filter config (generated by build script) ────\n'
        f'  {reco_status_js}\n'
        f'  {merge_groups_js}\n'
        f'  {accum_js}\n\n'
    )

    # Inject config at top of renderRecommendations() — unique anchor, correct scope
    reco_fn_anchor = "function renderRecommendations(){\n  const tbody = document.getElementById('recoBody');\n"
    if reco_fn_anchor in html:
        html = html.replace(reco_fn_anchor, reco_fn_anchor + config_block, 1)
    else:
        print('  WARNING: inject_reco_filter — renderRecommendations anchor not found, skipping config injection')

    # Filter tabs above the reco section
    old_section = (
        '<div class="section-title">Detailed SEO / SEM Recommendations by Sub-Category</div>\n'
        '<div class="reco-section">'
    )
    new_section = (
        '<div class="section-title">Detailed SEO / SEM Recommendations by Sub-Category</div>\n'
        '<div style="display:flex;align-items:center;gap:8px;padding:10px 24px 4px;background:#f4f4f4;border-bottom:1px solid #e0e0e0;">\n'
        '  <span style="font-size:10px;font-weight:700;color:#888;text-transform:uppercase;letter-spacing:.05em;margin-right:4px;">Show:</span>\n'
        '  <button class="reco-filter-btn" data-mode="active" onclick="filterRecoTable(this)" style="font-size:11px;padding:4px 14px;border:1px solid #1a7aad;border-radius:20px;background:#1a7aad;color:#fff;cursor:pointer;font-weight:600;">Active</button>\n'
        '  <button class="reco-filter-btn" data-mode="long-term" onclick="filterRecoTable(this)" style="font-size:11px;padding:4px 14px;border:1px solid #78909c;border-radius:20px;background:#fff;color:#78909c;cursor:pointer;font-weight:600;">Long-term</button>\n'
        '  <button class="reco-filter-btn" data-mode="all" onclick="filterRecoTable(this)" style="font-size:11px;padding:4px 14px;border:1px solid #bbb;border-radius:20px;background:#fff;color:#888;cursor:pointer;font-weight:600;">All</button>\n'
        '  <span id="reco-row-count" style="font-size:10px;color:#aaa;margin-left:6px;"></span>\n'
        '</div>\n'
        '<div class="reco-section">'
    )
    if old_section in html:
        html = html.replace(old_section, new_section, 1)
    else:
        print('  WARNING: inject_reco_filter — section title not found, skipping filter tabs')

    # Filter JS + row-status rendering are injected by patch_onesearch_js via
    # the substitution list. This function only handles the config + UI.
    return html


def inject_export_ui(html):
    html = html.replace('</head>', _JSON_EXPORT_CSS + '\n</head>', 1)
    body_pos = html.find('<body')
    body_end  = html.find('>', body_pos) + 1
    html = html[:body_end] + '\n' + _JSON_EXPORT_HTML + html[body_end:]
    html += '\n' + _JSON_EXPORT_JS
    return html


def inject_brand_config(html, brand_regex):
    """Inject per-client config as JS globals used by OneSearch Dashboard JS.

    OS_BRAND_REGEX        — RegExp to detect brand keywords
    OS_TOPIC_ORDER        — display order for Coverage gauges (empty = vol-desc auto)
    OS_COV_TARGET_BRAND   — coverage target % for branded territory gauges
    OS_COV_TARGET_GENERIC — coverage target % for non-branded territory gauges
    OS_TERRITORY_TOPICS   — ordered TOPICS list for Core Search Territories widget
    """
    topic_order_js     = json.dumps(TOPIC_ORDER)
    territory_topics_js = json.dumps(TERRITORY_TOPICS)
    # Escape backslashes in the regex for embedding in a JS string
    regex_escaped  = brand_regex.replace('\\', '\\\\').replace('/', '\\/')
    script = (
        '\n<script id="os-brand-config">\n'
        f'var OS_BRAND_REGEX = new RegExp({json.dumps(regex_escaped)}, "i");\n'
        f'var OS_TOPIC_ORDER = {topic_order_js};\n'
        f'var OS_COV_TARGET_BRAND   = {COV_TARGET_BRAND};\n'
        f'var OS_COV_TARGET_GENERIC = {COV_TARGET_GENERIC};\n'
        f'var OS_TERRITORY_TOPICS   = {territory_topics_js};\n'
        '</script>\n'
    )
    # Inject right after </head> so it's available before any panel JS runs
    return html.replace('</head>', script + '</head>', 1)


def replace_territory_panel(html, new_content):
    open_tag   = '<div id="panel-territory" class="tab-panel">'
    next_panel = '<div id="panel-recos" class="tab-panel">'
    start = html.index(open_tag) + len(open_tag)
    end   = html.index(next_panel)
    # Close panel-territory before the next panel opens — without this the
    # subsequent panels nest inside panel-territory and become invisible.
    return html[:start] + '\n' + new_content + '\n</div>\n\n' + html[end:]


# ── JavaScript serialization ────────────────────────────────────────────────────

def _js_val(v):
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        formatted = f'{v:.4f}'.rstrip('0').rstrip('.')
        return formatted if formatted else '0'
    return str(v)


def js_data(data_rows):
    lines = ['const DATA = [']
    for i, dr in enumerate(data_rows):
        comma = ',' if i < len(data_rows) - 1 else ''
        lines.append('  [' + ','.join(_js_val(v) for v in dr) + ']' + comma)
    lines.append('];')
    return '\n'.join(lines)


def js_tags(tags):
    lines = ['const TAGS = {']
    items = list(tags.items())
    for i, (kw, tag_dict) in enumerate(items):
        comma = ',' if i < len(items) - 1 else ''
        inner = ','.join(f'{json.dumps(k, ensure_ascii=False)}:{json.dumps(v, ensure_ascii=False)}'
                         for k, v in tag_dict.items())
        lines.append(f'  {json.dumps(kw, ensure_ascii=False)}:{{{inner}}}{comma}')
    lines.append('};')
    return '\n'.join(lines)


# ── Template injection ──────────────────────────────────────────────────────────

def replace_block(html, varname, new_block, decl='const'):
    """Replace `const/var VARNAME = [...];` or `{...};`.
    First occurrence gets new_block verbatim; subsequent occurrences get a bare
    reassignment (no const/var) to avoid redeclaration SyntaxErrors."""
    pattern = rf'(?:const|var)\s+{re.escape(varname)}\s*=\s*(?:\[[\s\S]*?\]|\{{[\s\S]*?\}});'
    seen = [0]

    def _replacer(m):
        seen[0] += 1
        if seen[0] == 1:
            return new_block
        # Strip leading const/var declaration for subsequent occurrences
        return re.sub(r'^(?:const|var)\s+', '', new_block, count=1)

    result = re.sub(pattern, _replacer, html, flags=re.DOTALL)
    return result, seen[0]


def apply_brand(html):
    subs = [
        # Title
        ('OneSearch Dashboard - Activia Canada', f'OneSearch Dashboard — {BRAND_NAME}'),
        ('OneSearch Dashboard – Activia Canada', f'OneSearch Dashboard — {BRAND_NAME}'),
        # Header / subtitle text
        ('Activia Canada', BRAND_NAME),
        ('ACTIVIA CA', BRAND_NAME.upper()),
        ('Activia', 'Oikos'),
        # Section title color (deep red → deep teal)
        ('#8b0000', BRAND_COLOR),
        # Accent red → accent blue
        ('#B8001C', BRAND_COLOR),
        ('#E8374A', ACCENT_CLR),
        # Very light pink bg → very light blue bg
        ('#fef5f5', LIGHT_BG),
        # Text color references
        ('color: #B8001C', f'color: {BRAND_COLOR}'),
        ("color: '#B8001C'", f"color: '{BRAND_COLOR}'"),
        ("color: '#E8374A'", f"color: '{ACCENT_CLR}'"),
        # Border color
        ('border-left: 3px solid #E8374A', f'border-left: 3px solid {BRAND_COLOR}'),
        ('border-right: 3px solid #4CAF50', 'border-right: 3px solid #2e7d32'),
        # OS_TOPIC_COLORS brand key — Activia had 'PRODUCTS' as dark red; keep structure
        ("'#B8001C'", f"'{BRAND_COLOR}'"),
    ]
    for old, new in subs:
        html = html.replace(old, new)
    return html


def apply_english(html):
    """Replace French UI labels with English equivalents and fix broken JS elements."""
    subs = [
        # Filter dropdowns
        ("innerHTML='<option value=\"\">Toutes</option>'",
         "innerHTML='<option value=\"\">All</option>'"),
        # Pie chart / breakdown labels
        ("'Autres'", "'Others'"),
        ('"Autres"', '"Others"'),
        ("|| 'Autre'", "|| 'Other'"),
        ("|| \"Autre\"", '|| "Other"'),
        ("==='Autre'", "==='Other'"),
        ('==="Autre"', '==="Other"'),
        # Metric label in breakdown table
        ("label: 'Clics'", "label: 'Clicks'"),
        ('label: "Clics"', 'label: "Clicks"'),
        # French match type strings visible in QS/SQR columns (keep data strings as-is,
        # only translate UI labels above)
        # SQR Detail by Keyword: rename "Demand" column header to "Search Demand"
        ('<th class="num">Demand</th><th class="num">Evo</th>\n        <th class="num">SEO Clicks</th>',
         '<th class="num">Search Demand</th><th class="num">Evo</th>\n        <th class="num">SEO Clicks</th>'),
    ]
    for old, new in subs:
        html = html.replace(old, new)

    # Fix reco filter: inject a hidden select + safe recoFilter so onclick handlers don't crash
    reco_fix = (
        '\n<select id="reco-filter-channel" style="display:none">'
        '<option value="all"></option>'
        '<option value="seo"></option>'
        '<option value="sem"></option>'
        '<option value="both"></option>'
        '</select>'
        '\n<script>window.recoFilter = window.recoFilter || function(){};</script>\n'
    )
    html = html.replace('<div id="panel-recos"', reco_fix + '<div id="panel-recos"', 1)
    return html


def patch_onesearch_js(html):
    """Fix OneSearch Dashboard JS: brand filter, topic order, dynamic territories,
    'Others' deduplication, KPI grid columns, and remove Activia-specific hardcodings.
    All brand/client-specific values come from the OS_* config variables injected by
    inject_brand_config(), not hardcoded here."""
    subs = [
        # JS comment + brand-country example string: Activia Canada → Oikos USA
        ("// Detects if a brand+country term is in the examples (e.g. \"activia canada\")",
         "// Detects if a brand+country term is in the examples (e.g. \"oikos usa\")"),
        ("<em>activia canada</em>",
         "<em>oikos usa</em>"),

        # KPI insights grid: 5 columns → 4 (only 4 cards rendered for this client)
        ('grid-template-columns:repeat(5,1fr)',
         'grid-template-columns:repeat(4,1fr)'),

        # Brand filter: use per-client regex (OS_BRAND_REGEX) on keyword text instead
        # of a hardcoded category check or campaign-name prefix
        ("const mf = (r[3]||'').startsWith('Danone') ? 'Marque' : 'Hors marque';",
         "const mf = (typeof OS_BRAND_REGEX!=='undefined'&&OS_BRAND_REGEX.test((r[0]||'').toLowerCase())) ? 'Brand' : 'Non-Brand';"),
        ("if(m==='marque'     && mf!=='Marque') return false;",
         "if(m==='marque'     && mf!=='Brand') return false;"),
        ("if(m==='horsmarque' && mf==='Marque') return false;",
         "if(m==='horsmarque' && mf!=='Non-Brand') return false;"),

        # Topic display order: use OS_TOPIC_ORDER (empty = auto-sort by volume)
        ("const _topicOrder=['PRODUCTS','HEALTH','EATING BETTER','RECIPES'];",
         "const _topicOrder=(typeof OS_TOPIC_ORDER!=='undefined'&&OS_TOPIC_ORDER.length)?OS_TOPIC_ORDER:[];"),

        # Update sort to fall back to volume desc when _topicOrder is empty
        (
            "const ia=_topicOrder.indexOf(a[0]); const ib=_topicOrder.indexOf(b[0]);\n"
            "    if(ia!==-1&&ib!==-1)return ia-ib;\n"
            "    if(ia!==-1)return -1; if(ib!==-1)return 1;\n"
            "    return b[1].volC-a[1].volC;",
            "if(!_topicOrder.length)return b[1].volC-a[1].volC;\n"
            "    const ia=_topicOrder.indexOf(a[0]); const ib=_topicOrder.indexOf(b[0]);\n"
            "    if(ia!==-1&&ib!==-1)return ia-ib;\n"
            "    if(ia!==-1)return -1; if(ib!==-1)return 1;\n"
            "    return b[1].volC-a[1].volC;"
        ),

        # Null fallback → 'Others' so ungrouped keywords merge with the donut tail
        ("|| 'Other'", "|| 'Others'"),

        # Coverage target thresholds: use OS_COV_TARGET_* instead of Activia hardcodings
        (
            "const objPct = nameLow.includes('pure brand') ? 30 : nameLow.includes('danone') || nameLow.includes('brand') ? 10 : 3;",
            "const _tBrand=(typeof OS_COV_TARGET_BRAND!=='undefined')?OS_COV_TARGET_BRAND:10;\n"
            "    const _tGeneric=(typeof OS_COV_TARGET_GENERIC!=='undefined')?OS_COV_TARGET_GENERIC:3;\n"
            "    const objPct = nameLow.includes('brand') ? _tBrand : _tGeneric;"
        ),

        # Donut chart BLACK_KEYS: remove Activia-specific brand name hardcodings
        ("const BLACK_KEYS = new Set(['PRODUCTS', 'Danone - Pure Brand']);",
         "const BLACK_KEYS = new Set([]);"),

        # SEO+SEM force override: replace Activia sub-category names with 'Brand'
        ("const _SEO_SEM_FORCE = new Set(['Danone - Pure Brand','Danone - Probiotics','Probiotic yogurt']);",
         "const _SEO_SEM_FORCE = new Set(['Brand']);"),

        # Split single "Conversions (QV)" KPI column into MikMak Checkout + MM Offline Store
        # Header
        ('<th>Conversions (QV)</th>',
         '<th>MM Checkout</th><th>MM Offline Store</th>'),

        # OS row: show seoCaC (checkout) + semCaC (offline) in two separate cells
        ('<td class="kpi-cell"><span class="kv" id="k-os-ca">—</span><span class="ke" id="k-os-ca-e"></span></td>',
         '<td class="kpi-cell"><span class="kv" id="k-os-ca-checkout">—</span><span class="ke" id="k-os-ca-checkout-e"></span></td>'
         '<td class="kpi-cell"><span class="kv" id="k-os-ca-offline">—</span><span class="ke" id="k-os-ca-offline-e"></span></td>'),

        # SEO row: checkout cell only (offline = dash)
        ('<td class="kpi-cell"><span class="kv" id="k-seo-ca">—</span><span class="ke" id="k-seo-ca-e"></span></td>',
         '<td class="kpi-cell"><span class="kv" id="k-seo-ca-checkout">—</span><span class="ke" id="k-seo-ca-checkout-e"></span></td>'
         '<td class="kpi-cell"><span class="kv" id="k-seo-ca-offline" style="color:#bbb;">—</span><span class="ke"></span></td>'),

        # SEM row: offline cell only (checkout = dash)
        ('<td class="kpi-cell"><span class="kv" id="k-sem-ca">—</span><span class="ke" id="k-sem-ca-e"></span></td>',
         '<td class="kpi-cell"><span class="kv" id="k-sem-ca-checkout" style="color:#bbb;">—</span><span class="ke"></span></td>'
         '<td class="kpi-cell"><span class="kv" id="k-sem-ca-offline">—</span><span class="ke" id="k-sem-ca-offline-e"></span></td>'),

        # renderKPIs: replace setKpi ca calls with split checkout/offline calls
        (
            "setKpi('os', 'ca',    osCaC,    osCaP);",
            "setKpi('os', 'ca-checkout', seoCaC, seoCaP);\n"
            "  setKpi('os', 'ca-offline',  semCaC, semCaP);"
        ),
        (
            "setKpi('seo','ca',    seoCaC,   seoCaP);",
            "setKpi('seo','ca-checkout', seoCaC, seoCaP);"
        ),
        (
            "setKpi('sem','ca',    semCaC,   semCaP);",
            "setKpi('sem','ca-offline',  semCaC, semCaP);"
        ),

        # setKpi function: add 'ca-checkout' and 'ca-offline' to the fmtCur branch
        (
            "else if(col==='cout'||col==='ca') el.textContent=fmtCur(val);",
            "else if(col==='cout'||col==='ca'||col==='ca-checkout'||col==='ca-offline') el.textContent=fmtCur(val);"
        ),

        # Replace reco row rendering with RECO_STATUS-aware version
        # (inject_reco_filter handles the config; this handles the per-row logic)
        (
            "    html2 += '<tr>'\n"
            "      +'<td><strong>'+cat+'</strong>'+qsChip+'<div class=\"reco-metrics\">'+d.kw_count+' keywords</div></td>'",
            "    const _recoFid = 'reco-json-'+(cat+'-'+subcat).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'');\n"
            "    var _rawStatus = RECO_STATUS[_recoFid] || 'active';\n"
            "    var _isMerge   = _rawStatus.startsWith('merge:');\n"
            "    var _mergeKey  = _isMerge ? _rawStatus.slice(6) : null;\n"
            "    if (_isMerge && _mergeAccum[_mergeKey]) {\n"
            "      var acc = _mergeAccum[_mergeKey];\n"
            "      acc.vol+=d.vol; acc.vol_p+=d.vol_p||0;\n"
            "      acc.clics_seo+=d.clics_seo; acc.clics_sem+=d.clics_sem;\n"
            "      acc.clics_p+=(d.clics_seo_p||0)+(d.clics_sem_p||0);\n"
            "      acc.ca+=(d.ca_seo||0)+(d.ca_sem||0);\n"
            "      acc.kw_count+=d.kw_count;\n"
            "      acc.kws=acc.kws.concat(d.kw_examples||[]);\n"
            "    } else {\n"
            "    var _status = _rawStatus;\n"
            "    var _trAttr = _status==='remove'\n"
            "      ? ' data-status=\"removed\" style=\"display:none;\"'\n"
            "      : ' data-status=\"'+(_status==='priority'?'priority':_status==='long-term'?'long-term':'active')+'\"';\n"
            "    var _statusBadge = _status==='priority'\n"
            "      ? '<span style=\"background:#e65100;color:#fff;font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;margin-left:5px;vertical-align:middle;\">&#9733; PRIORITY</span>'\n"
            "      : _status==='long-term'\n"
            "      ? '<span style=\"background:#78909c;color:#fff;font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;margin-left:5px;vertical-align:middle;\">LONG-TERM</span>'\n"
            "      : '';\n"
            "    var _rowStyle = _status==='long-term' ? ' style=\"opacity:.8;\"' : '';\n"
            "    html2 += '<tr'+_trAttr+(_status==='remove'?'':_rowStyle)+'>'\n"
            "      +'<td><strong>'+cat+'</strong>'+qsChip+'<div class=\"reco-metrics\">'+d.kw_count+' keywords</div></td>'"
        ),

        # Append JSON textarea + close row (inside the else branch)
        (
            "+'<td style=\"max-width:380px;\">'+_fmtReco(reco)+kwEx+'</td>'\n"
            "      +'</tr>';",
            "+'<td style=\"max-width:380px;\">'+_fmtReco(reco)+kwEx\n"
            "      +'<div contenteditable=\"true\"'\n"
            "      +' data-field-id=\"'+_recoFid+'\"'\n"
            "      +' data-placeholder=\"Add analyst notes (JSON or plain text)\\u2026\"'\n"
            "      +' style=\"min-height:36px;font-size:10px;line-height:1.5;color:#e0e0e0;border:1px dashed #555;border-radius:4px;padding:5px 7px;background:#3a3a3a;outline:none;margin-top:6px;font-family:monospace;white-space:pre-wrap;\"'\n"
            "      +' onfocus=\"this.style.borderColor=\\'#1a7aad\\';this.style.background=\\'#fff\\';\"'\n"
            "      +' onblur=\"this.style.borderColor=\\'#555\\';this.style.background=\\'#3a3a3a\\';\"'\n"
            "      +'></div>'\n"
            "      +'</td>'\n"
            "      +'</tr>';\n"
            "    }"
        ),

        # After tbody: render merge rows, init commentary, add filterRecoTable JS
        (
            "  tbody.innerHTML = html2;\n}",
            "  // Render merge group rows\n"
            "  Object.entries(RECO_MERGE_GROUPS).forEach(function(entry) {\n"
            "    var gk=entry[0],cfg=entry[1],acc=_mergeAccum[gk];\n"
            "    if(!acc.kw_count) return;\n"
            "    var mergedCov=acc.vol>0?((acc.clics_seo+acc.clics_sem)/acc.vol*100).toFixed(1)+'%':'—';\n"
            "    var mergedKws=acc.kws.sort(function(a,b){return b[1]-a[1];}).slice(0,4).map(function(x){return '<em>'+x[0]+'</em>';}).join(', ');\n"
            "    html2+='<tr data-status=\"long-term\" style=\"opacity:.8;border-left:3px solid #78909c;\">'\n"
            "      +'<td><strong>'+cfg.cat+'</strong><div class=\"reco-metrics\">'+acc.kw_count+' kw (merged)</div></td>'\n"
            "      +'<td style=\"font-size:11px;color:#555;\">'+cfg.subcat+'<span style=\"background:#78909c;color:#fff;font-size:9px;font-weight:700;padding:1px 6px;border-radius:3px;margin-left:5px;vertical-align:middle;\">MERGED · LONG-TERM</span></td>'\n"
            "      +'<td><span style=\"color:#bbb;font-size:11px;\">—</span></td>'\n"
            "      +'<td><span class=\"channel-badge '+cfg.channelClass+'\">'+cfg.channel+'</span></td>'\n"
            "      +'<td class=\"num\">'+fmtN(acc.vol)+'</td>'\n"
            "      +'<td class=\"num\">'+fmtN(acc.clics_seo+acc.clics_sem)+'</td>'\n"
            "      +'<td class=\"num\">'+fmtC(acc.ca)+'</td>'\n"
            "      +'<td class=\"num\">'+mergedCov+'</td>'\n"
            "      +'<td style=\"max-width:380px;\">'+_fmtReco(cfg.note)+'<div class=\"reco-kw-ex\" style=\"margin-top:4px;\">e.g.: '+mergedKws+'</div></td>'\n"
            "      +'</tr>';\n"
            "  });\n"
            "  tbody.innerHTML = html2;\n"
            "  document.querySelectorAll('#recoBody [contenteditable][data-field-id]').forEach(function(el){\n"
            "    if(window._commentaryInitField) window._commentaryInitField(el);\n"
            "  });\n"
            "  // Auto-apply 'Active' filter on load\n"
            "  var _defaultBtn=document.querySelector('.reco-filter-btn[data-mode=\"active\"]');\n"
            "  if(_defaultBtn) filterRecoTable(_defaultBtn);\n"
            "}\n"
            "function filterRecoTable(btn) {\n"
            "  var mode=btn.getAttribute('data-mode');\n"
            "  var rows=document.querySelectorAll('#recoBody tr[data-status]');\n"
            "  var shown=0;\n"
            "  rows.forEach(function(tr){\n"
            "    var s=tr.getAttribute('data-status')||'active';\n"
            "    var visible=mode==='all'||(mode==='active'&&(s==='active'||s==='priority'))||(mode==='long-term'&&s==='long-term');\n"
            "    tr.style.display=visible?'':'none';\n"
            "    if(visible) shown++;\n"
            "  });\n"
            "  document.querySelectorAll('.reco-filter-btn').forEach(function(b){\n"
            "    b.style.background='#fff'; b.style.color=b.style.borderColor;\n"
            "  });\n"
            "  btn.style.background=btn.style.borderColor; btn.style.color='#fff';\n"
            "  var el=document.getElementById('reco-row-count');\n"
            "  if(el) el.textContent=shown+' rows shown';\n"
            "}"
        ),

        # SQR Detail by Keyword — Search Demand: fall back to Average Search Volume (r[4]*3)
        # when Volume Q1 (r[5]) is blank. Rows enriched only via SE Ranking API have r[4]
        # populated but r[5]/r[6] empty; without this they show 0 in the Demand column.
        (
            "    const volC=r[5]||0, volP=r[6]||0;\n"
            "    const seoC=r[13]||0, seoP=r[15]||0;\n"
            "    const semC=r[14]||0, semP=r[16]||0;\n"
            "    const caOS=(r[25]||0)+(r[26]||0);\n"
            "    const covOS=volC>0?(seoC+semC)/volC:0;",
            "    const _avgVol=(r[4]||0)*3;\n"
            "    const volC=r[5]||_avgVol, volP=r[6]||_avgVol;\n"
            "    const seoC=r[13]||0, seoP=r[15]||0;\n"
            "    const semC=r[14]||0, semP=r[16]||0;\n"
            "    const caOS=(r[25]||0)+(r[26]||0);\n"
            "    const covOS=volC>0?(seoC+semC)/volC:0;"
        ),

        # SQR Insight cards: add JSON commentary box to Wasted Budget card
        (
            "+'<div style=\"margin-top:8px;font-size:10px;color:#888;line-height:1.5;\"><strong>Top wasted terms:</strong> '+ltTop+'</div>'\n"
            "    +'</div></div>';",
            "+'<div style=\"margin-top:8px;font-size:10px;color:#888;line-height:1.5;\"><strong>Top wasted terms:</strong> '+ltTop+'</div>'\n"
            "    +'<div contenteditable=\"true\"'\n"
            "    +' data-field-id=\"sqr-insights-wasted\"'\n"
            "    +' data-placeholder=\"Add analyst notes\\u2026\"'\n"
            "    +' style=\"min-height:36px;font-size:10px;line-height:1.5;color:#e0e0e0;border:1px dashed #555;border-radius:4px;padding:5px 7px;background:#3a3a3a;outline:none;margin-top:8px;font-family:monospace;white-space:pre-wrap;\"'\n"
            "    +' onfocus=\"this.style.borderColor=\\'#1a7aad\\';this.style.background=\\'#fff\\';\"'\n"
            "    +' onblur=\"this.style.borderColor=\\'#c0cfe0\\';this.style.background=\\'#f8f9fb\\';\"'\n"
            "    +'></div>'\n"
            "    +'</div></div>';"
        ),

        # SQR Insight cards: add JSON commentary box to Regressions card
        (
            "+'<div style=\"margin-top:8px;font-size:10px;color:#888;line-height:1.5;\"><strong>Top declining:</strong> '+regTop+'</div>'\n"
            "    +'</div></div>';",
            "+'<div style=\"margin-top:8px;font-size:10px;color:#888;line-height:1.5;\"><strong>Top declining:</strong> '+regTop+'</div>'\n"
            "    +'<div contenteditable=\"true\"'\n"
            "    +' data-field-id=\"sqr-insights-regression\"'\n"
            "    +' data-placeholder=\"Add analyst notes\\u2026\"'\n"
            "    +' style=\"min-height:36px;font-size:10px;line-height:1.5;color:#e0e0e0;border:1px dashed #555;border-radius:4px;padding:5px 7px;background:#3a3a3a;outline:none;margin-top:8px;font-family:monospace;white-space:pre-wrap;\"'\n"
            "    +' onfocus=\"this.style.borderColor=\\'#1a7aad\\';this.style.background=\\'#fff\\';\"'\n"
            "    +' onblur=\"this.style.borderColor=\\'#c0cfe0\\';this.style.background=\\'#f8f9fb\\';\"'\n"
            "    +'></div>'\n"
            "    +'</div></div>';"
        ),

        # SQR Insight cards: add JSON commentary box to Rising Stars card
        (
            "+'<div style=\"margin-top:8px;font-size:10px;color:#888;line-height:1.5;\"><strong>Top rising:</strong> '+starsTop+'</div>'\n"
            "    +'</div></div>';",
            "+'<div style=\"margin-top:8px;font-size:10px;color:#888;line-height:1.5;\"><strong>Top rising:</strong> '+starsTop+'</div>'\n"
            "    +'<div contenteditable=\"true\"'\n"
            "    +' data-field-id=\"sqr-insights-rising\"'\n"
            "    +' data-placeholder=\"Add analyst notes\\u2026\"'\n"
            "    +' style=\"min-height:36px;font-size:10px;line-height:1.5;color:#e0e0e0;border:1px dashed #555;border-radius:4px;padding:5px 7px;background:#3a3a3a;outline:none;margin-top:8px;font-family:monospace;white-space:pre-wrap;\"'\n"
            "    +' onfocus=\"this.style.borderColor=\\'#1a7aad\\';this.style.background=\\'#fff\\';\"'\n"
            "    +' onblur=\"this.style.borderColor=\\'#c0cfe0\\';this.style.background=\\'#f8f9fb\\';\"'\n"
            "    +'></div>'\n"
            "    +'</div></div>';"
        ),

        # SQR Insight cards: initialize commentary fields after innerHTML is set
        (
            "  document.getElementById('sqr-insights').innerHTML=c;\n}",
            "  document.getElementById('sqr-insights').innerHTML=c;\n"
            "  document.querySelectorAll('#sqr-insights [contenteditable][data-field-id]').forEach(function(el){\n"
            "    if(window._commentaryInitField) window._commentaryInitField(el);\n"
            "  });\n}"
        ),
    ]
    for old, new in subs:
        if old not in html:
            print(f'  WARNING: patch_onesearch_js substitution not found — skipping:\n    {old[:80]!r}', flush=True)
        html = html.replace(old, new)

    # Core Search Territories: replace hardcoded Activia block with dynamic category-based territories
    # Uses OS_COV_TARGET_BRAND / OS_COV_TARGET_GENERIC for the objective targets.
    old_core = (
        "    const _CORE_TERRITORIES = [\n"
        "      {label:'1. Yogurt Generic',    filter: r => r[2]==='YOGURTS' || r[3]==='Yogurts', obj:3},\n"
        "      {label:'2. Improving Health',  filter: r => r[2]==='IMPROVING HEALTH', obj:3},\n"
        "      {label:'3. Brand',             filter: r => (r[3]||'').startsWith('Danone'), obj:10},\n"
        "      {label:'4. Gut Health',        filter: r => r[3]==='Gut health', obj:3},\n"
        "      {label:'5. Probiotics',        filter: r => r[3]==='Probiotics'||r[3]==='Probiotic yogurt'||r[3]==='Danone - Probiotics', obj:3},\n"
        "      {label:'6. Healthier Eating',  filter: r => r[2]==='HEALTHIER EATING', obj:3},\n"
        "    ];"
    )
    new_core = (
        "    // Dynamic core territories from TOPICS values in DATA (r[1])\n"
        "    // OS_TERRITORY_TOPICS = ordered whitelist from per-client config (empty = all auto-sorted)\n"
        "    const _tBrand2=(typeof OS_COV_TARGET_BRAND!=='undefined')?OS_COV_TARGET_BRAND:10;\n"
        "    const _tGeneric2=(typeof OS_COV_TARGET_GENERIC!=='undefined')?OS_COV_TARGET_GENERIC:3;\n"
        "    const _topicSetT = new Set();\n"
        "    DATA.forEach(r => { if(r[1]) _topicSetT.add(r[1]); });\n"
        "    const _ttOrder=(typeof OS_TERRITORY_TOPICS!=='undefined'&&OS_TERRITORY_TOPICS.length)?OS_TERRITORY_TOPICS:[];\n"
        "    const _topicListT = _ttOrder.length\n"
        "      ? _ttOrder.filter(t => _topicSetT.has(t))\n"
        "      : [..._topicSetT].sort((a,b)=>a.localeCompare(b));\n"
        "    const _CORE_TERRITORIES = _topicListT.map(topic => ({\n"
        "      label: topic,\n"
        "      filter: r => r[1]===topic,\n"
        "      obj: (typeof OS_BRAND_REGEX!=='undefined'&&OS_BRAND_REGEX.test(topic.toLowerCase())) ? _tBrand2 : _tGeneric2\n"
        "    }));"
    )
    if old_core in html:
        html = html.replace(old_core, new_core)
    else:
        print('  WARNING: _CORE_TERRITORIES hardcoded block not found — skipping dynamic replacement', flush=True)

    # buildDonut: merge any pre-existing 'Others' entries with the overflow tail so
    # the same label never appears twice (once as a real segment, once as overflow)
    # NOTE: apply_english runs before this function, so 'Autres' is already 'Others'
    old_donut_top = (
        "  function buildDonut(entries, metricKey, metricFmt) {\n"
        "    // Top 5 + regrouper le reste en \"Others\"\n"
        "    const top5 = entries.slice(0, 5);\n"
        "    const rest = entries.slice(5);\n"
        "    const restVal = rest.reduce((s,[,v]) => s + v[metricKey], 0);\n"
        "    const display = restVal > 0 ? [...top5, ['Others', {impr:0,clics:0,ca:0,[metricKey]:restVal}]] : top5;"
    )
    new_donut_top = (
        "  function buildDonut(entries, metricKey, metricFmt) {\n"
        "    // Separate any pre-existing 'Others' so it merges cleanly with the overflow tail\n"
        "    const nonOthers = entries.filter(([n]) => n !== 'Others');\n"
        "    const othersVal = entries.filter(([n]) => n === 'Others').reduce((s,[,v]) => s + v[metricKey], 0);\n"
        "    const top5 = nonOthers.slice(0, 5);\n"
        "    const rest = nonOthers.slice(5);\n"
        "    const restVal = rest.reduce((s,[,v]) => s + v[metricKey], 0) + othersVal;\n"
        "    const display = restVal > 0 ? [...top5, ['Others', {impr:0,clics:0,ca:0,[metricKey]:restVal}]] : top5;"
    )
    if old_donut_top in html:
        html = html.replace(old_donut_top, new_donut_top)
    else:
        print('  WARNING: buildDonut top block not found — skipping Others merge fix', flush=True)

    return html


def build_recos_panel(territory_stats):
    """Generate Oikos-specific header and prioritization section for panel-recos.
    Replaces the hardcoded Activia content. The dynamic sub-category table (recoBody)
    is preserved unchanged — this only replaces the static strategic summary cards."""
    H = _html_escape.escape
    sorted_t = sorted(territory_stats.items(),
                      key=lambda x: x[1]['os_clicks_q1'], reverse=True)

    total_kws = sum(s['count'] for _, s in sorted_t)
    total_os  = sum(s['os_clicks_q1'] for _, s in sorted_t)

    # Classify territories by coverage tier for action priority
    immediate, short_term, maintain = [], [], []
    for topic, s in sorted_t:
        cov = _cov(s['os_clicks_q1'], s['avg_volume'])
        if cov < 0.03:
            immediate.append((topic, s, cov))
        elif cov < 0.10:
            short_term.append((topic, s, cov))
        else:
            maintain.append((topic, s, cov))

    def _reco_card(num, title, tags_html, body, border_color, bg_color, field_id=None, placeholder=None):
        commentary = ''
        if field_id:
            ph = placeholder or f'Add analyst notes for recommendation {num:02d}…'
            commentary = (
                f'<div contenteditable="true" data-field-id="{field_id}" data-placeholder="{_html_escape.escape(ph)}"'
                f' style="min-height:40px;font-size:11px;line-height:1.5;color:#444;'
                f'border:1px dashed #555;border-radius:5px;padding:6px 8px;'
                f'background:#3a3a3a;outline:none;margin-top:6px;"'
                f' onfocus="this.style.borderColor=\'{ACCENT_CLR}\';this.style.background=\'#fff\';"'
                f' onblur="this.style.borderColor=\'#555\';this.style.background=\'#3a3a3a\';"'
                f'>{ph}</div>'
            )
        return (
            f'<div style="display:flex;gap:10px;padding:9px 12px;border-left:3px solid {border_color};'
            f'background:{bg_color};border-radius:0 6px 6px 0;">'
            f'<span style="font-size:12px;font-weight:700;color:{border_color};min-width:22px;flex-shrink:0;">{num:02d}</span>'
            f'<div style="flex:1;">'
            f'<div style="font-size:12px;font-weight:600;color:#222;margin-bottom:4px;">{H(title)}</div>'
            f'<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:4px;">{tags_html}</div>'
            f'<div style="font-size:11px;color:#555;line-height:1.4;">{body}</div>'
            f'{commentary}'
            f'</div></div>'
        )

    def _tag(label, color, bg):
        return (f'<span style="font-size:10px;padding:2px 7px;background:{bg};color:{color};'
                f'border-radius:4px;font-weight:600;border:1px solid {color}33;">{label}</span>')

    seo_tag  = _tag('SEO',     '#1b5e20', '#e8f5e9')
    sem_tag  = _tag('SEM',     '#0d47a1', '#e3f2fd')
    both_tag = _tag('SEO+SEM', '#e65100', '#fff3e0')

    # Build cards — also collect (title, body_plain) tuples for top-15 list
    cards_immediate, cards_short, cards_maintain = [], [], []
    all_reco_items = []   # list of (title_plain, body_plain) for top-15 pull
    n = 1

    for topic, s, cov in immediate:
        cov_pct = cov * 100
        vol_k   = _fmt_num(s['avg_volume'])
        clicks_k = _fmt_num(s['os_clicks_q1'])
        body = (
            f'Coverage at {cov_pct:.1f}% — below 3% target. Territory has {vol_k} monthly searches '
            f'and {clicks_k} OS clicks in {PERIOD_P1}. '
        )
        if s['sem_clicks_q1'] == 0:
            body += f'No SEM presence — consider launching targeted campaigns on top keywords.'
        elif s['seo_clicks_q1'] == 0:
            body += f'No SEO clicks — organic content opportunity to reduce SEM dependency.'
        else:
            body += f'Both channels active but coverage gap remains — optimize bid strategy and expand content.'
        title_plain = f'{topic} — Coverage gap ({cov_pct:.1f}%)'
        all_reco_items.append((title_plain, body))
        slug = _slug(topic)
        cards_immediate.append(_reco_card(
            n, title_plain, both_tag, body, '#c62828', '#fdf5f5',
            field_id=f'detail-rec-{slug}',
            placeholder=f'Add analyst notes for {H(topic)} recommendations…',
        ))
        n += 1

    for topic, s, cov in short_term:
        cov_pct = cov * 100
        vol_k   = _fmt_num(s['avg_volume'])
        body = (
            f'Coverage at {cov_pct:.1f}% — approaching 3–10% range. {vol_k} monthly searches. '
            f'SEO: {_fmt_num(s["seo_clicks_q1"])} clicks · SEM: {_fmt_num(s["sem_clicks_q1"])} clicks in {PERIOD_P1}. '
            f'Build content depth and optimize SEM bids to push coverage toward 10%+ target.'
        )
        title_plain = f'{topic} — Growth opportunity'
        all_reco_items.append((title_plain, body))
        slug = _slug(topic)
        cards_short.append(_reco_card(
            n, title_plain, both_tag, body, '#e65100', '#fff8f0',
            field_id=f'detail-rec-{slug}',
            placeholder=f'Add analyst notes for {H(topic)} recommendations…',
        ))
        n += 1

    for topic, s, cov in maintain:
        cov_pct = cov * 100
        body = (
            f'Coverage at {cov_pct:.0f}% — above target. Maintain SEO+SEM dual presence. '
            f'Monitor competitor activity and protect top positions. '
            f'SEO: {_fmt_num(s["seo_clicks_q1"])} · SEM: {_fmt_num(s["sem_clicks_q1"])} clicks in {PERIOD_P1}.'
        )
        title_plain = f'{topic} — Maintain coverage'
        all_reco_items.append((title_plain, body))
        slug = _slug(topic)
        cards_maintain.append(_reco_card(
            n, title_plain, seo_tag, body, '#2e7d32', '#f1f8f1',
            field_id=f'detail-rec-{slug}',
            placeholder=f'Add analyst notes for {H(topic)} recommendations…',
        ))
        n += 1

    def _section(color, label, cards):
        if not cards:
            return ''
        return f'''
    <div style="margin-bottom:22px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #f0f0f0;">
        <span style="width:10px;height:10px;border-radius:50%;background:{color};flex-shrink:0;display:inline-block;"></span>
        <span style="font-size:11px;font-weight:700;color:{color};text-transform:uppercase;letter-spacing:.5px;">{label}</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;">{''.join(cards)}</div>
    </div>'''

    total_recos = n - 1
    # Summary stat cards (calculated from data)
    summary_cards = (
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;padding:16px 24px;">'
        f'<div style="background:#fff;border-radius:10px;padding:14px;text-align:center;border:1px solid #eee;border-top:3px solid #333;">'
        f'<div style="font-size:10px;color:#888;text-transform:uppercase;margin-bottom:4px;">Territories Analyzed</div>'
        f'<div style="font-size:28px;font-weight:700;color:#333;">{len(sorted_t)}</div>'
        f'<div style="font-size:10px;color:#888;">{total_kws:,} keywords classified</div>'
        f'</div>'
        f'<div style="background:#fff;border-radius:10px;padding:14px;text-align:center;border:1px solid #eee;border-top:3px solid #c62828;">'
        f'<div style="font-size:10px;color:#888;text-transform:uppercase;margin-bottom:4px;">Immediate Actions</div>'
        f'<div style="font-size:28px;font-weight:700;color:#c62828;">{len(immediate)}</div>'
        f'<div style="font-size:10px;color:#c62828;">coverage &lt; 3%</div>'
        f'</div>'
        f'<div style="background:#fff;border-radius:10px;padding:14px;text-align:center;border:1px solid #eee;border-top:3px solid #e65100;">'
        f'<div style="font-size:10px;color:#888;text-transform:uppercase;margin-bottom:4px;">Short-Term Actions</div>'
        f'<div style="font-size:28px;font-weight:700;color:#e65100;">{len(short_term)}</div>'
        f'<div style="font-size:10px;color:#e65100;">coverage 3–10%</div>'
        f'</div>'
        f'<div style="background:#fff;border-radius:10px;padding:14px;text-align:center;border:1px solid #eee;border-top:3px solid #2e7d32;">'
        f'<div style="font-size:10px;color:#888;text-transform:uppercase;margin-bottom:4px;">Maintain</div>'
        f'<div style="font-size:28px;font-weight:700;color:#2e7d32;">{len(maintain)}</div>'
        f'<div style="font-size:10px;color:#2e7d32;">coverage &gt; 10%</div>'
        f'</div>'
        f'</div>'
    )

    # Top-15 pull: first 15 items from all_reco_items (in order: immediate → short → maintain)
    top15 = all_reco_items[:15]
    top15_li = ''.join(
        f'<li style="margin-bottom:5px;line-height:1.45;">'
        f'<strong>{_html_escape.escape(title)}</strong> — {_html_escape.escape(body)}</li>'
        for title, body in top15
    )
    top15_placeholder = 'Add analyst notes or edit prioritization list…'

    priori_section = (
        f'<div class="section-title">One Search Recommendations Prioritization</div>'
        f'<div style="background:#fff;margin:0 24px 16px;padding:20px 24px;border-radius:0 0 8px 8px;box-shadow:0 1px 3px rgba(0,0,0,.1);">'
        f'<p style="font-size:11px;color:#888;margin:0 0 14px;line-height:1.5;">'
        f'OneSearch Action Plan &mdash; {PERIOD_P1} vs {PERIOD_P4} &middot; '
        f'{len(sorted_t)} territories &middot; {total_kws:,} keywords classified &middot; '
        f'Coverage target: &gt;3% non-brand &middot; &gt;10% brand</p>'
        f'<div style="font-size:9px;font-weight:700;color:#888;text-transform:uppercase;'
        f'letter-spacing:.05em;margin-bottom:8px;">Top {len(top15)} Priority Recommendations</div>'
        f'<ul style="list-style:disc;padding-left:18px;margin:0 0 12px;font-size:11px;'
        f'line-height:1.5;color:#444;">{top15_li}</ul>'
        f'<div contenteditable="true" data-field-id="top-recs-prioritization"'
        f' data-placeholder="{_html_escape.escape(top15_placeholder)}"'
        f' style="min-height:54px;font-size:11px;line-height:1.5;color:#444;'
        f'border:1px dashed #555;border-radius:5px;padding:7px 9px;'
        f'background:#3a3a3a;outline:none;margin-bottom:20px;"'
        f' onfocus="this.style.borderColor=\'{ACCENT_CLR}\';this.style.background=\'#fff\';"'
        f' onblur="this.style.borderColor=\'#555\';this.style.background=\'{LIGHT_BG}\';"'
        f'>{top15_placeholder}</div>'
        + _section('#c62828', 'Immediate — High Impact · Coverage Gap', cards_immediate)
        + _section('#e65100', 'Short-Term — Growth Opportunities', cards_short)
        + _section('#2e7d32', 'Maintain — Above Target', cards_maintain)
        + '</div>'
    )

    return summary_cards + '\n' + priori_section + '\n'


def replace_recos_panel(html, territory_stats):
    """Replace static Activia recommendation content in panel-recos with Oikos data-driven content.
    Preserves the header (logo/title), the filter buttons row, and the dynamic sub-category table."""
    # Replace from just after the filter buttons row through to the detailed table section title
    old_start = '<div class="section-title">One Search Recommendations Prioritization</div>'
    old_end   = '<div class="section-title">Detailed SEO / SEM Recommendations by Sub-Category</div>'

    if old_start not in html:
        print('  WARNING: recos static section anchor not found — skipping replacement', flush=True)
        return html

    start_idx = html.index(old_start)
    end_idx   = html.index(old_end)

    # Also replace the stats cards row just before old_start
    # Walk back to find the opening <div> of the stats grid
    stats_anchor = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;padding:16px 24px;">'
    stats_idx = html.rfind(stats_anchor, 0, start_idx)
    if stats_idx != -1:
        start_idx = stats_idx

    new_content = build_recos_panel(territory_stats)
    return html[:start_idx] + new_content + html[end_idx:]


def clean_embedded_docs(html):
    """Strip embedded <!DOCTYPE html>...<body></div> wrappers from concatenated template.

    The reference template was created by concatenating 3 HTML files. Each
    extra file starts with <!DOCTYPE html><html><head>CSS</head><body>\n</div>
    and ends with </body></html>. We keep the <style> CSS (it has QS/SQR
    specific styles) but remove all the structural wrapper tags that confuse
    browser parsing and break tab switching.
    """
    first_pos = html.find('<!DOCTYPE html>')
    if first_pos < 0:
        return html
    prefix = html[:first_pos + len('<!DOCTYPE html>')]
    rest   = html[first_pos + len('<!DOCTYPE html>'):]

    # Remove embedded doc openers, keeping only their <head> content (CSS).
    # Pattern: <!DOCTYPE html> <html ...> <head ...> CONTENT </head> <body ...> </div>
    def _keep_head_content(m):
        return m.group(1).strip() + '\n'

    rest = re.sub(
        r'<!DOCTYPE html>\s*<html[^>]*>\s*<head[^>]*>([\s\S]*?)'
        r'</head>\s*<body[^>]*>',
        _keep_head_content,
        rest,
        flags=re.DOTALL,
    )

    # Remove orphan mid-document </body></html> closers.
    # After truncate_after_last_script there is no valid final </body></html>,
    # so it's safe to remove all of them.
    rest = re.sub(r'</body>\s*</html>', '', rest)

    return prefix + rest


def truncate_after_last_script(html):
    """Remove raw data artifact that sits outside <script> tags at end of file."""
    last_end = html.rfind('</script>')
    if last_end == -1:
        return html
    return html[:last_end + len('</script>')] + '\n'


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f'Building {BRAND_NAME} OneSearch Dashboard…', flush=True)

    print('\n  Loading credentials…', flush=True)
    env = load_env()
    token = get_token(env)
    print('  Token OK', flush=True)

    print(f'\n  Reading Masterlist "{MASTER_TAB}"…', flush=True)
    headers, rows = read_masterlist(token)

    print('\n  Building DATA…', flush=True)
    data_rows = build_data(rows)
    print(f'  {len(data_rows)} keyword rows', flush=True)

    print('\n  Building TAGS…', flush=True)
    tags = build_tags(rows)
    print(f'  {len(tags)} keywords with taxonomy tags', flush=True)

    print('\n  Computing territory stats…', flush=True)
    territory_stats = compute_territory_stats(rows)
    classified = sum(s['count'] for s in territory_stats.values())
    print(f'  {len(territory_stats)} territories · {classified} classified rows', flush=True)

    print('\n  Loading brand-detection regex from reference sheet…', flush=True)
    brand_regex = load_brand_regex(token)

    print('\n  Loading HTML template…', flush=True)
    with open(TEMPLATE, encoding='utf-8') as f:
        html = f.read()
    print(f'  Template: {len(html):,} chars', flush=True)

    print('\n  Injecting DATA…', flush=True)
    data_js = js_data(data_rows)
    html, n = replace_block(html, 'DATA', data_js)
    print(f'    {n} occurrence(s) replaced ({len(data_js):,} chars)', flush=True)

    print('  Injecting TAGS…', flush=True)
    tags_js = js_tags(tags)
    html, n = replace_block(html, 'TAGS', tags_js)
    print(f'    {n} occurrence(s) replaced ({len(tags_js):,} chars)', flush=True)

    print('  Loading Quality Score data from Google Sheets…', flush=True)
    qs_js = load_qs_data(token, rows)
    qs_count = qs_js.count('\n') - 1
    print(f'    {qs_count} QS rows loaded', flush=True)

    print('  Building SQR data from masterlist (keywords with SEM clicks)…', flush=True)
    sqr_js = build_sqr_data(rows)
    sqr_count = sqr_js.count('\n') - 1
    print(f'    {sqr_count} SQR rows built', flush=True)

    html, n1 = replace_block(html, 'QS_CLASSIFIED', qs_js)
    html, n2 = replace_block(html, 'SQR_ACTIVIA',   sqr_js, decl='var')
    html, n3 = replace_block(html, 'SQR_DATA',       'var SQR_DATA = [];',    decl='var')
    print(f'    QS_CLASSIFIED: {n1}×  SQR_ACTIVIA: {n2}×  SQR_DATA: {n3}×', flush=True)

    print('  Applying brand colours and labels…', flush=True)
    html = apply_brand(html)

    print('  Applying English labels and fixing JS elements…', flush=True)
    html = apply_english(html)

    print('\n  Building Territory Deep Dive panel…', flush=True)
    territory_html = build_territory_panel(territory_stats)
    html = replace_territory_panel(html, territory_html)
    print(f'  Territory panel: {len(territory_html):,} chars', flush=True)

    print('  Building Recommendations panel (replacing Activia content)…', flush=True)
    html = replace_recos_panel(html, territory_stats)

    print('  Patching OneSearch Dashboard JS (brand filter, territories, Other/Others)…', flush=True)
    html = patch_onesearch_js(html)

    print('  Stripping embedded document wrappers…', flush=True)
    before_clean = len(html)
    html = clean_embedded_docs(html)
    print(f'    Removed {before_clean - len(html):,} chars of embedded-doc boilerplate', flush=True)

    print('  Truncating raw data artifact outside script tags…', flush=True)
    before = len(html)
    html = truncate_after_last_script(html)
    print(f'    Removed {before - len(html):,} chars of post-script content', flush=True)

    print('  Injecting brand config (regex, topic order, coverage targets)…', flush=True)
    html = inject_brand_config(html, brand_regex)

    print('  Injecting commentary export UI…', flush=True)
    html = inject_export_ui(html)

    print('  Injecting reco filter config + filter tabs…', flush=True)
    html = inject_reco_filter(html)

    # Taxonomy glossary — inject into the glossary tab
    taxonomy_html = build_taxonomy_glossary_html(rows)
    if '<!-- TAXONOMY_GLOSSARY -->' in html:
        html = html.replace('<!-- TAXONOMY_GLOSSARY -->', taxonomy_html, 1)
    else:
        print('  WARNING: <!-- TAXONOMY_GLOSSARY --> placeholder not found — skipping taxonomy section')

    print(f'\n  Writing → {OUTPUT_FILE}', flush=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f'\nDone.', flush=True)
    print(f'  Output : {OUTPUT_FILE}', flush=True)
    print(f'  Size   : {size_kb:.0f} KB', flush=True)
    print(f'  Open   : open "{OUTPUT_FILE}"', flush=True)


if __name__ == '__main__':
    main()
