#!/usr/bin/env python3
"""
AXK Network — five-year synthetic operating record (Sep 2021 → Sep 2026)

Produces internally consistent, cross-referenced records for six Frappe DocTypes:
  Cooperative  →  Harvest Record  →  Lot  →  Verification Event  →  AXK Order  →  Escrow Contract

Everything is deterministic (fixed seed). Re-running produces identical output.
Field names are defined ONCE in FIELDS below; align them with your DocType JSONs.

Design notes
- Corridors: Rwanda–DRC (Rubavu→Goma, Rusizi→Bukavu), Rwanda–Uganda (Gatuna/Katuna, Cyanika),
  occasional Rwanda–Tanzania (Rusumo) and domestic Kigali (Kimironko) sales as a baseline.
- Seasonality: Rwanda Season A harvest Jan–Feb, Season B harvest Jun–Jul, Season C (marshland) Sep.
- Prices: RWF/kg base (2021) × annual inflation index × seasonal factor × grade factor.
- Anchoring: records before 2024-06 are "offchain" (paper/PDF ledger); from 2024-06 Xahau.
- Verification events form a per-lot SHA-256 hash chain (prev_hash → event_hash).
- Order.completion_time_hours and Order.baseline_recall_hours are the capstone outcome variables.
"""

import csv, json, hashlib, random, os
from datetime import date, datetime, timedelta

SEED = 20260929
random.seed(SEED)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)

START = date(2021, 9, 1)
END = date(2026, 9, 28)
END_DT = datetime(2026, 9, 28, 18, 0, 0)
AGG_END = END - timedelta(days=70)   # leave room for the downstream trade lifecycle

# --------------------------------------------------------------------------------------
# FIELD MAP — change values here to match your DocType fieldnames. Keys are internal.
# --------------------------------------------------------------------------------------
FIELDS = {
    "Cooperative": [
        "coop_id", "cooperative_name", "short_code", "registration_no", "rca_registration_date",
        "province", "district", "sector", "corridor", "primary_commodity", "secondary_commodity",
        "member_count", "female_member_pct", "founded_year", "chairperson", "qa_officer",
        "contact_phone", "momo_number", "momo_provider", "bank_name", "warehouse_capacity_tonnes",
        "gps_lat", "gps_lng", "wallet_chain", "wallet_address", "status", "onboarded_at", "notes",
    ],
    "Harvest Record": [
        "harvest_id", "cooperative", "farmer_name", "farmer_member_no", "farmer_gender",
        "commodity", "variety", "season", "harvest_date", "plot_size_ha", "quantity_kg",
        "moisture_pct_at_intake", "intake_date", "storage_location", "recorded_by",
        "record_source", "content_hash", "notes",
    ],
    "Lot": [
        "lot_id", "cooperative", "commodity", "variety", "grade", "quantity_kg", "bag_count",
        "bag_size_kg", "moisture_pct", "foreign_matter_pct", "aggregation_date",
        "origin_district", "warehouse", "harvest_record_ids", "harvest_record_count",
        "unit_price_rwf", "indicative_value_rwf", "status", "content_hash",
        "anchor_chain", "anchor_tx_hash", "anchor_ledger_index", "anchored_at", "notes",
    ],
    "Verification Event": [
        "event_id", "lot", "sequence_no", "event_type", "timestamp", "verifier_name",
        "verifier_org", "verifier_role", "location", "gps_lat", "gps_lng",
        "quantity_kg_measured", "moisture_pct", "grade_assigned", "result", "device_id",
        "evidence_type", "evidence_hash", "prev_hash", "event_hash",
        "anchor_chain", "anchor_tx_hash", "anchor_ledger_index", "notes",
    ],
    "AXK Order": [
        "order_id", "lot", "cooperative", "buyer_name", "buyer_country", "buyer_city",
        "buyer_type", "corridor", "border_post", "commodity", "grade", "quantity_kg",
        "unit_price", "currency", "total_amount", "fx_rate_usd", "total_usd",
        "order_date", "confirmed_at", "dispatch_date", "delivered_at", "settled_at",
        "status", "settlement_channel", "escrow_contract", "completion_time_hours",
        "baseline_recall_hours", "trust_score_pre", "trust_score_post", "dispute_flag",
        "cancellation_reason", "notes",
    ],
    "Escrow Contract": [
        "escrow_id", "order", "lot", "cooperative", "buyer_name", "amount", "currency",
        "amount_usd", "chain", "network", "escrow_account", "release_condition",
        "condition_event_type", "created_at", "funded_at", "fund_tx_hash", "fund_ledger_index",
        "released_at", "release_tx_hash", "release_ledger_index", "refunded_at",
        "refund_tx_hash", "status", "fee_amount", "fee_currency", "dispute_reason",
        "dispute_opened_at", "dispute_resolved_at", "arbiter", "notes",
    ],
}

# --------------------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------------------
INFLATION = {2021: 1.00, 2022: 1.21, 2023: 1.43, 2024: 1.49, 2025: 1.56, 2026: 1.63}
FX_USD_RWF = {2021: 1010, 2022: 1060, 2023: 1180, 2024: 1310, 2025: 1410, 2026: 1450}
FX_USD_CDF = {2021: 2000, 2022: 2050, 2023: 2450, 2024: 2820, 2025: 2870, 2026: 2900}
FX_USD_UGX = {2021: 3560, 2022: 3700, 2023: 3740, 2024: 3780, 2025: 3650, 2026: 3620}
FX_USD_TZS = {2021: 2300, 2022: 2320, 2023: 2450, 2024: 2620, 2025: 2650, 2026: 2600}

COMMODITIES = {
    # base RWF/kg (2021), seasonal months of harvest, varieties, bag size, moisture max %
    "Maize (dry grain)":        dict(base=290, harvest=[1, 2, 6, 7], bag=50, moist=13.5,
                                     var=["RHM 104", "SC 403", "Pool 9A", "PAN 53", "ZM 607"]),
    "Beans (dry)":              dict(base=680, harvest=[1, 2, 6, 7], bag=50, moist=14.0,
                                     var=["RWR 2245", "MAC 44", "Gasilida", "RWV 1348", "Ngwinurare"]),
    "Irish Potato":             dict(base=230, harvest=[1, 2, 3, 6, 7, 8, 9], bag=100, moist=0,
                                     var=["Kinigi", "Kirundo", "Cruza", "Victoria", "Sangema"]),
    "Coffee (parchment)":       dict(base=2300, harvest=[3, 4, 5, 6], bag=60, moist=11.5,
                                     var=["Bourbon Mayaguez 139", "Jackson 2/1257", "BM 71", "Pop 3303/21"]),
    "Cassava (dried chips)":    dict(base=210, harvest=[2, 3, 7, 8, 9, 10], bag=50, moist=12.0,
                                     var=["NASE 14", "Mbakungahaze", "Seruruseke", "Garukunsubire"]),
    "Sorghum":                  dict(base=360, harvest=[6, 7], bag=50, moist=13.0,
                                     var=["Ikinyaruka", "SRN 39", "Gambella 1107"]),
    "Soybean":                  dict(base=610, harvest=[1, 2, 6, 7], bag=50, moist=12.5,
                                     var=["SB 24", "Peka 6", "Yezumutima", "SB 19"]),
    "Rice (paddy)":             dict(base=370, harvest=[1, 2, 6, 7], bag=50, moist=14.0,
                                     var=["WAT 54-11", "Kigori", "Ndamirabana", "Basmati 370"]),
    "Wheat":                    dict(base=410, harvest=[2, 3, 7, 8], bag=50, moist=13.0,
                                     var=["Kenya Ibis", "Nyaruguru", "Musama 11"]),
}
GRADES = {"A": 1.00, "B": 0.90, "C": 0.78}
GRADE_W = [0.42, 0.44, 0.14]

