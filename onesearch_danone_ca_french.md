---
name: onesearch-danone
description: >
  Génère un dashboard One Search interactif HTML self-contained pour une marque Danone Canada
  (Activia, Oikos, Silk, International Delight). Orchestre la collecte des données Google Ads,
  GSC, SE Ranking, puis génère les 6 onglets du dashboard V8 (Glossaire, OneSearch Dashboard,
  Territory Deep Dive, Recommendations, Quality Score, SQR).
  Use when the user wants to create or update a One Search dashboard, mentions "/onesearch-danone",
  or asks to generate a Danone brand dashboard.
---

# One Search Danone — Dashboard HTML V8

Ce skill génère un dashboard One Search complet et interactif pour les marques Danone Canada.
Le fichier de référence est :
`/Users/thomasjoachim/Documents/One Search Danone/dashboard_onesearch_ACTIVIA_V8.html`

## Arguments

- `$ARGUMENTS` — La marque cible. Valeurs acceptées : `activia`, `oikos`, `silk`, `id`

## Flags optionnels

| Flag | Effet |
|------|-------|
| `--period-current <Q>` | Période actuelle (ex: `Q1 2026`, défaut: détecté depuis les fichiers CSV) |
| `--period-prev <Q>` | Période précédente (ex: `Q4 2025`) |
| `--data-path <chemin>` | Chemin vers le dossier DATA (défaut: `/Users/thomasjoachim/Documents/One Search Danone/DATA/`) |
| `--masterlist <chemin>` | Chemin vers la MASTERLIST XLSX (défaut: détectée automatiquement) |
| `--output <chemin>` | Fichier HTML de sortie (défaut: même dossier que les dashboards V8 existants) |
| `--no-sqr` | Skip l'onglet SQR (si données non disponibles) |

---

## CONTEXTE PRODUIT

### Marques Danone Canada

| Marque | Abrév. | Fichier de référence |
|--------|--------|----------------------|
| Activia | ACTIVIA | dashboard_onesearch_ACTIVIA_V8.html |
| Oikos | OIKOS | dashboard_onesearch_OIKOS_V8.html |
| Silk | SILK | dashboard_onesearch_SILK_V8.html |
| International Delight | ID | dashboard_onesearch_ID_V8.html |

### Périodes standard

- **Current** : trimestre en cours (ex: Q1 2026 = 1 jan - 31 mar)
- **Previous** : trimestre précédent (ex: Q4 2025 = 1 oct - 31 dec)
- Comparer toujours Current vs Previous dans toutes les métriques

### Naming des fichiers de données

**Google Ads Search Query Report (SQR) :**
`<Marque> <Q> <Annee> - Rapport sur les termes de recherche.csv`

**Google Ads Keywords Report :**
`<Marque> <Q> <Annee> - Rapport sur les mots clés pour le Réseau de Recherche.csv`

**Landing Pages Report :**
`<Marque> <Q> <Annee> - Page_de_destination.csv`

**SE Ranking :**
`export_research_ca_domain_history_eur_<AAAA-MM>_<marque>.csv`

**MASTERLIST :**
`MASTERLIST - <Marque> OneSearch - Offline DEF V5.xlsx`

---

## WORKFLOW

```
ÉTAPE 1  COLLECTE DONNÉES    → Lire CSV/XLSX depuis DATA/ et MASTERLIST
ÉTAPE 2  CALCUL MÉTRIQUES    → Agréger KPIs, territories, QS, SQR
ÉTAPE 3  PRÉPARATION JS      → Structurer les arrays de données pour injection
ÉTAPE 4  GÉNÉRATION HTML     → Partir du template V8 existant (même marque ou Activia)
ÉTAPE 5  INJECTION DONNÉES   → Remplacer les blocs de données JS dans le HTML
ÉTAPE 6  VALIDATION          → Vérifier les 6 onglets, KPIs, charts, filtres
```

---

## ÉTAPE 1 — COLLECTE DES DONNÉES

### 1.1 Identifier les fichiers disponibles

```bash
# Lister les fichiers de données pour la marque
ls "/Users/thomasjoachim/Documents/One Search Danone/DATA/" | grep -i <marque>
```

