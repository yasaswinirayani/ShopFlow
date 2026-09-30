"""
Unit tests for dashboard helpers and query functions.
Tests metric formatting, filter builders, KPI calculations, and database checks.
"""

import pytest
import sqlite3
import pandas as pd
from pathlib import Path
from src.analytics import (
    format_currency,
    format_number,
    format_percent,
    build_filter_clause,
    get_available_filter_options,
    get_filtered_sales_kpis,
    get_filtered_monthly_sales,
    get_top_products,
    get_daily_sales,
    verify_financial_reconciliation,
    AnalyticsError
)
from src.load import load_transformed_data, DEFAULT_SCHEMA_PATH
from src.transform import transform_retail_data


@pytest.fixture
def dashboard_test_db(tmp_path):
    """Creates a temporary SQLite database loaded with multi-country synthetic data."""
    db_file = tmp_path / "test_dash.db"
    
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


def test_metric_formatters():
    # Currency formatting
    assert format_currency(1234.56) == "£1,234.56"
    assert format_currency(-893979.73) == "-£893,979.73"
    assert format_currency(0.0) == "£0.00"
    assert format_currency(None) == "£0.00"
    
    # Number formatting
    assert format_number(1000) == "1,000"
    assert format_number(541909) == "541,909"
    assert format_number(None) == "0"
    
    # Percentage formatting
    assert format_percent(15.2) == "+15.2%"
    assert format_percent(-10.5) == "-10.5%"
    assert format_percent(0.0) == "0.0%"


def test_build_filter_clause():
    clause, params = build_filter_clause(
        start_date="2011-01-01",
        end_date="2011-03-31",
        country="France",
        search_query="HEART"
    )
    assert "SUBSTR(invoice_date, 1, 10) >= ?" in clause
    assert "SUBSTR(invoice_date, 1, 10) <= ?" in clause
    assert "country = ?" in clause
    assert "stock_code LIKE ? OR description LIKE ?" in clause
    assert params == ["2011-01-01", "2011-03-31", "France", "%HEART%", "%HEART%"]
    
    # Unrestricted filter
    empty_clause, empty_params = build_filter_clause(country="All")
    assert empty_clause == ""
    assert empty_params == []


def test_filter_options(dashboard_test_db):
    opts = get_available_filter_options(db_path=dashboard_test_db)
    assert opts["min_date"] == "2011-01-05"
    assert opts["max_date"] == "2011-03-10"
    assert "All" in opts["countries"]
    assert "United Kingdom" in opts["countries"]
    assert "France" in opts["countries"]


def test_filtered_kpis_and_country_filtering(dashboard_test_db):
    # Unfiltered
    kpis_all = get_filtered_sales_kpis(db_path=dashboard_test_db)
    assert kpis_all["sales_invoices"] == 6
    assert kpis_all["gross_sales_revenue"] > 0
    
    # Filtered by country = France
    kpis_france = get_filtered_sales_kpis(db_path=dashboard_test_db, country="France")
    assert kpis_france["sales_invoices"] == 2
    assert kpis_france["identified_customers"] == 1  # Customer 1002
    assert kpis_france["gross_sales_revenue"] == (5 * 10.00) + (8 * 5.00)  # 50 + 40 = 90.00


def test_filtered_kpis_empty_results(dashboard_test_db):
    # Non-matching date range
    kpis_empty = get_filtered_sales_kpis(
        db_path=dashboard_test_db,
        start_date="2030-01-01",
        end_date="2030-12-31"
    )
    assert kpis_empty["total_rows"] == 0
    assert kpis_empty["gross_sales_revenue"] == 0.0
    assert kpis_empty["net_revenue"] == 0.0
    assert kpis_empty["gross_aov"] == 0.0


def test_filtered_monthly_sales(dashboard_test_db):
    df_m = get_filtered_monthly_sales(db_path=dashboard_test_db, country="United Kingdom")
    assert len(df_m) == 3
    assert set(df_m["sales_month"]) == {"2011-01", "2011-02", "2011-03"}


def test_financial_consistency_with_analytics(dashboard_test_db):
    kpis = get_filtered_sales_kpis(db_path=dashboard_test_db)
    recon = verify_financial_reconciliation(db_path=dashboard_test_db)
    
    # Assert exact match between KPI card net revenue and audited reconciliation net revenue
    assert kpis["net_revenue"] == recon["net_revenue_non_duplicate"]
    assert kpis["gross_sales_revenue"] == recon["gross_normal_sales"]
    assert recon["discrepancy"] == 0.0
