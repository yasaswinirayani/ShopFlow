"""
ShopFlow - ETL Pipeline Orchestration Module
Coordinates end-to-end extraction, profiling, transformation, validation,
transactional loading into SQLite, and post-load database verification.
"""

import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.profile_data import profile_dataset
from src.transform import transform_retail_data
from src.validate import run_all_validations, ValidationError
from src.load import (
    load_transformed_data,
    query_database_audit_metrics,
    DEFAULT_DB_PATH,
    DEFAULT_SCHEMA_PATH
)

DEFAULT_RAW_DATA_PATH = BASE_DIR / "data" / "raw" / "Online Retail.xlsx"
DEFAULT_PROFILE_REPORT = BASE_DIR / "reports" / "pipeline_dataset_profile.txt"
DEFAULT_PIPELINE_SUMMARY = BASE_DIR / "reports" / "pipeline_run_summary.txt"


class PipelineError(Exception):
    """Raised when an unrecoverable ETL pipeline error occurs."""
    pass


def run_pipeline(
    raw_data_path: Path = DEFAULT_RAW_DATA_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    schema_path: Path = DEFAULT_SCHEMA_PATH,
    profile_report_path: Optional[Path] = DEFAULT_PROFILE_REPORT,
    summary_report_path: Path = DEFAULT_PIPELINE_SUMMARY,
    full_refresh: bool = True
) -> Dict[str, Any]:
    """
    Executes the ShopFlow ETL pipeline in 8 coordinated steps:
    1. Verify raw dataset existence.
    2. Extract raw dataset.
    3. Generate/update profiling report.
    4. Transform data & classify transactions.
    5. Validate transformed data & reconcile row counts.
    6. Transactionally load data into SQLite.
    7. Query database for post-load verification.
    8. Write pipeline execution summary report.
    
    Returns a comprehensive execution result dictionary.
    Raises PipelineError if any critical step fails.
    """
    start_time = time.time()
    steps_status = {}
    logs = []

    def log(msg: str = ""):
        logs.append(str(msg))
        print(msg)

    log("=" * 80)
    log("SHOPFLOW — ETL PIPELINE EXECUTION")
    log("=" * 80)
    log(f"Execution started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log()

    # -------------------------------------------------------------------------
    # Step 1: Verify raw dataset exists
    # -------------------------------------------------------------------------
    log("[Step 1/8] Verifying raw dataset existence...")
    if not raw_data_path.exists():
        err_msg = f"Raw dataset not found at: {raw_data_path}"
        log(f"ERROR: {err_msg}")
        steps_status["step_1_verify_raw"] = "FAILED"
        _write_failure_summary(summary_report_path, steps_status, err_msg, logs)
        raise PipelineError(err_msg)
    
    steps_status["step_1_verify_raw"] = "SUCCESS"
    log(f"  Found dataset: {raw_data_path} ({raw_data_path.stat().st_size:,} bytes)")

    # -------------------------------------------------------------------------
    # Step 2: Extract raw dataset
    # -------------------------------------------------------------------------
    log("\n[Step 2/8] Extracting raw dataset into memory...")
    try:
        if raw_data_path.suffix.lower() in [".xlsx", ".xls"]:
            raw_df = pd.read_excel(raw_data_path, sheet_name=0, engine="openpyxl")
        elif raw_data_path.suffix.lower() == ".csv":
            raw_df = pd.read_csv(raw_data_path)
        else:
            raw_df = pd.read_excel(raw_data_path, sheet_name=0)
            
        raw_row_count = len(raw_df)
        steps_status["step_2_extract"] = "SUCCESS"
        log(f"  Extracted {raw_row_count:,} records across {len(raw_df.columns)} columns.")
    except Exception as exc:
        err_msg = f"Failed to extract dataset: {exc}"
        log(f"ERROR: {err_msg}")
        steps_status["step_2_extract"] = "FAILED"
        _write_failure_summary(summary_report_path, steps_status, err_msg, logs)
        raise PipelineError(err_msg) from exc

    # -------------------------------------------------------------------------
    # Step 3: Profile dataset
    # -------------------------------------------------------------------------
    log("\n[Step 3/8] Profiling dataset...")
    if profile_report_path:
        try:
            profile_dataset(raw_data_path, profile_report_path, df=raw_df)
            steps_status["step_3_profile"] = "SUCCESS"
            log(f"  Profiling report saved to: {profile_report_path}")
        except Exception as exc:
            err_msg = f"Profiling failed: {exc}"
            log(f"WARNING: {err_msg}")
            steps_status["step_3_profile"] = f"FAILED: {exc}"
    else:
        steps_status["step_3_profile"] = "SKIPPED"
        log("  Profiling step skipped (no report path specified).")

    # -------------------------------------------------------------------------
    # Step 4: Transform data
    # -------------------------------------------------------------------------
    log("\n[Step 4/8] Transforming data and classifying transactions...")
    try:
        transformed_df = transform_retail_data(raw_df)
        transformed_row_count = len(transformed_df)
        steps_status["step_4_transform"] = "SUCCESS"
        log(f"  Transformation complete: {transformed_row_count:,} rows, {len(transformed_df.columns)} columns.")
    except Exception as exc:
        err_msg = f"Data transformation failed: {exc}"
        log(f"ERROR: {err_msg}")
        steps_status["step_4_transform"] = "FAILED"
        _write_failure_summary(summary_report_path, steps_status, err_msg, logs)
        raise PipelineError(err_msg) from exc

    # -------------------------------------------------------------------------
    # Step 5: Validate transformed DataFrame
    # -------------------------------------------------------------------------
    log("\n[Step 5/8] Running data validation and reconciliation rules...")
    try:
        audit_summary = run_all_validations(raw_df, transformed_df)
        steps_status["step_5_validate"] = "SUCCESS"
        log("  All validation checks passed: Schema, Types, Revenue, and Row Counts.")
    except ValidationError as val_err:
        err_msg = f"Validation failed: {val_err}"
        log(f"ERROR: {err_msg}")
        steps_status["step_5_validate"] = "FAILED"
        _write_failure_summary(summary_report_path, steps_status, err_msg, logs)
        raise PipelineError(err_msg) from val_err
    except Exception as exc:
        err_msg = f"Unexpected validation error: {exc}"
        log(f"ERROR: {err_msg}")
        steps_status["step_5_validate"] = "FAILED"
        _write_failure_summary(summary_report_path, steps_status, err_msg, logs)
        raise PipelineError(err_msg) from exc

    # -------------------------------------------------------------------------
    # Step 6: Load data into SQLite transactionally
    # -------------------------------------------------------------------------
    log(f"\n[Step 6/8] Loading data into SQLite database ({db_path}) ...")
    try:
        loaded_rows = load_transformed_data(
            df=transformed_df,
            db_path=db_path,
            schema_path=schema_path,
            full_refresh=full_refresh
        )
        steps_status["step_6_load"] = "SUCCESS"
        log(f"  Transaction committed: {loaded_rows:,} records loaded.")
    except Exception as exc:
        err_msg = f"Database loading failed: {exc}"
        log(f"ERROR: {err_msg}")
        steps_status["step_6_load"] = "FAILED"
        _write_failure_summary(summary_report_path, steps_status, err_msg, logs)
        raise PipelineError(err_msg) from exc

    # -------------------------------------------------------------------------
    # Step 7: Post-load database verification
    # -------------------------------------------------------------------------
    log("\n[Step 7/8] Running post-load database verification queries...")
    try:
        db_metrics = query_database_audit_metrics(db_path)
        
        # Verify row count
        if db_metrics["total_rows"] != raw_row_count:
            raise PipelineError(
                f"Row count mismatch in DB! Expected {raw_row_count:,}, found {db_metrics['total_rows']:,}"
            )
            
        # Verify financial discrepancy
        if db_metrics["financials"]["discrepancy"] > 0.01:
            raise PipelineError(
                f"Financial discrepancy detected in DB: £{db_metrics['financials']['discrepancy']:.4f}"
            )
            
        steps_status["step_7_verify_db"] = "SUCCESS"
        log("  Database post-load verification: 100% row match & exact financial reconciliation.")
    except Exception as exc:
        err_msg = f"Post-load verification failed: {exc}"
        log(f"ERROR: {err_msg}")
        steps_status["step_7_verify_db"] = "FAILED"
        _write_failure_summary(summary_report_path, steps_status, err_msg, logs)
        raise PipelineError(err_msg) from exc

    # -------------------------------------------------------------------------
    # Step 8: Generate Pipeline Summary Report
    # -------------------------------------------------------------------------
    elapsed_time = round(time.time() - start_time, 2)
    steps_status["step_8_summary"] = "SUCCESS"
    log(f"\n[Step 8/8] Writing pipeline run summary to {summary_report_path} ...")
    
    fin = db_metrics["financials"]
    summary_lines = [
        "=" * 80,
        "SHOPFLOW — ETL PIPELINE EXECUTION SUMMARY",
        "=" * 80,
        f"Execution Timestamp:       {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total Execution Time:      {elapsed_time:.2f} seconds",
        f"Overall Pipeline Status:   SUCCESS",
        "",
        "--- STEP STATUS BREAKDOWN ---",
    ]
    for step_name, status in steps_status.items():
        summary_lines.append(f"  {step_name:<26s}: {status}")
        
    summary_lines.extend([
        "",
        "--- RECORD RECONCILIATION ---",
        f"  Raw Input Records:         {raw_row_count:>10,}",
        f"  Transformed Records:       {transformed_row_count:>10,}",
        f"  Database Loaded Records:   {db_metrics['total_rows']:>10,}",
        f"  Row Match Reconciliation:  PERFECT MATCH (0 dropped)",
        "",
        "--- DATA QUALITY & NULL COUNTS ---",
        f"  Missing Customer IDs (NULL): {db_metrics['missing_customers']:>8,} (Guest checkouts preserved)",
        f"  Missing Descriptions:        {db_metrics['missing_descriptions']:>8,} (Flagged as UNSPECIFIED)",
        f"  Exact Duplicate Records:     {db_metrics['duplicates']:>8,} (Flagged is_duplicate=1)",
        "",
        "--- TRANSACTION CLASSIFICATIONS ---",
        f"  Normal Sales:                {db_metrics['normal_sales']:>8,} ({db_metrics['normal_sales']/db_metrics['total_rows']*100:.2f}%)",
        f"  Cancelled Orders:            {db_metrics['cancellations']:>8,} ({db_metrics['cancellations']/db_metrics['total_rows']*100:.2f}%)",
        f"  Negative Quantities:         {db_metrics['neg_quantities']:>8,} ({db_metrics['neg_quantities']/db_metrics['total_rows']*100:.2f}%)",
        f"  Zero Price Items:            {db_metrics['zero_prices']:>8,} ({db_metrics['zero_prices']/db_metrics['total_rows']*100:.2f}%)",
        f"  Negative Price Adjustments:  {db_metrics['neg_prices']:>8,} ({db_metrics['neg_prices']/db_metrics['total_rows']*100:.2f}%)",
        "",
        "--- FINANCIAL TOTALS & RECONCILIATION ---",
        f"  (A) Gross Normal Sales Revenue:       GBP {fin['gross_normal_sales']:>15,.2f}",
        f"  (B) Cancellations / Returns (Non-Dup):GBP {fin['cancelled_returns_non_dup']:>15,.2f}",
        f"  (C) Bad Debt Accounting Adjustments:  GBP {fin['bad_debt_adjustments']:>15,.2f}",
        f"  (D) Other Negative Qty Adjustments:   GBP {fin['other_neg_qty_adjustments']:>15,.2f}",
        "  -------------------------------------------------------------",
        f"  (E) Reconciled Component Sum (A+B+C+D):GBP {fin['component_sum']:>15,.2f}",
        f"  (F) Net Revenue (All Non-Duplicate):  GBP {fin['net_revenue_non_duplicate']:>15,.2f}",
        f"  Discrepancy (E - F):                  GBP {fin['discrepancy']:>15,.4f}",
        "",
        f"  [Context] Duplicate Revenue Excluded: GBP {fin['duplicate_revenue_excluded']:>15,.2f}",
        f"  [Context] Total Table Revenue:        GBP {fin['total_table_revenue']:>15,.2f}",
        "=" * 80
    ])

    summary_report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_report_path.write_text("\n".join(summary_lines), encoding="utf-8")
    log(f"  Summary saved successfully.")
    log(f"\nPipeline finished successfully in {elapsed_time:.2f} seconds.")
    log("=" * 80)

    return {
        "status": "SUCCESS",
        "elapsed_seconds": elapsed_time,
        "raw_rows": raw_row_count,
        "loaded_rows": db_metrics["total_rows"],
        "steps_status": steps_status,
        "db_metrics": db_metrics
    }


def _write_failure_summary(
    summary_path: Path,
    steps_status: Dict[str, str],
    error_message: str,
    logs: list
):
    """Writes a detailed failure report to the summary path when pipeline halts."""
    summary_lines = [
        "=" * 80,
        "SHOPFLOW — ETL PIPELINE EXECUTION SUMMARY (FAILED)",
        "=" * 80,
        f"Execution Timestamp:     {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Overall Pipeline Status: FAILED",
        f"Failure Reason:          {error_message}",
        "",
        "--- STEP STATUS BREAKDOWN ---",
    ]
    for step_name, status in steps_status.items():
        summary_lines.append(f"  {step_name:<26s}: {status}")
    summary_lines.append("=" * 80)
    
    try:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        run_pipeline()
        sys.exit(0)
    except PipelineError as p_err:
        print(f"\nPIPELINE EXECUTION FAILED: {p_err}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\nUNEXPECTED FATAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