Fichiers attendus (2 périodes × 3 types = 6 CSV minimum) :
- SQR Current + Previous
- Keywords Current + Previous
- Landing Pages Current + Previous
- SE Ranking (export le plus récent)

### 1.2 Lire la MASTERLIST

La MASTERLIST est la source de vérité pour :
- La liste complète des keywords prioritaires
- Les territories et catégories
- Les données SEO agrégées (position SE Ranking, volume)
- La classification Topic/Category/Subcategory pour le QS panel

Lire avec Python :
```python
import pandas as pd
masterlist = pd.read_excel(
    "/Users/thomasjoachim/Documents/One Search Danone/MASTERLIST - Activia OneSearch - Offline DEF V5.xlsx",
    sheet_name=None  # Charger toutes les feuilles
)
```

### 1.3 En-têtes CSV Google Ads (tous en français)

**SQR — Termes de recherche :**
```
Terme de recherche | Type de correspondance | Ajoutée/Exclue | Campagne | Groupe d'annonces |
Mot clé | Impr. | Impr. (par rapport à) | Impr. (différence) | Impr. (différence en pourcentage) |
Clics | Clics (par rapport à) | Clics (différence) | Clics (différence en pourcentage) |
Code de la devise | CPC moy. | CPC moy. (différence) | CPC moy. (différence en pourcentage) |
Coût | Coût (différence) | Coût (différence en pourcentage) |
Conversions | Conversions (différence) | Taux de conv. | Taux de conv. (différence) |
Coût/conv. | Coût/conv. (différence)
```

**Keywords — Mots clés réseau de recherche :**
Même structure que SQR mais par mot-clé agrégé + colonne Quality Score

**Landing Pages :**
```
Page de destination finale | Code de la devise | Impr. | Clics | Coût | Conv. |
Taux de conv. | Valeur conv. | Coût/conv.
```

**SE Ranking :**
```
Keyword | Difficulty | Position | Previous position | Search vol. | Search intent |
SERP features | Competition | CPC | URL | Traffic | Traffic share | Traffic cost
```

---

## ÉTAPE 2 — CALCUL DES MÉTRIQUES

### 2.1 KPIs globaux (onglet OneSearch Dashboard)

Calculer depuis la MASTERLIST et les CSV :

| Métrique | Calcul | Source |
|----------|--------|--------|
| Search Volume | Somme volume mensuel × 3 | SE Ranking |
| OneSearch Clicks | SEO Clicks + SEM Clicks | GSC + Google Ads |
| SEO Clicks | Somme clics GSC sur keywords prioritaires | GSC |
| SEM Clicks | Somme clics Google Ads | Google Ads Keywords |
| Coverage % | Keywords avec position SEO ≤ 20 ou SEM actif / total keywords | SE Ranking + Keywords |
| Conversions | Conv. SEM + Conv. SEO | Google Ads + GSC (si dispo) |

**Variation** : toujours `(Current - Previous) / Previous × 100`

### 2.2 Calcul Coverage

```
OneSearch Coverage = keywords avec (SEO pos ≤ 20 OU SEM impressions > 0) / total × 100
SEO Coverage       = keywords avec SEO pos ≤ 20 / total × 100
SEM Coverage       = keywords avec SEM impressions > 0 / total × 100
```

### 2.3 Quality Score — Structure des données

La colonne QS vient du rapport Keywords. Enrichir avec la MASTERLIST pour Topic/Category/Subcategory.

Format de l'array `QS_CLASSIFIED` injecté en JS :
```javascript
// [KW, MATCH, CAMP, ADGR, STATUS, URL, QS, LP_EXP, CTR_ATT, PERT, IMPR, CLICS, COUT, CPC, CONV, TOPIC, CAT, SUB]
var QS_CLASSIFIED = [
  ["greek yogurt", "Broad", "CAN_EDP_ACTIVIA_CORE-PROBIOTICS_NA_EN", "Yogurt probiotics",
   "Eligible", "https://www.activia.ca/en/probiotics", 6, "Average", "Average", "Relevant",
   39, 1, 2.45, 2.45, 1.0, "Probiotics", "Generic", "Yogurt"],
  // ...
];
```

