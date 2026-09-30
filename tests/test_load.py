"""
Unit tests for src/load.py
Uses pytest tmp_path fixture and synthetic DataFrames for fast, isolated SQLite testing.
"""

import sqlite3
import pytest
import pandas as pd
from pathlib import Path
from src.load import (
    init_database,
    prepare_dataframe_for_sqlite,
    load_transformed_data,
    query_database_audit_metrics,
    DEFAULT_SCHEMA_PATH
)
from src.transform import transform_retail_data


@pytest.fixture
def synthetic_retail_df():
    """Returns a transformed synthetic retail DataFrame with edge cases."""
    raw = pd.DataFrame({
        "InvoiceNo": ["536365", "C536366", "536367", "536367", "A563186"],
        "StockCode": ["85123A", "85123A", "71053", "71053", "B"],
        "Description": ["WHITE HEART", "WHITE HEART", "LANTERN", "LANTERN", "Adjust bad debt"],
        "Quantity": [6, -2, 4, 4, 1],
        "InvoiceDate": ["2010-12-01 08:26:00", "2010-12-01 09:00:00", "2010-12-01 10:00:00",
                        "2010-12-01 10:00:00", "2010-12-01 11:00:00"],
        "UnitPrice": [2.50, 2.50, 3.00, 3.00, -100.00],
        "CustomerID": [17850.0, 17850.0, None, None, None],
        "Country": ["United Kingdom", "United Kingdom", "France", "France", "United Kingdom"]
    })
    return transform_retail_data(raw)


def test_init_database(tmp_path):
    db_file = tmp_path / "test_init.db"
    init_database(db_path=db_file, schema_path=DEFAULT_SCHEMA_PATH)
    assert db_file.exists()
    
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='retail_transactions';")
        assert cursor.fetchone() is not None
        
        # Verify index creation
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tx_invoice_no';")
        assert cursor.fetchone() is not None


def test_prepare_dataframe_for_sqlite(synthetic_retail_df):
    prep = prepare_dataframe_for_sqlite(synthetic_retail_df)
    
    assert "invoice_no" in prep.columns
    assert "customer_id" in prep.columns
    assert "line_revenue" in prep.columns
    assert "is_normal_sale" in prep.columns
    
    # Check null preservation for guest checkout
    assert prep.loc[2, "customer_id"] is None
    # Check date formatting string
    assert prep.loc[0, "invoice_date"] == "2010-12-01 08:26:00"


def test_load_transformed_data_and_reconciliation(tmp_path, synthetic_retail_df):
    db_file = tmp_path / "test_load.db"
    
    # 1. Load data
    loaded_count = load_transformed_data(
        df=synthetic_retail_df,
        db_path=db_file,
        schema_path=DEFAULT_SCHEMA_PATH,
        full_refresh=True
    )
    assert loaded_count == len(synthetic_retail_df)
    
    # 2. Query and verify reconciliation
    metrics = query_database_audit_metrics(db_path=db_file)
    assert metrics["total_rows"] == 5
    assert metrics["missing_customers"] == 3  # rows 2, 3, 4
    assert metrics["duplicates"] == 1         # row 3 is duplicate of 2
    assert metrics["cancellations"] == 1      # row 1 is C536366
    assert metrics["normal_sales"] == 2       # row 0 (WHITE HEART) and row 2 (first LANTERN)


def test_safe_repeated_loading(tmp_path, synthetic_retail_df):
    db_file = tmp_path / "test_repeat.db"
    
    # First load
    load_transformed_data(synthetic_retail_df, db_path=db_file, full_refresh=True)
    m1 = query_database_audit_metrics(db_file)
    assert m1["total_rows"] == 5
    
    # Repeated full refresh load
    load_transformed_data(synthetic_retail_df, db_path=db_file, full_refresh=True)
    m2 = query_database_audit_metrics(db_file)
    # Row count must NOT double
    assert m2["total_rows"] == 5
    assert m2["financials"]["net_revenue_non_duplicate"] == m1["financials"]["net_revenue_non_duplicate"]


def test_financial_reconciliation_in_database(tmp_path, synthetic_retail_df):
    db_file = tmp_path / "test_fin.db"
    load_transformed_data(synthetic_retail_df, db_path=db_file, full_refresh=True)
    m = query_database_audit_metrics(db_file)
    
    fin = m["financials"]
    # Gross normal sales: 6*2.50 (15.0) + 4*3.00 (12.0) = 27.0
    assert fin["gross_normal_sales"] == 27.0
    # Cancellations non-dup: -2*2.50 = -5.0
    assert fin["cancelled_returns_non_dup"] == -5.0
    # Bad debt: 1*-100 = -100.0
    assert fin["bad_debt_adjustments"] == -100.0
    # Net revenue non-duplicate: 27 - 5 - 100 = -78.0
    assert fin["net_revenue_non_duplicate"] == -78.0
    assert fin["discrepancy"] == 0.0


def test_rollback_on_failure(tmp_path, synthetic_retail_df):
    db_file = tmp_path / "test_rollback.db"
    
    # Corrupt dataframe by adding an invalid column that cannot match schema
    corrupted_df = synthetic_retail_df.copy()
    corrupted_df["InvoiceNo"] = None  # NOT NULL constraint violation
    
    with pytest.raises(RuntimeError, match="Database load failed; transaction rolled back"):
        load_transformed_data(corrupted_df, db_path=db_file, full_refresh=True)