PROVINCES = {
    "Northern":  {"Musanze": ["Kinigi", "Muhoza", "Cyuve", "Busogo", "Gataraga"],
                  "Burera": ["Cyanika", "Butaro", "Rugarama", "Kinoni"],
                  "Gicumbi": ["Byumba", "Rukomo", "Kaniga", "Mukarange"],
                  "Gakenke": ["Gakenke", "Nemba", "Ruli", "Coko"]},
    "Western":   {"Rubavu": ["Gisenyi", "Rubavu", "Nyamyumba", "Busasamana"],
                  "Rusizi": ["Kamembe", "Gihundwe", "Bugarama", "Nzahaha"],
                  "Nyabihu": ["Mukamira", "Jenda", "Bigogwe", "Karago"],
                  "Karongi": ["Bwishyura", "Rubengera", "Rugabano"]},
    "Eastern":   {"Nyagatare": ["Rwimiyaga", "Karangazi", "Nyagatare", "Matimba"],
                  "Kirehe": ["Nasho", "Mahama", "Mpanga", "Kigina"],
                  "Bugesera": ["Ntarama", "Nyamata", "Rilima", "Mayange"],
                  "Kayonza": ["Mukarange", "Ndego", "Rwinkwavu"]},
    "Southern":  {"Huye": ["Ngoma", "Tumba", "Ruhashya", "Maraba"],
                  "Nyanza": ["Busasamana", "Rwabicuma", "Ntyazo"],
                  "Muhanga": ["Nyamabuye", "Shyogwe", "Rongi"]},
    "Kigali":    {"Gasabo": ["Kimironko", "Remera", "Rusororo"],
                  "Kicukiro": ["Gatenga", "Nyarugunga"]},
}
DISTRICT_GPS = {
    "Musanze": (-1.4996, 29.6350), "Burera": (-1.4527, 29.8660), "Gicumbi": (-1.5768, 30.0670),
    "Gakenke": (-1.6849, 29.7900), "Rubavu": (-1.6935, 29.2586), "Rusizi": (-2.4849, 28.9075),
    "Nyabihu": (-1.6537, 29.5069), "Karongi": (-2.0592, 29.3476), "Nyagatare": (-1.2977, 30.3253),
    "Kirehe": (-2.2227, 30.7157), "Bugesera": (-2.1901, 30.1116), "Kayonza": (-1.8829, 30.6236),
    "Huye": (-2.5964, 29.7395), "Nyanza": (-2.3520, 29.7409), "Muhanga": (-2.0857, 29.7529),
    "Gasabo": (-1.9302, 30.1091), "Kicukiro": (-1.9906, 30.0980),
}
DISTRICT_COMMODITY = {
    "Musanze": ["Irish Potato", "Maize (dry grain)", "Wheat"], "Burera": ["Irish Potato", "Beans (dry)", "Wheat"],
    "Gicumbi": ["Maize (dry grain)", "Beans (dry)", "Wheat"], "Gakenke": ["Coffee (parchment)", "Beans (dry)"],
    "Rubavu": ["Irish Potato", "Maize (dry grain)", "Beans (dry)"], "Rusizi": ["Coffee (parchment)", "Rice (paddy)", "Cassava (dried chips)"],
    "Nyabihu": ["Irish Potato", "Wheat", "Maize (dry grain)"], "Karongi": ["Coffee (parchment)", "Cassava (dried chips)"],
    "Nyagatare": ["Maize (dry grain)", "Rice (paddy)", "Soybean", "Sorghum"], "Kirehe": ["Maize (dry grain)", "Rice (paddy)", "Beans (dry)"],
    "Bugesera": ["Maize (dry grain)", "Cassava (dried chips)", "Sorghum"], "Kayonza": ["Maize (dry grain)", "Soybean", "Beans (dry)"],
    "Huye": ["Coffee (parchment)", "Cassava (dried chips)", "Rice (paddy)"], "Nyanza": ["Coffee (parchment)", "Cassava (dried chips)"],
    "Muhanga": ["Coffee (parchment)", "Maize (dry grain)", "Beans (dry)"],
    "Gasabo": ["Maize (dry grain)", "Beans (dry)"], "Kicukiro": ["Beans (dry)", "Maize (dry grain)"],
}
# corridor keyed by province/district geography
DISTRICT_CORRIDOR = {
    "Rubavu": "RW-DRC (Rubavu–Goma)", "Rusizi": "RW-DRC (Rusizi–Bukavu)", "Nyabihu": "RW-DRC (Rubavu–Goma)",
    "Karongi": "RW-DRC (Rusizi–Bukavu)", "Musanze": "RW-UG (Cyanika–Kisoro)", "Burera": "RW-UG (Cyanika–Kisoro)",
    "Gicumbi": "RW-UG (Gatuna–Katuna)", "Gakenke": "RW-UG (Gatuna–Katuna)", "Nyagatare": "RW-UG (Kagitumba–Mirama Hills)",
    "Kayonza": "RW-UG (Kagitumba–Mirama Hills)", "Kirehe": "RW-TZ (Rusumo)", "Bugesera": "RW-TZ (Rusumo)",
    "Huye": "RW-DRC (Rusizi–Bukavu)", "Nyanza": "RW-DRC (Rusizi–Bukavu)", "Muhanga": "RW-DRC (Rubavu–Goma)",
    "Gasabo": "Domestic (Kigali)", "Kicukiro": "Domestic (Kigali)",
}
BORDER_POST = {
    "RW-DRC (Rubavu–Goma)": ("Grande Barrière (Rubavu/Goma)", "DGDA Goma", "CD", "CDF", "Goma"),
    "RW-DRC (Rusizi–Bukavu)": ("Rusizi I (Kamembe/Bukavu)", "DGDA Bukavu", "CD", "CDF", "Bukavu"),
    "RW-UG (Cyanika–Kisoro)": ("Cyanika OSBP", "URA Cyanika", "UG", "UGX", "Kisoro"),
    "RW-UG (Gatuna–Katuna)": ("Gatuna/Katuna OSBP", "URA Katuna", "UG", "UGX", "Kabale"),
    "RW-UG (Kagitumba–Mirama Hills)": ("Kagitumba/Mirama Hills OSBP", "URA Mirama Hills", "UG", "UGX", "Mbarara"),
    "RW-TZ (Rusumo)": ("Rusumo OSBP", "TRA Rusumo", "TZ", "TZS", "Mwanza"),
    "Domestic (Kigali)": ("Kimironko Market gate", "Kigali City", "RW", "RWF", "Kigali"),
}
CITY_GPS = {"Goma": (-1.6792, 29.2228), "Bukavu": (-2.5083, 28.8608), "Kisoro": (-1.2855, 29.6851),
            "Kabale": (-1.2489, 29.9899), "Mbarara": (-0.6072, 30.6545), "Jinja": (0.4244, 33.2041), "Kampala": (0.3476, 32.5825),
            "Bushenyi": (-0.5425, 30.1861), "Rubanda": (-1.2213, 29.8433), "Mwanza": (-2.5164, 32.9175), "Bukoba": (-1.3317, 31.8120),
            "Kigali": (-1.9441, 30.0619)}
