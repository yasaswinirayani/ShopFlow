"""
Unit tests for src/analytics.py
Tests analytical SQL queries, parameters, chronological ordering,
customer aggregation, and financial reconciliation on a synthetic database.
"""

import pytest
import sqlite3
import pandas as pd
from pathlib import Path
from src.load import load_transformed_data, DEFAULT_SCHEMA_PATH
from src.transform import transform_retail_data
from src.analytics import (
    get_sales_overview,
    get_monthly_sales,
    get_top_products,
    get_country_analysis,
    get_customer_analysis,
    get_customer_summary_metrics,
    get_returns_and_cancellations,
    get_daily_sales,
    verify_financial_reconciliation,
    AnalyticsError
)


@pytest.fixture
def analytics_test_db(tmp_path):
    """Creates a temporary SQLite database loaded with multi-month synthetic data."""
    db_file = tmp_path / "test_analytics.db"
    
    raw = pd.DataFrame({
        "InvoiceNo": [
            "536365", "536366", "C536367", "536368", "536369", 
            "536370", "536370", "A563186", "536371"
        ],
        "StockCode": [
            "PROD_A", "PROD_B", "PROD_A", "PROD_A", "PROD_C",
            "PROD_B", "PROD_B", "B", "PROD_A"
        ],
        "Description": [
            "Product A", "Product B", "Product A", "Product A", None,
            "Product B", "Product B", "Adjust bad debt", "Product A"
        ],
        "Quantity": [
            10, 5, -2, 20, 15,
            4, 4, 1, 8
        ],
        "InvoiceDate": [
            "2011-01-05 10:00:00", "2011-01-15 11:00:00", "2011-01-20 12:00:00",
            "2011-02-01 10:00:00", "2011-02-15 14:00:00", "2011-03-01 09:00:00",
            "2011-03-01 09:00:00", "2011-03-05 12:00:00", "2011-03-10 15:00:00"
        ],
        "UnitPrice": [
            5.00, 10.00, 5.00, 5.00, 2.00,
            10.00, 10.00, -50.00, 5.00
        ],
        "CustomerID": [
            1001.0, 1002.0, 1001.0, 1001.0, None,
            1003.0, 1003.0, None, 1002.0
        ],
        "Country": [
            "United Kingdom", "France", "United Kingdom", "United Kingdom", "Germany",
            "United Kingdom", "United Kingdom", "United Kingdom", "France"
        ]
    })
    
    transformed = transform_retail_data(raw)
    load_transformed_data(transformed, db_path=db_file, schema_path=DEFAULT_SCHEMA_PATH, full_refresh=True)
    return db_file


def test_sales_overview(analytics_test_db):
    df = get_sales_overview(db_path=analytics_test_db)
    assert len(df) == 1
    row = df.iloc[0]
    
    assert row["total_transaction_lines"] == 9
    assert row["duplicate_lines"] == 1
    assert row["sales_invoices"] == 6
    assert row["cancellation_invoices"] == 1
    assert row["gross_sales_revenue"] > 0
    assert row["net_revenue"] > 0


def test_monthly_sales_chronological(analytics_test_db):
    df = get_monthly_sales(db_path=analytics_test_db)
    assert len(df) == 3
    months = df["sales_month"].tolist()
    assert months == ["2011-01", "2011-02", "2011-03"]
    # Check that prev_month_net_revenue is None for the first month
    assert pd.isna(df.loc[0, "prev_month_net_revenue"])
    assert not pd.isna(df.loc[1, "prev_month_net_revenue"])


def test_top_products_ranking(analytics_test_db):
    df_rev = get_top_products(db_path=analytics_test_db, order_by="revenue", limit=2)
    assert len(df_rev) == 2
    assert df_rev.iloc[0]["stock_code"] == "PROD_A"
    
    # Missing description handled as UNSPECIFIED
    df_qty = get_top_products(db_path=analytics_test_db, order_by="quantity", limit=5)
    prod_c = df_qty[df_qty["stock_code"] == "PROD_C"]
    assert not prod_c.empty
    assert prod_c.iloc[0]["product_name"] == "UNSPECIFIED"
    
    with pytest.raises(ValueError, match="Invalid order_by"):
        get_top_products(db_path=analytics_test_db, order_by="invalid_col")


def test_country_analysis(analytics_test_db):
    df = get_country_analysis(db_path=analytics_test_db)
    assert "United Kingdom" in df["country"].values
    assert "France" in df["country"].values
    assert "Germany" in df["country"].values
    
    # UK should have highest revenue in synthetic set
    assert df.iloc[0]["country"] == "United Kingdom"


def test_customer_metrics_and_guest_omission(analytics_test_db):
    df_cust = get_customer_analysis(db_path=analytics_test_db, limit=10)
    # Identified customers: 1001, 1002, 1003
    assert len(df_cust) == 3
    # Ensure None/NaN customer is NOT present
    assert df_cust["customer_id"].notna().all()
    
    kpis = get_customer_summary_metrics(db_path=analytics_test_db)
    assert kpis["total_identified_customers"] == 3
    # Repeat customers (1001 has 2 completed orders, 1002 has 2 completed orders)
    assert kpis["repeat_customers"] == 2
    assert kpis["one_time_customers"] == 1


def test_returns_and_cancellations(analytics_test_db):
    df = get_returns_and_cancellations(db_path=analytics_test_db)
    categories = df["anomaly_category"].tolist()
    assert "Cancelled Invoices (Starts with C)" in categories
    assert "Negative Price Adjustments (Bad Debt)" in categories
    
    cancel_row = df[df["anomaly_category"] == "Cancelled Invoices (Starts with C)"].iloc[0]
    assert cancel_row["record_count"] == 1
    assert cancel_row["net_units_impact"] == -2
    assert cancel_row["net_revenue_impact"] == -10.0


def test_daily_sales_and_filters(analytics_test_db):
    # Full range
    df_all = get_daily_sales(db_path=analytics_test_db)
    assert len(df_all) > 0
    
    # Filtered range
    df_filtered = get_daily_sales(db_path=analytics_test_db, start_date="2011-01-01", end_date="2011-01-31")
    assert len(df_filtered) == 3
    for d in df_filtered["sales_date"]:
        assert d.startswith("2011-01")
        
    # Empty range
    df_empty = get_daily_sales(db_path=analytics_test_db, start_date="2025-01-01", end_date="2025-01-31")
    assert len(df_empty) == 0


def test_financial_reconciliation(analytics_test_db):
    recon = verify_financial_reconciliation(db_path=analytics_test_db)
    assert recon["discrepancy"] == 0.0
    assert recon["component_sum"] == recon["net_revenue_non_duplicate"]


def test_missing_database_error(tmp_path):
    missing_db = tmp_path / "non_existent.db"
    with pytest.raises(AnalyticsError, match="Database not found"):
        get_sales_overview(db_path=missing_db)