Indices JS :
```javascript
var I = {KW:0, MATCH:1, CAMP:2, ADGR:3, STATUS:4, URL:5, QS:6, LP:7,
         CTR_ATT:8, PERT:9, IMPR:10, CLICS:11, COUT:12, CPC:13, CONV:14,
         TOPIC:15, CAT:16, SUB:17};
```

Valeurs LP_EXP : `"Above Average"`, `"Average"`, `"Below Average"`, `"Not Available"`
Valeurs STATUS : `"Eligible"` (actif), `"Veille"` (mis en pause), `"Non eligible"` (hors campagne)

### 2.4 Territories — Structure

Chaque marque a 5-7 territoires. Pour Activia :
1. Yogurt Generic
2. Probiotics
3. Brand
4. Nutrition & Digestive Health
5. Product-Specific
6. Recipes & Content

Pour chaque territoire, calculer :
```python
territory_data = {
    "name": "Yogurt Generic",
    "keywords_count": 487,
    "volume_current": 685600,
    "volume_prev": 710000,
    "onesearch_clicks_current": 1240,
    "onesearch_clicks_prev": 980,
    "seo_clicks_current": 890,
    "seo_clicks_prev": 720,
    "sem_clicks_current": 350,
    "sem_clicks_prev": 260,
    "coverage_current": 67.4,
    "coverage_prev": 62.1,
    "conv_seo_current": 12,
    "conv_sem_current": 34,
    "top5_keywords": [
        {"kw": "yogurt", "clicks": 245},
        {"kw": "greek yogurt", "clicks": 189},
        # ...
    ]
}
```

### 2.5 SQR — Structure pour onglet SQR

Partir du fichier SQR Current. Format attendu pour injection JS :
```javascript
var SQR_DATA = [
  // [query, match_type, added_excluded, campaign, adgroup, keyword,
  //  impr_curr, impr_prev, impr_diff, impr_pct,
  //  clicks_curr, clicks_prev, clicks_diff, clicks_pct,
  //  cpc_curr, cpc_prev, cpc_diff, cpc_pct,
  //  cost_curr, cost_prev, cost_diff, cost_pct,
  //  conv_curr, conv_prev, conv_diff, conv_pct,
  //  conv_rate_curr, conv_rate_prev, conv_rate_pct,
  //  cpa_curr, cpa_prev, cpa_diff, cpa_pct]
  ["greek yogurt", "Broad", "None", "CAN_EDP_ACTIVIA_...", "Yogurt probiotics",
   "probiotic yogurt", 39, 183, -144, -78.69, 1, 2, -1, -50.0,
   2.45, 2.48, -0.03, -1.01, 2.45, 4.95, -2.50, -50.51,
   1.0, 0.0, 1.0, 100.0, 100.0, 0.0, 0.0, 2.45, 0.0, 2.45, 100.0],
  // ...
];
```

---

## ÉTAPE 3 — PRÉPARATION DES DONNÉES JS

Générer les blocs de données via un script Python :

```bash
python3 << 'EOF'
import pandas as pd
import json

brand = "activia"  # adapter
data_path = "/Users/thomasjoachim/Documents/One Search Danone/DATA/"

# 1. Charger les fichiers
# 2. Calculer les métriques
# 3. Générer les arrays JS
# 4. Exporter vers un fichier .js ou directement dans le HTML
EOF
```

### Blocs JS à injecter dans le HTML

Identifier les blocs dans le fichier HTML source entre :
```html
<script>
// === DATA INJECTION START ===
var QS_CLASSIFIED = [...];
var TERRITORY_DATA = [...];
var SQR_DATA = [...];
var KPI_SUMMARY = {...};
// === DATA INJECTION END ===
</script>
```

---

## ÉTAPE 4 — GÉNÉRATION DU HTML

### 4.1 Partir du fichier de référence existant

**TOUJOURS partir du HTML V8 existant** de la marque concernée, ou d'Activia si nouvelle marque.

```python
# Lire le fichier de référence
with open("/Users/thomasjoachim/Documents/One Search Danone/dashboard_onesearch_ACTIVIA_V8.html", "r") as f:
    html_content = f.read()
```

**Ne jamais régénérer de zéro.** Le template V8 contient 35 000+ lignes de CSS, JS interactif, et composants visuels finalisés.

### 4.2 Adaptations par marque

