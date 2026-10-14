import pandas as pd
from datetime import date
import psycopg
import os

conn = psycopg.connect(
    host="localhost",
    dbname="kolscan",
    user="kolscan",
    password=os.environ["KOLSCAN_DB_PASSWORD"]
)

cursor = conn.cursor()

print("Connected to Postgresql")

today = date.today()
csv_file = f"snapshots/{today}.csv"

def clean_pnl_usd(value):
    value = value.strip()
    value = value.replace('(', '').replace(')', '')
    value = value.replace('$', '').replace(',', '')

    return float(value)

def clean_pnl_sol(value):
    number = float(value.split()[0].replace(',', ''))
    return number

def load_csv():
    df = pd.read_csv(csv_file)

    df["pnl_usd"] = df["pnl_usd"].apply(clean_pnl_usd)
    df["pnl_sol"] = df["pnl_sol"].apply(clean_pnl_sol)

    df = df.rename(columns={
        "period": "timeframe",
        "win": "wins",
        "loss": "losses"
    })

    df["snapshot_date"] = today
    print(df.head())
    print(df.columns)

    return df

def update_db():
    df = load_csv()

    insert_query = """
        INSERT INTO kol_snapshots (
            snapshot_date,
            timeframe,
            wallet_address,
            wallet_name,
            wallet_avatar,
            account_name,
            wins,
            losses,
            pnl_usd,
            pnl_sol,
            telegram,
            twitter
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (snapshot_date, timeframe, wallet_address)
        DO NOTHING
    """

    for _, row in df.iterrows():
        cursor.execute(insert_query, (
            row["snapshot_date"],
            row["timeframe"],
            row["wallet_address"],
            row["wallet_name"],
            row["wallet_avatar"],
            row["account_name"],
            row["wins"],
            row["losses"],
            row["pnl_usd"],
            row["pnl_sol"],
            row["telegram"],
            row["twitter"]
        ))

    conn.commit()

update_db()



