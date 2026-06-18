"""Rewrite Synergy Presentation Notes Google Doc with proper headings, bold, bullets."""
import os, warnings
warnings.filterwarnings('ignore')
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

env = {}
with open('/Users/carlaklaasen/claude_code/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            env[k.strip()] = v.strip()

creds = Credentials.from_authorized_user_file(env['GOOGLE_TOKEN_FILE'])
if not creds.valid and creds.expired and creds.refresh_token:
    creds.refresh(Request())
service = build('docs', 'v1', credentials=creds)
DOC_ID = '1hIWUG06ZDp0N0favHd7fzHwhelpHcm7FRTZPnYDTZoE'

# ── Structured content ────────────────────────────────────────────────
# (text, named_style, [substrings to bold])
# Use HEADING_1 / HEADING_2 / HEADING_3 / NORMAL_TEXT
SECTIONS = [
    # Title
    ("OneSearch Presentation Cheat Sheet — Oikos USA Q1 2026", "HEADING_1", []),
    ("Analyst-only  |  Quick-reference during presentation", "NORMAL_TEXT", []),

    # ── METHODOLOGY ──
    ("METHODOLOGY", "HEADING_2", []),

    ("What is OneSearch", "HEADING_3", []),
    ("Goal: unified keyword performance view — one row per keyword, all channels", "NORMAL_TEXT", ["Goal:"]),
    ("Answers: for a given keyword, how are we doing organically AND in paid?", "NORMAL_TEXT", ["Answers:"]),
    ("Output: ~60-column masterlist in Google Sheets exported to HTML dashboard", "NORMAL_TEXT", ["Output:"]),
    ("Territories: Brand, Competitor, Generic, Recipe, Source of Protein, Consumer Habits", "NORMAL_TEXT", ["Territories:"]),
    ("Comparison period: Q1 2026 vs Q4 2025 throughout", "NORMAL_TEXT", ["Comparison period:"]),

    ("Data Sources", "HEADING_3", []),
    ("Google Search Console (GSC) — organic clicks + impressions by search query", "NORMAL_TEXT", ["Google Search Console (GSC)"]),
    ("Google Ads / GA4 Ads export — paid clicks, cost, sessions, landing page by query", "NORMAL_TEXT", ["Google Ads / GA4 Ads export"]),
    ("Google Analytics (GA4) — qualified visit rates per landing page", "NORMAL_TEXT", ["Google Analytics (GA4)"]),
    ("SE Ranking — tracked keyword positions (monthly snapshot)", "NORMAL_TEXT", ["SE Ranking"]),
    ("Internal keyword study — seed list of ~3,700 keywords with volume, topics, tags", "NORMAL_TEXT", ["Internal keyword study"]),
    ("All sources use different query formats — unified via fuzzy matching (trigram index)", "NORMAL_TEXT", ["fuzzy matching (trigram index)"]),

    ("Keyword Spine & Fuzzy Matching", "HEADING_3", []),
    ("Problem: GSC has user-typed queries, Ads has matched keywords, SE Ranking has tracked terms — all slightly different spellings", "NORMAL_TEXT", ["Problem:"]),
    ("Solution: trigram index breaks each keyword into 3-char n-grams and scores similarity", "NORMAL_TEXT", ["Solution:"]),
    ("Match threshold: ~0.65 similarity — misspellings like oikios still map correctly", "NORMAL_TEXT", ["Match threshold:"]),
    ("Unmatched queries flagged as spine expansion candidates (~70 in Q1 2026)", "NORMAL_TEXT", []),

    ("Coverage Calculation", "HEADING_3", []),
    ("Coverage = (SEO clicks + SEM clicks) / Monthly Volume", "NORMAL_TEXT", ["Coverage ="]),
    ("Target: Brand >= 10%  |  Non-brand >= 3%  |  Competitor >= 2%", "NORMAL_TEXT", ["Target:"]),
    ("Example: 1,000 monthly searches + 100 SEO + 50 SEM clicks = 15% coverage", "NORMAL_TEXT", ["Example:"]),

    ("Qualified Visit (QV) Methodology — Thomas Joachim LP-rate method", "HEADING_3", []),
    ("Step 1: GA4 Ads export gives sessions per (search query, landing page)", "NORMAL_TEXT", ["Step 1:"]),
    ("Step 2: LP rate = engaged sessions / total sessions — calculated per landing page", "NORMAL_TEXT", ["Step 2:", "LP rate ="]),
    ("Step 3: QV SEM = sessions on keyword x LP rate for that keyword's landing page", "NORMAL_TEXT", ["Step 3:", "QV SEM ="]),
    ("Qualified session (GA4): >= 10 sec on site, or 2+ page views, or conversion event", "NORMAL_TEXT", ["Qualified session (GA4):"]),
    ("LP rate is the key lever — same keyword on a better landing page = more QVs", "NORMAL_TEXT", ["LP rate is the key lever"]),
    ("Q1 2026 total QV SEM (Brand territory): 1,338 across 86 brand keywords", "NORMAL_TEXT", ["1,338"]),
    ("\"oikos\" (36.8K vol): QV SEM = 0.046 — very low, signals landing page mismatch", "NORMAL_TEXT", ["QV SEM = 0.046"]),

    ("Brand SEM Negative Keyword Logic", "HEADING_3", []),
    ("Rule: a paid keyword is waste if organic already captures the user AND paid adds zero QVs", "NORMAL_TEXT", ["Rule:"]),
    ("EXCLUDE — add as negative keyword (17 keywords):", "NORMAL_TEXT", ["EXCLUDE"]),
    ("    Condition 1: SEO Coverage > 10%", "NORMAL_TEXT", ["Condition 1:"]),
    ("    Condition 2: SEO Position <= 5", "NORMAL_TEXT", ["Condition 2:"]),
    ("    Condition 3: QV SEM = 0   (all three must be true)", "NORMAL_TEXT", ["Condition 3:"]),
    ("KEEP-ACTIVE — maintain or increase bids (59 keywords):", "NORMAL_TEXT", ["KEEP-ACTIVE"]),
    ("    QV SEM > 0 AND SEO coverage < 10% — paid is doing real work, organic not covering", "NORMAL_TEXT", []),
    ("KEEP-TEST — monitor 4 weeks before pausing (8 keywords):", "NORMAL_TEXT", ["KEEP-TEST"]),
    ("    SEO cov > 10% AND QV SEM > 0 — organic present but paid still adding QVs", "NORMAL_TEXT", []),
    ("    Pause rule: organic holds top-5 AND QV SEM = 0 for 2 consecutive months", "NORMAL_TEXT", ["Pause rule:"]),
    ("Budget reallocation: freed budget from negatives goes to Keep-Active high-QV terms", "NORMAL_TEXT", ["Budget reallocation:"]),
    ("Impression Share target: 80% IS on oikos, oikos triple zero, oikos pro, oikos yogurt", "NORMAL_TEXT", ["Impression Share target:"]),

    # ── TAB 1 ──
    ("TAB 1 — INTRODUCTION & GLOSSARY", "HEADING_2", []),

    ("Territory KPI Summary Table", "HEADING_3", []),
    ("One row per territory: SEO clicks / SEM clicks / Total OS clicks / Coverage Q1 vs Q4 / QV SEO / QV SEM", "NORMAL_TEXT", []),
    ("Coverage % = (SEO + SEM clicks) / Monthly Volume — share of total demand captured", "NORMAL_TEXT", ["Coverage %"]),
    ("If asked why Brand coverage is higher: strong organic positions (top-5) drive most clicks organically", "NORMAL_TEXT", ["If asked"]),
    ("If asked why Source of Protein is 0% SEO: no pages rank — 100% of those clicks came from SEM", "NORMAL_TEXT", ["If asked"]),

    ("Glossary / Methodology Panel", "HEADING_3", []),
    ("Defines all metrics: QV, Coverage, LP rate, SEM QV, etc.", "NORMAL_TEXT", []),
    ("Point here when explaining QV or coverage formulas during the presentation", "NORMAL_TEXT", []),

    ("Brand SEM Campaign Optimization Table", "HEADING_3", []),
    ("Summary row: Exclude 17 / Keep-Active 59 / Keep-Test 8", "NORMAL_TEXT", ["Exclude 17", "Keep-Active 59", "Keep-Test 8"]),
    ("Click each group to expand — shows per-keyword: Monthly Vol / SEO Position / Coverage / QV SEM / QV SEO", "NORMAL_TEXT", []),
    ("All three exclusion criteria are shown per keyword in the expanded rows", "NORMAL_TEXT", []),
    ("80% IS target card: increase bids on oikos, oikos triple zero, oikos pro, oikos yogurt after negatives applied", "NORMAL_TEXT", ["80% IS target card:"]),

    # ── TAB 2 ──
    ("TAB 2 — ONESEARCH DASHBOARD", "HEADING_2", []),

    ("Territory Coverage Bars (top section)", "HEADING_3", []),
    ("Visual progress bars: filled segment = current coverage vs target for each territory", "NORMAL_TEXT", []),
    ("Short or red bar = below target — drives the recommendations in Tab 4", "NORMAL_TEXT", ["Short or red bar"]),
    ("Brand will be highest; Competitor, Generic, Source of Protein will be lowest", "NORMAL_TEXT", []),

    ("KPI Cards — Q1 vs Q4 Deltas", "HEADING_3", []),
    ("Shows: total OneSearch clicks, QV SEM, QV SEO, spend, coverage — all territories combined", "NORMAL_TEXT", []),
    ("Up/down arrows = Q1 vs Q4 change — positive is better for clicks/QV, context-dependent for spend", "NORMAL_TEXT", []),

    ("Territory Detail Cards", "HEADING_3", []),
    ("One card per territory — click to drill into Territory Deep Dive", "NORMAL_TEXT", []),
    ("Each card: monthly volume / OS coverage / QV SEM / leading sub-categories", "NORMAL_TEXT", []),

    # ── TAB 3 ──
    ("TAB 3 — TERRITORY DEEP DIVE", "HEADING_2", []),

    ("Territory Selector", "HEADING_3", []),
    ("Click any territory card or use the filter to drill into that territory", "NORMAL_TEXT", []),

    ("Sub-Category Breakdown Table", "HEADING_3", []),
    ("One row per sub-category within the selected territory", "NORMAL_TEXT", []),
    ("Columns: Demand (monthly vol) / SEO clicks / SEM clicks / Coverage / QV SEM / Top keywords", "NORMAL_TEXT", ["Demand", "Coverage", "QV SEM"]),
    ("Sort by Demand to find highest-volume uncovered sub-categories", "NORMAL_TEXT", []),
    ("Sort by QV SEM descending to find which sub-categories drove the most qualified paid traffic", "NORMAL_TEXT", []),

    ("Keyword Spine Table (full list)", "HEADING_3", []),
    ("~3,700 rows — use search or topic/category filters to find specific keywords", "NORMAL_TEXT", []),
    ("Every keyword: vol / position / coverage Q1 vs Q4 / SEO clicks / SEM clicks / QV SEO / QV SEM / CPC / spend", "NORMAL_TEXT", []),
    ("If asked about a specific keyword: search here for full Q1 vs Q4 performance in one row", "NORMAL_TEXT", ["If asked"]),

    # ── TAB 4 ──
    ("TAB 4 — ONE SEARCH RECOMMENDATIONS", "HEADING_2", []),

    ("12 Action Cards (01-12)", "HEADING_3", []),
    ("Red 01-02: SEO Q2 critical — product and category pages (highest priority)", "NORMAL_TEXT", ["Red 01-02:"]),
    ("Orange 03-05: SEO Q2-Q3 — source of protein, recipe, consumer habits", "NORMAL_TEXT", ["Orange 03-05:"]),
    ("Blue 06-10: SEM Q2 — brand negatives, IS uplift, Keep-Test monitoring, incremental measurement, competitor", "NORMAL_TEXT", ["Blue 06-10:"]),
    ("Purple 11-12: QS improvement + QV tracking cadence", "NORMAL_TEXT", ["Purple 11-12:"]),
    ("Each card: channel tag (SEO / SEM) / category / quarter / bullet action list", "NORMAL_TEXT", []),
    ("If asked why something is Q3: sequencing — product pages must be live before informational content", "NORMAL_TEXT", ["If asked"]),

    ("Detailed Sub-Category Recommendations Table", "HEADING_3", []),
    ("Every sub-category with recommended channel + action", "NORMAL_TEXT", []),
    ("Columns: Category / Sub-category / SEO Position bucket / Channel / Demand / Clicks OS / QV OneSearch / Coverage / Recommendation", "NORMAL_TEXT", []),
    ("SEO Position color coding: green = 1-3  |  orange = 4-10  |  red = > 10  |  grey = not ranking", "NORMAL_TEXT", ["green = 1-3", "orange = 4-10", "red = > 10", "grey = not ranking"]),
    ("Filters: Active (Q2) / Long-term (Q3-Q4) / All  |  SEO / SEM / Both  |  Category dropdown", "NORMAL_TEXT", ["Filters:"]),
    ("If asked why a sub-category has 0 SEO clicks: no ranking position — SEM is the only channel covering it", "NORMAL_TEXT", ["If asked"]),

    # ── TAB 5 ──
    ("TAB 5 — QUALITY SCORE", "HEADING_2", []),

    ("KPI Cards (top row)", "HEADING_3", []),
    ("Keywords / Avg QS / Impressions / Clicks / CTR / Cost — from Google Ads QS report (161 brand keywords)", "NORMAL_TEXT", []),
    ("Note: Impressions and Clicks are 0 for most rows — QS report captures QS only; full performance data pending from SQR export with LP column", "NORMAL_TEXT", ["Note:"]),

    ("QS Distribution Chart (bar chart 1-10)", "HEADING_3", []),
    ("How many keywords sit at each QS level (1 = worst, 10 = best)", "NORMAL_TEXT", []),
    ("Goal: most keywords >= 7; keywords <= 5 need ad copy + LP fix", "NORMAL_TEXT", ["Goal:"]),
    ("7 keywords identified below QS 5 in Q1 — covered by Recommendation 11", "NORMAL_TEXT", ["7 keywords"]),

    ("LP Experience Chart (horizontal bars)", "HEADING_3", []),
    ("Google's LP quality rating: Above Average / Average / Below Average / Not Available", "NORMAL_TEXT", []),
    ("Not Available = keyword has too few impressions for Google to rate the LP yet", "NORMAL_TEXT", ["Not Available"]),
    ("Below Average = Google sees a mismatch between ad copy and landing page content", "NORMAL_TEXT", ["Below Average"]),

    ("By Keyword Table", "HEADING_3", []),
    ("Columns: Keyword / Match / Campaign / QS (1-10) / LP Exp / Expected CTR / Ad Relevance / Impr / Clicks / Cost / CPC", "NORMAL_TEXT", []),
    ("Sort by QS column to find worst performers quickly", "NORMAL_TEXT", []),
    ("LP Exp / Expected CTR / Ad Relevance: Google's three QS sub-components — each rated Above/Average/Below", "NORMAL_TEXT", ["LP Exp", "Expected CTR", "Ad Relevance"]),

    ("By Landing Page Table", "HEADING_3", []),
    ("Keywords grouped by their landing page URL", "NORMAL_TEXT", []),
    ("Columns: URL / KW count / Avg QS / LP Above/Avg/Below counts / Impr / Clicks / Cost", "NORMAL_TEXT", []),
    ("URL sourced from SE Ranking export (organic position by page), not directly from Google Ads", "NORMAL_TEXT", []),
    ("If Impr/Clicks show 0: performance data pending — SQR export with LP column not yet available (amber callout visible at bottom of tab)", "NORMAL_TEXT", ["If Impr/Clicks show 0:"]),
    ("Use this view to spot LPs with many Below Average LP ratings — prioritize those pages for optimization", "NORMAL_TEXT", []),

    # ── TAB 6 ──
    ("TAB 6 — SQR (Search Query Report)", "HEADING_2", []),

    ("Source & Context", "HEADING_3", []),
    ("Source: GA4 Google Ads export — actual user-typed queries that triggered an ad and produced a session", "NORMAL_TEXT", ["Source:"]),
    ("Different from Google Ads search terms report — these have QV attribution via LP rate", "NORMAL_TEXT", []),

    ("Wasted Spend Section", "HEADING_3", []),
    ("Queries with SEM spend but QV SEM = 0 (clicks that produced zero qualified visits)", "NORMAL_TEXT", []),
    ("Logic: paid for the click, user did not engage — pure waste", "NORMAL_TEXT", ["Logic:"]),
    ("If asked for exact wasted dollar amount: current data is session-level; precise attribution requires per-keyword conversion export", "NORMAL_TEXT", ["If asked"]),
    ("Action: high-waste queries go to negative keyword list (feeds into the 17 Exclude keywords)", "NORMAL_TEXT", ["Action:"]),

    ("Regression Queries Section", "HEADING_3", []),
    ("Queries where QV SEM dropped significantly from Q4 2025 to Q1 2026", "NORMAL_TEXT", []),
    ("Possible causes: LP change, ad copy change, bid reduction, increased competitor IS", "NORMAL_TEXT", ["Possible causes:"]),
    ("Use to prioritize bid recovery or LP investigation for next month", "NORMAL_TEXT", []),

    ("Rising Queries Section", "HEADING_3", []),
    ("Queries with strong QV growth from Q4 2025 to Q1 2026", "NORMAL_TEXT", []),
    ("Action: increase bids / ensure coverage — these are the next Keep-Active candidates", "NORMAL_TEXT", ["Action:"]),
    ("Also use to identify emerging keyword clusters not yet in the spine", "NORMAL_TEXT", []),

    # ── TIMING ──
    ("PRESENTATION TIMING (1 hour)", "HEADING_2", []),
    ("Introduction & Glossary — What is OneSearch, methodology, QV, coverage: 10 min", "NORMAL_TEXT", ["Introduction & Glossary"]),
    ("OneSearch Dashboard — territory KPIs, coverage overview: 8 min", "NORMAL_TEXT", ["OneSearch Dashboard"]),
    ("Territory Deep Dive — per-territory breakdown, key findings: 12 min", "NORMAL_TEXT", ["Territory Deep Dive"]),
    ("One Search Recommendations — walk through 12 actions, Brand SEM table: 15 min", "NORMAL_TEXT", ["One Search Recommendations"]),
    ("Quality Score — QS distribution, LP experience, by-LP view: 8 min", "NORMAL_TEXT", ["Quality Score"]),
    ("SQR — wasted spend, regression, rising queries: 5 min", "NORMAL_TEXT", ["SQR"]),
    ("Q&A + scalability pitch (reuse for other Danone brands): 5 min", "NORMAL_TEXT", ["Q&A"]),
    ("Tip: QV methodology + negative keyword logic will get the most questions — budget extra time here", "NORMAL_TEXT", ["Tip:"]),
]

# ── Build text blob and track positions ──────────────────────────────
full_text = ""
para_info = []  # (start, end, style, bolds, raw_text)

for (text, style, bolds) in SECTIONS:
    start = len(full_text) + 1  # doc offset starts at 1
    full_text += text + "\n"
    end = len(full_text) + 1
    para_info.append((start, end - 1, style, bolds, text))

# ── Google Docs API batchUpdate ──────────────────────────────────────
doc = service.documents().get(documentId=DOC_ID).execute()
end_index = doc['body']['content'][-1]['endIndex']

requests = []

# 1. Delete all existing content
if end_index > 2:
    requests.append({
        'deleteContentRange': {
            'range': {'startIndex': 1, 'endIndex': end_index - 1}
        }
    })

# 2. Insert full text blob
requests.append({
    'insertText': {
        'location': {'index': 1},
        'text': full_text
    }
})

# 3. Apply paragraph styles (end to start — indices stable since no content change)
for (start, end, style, bolds, text) in reversed(para_info):
    requests.append({
        'updateParagraphStyle': {
            'range': {'startIndex': start, 'endIndex': end},
            'paragraphStyle': {'namedStyleType': style},
            'fields': 'namedStyleType'
        }
    })

# 4. Apply bold to specified substrings (end to start)
for (start, end, style, bolds, text) in reversed(para_info):
    for bold_str in reversed(bolds):
        idx = text.find(bold_str)
        if idx >= 0:
            bs = start + idx
            be = bs + len(bold_str)
            requests.append({
                'updateTextStyle': {
                    'range': {'startIndex': bs, 'endIndex': be},
                    'textStyle': {'bold': True},
                    'fields': 'bold'
                }
            })

result = service.documents().batchUpdate(
    documentId=DOC_ID,
    body={'requests': requests}
).execute()
print(f"Done. {len(requests)} requests applied.")
print(f"Total paragraphs written: {len(SECTIONS)}")