BUYERS = {
    "CD": [("Ets. Mwangachuchu Frères", "Goma", "Wholesaler"), ("Société Kivu Grains SARL", "Goma", "Processor"),
           ("Depot Bahati Alimentation", "Goma", "Wholesaler"), ("Ets. Kahindo & Fils", "Goma", "Retail chain"),
           ("Bukavu Agri-Négoce SARL", "Bukavu", "Wholesaler"), ("Maison Furaha Vivres", "Bukavu", "Wholesaler"),
           ("Coopérative COOPADEC", "Bukavu", "Cooperative buyer"), ("Ets. Amani Wa Mungu", "Goma", "Wholesaler"),
           ("Kivu Fresh Import-Export", "Goma", "Importer"), ("Ets. Zawadi Commerce Général", "Bukavu", "Wholesaler"),
           ("Minoterie du Kivu", "Goma", "Processor"), ("Ets. Baraka Food Supply", "Goma", "Institutional supplier")],
    "UG": [("Kisoro Fresh Produce Ltd", "Kisoro", "Wholesaler"), ("Kabale Grain Traders Ltd", "Kabale", "Wholesaler"),
           ("Mbarara Agro Millers Ltd", "Mbarara", "Processor"), ("Nile Breweries (contract sorghum)", "Jinja", "Processor"),
           ("Kampala Cereal Merchants Ltd", "Kampala", "Wholesaler"), ("Ankole Coffee Producers CU", "Bushenyi", "Cooperative buyer"),
           ("Owino Market Consortium", "Kampala", "Wholesaler"), ("Kigezi Highland Foods", "Kabale", "Processor"),
           ("Great Lakes Agri Supplies", "Mbarara", "Wholesaler"), ("Rubanda Potato Traders Assoc.", "Rubanda", "Association buyer")],
    "TZ": [("Mwanza Grain Depot Co.", "Mwanza", "Wholesaler"), ("Kagera Farmers Supply Ltd", "Bukoba", "Wholesaler"),
           ("Lake Zone Millers", "Mwanza", "Processor")],
    "RW": [("Kimironko Market Aggregators", "Kigali", "Wholesaler"), ("Minimex Ltd", "Kigali", "Processor"),
           ("Africa Improved Foods", "Kigali", "Processor"), ("Sina Gerard Enterprise", "Kigali", "Processor"),
           ("Bralirwa (contract grain)", "Kigali", "Processor"), ("Kigali Wholesale Traders", "Kigali", "Wholesaler"),
           ("Rwanda Grains & Cereals Corp.", "Kigali", "Institutional supplier")],
}
COOP_NAMES = [
    "Koperative Twitezimbere", "Koperative Abahuzamugambi", "Koperative Dukundane", "Koperative Twisungane",
    "Koperative Abishyizehamwe", "Koperative Ejo Heza", "Koperative Terimbere", "Koperative Duterimbere",
    "Koperative Abadahigwa", "Koperative Icyerekezo", "Koperative Tuzamurane", "Koperative Abakundana",
    "Koperative Ihuriro", "Koperative Girubukire", "Koperative Kundumurimo", "Koperative Turwanyubukene",
    "Koperative Abizeranye", "Koperative Indatwa", "Koperative Umucyo", "Koperative Inganzo",
    "Koperative Ubumwe", "Koperative Imbaraga", "Koperative Kotemu", "Koperative Coopac",
    "Koperative Abahujumugambi", "Koperative Tubungabunge", "Koperative Dufatanye", "Koperative Amizero",
    "Koperative Iterambere", "Koperative Girumurimo", "Koperative Abateraninkunga", "Koperative Twiyubake",
    "Koperative Kopakama", "Koperative Sholi", "Koperative Coopaviba", "Koperative Kobacyamu",
    "Koperative Impuzamashyirahamwe", "Koperative Abakoranabushake", "Koperative Tuzamure", "Koperative Ineza",
    "Koperative Duhuzimbaraga", "Koperative Abishyizehamwe ba Nasho",
]
FIRST_M = ["Jean Bosco", "Emmanuel", "Théogène", "Innocent", "Vincent", "Fidèle", "Jean de Dieu", "Célestin",
           "Eric", "Aimable", "Jean Paul", "Samuel", "Damascène", "Faustin", "Pascal", "Olivier", "Claude", "Gaspard"]
FIRST_F = ["Marie Claire", "Josiane", "Alphonsine", "Jeanne", "Vestine", "Immaculée", "Béatrice", "Claudine",
           "Espérance", "Dative", "Solange", "Chantal", "Clémentine", "Divine", "Odette", "Uwase", "Ange", "Liliane"]
LAST = ["Uwimana", "Mukamana", "Niyonzima", "Habimana", "Nsengiyumva", "Mugisha", "Uwase", "Ndayishimiye",
        "Hakizimana", "Nyirahabimana", "Bizimana", "Mukeshimana", "Ntawukuriryayo", "Iradukunda", "Tuyisenge",
        "Ingabire", "Nshimiyimana", "Umutoni", "Rukundo", "Mutesi", "Kamanzi", "Nyiraneza", "Uwizeyimana",
        "Ishimwe", "Nizeyimana", "Mukashyaka", "Karangwa", "Uwamahoro", "Ndahiro", "Muhire"]
VERIFIER_ORGS = {
    "cooperative_intake": ("Cooperative QA desk", "Cooperative QA officer"),
    "moisture_test": ("Cooperative QA desk", "Grain quality technician"),
    "weighbridge": ("District weighbridge", "Weighbridge operator"),
    "quality_grading": ("RAB / RSB inspector", "Quality inspector"),
    "warehouse_receipt": ("Warehouse operator", "Warehouse clerk"),
    "phytosanitary_certificate": ("RAB Plant Health", "Phytosanitary inspector"),
    "certificate_of_origin": ("Rwanda Revenue Authority", "Customs officer"),
    "border_exit": ("Rwanda Revenue Authority", "Customs officer"),
    "border_entry": (None, "Customs officer"),          # filled per corridor
    "buyer_receipt": (None, "Buyer receiving clerk"),   # buyer name
    "dispute_inspection": ("Independent surveyor", "Surveyor"),
}
SETTLEMENT_BY_YEAR = {
    2021: [("Cash on delivery", 0.55), ("Bank transfer (SWIFT/USD)", 0.25), ("MTN MoMo", 0.15), ("Airtel Money", 0.05)],
    2022: [("Cash on delivery", 0.48), ("Bank transfer (SWIFT/USD)", 0.24), ("MTN MoMo", 0.20), ("Airtel Money", 0.08)],
    2023: [("Cash on delivery", 0.38), ("Bank transfer (SWIFT/USD)", 0.20), ("MTN MoMo", 0.28), ("Airtel Money", 0.09), ("PAPSS", 0.05)],
    2024: [("Cash on delivery", 0.22), ("Bank transfer (SWIFT/USD)", 0.14), ("MTN MoMo", 0.30), ("Airtel Money", 0.08), ("PAPSS", 0.06), ("AXK escrow (XAH)", 0.20)],
    2025: [("Cash on delivery", 0.10), ("Bank transfer (SWIFT/USD)", 0.08), ("MTN MoMo", 0.22), ("Airtel Money", 0.06), ("PAPSS", 0.06), ("AXK escrow (XAH)", 0.48)],
    2026: [("Cash on delivery", 0.05), ("Bank transfer (SWIFT/USD)", 0.05), ("MTN MoMo", 0.16), ("Airtel Money", 0.04), ("PAPSS", 0.06), ("AXK escrow (XAH)", 0.58), ("AXK escrow (Stellar USDC, testnet)", 0.06)],
}
YEAR_WEIGHT = {2021: 0.05, 2022: 0.11, 2023: 0.17, 2024: 0.24, 2025: 0.28, 2026: 0.15}

# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def canon(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)

def wchoice(pairs):
    items, weights = zip(*pairs)
    return random.choices(items, weights=weights, k=1)[0]

def rand_date(y, months):
    m = random.choice(months)
    d = date(y, m, min(28, random.randint(1, 28)))
    return d

def ts(d: date, h=None):
    h = random.randint(7, 17) if h is None else h
    return datetime(d.year, d.month, d.day, h, random.randint(0, 59), random.randint(0, 59))

def fmt_dt(x): return x.strftime("%Y-%m-%d %H:%M:%S")
def fmt_d(x): return x.strftime("%Y-%m-%d")

def xah_tx(): return "".join(random.choice("0123456789ABCDEF") for _ in range(64))
def xah_acct(): return "r" + "".join(random.choice("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz") for _ in range(33))
def stellar_tx(): return "".join(random.choice("0123456789abcdef") for _ in range(64))
def stellar_acct(): return "G" + "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(55))
def stellar_contract(): return "C" + "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(55))

LEDGER_BASE = {"xahau": 9_800_000}
def ledger_index(chain, when: datetime):
    # Xahau ~ 3.5s per ledger; anchor genesis for our purposes at 2024-06-01
    origin = datetime(2024, 6, 1)
    return LEDGER_BASE["xahau"] + int((when - origin).total_seconds() / 3.5)

def phone_rw(): return f"+2507{random.choice('2389')}{random.randint(1000000, 9999999)}"
def person(gender=None):
    g = gender or random.choice(["F", "M", "M"])
    return (random.choice(FIRST_F if g == "F" else FIRST_M) + " " + random.choice(LAST)), g

def price_per_kg(commodity, when: date, grade):
    c = COMMODITIES[commodity]
    base = c["base"] * INFLATION[when.year]
    # seasonal: cheapest right after harvest, +25% in lean months
    months_from_harvest = min((when.month - m) % 12 for m in c["harvest"])
    seasonal = 1.0 + 0.25 * (months_from_harvest / 6.0)
    noise = random.uniform(0.94, 1.06)
    return round(base * seasonal * GRADES[grade] * noise)

def year_for_index(i, n):
    # deterministic distribution of records across years by YEAR_WEIGHT
    return random.choices(list(YEAR_WEIGHT.keys()), weights=list(YEAR_WEIGHT.values()), k=1)[0]

def clamp_date(d):
    return max(START, min(END, d))

# --------------------------------------------------------------------------------------
# 1. Cooperatives
# --------------------------------------------------------------------------------------
coops = []
district_pool = [(p, d) for p, ds in PROVINCES.items() for d in ds]
for i, name in enumerate(COOP_NAMES):
    prov, dist = district_pool[i % len(district_pool)]
    sector = random.choice(PROVINCES[prov][dist])
    comms = DISTRICT_COMMODITY[dist]
    primary = comms[0] if random.random() < 0.6 else random.choice(comms)
    secondary = random.choice([c for c in comms if c != primary])
    founded = random.randint(2006, 2019)
    onboard_year = wchoice([(2021, 0.25), (2022, 0.25), (2023, 0.25), (2024, 0.15), (2025, 0.10)])
    onboard = clamp_date(date(onboard_year, random.randint(1, 12), random.randint(1, 28)))
    lat, lng = DISTRICT_GPS[dist]
    chair, _ = person()
    qa, _ = person()
    short = "".join(w[0] for w in name.split()[1:]).upper() + dist[:3].upper()
    wallet_chain = "xahau" if onboard < date(2026, 6, 1) else "stellar-testnet"
    coops.append({
        "coop_id": f"COOP-{i+1:03d}",
        "cooperative_name": f"{name} {dist}",
        "short_code": short,
        "registration_no": f"RCA/{random.randint(100, 999)}/{founded}",
        "rca_registration_date": fmt_d(date(founded, random.randint(1, 12), random.randint(1, 28))),
        "province": prov, "district": dist, "sector": sector,
        "corridor": DISTRICT_CORRIDOR[dist],
        "primary_commodity": primary, "secondary_commodity": secondary,
        "member_count": random.randint(85, 1450),
        "female_member_pct": round(random.uniform(38, 64), 1),
        "founded_year": founded,
        "chairperson": chair, "qa_officer": qa,
        "contact_phone": phone_rw(), "momo_number": phone_rw(),
        "momo_provider": random.choice(["MTN MoMo", "MTN MoMo", "Airtel Money"]),
        "bank_name": random.choice(["Bank of Kigali", "Equity Bank Rwanda", "BPR Bank", "Urwego Bank", "I&M Bank Rwanda", "SACCO (Umurenge)"]),
        "warehouse_capacity_tonnes": random.choice([40, 60, 80, 120, 150, 200, 300, 500]),
        "gps_lat": round(lat + random.uniform(-0.04, 0.04), 5),
        "gps_lng": round(lng + random.uniform(-0.04, 0.04), 5),
        "wallet_chain": wallet_chain,
        "wallet_address": xah_acct() if wallet_chain == "xahau" else stellar_acct(),
        "status": wchoice([("Active", 0.86), ("Dormant", 0.09), ("Suspended", 0.05)]),
        "onboarded_at": fmt_d(onboard),
        "notes": random.choice([
            "Uses Post-Harvest Handling and Storage (PHHS) drying floor; hermetic bags since 2023.",
            "Aggregation point shared with two neighbouring cooperatives; weighbridge 6 km away.",
            "Member of Rwanda Cooperative Agency federation; audited annually.",
            "Has RAB-certified drying and shelling equipment; sells to WFP P4P when tendered.",
            "Operates a warehouse receipt arrangement with a district SACCO.",
            "Seasonal cash-flow stress reported before Season A; relies on early sales to border traders.",
            "",
        ]),
    })
coop_by_id = {c["coop_id"]: c for c in coops}

# --------------------------------------------------------------------------------------
# 2. Harvest Records
# --------------------------------------------------------------------------------------
harvests = []
N_HARVEST = 3400
members = {}  # coop -> list of (name, gender, member_no)
for c in coops:
    members[c["coop_id"]] = []
    for k in range(random.randint(25, 60)):
        nm, g = person()
        members[c["coop_id"]].append((nm, g, f"{c['short_code']}-M{k+1:04d}"))

