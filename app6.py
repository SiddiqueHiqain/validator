import streamlit as st
import pandas as pd
import sqlite3
import re
import io
import sys
from pathlib import Path
from importlib.util import find_spec

# ========================== INTERNAL SETTINGS ==========================
DB_FILE = "nanpa.db"   # Hidden - Not shown anywhere in UI
VENV_SITE_PACKAGES = Path(__file__).resolve().parent / "venv" / "Lib" / "site-packages"

if VENV_SITE_PACKAGES.exists():
    sys.path.append(str(VENV_SITE_PACKAGES))

try:
    import phonenumbers
    from phonenumbers import geocoder, timezone as phone_timezone
except Exception:
    phonenumbers = None
    geocoder = None
    phone_timezone = None

# ========================== DATA LOADER ================================
def load_nanpa():
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM nanpa_prefixes", conn)
        conn.close()
        for col in ["prefix", "company", "line_type", "state", "city", "timezone"]:
            if col not in df.columns:
                df[col] = ""
        df["company"] = df["company"].astype(str).apply(lambda x: x.strip().strip('"').strip("'"))
        return df
    except:
        return pd.DataFrame(columns=["prefix", "company", "line_type", "state", "city", "timezone"])

NANPA = load_nanpa()

# ========================== HELPERS ====================================
def clean_number(n):
    return re.sub(r"\D", "", str(n))

def split_pasted_numbers(raw_text):
    numbers = []
    for line in raw_text.splitlines():
        cleaned_line = line.strip()
        if cleaned_line:
            numbers.append(cleaned_line)
    return numbers

def build_download_file(df, base_name):
    if find_spec("openpyxl") is not None:
        buf = io.BytesIO()
        df.to_excel(buf, index=False)
        return buf.getvalue(), f"{base_name}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", None

    csv_data = df.to_csv(index=False).encode("utf-8")
    warning = "Excel export needs `openpyxl`, so this download is being provided as CSV instead."
    return csv_data, f"{base_name}.csv", "text/csv", warning

KNOWN_VOIP = [
    "twilio","vonage","bandwidth","level 3","level3",
    "voip","sip","ringcentral","telnyx","nexmo","plivo"
]

def detect_voip(company, line_type):
    c = (company or "").lower()
    lt = (line_type or "").lower()
    if "voip" in lt:
        return True
    if any(v in c for v in KNOWN_VOIP):
        return True
    return False

def yes_no(value):
    return "Yes" if value else "No"

def clean_text(value):
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    return text

def lookup_location(num):
    if not phonenumbers:
        return "", ""
    try:
        parsed = phonenumbers.parse(str(num), "US")
        if not phonenumbers.is_possible_number(parsed):
            return "", ""

        description = clean_text(geocoder.description_for_number(parsed, "en"))
        if "," in description:
            city = clean_text(description.split(",", 1)[0])
        else:
            city = ""

        timezones = phone_timezone.time_zones_for_number(parsed)
        timezone_value = ", ".join(timezones) if timezones else ""
        return city, timezone_value
    except Exception:
        return "", ""

def nanpa_lookup(num):
    c = clean_number(num)
    if len(c) < 6:
        return "", "", "", "", ""
    pref = c[:6]
    row = NANPA[NANPA["prefix"] == pref]
    if row.empty:
        return "", "", "", "", ""
    r = row.iloc[0]
    company = clean_text(r.get("company", ""))
    line_type = clean_text(r.get("line_type", ""))
    state = clean_text(r.get("state", ""))
    city = clean_text(r.get("city", ""))
    timezone = clean_text(r.get("timezone", ""))

    if not city or not timezone:
        detected_city, detected_timezone = lookup_location(num)
        city = city or detected_city
        timezone = timezone or detected_timezone

    city = city or "Unknown"
    timezone = timezone or "Unknown"
    return company, line_type, state, city, timezone

def filter_by_line_type(df, selected_line_type):
    if selected_line_type == "All":
        return df
    return df[df["Line Type"] == selected_line_type]

def render_bulk_results(results_key, filter_key, download_label, base_name, max_rows=None):
    final = st.session_state.get(results_key)
    if final is None or final.empty:
        return

    line_type_options = ["All"] + sorted(
        value for value in final["Line Type"].fillna("").unique() if str(value).strip()
    )
    selected_line_type = st.selectbox(
        "Filter by line type",
        line_type_options,
        key=filter_key
    )

    filtered = filter_by_line_type(final, selected_line_type)
    display_df = filtered.head(max_rows) if max_rows else filtered

    st.write(f"Showing **{len(filtered)}** result(s).")
    st.dataframe(
        display_df,
        use_container_width=True,
        column_config={
            "Company": None,
            "Is_VoIP": None
        }
    )

    download_data, download_name, mime_type, _ = build_download_file(filtered, base_name)
    st.download_button(
        download_label,
        data=download_data,
        file_name=download_name,
        mime=mime_type
    )

