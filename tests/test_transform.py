"""
Unit tests for src/transform.py
Uses small synthetic DataFrames for fast, isolated verification.
"""

import pytest
import pandas as pd
import numpy as np
from src.transform import (
    standardize_columns,
    clean_text_fields,
    convert_data_types,
    calculate_line_revenue,
    detect_duplicates,
    classify_transactions,
    transform_retail_data,
    REQUIRED_COLUMNS
)


@pytest.fixture
def sample_raw_df():
    """Returns a representative synthetic DataFrame with typical edge cases."""
    return pd.DataFrame({
        " InvoiceNo ": ["536365", "C536379", "536380", "536381", "536381", "536382", "536383"],
        "StockCode": ["85123A", "D", " 22423 ", "71053", "71053", "B", "35004B"],
        "Description": ["WHITE HEART", "Discount", None, "LANTERN", "LANTERN", "Adjust bad debt", "SET"],
        "Quantity": [6, -1, 10, 2, 2, -1, 0],
        "InvoiceDate": ["2010-12-01 08:26:00", "2010-12-01 09:41:00", "2010-12-01 10:00:00",
                        "2010-12-01 11:00:00", "2010-12-01 11:00:00", "2010-12-01 12:00:00", "2010-12-01 13:00:00"],
        "UnitPrice": [2.55, 27.50, 1.25, 3.39, 3.39, -11062.06, 0.0],
        "CustomerID": [17850.0, 17850.0, None, 13047.0, 13047.0, None, 14500.0],
        "Country": ["United Kingdom ", "United Kingdom", "France", "United Kingdom", "United Kingdom", "United Kingdom", "EIRE"]
    })


def test_standardize_columns(sample_raw_df):
    cleaned_df = standardize_columns(sample_raw_df)
    assert "InvoiceNo" in cleaned_df.columns
    assert " InvoiceNo " not in cleaned_df.columns
    
    # Test missing column exception
    incomplete_df = sample_raw_df.drop(columns=["UnitPrice"])
    with pytest.raises(ValueError, match="Missing required columns"):
        standardize_columns(incomplete_df)


def test_clean_text_fields(sample_raw_df):
    std_df = standardize_columns(sample_raw_df)
    cleaned_df = clean_text_fields(std_df)
    
    # StockCode whitespace stripped but case preserved
    assert cleaned_df.loc[0, "StockCode"] == "85123A"
    assert cleaned_df.loc[2, "StockCode"] == "22423"
    assert cleaned_df.loc[0, "Country"] == "United Kingdom"
    
    # Missing description handled transparently
    assert cleaned_df.loc[2, "Description"] == "UNSPECIFIED"
    assert cleaned_df.loc[2, "is_missing_description"] == True
    assert cleaned_df.loc[0, "is_missing_description"] == False


def test_convert_data_types(sample_raw_df):
    std_df = standardize_columns(sample_raw_df)
    typed_df = convert_data_types(std_df)
    
    assert pd.api.types.is_datetime64_any_dtype(typed_df["InvoiceDate"])
    assert pd.api.types.is_integer_dtype(typed_df["Quantity"])
    assert pd.api.types.is_float_dtype(typed_df["UnitPrice"])
    assert pd.api.types.is_integer_dtype(typed_df["CustomerID"])
    assert pd.isna(typed_df.loc[2, "CustomerID"])


def test_calculate_line_revenue():
    df = pd.DataFrame({
        "Quantity": [10, -2, 5, 0],
        "UnitPrice": [2.50, 15.00, 0.0, 4.00]
    })
    res = calculate_line_revenue(df)
    assert res["LineRevenue"].tolist() == [25.0, -30.0, 0.0, 0.0]


def test_detect_duplicates(sample_raw_df):
    std_df = standardize_columns(sample_raw_df)
    dup_df = detect_duplicates(std_df)
    
    # Row 3 is original, Row 4 is duplicate of Row 3
    assert dup_df.loc[3, "is_duplicate"] == False
    assert dup_df.loc[4, "is_duplicate"] == True


def test_classify_transactions(sample_raw_df):
    std_df = standardize_columns(sample_raw_df)
    typed_df = convert_data_types(std_df)
    dup_df = detect_duplicates(typed_df)
    rev_df = calculate_line_revenue(dup_df)
    classified_df = classify_transactions(rev_df)
    
    # Row 0: Normal sale
    assert classified_df.loc[0, "is_normal_sale"] == True
    assert classified_df.loc[0, "transaction_category"] == "NORMAL_SALE"
    
    # Row 1: Cancelled invoice (starts with C)
    assert classified_df.loc[1, "is_cancelled"] == True
    assert classified_df.loc[1, "is_negative_quantity"] == True
    assert classified_df.loc[1, "is_normal_sale"] == False
    assert classified_df.loc[1, "transaction_category"] == "CANCELLED_INVOICE"
    
    # Row 2: Missing customer
    assert classified_df.loc[2, "is_missing_customer"] == True
    assert classified_df.loc[2, "is_normal_sale"] == True  # Valid sale despite missing ID
    
    # Row 4: Duplicate
    assert classified_df.loc[4, "is_duplicate"] == True
    assert classified_df.loc[4, "is_normal_sale"] == False
    assert classified_df.loc[4, "transaction_category"] == "DUPLICATE"
    
    # Row 5: Negative price
    assert classified_df.loc[5, "is_negative_price"] == True
    assert classified_df.loc[5, "transaction_category"] == "NEGATIVE_PRICE_ADJUSTMENT"
    
    # Row 6: Zero price
    assert classified_df.loc[6, "is_zero_price"] == True
    assert classified_df.loc[6, "is_zero_quantity"] == True


def test_transform_retail_data_end_to_end(sample_raw_df):
    df_result = transform_retail_data(sample_raw_df)
    
    # Row count must match exactly
    assert len(df_result) == len(sample_raw_df)
    
    # Essential columns must exist
    for col in REQUIRED_COLUMNS:
        assert col in df_result.columns
    assert "LineRevenue" in df_result.columns
    assert "is_normal_sale" in df_result.columns
    assert "transaction_category" in df_result.columns
