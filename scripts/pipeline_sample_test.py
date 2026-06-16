#!/usr/bin/env python3
"""
20-row pipeline simulation.
Runs the same logic as the n8n Code nodes on real data samples.
Prints expected output and actual result at each step.
"""

import csv
import json
import re
import subprocess
from collections import defaultdict

# ── Paths ────────────────────────────────────────────────────────────────────
BASE = "/Users/carlaklaasen/claude_code/one_search/"
GSC_FILE  = BASE + "gsc_export_queries_oikos.csv"
SQR_FILE  = BASE + "account_level_sqr_report_oikos.csv"
SE_FILE   = BASE + "se_ranking_april_oikos.csv"
GOOGLE_REFRESH = "1//015Xj7niGA8Q4CgYIARAAGAESNwF-L9IrpDFUUZa5zCaTR_Y2xlvBWmMNBbPQBVGzoblny7NDVwk0vcmywH9ek6dU62ORnwd1tsY"
GOOGLE_CLIENT_ID = "192073959907-dicmk9ruboeg6hjq26lkjcuvjo3tqgcm.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"
KS_SHEET_ID = "1rTdi4cLDiFUdQHH8hj4V1GIQb8iKToKXRgFHlQcVHEI"

SAMPLE = 20

# ── Helpers ──────────────────────────────────────────────────────────────────
def normalize(s):
    s = str(s or "").lower()
    s = re.sub(r"[   ​]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()

def clean_num(v):
    s = str(v or "0")
    s = re.sub(r"[   \s]", "", s)  # remove thousands separators
    s = s.replace(",", ".")                        # European decimal comma → period
    s = re.sub(r"[^0-9.]", "", s)
    try:
        return float(s)
    except ValueError:
        return 0.0

def parse_pct(v):
    return float(str(v or "0").replace("%", "")) / 100

def get_token():
    result = subprocess.run([
        "curl", "-s", "-X", "POST", "https://oauth2.googleapis.com/token",
        "-d", f"client_id={GOOGLE_CLIENT_ID}",
        "-d", f"client_secret={GOOGLE_CLIENT_SECRET}",
        "-d", f"refresh_token={GOOGLE_REFRESH}",
        "-d", "grant_type=refresh_token",
    ], capture_output=True, text=True)
    return json.loads(result.stdout)["access_token"]

def fetch_sheet_rows(token, sheet_id, tab, range_):
    from urllib.parse import quote
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{quote(tab)}!{range_}"
    result = subprocess.run(
        ["curl", "-s", url, "-H", f"Authorization: Bearer {token}"],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)
    rows = data.get("values", [])
    if not rows:
        return []
    headers = rows[0]
    return [dict(zip(headers, r + [""] * (len(headers) - len(r)))) for r in rows[1:]]

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print("="*70)

def subsection(title):
    print(f"\n  {'─'*60}")
    print(f"  {title}")
    print(f"  {'─'*60}")

# ── Step 0: Load sources ──────────────────────────────────────────────────────
section("STEP 0 — Load 20-row samples from each source")

# GSC
gsc_raw = []
with open(GSC_FILE, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= SAMPLE:
            break
        gsc_raw.append(row)
print(f"\n  GSC: {len(gsc_raw)} rows, cols: {list(gsc_raw[0].keys())}")

# SQR (skip row 0 = date range; row 1 = actual headers)
sqr_raw = []
with open(SQR_FILE, newline="", encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    next(reader)  # skip date range header
    headers = next(reader)  # actual column headers
    for i, row in enumerate(reader):
        if i >= SAMPLE:
            break
        sqr_raw.append(dict(zip(headers, row)))
print(f"  SQR: {len(sqr_raw)} rows, cols: {list(sqr_raw[0].keys())[:10]} ...")

# SE Ranking
se_raw = []
with open(SE_FILE, newline="", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= SAMPLE:
            break
        se_raw.append(row)
print(f"  SE:  {len(se_raw)} rows, cols: {list(se_raw[0].keys())}")

# Keyword Study (first 20 rows via API)
print("\n  Fetching 20 KS rows via Sheets API...")
token = get_token()
ks_raw = fetch_sheet_rows(token, KS_SHEET_ID, "Keyword study US", "A1:BZ21")
print(f"  KS:  {len(ks_raw)} rows, cols (first 6): {list(ks_raw[0].keys())[:6]}")

# ── Step 2a: Normalize & Filter ───────────────────────────────────────────────
section("STEP 2a — Normalize & Filter")

# KS
ks = [
    {
        "keyword": r.get("Keyword", "").strip(),
        "norm_keyword": normalize(r.get("Keyword", "")),
        "topic": r.get("TOPIC", ""),
        "category": r.get("CATEGORY", ""),
        "sub_category": r.get("SUB-CATEGORY", ""),
        "Searches: Oct 2025": r.get("Searches: Oct 2025", ""),
    }
    for r in ks_raw if r.get("Keyword", "").strip()
]

# GSC: filter clicks > 1 in either period
gsc_filtered = []
gsc_dropped = []
for r in gsc_raw:
    p1 = clean_num(r.get("1/1/26 - 3/31/26 Clicks", 0))
    p2 = clean_num(r.get("10/1/25 - 12/31/25 Clicks", 0))
    entry = {
        "query": r["Top queries"],
        "norm_query": normalize(r["Top queries"]),
        "gsc_clicks_p1": p1,
        "gsc_clicks_p2": p2,
        "gsc_impr_p1": clean_num(r.get("1/1/26 - 3/31/26 Impressions")),
        "gsc_impr_p2": clean_num(r.get("10/1/25 - 12/31/25 Impressions")),
        "gsc_ctr_p1":  parse_pct(r.get("1/1/26 - 3/31/26 CTR")),
        "gsc_ctr_p2":  parse_pct(r.get("10/1/25 - 12/31/25 CTR")),
        "gsc_pos_p1":  clean_num(r.get("1/1/26 - 3/31/26 Position")),
        "gsc_pos_p2":  clean_num(r.get("10/1/25 - 12/31/25 Position")),
    }
    if p1 > 1 or p2 > 1:
        gsc_filtered.append(entry)
    else:
        gsc_dropped.append(r["Top queries"])

# SQR: filter clicks > 1
sqr_filtered = []
sqr_dropped = []
for r in sqr_raw:
    clicks = clean_num(r.get("Clicks", 0))
    entry = {
        "search_term": r.get("Search term", ""),
        "norm_term": normalize(r.get("Search term", "")),
        "search_keyword": r.get("Search keyword", ""),
        "sqr_clicks_p1": clicks,
        "sqr_clicks_p2": clean_num(r.get("Clicks (Compare to)")),
        "sqr_cost_p1":   clean_num(r.get("Cost")),
        "sqr_cost_p2":   clean_num(r.get("Cost (Compare to)")),
        "sqr_impr_p1":   clean_num(r.get("Impr.")),
        "sqr_impr_p2":   clean_num(r.get("Impr. (Compare to)")),
    }
    if clicks > 1:
        sqr_filtered.append(entry)
    else:
        sqr_dropped.append(r.get("Search term", ""))

# SE
se = []
for r in se_raw:
    kw = r.get("Keyword", "").strip()
    se.append({
        "se_keyword": kw,
        "norm_se_keyword": normalize(kw),
        "se_position":   clean_num(r.get("Position")),
        "se_search_vol": clean_num(r.get("Search vol.")),
        "se_cpc": clean_num(r.get("CPC")),
    })

print(f"\n  KS:  {len(ks)} keywords loaded (sample)")
print(f"\n  GSC: {len(gsc_filtered)} kept (clicks>1 in either period), {len(gsc_dropped)} dropped")
if gsc_dropped:
    print(f"    Dropped: {gsc_dropped}")
print(f"\n  SQR: {len(sqr_filtered)} kept (clicks>1), {len(sqr_dropped)} dropped")
if sqr_dropped:
    print(f"    Dropped: {sqr_dropped[:5]}")
print(f"\n  SE:  {len(se)} rows")

subsection("Sample GSC rows (first 3 after filter)")
for r in gsc_filtered[:3]:
    print(f"    [{r['norm_query']}] clicks P1={r['gsc_clicks_p1']:.0f} P2={r['gsc_clicks_p2']:.0f} | impr P1={r['gsc_impr_p1']:.0f} P2={r['gsc_impr_p2']:.0f}")

subsection("Sample SQR rows (first 3 after filter)")
for r in sqr_filtered[:3]:
    print(f"    [{r['norm_term']}] clicks P1={r['sqr_clicks_p1']:.0f} P2={r['sqr_clicks_p2']:.0f} | cost P1=${r['sqr_cost_p1']:.2f}")

# ── Step 2b: Dedup + Join ─────────────────────────────────────────────────────
section("STEP 2b — Dedup within sources, then full-outer-join GSC + SQR")

# Dedup GSC
gsc_map = {}
for row in gsc_filtered:
    key = row["norm_query"]
    if key not in gsc_map:
        gsc_map[key] = dict(row)
    else:
        m = gsc_map[key]
        prev_i1, prev_i2 = m["gsc_impr_p1"], m["gsc_impr_p2"]
        m["gsc_clicks_p1"] += row["gsc_clicks_p1"]
        m["gsc_clicks_p2"] += row["gsc_clicks_p2"]
        m["gsc_impr_p1"]   += row["gsc_impr_p1"]
        m["gsc_impr_p2"]   += row["gsc_impr_p2"]
        if m["gsc_impr_p1"] > 0:
            m["gsc_pos_p1"] = (m["gsc_pos_p1"] * prev_i1 + row["gsc_pos_p1"] * row["gsc_impr_p1"]) / m["gsc_impr_p1"]
        if m["gsc_impr_p2"] > 0:
            m["gsc_pos_p2"] = (m["gsc_pos_p2"] * prev_i2 + row["gsc_pos_p2"] * row["gsc_impr_p2"]) / m["gsc_impr_p2"]
for k in gsc_map:
    m = gsc_map[k]
    m["gsc_ctr_p1"] = m["gsc_clicks_p1"] / m["gsc_impr_p1"] if m["gsc_impr_p1"] > 0 else 0
    m["gsc_ctr_p2"] = m["gsc_clicks_p2"] / m["gsc_impr_p2"] if m["gsc_impr_p2"] > 0 else 0

# Dedup SQR
sqr_map = {}
for row in sqr_filtered:
    key = row["norm_term"]
    if key not in sqr_map:
        sqr_map[key] = dict(row)
        sqr_map[key]["_kws"] = {row["search_keyword"]}
    else:
        m = sqr_map[key]
        m["sqr_clicks_p1"] += row["sqr_clicks_p1"]
        m["sqr_clicks_p2"] += row["sqr_clicks_p2"]
        m["sqr_cost_p1"]   += row["sqr_cost_p1"]
        m["sqr_cost_p2"]   += row["sqr_cost_p2"]
        m["sqr_impr_p1"]   += row["sqr_impr_p1"]
        m["sqr_impr_p2"]   += row["sqr_impr_p2"]
        m["_kws"].add(row["search_keyword"])
for k in sqr_map:
    sqr_map[k]["search_keyword"] = " | ".join(sqr_map[k]["_kws"])
    del sqr_map[k]["_kws"]

print(f"\n  GSC unique after dedup: {len(gsc_map)} (from {len(gsc_filtered)})")
print(f"  SQR unique after dedup: {len(sqr_map)} (from {len(sqr_filtered)})")

# Full outer join
ZERO_SQR = {"sqr_clicks_p1":0, "sqr_clicks_p2":0, "sqr_cost_p1":0, "sqr_cost_p2":0, "sqr_impr_p1":0, "sqr_impr_p2":0, "search_keyword":""}
ZERO_GSC = {"gsc_clicks_p1":0, "gsc_clicks_p2":0, "gsc_impr_p1":0, "gsc_impr_p2":0, "gsc_ctr_p1":0, "gsc_ctr_p2":0, "gsc_pos_p1":0, "gsc_pos_p2":0, "query":""}

sqr_remaining = dict(sqr_map)
unified = {}
for key, gsc_row in gsc_map.items():
    unified[key] = {"unified_key": key, **ZERO_SQR, **gsc_row}
    if key in sqr_remaining:
        unified[key].update(sqr_remaining.pop(key))
for key, sqr_row in sqr_remaining.items():
    unified[key] = {"unified_key": key, "norm_query": key, **ZERO_GSC, **sqr_row}

unified_list = list(unified.values())

gsc_only = [k for k, v in unified.items() if v["sqr_clicks_p1"] == 0 and v["gsc_clicks_p1"] > 0]
sqr_only = [k for k, v in unified.items() if v["gsc_clicks_p1"] == 0 and v["sqr_clicks_p1"] > 0]
both     = [k for k, v in unified.items() if v["gsc_clicks_p1"] > 0 and v["sqr_clicks_p1"] > 0]

print(f"\n  Unified list: {len(unified_list)} keywords")
print(f"    GSC-only: {len(gsc_only)}, SQR-only: {len(sqr_only)}, Both: {len(both)}")
if both:
    print(f"    Keywords in both: {both[:5]}")

# ── Step 2c+2d: Trigram Match ────────────────────────────────────────────────
section("STEP 2c+2d — Build trigram index, match unified + SE → Keyword Study")

def trigrams(s):
    s = " " + s + " "
    return set(s[i:i+3] for i in range(len(s)-2))

def jaccard(a, b):
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter) if (len(a) + len(b) - inter) > 0 else 0

# Build index over KS
ks_index = defaultdict(list)
ks_trigrams = []
for idx, row in enumerate(ks):
    tg = trigrams(row["norm_keyword"])
    ks_trigrams.append(tg)
    for t in tg:
        ks_index[t].append(idx)

print(f"\n  Trigram index built over {len(ks)} KS keywords")
print(f"  Unique trigrams in index: {len(ks_index)}")

def match_to_ks(norm_str):
    q_tg = trigrams(norm_str)
    candidates = set()
    for t in q_tg:
        for idx in ks_index.get(t, []):
            candidates.add(idx)
    best_idx, best_score = -1, 0.0
    for idx in candidates:
        score = jaccard(q_tg, ks_trigrams[idx])
        if score > best_score:
            best_score, best_idx = score, idx
    if best_score >= 0.5:
        return best_idx, best_score
    return -1, best_score

# Match unified → KS
matched, unmatched = [], []
for row in unified_list:
    norm_key = row.get("norm_query") or row.get("unified_key", "")
    idx, score = match_to_ks(norm_key)
    if idx >= 0:
        matched.append({**row, "ks_match_keyword": ks[idx]["keyword"], "ks_match_idx": idx, "similarity": score})
    else:
        unmatched.append({**row, "similarity": score, "unmatched_reason": "similarity < 0.5"})

# Match SE → KS
se_matched = {}
for row in se:
    idx, score = match_to_ks(row["norm_se_keyword"])
    if idx >= 0:
        kw = ks[idx]["keyword"]
        if kw not in se_matched or score > se_matched[kw]["similarity"]:
            se_matched[kw] = {"se_position": row["se_position"], "se_search_vol": row["se_search_vol"], "se_cpc": row["se_cpc"], "similarity": score}

print(f"\n  Unified → KS matching:")
print(f"    Matched:   {len(matched)} ({len(matched)/len(unified_list)*100:.0f}%)")
print(f"    Unmatched: {len(unmatched)} ({len(unmatched)/len(unified_list)*100:.0f}%)")
print(f"\n  SE Ranking → KS matching:")
print(f"    SE rows matched to KS: {len(se_matched)} / {len(se)}")

subsection("Trigram match examples (first 5 matched)")
for r in matched[:5]:
    print(f"    [{r['unified_key']:30s}] → [{r['ks_match_keyword']:30s}] sim={r['similarity']:.3f}")

subsection("Unmatched keywords (if any)")
for r in unmatched[:5]:
    print(f"    [{r['unified_key']:30s}] best_sim={r['similarity']:.3f}")

# ── Step 2e+3: Merge & Compute ────────────────────────────────────────────────
section("STEP 2e+3 — Aggregate per KS keyword, compute all 57 Masterlist columns")

# Aggregate matched performance data by KS keyword
perf_by_ks = {}
for row in matched:
    key = row["ks_match_keyword"]
    if key not in perf_by_ks:
        perf_by_ks[key] = dict(row)
    else:
        m = perf_by_ks[key]
        for f in ["gsc_clicks_p1","gsc_clicks_p2","gsc_impr_p1","gsc_impr_p2",
                  "sqr_clicks_p1","sqr_clicks_p2","sqr_cost_p1","sqr_cost_p2",
                  "sqr_impr_p1","sqr_impr_p2"]:
            m[f] = m.get(f, 0) + row.get(f, 0)

def fmt(v):
    return "" if (v is None or v == "" or v == 0) else v
def fmt_pct(v):
    return "" if v == "" else f"{round(v*10000)/100}%"
def fmt_num(v):
    return "" if v == "" else round(v * 100) / 100

output_rows = []
for ks_row in ks:
    perf = perf_by_ks.get(ks_row["keyword"], {})
    se_d = se_matched.get(ks_row["keyword"], {})

    gsc_c1, gsc_c2 = perf.get("gsc_clicks_p1", 0), perf.get("gsc_clicks_p2", 0)
    sqr_c1, sqr_c2 = perf.get("sqr_clicks_p1", 0), perf.get("sqr_clicks_p2", 0)
    gsc_i1, gsc_i2 = perf.get("gsc_impr_p1", 0), perf.get("gsc_impr_p2", 0)
    sqr_i1, sqr_i2 = perf.get("sqr_impr_p1", 0), perf.get("sqr_impr_p2", 0)
    sqr_co1, sqr_co2 = perf.get("sqr_cost_p1", 0), perf.get("sqr_cost_p2", 0)

    vol_p2 = clean_num(ks_row.get("Searches: Oct 2025", 0))  # partial

    os_c1, os_c2 = gsc_c1 + sqr_c1, gsc_c2 + sqr_c2
    os_i1, os_i2 = gsc_i1 + sqr_i1, gsc_i2 + sqr_i2

    ctr_sem_p1 = sqr_c1 / sqr_i1 if sqr_i1 > 0 else ""
    ctr_sem_p2 = sqr_c2 / sqr_i2 if sqr_i2 > 0 else ""
    ctr_seo_p1 = gsc_c1 / gsc_i1 if gsc_i1 > 0 else ""
    ctr_seo_p2 = gsc_c2 / gsc_i2 if gsc_i2 > 0 else ""
    cpc_sem_p1 = sqr_co1 / sqr_c1 if sqr_c1 > 0 else ""

    row_out = {
        "LANG": "EN",
        "Keyword": ks_row["keyword"],
        "TOPICS": ks_row["topic"],
        "CATEGORY": ks_row["category"],
        "SUB-CATEGORY": ks_row["sub_category"],
        "Position SE Ranking": fmt(se_d.get("se_position", "")),
        "Average Search Volume": fmt(se_d.get("se_search_vol", "")),
        "Volume Q1 2026": "",
        "Volume Q4 2025": fmt(vol_p2),
        "Coverage One Search Q1 2026": "",
        "Coverage One Search Q4 2025": "",
        "Clics OneSearch Q1 2026": fmt(os_c1),
        "Impressions OneSearch Q1 2026": fmt(os_i1),
        "Clics OneSearch Q4 2025": fmt(os_c2),
        "Impressions OneSearch Q4 2025": fmt(os_i2),
        "Clics SEO Q1 2026": fmt(gsc_c1),
        "Clics SEM Q1 2026": fmt(sqr_c1),
        "Clics SEO Q4 2025": fmt(gsc_c2),
        "Clics SEM Q4 2025": fmt(sqr_c2),
        "Impr. SEO Q1 2026": fmt(gsc_i1),
        "Impr. SEM Q1 2026": fmt(sqr_i1),
        "Impr. SEO Q4 2025": fmt(gsc_i2),
        "Impr. SEM Q4 2025": fmt(sqr_i2),
        "CTR SEO Q1 2026": fmt_pct(ctr_seo_p1) if ctr_seo_p1 != "" else "",
        "CTR SEM Q1 2026": fmt_pct(ctr_sem_p1) if ctr_sem_p1 != "" else "",
        "CTR SEO Q4 2025": fmt_pct(ctr_seo_p2) if ctr_seo_p2 != "" else "",
        "CTR SEM Q4 2025": fmt_pct(ctr_sem_p2) if ctr_sem_p2 != "" else "",
        "Conversions SEO Q1 2026": "", "Conversions SEM Q1 2026": "",
        "Conversions SEO Q4 2025": "", "Conversions SEM Q4 2025": "",
        "CPC SEO Q1 2026": fmt(se_d.get("se_cpc", "")),
        "CPC avg. SEM Q1 2026": fmt_num(cpc_sem_p1) if cpc_sem_p1 != "" else "",
        "Spent SEM Q1 2026": fmt(sqr_co1),
        "Cost SEO Q1 2026": "", "Spent SEM Q4 2025": fmt(sqr_co2), "Cost SEO Q4 2025": "",
        "Purchase intent": "", "Questions": "", "Yogurt types": "", "Taste": "",
        "Packaging": "", "Ingredient": "", "Brands": "", "Retailer": "",
        "Demography": "", "Benefits": "", "Testimonials": "", "Bio": "",
        "Moments": "", "Recipes": "",
        "Searches: Oct 2025": fmt(ks_row.get("Searches: Oct 2025", "")),
        "Searches: Nov 2025": "", "Searches: Dec 2025": "",
        "Searches: Jan 2026": "", "Searches: Feb 2026": "", "Searches: Mar 2026": "",
    }
    output_rows.append(row_out)

print(f"\n  Output rows: {len(output_rows)}")

subsection("Full output for first 5 KS keywords")
SHOW_COLS = [
    "Keyword", "Clics SEO Q1 2026", "Clics SEM Q1 2026",
    "Clics OneSearch Q1 2026", "Impr. SEO Q1 2026", "Impr. SEM Q1 2026",
    "CTR SEO Q1 2026", "CTR SEM Q1 2026", "CPC avg. SEM Q1 2026",
    "Position SE Ranking", "Average Search Volume",
    "Clics SEO Q4 2025", "Clics SEM Q4 2025",
]
for r in output_rows[:5]:
    print(f"\n  Keyword: [{r['Keyword']}]")
    for col in SHOW_COLS[1:]:
        val = r.get(col, "")
        if val != "":
            print(f"    {col:35s}: {val}")

# ── QA: Spot-check ────────────────────────────────────────────────────────────
section("QA — Spot-check: verify OneSearch = SEO + SEM")

qa_issues = []
for r in output_rows:
    seo_c1 = r["Clics SEO Q1 2026"] or 0
    sem_c1 = r["Clics SEM Q1 2026"] or 0
    os_c1  = r["Clics OneSearch Q1 2026"] or 0
    expected = (seo_c1 or 0) + (sem_c1 or 0)
    if isinstance(os_c1, (int, float)) and isinstance(expected, (int, float)):
        if abs(os_c1 - expected) > 0.01:
            qa_issues.append(f"  FAIL [{r['Keyword']}]: OneSearch={os_c1} ≠ SEO({seo_c1}) + SEM({sem_c1})={expected}")

if qa_issues:
    print("\n  QA FAILURES:")
    for issue in qa_issues:
        print(issue)
else:
    print(f"\n  PASS — OneSearch totals match SEO+SEM for all {len(output_rows)} rows")

# ── Summary ───────────────────────────────────────────────────────────────────
section("SUMMARY")
print(f"""
  Source samples used:
    KS:  {len(ks)} keywords (rows 1-{len(ks)} of Keyword study US)
    GSC: {len(gsc_raw)} rows → {len(gsc_filtered)} after filter (clicks>1)
    SQR: {len(sqr_raw)} rows → {len(sqr_filtered)} after filter (clicks>1)
    SE:  {len(se)} rows

  After dedup + join:
    Unified list: {len(unified_list)} keywords
    GSC-only: {len(gsc_only)}, SQR-only: {len(sqr_only)}, Both: {len(both)}

  After trigram match (threshold ≥ 0.5):
    Matched to KS: {len(matched)} ({len(matched)/max(1,len(unified_list))*100:.0f}%)
    Unmatched:     {len(unmatched)} ({len(unmatched)/max(1,len(unified_list))*100:.0f}%)
    SE matched:    {len(se_matched)} / {len(se)}

  Output: {len(output_rows)} Masterlist rows (one per KS keyword)
  QA: {"PASS" if not qa_issues else f"FAIL ({len(qa_issues)} issues)"}

  GAPS (known):
    - Volume P1 (Q1 2026): blank — Jan/Feb/Mar 2026 not yet in KS
    - Volume P2 (Q4 2025): Oct 2025 only — Nov/Dec 2025 not in KS
    - Classification labels (AL-AY): blank — not found in KS sheet
    - Conversions (AB-AE): blank — separate export not yet available
""")