for i in range(N_HARVEST):
    c = random.choice(coops)
    y = year_for_index(i, N_HARVEST)
    onboard = datetime.strptime(c["onboarded_at"], "%Y-%m-%d").date()
    commodity = c["primary_commodity"] if random.random() < 0.72 else c["secondary_commodity"]
    spec = COMMODITIES[commodity]
    hd = clamp_date(rand_date(y, spec["harvest"]))
    if hd < START:
        hd = START + timedelta(days=random.randint(0, 120))
    season = "A" if hd.month in (1, 2, 3) else ("B" if hd.month in (5, 6, 7, 8) else "C")
    farmer, g, mno = random.choice(members[c["coop_id"]])
    plot = round(random.choice([0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0, 1.2, 1.5, 2.0]) * random.uniform(0.9, 1.1), 2)
    yield_kg_ha = {"Maize (dry grain)": 2600, "Beans (dry)": 1200, "Irish Potato": 11000, "Coffee (parchment)": 900,
                   "Cassava (dried chips)": 4500, "Sorghum": 1400, "Soybean": 1300, "Rice (paddy)": 4800, "Wheat": 2200}[commodity]
    qty = round(plot * yield_kg_ha * random.uniform(0.55, 1.15))
    moist_max = spec["moist"]
    moist = 0 if moist_max == 0 else round(random.uniform(moist_max - 1.5, moist_max + 6.0), 1)
    intake = hd + timedelta(days=random.randint(1, 12))
    src = "Paper ledger (digitised)" if intake < onboard or intake < date(2023, 6, 1) else wchoice([("AXK mobile app", 0.7), ("USSD entry", 0.2), ("Paper ledger (digitised)", 0.1)])
    rec = {
        "harvest_id": f"HR-{hd.year}-{i+1:05d}",
        "cooperative": c["coop_id"],
        "farmer_name": farmer, "farmer_member_no": mno, "farmer_gender": g,
        "commodity": commodity, "variety": random.choice(spec["var"]),
        "season": f"{hd.year}{season}",
        "harvest_date": fmt_d(hd),
        "plot_size_ha": plot, "quantity_kg": qty,
        "moisture_pct_at_intake": moist,
        "intake_date": fmt_d(intake),
        "storage_location": f"{c['short_code']} Store {random.choice('ABC')}, {c['sector']}",
        "recorded_by": c["qa_officer"],
        "record_source": src,
        "notes": random.choice(["", "", "", "Delivered in woven PP bags; re-dried on floor 2 days.",
                                "Farmer requested advance against delivery.", "Partial delivery; balance expected next week.",
                                "Rain during transport; moisture re-checked at intake.", "PICS hermetic bags used."]),
    }
    rec["content_hash"] = sha(canon({k: rec[k] for k in ("harvest_id", "cooperative", "farmer_member_no", "commodity", "harvest_date", "quantity_kg", "moisture_pct_at_intake")}))
    harvests.append(rec)
harvests.sort(key=lambda r: r["harvest_date"])

# --------------------------------------------------------------------------------------
# 3. Lots (aggregate 2–9 harvest records of the same coop + commodity)
# --------------------------------------------------------------------------------------
lots = []
by_key = {}
for h in harvests:
    by_key.setdefault((h["cooperative"], h["commodity"]), []).append(h)

lot_counter = 0
lot_year_counts = {}
for key, recs in by_key.items():
    recs.sort(key=lambda r: r["intake_date"])
    idx = 0
    while idx < len(recs):
        n = random.randint(2, 9)
        chunk = recs[idx: idx + n]
        idx += n
        if len(chunk) < 2 and random.random() < 0.5:
            continue  # small leftover, left un-lotted (realistic)
        c = coop_by_id[key[0]]
        commodity = key[1]
        spec = COMMODITIES[commodity]
        last_intake = datetime.strptime(chunk[-1]["intake_date"], "%Y-%m-%d").date()
        agg = max(START, min(AGG_END, last_intake + timedelta(days=random.randint(2, 21))))
        qty = sum(r["quantity_kg"] for r in chunk)
        moist_vals = [r["moisture_pct_at_intake"] for r in chunk if r["moisture_pct_at_intake"]]
        moist = round(sum(moist_vals) / len(moist_vals) - random.uniform(0.5, 3.0), 1) if moist_vals else 0
        moist = max(moist, spec["moist"] - 2.5) if spec["moist"] else 0
        grade = wchoice(list(zip(GRADES.keys(), GRADE_W)))
        if spec["moist"] and moist > spec["moist"] + 1.0:
            grade = "C" if grade != "C" else "C"
        fm = round(random.uniform(0.3, 3.5), 2)
        bag = spec["bag"]
        bags = qty // bag
        qty = bags * bag if bags > 0 else qty
        lot_counter += 1
        lot_year_counts[agg.year] = lot_year_counts.get(agg.year, 0) + 1
        lot_id = f"AXK-LOT-{agg.year}-{lot_year_counts[agg.year]:05d}"
        unit = price_per_kg(commodity, agg, grade)
        status = wchoice([("Closed", 0.58), ("Delivered", 0.09), ("In Transit", 0.05), ("Listed", 0.08),
                          ("Reserved", 0.05), ("Inspected", 0.05), ("Aggregated", 0.04), ("Rejected", 0.06)])
        if agg < date(2026, 3, 1):  # older lots should mostly be closed
            status = wchoice([("Closed", 0.84), ("Rejected", 0.07), ("Delivered", 0.05), ("Listed", 0.04)])
        anchored = agg >= date(2024, 6, 1)
        anchored_at = min(END_DT, ts(agg + timedelta(days=random.randint(0, 2)))) if anchored else None
        lot = {
            "lot_id": lot_id,
            "cooperative": c["coop_id"], "commodity": commodity,
            "variety": chunk[0]["variety"], "grade": grade,
            "quantity_kg": qty, "bag_count": bags, "bag_size_kg": bag,
            "moisture_pct": moist, "foreign_matter_pct": fm,
            "aggregation_date": fmt_d(agg),
            "origin_district": c["district"],
            "warehouse": f"{c['short_code']} Central Store, {c['sector']} sector",
            "harvest_record_ids": ";".join(r["harvest_id"] for r in chunk),
            "harvest_record_count": len(chunk),
            "unit_price_rwf": unit,
            "indicative_value_rwf": unit * qty,
            "status": status,
            "anchor_chain": "xahau" if anchored else "offchain",
            "anchor_tx_hash": xah_tx() if anchored else "",
            "anchor_ledger_index": ledger_index("xahau", anchored_at) if anchored else "",
            "anchored_at": fmt_dt(anchored_at) if anchored else "",
            "notes": "",
        }
        lot["content_hash"] = sha(canon({k: lot[k] for k in ("lot_id", "cooperative", "commodity", "grade", "quantity_kg", "moisture_pct", "aggregation_date", "harvest_record_ids")}))
        lots.append(lot)
lots.sort(key=lambda l: l["aggregation_date"])
lot_by_id = {l["lot_id"]: l for l in lots}

# --------------------------------------------------------------------------------------
# 4. Verification Events (hash-chained per lot) — created alongside orders below
#    and 5. AXK Orders   6. Escrow Contracts
# --------------------------------------------------------------------------------------
events, orders, escrows = [], [], []
ev_counter = 0
order_year_counts, esc_year_counts = {}, {}

