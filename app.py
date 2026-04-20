import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(
    page_title="BrainMarket – Marketing Náklady",
    page_icon="📊",
    layout="wide",
)

MONTHS_CZ = [
    "Leden", "Únor", "Březen", "Duben", "Květen", "Červen",
    "Červenec", "Srpen", "Září", "Říjen", "Listopad", "Prosinec",
]
MONTH_LABELS = ["Led", "Úno", "Bře", "Dub", "Kvě", "Čvn",
                "Čvc", "Srp", "Zář", "Říj", "Lis", "Pro"]

SKIP_KANALY = {"VŠECHNY KANÁLY", ""}
SKIP_ZEME = {"VŠECHNY ZEMĚ", ""}


def parse_czk(val) -> float:
    if val is None or val == "":
        return 0.0
    s = str(val).replace("Kč", "").replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    if not s or s.startswith("#"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


@st.cache_data(ttl=300, show_spinner="Načítám data z Google Sheets…")
def load_data(sheet_id: str, creds_info: dict) -> pd.DataFrame:
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)

    frames = []
    for year in [2025, 2026]:
        try:
            ws = spreadsheet.worksheet(str(year))
            rows = ws.get_all_values()
        except gspread.WorksheetNotFound:
            st.warning(f"List '{year}' nenalezen v tabulce.")
            continue

        if len(rows) < 2:
            continue

        header = rows[0]
        df = pd.DataFrame(rows[1:], columns=header)
        df["Rok"] = year
        frames.append(df)

    if not frames:
        st.error("Nepodařilo se načíst žádná data.")
        st.stop()

    return pd.concat(frames, ignore_index=True)


def clean_data(raw: pd.DataFrame) -> pd.DataFrame:
    keep = ["Kanál", "Země", "Rok"] + MONTHS_CZ
    available = [c for c in keep if c in raw.columns]
    df = raw[available].copy()

    df["Kanál"] = df["Kanál"].str.strip()
    df["Země"] = df["Země"].str.strip()

    df = df[
        df["Kanál"].notna()
        & (~df["Kanál"].isin(SKIP_KANALY))
        & df["Země"].notna()
        & (~df["Země"].isin(SKIP_ZEME))
    ]

    months_present = [m for m in MONTHS_CZ if m in df.columns]
    for m in months_present:
        df[m] = df[m].apply(parse_czk)

    df_long = df.melt(
        id_vars=["Kanál", "Země", "Rok"],
        value_vars=months_present,
        var_name="Měsíc",
        value_name="Náklady",
    )
    df_long["Měsíc_num"] = df_long["Měsíc"].map({m: i + 1 for i, m in enumerate(MONTHS_CZ)})
    df_long["Měsíc_label"] = df_long["Měsíc_num"].map({i + 1: l for i, l in enumerate(MONTH_LABELS)})
    df_long = df_long[df_long["Náklady"] > 0].copy()

    return df_long


def fmt_czk(val: float) -> str:
    return f"{val:,.0f} Kč".replace(",", " ")


# ── Credentials & Sheet ID ────────────────────────────────────────────────────

if "gcp_service_account" not in st.secrets or "sheet_id" not in st.secrets:
    st.error(
        "Chybí konfigurace. Vytvořte soubor `.streamlit/secrets.toml` podle vzoru níže:\n\n"
        "```toml\n"
        'sheet_id = "VÁŠ_SHEET_ID"\n\n'
        "[gcp_service_account]\n"
        'type = "service_account"\n'
        'project_id = "..."\n'
        'private_key_id = "..."\n'
        'private_key = "-----BEGIN RSA PRIVATE KEY-----\\n..."\n'
        'client_email = "...@....iam.gserviceaccount.com"\n'
        'client_id = "..."\n'
        "```"
    )
    st.stop()

sheet_id = st.secrets["sheet_id"]
creds_info = dict(st.secrets["gcp_service_account"])

raw_df = load_data(sheet_id, creds_info)
df = clean_data(raw_df)

# ── Sidebar filtry ────────────────────────────────────────────────────────────

st.sidebar.title("Filtry")

roky = sorted(df["Rok"].unique())
vybrane_roky = st.sidebar.multiselect("Rok", roky, default=roky)

zeme_options = sorted(df["Země"].unique())
vse_zeme = st.sidebar.checkbox("Vybrat všechny země", value=True, key="vse_zeme")
if vse_zeme:
    vybrane_zeme = zeme_options
else:
    vybrane_zeme = st.sidebar.multiselect("Země", zeme_options, default=zeme_options, key="ms_zeme")

kanal_options = sorted(df["Kanál"].unique())
vse_kanaly = st.sidebar.checkbox("Vybrat všechny kanály", value=True, key="vse_kanaly")
if vse_kanaly:
    vybrane_kanaly = kanal_options