# ========================== UI SETTINGS =================================
st.set_page_config(page_title="HiQain Validator", layout="centered")

# ========================== HEADER ======================================
st.markdown("""
<div style="text-align:center; padding-top:40px;">
    <h1 style="font-size:46px; margin-bottom:10px;">HiQain Validator</h1>
    <p style="font-size:18px; color:gray;">Fast & Accurate Phone Line Validation</p>
</div>
""", unsafe_allow_html=True)

# ========================== SINGLE SEARCH (Veriphone style) =============
st.write("")
st.write("")
phone = st.text_input("", placeholder="Enter phone number e.g. +1 415 466 8304")

if st.button("Validate Number", use_container_width=True):
    if not phone:
        st.warning("Please enter a phone number.")
    else:
        comp, ltype, state, city, timezone = nanpa_lookup(phone)
        is_voip = detect_voip(comp, ltype)

        # Output card - clean & modern like Veriphone
        st.markdown("""
        <div style="background:#ffffff; padding:25px; border-radius:12px;
                    box-shadow: 0px 4px 10px rgba(0,0,0,0.1); margin-top:20px;">
            <h3 style="margin-top:0;">Result</h3>
        """, unsafe_allow_html=True)

        st.write("**Cleaned Number:**", clean_number(phone))
        st.write("**Carrier / Company:**", comp if comp else "Unknown")
        st.write("**Line Type:**", ltype if ltype else "Unknown")
        st.write("**State:**", state if state else "Unknown")
        st.write("**City:**", city if city else "Unknown")
        st.write("**Timezone:**", timezone if timezone else "Unknown")

        if is_voip:
            st.success("This appears to be a **VoIP number**.")
        else:
            st.info("This appears to be a **Non-VoIP number**.")

        st.markdown("</div>", unsafe_allow_html=True)

# ========================== BATCH (Optional) ============================
st.write("---")
st.subheader("Bulk Validator (Excel Upload)")

file = st.file_uploader("Upload .xlsx", type=["xlsx"])

if file:
    df = pd.read_excel(file)
    phone_col = st.selectbox("Select phone column", df.columns)

    if st.button("Run Bulk Validation"):
        out = []
        for p in df[phone_col]:
            comp, ltype, state, city, timezone = nanpa_lookup(p)
            out.append({
                "Original": p,
                "Cleaned": clean_number(p),
                "Company": comp,
                "Line Type": ltype,
                "State": state,
                "City": city,
                "Timezone": timezone,
                "Is_VoIP": yes_no(detect_voip(comp, ltype))
            })

        st.session_state["bulk_validation_results"] = pd.DataFrame(out)

    render_bulk_results(
        "bulk_validation_results",
        "bulk_line_type_filter",
        "Download Results",
        "hiqain_validated",
        max_rows=200
    )

# ========================== PASTE BULK VALIDATOR =======================
st.write("---")
st.subheader("Paste & Validate Numbers")
st.caption("Paste up to 500 phone numbers, one per line, and validate them instantly.")

pasted_numbers = st.text_area(
    "Paste phone numbers here",
    height=220,
    placeholder="2135551212\n(213) 555-1212\n+1 213 555 1212",
)

if pasted_numbers:
    parsed_numbers = split_pasted_numbers(pasted_numbers)
    st.write(f"Detected **{len(parsed_numbers)}** number(s).")
else:
    parsed_numbers = []

if st.button("Run Paste Validation", use_container_width=True):
    if not parsed_numbers:
        st.warning("Please paste at least one phone number.")
    elif len(parsed_numbers) > 500:
        st.warning("Please limit pasted input to 500 phone numbers at a time.")
    else:
        out = []
        for p in parsed_numbers:
            comp, ltype, state, city, timezone = nanpa_lookup(p)
            out.append({
                "Original": p,
                "Company": comp,
                "Line Type": ltype,
                "State": state,
                "City": city,
                "Timezone": timezone,
                "Is_VoIP": yes_no(detect_voip(comp, ltype))
            })

        st.session_state["paste_validation_results"] = pd.DataFrame(out)

render_bulk_results(
    "paste_validation_results",
    "paste_line_type_filter",
    "Download Pasted Results",
    "hiqain_pasted_validated"
)