def add_event(lot, seq, etype, when: datetime, org, role, loc, lat, lng, qty, moist, grade, result, prev, notes=""):
    global ev_counter
    ev_counter += 1
    anchored = when.date() >= date(2024, 6, 1)
    payload = {"lot": lot["lot_id"], "seq": seq, "type": etype, "ts": fmt_dt(when), "org": org, "loc": loc,
               "qty": qty, "moist": moist, "grade": grade, "result": result}
    evidence_hash = sha(f"evidence:{lot['lot_id']}:{seq}:{etype}:{when.isoformat()}")
    ehash = sha(prev + canon(payload) + evidence_hash)
    vname, _ = person()
    ev = {
        "event_id": f"VE-{when.year}-{ev_counter:06d}",
        "lot": lot["lot_id"], "sequence_no": seq, "event_type": etype,
        "timestamp": fmt_dt(when),
        "verifier_name": vname, "verifier_org": org, "verifier_role": role,
        "location": loc, "gps_lat": round(lat + random.uniform(-0.01, 0.01), 5), "gps_lng": round(lng + random.uniform(-0.01, 0.01), 5),
        "quantity_kg_measured": qty, "moisture_pct": moist, "grade_assigned": grade, "result": result,
        "device_id": f"AXK-DEV-{random.randint(1000, 9999)}" if anchored else "",
        "evidence_type": random.choice(["Photo (geo-tagged)", "Photo (geo-tagged)", "Signed PDF", "Weighbridge ticket scan", "Moisture meter reading"]),
        "evidence_hash": evidence_hash, "prev_hash": prev, "event_hash": ehash,
        "anchor_chain": "xahau" if anchored else "offchain",
        "anchor_tx_hash": xah_tx() if anchored else "",
        "anchor_ledger_index": ledger_index("xahau", when) if anchored else "",
        "notes": notes,
    }
    events.append(ev)
    return ehash

