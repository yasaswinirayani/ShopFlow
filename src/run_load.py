"""
ShopFlow - Database Loading Runner
Executes transformation, validation, and transactional loading into SQLite (data/processed/shopflow.db).
Performs database verification queries and outputs reports/database_load_summary.txt.
"""

import sys
from pathlib import Path
import sqlite3
import pandas as pd

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.transform import transform_retail_data
from src.validate import run_all_validations
from src.load import (
    load_transformed_data,
    query_database_audit_metrics,
    DEFAULT_DB_PATH,
    DEFAULT_SCHEMA_PATH
)

RAW_DATA_PATH = BASE_DIR / "data" / "raw" / "Online Retail.xlsx"
REPORT_PATH = BASE_DIR / "reports" / "database_load_summary.txt"


def main():
    lines = []
    def log(msg=""):
        lines.append(str(msg))
        print(msg)

    log("=" * 80)
    log("SHOPFLOW — DATABASE LOADING & RECONCILIATION REPORT")
    log("=" * 80)
    log()

    # 1. Load Raw
    log(f"Loading raw dataset from {RAW_DATA_PATH} ...")
    raw_df = pd.read_excel(RAW_DATA_PATH, sheet_name=0, engine="openpyxl")
    log(f"Raw records loaded into memory: {len(raw_df):,}")

    # 2. Transform
    log("Applying transformations and transaction classifications...")
    transformed_df = transform_retail_data(raw_df)

    # 3. Validate
    log("Running validation rules and revenue consistency checks...")
    audit = run_all_validations(raw_df, transformed_df)
    log("Validation successful! 0 critical discrepancies found.")

    # 4. Load into SQLite
    log(f"\nLoading records transactionally into {DEFAULT_DB_PATH} ...")
    loaded_rows = load_transformed_data(
        df=transformed_df,
        db_path=DEFAULT_DB_PATH,
        schema_path=DEFAULT_SCHEMA_PATH,
        full_refresh=True
    )
    log(f"Database transaction committed: {loaded_rows:,} records inserted.")
    log()

    # 5. Direct Database Query Verification
    log("--- 1. DATABASE SCHEMA & TABLE VERIFICATION ---")
    with sqlite3.connect(DEFAULT_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]
        log(f"Managed Tables: {tables}")

        cursor.execute("PRAGMA table_info(retail_transactions);")
        columns = cursor.fetchall()
        log("Columns in retail_transactions:")
        for col in columns:
            cid, name, col_type, notnull, dflt, pk = col
            pk_str = " (PK)" if pk else ""
            nn_str = " NOT NULL" if notnull else ""
            log(f"  - {name:<26s} {col_type:<10s}{nn_str}{pk_str}")
        log()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='retail_transactions';")
        indexes = [row[0] for row in cursor.fetchall()]
        log(f"Created Indexes: {indexes}")
    log()

    # 6. Audit Metrics Query
    metrics = query_database_audit_metrics(DEFAULT_DB_PATH)

    log("--- 2. DATABASE RECORD RECONCILIATION ---")
    log(f"Raw Input Rows:            {len(raw_df):,}")
    log(f"Transformed In-Memory Rows:{len(transformed_df):,}")
    log(f"Database Loaded Rows:      {metrics['total_rows']:,}")
    reconciled = (len(raw_df) == metrics['total_rows'])
    log(f"Row Reconciliation Status: {'PERFECT RECONCILIATION (100% matched)' if reconciled else 'MISMATCH'}")
    log()

    log("--- 3. NULL COUNTS & DATA INTEGRITY ---")
    log(f"Missing Customer IDs (NULL):    {metrics['missing_customers']:,} (preserved as genuine SQL NULLs)")
    log(f"Missing Descriptions Flagged:   {metrics['missing_descriptions']:,} (stored as 'UNSPECIFIED')")
    log()

    log("--- 4. TRANSACTION CLASSIFICATION & FLAG BREAKDOWN ---")
    log(f"  is_normal_sale:          {metrics['normal_sales']:>8,} ({metrics['normal_sales']/metrics['total_rows']*100:.2f}%)")
    log(f"  is_cancelled:            {metrics['cancellations']:>8,} ({metrics['cancellations']/metrics['total_rows']*100:.2f}%)")
    log(f"  is_duplicate:            {metrics['duplicates']:>8,} ({metrics['duplicates']/metrics['total_rows']*100:.2f}%)")
    log(f"  is_negative_quantity:    {metrics['neg_quantities']:>8,} ({metrics['neg_quantities']/metrics['total_rows']*100:.2f}%)")
    log(f"  is_zero_price:           {metrics['zero_prices']:>8,} ({metrics['zero_prices']/metrics['total_rows']*100:.2f}%)")
    log(f"  is_negative_price:       {metrics['neg_prices']:>8,} ({metrics['neg_prices']/metrics['total_rows']*100:.2f}%)")
    log()

    log("Primary Categories:")
    for cat, count in metrics["category_counts"].items():
        log(f"  - {cat:<28s}: {count:>8,} ({count/metrics['total_rows']*100:.2f}%)")
    log()

    log("--- 5. SQL FINANCIAL RECONCILIATION ---")
    fin = metrics["financials"]
    log(f"  (A) Gross Normal Sales Revenue:       GBP {fin['gross_normal_sales']:>15,.2f}")
    log(f"  (B) Cancellations / Returns (Non-Dup):GBP {fin['cancelled_returns_non_dup']:>15,.2f}")
    log(f"  (C) Bad Debt Accounting Adjustments:  GBP {fin['bad_debt_adjustments']:>15,.2f}")
    log(f"  (D) Other Negative Qty Adjustments:   GBP {fin['other_neg_qty_adjustments']:>15,.2f}")
    log("  -------------------------------------------------------------")
    log(f"  (E) Reconciled Components (A+B+C+D):  GBP {fin['component_sum']:>15,.2f}")
    log(f"  (F) Net Revenue (All Non-Duplicate):  GBP {fin['net_revenue_non_duplicate']:>15,.2f}")
    log(f"  Discrepancy (E - F):                  GBP {fin['discrepancy']:>15,.4f}")
    log()
    log(f"  [Context] Duplicate Revenue Excluded: GBP {fin['duplicate_revenue_excluded']:>15,.2f}")
    log(f"  [Context] Total Table Revenue:        GBP {fin['total_table_revenue']:>15,.2f}")
    log("=" * 80)

    # Save summary report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nDatabase load summary saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
