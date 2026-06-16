#!/usr/bin/env python3
"""
OneSearch n8n workflow v5 — split-loop + batch architecture.

Flow:
  Trigger → Source Config → 4 reads → 4 norms (SE filtered to position ≤ 50)
  Norm GSC + Norm SQR → Merge → Format: Base Rows → Write: Masterlist — Base
  Sync SE → Build: Trigram Index → Distribute: SE Rows
    → Split: SE Batches (500/batch, native node)
      [loop] → Match: SE Batch → Update: Masterlist — SE Batch
      [done] → Write: Cost SEO Formulas (ARRAYFORMULA AI + AK via Sheets API)
             → Sync: KS Enrichment → Match: KS Keywords
               [≥0.65] → Update: Masterlist — KS cols
               [else]  → Write: KW Review Sheet → Wait → Resume path
"""
import json, subprocess, os

N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmM2IyNjdiMC02N2IyLTQyNWYtOWM1Ni0yMjQ4NmI3YmU2ODEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMTE5NTM1OGUtZmYwOS00YmFmLTk2MGEtNmIzMTk1OTg1ODg1IiwiaWF0IjoxNzc3MzEzMDMzfQ.428JK3lqLsPkBZzn8yI9TiY6Qani-tpSZoT8A7_s4pw"
WORKFLOW_ID = "rzDfdz6sT6cYtgbl"
GS_CRED_ID  = "c4NHY7MkmOJ9YYBO"

REF_ID  = "1o526Qv4UzP_Qfe-cjrfvcA7jRUi6zUtd9Ecp2WPMIhQ"
REF_GID = 850184782

MASTER_ID     = "1W73Lzli30z4GnO_WtLjs0hWOdPcEZw1jptXKG8exKoU"
MASTER_GID    = 1730573329
KW_REVIEW_GID = 1964784525
KS_ID         = "1rTdi4cLDiFUdQHH8hj4V1GIQb8iKToKXRgFHlQcVHEI"
MASTER_TAB    = "Listing"

def surl(did, gid): return f"https://docs.google.com/spreadsheets/d/{did}/edit#gid={gid}"

def gs_read_expr(nid, name, export_label, doc_mode, pos, opts=None):
    o = opts or {}
    doc_expr = f'={{{{ $items().find(item => item.json["Export"] === "{export_label}").json["Doc ID"] }}}}'
    tab_expr = f'={{{{ $items().find(item => item.json["Export"] === "{export_label}").json["Sheet Tab"] }}}}'
    return {"id": nid, "name": name, "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5, "position": pos,
            "parameters": {
                "documentId": {"__rl": True, "value": doc_expr, "mode": doc_mode},
                "sheetName":  {"__rl": True, "value": tab_expr, "mode": "name"},
                "options": o},
            "credentials": {"googleSheetsOAuth2Api": {"id": GS_CRED_ID, "name": "Google Sheets OAuth2 API"}}}

def gs_read(nid, name, did, gid, tab, pos, opts=None):
    o = opts or {}
    return {"id": nid, "name": name, "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5, "position": pos,
            "parameters": {
                "documentId": {"__rl": True, "value": did, "mode": "id"},
                "sheetName":  {"__rl": True, "value": gid, "mode": "list",
                               "cachedResultName": tab, "cachedResultUrl": surl(did, gid)},
                "options": o},
            "credentials": {"googleSheetsOAuth2Api": {"id": GS_CRED_ID, "name": "Google Sheets OAuth2 API"}}}

def gs_append(nid, name, did, gid, tab, pos):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5, "position": pos,
            "parameters": {
                "operation": "append",
                "documentId": {"__rl": True, "value": did, "mode": "id"},
                "sheetName":  {"__rl": True, "value": gid, "mode": "list",
                               "cachedResultName": tab, "cachedResultUrl": surl(did, gid)},
                "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
                "options": {"cellFormat": "USER_ENTERED"}},
            "credentials": {"googleSheetsOAuth2Api": {"id": GS_CRED_ID, "name": "Google Sheets OAuth2 API"}}}

def gs_update(nid, name, did, gid, tab, match_cols, pos):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5, "position": pos,
            "parameters": {
                "operation": "update",
                "documentId": {"__rl": True, "value": did, "mode": "id"},
                "sheetName":  {"__rl": True, "value": gid, "mode": "list",
                               "cachedResultName": tab, "cachedResultUrl": surl(did, gid)},
                "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": match_cols, "schema": []},
                "options": {"cellFormat": "USER_ENTERED"}},
            "credentials": {"googleSheetsOAuth2Api": {"id": GS_CRED_ID, "name": "Google Sheets OAuth2 API"}}}

def code_node(nid, name, code, pos, n_out=1):
    p = {"mode": "runOnceForAllItems", "jsCode": code.strip()}
    if n_out > 1: p["outputType"] = "MultipleOutputs"; p["numberOutputs"] = n_out
    return {"id": nid, "name": name, "type": "n8n-nodes-base.code",
            "typeVersion": 2, "position": pos, "parameters": p}

def merge_gate(nid, name, n_inputs, pos):
    """chooseBranch + output:empty — sync gate. Downstream nodes read data via $('NodeName').all()."""
    return {"id": nid, "name": name, "type": "n8n-nodes-base.merge",
            "typeVersion": 3.2, "position": pos,
            "parameters": {"mode": "chooseBranch", "numberInputs": n_inputs, "output": "empty"}}

def split_batches_node(nid, name, batch_size, pos):
    """Native n8n Split in Batches node. Output 0 = loop (current batch), Output 1 = done."""
    return {"id": nid, "name": name, "type": "n8n-nodes-base.splitInBatches",
            "typeVersion": 3, "position": pos,
            "parameters": {"batchSize": batch_size, "options": {}}}