GENESIS = "0" * 64
for lot in lots:
    c = coop_by_id[lot["cooperative"]]
    lat, lng = DISTRICT_GPS[c["district"]]
    agg = datetime.strptime(lot["aggregation_date"], "%Y-%m-%d").date()
    spec = COMMODITIES[lot["commodity"]]
    prev = GENESIS
    seq = 0
    t = ts(agg)

    # --- intake chain at cooperative
    seq += 1; prev = add_event(lot, seq, "cooperative_intake", t, "Cooperative QA desk", "Cooperative QA officer",
                               f"{c['sector']}, {c['district']}", lat, lng, lot["quantity_kg"] + random.randint(-40, 60),
                               lot["moisture_pct"] + round(random.uniform(0, 1.5), 1), "", "pass", prev)
    if spec["moist"]:
        t += timedelta(hours=random.randint(2, 30)); seq += 1
        m = lot["moisture_pct"]
        res = "pass" if m <= spec["moist"] else ("conditional" if m <= spec["moist"] + 1.5 else "fail")
        prev = add_event(lot, seq, "moisture_test", t, "Cooperative QA desk", "Grain quality technician",
                         f"{c['sector']}, {c['district']}", lat, lng, "", m, "", res, prev,
                         "" if res == "pass" else "Re-drying ordered before grading.")
    t += timedelta(hours=random.randint(6, 48)); seq += 1
    prev = add_event(lot, seq, "weighbridge", t, "District weighbridge", "Weighbridge operator",
                     f"{c['district']} weighbridge", lat, lng, lot["quantity_kg"] + random.randint(-25, 25), "", "", "pass", prev)
    t += timedelta(hours=random.randint(4, 72)); seq += 1
    grade_res = "fail" if lot["status"] == "Rejected" else "pass"
    prev = add_event(lot, seq, "quality_grading", t, random.choice(["RAB inspector", "RSB inspector", "Cooperative QA desk"]),
                     "Quality inspector", f"{c['sector']}, {c['district']}", lat, lng, "", lot["moisture_pct"], lot["grade"], grade_res, prev,
                     "" if grade_res == "pass" else random.choice(["Aflatoxin risk: visible mould in 3 of 12 sampled bags.",
                                                                    "Foreign matter above 3%; lot returned for re-cleaning.",
                                                                    "Moisture out of tolerance after re-drying; lot rejected."]))
    if lot["status"] == "Rejected" or lot["status"] in ("Aggregated", "Inspected"):
        continue
    t += timedelta(hours=random.randint(2, 24)); seq += 1
    prev = add_event(lot, seq, "warehouse_receipt", t, "Warehouse operator", "Warehouse clerk",
                     lot["warehouse"], lat, lng, lot["quantity_kg"], "", lot["grade"], "pass", prev)
    if lot["status"] == "Listed":
        continue

    # --- an order exists for Reserved / In Transit / Delivered / Closed lots
    corridor = c["corridor"]
    if random.random() < 0.12 and corridor != "Domestic (Kigali)":
        corridor = "Domestic (Kigali)"  # some lots sold locally
    post, entry_org, bcountry, bcur, bcity = BORDER_POST[corridor]
    bname, bcity2, btype = random.choice(BUYERS[bcountry])
    order_date = clamp_date(t.date() + timedelta(days=random.randint(0, 25)))
    y = order_date.year
    order_year_counts[y] = order_year_counts.get(y, 0) + 1
    order_id = f"AXK-ORD-{y}-{order_year_counts[y]:05d}"
    unit_rwf = price_per_kg(lot["commodity"], order_date, lot["grade"])
    fx_rwf = FX_USD_RWF[y] * random.uniform(0.985, 1.015)
    fx_map = {"RWF": FX_USD_RWF, "CDF": FX_USD_CDF, "UGX": FX_USD_UGX, "TZS": FX_USD_TZS}
    # cross-border buyers typically pay a 8–22% premium over Kigali farmgate
    premium = 1.0 if corridor.startswith("Domestic") else random.uniform(1.08, 1.22)
    currency = bcur if random.random() < 0.7 else "USD"
    unit_usd = unit_rwf * premium / fx_rwf
    if currency == "USD":
        unit_price = round(unit_usd, 3); fx = 1.0
    else:
        fx = fx_map[currency][y] * random.uniform(0.985, 1.015)
        unit_price = round(unit_usd * fx, 2 if currency == "RWF" else 0)
    total = round(unit_price * lot["quantity_kg"], 2)
    total_usd = round(total / fx, 2)
    channel = wchoice(SETTLEMENT_BY_YEAR[y])
    if corridor.startswith("Domestic") and channel in ("PAPSS", "Bank transfer (SWIFT/USD)"):
        channel = "MTN MoMo"
    escrowed = channel.startswith("AXK escrow")

    status_map = {"Reserved": "Confirmed", "In Transit": "In Transit", "Delivered": "Delivered", "Closed": "Settled"}
    ostatus = status_map[lot["status"]]
    if ostatus == "Settled" and random.random() < 0.05:
        ostatus = "Disputed"
    if ostatus == "Confirmed" and random.random() < 0.15:
        ostatus = "Cancelled"

    confirmed = ts(order_date + timedelta(days=random.randint(0, 3)))
    dispatch = delivered = settled = None
    # --- outcome variables: completion time (order confirmed → settled) in hours
    if escrowed:
        base_hours = random.uniform(30, 96)
    elif channel in ("MTN MoMo", "Airtel Money"):
        base_hours = random.uniform(72, 240)
    elif channel == "PAPSS":
        base_hours = random.uniform(96, 260)
    elif channel == "Cash on delivery":
        base_hours = random.uniform(120, 400)
    else:
        base_hours = random.uniform(240, 720)
    if corridor.startswith("Domestic"):
        base_hours *= 0.55
    baseline_recall = round(random.uniform(168, 720))  # traders' recalled pre-AXK completion time

    if ostatus in ("In Transit", "Delivered", "Settled", "Disputed"):
        dispatch = confirmed + timedelta(hours=random.uniform(6, 72))
    if ostatus in ("Delivered", "Settled", "Disputed"):
        delivered = dispatch + timedelta(hours=random.uniform(6, 60))
    if ostatus == "Settled":
        settled = confirmed + timedelta(hours=base_hours)
        if delivered and settled < delivered:
            settled = delivered + timedelta(hours=random.uniform(2, 36))
    # nothing may sit in the future
    if settled and settled > END_DT:
        settled = None; ostatus = "Delivered"
    if delivered and delivered > END_DT:
        delivered = None; ostatus = "In Transit"
    if dispatch and dispatch > END_DT:
        dispatch = None; ostatus = "Confirmed"
    if confirmed > END_DT:
        confirmed = END_DT - timedelta(hours=random.uniform(1, 40))

    bcity_gps = CITY_GPS[bcity]
    mspec_ok = bool(spec["moist"])
    if dispatch:
        seq += 1; t2 = dispatch + timedelta(hours=random.uniform(1, 6))
        if not corridor.startswith("Domestic"):
            prev = add_event(lot, seq, "certificate_of_origin", t2 - timedelta(hours=random.uniform(12, 48)), "Rwanda Revenue Authority",
                             "Customs officer", f"RRA {c['district']} office", lat, lng, "", "", "", "pass", prev, "AfCFTA/EAC simplified certificate of origin issued.")
            if lot["commodity"] in ("Irish Potato", "Beans (dry)", "Maize (dry grain)", "Coffee (parchment)"):
                seq += 1
                prev = add_event(lot, seq, "phytosanitary_certificate", t2 - timedelta(hours=random.uniform(6, 30)), "RAB Plant Health",
                                 "Phytosanitary inspector", f"RAB {c['district']}", lat, lng, "", "", "", "pass", prev)
            seq += 1
            prev = add_event(lot, seq, "border_exit", t2, "Rwanda Revenue Authority", "Customs officer", post, lat, lng,
                             lot["quantity_kg"], "", "", "pass", prev)
            seq += 1
            prev = add_event(lot, seq, "border_entry", t2 + timedelta(hours=random.uniform(0.5, 9)), entry_org, "Customs officer",
                             post, lat, lng, lot["quantity_kg"] - random.randint(0, 60), "", "", wchoice([("pass", 0.93), ("conditional", 0.07)]), prev,
                             random.choice(["", "", "", "Queue at post: 4h20m.", "Manifest re-checked against AXK lot hash (QR)."]))
    if delivered:
        seq += 1
        rres = "fail" if ostatus == "Disputed" else wchoice([("pass", 0.94), ("conditional", 0.06)])
        prev = add_event(lot, seq, "buyer_receipt", delivered, bname, "Buyer receiving clerk", f"{bcity}, {bcountry}",
                         bcity_gps[0], bcity_gps[1],
                         lot["quantity_kg"] - random.randint(0, 90), (lot["moisture_pct"] + round(random.uniform(-0.3, 0.8), 1)) if mspec_ok else "",
                         lot["grade"], rres, prev, "" if rres == "pass" else random.choice(
                             ["Short delivery of 2 bags; credit note raised.", "Buyer disputes grade; surveyor called.",
                              "Moisture above contract tolerance on arrival."]))
    if ostatus == "Disputed":
        seq += 1
        prev = add_event(lot, seq, "dispute_inspection", min(END_DT, delivered + timedelta(days=random.randint(2, 9))), "Independent surveyor",
                         "Surveyor", f"{bcity}, {bcountry}", bcity_gps[0], bcity_gps[1], lot["quantity_kg"] - random.randint(50, 200), "",
                         random.choice(["B", "C"]), "conditional", prev, "Partial release recommended after re-grading.")

    completion = round((settled - confirmed).total_seconds() / 3600, 1) if settled else ""
    trust_pre = round(random.uniform(2.2, 3.4), 1)
    trust_post = round(min(5.0, trust_pre + (random.uniform(0.6, 1.6) if escrowed else random.uniform(0.0, 0.8))), 1) if ostatus == "Settled" else ""
    esc_id = ""
    if escrowed and ostatus != "Cancelled":
        esc_year_counts[y] = esc_year_counts.get(y, 0) + 1
        esc_id = f"AXK-ESC-{y}-{esc_year_counts[y]:05d}"

    order = {
        "order_id": order_id, "lot": lot["lot_id"], "cooperative": c["coop_id"],
        "buyer_name": bname, "buyer_country": bcountry, "buyer_city": bcity2, "buyer_type": btype,
        "corridor": corridor, "border_post": post,
        "commodity": lot["commodity"], "grade": lot["grade"], "quantity_kg": lot["quantity_kg"],
        "unit_price": unit_price, "currency": currency, "total_amount": total,
        "fx_rate_usd": round(fx, 4), "total_usd": total_usd,
        "order_date": fmt_d(order_date), "confirmed_at": fmt_dt(confirmed) if ostatus != "Draft" else "",
        "dispatch_date": fmt_dt(dispatch) if dispatch else "",
        "delivered_at": fmt_dt(delivered) if delivered else "",
        "settled_at": fmt_dt(settled) if settled else "",
        "status": ostatus, "settlement_channel": channel, "escrow_contract": esc_id,
        "completion_time_hours": completion, "baseline_recall_hours": baseline_recall,
        "trust_score_pre": trust_pre, "trust_score_post": trust_post,
        "dispute_flag": 1 if ostatus == "Disputed" else 0,
        "cancellation_reason": random.choice(["Buyer FX shortage", "Price renegotiation failed", "Truck unavailable", "Border closure (Goma)"]) if ostatus == "Cancelled" else "",
        "notes": random.choice(["", "", "", "Buyer scanned lot QR at receipt; hash matched.",
                                "Settled in local currency; no correspondent bank leg.", "Truck: Fuso 7t, 2 axles.",
                                "Buyer requested split delivery; single lot kept.", "Rainy-season road delay on RN4."]),
    }
    orders.append(order)

    if esc_id:
        stellar = channel.endswith("(Stellar USDC, testnet)")
        chain = "stellar" if stellar else "xahau"
        network = "testnet" if stellar else "mainnet"
        created = min(END_DT, confirmed + timedelta(minutes=random.randint(3, 240)))
        funded = created + timedelta(hours=random.uniform(0.2, 30))
        if funded > END_DT: funded = None
        cond_type = "buyer_receipt" if random.random() < 0.8 else "border_entry"
        estatus = {"Confirmed": "Funded", "In Transit": "Funded", "Delivered": "Release Pending",
                   "Settled": "Released", "Disputed": "Disputed"}[ostatus]
        if (ostatus == "Confirmed" and random.random() < 0.3) or funded is None:
            estatus, funded = "Created", None
        released = settled if estatus == "Released" else None
        fee = round(total * 0.004, 2)
        esc = {
            "escrow_id": esc_id, "order": order_id, "lot": lot["lot_id"], "cooperative": c["coop_id"],
            "buyer_name": bname, "amount": total, "currency": currency, "amount_usd": total_usd,
            "chain": chain, "network": network,
            "escrow_account": stellar_contract() if stellar else xah_acct(),
            "release_condition": ("Release on verified buyer_receipt event (hash-chained, anchored)"
                                  if cond_type == "buyer_receipt" else "Release on verified border_entry event + 48h no-dispute window"),
            "condition_event_type": cond_type,
            "created_at": fmt_dt(created),
            "funded_at": fmt_dt(funded) if funded else "",
            "fund_tx_hash": (stellar_tx() if stellar else xah_tx()) if funded else "",
            "fund_ledger_index": (ledger_index("xahau", funded) if funded and not stellar else ""),
            "released_at": fmt_dt(released) if released else "",
            "release_tx_hash": (stellar_tx() if stellar else xah_tx()) if released else "",
            "release_ledger_index": (ledger_index("xahau", released) if released and not stellar else ""),
            "refunded_at": "", "refund_tx_hash": "",
            "status": estatus, "fee_amount": fee, "fee_currency": currency,
            "dispute_reason": (random.choice(["Grade mismatch on arrival", "Short delivery", "Moisture above tolerance"]) if estatus == "Disputed" else ""),
            "dispute_opened_at": fmt_dt(delivered + timedelta(hours=random.uniform(2, 30))) if estatus == "Disputed" else "",
            "dispute_resolved_at": "", "arbiter": "AXK dispute desk (Kigali)" if estatus == "Disputed" else "",
            "notes": "EscrowCreate with FinishAfter + Condition (crypto-condition preimage = buyer_receipt event_hash)." if not stellar
                     else "Soroban escrow contract; release authorised by AXK oracle signature over event_hash.",
        }
        escrows.append(esc)

