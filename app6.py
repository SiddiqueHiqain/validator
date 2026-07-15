import streamlit as st
import pandas as pd
import sqlite3
import re
import json
from pathlib import Path
import streamlit.components.v1 as components

# ========================== INTERNAL SETTINGS ==========================
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "nanpa.db"   # Hidden - Not shown anywhere in UI

try:
    import phonenumbers
    from phonenumbers import geocoder, timezone as phone_timezone
except Exception:
    phonenumbers = None
    geocoder = None
    phone_timezone = None

# ========================== DATA LOADER ================================
US_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia"
}

TIMEZONE_ABBREVIATIONS = {
    "America/New_York": "EST",
    "America/Detroit": "EST",
    "America/Indiana/Indianapolis": "EST",
    "America/Indiana/Knox": "CST",
    "America/Indiana/Marengo": "EST",
    "America/Indiana/Petersburg": "EST",
    "America/Indiana/Tell_City": "CST",
    "America/Indiana/Vevay": "EST",
    "America/Indiana/Vincennes": "EST",
    "America/Indiana/Winamac": "EST",
    "America/Kentucky/Louisville": "EST",
    "America/Kentucky/Monticello": "EST",
    "America/Chicago": "CST",
    "America/Menominee": "CST",
    "America/North_Dakota/Beulah": "CST",
    "America/North_Dakota/Center": "CST",
    "America/North_Dakota/New_Salem": "CST",
    "America/Denver": "MST",
    "America/Boise": "MST",
    "America/Phoenix": "MST",
    "America/Los_Angeles": "PST",
    "America/Anchorage": "AKST",
    "America/Juneau": "AKST",
    "America/Metlakatla": "AKST",
    "America/Nome": "AKST",
    "America/Sitka": "AKST",
    "America/Yakutat": "AKST",
    "Pacific/Honolulu": "HST",
}

def load_nanpa():
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query("SELECT * FROM nanpa_prefixes", conn)
        conn.close()
        for col in ["prefix", "company", "line_type", "state", "city", "timezone"]:
            if col not in df.columns:
                df[col] = ""
        df["prefix"] = df["prefix"].astype(str).str.extract(r"(\d{6})", expand=False).fillna("")
        for col in ["state", "city", "timezone"]:
            df[col] = df[col].fillna("").astype(str).str.strip()
        df["company"] = df["company"].astype(str).apply(lambda x: x.strip().strip('"').strip("'"))
        return df
    except:
        return pd.DataFrame(columns=["prefix", "company", "line_type", "state", "city", "timezone"])

NANPA = load_nanpa()

# ========================== HELPERS ====================================
def clean_number(n):
    return re.sub(r"\D", "", str(n))

def normalize_nanpa_digits(value):
    digits = clean_number(value)
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits

def format_phone_display(value):
    digits = normalize_nanpa_digits(value)

    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

    return str(value).strip()

def split_pasted_numbers(raw_text):
    numbers = []
    for line in raw_text.splitlines():
        cleaned_line = line.strip()
        if cleaned_line:
            numbers.append(cleaned_line)
    return numbers