def sheets_formula_node(nid, name, master_id, formula_cells, pos, cred_id):
    """Write ARRAYFORMULA to specific cells using Sheets API values:batchUpdate (POST).
    formula_cells = list of ("SheetName!CellRef", "formula string") tuples."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{master_id}/values:batchUpdate"
    body = {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": r, "values": [[f]]} for r, f in formula_cells]
    }
    return {
        "id": nid, "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2, "position": pos,
        "parameters": {
            "method": "POST",
            "url": url,
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "googleSheetsOAuth2Api",
            "sendBody": True,
            "bodyContentType": "json",
            "jsonBody": json.dumps(body),
            "options": {}
        },
        "credentials": {"googleSheetsOAuth2Api": {"id": cred_id, "name": "Google Sheets OAuth2 API"}}
    }

def note(nid, txt, pos, w=300, h=160, color=6):
    return {"id": nid, "name": f"Note_{nid}", "type": "n8n-nodes-base.stickyNote",
            "typeVersion": 1, "position": pos,
            "parameters": {"content": txt, "height": h, "width": w, "color": color}}

# ── Shared normalize helper ────────────────────────────────────────────────────
_NORMALIZE = r"""
const normalize = s =>
  String(s||'').toLowerCase()
    .replace(/[ ​]/g,' ')
    .replace(/[^a-z0-9 ]/g,'')
    .replace(/\s+/g,' ').trim();

const cleanNum = v => {
  // Commas are thousands separators in North American Google Ads exports (e.g. "1,234" = 1234)
  const s = String(v||'0').replace(/,/g,'').trim();
  return parseFloat(s.replace(/[^0-9.\-]/g,''))||0;
};
"""

# ── Normalize nodes ────────────────────────────────────────────────────────────

NORM_KS = _NORMALIZE + r"""
// Normalize Keyword Study rows.
// Passes through: keyword fields, taxonomy cols, monthly volume cols (Oct 2025–Mar 2026).
return $input.all()
  .filter(i => String(i.json['Keyword']||'').trim())
  .map(i => {
    const j = i.json;
    return { json: {
      norm_keyword:    normalize(j['Keyword']||''),
      keyword:         String(j['Keyword']||'').trim(),
      lang:            j['LANG']         ||'EN',
      topic:           j['TOPIC']        ||'',
      category:        j['CATEGORY']     ||'',
      sub_category:    j['SUB-CATEGORY'] ||'',
      'Yogurt types':  j['Yogurt types'] ||'',
      'Taste':         j['Taste']        ||'',
      'Packaging':     j['Packaging']    ||'',
      'Ingredient':    j['Ingredient']   ||'',
      'Brands':        j['Brands']       ||'',
      'Retailer':      j['Retailer']     ||'',
      'Demography':    j['Demography']   ||'',
      'Benefits':      j['Benefits']     ||'',
      'Testimonials':  j['Testimonials'] ||'',
      'Bio':           j['Bio']          ||'',
      'Moments':       j['Moments']      ||'',
      'Recipes':       j['Recipes']      ||'',
      'Searches: Oct 2025': j['Searches: Oct 2025']||'',
      'Searches: Nov 2025': j['Searches: Nov 2025']||'',
      'Searches: Dec 2025': j['Searches: Dec 2025']||'',
      'Searches: Jan 2026': j['Searches: Jan 2026']||'',
      'Searches: Feb 2026': j['Searches: Feb 2026']||'',
      'Searches: Mar 2026': j['Searches: Mar 2026']||'',
    }};
  });
"""

NORM_GSC = _NORMALIZE + r"""
// Normalize GSC rows. Maps date-range col names to standard field names.
// No click filtering here — filtering happens in Merge: Only One Click and Higher.
const parsePct = v => parseFloat(String(v||'0').replace('%','').trim())/100||0;

return $input.all()
  .filter(i => String(i.json['Top queries']||'').trim())
  .map(i => {
    const j = i.json;
    return { json: {
      norm_query:    normalize(j['Top queries']||''),
      query:         String(j['Top queries']||''),
      gsc_clicks_p1: cleanNum(j['1/1/26 - 3/31/26 Clicks']),
      gsc_clicks_p2: cleanNum(j['10/1/25 - 12/31/25 Clicks']),
      gsc_impr_p1:   cleanNum(j['1/1/26 - 3/31/26 Impressions']),
      gsc_impr_p2:   cleanNum(j['10/1/25 - 12/31/25 Impressions']),
      gsc_ctr_p1:    parsePct(j['1/1/26 - 3/31/26 CTR']),
      gsc_ctr_p2:    parsePct(j['10/1/25 - 12/31/25 CTR']),
      gsc_pos_p1:    cleanNum(j['1/1/26 - 3/31/26 Position']),
      gsc_pos_p2:    cleanNum(j['10/1/25 - 12/31/25 Position']),
    }};
  });
"""

NORM_SQR = _NORMALIZE + r"""
// Normalize SQR rows. Maps column names to standard field names.
// No click filtering here — filtering happens in Merge: Only One Click and Higher.
return $input.all()
  .filter(i => String(i.json['Search term']||'').trim())
  .map(i => {
    const j = i.json;
    return { json: {
      norm_term:      normalize(j['Search term']||''),
      search_term:    String(j['Search term']||''),
      search_keyword: String(j['Search keyword']||''),
      sqr_clicks_p1:  cleanNum(j['Clicks']),
      sqr_clicks_p2:  cleanNum(j['Clicks (Compare to)']),
      sqr_cost_p1:    cleanNum(j['Cost']),
      sqr_cost_p2:    cleanNum(j['Cost (Compare to)']),
      sqr_impr_p1:    cleanNum(j['Impr.']),
      sqr_impr_p2:    cleanNum(j['Impr. (Compare to)']),
    }};
  });
