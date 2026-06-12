import pandas as pd
import sqlite3
import os
import re

DB_PATH = "nanpa.db"

def detect_nanpa_file():
    """Find the latest NANPA .txt or .csv file in current directory"""
    for f in os.listdir("."):
        if f.lower().startswith("cocodeassignment") and (f.endswith(".txt") or f.endswith(".csv")):
            return f
    return None


def smart_read_nanpa(filepath):
    """Try multiple ways to read NANPA file automatically"""
    print(f"📂 Reading file: {filepath}")

    # 1️⃣ Try CSV normally
    try:
        df = pd.read_csv(filepath, dtype=str, low_memory=False)
        if len(df.columns) > 3:
            print(f"✅ Loaded {len(df)} rows using comma-separated CSV")
            return df
    except Exception:
        pass

    # 2️⃣ Try tab-separated
    try:
        df = pd.read_csv(filepath, sep="\t", dtype=str, engine="python", low_memory=False)
        if len(df.columns) > 3:
            print(f"✅ Loaded {len(df)} rows using tab-separated format")
            return df
    except Exception:
        pass

    # 3️⃣ Try whitespace (for weirdly spaced text)
    try:
        df = pd.read_csv(filepath, delim_whitespace=True, dtype=str, engine="python", low_memory=False)
        if len(df.columns) > 3:
            print(f"✅ Loaded {len(df)} rows using whitespace parser")
            return df
    except Exception:
        pass

    # 4️⃣ Try fixed-width (fwf)
    try:
        df = pd.read_fwf(filepath, dtype=str)
        if len(df.columns) > 3:
            print(f"✅ Loaded {len(df)} rows using fixed-width format")
            return df
    except Exception:
        pass

    print("❌ Could not parse NANPA file. Try checking file format.")
    return None


def clean_nanpa(df):
    """Clean and normalize NANPA data"""
    possible_prefix_cols = [c for c in df.columns if "NPA" in c.upper()]
    possible_company_cols = [c for c in df.columns if "COMPANY" in c.upper()]
    possible_use_cols = [c for c in df.columns if "USE" in c.upper()]
    possible_state_cols = [c for c in df.columns if "STATE" in c.upper()]

    prefix_col = possible_prefix_cols[0] if possible_prefix_cols else None
    company_col = possible_company_cols[0] if possible_company_cols else None
    use_col = possible_use_cols[0] if possible_use_cols else None
    state_col = possible_state_cols[0] if possible_state_cols else None

    print(f"✅ Using columns: Prefix={prefix_col}, Company={company_col}, Use={use_col}, State={state_col}")

    cleaned = []
    for _, row in df.iterrows():
        prefix = str(row.get(prefix_col, "")).strip().replace("-", "")
        company = str(row.get(company_col, "")).strip()
        use = str(row.get(use_col, "")).upper().strip()
        state = str(row.get(state_col, "")).strip()

        if not prefix.isdigit() or len(prefix) < 6:
            continue

        # --- Smart Line Type Detection ---
        use_clean = use.upper()
        comp = company.upper()

        if any(k in comp for k in ["WIRELESS", "CELLULAR", "PCS", "MOBILE", "RES", "CINGULAR", "T-MOBILE", "VERIZON WIRELESS", "ATT MOBILE"]) or use_clean in ["W", "C", "R", "PCS", "MOBILE"]:
            line_type = "Mobile"
        elif any(k in comp for k in ["CLEC", "ILEC", "INC", "COMMUNICATIONS", "TEL", "LANDLINE"]) or use_clean in ["L", "I"]:
            line_type = "Landline"
        elif "VOIP" in comp or use_clean == "V":
            line_type = "VoIP"
        else:
            line_type = "Unknown"

        cleaned.append((prefix, company, line_type, state))

    print(f"✅ Cleaned {len(cleaned)} unique prefixes. Writing to DB...")
    return cleaned


def update_db(records):
    """Insert cleaned data into SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nanpa_prefixes (
            prefix TEXT PRIMARY KEY,
            company TEXT,
            line_type TEXT,
            state TEXT
        )
    """)
    conn.commit()

    cur.execute("DELETE FROM nanpa_prefixes")

    cur.executemany("INSERT OR REPLACE INTO nanpa_prefixes VALUES (?, ?, ?, ?)", records)
    conn.commit()

    total = cur.execute("SELECT COUNT(*) FROM nanpa_prefixes").fetchone()[0]

    # 📊 Show summary breakdown
    summary = cur.execute("SELECT line_type, COUNT(*) FROM nanpa_prefixes GROUP BY line_type").fetchall()
    conn.close()

    print(f"✅ Database updated successfully: {DB_PATH}")
    print(f"📊 Total prefixes in DB: {total}")
    print("\n📊 Line type breakdown:")
    for t, c in summary:
        print(f"   {t or 'Unknown'}: {c} prefixes")


# ----------------------------
# Main Script
# ----------------------------
if __name__ == "__main__":
    print("🔄 NANPA Database Updater (auto-detect .txt/.csv)")
    file = detect_nanpa_file()
    if not file:
        print("❌ No NANPA file found in this folder.")
    else:
        print(f"📁 Using latest NANPA file: {file}")
        df = smart_read_nanpa(file)
        if df is not None:
            records = clean_nanpa(df)
            update_db(records)