| Élément | Localisation | Adapter |
|---------|-------------|---------|
| Titre H1 | `<h1>` dans le hero banner | "One Search Dashboard — [Marque] Canada" |
| Sous-titre | `.subtitle` | "Digitad × [Marque] Canada · One Search · [Mois Année]" |
| Chips header | `.chip` | Mettre à jour keywords count, période, KPIs |
| Couleur brand | `--brand` variable CSS | Adapter à la marque si différente de #B8001C |
| Périodes | Textes "Q1 2026", "Q4 2025" | Mettre à jour partout |
| Territoires | Section `panel-territory` | Remplacer les 6 blocs territoire |

### 4.3 Charte couleurs par marque

| Marque | Brand Color | Notes |
|--------|-------------|-------|
| Activia | #B8001C (Danone red) | Défaut |
| Oikos | #1A3C6E (Oikos blue) | Adapter `--brand` |
| Silk | #2E7D32 (Silk green) | Adapter `--brand` |
| International Delight | #E65100 (ID orange) | Adapter `--brand` |

### 4.4 Éléments statiques à mettre à jour manuellement

Ces sections sont rédigées en prose et ne sont pas générées depuis les données :
- **Territory Deep Dive** : Wins, Attention Points, Actions & Next Steps
- **One Search Recommendations** : Recommandations priorisées (Immediate / Short Term / Medium Term)
- **Introduction** : Chips, formules, glossaire

---

## ÉTAPE 5 — INJECTION DES DONNÉES

### 5.1 Localiser les blocs de données dans le HTML

Utiliser `grep` pour trouver les balises d'injection :

```bash
grep -n "QS_CLASSIFIED\|TERRITORY_DATA\|SQR_DATA\|KPI_SUMMARY" \
  "/Users/thomasjoachim/Documents/One Search Danone/dashboard_onesearch_ACTIVIA_V8.html" | head -20
```

### 5.2 Remplacer les données avec Python

```python
import re

# Pattern pour remplacer le bloc QS_CLASSIFIED
pattern = r'var QS_CLASSIFIED\s*=\s*\[.*?\];'
replacement = f'var QS_CLASSIFIED = {json.dumps(qs_data)};'
html_content = re.sub(pattern, replacement, html_content, flags=re.DOTALL)

# Idem pour SQR_DATA et les autres arrays
```

### 5.3 Mettre à jour les KPIs codés en dur

Rechercher et remplacer les valeurs de KPIs dans le HTML statique (onglets Glossaire et Introduction) :
- Volume total de keywords prioritaires
- Nombre de mots-clés dans chaque territoire
- Période affichée

---

## ÉTAPE 6 — VALIDATION

Avant de livrer, vérifier :

### Onglet 1 — Introduction & Glossary
- [ ] Titre et sous-titre corrects (marque + période)
- [ ] Chips à jour (keywords count, période, KPIs)
- [ ] Formules Coverage affichées correctement

### Onglet 2 — OneSearch Dashboard
- [ ] KPI cards avec valeurs correctes + variations Q→Q
- [ ] Gauges SVG rendering (4 jauges circulaires)
- [ ] Donut charts (Clicks by Territory, Coverage by Channel, Conversions)
- [ ] Matrix/Bubble chart (hover tooltip fonctionne)
- [ ] SQR Only Keywords table visible

### Onglet 3 — Territory Deep Dive
- [ ] 5-7 territoires présents
- [ ] Performance Tables avec variations ▲/▼ correctes
- [ ] Top 5 Keywords chips visibles
- [ ] Sections SEO/SEM Analysis renseignées

### Onglet 4 — One Search Recommendations
- [ ] 3 niveaux de priorité présents (Immediate / Short Term / Medium Term)
- [ ] Chaque reco avec contexte, problème, SEO Action, SEM Action, gain estimé

### Onglet 5 — Quality Score
- [ ] KPI cards calculées depuis QS_CLASSIFIED
- [ ] Distribution chart (barres QS 1-10) correctement rendu
- [ ] LP Experience distribution visible
- [ ] Table filtrable et paginée fonctionnelle (filtres Topic, Category, Status, QS range)
- [ ] Recherche full-text opérationnelle

