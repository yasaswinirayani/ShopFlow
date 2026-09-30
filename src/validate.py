"""
ShopFlow - Data Validation Module
Provides validation functions to check schema integrity, type correctness,
revenue calculations, duplicate detection, and row-count reconciliation.
"""

from typing import Dict, Any, List
import pandas as pd
import numpy as np


class ValidationError(Exception):
    """Raised when critical validation checks fail."""
    pass


def validate_required_columns(df: pd.DataFrame, required_columns: List[str]) -> bool:
    """
    Checks that all required columns are present in the DataFrame.
    Raises ValidationError if any are missing.
    """
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValidationError(f"Schema validation failed. Missing required columns: {missing}")
    return True


def validate_data_types(df: pd.DataFrame) -> bool:
    """
    Checks that dates and numeric columns have appropriate types.
    Raises ValidationError if types are invalid.
    """
    if not pd.api.types.is_datetime64_any_dtype(df["InvoiceDate"]):
        raise ValidationError(f"InvoiceDate must be datetime, found: {df['InvoiceDate'].dtype}")
    
    if not pd.api.types.is_numeric_dtype(df["Quantity"]):
        raise ValidationError(f"Quantity must be numeric, found: {df['Quantity'].dtype}")
        
    if not pd.api.types.is_numeric_dtype(df["UnitPrice"]):
        raise ValidationError(f"UnitPrice must be numeric, found: {df['UnitPrice'].dtype}")

    if "LineRevenue" in df.columns and not pd.api.types.is_numeric_dtype(df["LineRevenue"]):
        raise ValidationError(f"LineRevenue must be numeric, found: {df['LineRevenue'].dtype}")

    return True


def validate_revenue_calculation(df: pd.DataFrame, tolerance: float = 0.01) -> bool:
    """
    Checks that LineRevenue equals Quantity multiplied by UnitPrice.
    Raises ValidationError if discrepancy exceeds numerical tolerance.
    """
    if "LineRevenue" not in df.columns:
        raise ValidationError("LineRevenue column is missing.")
    
    expected_revenue = df["Quantity"] * df["UnitPrice"]
    diff = (df["LineRevenue"] - expected_revenue).abs()
    
    mismatches = diff > tolerance
    mismatch_count = mismatches.sum()
    if mismatch_count > 0:
        sample_error = df[mismatches][["Quantity", "UnitPrice", "LineRevenue"]].head(3)
        raise ValidationError(
            f"Revenue validation failed for {mismatch_count:,} records. Sample mismatches:\n{sample_error}"
        )
    return True


def validate_row_count_reconciliation(df_before: pd.DataFrame, df_after: pd.DataFrame) -> bool:
    """
    Reconciles row counts before and after transformation.
    Since ShopFlow preserves all records for full auditability,
    the row counts must match exactly.
    """
    rows_before = len(df_before)
    rows_after = len(df_after)
    if rows_before != rows_after:
        raise ValidationError(
            f"Row count reconciliation failed: before={rows_before:,}, after={rows_after:,} (difference: {rows_after - rows_before})"
        )
    return True


def generate_audit_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Generates a structured audit report summarizing:
    - Missing value counts per column.
    - Duplicate record counts.
    - Breakdown of all anomaly flags and transaction classifications.
    - Financial totals (gross sales, cancellations, net revenue).
    """
    total_rows = len(df)
    
    # Missing values
    missing_summary = {col: int(df[col].isna().sum()) for col in df.columns}
    
    # Flags summary
    audit_flags = {}
    flag_columns = [
        "is_duplicate",
        "is_cancelled",
        "is_negative_quantity",
        "is_zero_quantity",
        "is_negative_price",
        "is_zero_price",
        "is_missing_customer",
        "is_missing_description",
        "is_normal_sale"
    ]
    for flag in flag_columns:
        if flag in df.columns:
            cnt = int(df[flag].sum())
            audit_flags[flag] = {
                "count": cnt,
                "percentage": round((cnt / total_rows * 100) if total_rows > 0 else 0.0, 2)
            }
            
    # Financial metrics
    financials = {}
    if "LineRevenue" in df.columns:
        non_dup_df = df[~df.get("is_duplicate", False)]
        dup_df = df[df.get("is_duplicate", False)]
        
        # 1. Gross normal sales (Quantity > 0, UnitPrice > 0, not cancelled, non-duplicate)
        gross_sales = float(non_dup_df[non_dup_df.get("is_normal_sale", False)]["LineRevenue"].sum())
        
        # 2. Cancellations / customer returns (non-duplicate)
        cancelled_rev_non_dup = float(non_dup_df[non_dup_df.get("is_cancelled", False)]["LineRevenue"].sum())
        all_cancelled_rev = float(df[df.get("is_cancelled", False)]["LineRevenue"].sum())
        
        # 3. Accounting adjustments (UnitPrice < 0, e.g. Adjust bad debt)
        bad_debt_rev = float(non_dup_df[non_dup_df.get("is_negative_price", False)]["LineRevenue"].sum())
        
        # 4. Other negative quantity adjustments (damaged/lost stock, price = 0)
        other_neg_qty = non_dup_df[non_dup_df.get("is_negative_quantity", False) & ~non_dup_df.get("is_cancelled", False)]
        other_neg_qty_rev = float(other_neg_qty["LineRevenue"].sum())
        
        # 5. Duplicate revenue excluded
        duplicate_rev = float(dup_df["LineRevenue"].sum())
        
        # 6. Total Net Revenue across all non-duplicate records
        net_revenue = float(non_dup_df["LineRevenue"].sum())
        
        # Reconciled sum of individual components
        component_sum = gross_sales + cancelled_rev_non_dup + bad_debt_rev + other_neg_qty_rev
        
        financials = {
            "gross_normal_sales": round(gross_sales, 2),
            "cancelled_returns_offset_non_dup": round(cancelled_rev_non_dup, 2),
            "cancelled_returns_offset_all": round(all_cancelled_rev, 2),
            "bad_debt_accounting_adjustments": round(bad_debt_rev, 2),
            "other_negative_quantity_adjustments": round(other_neg_qty_rev, 2),
            "duplicate_revenue_excluded": round(duplicate_rev, 2),
            "net_revenue_non_duplicate": round(net_revenue, 2),
            "component_reconciled_sum": round(component_sum, 2),
            "reconciliation_difference": round(abs(component_sum - net_revenue), 4)
        }

    return {
        "total_records": total_rows,
        "missing_values": missing_summary,
        "audit_flags": audit_flags,
        "financial_summary": financials
    }


def run_all_validations(df_raw: pd.DataFrame, df_transformed: pd.DataFrame) -> Dict[str, Any]:
    """
    Runs all validation checks in sequence and returns the audit dictionary.
    Raises ValidationError if any critical rule fails.
    """
    validate_row_count_reconciliation(df_raw, df_transformed)
    
    required_cols = ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "Country"]
    validate_required_columns(df_transformed, required_cols)
    
    validate_data_types(df_transformed)
    validate_revenue_calculation(df_transformed)
    
    summary = generate_audit_summary(df_transformed)
    return summary
