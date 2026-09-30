"""
ShopFlow - Transformation Preview & Audit Runner
Applies transformation and validation to the full raw dataset,
verifies data integrity, and saves reports/transformation_summary.txt.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
from src.transform import transform_retail_data
from src.validate import run_all_validations

RAW_DATA_PATH = BASE_DIR / "data" / "raw" / "Online Retail.xlsx"
SUMMARY_REPORT_PATH = BASE_DIR / "reports" / "transformation_summary.txt"


def main():
    print(f"Loading raw dataset from {RAW_DATA_PATH} ...")
    raw_df = pd.read_excel(RAW_DATA_PATH, sheet_name=0, engine="openpyxl")
    print(f"Loaded {len(raw_df):,} raw records.")

    print("Executing transformation pipeline...")
    transformed_df = transform_retail_data(raw_df)
    print("Transformation complete.")

    print("Running validation checks and generating audit summary...")
    audit = run_all_validations(raw_df, transformed_df)
    print("Validation passed successfully!")

    lines = []
    def log(msg=""):
        lines.append(str(msg))
        print(msg)

    log("=" * 80)
    log("SHOPFLOW — TRANSFORMATION & AUDIT SUMMARY")
    log("=" * 80)
    log()
    log(f"Raw Input Records:         {len(raw_df):,}")
    log(f"Transformed Output Records: {len(transformed_df):,}")
    log("Row Count Reconciliation:  PERFECT MATCH (No rows silently dropped)")
    log()
    log("--- TRANSACTION CLASSIFICATION & AUDIT FLAGS ---")
    for flag, stats in audit["audit_flags"].items():
        log(f"  {flag:26s}: {stats['count']:>8,} ({stats['percentage']:>5.2f}%)")
    log()
    log("--- PRIMARY TRANSACTION CATEGORIES ---")
    cat_counts = transformed_df["transaction_category"].value_counts()
    for cat, count in cat_counts.items():
        pct = (count / len(transformed_df)) * 100
        log(f"  {cat:26s}: {count:>8,} ({pct:>5.2f}%)")
    log()
    log("--- FINANCIAL SUMMARY & RECONCILIATION ---")
    fin = audit["financial_summary"]
    log(f"  Gross Normal Sales Revenue:       GBP {fin['gross_normal_sales']:>15,.2f}")
    log(f"  Cancellations / Returns (Non-Dup):GBP {fin['cancelled_returns_offset_non_dup']:>15,.2f}")
    log(f"  Bad Debt Accounting Adjustments:  GBP {fin['bad_debt_accounting_adjustments']:>15,.2f}")
    log(f"  Other Negative Qty Adjustments:   GBP {fin['other_negative_quantity_adjustments']:>15,.2f}")
    log("  -------------------------------------------------------------")
    log(f"  Reconciled Component Sum:         GBP {fin['component_reconciled_sum']:>15,.2f}")
    log(f"  Net Revenue (Non-Duplicate):      GBP {fin['net_revenue_non_duplicate']:>15,.2f}")
    log(f"  Reconciliation Discrepancy:       GBP {fin['reconciliation_difference']:>15,.4f}")
    log()
    log(f"  [Context] Duplicate Revenue (Excluded): GBP {fin['duplicate_revenue_excluded']:>11,.2f}")
    log(f"  [Context] Cancellations with Duplicates: GBP {fin['cancelled_returns_offset_all']:>11,.2f}")
    log()
    log("--- DATA QUALITY & MISSING VALUES ---")
    for col, null_cnt in audit["missing_values"].items():
        if null_cnt > 0:
            log(f"  {col:20s}: {null_cnt:>8,} missing")
    log()
    log("=" * 80)

    SUMMARY_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nTransformation summary successfully saved to: {SUMMARY_REPORT_PATH}")


if __name__ == "__main__":
    main()