"""

# Lever 1: filter to se_position <= 50 — eliminates low-ranking keywords that
# won't plausibly match the ~1,240 Masterlist queries, reducing data volume ~80-90%.
NORM_SE = _NORMALIZE + r"""
// Normalize SE Ranking rows. Handles BOM character on Keyword column.
// Lever 1: keep only position 1–50 (discards low-ranking rows that can't match Masterlist queries).
return $input.all()
  .map(i => {
    const j = i.json;
    const kwKey = Object.keys(j).find(k => k.replace(/﻿/g,'') === 'Keyword') || 'Keyword';
    const kw = j[kwKey] || '';
    return { json: {
      norm_se_keyword:  normalize(kw),
      se_keyword:       kw,
      se_position:      cleanNum(j['Position']),
      se_search_vol:    cleanNum(j['Search vol.']),
      se_cpc:           parseFloat(String(j['CPC']||'0').replace(/[^0-9.]/g,''))||0,
      se_search_intent: j['Search intent']||'',
    }};
  })
  .filter(r => r.json.norm_se_keyword
            && r.json.se_position > 0
            && r.json.se_position <= 50);
"""

# ── Merge: Only One Click and Higher ──────────────────────────────────────────

MERGE_CLICKS = r"""
// Reads normalized GSC and SQR by node name.
// 1. Filters: keep rows with clicks > 1 in Q1 OR Q4
// 2. Deduplicates each source by normalized keyword
// 3. Full outer join GSC ∪ SQR — one row per unique search term
//    GSC-only rows: SQR cols = 0  |  SQR-only rows: GSC cols = 0

const gscRaw = $('Norm: GSC Queries').all().map(i => i.json);
const sqrRaw = $('Norm: SQR Report').all().map(i => i.json);

const gscFiltered = gscRaw.filter(r => r.gsc_clicks_p1 > 1 || r.gsc_clicks_p2 > 1);
const sqrFiltered = sqrRaw.filter(r => r.sqr_clicks_p1 > 1 || r.sqr_clicks_p2 > 1);

// Dedup GSC
const gscMap = {};
for (const r of gscFiltered) {
  const k = r.norm_query;
  if (!gscMap[k]) { gscMap[k] = {...r}; }
  else {
    const m = gscMap[k];
    const pi1 = m.gsc_impr_p1, pi2 = m.gsc_impr_p2;
    m.gsc_clicks_p1 += r.gsc_clicks_p1; m.gsc_clicks_p2 += r.gsc_clicks_p2;
    m.gsc_impr_p1   += r.gsc_impr_p1;   m.gsc_impr_p2   += r.gsc_impr_p2;
    if (m.gsc_impr_p1 > 0) m.gsc_pos_p1 = (m.gsc_pos_p1*pi1 + r.gsc_pos_p1*r.gsc_impr_p1) / m.gsc_impr_p1;
    if (m.gsc_impr_p2 > 0) m.gsc_pos_p2 = (m.gsc_pos_p2*pi2 + r.gsc_pos_p2*r.gsc_impr_p2) / m.gsc_impr_p2;
  }
}
for (const k in gscMap) {
  const m = gscMap[k];
  m.gsc_ctr_p1 = m.gsc_impr_p1 > 0 ? m.gsc_clicks_p1 / m.gsc_impr_p1 : 0;
  m.gsc_ctr_p2 = m.gsc_impr_p2 > 0 ? m.gsc_clicks_p2 / m.gsc_impr_p2 : 0;
}

// Dedup SQR
const sqrMap = {};
for (const r of sqrFiltered) {
  const k = r.norm_term;
  if (!sqrMap[k]) { sqrMap[k] = {...r, _kws: new Set([r.search_keyword])}; }
  else {
    const m = sqrMap[k];
    m.sqr_clicks_p1 += r.sqr_clicks_p1; m.sqr_clicks_p2 += r.sqr_clicks_p2;
    m.sqr_cost_p1   += r.sqr_cost_p1;   m.sqr_cost_p2   += r.sqr_cost_p2;
    m.sqr_impr_p1   += r.sqr_impr_p1;   m.sqr_impr_p2   += r.sqr_impr_p2;
    m._kws.add(r.search_keyword);
  }
}
for (const k in sqrMap) {
  sqrMap[k].search_keyword = Array.from(sqrMap[k]._kws).join(' | ');
  delete sqrMap[k]._kws;
}

// Full outer join
const ZSQR = {sqr_clicks_p1:0, sqr_clicks_p2:0, sqr_cost_p1:0, sqr_cost_p2:0,
              sqr_impr_p1:0, sqr_impr_p2:0, search_keyword:'', search_term:''};
const ZGSC  = {gsc_clicks_p1:0, gsc_clicks_p2:0, gsc_impr_p1:0, gsc_impr_p2:0,
               gsc_ctr_p1:0, gsc_ctr_p2:0, gsc_pos_p1:0, gsc_pos_p2:0, query:''};

const sqrRem = {...sqrMap};
const unified = {};
for (const k in gscMap) {
  unified[k] = {unified_key: k, ...ZSQR, ...gscMap[k]};
  if (sqrRem[k]) { Object.assign(unified[k], sqrRem[k]); delete sqrRem[k]; }
}
for (const k in sqrRem) {
  unified[k] = {unified_key: k, norm_query: k, ...ZGSC, ...sqrRem[k]};
}

return Object.values(unified).map(r => ({json: r}));
"""

# ── Format: Base Rows ──────────────────────────────────────────────────────────

FORMAT_BASE = r"""
// Maps unified GSC+SQR fields to Masterlist column headers for base write.
// Writes only base perf cols — KS/SE enrichment cols filled in later update passes.
// Never emits Coverage cols J/K (sheet formulas) or AI/AK (ARRAYFORMULA, set separately).
const f    = v => (v===undefined||v===null||v===0) ? '' : v;
const fPct = v => v==='' ? '' : Math.round(v*10000)/100+'%';
const fNum = v => v==='' ? '' : Math.round(v*100)/100;

