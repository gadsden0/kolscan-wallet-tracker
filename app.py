
import os

import pandas as pd
import psycopg2
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="KOLscan Wallet Analytics",
    page_icon="📊",
    layout="wide",
)

st.title("KOLscan Wallet Analytics")
st.caption("Historical leaderboard tracking and wallet consistency")


@st.cache_data(ttl=60)
def load_snapshots():
    conn = psycopg2.connect(
        host=os.getenv("KOLSCAN_DB_HOST", "localhost"),
        dbname=os.getenv("KOLSCAN_DB_NAME", "kolscan"),
        user=os.getenv("KOLSCAN_DB_USER", "kolscan"),
        password=os.environ["KOLSCAN_DB_PASSWORD"],
    )
    try:
        return pd.read_sql_query(
            """
            SELECT
                snapshot_date,
                timeframe,
                wallet_address,
                wallet_name,
                wins,
                losses,
                pnl_usd,
                pnl_sol
            FROM kol_snapshots
            ORDER BY snapshot_date, timeframe
            """,
            conn,
        )
    finally:
        conn.close()


try:
    df = load_snapshots()
except Exception as exc:
    st.error(f"Could not load PostgreSQL data: {exc}")
    st.stop()

if df.empty:
    st.warning("No historical snapshots were found.")
    st.stop()

df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
df["timeframe"] = pd.to_numeric(df["timeframe"], errors="coerce")
df["wins"] = pd.to_numeric(df["wins"], errors="coerce").fillna(0)
df["losses"] = pd.to_numeric(df["losses"], errors="coerce").fillna(0)

timeframe_labels = {
    1: "Daily",
    7: "Weekly",
    30: "Monthly",
}

available_timeframes = sorted(
    df["timeframe"].dropna().astype(int).unique()
)

selected_timeframe = st.selectbox(
    "Leaderboard timeframe",
    available_timeframes,
    format_func=lambda x: timeframe_labels.get(x, str(x)),
)

data = df[df["timeframe"] == selected_timeframe].copy()

# Each date represents one observed leaderboard snapshot.
dates = sorted(data["snapshot_date"].dt.date.unique())
number_of_dates = len(dates)

latest_date = data["snapshot_date"].max()
latest = data[data["snapshot_date"] == latest_date].copy()

# Measure how often each wallet appeared in recorded snapshots.
history = (
    data.groupby("wallet_address")
    .agg(
        wallet_name=("wallet_name", "last"),
        appearances=("snapshot_date", "nunique"),
        total_wins=("wins", "max"),
        total_losses=("losses", "max"),
        first_seen=("snapshot_date", "min"),
        last_seen=("snapshot_date", "max"),
    )
    .reset_index()
)

history["consistency_pct"] = (
    100 * history["appearances"] / max(number_of_dates, 1)
)

history["observations"] = number_of_dates
history["sample_sufficient"] = history["appearances"] >= 5

# Current leaderboard membership is kept separate from historical persistence.
latest_wallets = set(latest["wallet_address"])
history["in_latest_snapshot"] = history["wallet_address"].isin(
    latest_wallets
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Wallets in latest snapshot", len(latest_wallets))
c2.metric("Wallets in history", history["wallet_address"].nunique())
c3.metric("Snapshots recorded", number_of_dates)
c4.metric("Latest snapshot", latest_date.strftime("%Y-%m-%d"))

st.divider()

st.subheader("Wallet consistency rankings")
st.write(
    "Consistency measures the percentage of recorded snapshots in which "
    "a wallet appeared. It is not a measure of trade-level win rate."
)

min_appearances = st.slider(
    "Minimum historical appearances",
    min_value=1,
    max_value=max(1, number_of_dates),
    value=min(2, max(1, number_of_dates)),
)

search = st.text_input("Search wallet name or address")

ranked = history[
    history["appearances"] >= min_appearances
].copy()

if search.strip():
    mask = (
        ranked["wallet_name"].fillna("").str.contains(
            search, case=False, regex=False
        )
        | ranked["wallet_address"].str.contains(
            search, case=False, regex=False
        )
    )
    ranked = ranked[mask]

ranked = ranked.sort_values(
    ["consistency_pct", "appearances", "wallet_name"],
    ascending=[False, False, True],
)

st.dataframe(
    ranked[
        [
            "wallet_name",
            "wallet_address",
            "appearances",
            "observations",
            "consistency_pct",
            "in_latest_snapshot",
            "first_seen",
            "last_seen",
        ]
    ].rename(
        columns={
            "wallet_name": "Wallet",
            "wallet_address": "Address",
            "appearances": "Appearances",
            "observations": "Recorded snapshots",
            "consistency_pct": "Consistency (%)",
            "in_latest_snapshot": "In latest snapshot",
            "first_seen": "First observed",
            "last_seen": "Last observed",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

st.caption(
    "The current dataset contains leaderboard snapshots, not complete "
    "trade histories. Consistency is based only on observed dates; "
    "missing collection dates are not treated as observations."
)

st.divider()
st.subheader("Wallet history")

options = ranked[["wallet_address", "wallet_name"]].drop_duplicates()
if options.empty:
    st.info("No wallets match these filters.")
    st.stop()

options["label"] = (
    options["wallet_name"].fillna("Unknown")
    + " — "
    + options["wallet_address"].str.slice(0, 8)
)

selected_address = st.selectbox(
    "Select a wallet",
    options["wallet_address"].tolist(),
    format_func=lambda address: options.loc[
        options["wallet_address"] == address, "label"
    ].iloc[0],
)

wallet_history = data[
    data["wallet_address"] == selected_address
].sort_values("snapshot_date")

st.write(f"**Wallet address:** `{selected_address}`")

fig = px.scatter(
    wallet_history,
    x="snapshot_date",
    y="pnl_usd",
    hover_data=["wallet_name", "wins", "losses"],
    title="Reported USD PnL across recorded snapshots",
    labels={
        "snapshot_date": "Snapshot date",
        "pnl_usd": "Reported USD PnL",
    },
)
st.plotly_chart(fig, use_container_width=True)

st.dataframe(
    wallet_history[
        [
            "snapshot_date",
            "wallet_name",
            "wins",
            "losses",
            "pnl_usd",
            "pnl_sol",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)

if not history["sample_sufficient"].all():
    st.caption(
        "Wallets with fewer than five appearances have limited historical "
        "evidence. Scores should be interpreted cautiously."
    )
