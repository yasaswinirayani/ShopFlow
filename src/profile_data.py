"""
ShopFlow - Dataset Exploration and Profiling Script
Inspects data/raw/Online Retail.xlsx and produces a profiling report.
"""

from pathlib import Path
import pandas as pd
import openpyxl


from typing import Optional


def profile_dataset(file_path: Path, output_report_path: Path, df: Optional[pd.DataFrame] = None):
    if df is None:
        print(f"Loading dataset from: {file_path} ...")
        wb = openpyxl.load_workbook(file_path, read_only=True)
        sheet_names = wb.sheetnames
        wb.close()
        df = pd.read_excel(file_path, sheet_name=0, engine="openpyxl")
    else:
        sheet_names = [file_path.stem if file_path else "Primary Data"]
    
    lines = []
    def log(msg=""):
        lines.append(str(msg))
        print(msg)

    log("=" * 80)
    log("SHOPFLOW — DATASET PROFILING & EXPLORATION REPORT")
    log("=" * 80)
    log()
    
    # Basic Metadata
    log("--- 1. BASIC DATASET METADATA ---")
    log(f"File Path: {file_path}")
    log(f"Available Sheets: {sheet_names}")
    log(f"Active Sheet Analyzed: {sheet_names[0]}")
    log(f"Total Rows: {len(df):,}")
    log(f"Total Columns: {len(df.columns)}")
    log()
    
    # Column details and types
    log("--- 2. COLUMNS & DATA TYPES ---")
    col_info = pd.DataFrame({
        "Column": df.columns,
        "Dtype": df.dtypes.astype(str),
        "Non-Null Count": df.notnull().sum().values,
        "Null Count": df.isnull().sum().values,
        "Null %": (df.isnull().sum() / len(df) * 100).round(2).values
    })
    log(col_info.to_string(index=False))
    log()

    # Sample records
    log("--- 3. SAMPLE ROWS (First 5) ---")
    log(df.head(5).to_string())
    log()

    # Duplicates
    log("--- 4. DUPLICATE RECORDS ---")
    duplicate_count = df.duplicated().sum()
    duplicate_pct = (duplicate_count / len(df)) * 100
    log(f"Exact Duplicate Rows: {duplicate_count:,} ({duplicate_pct:.2f}%)")
    log()

    # Date Range
    log("--- 5. TEMPORAL COVERAGE (InvoiceDate) ---")
    if "InvoiceDate" in df.columns:
        min_date = df["InvoiceDate"].min()
        max_date = df["InvoiceDate"].max()
        log(f"Earliest Invoice Date: {min_date}")
        log(f"Latest Invoice Date:   {max_date}")
        log(f"Timespan: {(max_date - min_date).days} days")
    else:
        log("InvoiceDate column not found.")
    log()

    # Numeric Summary Stats
    log("--- 6. NUMERIC SUMMARY STATISTICS ---")
    stats = df[["Quantity", "UnitPrice"]].describe().round(4)
    log(stats.to_string())
    log()

    # Specific Business Anomalies & Edge Cases
    log("--- 7. BUSINESS LOGIC & ANOMALY ANALYSIS ---")
    
    # InvoiceNo patterns (Cancellations)
    df["InvoiceNo_str"] = df["InvoiceNo"].astype(str)
    cancelled_mask = df["InvoiceNo_str"].str.startswith("C", na=False)
    cancelled_count = cancelled_mask.sum()
    cancelled_pct = (cancelled_count / len(df)) * 100
    log(f"Cancelled Invoices (InvoiceNo starts with 'C'): {cancelled_count:,} ({cancelled_pct:.2f}%)")

    # Negative Quantities
    neg_qty_mask = df["Quantity"] < 0
    neg_qty_count = neg_qty_mask.sum()
    neg_qty_cancelled_overlap = (neg_qty_mask & cancelled_mask).sum()
    neg_qty_non_cancelled = (neg_qty_mask & ~cancelled_mask).sum()
    log(f"Total Negative Quantity Records: {neg_qty_count:,}")
    log(f"  - Associated with cancelled invoices ('C'): {neg_qty_cancelled_overlap:,}")
    log(f"  - Negative quantity but NOT starting with 'C': {neg_qty_non_cancelled:,}")

    # Zero or Negative Unit Prices
    zero_price_mask = df["UnitPrice"] == 0
    neg_price_mask = df["UnitPrice"] < 0
    log(f"Records with Zero Unit Price: {zero_price_mask.sum():,}")
    log(f"Records with Negative Unit Price: {neg_price_mask.sum():,}")

    # Missing CustomerID
    missing_cust_mask = df["CustomerID"].isnull()
    missing_cust_count = missing_cust_mask.sum()
    missing_cust_pct = (missing_cust_count / len(df)) * 100
    log(f"Missing CustomerID Records: {missing_cust_count:,} ({missing_cust_pct:.2f}%)")
    log()

    # Domain Interpretation
    log("--- 8. DATA ENGINEERING & DOMAIN INTERPRETATIONS ---")
    log("1. Cancelled Invoices & Negative Quantities:")
    log("   - Rows with InvoiceNo starting with 'C' indicate order cancellations or customer returns.")
    log("   - The negative Quantity reflects stock returning to inventory and offsets gross sales.")
    log("   - Non-cancelled negative quantities often indicate damaged stock, inventory write-offs,")
    log("     or administrative corrections (e.g. 'lost', 'damaged', 'check').")
    log()
    log("2. Zero & Negative Unit Prices:")
    log("   - Zero UnitPrice records frequently correspond to promotional free gifts, samples,")
    log("     or internal adjustments.")
    log("   - Negative UnitPrice records (e.g. 'Adjust bad debt') are accounting adjustments rather")
    log("     than consumer product sales.")
    log()
    log("3. Missing Customer IDs (~25% of dataset):")
    log("   - Missing CustomerIDs represent anonymous or guest checkouts where the buyer did not")
    log("     log into a registered account.")
    log("   - While these cannot be used for customer-level cohort or retention analytics, they ARE")
    log("     valid revenue transactions for total sales and product performance metrics.")
    log()
    log("4. Duplicate Records:")
    log(f"   - {duplicate_count:,} rows are complete duplicates across all columns.")
    log("   - In a production pipeline, exact duplicates should be deduplicated to avoid double-counting sales.")
    log("=" * 80)

    # Clean temporary column
    df.drop(columns=["InvoiceNo_str"], inplace=True)

    # Save to report file
    output_report_path.parent.mkdir(parents=True, exist_ok=True)
    output_report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport successfully saved to: {output_report_path}")


if __name__ == "__main__":
    # Define project root relative to this script
    BASE_DIR = Path(__file__).resolve().parent.parent
    RAW_DATA_PATH = BASE_DIR / "data" / "raw" / "Online Retail.xlsx"
    REPORT_PATH = BASE_DIR / "reports" / "dataset_profile.txt"
    
    if not RAW_DATA_PATH.exists():
        print(f"ERROR: Dataset not found at {RAW_DATA_PATH}")
    else:
        profile_dataset(RAW_DATA_PATH, REPORT_PATH)