return $input.all().map(item => {
  const r = item.json;
  const gC1=r.gsc_clicks_p1||0, gC2=r.gsc_clicks_p2||0;
  const sC1=r.sqr_clicks_p1||0, sC2=r.sqr_clicks_p2||0;
  const gI1=r.gsc_impr_p1  ||0, gI2=r.gsc_impr_p2  ||0;
  const sI1=r.sqr_impr_p1  ||0, sI2=r.sqr_impr_p2  ||0;
  const sCo1=r.sqr_cost_p1 ||0, sCo2=r.sqr_cost_p2 ||0;

  const osC1=gC1+sC1, osI1=gI1+sI1;
  const osC2=gC2+sC2, osI2=gI2+sI2;

  const ctrSeoP1 = gI1>0 ? fPct(gC1/gI1) : '';
  const ctrSeoP2 = gI2>0 ? fPct(gC2/gI2) : '';
  const ctrSemP1 = sI1>0 ? fPct(sC1/sI1) : '';
  const ctrSemP2 = sI2>0 ? fPct(sC2/sI2) : '';
  const cpcAvgP1 = sC1>0 ? fNum(sCo1/sC1) : '';

  return { json: {
    'Keyword':                       r.query || r.search_term || r.unified_key,
    'Clics OneSearch Q1 2026':       f(osC1),
    'Impressions OneSearch Q1 2026': f(osI1),
    'Clics OneSearch Q4 2025':       f(osC2),
    'Impressions OneSearch Q4 2025': f(osI2),
    'Clics SEO Q1 2026':             f(gC1),
    'Clics SEM Q1 2026':             f(sC1),
    'Clics SEO Q4 2025':             f(gC2),
    'Clics SEM Q4 2025':             f(sC2),
    'Impr. SEO Q1 2026':             f(gI1),
    'Impr. SEM Q1 2026':             f(sI1),
    'Impr. SEO Q4 2025':             f(gI2),
    'Impr. SEM Q4 2025':             f(sI2),
    'CTR SEO Q1 2026':               ctrSeoP1,
    'CTR SEM Q1 2026':               ctrSemP1,
    'CTR SEO Q4 2025':               ctrSeoP2,
    'CTR SEM Q4 2025':               ctrSemP2,
    'CPC avg. SEM Q1 2026':          cpcAvgP1,
    'Spent SEM Q1 2026':             f(sCo1),
    'Spent SEM Q4 2025':             f(sCo2),
  }};
});
"""

# ── Build: Trigram Index ───────────────────────────────────────────────────────

BUILD_INDEX = r"""
// Build trigram (n=3) index on Masterlist col B (~1,240 unified rows).
// Includes uDisplay (display keyword per unified row) so batch match nodes
// don't need to reload the full unified dataset.
// Outputs ONE serialized item — {uKeys, uDisplay, uTg, idx} — plain arrays, JSON-safe.

const normalize = s =>
  String(s||'').toLowerCase()
    .replace(/[ ​]/g,' ')
    .replace(/[^a-z0-9 ]/g,'')
    .replace(/\s+/g,' ').trim();

function trigramsArr(str) {
  const s=' '+str+' '; const seen=new Set(), out=[];
  for(let i=0;i<=s.length-3;i++){
    const t=s.slice(i,i+3);
    if(!seen.has(t)){seen.add(t);out.push(t);}
  }
  return out;
}

const unified  = $('Merge: Only One Click and Higher').all().map(i => i.json);
const uKeys    = unified.map(r => r.unified_key||r.norm_query||'');
const uDisplay = unified.map(r => r.query||r.search_term||r.unified_key||'');
const uTg      = uKeys.map(k => trigramsArr(normalize(k)));

const idx = {};
uTg.forEach((tg,i) => { for(const t of tg){ if(!idx[t]) idx[t]=[]; idx[t].push(i); } });

return [{json: {uKeys, uDisplay, uTg, idx}}];
"""

# ── Distribute: SE Rows ────────────────────────────────────────────────────────

DISTRIBUTE_SE = r"""
// Runs after Build: Trigram Index to ensure correct execution order.
// Reads all (position-filtered) SE Ranking rows and outputs them as items
// so Split: SE Batches can chunk them into batches of 500.
return $('Norm: SE Ranking').all();
"""

# ── Match: SE Batch ────────────────────────────────────────────────────────────

MATCH_SE_BATCH = r"""
// Reads pre-built index from Build: Trigram Index by node name — no rebuild per batch.
// Processes ONLY the current batch of SE rows from $input (≤500 rows at a time).
// Lever 2: no AI/AK computation here — handled by ARRAYFORMULA written to sheet.
// Outputs update rows for: F (Position) · G (Vol) · AF (CPC SEO) · AL (Purchase intent).

function trigramsArr(str) {
  const s=' '+str+' '; const seen=new Set(), out=[];
  for(let i=0;i<=s.length-3;i++){
    const t=s.slice(i,i+3);
    if(!seen.has(t)){seen.add(t);out.push(t);}
  }
  return out;
}
function jaccard(uArr, qSet) {
  let n=0; for(const t of uArr) if(qSet.has(t)) n++;
  return n/(uArr.length + qSet.size - n);
}

const {uKeys, uDisplay, uTg, idx} = $('Build: Trigram Index').first().json;
const seRows = $input.all().map(i => i.json);  // current batch only

const bestSE = {};
for(const r of seRows) {
  const qArr = trigramsArr(r.norm_se_keyword);
  const qSet = new Set(qArr);
  const cands = new Set();
  for(const t of qArr) if(idx[t]) for(const i of idx[t]) cands.add(i);
  let bi=-1, bs=0;
  for(const i of cands) {
    const s = jaccard(uTg[i], qSet);
    if(s>bs){bs=s;bi=i;}
  }
  if(bi>=0 && bs>=0.50) {
    const k=uKeys[bi];
    if(!bestSE[k]||bs>bestSE[k]._sim)
      bestSE[k]={_sim:bs, _display:uDisplay[bi],
                 se_position:r.se_position, se_search_vol:r.se_search_vol,
                 se_cpc:r.se_cpc, se_search_intent:r.se_search_intent};
  }
}