# a small number of refunded escrows (cancelled after funding)
for esc in random.sample([e for e in escrows if e["status"] == "Funded"], k=min(9, len([e for e in escrows if e["status"] == "Funded"]))):
    fa = datetime.strptime(esc["funded_at"], "%Y-%m-%d %H:%M:%S")
    esc["status"] = "Refunded"
    esc["refunded_at"] = fmt_dt(min(END_DT, fa + timedelta(days=random.randint(5, 21))))
    esc["refund_tx_hash"] = xah_tx() if esc["chain"] == "xahau" else stellar_tx()
    esc["notes"] += " EscrowCancel after CancelAfter elapsed; goods not dispatched."
    for o in orders:
        if o["order_id"] == esc["order"]:
            o["status"] = "Cancelled"; o["cancellation_reason"] = "Escrow expired before dispatch"

events.sort(key=lambda e: e["timestamp"])
orders.sort(key=lambda o: o["order_date"])
escrows.sort(key=lambda e: e["created_at"])

# --------------------------------------------------------------------------------------
# Write outputs
# --------------------------------------------------------------------------------------
DATASETS = {
    "Cooperative": coops, "Harvest Record": harvests, "Lot": lots,
    "Verification Event": events, "AXK Order": orders, "Escrow Contract": escrows,
}
for dt, rows in DATASETS.items():
    cols = FIELDS[dt]
    slug = dt.lower().replace(" ", "_")
    with open(os.path.join(OUT, f"{slug}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, f"{slug}.json"), "w", encoding="utf-8") as f:
        json.dump([{k: r.get(k, "") for k in cols} for r in rows], f, ensure_ascii=False, indent=1)

# --------------------------------------------------------------------------------------
# Integrity checks + summary
# --------------------------------------------------------------------------------------
coop_ids = {c["coop_id"] for c in coops}
hr_ids = {h["harvest_id"] for h in harvests}
lot_ids = set(lot_by_id)
order_ids = {o["order_id"] for o in orders}
assert all(h["cooperative"] in coop_ids for h in harvests)
assert all(l["cooperative"] in coop_ids for l in lots)
assert all(all(x in hr_ids for x in l["harvest_record_ids"].split(";")) for l in lots)
assert all(e["lot"] in lot_ids for e in events)
assert all(o["lot"] in lot_ids and o["cooperative"] in coop_ids for o in orders)
assert all(e["order"] in order_ids and e["lot"] in lot_ids for e in escrows)
# hash chain check
chains = {}
for e in events:
    chains.setdefault(e["lot"], []).append(e)
for lot_id, evs in chains.items():
    evs.sort(key=lambda e: e["sequence_no"])
    prev = GENESIS
    for e in evs:
        assert e["prev_hash"] == prev, f"chain break at {e['event_id']}"
        prev = e["event_hash"]
assert len({o["escrow_contract"] for o in orders if o["escrow_contract"]}) == len(escrows)
_maxts = max([e["timestamp"] for e in events] + [o["settled_at"] or o["delivered_at"] or o["confirmed_at"] for o in orders]
             + [x for e in escrows for x in (e["released_at"], e["funded_at"], e["refunded_at"], e["created_at"]) if x])
assert _maxts <= fmt_dt(END_DT), _maxts

def by_year(rows, field):
    out = {}
    for r in rows:
        y = str(r[field])[:4]
        out[y] = out.get(y, 0) + 1
    return dict(sorted(out.items()))

settled = [o for o in orders if o["status"] == "Settled"]
def mean(xs): return round(sum(xs) / len(xs), 1) if xs else 0
esc_ct = mean([o["completion_time_hours"] for o in settled if o["settlement_channel"].startswith("AXK escrow")])
nonesc_ct = mean([o["completion_time_hours"] for o in settled if not o["settlement_channel"].startswith("AXK escrow")])
summary = {
    "seed": SEED, "window": f"{START} → {END}",
    "counts": {dt: len(rows) for dt, rows in DATASETS.items()},
    "lots_by_year": by_year(lots, "aggregation_date"),
    "orders_by_year": by_year(orders, "order_date"),
    "escrows_by_year": by_year(escrows, "created_at"),
    "events_by_year": by_year(events, "timestamp"),
    "order_status": {s: sum(1 for o in orders if o["status"] == s) for s in sorted({o["status"] for o in orders})},
    "escrow_status": {s: sum(1 for e in escrows if e["status"] == s) for s in sorted({e["status"] for e in escrows})},
    "settlement_channel_share": {s: sum(1 for o in orders if o["settlement_channel"] == s) for s in sorted({o["settlement_channel"] for o in orders})},
    "mean_completion_hours": {"AXK escrow": esc_ct, "non-escrow": nonesc_ct, "baseline_recall": mean([o["baseline_recall_hours"] for o in orders])},
    "total_settled_usd": round(sum(o["total_usd"] for o in settled), 2),
    "anchored_lots": sum(1 for l in lots if l["anchor_chain"] == "xahau"),
    "anchored_events": sum(1 for e in events if e["anchor_chain"] == "xahau"),
    "hash_chain_verified_lots": len(chains),
}
with open(os.path.join(OUT, "SUMMARY.json"), "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
