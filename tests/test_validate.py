"""
Unit tests for src/validate.py
Tests validation rules, type checks, revenue precision, and row-count reconciliation.
"""

import pytest
import pandas as pd
import numpy as np
from src.validate import (
    ValidationError,
    validate_required_columns,
    validate_data_types,
    validate_revenue_calculation,
    validate_row_count_reconciliation,
    generate_audit_summary,
    run_all_validations
)
from src.transform import transform_retail_data


@pytest.fixture
def valid_transformed_df():
    """Returns a valid transformed DataFrame that passes all validation rules."""
    return pd.DataFrame({
        "InvoiceNo": ["536365", "C536366"],
        "StockCode": ["85123A", "85123A"],
        "Description": ["WHITE HEART", "WHITE HEART"],
        "Quantity": [6, -2],
        "InvoiceDate": pd.to_datetime(["2010-12-01 08:26:00", "2010-12-01 09:00:00"]),
        "UnitPrice": [2.55, 2.55],
        "CustomerID": pd.Series([17850, 17850], dtype="Int64"),
        "Country": ["United Kingdom", "United Kingdom"],
        "LineRevenue": [15.30, -5.10],
        "is_duplicate": [False, False],
        "is_cancelled": [False, True],
        "is_negative_quantity": [False, True],
        "is_zero_quantity": [False, False],
        "is_negative_price": [False, False],
        "is_zero_price": [False, False],
        "is_missing_customer": [False, False],
        "is_normal_sale": [True, False],
        "transaction_category": ["NORMAL_SALE", "CANCELLED_INVOICE"]
    })


def test_validate_required_columns(valid_transformed_df):
    required = ["InvoiceNo", "StockCode", "Quantity", "UnitPrice", "InvoiceDate", "Country"]
    assert validate_required_columns(valid_transformed_df, required) is True
    
    with pytest.raises(ValidationError, match="Missing required columns"):
        validate_required_columns(valid_transformed_df.drop(columns=["Quantity"]), required)


def test_validate_data_types(valid_transformed_df):
    assert validate_data_types(valid_transformed_df) is True
    
    # Check invalid date type
    bad_dates = valid_transformed_df.copy()
    bad_dates["InvoiceDate"] = "not-a-datetime"
    with pytest.raises(ValidationError, match="InvoiceDate must be datetime"):
        validate_data_types(bad_dates)
        
    # Check non-numeric quantity
    bad_qty = valid_transformed_df.copy()
    bad_qty["Quantity"] = "six"
    with pytest.raises(ValidationError, match="Quantity must be numeric"):
        validate_data_types(bad_qty)


def test_validate_revenue_calculation(valid_transformed_df):
    assert validate_revenue_calculation(valid_transformed_df) is True
    
    # Corrupt revenue
    corrupted = valid_transformed_df.copy()
    corrupted.loc[0, "LineRevenue"] = 9999.99
    with pytest.raises(ValidationError, match="Revenue validation failed"):
        validate_revenue_calculation(corrupted)


def test_validate_row_count_reconciliation():
    df_raw = pd.DataFrame({"a": [1, 2, 3]})
    df_transformed = pd.DataFrame({"a": [1, 2, 3]})
    assert validate_row_count_reconciliation(df_raw, df_transformed) is True
    
    # Dropped row
    df_dropped = pd.DataFrame({"a": [1, 2]})
    with pytest.raises(ValidationError, match="Row count reconciliation failed"):
        validate_row_count_reconciliation(df_raw, df_dropped)


def test_generate_audit_summary(valid_transformed_df):
    summary = generate_audit_summary(valid_transformed_df)
    
    assert summary["total_records"] == 2
    assert "audit_flags" in summary
    assert summary["audit_flags"]["is_normal_sale"]["count"] == 1
    assert summary["audit_flags"]["is_cancelled"]["count"] == 1
    assert summary["financial_summary"]["gross_normal_sales"] == 15.30
    assert summary["financial_summary"]["cancelled_returns_offset_non_dup"] == -5.10
    assert summary["financial_summary"]["net_revenue_non_duplicate"] == 10.20
    assert summary["financial_summary"]["reconciliation_difference"] == 0.0


def test_run_all_validations_end_to_end():
    raw_df = pd.DataFrame({
        "InvoiceNo": ["536365", "536365"],
        "StockCode": ["85123A", "85123A"],
        "Description": ["WHITE HEART", "WHITE HEART"],
        "Quantity": [6, 6],
        "InvoiceDate": ["2010-12-01 08:26:00", "2010-12-01 08:26:00"],
        "UnitPrice": [2.55, 2.55],
        "CustomerID": [17850.0, 17850.0],
        "Country": ["United Kingdom", "United Kingdom"]
    })
    
    transformed_df = transform_retail_data(raw_df)
    audit = run_all_validations(raw_df, transformed_df)
    
    assert audit["total_records"] == 2
    assert audit["audit_flags"]["is_duplicate"]["count"] == 1
    assert audit["audit_flags"]["is_normal_sale"]["count"] == 1