const f = v => (v===undefined||v===null||v===0)?'':v;

return Object.entries(bestSE).map(([key, se]) => ({json: {
  'Keyword':               se._display || key,
  'Position SE Ranking':   f(se.se_position),
  'Average Search Volume': f(se.se_search_vol),
  'CPC SEO Q1 2026':       f(se.se_cpc),
  'Purchase intent':       se.se_search_intent||'',
}}));
"""

# ── Match: KS Keywords ─────────────────────────────────────────────────────────

MATCH_KS = open(
    os.path.join(os.path.dirname(__file__), "one_search_skill", "ks_map.js")
).read()

# ── Process: Approved Keywords ─────────────────────────────────────────────────

PROCESS_APPROVED = r"""
// After webhook resume. SE cols already written to Masterlist — no SE re-read needed.
// Reads KS and KW Review by node name. Outputs update rows for KS cols only.

const normalize = s =>
  String(s||'').toLowerCase()
    .replace(/[ ​]/g,' ')
    .replace(/[^a-z0-9 ]/g,'')
    .replace(/\s+/g,' ').trim();

function trigramsArr(str){
  const s=' '+str+' '; const seen=new Set(), out=[];
  for(let i=0;i<=s.length-3;i++){
    const t=s.slice(i,i+3);
    if(!seen.has(t)){seen.add(t);out.push(t);}
  }
  return out;
}
function jaccard(uArr, qSet){
  let n=0; for(const t of uArr) if(qSet.has(t)) n++;
  return n/(uArr.length + qSet.size - n);
}

const ksRaw     = $('Read: KS (Resume)').all().map(i => i.json);
const reviewRows= $('Read: KW Review (Resume)').all().map(i => i.json);

const approved=reviewRows.filter(r=>String(r['approved']||'').toUpperCase().trim()==='YES');
if(!approved.length) return [{json:{status:'no approved keywords'}}];

const ksAll=ksRaw.filter(j=>String(j['Keyword']||'').trim()).map(j=>({
  keyword:     String(j['Keyword']||'').trim(),
  norm_keyword:normalize(j['Keyword']||''),
  lang:        j['LANG']||'EN', topic: j['TOPIC']||'',
  category:    j['CATEGORY']||'', sub_category: j['SUB-CATEGORY']||'',
  'Yogurt types':j['Yogurt types']||'','Taste':j['Taste']||'',
  'Packaging':j['Packaging']||'','Ingredient':j['Ingredient']||'',
  'Brands':j['Brands']||'','Retailer':j['Retailer']||'',
  'Demography':j['Demography']||'','Benefits':j['Benefits']||'',
  'Testimonials':j['Testimonials']||'','Bio':j['Bio']||'',
  'Moments':j['Moments']||'','Recipes':j['Recipes']||'',
  'Searches: Oct 2025':j['Searches: Oct 2025']||'',
  'Searches: Nov 2025':j['Searches: Nov 2025']||'',
  'Searches: Dec 2025':j['Searches: Dec 2025']||'',
  'Searches: Jan 2026':j['Searches: Jan 2026']||'',
  'Searches: Feb 2026':j['Searches: Feb 2026']||'',
  'Searches: Mar 2026':j['Searches: Mar 2026']||'',
}));

const ksNameMap={};
for(const r of ksAll) ksNameMap[r.keyword.toLowerCase()]=r;

const ksTg=ksAll.map(r=>trigramsArr(r.norm_keyword));
const idx={};
ksTg.forEach((tg,i)=>{ for(const t of tg){ if(!idx[t]) idx[t]=[]; idx[t].push(i); } });
function bestMatch(normStr){
  const qArr=trigramsArr(normStr); const qSet=new Set(qArr); const cands=new Set();
  for(const t of qArr) if(idx[t]) for(const i of idx[t]) cands.add(i);
  let bi=-1,bs=0;
  for(const i of cands){ const s=jaccard(ksTg[i],qSet); if(s>bs){bs=s;bi=i;} }
  return bi>=0?ksAll[bi]:null;
}

const f=v=>(v===undefined||v===null||v===0)?'':v;