def load_bulk_file(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(uploaded_file)

    if suffix == ".xlsx":
        try:
            return pd.read_excel(uploaded_file)
        except ImportError as exc:
            raise RuntimeError("Excel uploads require the `openpyxl` package to be installed.") from exc

    raise RuntimeError("Unsupported file type. Please upload a CSV or XLSX file.")

def build_validation_row(phone_value):
    comp, ltype, state, city, timezone = nanpa_lookup(phone_value)
    return {
        "Original": format_phone_display(phone_value),
        "Cleaned": clean_number(phone_value),
        "Company": comp,
        "Line Type": ltype,
        "State": state,
        "City": city,
        "Timezone": timezone,
        "Is_VoIP": yes_no(detect_voip(comp, ltype))
    }

def process_numbers_with_progress(phone_values, progress_label):
    total = len(phone_values)
    progress_container = st.empty()
    progress_bar = progress_container.progress(0)
    status = st.empty()
    results = []

    if total == 0:
        progress_bar.progress(100)
        progress_container.empty()
        status.empty()
        return results

    for index, phone_value in enumerate(phone_values, start=1):
        results.append(build_validation_row(phone_value))
        progress = int(index / total * 100)
        progress_bar.progress(progress)
        status.write(f"{progress_label} {index} of {total} phone number(s)... {progress}%")

    progress_container.empty()
    status.empty()
    return results

def deduplicate_results(rows):
    if not rows:
        return pd.DataFrame(), 0

    df = pd.DataFrame(rows)
    dedupe_key = df["Cleaned"].fillna("").astype(str).str.strip()
    fallback_key = df["Original"].fillna("").astype(str).str.strip()
    df["_dedupe_key"] = dedupe_key.where(dedupe_key != "", fallback_key)

    deduped = df.drop_duplicates(subset="_dedupe_key", keep="first").drop(columns="_dedupe_key")
    duplicates_filtered = len(df) - len(deduped)
    return deduped, duplicates_filtered

def build_download_file(df, base_name):
    csv_data = df.to_csv(index=False).encode("utf-8")
    return csv_data, f"{base_name}.csv", "text/csv", None

def build_copy_text(df):
    return df.to_csv(index=False, sep="\t")

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

def format_state(state):
    value = clean_text(state)
    if not value:
        return "Unknown"
    if len(value) == 2:
        return US_STATE_NAMES.get(value.upper(), value.upper())
    return value

def format_timezone(timezone_value):
    value = clean_text(timezone_value)
    if not value:
        return "Unknown"

    timezones = [clean_text(part) for part in value.split(",") if clean_text(part)]
    if not timezones:
        return "Unknown"

    formatted = [TIMEZONE_ABBREVIATIONS.get(tz, tz) for tz in timezones]
    return ", ".join(dict.fromkeys(formatted))

def extract_city(description, state):
    description_value = clean_text(description)
    if not description_value:
        return ""

    parts = [clean_text(part) for part in description_value.split(",") if clean_text(part)]
    candidate = parts[0] if parts else description_value
    state_code = clean_text(state).upper()
    state_name = US_STATE_NAMES.get(state_code, "").lower()
    candidate_lower = candidate.lower()

    if candidate_lower in {"united states", "canada"}:
        return ""
    if state_name and candidate_lower == state_name:
        return ""
    if state_code and candidate_lower == state_code.lower():
        return ""
    return candidate

def persist_location(prefix, city, timezone):
    if not prefix or (not city and not timezone):
        return
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        columns = {row[1] for row in cur.execute("PRAGMA table_info(nanpa_prefixes)").fetchall()}
        if "city" not in columns:
            cur.execute("ALTER TABLE nanpa_prefixes ADD COLUMN city TEXT")
        if "timezone" not in columns:
            cur.execute("ALTER TABLE nanpa_prefixes ADD COLUMN timezone TEXT")
        cur.execute(
            """
            UPDATE nanpa_prefixes
            SET city = COALESCE(NULLIF(TRIM(city), ''), ?),
                timezone = COALESCE(NULLIF(TRIM(timezone), ''), ?)
            WHERE prefix = ?
            """,
            (city, timezone, prefix),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def lookup_location(num, state=""):
    if not phonenumbers:
        return "", ""
    try:
        parsed = phonenumbers.parse(str(num), "US")
        if not phonenumbers.is_possible_number(parsed):
            return "", ""

        description = clean_text(geocoder.description_for_number(parsed, "en"))
        city = extract_city(description, state)

        timezones = phone_timezone.time_zones_for_number(parsed)
        timezone_value = ", ".join(timezones) if timezones else ""
        return city, timezone_value
    except Exception:
        return "", ""

def nanpa_lookup(num):
    c = normalize_nanpa_digits(num)
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
        detected_city, detected_timezone = lookup_location(num, state)
        city = city or detected_city
        timezone = timezone or detected_timezone
        if detected_city or detected_timezone:
            NANPA.loc[NANPA["prefix"] == pref, "city"] = city
            NANPA.loc[NANPA["prefix"] == pref, "timezone"] = timezone
            persist_location(pref, city, timezone)

    city = city or "Unknown"
    state = format_state(state)
    timezone = format_timezone(timezone)
    return company, line_type, state, city, timezone

def filter_by_line_type(df, selected_line_type):
    if selected_line_type == "All":
        return df
    return df[df["Line Type"] == selected_line_type]

def render_copy_button(copy_label, copy_text, button_key):
    button_id = f"copy-btn-{button_key}"
    wrapper_id = f"copy-wrapper-{button_key}"
    escaped_copy_text = json.dumps(copy_text)

    components.html(
        f"""
        <style>
            #{wrapper_id} {{
                --btn-bg-secondary: #ffffff;
                --btn-border-secondary: #d1d5db;
                --btn-text-secondary: #111827;
            }}

            @media (prefers-color-scheme: dark) {{
                #{wrapper_id} {{
                    --btn-bg-secondary: transparent;
                    --btn-border-secondary: rgba(250, 250, 250, 0.2);
                    --btn-text-secondary: #fafafa;
                }}
            }}
        </style>
        <div id="{wrapper_id}">
            <button
                id="{button_id}"
                type="button"
                style="
                    width:100%;
                    min-height:38px;
                    padding:0.6rem 0.75rem;
                    border-radius:0.5rem;
                    border:1px solid var(--btn-border-secondary);
                    background:var(--btn-bg-secondary);
                    color:var(--btn-text-secondary);
                    font-weight:600;
                    cursor:pointer;
                    box-sizing:border-box;
                "
            >
                {copy_label}
            </button>
        </div>
        <script>
            const button = document.getElementById("{button_id}");
            const textToCopy = {escaped_copy_text};
            const originalLabel = {json.dumps(copy_label)};

            button.addEventListener("click", async () => {{
                try {{
                    await navigator.clipboard.writeText(textToCopy);
                    button.textContent = "Copied";
                }} catch (error) {{
                    button.textContent = "Copy failed";
                }}

                window.setTimeout(() => {{
                    button.textContent = originalLabel;
                }}, 1600);
            }});
        </script>
        """,
        height=46,
    )

def render_bulk_results(results_key, filter_key, download_label, base_name, max_rows=None, copy_label=None):
    final = st.session_state.get(results_key)
    if final is None or final.empty:
        return
    duplicates_filtered = st.session_state.get(f"{results_key}_duplicates_filtered", 0)

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

    st.caption(f"Duplicates filtered: {duplicates_filtered}")

    download_data, download_name, mime_type, _ = build_download_file(filtered, base_name)
    button_columns = st.columns(3, vertical_alignment="bottom")

    with button_columns[0]:
        st.download_button(
            download_label,
            data=download_data,
            file_name=download_name,
            mime=mime_type,
            use_container_width=True
        )

    with button_columns[1]:
        if copy_label:
            render_copy_button(copy_label, build_copy_text(filtered), results_key)

    with button_columns[2]:
        if st.button("Clear Results", key=f"clear-{results_key}", use_container_width=True):
            st.session_state.pop(results_key, None)
            st.session_state.pop(f"{results_key}_duplicates_filtered", None)
            st.session_state.pop(filter_key, None)
            st.rerun()

# ========================== UI SETTINGS =================================
st.set_page_config(page_title="HiQain Validator", layout="centered")

# ========================== HEADER ======================================
st.markdown("""
<div style="text-align:center; padding-top:40px;">
    <h1 style="font-size:46px; margin-bottom:10px;">HiQain Validator</h1>
    <p style="font-size:18px; color:gray;">Fast & Accurate Phone Line Validation</p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<style>
div[data-testid="stFileUploaderDropzoneInstructions"] > div > span:last-child,
div[data-testid="stFileUploaderDropzoneInstructions"] small {
    display: none;
}
</style>
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
st.subheader("Bulk Validator (CSV / Excel Upload)")

file = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])

if file:
    try:
        df = load_bulk_file(file)
    except RuntimeError as exc:
        st.error(str(exc))
        df = None

    if df is not None:
        phone_col = st.selectbox("Select phone column", df.columns)

        if st.button("Run Bulk Validation"):
            phone_values = df[phone_col].tolist()
            out = process_numbers_with_progress(phone_values, "Processing uploaded numbers:")

            deduped_results, duplicates_filtered = deduplicate_results(out)
            st.session_state["bulk_validation_results"] = deduped_results
            st.session_state["bulk_validation_results_duplicates_filtered"] = duplicates_filtered

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
st.caption("Paste as many phone numbers as you want, one per line, and validate them instantly.")

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
    else:
        out = process_numbers_with_progress(parsed_numbers, "Processing pasted numbers:")

        deduped_results, duplicates_filtered = deduplicate_results(out)
        st.session_state["paste_validation_results"] = deduped_results
        st.session_state["paste_validation_results_duplicates_filtered"] = duplicates_filtered

render_bulk_results(
    "paste_validation_results",
    "paste_line_type_filter",
    "Download Pasted Results",
    "hiqain_pasted_validated",
    copy_label="Copy Pasted Results"
)