else:
    vybrane_kanaly = st.sidebar.multiselect("Kanál", kanal_options, default=kanal_options, key="ms_kanaly")

if st.sidebar.button("🔄 Obnovit data"):
    st.cache_data.clear()
    st.rerun()

# ── Filtrování ────────────────────────────────────────────────────────────────

mask = (
    df["Rok"].isin(vybrane_roky)
    & df["Země"].isin(vybrane_zeme)
    & df["Kanál"].isin(vybrane_kanaly)
)
fdf = df[mask]

if fdf.empty:
    st.warning("Žádná data pro vybrané filtry.")
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────

st.title("📊 BrainMarket – Marketing Náklady")

# ── KPI karty ─────────────────────────────────────────────────────────────────

total = fdf["Náklady"].sum()
col1, col2, col3, col4 = st.columns(4)

val_2025 = fdf[fdf["Rok"] == 2025]["Náklady"].sum()
val_2026 = fdf[fdf["Rok"] == 2026]["Náklady"].sum()

with col1:
    st.metric("Celkem (vybraný filtr)", fmt_czk(total))

with col2:
    st.metric("YTD 2026", fmt_czk(val_2026))

with col3:
    st.metric("YTD 2025", fmt_czk(val_2025))

with col4:
    if val_2025 > 0:
        delta_pct = (val_2026 - val_2025) / val_2025 * 100
        st.metric("Meziroční změna", f"{delta_pct:+.1f} %")
    else:
        st.metric("Meziroční změna", "—")

st.divider()

# ── Meziroční srovnání (stejné období) ───────────────────────────────────────

import datetime
current_month = datetime.date.today().month

# Poslední dokončený měsíc = aktuální měsíc - 1
last_complete_month = current_month - 1

months_with_2026_data = sorted(fdf[fdf["Rok"] == 2026]["Měsíc_num"].unique())
comparable_months = [m for m in months_with_2026_data if m <= last_complete_month]

if comparable_months:
    from_month = 1
    to_month = max(comparable_months)
    label_from = MONTHS_CZ[from_month - 1]
    label_to = MONTHS_CZ[to_month - 1]

    mask_period = fdf["Měsíc_num"].between(from_month, to_month)
    period_2025 = fdf[(fdf["Rok"] == 2025) & mask_period]["Náklady"].sum()
    period_2026 = fdf[(fdf["Rok"] == 2026) & mask_period]["Náklady"].sum()

    st.subheader(f"Meziroční srovnání: {label_from} – {label_to}")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(f"{label_from}–{label_to} 2025", fmt_czk(period_2025))
    with c2:
        st.metric(f"{label_from}–{label_to} 2026", fmt_czk(period_2026))
    with c3:
        diff = period_2026 - period_2025
        st.metric("Rozdíl", fmt_czk(diff), delta=f"{diff:+,.0f} Kč".replace(",", " "))
    with c4:
        if period_2025 > 0:
            pct = (period_2026 - period_2025) / period_2025 * 100
            st.metric("Změna", f"{pct:+.1f} %")
        else:
            st.metric("Změna", "—")

    # Měsíc po měsíci srovnání
    monthly_cmp = (
        fdf[mask_period & fdf["Rok"].isin([2025, 2026])]
        .groupby(["Rok", "Měsíc_num", "Měsíc_label"])["Náklady"]
        .sum()
        .reset_index()
        .sort_values(["Měsíc_num", "Rok"])
    )
    monthly_cmp["Rok"] = monthly_cmp["Rok"].astype(str)

    fig_cmp = px.bar(
        monthly_cmp,
        x="Měsíc_label",
        y="Náklady",
        color="Rok",
        barmode="group",
        text_auto=False,
        labels={"Náklady": "Náklady (Kč)", "Měsíc_label": "Měsíc"},
        color_discrete_sequence=["#4C78A8", "#F58518"],
    )
    fig_cmp.update_layout(yaxis_tickformat=",.0f", legend_title_text="Rok")
    st.plotly_chart(fig_cmp, use_container_width=True)

    # Meziroční rozdíl podle kanálu
    st.subheader(f"Meziroční rozdíl podle kanálu ({label_from}–{label_to})")

    kanal_2025 = (
        fdf[(fdf["Rok"] == 2025) & mask_period]
        .groupby("Kanál")["Náklady"].sum()
    )
    kanal_2026 = (
        fdf[(fdf["Rok"] == 2026) & mask_period]
        .groupby("Kanál")["Náklady"].sum()
    )
    kanal_diff = (kanal_2026 - kanal_2025).fillna(kanal_2026).fillna(-kanal_2025).dropna()
    kanal_diff = kanal_diff[kanal_diff != 0].sort_values()

    colors = ["#d62728" if v > 0 else "#2ca02c" for v in kanal_diff.values]

    fig_diff = go.Figure(go.Bar(
        x=kanal_diff.values,
        y=kanal_diff.index,
        orientation="h",
        marker_color=colors,
        text=[fmt_czk(v) for v in kanal_diff.values],
        textposition="outside",
    ))
    fig_diff.update_layout(
        xaxis_tickformat=",.0f",
        xaxis_title="Rozdíl (Kč)",
        yaxis_title=None,
        showlegend=False,
        margin=dict(l=10, r=150),
        xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor="gray"),
    )
    st.plotly_chart(fig_diff, use_container_width=True)
    st.caption("Červená = náklady vzrostly, zelená = náklady klesly")