return approved.map(r=>{
  const manKey=String(r['manual_ks_match']||'').trim().toLowerCase();
  const sugKey=String(r['suggested_ks_match']||'').trim().toLowerCase();
  const ks=ksNameMap[manKey]||ksNameMap[sugKey]||bestMatch(normalize(r['keyword']||''));
  if(!ks) return null;

  const volP1=(parseFloat(ks['Searches: Jan 2026'])||0)
             +(parseFloat(ks['Searches: Feb 2026'])||0)
             +(parseFloat(ks['Searches: Mar 2026'])||0);
  const volP2=(parseFloat(ks['Searches: Oct 2025'])||0)
             +(parseFloat(ks['Searches: Nov 2025'])||0)
             +(parseFloat(ks['Searches: Dec 2025'])||0);

  return {json:{
    'Keyword':       r['keyword']||'',
    'LANG':          ks.lang||'EN',
    'TOPICS':        ks.topic||'', 'CATEGORY': ks.category||'', 'SUB-CATEGORY': ks.sub_category||'',
    'Volume Q1 2026':f(volP1), 'Volume Q4 2025':f(volP2),
    'Yogurt types':ks['Yogurt types']||'','Taste':ks['Taste']||'',
    'Packaging':ks['Packaging']||'','Ingredient':ks['Ingredient']||'',
    'Brands':ks['Brands']||'','Retailer':ks['Retailer']||'',
    'Demography':ks['Demography']||'','Benefits':ks['Benefits']||'',
    'Testimonials':ks['Testimonials']||'','Bio':ks['Bio']||'',
    'Moments':ks['Moments']||'','Recipes':ks['Recipes']||'',
    'Searches: Oct 2025':f(ks['Searches: Oct 2025']),
    'Searches: Nov 2025':f(ks['Searches: Nov 2025']),
    'Searches: Dec 2025':f(ks['Searches: Dec 2025']),
    'Searches: Jan 2026':f(ks['Searches: Jan 2026']),
    'Searches: Feb 2026':f(ks['Searches: Feb 2026']),
    'Searches: Mar 2026':f(ks['Searches: Mar 2026']),
  }};
}).filter(Boolean);
"""

# ── Nodes ──────────────────────────────────────────────────────────────────────
# Layout:
#   Input section:    x = -1312 … -60,    y = 240 (main) / 0–480 (per-source)
#   Merge/Base:       x = 240 … 1280,     y = 240
#   SE batch section: x = 1540 … 2060,    y = 240 (main) / 440 (loop) / 60 (done)
#   KS section:       x = 2320 … 2840,    y = 60 (main)
#   Post-approval:    x = 3100 … 4140,    y = various

nodes = [
    # ── Trigger ──────────────────────────────────────────────────────────────
    {"id":"trigger-01","name":"Manual Trigger","type":"n8n-nodes-base.manualTrigger",
     "typeVersion":1,"position":[-1312,240],"parameters":{}},

    # ── Source config (Export name → Doc ID + Sheet Tab) ─────────────────────
    {"id":"ref-sheet","name":"Read: Source Config",
     "type":"n8n-nodes-base.googleSheets","typeVersion":4.7,"position":[-1136,240],
     "parameters":{
         "documentId":{"__rl":True,"value":REF_ID,"mode":"id"},
         "sheetName": {"__rl":True,"value":REF_GID,"mode":"list",
                       "cachedResultName":"One Search ",
                       "cachedResultUrl":surl(REF_ID, REF_GID)},
         "options":{}},
     "credentials":{"googleSheetsOAuth2Api":{"id":GS_CRED_ID,"name":"Google Sheets OAuth2 API"}}},

    # ── 4 source reads ────────────────────────────────────────────────────────
    gs_read_expr("read-ks",  "Read: Keyword Study", "Keyword study",            "id",  [-380,   0]),
    gs_read_expr("read-gsc", "Read: GSC Queries",   "GSC Export",               "url", [-380, 160]),
    gs_read_expr("read-sqr", "Read: SQR Report",    "Account Level SQR Report", "url", [-380, 320], opts={"range":"A2:U"}),
    gs_read_expr("read-se",  "Read: SE Ranking",    "SE Ranking",               "id",  [-380, 480]),

    # ── Normalize (one per source) ────────────────────────────────────────────
    code_node("norm-ks",  "Norm: Keyword Study", NORM_KS,  [-60,   0]),
    code_node("norm-gsc", "Norm: GSC Queries",   NORM_GSC, [-60, 160]),
    code_node("norm-sqr", "Norm: SQR Report",    NORM_SQR, [-60, 320]),
    code_node("norm-se",  "Norm: SE Ranking",    NORM_SE,  [-60, 480]),

    # ── Sync gate: wait for BOTH Norm GSC and Norm SQR before merging ────────
    # Code nodes only have input index 0. Without this gate, connecting SQR at
    # index 1 is invalid and the Merge node runs before SQR data is available.
    merge_gate("sync-gscsqr", "Sync: GSC + SQR", 2, [80, 240]),

    # ── Merge GSC + SQR ───────────────────────────────────────────────────────
    code_node("merge-clicks", "Merge: Only One Click and Higher", MERGE_CLICKS, [240, 240]),

    # ── Format base cols → append to Masterlist ───────────────────────────────
    code_node("format-base", "Format: Base Rows", FORMAT_BASE, [500, 240]),
    gs_append("write-base", "Write: Masterlist — Base", MASTER_ID, MASTER_GID, MASTER_TAB, [760, 240]),

    # ── Sync: wait for Write Base + Norm SE ──────────────────────────────────
    merge_gate("sync-se", "Sync: SE Enrichment", 2, [1020, 240]),

    # ── Build trigram index (once) ────────────────────────────────────────────
    code_node("build-idx", "Build: Trigram Index", BUILD_INDEX, [1280, 240]),

    # ── Distribute SE rows to Split node ─────────────────────────────────────
    code_node("dist-se", "Distribute: SE Rows", DISTRIBUTE_SE, [1540, 240]),

    # ── Split SE rows into batches of 500 ────────────────────────────────────
    split_batches_node("split-se", "Split: SE Batches", 500, [1800, 240]),

    # ── [LOOP PATH] Match + Update per batch (runs N times) ──────────────────
    code_node("match-se-batch", "Match: SE Batch", MATCH_SE_BATCH, [2060, 440]),
    gs_update("update-se-batch", "Update: Masterlist — SE Batch",
              MASTER_ID, MASTER_GID, MASTER_TAB, ["Keyword"], [2320, 440]),

    # ── [DONE PATH] Write Cost SEO ARRAYFORMULA to sheet (AI + AK) ───────────
    sheets_formula_node("write-formulas", "Write: Cost SEO Formulas", MASTER_ID, [
        (f"{MASTER_TAB}!AI2", '=ARRAYFORMULA(IF(ISBLANK(AF2:AF),"",AF2:AF*P2:P))'),
        (f"{MASTER_TAB}!AK2", '=ARRAYFORMULA(IF(ISBLANK(AF2:AF),"",AF2:AF*R2:R))'),
    ], [2060, 60], GS_CRED_ID),

    # ── Sync: wait for formula write + Norm KS ────────────────────────────────
    merge_gate("sync-ks", "Sync: KS Enrichment", 2, [2320, 60]),

    # ── Match KS (reads index by node name, no rebuild) ───────────────────────
    code_node("match-ks", "Match: KS Keywords", MATCH_KS, [2580, 60], n_out=2),

    # ── High-confidence KS update ─────────────────────────────────────────────
    gs_update("update-ks", "Update: Masterlist — KS cols",
              MASTER_ID, MASTER_GID, MASTER_TAB, ["Keyword"], [2840, -60]),

    # ── KW Review path ────────────────────────────────────────────────────────
    gs_append("write-kwr", "Write: KW Review Sheet",
              MASTER_ID, KW_REVIEW_GID, "KW Review", [2840, 200]),

    {"id":"wait-approval","name":"Wait: User Approval","type":"n8n-nodes-base.wait",
     "typeVersion":1.1,"position":[3100, 200],
     "parameters":{"resume":"webhook","options":{}}},

    # ── Post-approval resume ──────────────────────────────────────────────────
    gs_read("read-kwr-resume", "Read: KW Review (Resume)",
            MASTER_ID, KW_REVIEW_GID, "KW Review", [3360, 260]),
    gs_read("read-ks-resume",  "Read: KS (Resume)",
            KS_ID, 1573806855, "Keyword study US", [3360, 0]),

    merge_gate("sync-resume", "Sync: Resume Sources", 2, [3620, 120]),
    code_node("process-approved", "Process: Approved Keywords", PROCESS_APPROVED, [3880, 120]),
    gs_update("update-ks-approved", "Update: Masterlist — KS cols (Approved)",
              MASTER_ID, MASTER_GID, MASTER_TAB, ["Keyword"], [4140, 120]),

    # ── Stubs ─────────────────────────────────────────────────────────────────
    note("note-ga4-stub",
         "### Stub: GA4 Loop\nNOT CONNECTED\n\nWill reuse Build: Trigram Index output by node name.\nTarget cols: AB (Conversions SEO Q1) · AD (Conversions SEO Q4)\nConnect when GA4 organic conversion export is available.",
         [2580, -200], w=340, h=160, color=5),

    note("note-conv-sem",
         "### Stub: Conversions SEM\nNOT CONNECTED\n\nSeparate Google Ads conversion export needed.\nFilter to: mikmak_checkout + mikmak_click_offline_store\nTarget: cols AC (Conv SEM Q1) · AE (Conv SEM Q4)",
         [2580, -400], w=340, h=140, color=5),

    # ── Architecture notes ────────────────────────────────────────────────────
    note("note-main",
         "### OneSearch — Oikos USA (v5)\n\n**Batch + ARRAYFORMULA architecture (Apr 2026):**\n1. Trigger → Source Config → 4 reads → 4 norms\n   SE filtered: position 1–50 only (Lever 1)\n2. Norm GSC + SQR → Merge → Format → Write Base\n3. Sync SE → Build: Trigram Index (once)\n4. Distribute: SE Rows → Split: SE Batches (500/batch)\n   [loop] Match: SE Batch → Update SE Batch (per batch)\n   [done] Write: Cost SEO Formulas (ARRAYFORMULA AI+AK)\n5. Sync KS → Match: KS Keywords (reuses index)\n   ≥0.65 → Update KS cols · else → KW Review\n6. KW Review → Wait → Resume → Process → Update\n\n⚠️ Clear rows 2+ in Listing before re-running",
         [-1312,-360], w=380, h=520, color=6),

    note("note-lever1",
         "### Lever 1 — SE Position Filter\nNorm: SE Ranking keeps only rows where\nse_position > 0 AND se_position ≤ 50.\nEliminates ~80–90% of SE rows before matching,\nfixing the runner crash in Match: SE Keywords.",
         [-60, 620], w=320, h=160, color=7),

    note("note-build-idx",
         "### Build: Trigram Index\nBuilds n=3 index on ~1,240 Masterlist col B rows.\nIncludes uDisplay (keyword display text) — batch nodes\ndon't need to reload unified data.\nOutputs ONE item: {uKeys, uDisplay, uTg, idx}.",
         [1280, 60], w=320, h=160, color=4),

    note("note-batch",
         "### SE Batch Loop\nSplit: SE Batches chunks filtered SE rows (≤500 each).\nEach batch: Match: SE Batch reads index by node name\n(no rebuild) and processes only $input (500 rows max).\nUpdate: Masterlist — SE Batch writes per batch.\nLast batch's match wins if multiple batches match\nthe same Masterlist row (rare after position filter).",
         [1800, 580], w=360, h=200, color=4),

    note("note-formulas",
         "### Write: Cost SEO Formulas (Lever 2)\nFires from Split: SE Batches done output —\nafter ALL batches complete.\nWrites ARRAYFORMULA to Masterlist sheet:\n  AI2 = ARRAYFORMULA(IF(ISBLANK(AF2:AF),\"\",AF2:AF*P2:P))\n  AK2 = ARRAYFORMULA(IF(ISBLANK(AF2:AF),\"\",AF2:AF*R2:R))\nAI = Cost SEO Q1 2026 · AK = Cost SEO Q4 2025",
         [2060, -200], w=380, h=220, color=4),

    note("note-match-ks",
         "### Match: KS Keywords\nReads index via $('Build: Trigram Index').first().json.\nNo rebuild — index built once and reused.\nIterates 14,273 KS keywords.\n≥ 0.65 → Update KS cols (auto)\n0.50–0.65 · <0.50 → KW Review (human)\nFills: A C D E H I AM–AX AZ–BE",
         [2580, 200], w=320, h=200, color=4),

    note("note-approval",
         "### Human-in-the-loop\n1. Borderline + unmatched → KW Review tab\n2. Workflow pauses — find Resume URL in execution log\n3. Open KW Review · type YES in 'approved'\n   Optionally fill 'manual_ks_match'\n4. POST to webhook or click Resume in n8n UI\n5. Approved rows computed + Masterlist updated",
         [3100, 400], w=340, h=220, color=3),
]

# ── Connections ────────────────────────────────────────────────────────────────
connections = {
    # Input section
    "Manual Trigger":    {"main": [[{"node":"Read: Source Config","type":"main","index":0}]]},
    "Read: Source Config": {"main": [[
        {"node":"Read: Keyword Study","type":"main","index":0},
        {"node":"Read: GSC Queries",  "type":"main","index":0},
        {"node":"Read: SQR Report",   "type":"main","index":0},
        {"node":"Read: SE Ranking",   "type":"main","index":0},
    ]]},
    "Read: Keyword Study": {"main": [[{"node":"Norm: Keyword Study","type":"main","index":0}]]},
    "Read: GSC Queries":   {"main": [[{"node":"Norm: GSC Queries",  "type":"main","index":0}]]},
    "Read: SQR Report":    {"main": [[{"node":"Norm: SQR Report",   "type":"main","index":0}]]},
    "Read: SE Ranking":    {"main": [[{"node":"Norm: SE Ranking",   "type":"main","index":0}]]},

    # Norm → downstream
    "Norm: Keyword Study": {"main": [[{"node":"Sync: KS Enrichment","type":"main","index":1}]]},
    "Norm: GSC Queries":   {"main": [[{"node":"Sync: GSC + SQR","type":"main","index":0}]]},
    "Norm: SQR Report":    {"main": [[{"node":"Sync: GSC + SQR","type":"main","index":1}]]},
    "Norm: SE Ranking":    {"main": [[{"node":"Sync: SE Enrichment","type":"main","index":1}]]},

    # Sync gate → Merge
    "Sync: GSC + SQR": {"main": [[{"node":"Merge: Only One Click and Higher","type":"main","index":0}]]},

    # Merge → Format → Write Base → Sync SE
    "Merge: Only One Click and Higher": {"main": [[{"node":"Format: Base Rows","type":"main","index":0}]]},
    "Format: Base Rows":                {"main": [[{"node":"Write: Masterlist — Base","type":"main","index":0}]]},
    "Write: Masterlist — Base":         {"main": [[{"node":"Sync: SE Enrichment","type":"main","index":0}]]},

    # SE enrichment — build index, distribute, split
    "Sync: SE Enrichment":   {"main": [[{"node":"Build: Trigram Index",  "type":"main","index":0}]]},
    "Build: Trigram Index":  {"main": [[{"node":"Distribute: SE Rows",   "type":"main","index":0}]]},
    "Distribute: SE Rows":   {"main": [[{"node":"Split: SE Batches",     "type":"main","index":0}]]},

    # Split outputs: 0=loop, 1=done
    "Split: SE Batches": {"main": [
        [{"node":"Match: SE Batch",         "type":"main","index":0}],  # loop
        [{"node":"Write: Cost SEO Formulas","type":"main","index":0}],  # done
    ]},

    # Loop path: match → update (runs per batch)
    "Match: SE Batch":              {"main": [[{"node":"Update: Masterlist — SE Batch","type":"main","index":0}]]},

    # Done path: formula write → Sync KS
    "Write: Cost SEO Formulas": {"main": [[{"node":"Sync: KS Enrichment","type":"main","index":0}]]},

    # KS section
    "Sync: KS Enrichment": {"main": [[{"node":"Match: KS Keywords","type":"main","index":0}]]},
    "Match: KS Keywords": {"main": [
        [{"node":"Update: Masterlist — KS cols","type":"main","index":0}],  # high conf
        [{"node":"Write: KW Review Sheet",      "type":"main","index":0}],  # review
    ]},

    # KW Review path
    "Write: KW Review Sheet": {"main": [[{"node":"Wait: User Approval","type":"main","index":0}]]},

    # Post-approval
    "Wait: User Approval": {"main": [[
        {"node":"Read: KW Review (Resume)","type":"main","index":0},
        {"node":"Read: KS (Resume)",       "type":"main","index":0},
    ]]},
    "Read: KW Review (Resume)": {"main": [[{"node":"Sync: Resume Sources","type":"main","index":0}]]},
    "Read: KS (Resume)":        {"main": [[{"node":"Sync: Resume Sources","type":"main","index":1}]]},
    "Sync: Resume Sources":     {"main": [[{"node":"Process: Approved Keywords","type":"main","index":0}]]},
    "Process: Approved Keywords": {"main": [[{"node":"Update: Masterlist — KS cols (Approved)","type":"main","index":0}]]},
}

# ── Build + deploy ─────────────────────────────────────────────────────────────
payload = {
    "name": "One Search - Merge Documents",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "pinData": {}
}

out_path = os.path.join(os.path.dirname(__file__), "one_search_skill", "n8n_workflow_v5.json")
with open(out_path, "w") as fh:
    json.dump(payload, fh, indent=2)
print(f"Saved: {out_path}")
print(f"Payload: {len(json.dumps(payload)):,} bytes | {len(nodes)} nodes")

r = subprocess.run([
    "curl","-s","-w","\n---STATUS:%{http_code}---",
    "-X","PUT",
    f"https://opdigitad.app.n8n.cloud/api/v1/workflows/{WORKFLOW_ID}",
    "-H",f"X-N8N-API-KEY: {N8N_API_KEY}",
    "-H","Content-Type: application/json",
    "-d", json.dumps(payload),
], capture_output=True, text=True)

out = r.stdout; cut = out.rfind("---STATUS:")
body, status = out[:cut], out[cut+10:].strip().rstrip("-")
print(f"HTTP {status}")
try:
    resp = json.loads(body)
    if "message" in resp: print(f"ERROR: {resp['message']}")
    else: print(f"OK — {len(resp.get('nodes',[]))} nodes | versionId: {resp.get('versionId','?')}")
except: print("Raw:", body[:400])
