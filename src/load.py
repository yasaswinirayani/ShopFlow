"""
ShopFlow - Database Loading Module
Handles schema initialization, DataFrame transformation mapping, and
transactional data loading into SQLite (data/processed/shopflow.db).
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any
import sqlite3
import pandas as pd
import numpy as np

# Ensure project root is available
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DEFAULT_DB_PATH = BASE_DIR / "data" / "processed" / "shopflow.db"
DEFAULT_SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"


def init_database(db_path: Path = DEFAULT_DB_PATH, schema_path: Path = DEFAULT_SCHEMA_PATH) -> None:
    """
    Initializes the SQLite database with tables and indexes defined in sql/schema.sql.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = schema_path.read_text(encoding="utf-8")
    
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_sql)
        conn.commit()


def prepare_dataframe_for_sqlite(df: pd.DataFrame) -> pd.DataFrame:
    """
    Maps pandas DataFrame columns to SQLite schema column names and formats:
    - Renames to snake_case.
    - Formats dates as standard ISO-8601 strings.
    - Converts booleans to integers (0/1).
    - Preserves null customer IDs as None/NULL.
    """
    df_out = pd.DataFrame()
    
    # Core columns
    df_out["invoice_no"] = df["InvoiceNo"].astype(str)
    df_out["stock_code"] = df["StockCode"].astype(str)
    df_out["description"] = df["Description"].astype(str)
    df_out["quantity"] = df["Quantity"].astype("int64")
    
    # Format InvoiceDate as ISO string
    if pd.api.types.is_datetime64_any_dtype(df["InvoiceDate"]):
        df_out["invoice_date"] = df["InvoiceDate"].dt.strftime("%Y-%m-%d %H:%M:%S")
    else:
        df_out["invoice_date"] = pd.to_datetime(df["InvoiceDate"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        
    df_out["unit_price"] = df["UnitPrice"].astype("float64")
    
    # Nullable customer_id: explicitly store as object containing Python int or None
    # so that SQLite inserts genuine NULL values rather than NaN floats
    df_out["customer_id"] = pd.Series(
        [int(v) if pd.notna(v) else None for v in df["CustomerID"]],
        index=df.index,
        dtype=object
    )
    df_out["country"] = df["Country"].astype(str)
    df_out["line_revenue"] = df["LineRevenue"].astype("float64")
    
    # Audit & classification boolean flags -> integers (0 or 1)
    flag_cols = [
        ("is_duplicate", "is_duplicate"),
        ("is_cancelled", "is_cancelled"),
        ("is_negative_quantity", "is_negative_quantity"),
        ("is_zero_quantity", "is_zero_quantity"),
        ("is_negative_price", "is_negative_price"),
        ("is_zero_price", "is_zero_price"),
        ("is_missing_customer", "is_missing_customer"),
        ("is_missing_description", "is_missing_description"),
        ("is_normal_sale", "is_normal_sale"),
    ]
    for src_col, dest_col in flag_cols:
        if src_col in df.columns:
            df_out[dest_col] = df[src_col].astype(int)
        else:
            df_out[dest_col] = 0

    df_out["transaction_category"] = df.get("transaction_category", "UNKNOWN").astype(str)
    
    return df_out


def load_transformed_data(
    df: pd.DataFrame,
    db_path: Path = DEFAULT_DB_PATH,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    full_refresh: bool = True
) -> int:
    """
    Loads transformed retail data into SQLite using transactions.
    
    If full_refresh=True:
    - Atomically clears previous records and resets identity counters within a transaction.
    - Appends all prepared records cleanly.
    - If any error occurs, rolls back completely.
    
    Returns the number of rows loaded.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Ensure schema exists
    init_database(db_path, schema_path)
    
    prepared_df = prepare_dataframe_for_sqlite(df)
    total_rows = len(prepared_df)
    
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN TRANSACTION;")
        
        if full_refresh:
            cursor.execute("DELETE FROM retail_transactions;")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'retail_transactions';")
        
        # Load in optimized chunks using pandas to_sql on the open connection
        prepared_df.to_sql(
            name="retail_transactions",
            con=conn,
            if_exists="append",
            index=False,
            chunksize=25000
        )
        
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"Database load failed; transaction rolled back. Error: {exc}") from exc
    finally:
        conn.close()
        
    return total_rows


def query_database_audit_metrics(db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    Queries the loaded database to verify row counts, null counts, flag totals,
    and financial reconciliation figures.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Total rows
        cursor.execute("SELECT COUNT(*) FROM retail_transactions;")
        total_rows = cursor.fetchone()[0]
        
        # Null counts
        cursor.execute("SELECT COUNT(*) FROM retail_transactions WHERE customer_id IS NULL;")
        missing_customers = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM retail_transactions WHERE is_missing_description = 1;")
        missing_descriptions = cursor.fetchone()[0]
        
        # Flags
        cursor.execute("SELECT COUNT(*) FROM retail_transactions WHERE is_duplicate = 1;")
        duplicates = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM retail_transactions WHERE is_cancelled = 1;")
        cancellations = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM retail_transactions WHERE is_normal_sale = 1;")
        normal_sales = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM retail_transactions WHERE is_negative_quantity = 1;")
        neg_quantities = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM retail_transactions WHERE is_zero_price = 1;")
        zero_prices = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM retail_transactions WHERE is_negative_price = 1;")
        neg_prices = cursor.fetchone()[0]
        
        # Category breakdown
        cursor.execute("""
            SELECT transaction_category, COUNT(*) 
            FROM retail_transactions 
            GROUP BY transaction_category 
            ORDER BY COUNT(*) DESC;
        """)
        categories = dict(cursor.fetchall())
        
        # Financial metrics
        # 1. Gross normal sales
        cursor.execute("""
            SELECT ROUND(SUM(line_revenue), 2)
            FROM retail_transactions
            WHERE is_normal_sale = 1;
        """)
        gross_sales = cursor.fetchone()[0] or 0.0

        # 2. Cancelled invoice revenue (non-duplicate)
        cursor.execute("""
            SELECT ROUND(SUM(line_revenue), 2)
            FROM retail_transactions
            WHERE is_cancelled = 1 AND is_duplicate = 0;
        """)
        cancelled_rev_non_dup = cursor.fetchone()[0] or 0.0

        # 3. Bad debt adjustment (negative price, non-duplicate)
        cursor.execute("""
            SELECT ROUND(SUM(line_revenue), 2)
            FROM retail_transactions
            WHERE is_negative_price = 1 AND is_duplicate = 0;
        """)
        bad_debt_rev = cursor.fetchone()[0] or 0.0

        # 4. Other negative quantity revenue (non-duplicate, non-cancelled)
        cursor.execute("""
            SELECT ROUND(SUM(line_revenue), 2)
            FROM retail_transactions
            WHERE is_negative_quantity = 1 AND is_cancelled = 0 AND is_duplicate = 0;
        """)
        other_neg_qty_rev = cursor.fetchone()[0] or 0.0

        # 5. Duplicate revenue excluded
        cursor.execute("""
            SELECT ROUND(SUM(line_revenue), 2)
            FROM retail_transactions
            WHERE is_duplicate = 1;
        """)
        duplicate_rev = cursor.fetchone()[0] or 0.0

        # 6. Total net revenue across all non-duplicate records
        cursor.execute("""
            SELECT ROUND(SUM(line_revenue), 2)
            FROM retail_transactions
            WHERE is_duplicate = 0;
        """)
        net_revenue_non_dup = cursor.fetchone()[0] or 0.0

        # 7. Total table revenue (all records including duplicates)
        cursor.execute("""
            SELECT ROUND(SUM(line_revenue), 2)
            FROM retail_transactions;
        """)
        total_table_revenue = cursor.fetchone()[0] or 0.0

    component_sum = round(gross_sales + cancelled_rev_non_dup + bad_debt_rev + other_neg_qty_rev, 2)
    discrepancy = round(abs(component_sum - net_revenue_non_dup), 4)

    return {
        "total_rows": total_rows,
        "missing_customers": missing_customers,
        "missing_descriptions": missing_descriptions,
        "duplicates": duplicates,
        "cancellations": cancellations,
        "normal_sales": normal_sales,
        "neg_quantities": neg_quantities,
        "zero_prices": zero_prices,
        "neg_prices": neg_prices,
        "category_counts": categories,
        "financials": {
            "gross_normal_sales": gross_sales,
            "cancelled_returns_non_dup": cancelled_rev_non_dup,
            "bad_debt_adjustments": bad_debt_rev,
            "other_neg_qty_adjustments": other_neg_qty_rev,
            "duplicate_revenue_excluded": duplicate_rev,
            "net_revenue_non_duplicate": net_revenue_non_dup,
            "total_table_revenue": total_table_revenue,
            "component_sum": component_sum,
            "discrepancy": discrepancy
        }
    }