st.divider()

# ── Náklady po měsících ───────────────────────────────────────────────────────

st.subheader("Náklady po měsících")

monthly = (
    fdf.groupby(["Rok", "Měsíc_num", "Měsíc_label"])["Náklady"]
    .sum()
    .reset_index()
    .sort_values(["Rok", "Měsíc_num"])
)
monthly["Rok"] = monthly["Rok"].astype(str)

fig_monthly = px.bar(
    monthly,
    x="Měsíc_label",
    y="Náklady",
    color="Rok",
    barmode="group",
    labels={"Náklady": "Náklady (Kč)", "Měsíc_label": "Měsíc"},
    color_discrete_sequence=["#4C78A8", "#F58518"],
)
fig_monthly.update_layout(yaxis_tickformat=",.0f", legend_title_text="Rok")
st.plotly_chart(fig_monthly, use_container_width=True)

st.divider()

# ── Podle zemí a kanálů ───────────────────────────────────────────────────────

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Podle země")
    by_zeme = (
        fdf.groupby(["Země", "Rok"])["Náklady"]
        .sum()
        .reset_index()
        .sort_values("Náklady", ascending=False)
    )
    by_zeme["Rok"] = by_zeme["Rok"].astype(str)
    fig_zeme = px.bar(
        by_zeme,
        x="Náklady",
        y="Země",
        color="Rok",
        orientation="h",
        barmode="group",
        labels={"Náklady": "Náklady (Kč)"},
        color_discrete_sequence=["#4C78A8", "#F58518"],
    )
    fig_zeme.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_tickformat=",.0f")
    st.plotly_chart(fig_zeme, use_container_width=True)

with col_right:
    st.subheader("Podle kanálu")
    by_kanal = (
        fdf.groupby(["Kanál", "Rok"])["Náklady"]
        .sum()
        .reset_index()
        .sort_values("Náklady", ascending=False)
    )
    by_kanal["Rok"] = by_kanal["Rok"].astype(str)
    fig_kanal = px.bar(
        by_kanal,
        x="Náklady",
        y="Kanál",
        color="Rok",
        orientation="h",
        barmode="group",
        labels={"Náklady": "Náklady (Kč)"},
        color_discrete_sequence=["#4C78A8", "#F58518"],
    )
    fig_kanal.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_tickformat=",.0f")
    st.plotly_chart(fig_kanal, use_container_width=True)

st.divider()

# ── Treemapa kanál × země ─────────────────────────────────────────────────────

st.subheader("Rozložení nákladů: Kanál × Země")

tree = fdf.groupby(["Země", "Kanál"])["Náklady"].sum().reset_index()
tree = tree[tree["Náklady"] > 0]

fig_tree = px.treemap(
    tree,
    path=["Země", "Kanál"],
    values="Náklady",
    color="Náklady",
    color_continuous_scale="Blues",
    custom_data=["Náklady"],
)
fig_tree.update_traces(
    texttemplate="<b>%{label}</b><br>%{value:,.0f} Kč",
    hovertemplate="<b>%{label}</b><br>%{value:,.0f} Kč<extra></extra>",
)
fig_tree.update_layout(margin=dict(t=30, l=0, r=0, b=0), coloraxis_showscale=False)
st.plotly_chart(fig_tree, use_container_width=True)

st.divider()

# ── Detailní tabulka ──────────────────────────────────────────────────────────

with st.expander("Detailní tabulka"):
    tbl = (
        fdf.groupby(["Rok", "Kanál", "Země", "Měsíc_num", "Měsíc"])["Náklady"]
        .sum()
        .reset_index()
        .sort_values(["Rok", "Měsíc_num", "Kanál", "Země"])
        .drop(columns="Měsíc_num")
    )
    tbl["Náklady"] = tbl["Náklady"].apply(fmt_czk)
    st.dataframe(tbl, use_container_width=True, hide_index=True)