### Onglet 6 — SQR
- [ ] Table avec toutes les colonnes (Query, Match, Campaign, Impr, Clicks, CPC, Cost, Conv, CPA)
- [ ] Variations Current vs Previous affichées
- [ ] Filtres (Campagne, AdGroup, Match Type, Status) fonctionnels
- [ ] Tri par colonne opérationnel
- [ ] Pagination correcte

---

## STRUCTURE HTML — RÉFÉRENCE RAPIDE

### Navigation (6 onglets)

```html
<nav class="tab-nav">
  <button class="tab-btn active" onclick="switchTab('glossaire', this)">Introduction & Glossary</button>
  <button class="tab-btn" onclick="switchTab('onesearch', this)">OneSearch Dashboard</button>
  <button class="tab-btn" onclick="switchTab('territory', this)">Territory Deep Dive</button>
  <button class="tab-btn" onclick="switchTab('recos', this)">One Search Recommendations</button>
  <button class="tab-btn" onclick="switchTab('qualityscore', this)">Quality Score</button>
  <button class="tab-btn" onclick="switchTab('sqr', this)">SQR</button>
</nav>
```

### Panneaux

```html
<div id="panel-glossaire" class="tab-panel active"> ... </div>
<div id="panel-onesearch" class="tab-panel"> ... </div>
<div id="panel-territory" class="tab-panel"> ... </div>
<div id="panel-recos" class="tab-panel"> ... </div>
<div id="panel-qualityscore" class="tab-panel"> ... </div>
<div id="panel-sqr" class="tab-panel"> ... </div>
```

### Palette CSS — Variables

```css
:root {
  --brand: #B8001C;        /* Rouge Danone (adapter par marque) */
  --green: #16A34A;
  --orange: #EA580C;
  --blue: #1D4ED8;
  --gray: #6B7280;
  --bg: #F9FAFB;
  --card: #FFFFFF;
  --border: #E5E7EB;
  --text: #111827;
  --text-light: #6B7280;
}
```

### Composants graphiques

**Gauge SVG (4 jauges OneSearch Dashboard) :**
```javascript
function renderGauge(containerId, value, maxValue, label, variation) {
  const pct = value / maxValue;
  const angle = pct * 180 - 90;
  // SVG avec arc strokeDasharray calculé dynamiquement
}
```

**Donut Chart :**
```javascript
function renderDonut(canvasId, data, colors) {
  // Canvas 2D — arc() pour chaque segment
  // Labels positionnés radialement
}
```

**Matrix Bubble Chart :**
```javascript
function renderMatrix(canvasId, territories) {
  // Axes : SEO Clicks (X) vs SEM Clicks (Y)
  // Radius = sqrt(conversions) × scale
  // Colors par territoire
  // Quadrants avec annotations texte
  // Tooltip on mousemove
}
```

---

## FICHIERS DE SORTIE

| Fichier | Chemin |
|---------|--------|
| Dashboard HTML | `/Users/thomasjoachim/Documents/One Search Danone/dashboard_onesearch_<MARQUE>_V8.html` |
| Données JS (intermédiaire) | `/Users/thomasjoachim/Documents/One Search Danone/data_<marque>_<periode>.js` |

---

## NOTES D'IMPLÉMENTATION

- **Auto-contenu** : Pas de dépendances externes (pas de CDN, pas de fetch). Toutes les données et le code sont inline dans le HTML.
- **Google Fonts Poppins** : La seule dépendance externe est la font Poppins — acceptable car le dashboard est ouvert dans un navigateur.
- **Taille fichier** : Le HTML final fait 5-8 MB selon le volume de données SQR. C'est normal.
- **Pas de frameworks JS** : Vanilla JS pur — pas de React, Vue, D3. Garder cette contrainte.
- **Données SQR** : Peuvent représenter 10 000+ lignes — pagination côté client (100 rows/page) est obligatoire.
- **Périodes** : Les labels "Q1 2026" et "Q4 2025" doivent être cohérents partout dans le fichier.

## RAPPEL FINAL

Le livrable est un **fichier HTML unique self-contained**. Le destinataire l'ouvre dans un navigateur sans aucune dépendance serveur. C'est à la fois sa force (portabilité totale) et sa contrainte (tout doit être inline).
