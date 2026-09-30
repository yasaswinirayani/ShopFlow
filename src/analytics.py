"""
ShopFlow - Business Analytics Module
Executes analytical SQL queries against data/processed/shopflow.db and
returns typed, documented pandas DataFrames for reporting and dashboarding.
"""

import sys
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, Union
import pandas as pd

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DEFAULT_DB_PATH = BASE_DIR / "data" / "processed" / "shopflow.db"
ANALYTICS_SQL_DIR = BASE_DIR / "sql" / "analytics"


class AnalyticsError(Exception):
    """Raised when an analytical query fails."""
    pass


def _get_connection(db_path: Path = DEFAULT_DB_PATH, conn: Optional[sqlite3.Connection] = None):
    """Context manager or connection resolver for safe database access."""
    if conn is not None:
        return conn, False
    if not db_path.exists():
        raise AnalyticsError(f"Database not found at {db_path}. Please run ETL pipeline first.")
    return sqlite3.connect(db_path), True


def execute_query(query: str, params: Optional[Union[tuple, dict]] = None, db_path: Path = DEFAULT_DB_PATH, conn: Optional[sqlite3.Connection] = None) -> pd.DataFrame:
    """
    Executes a parameterized SQL query and returns results as a pandas DataFrame.
    """
    connection, close_conn = _get_connection(db_path, conn)
    try:
        if params:
            df = pd.read_sql_query(query, connection, params=params)
        else:
            df = pd.read_sql_query(query, connection)
        return df
    except Exception as exc:
        raise AnalyticsError(f"SQL query execution failed: {exc}") from exc
    finally:
        if close_conn:
            connection.close()


def get_sales_overview(db_path: Path = DEFAULT_DB_PATH, conn: Optional[sqlite3.Connection] = None) -> pd.DataFrame:
    """
    Executes sql/analytics/sales_overview.sql and returns platform-level KPIs.
    """
    sql_file = ANALYTICS_SQL_DIR / "sales_overview.sql"
    sql = sql_file.read_text(encoding="utf-8")
    return execute_query(sql, db_path=db_path, conn=conn)


def get_monthly_sales(db_path: Path = DEFAULT_DB_PATH, conn: Optional[sqlite3.Connection] = None) -> pd.DataFrame:
    """
    Executes sql/analytics/monthly_sales.sql to return monthly trends and MoM growth.
    """
    sql_file = ANALYTICS_SQL_DIR / "monthly_sales.sql"
    sql = sql_file.read_text(encoding="utf-8")
    return execute_query(sql, db_path=db_path, conn=conn)


def get_top_products(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
    order_by: str = "revenue",
    limit: int = 10,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    country: Optional[str] = None,
    search_query: Optional[str] = None
) -> pd.DataFrame:
    """
    Ranks top products by gross revenue or quantity sold with optional filtering.
    Parameter order_by: 'revenue' or 'quantity' (defaults to 'revenue').
    """
    if order_by not in ["revenue", "quantity"]:
        raise ValueError(f"Invalid order_by '{order_by}'. Must be 'revenue' or 'quantity'.")
        
    sort_column = "gross_revenue" if order_by == "revenue" else "gross_units_sold"
    
    where_conditions = ["t.stock_code NOT IN ('POST', 'D', 'M', 'BANK CHARGES', 'PADS', 'DOT', 'CRUK')"]
    params = []
    
    if start_date:
        where_conditions.append("SUBSTR(t.invoice_date, 1, 10) >= ?")
        params.append(start_date)
    if end_date:
        where_conditions.append("SUBSTR(t.invoice_date, 1, 10) <= ?")
        params.append(end_date)
    if country and country != "All":
        where_conditions.append("t.country = ?")
        params.append(country)
    if search_query and search_query.strip():
        q = f"%{search_query.strip()}%"
        where_conditions.append("(t.stock_code LIKE ? OR t.description LIKE ?)")
        params.extend([q, q])
        
    where_sql = f"WHERE {' AND '.join(where_conditions)}"
    params.append(limit)

    query = f"""
    WITH canonical_names AS (
        SELECT 
            stock_code, 
            description,
            ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY COUNT(*) DESC) AS rn
        FROM retail_transactions
        WHERE is_normal_sale = 1 AND description NOT IN ('UNSPECIFIED', '')
        GROUP BY stock_code, description
    )
    SELECT
        t.stock_code,
        COALESCE(cn.description, 'UNSPECIFIED')                               AS product_name,
        COALESCE(SUM(CASE WHEN t.is_normal_sale = 1 THEN t.quantity ELSE 0 END), 0)       AS gross_units_sold,
        COALESCE(SUM(CASE WHEN t.is_cancelled = 1 AND t.is_duplicate = 0 THEN t.quantity ELSE 0 END), 0) AS units_returned,
        COALESCE(SUM(CASE WHEN t.is_duplicate = 0 THEN t.quantity ELSE 0 END), 0)         AS net_units_sold,
        COALESCE(ROUND(SUM(CASE WHEN t.is_normal_sale = 1 THEN t.line_revenue ELSE 0 END), 2), 0.0) AS gross_revenue,
        COALESCE(ROUND(SUM(CASE WHEN t.is_duplicate = 0 THEN t.line_revenue ELSE 0 END), 2), 0.0) AS net_revenue,
        COUNT(DISTINCT CASE WHEN t.is_normal_sale = 1 THEN t.invoice_no END)  AS order_count
    FROM retail_transactions t
    LEFT JOIN canonical_names cn ON t.stock_code = cn.stock_code AND cn.rn = 1
    {where_sql}
    GROUP BY t.stock_code
    ORDER BY {sort_column} DESC
    LIMIT ?;
    """
    return execute_query(query, params=tuple(params), db_path=db_path, conn=conn)


def get_country_analysis(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
    limit: Optional[int] = None
) -> pd.DataFrame:
    """
    Executes country performance analysis.
    """
    sql_file = ANALYTICS_SQL_DIR / "country_analysis.sql"
    sql = sql_file.read_text(encoding="utf-8")
    if limit is not None:
        sql = sql.rstrip("; \n") + f"\nLIMIT {int(limit)};"
    return execute_query(sql, db_path=db_path, conn=conn)


def get_customer_analysis(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
    limit: int = 50
) -> pd.DataFrame:
    """
    Executes customer segmentation and lifetime spend rankings for identified customers.
    """
    query = """
    SELECT
        customer_id,
        MAX(country)                                                          AS primary_country,
        COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END)      AS completed_orders,
        COUNT(DISTINCT CASE WHEN is_cancelled = 1 THEN invoice_no END)        AS cancellation_orders,
        SUM(CASE WHEN is_normal_sale = 1 THEN quantity ELSE 0 END)            AS units_purchased,
        ROUND(SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END), 2) AS gross_spend,
        ROUND(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS returns_refunded,
        ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS net_lifetime_spend,
        CASE 
            WHEN COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END) > 1 THEN 'REPEAT'
            ELSE 'ONE_TIME'
        END AS customer_type
    FROM retail_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
    ORDER BY net_lifetime_spend DESC
    LIMIT ?;
    """
    return execute_query(query, params=(limit,), db_path=db_path, conn=conn)


def get_customer_summary_metrics(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Calculates macro customer health metrics across all identified customers.
    """
    query = """
    WITH customer_aggregates AS (
        SELECT
            customer_id,
            COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END) AS order_count,
            ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS net_spend
        FROM retail_transactions
        WHERE customer_id IS NOT NULL
        GROUP BY customer_id
    )
    SELECT
        COUNT(DISTINCT customer_id)                                         AS total_identified_customers,
        COUNT(DISTINCT CASE WHEN order_count > 1 THEN customer_id END)      AS repeat_customers,
        COUNT(DISTINCT CASE WHEN order_count = 1 THEN customer_id END)      AS one_time_customers,
        ROUND(AVG(net_spend), 2)                                            AS avg_spend_per_customer,
        ROUND(MEDIAN_APPROX(net_spend), 2)                                  AS approx_median_spend
    FROM (
        SELECT customer_id, order_count, net_spend, 
               ROW_NUMBER() OVER (ORDER BY net_spend) as row_num,
               COUNT(*) OVER () as total_cnt
        FROM customer_aggregates
    );
    """
    # SQLite does not have native MEDIAN, so we query standard aggregates cleanly
    query_clean = """
    WITH customer_aggregates AS (
        SELECT
            customer_id,
            COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END) AS order_count,
            ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS net_spend
        FROM retail_transactions
        WHERE customer_id IS NOT NULL
        GROUP BY customer_id
    )
    SELECT
        COUNT(DISTINCT customer_id)                                         AS total_identified_customers,
        COUNT(DISTINCT CASE WHEN order_count > 1 THEN customer_id END)      AS repeat_customers,
        COUNT(DISTINCT CASE WHEN order_count = 1 THEN customer_id END)      AS one_time_customers,
        ROUND(AVG(net_spend), 2)                                            AS avg_spend_per_customer
    FROM customer_aggregates;
    """
    df = execute_query(query_clean, db_path=db_path, conn=conn)
    row = df.iloc[0].to_dict()
    total = row["total_identified_customers"]
    repeat = row["repeat_customers"]
    row["repeat_customer_rate_pct"] = round((repeat / total * 100) if total > 0 else 0.0, 2)
    return row


def get_returns_and_cancellations(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None
) -> pd.DataFrame:
    """
    Executes sql/analytics/returns_and_cancellations.sql to audit non-standard transactions.
    """
    sql_file = ANALYTICS_SQL_DIR / "returns_and_cancellations.sql"
    sql = sql_file.read_text(encoding="utf-8")
    return execute_query(sql, db_path=db_path, conn=conn)


def get_daily_sales(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    country: Optional[str] = None,
    search_query: Optional[str] = None
) -> pd.DataFrame:
    """
    Returns daily time series for charts, with optional date, country, and product filtering.
    Format for start_date / end_date: 'YYYY-MM-DD'.
    """
    where_clause, params = build_filter_clause(start_date, end_date, country, search_query)
    
    query = f"""
    SELECT
        SUBSTR(invoice_date, 1, 10)                                         AS sales_date,
        COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END)      AS order_count,
        COALESCE(SUM(CASE WHEN is_normal_sale = 1 THEN quantity ELSE 0 END), 0)            AS units_sold,
        COALESCE(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN quantity ELSE 0 END), 0) AS units_returned,
        COALESCE(ROUND(SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END), 2), 0.0) AS gross_revenue,
        COALESCE(ROUND(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2), 0.0) AS returns_offset,
        COALESCE(ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2), 0.0) AS net_revenue
    FROM retail_transactions
    {where_clause}
    GROUP BY SUBSTR(invoice_date, 1, 10)
    ORDER BY sales_date ASC;
    """
    return execute_query(query, params=tuple(params) if params else None, db_path=db_path, conn=conn)


def verify_financial_reconciliation(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Reproduces the exact financial reconciliation from the SQLite database.
    """
    query = """
    SELECT
        ROUND(SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END), 2) AS gross_normal_sales,
        ROUND(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS cancellations_non_dup,
        ROUND(SUM(CASE WHEN is_negative_price = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS bad_debt_adjustments,
        ROUND(SUM(CASE WHEN is_negative_quantity = 1 AND is_cancelled = 0 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS other_neg_qty,
        ROUND(SUM(CASE WHEN is_duplicate = 1 THEN line_revenue ELSE 0 END), 2) AS duplicate_revenue_excluded,
        ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS net_revenue_non_duplicate,
        ROUND(SUM(line_revenue), 2) AS total_table_revenue
    FROM retail_transactions;
    """
    df = execute_query(query, db_path=db_path, conn=conn)
    row = df.iloc[0].to_dict()
    
    comp_sum = round(
        row["gross_normal_sales"] + 
        row["cancellations_non_dup"] + 
        row["bad_debt_adjustments"] + 
        row["other_neg_qty"], 
        2
    )
    discrepancy = round(abs(comp_sum - row["net_revenue_non_duplicate"]), 4)
    
    row["component_sum"] = comp_sum
    row["discrepancy"] = discrepancy
    return row


# ==============================================================================
# Formatting & Filtered Query Helpers for Streamlit Dashboard & Testing
# ==============================================================================

def format_currency(val: Optional[Union[int, float]]) -> str:
    """Formats numeric value to GBP currency string with clean negative handling."""
    if val is None or pd.isna(val):
        return "£0.00"
    if val < 0:
        return f"-£{abs(val):,.2f}"
    return f"£{val:,.2f}"


def format_number(val: Optional[Union[int, float]]) -> str:
    """Formats integer or float with thousand-separator comma."""
    if val is None or pd.isna(val):
        return "0"
    return f"{int(round(val)):,}"


def format_percent(val: Optional[Union[int, float]]) -> str:
    """Formats decimal or float percentage."""
    if val is None or pd.isna(val):
        return "0.0%"
    return f"{val:+.1f}%" if val != 0 else "0.0%"


def build_filter_clause(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    country: Optional[str] = None,
    search_query: Optional[str] = None,
    table_prefix: str = ""
) -> tuple[str, list]:
    """
    Safely constructs a parameterized SQL WHERE clause and parameter list.
    """
    conditions = []
    params = []
    p = f"{table_prefix}." if table_prefix else ""
    
    if start_date:
        conditions.append(f"SUBSTR({p}invoice_date, 1, 10) >= ?")
        params.append(start_date)
    if end_date:
        conditions.append(f"SUBSTR({p}invoice_date, 1, 10) <= ?")
        params.append(end_date)
    if country and country != "All":
        conditions.append(f"{p}country = ?")
        params.append(country)
    if search_query and search_query.strip():
        q = f"%{search_query.strip()}%"
        conditions.append(f"({p}stock_code LIKE ? OR {p}description LIKE ?)")
        params.extend([q, q])
        
    clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return clause, params


def get_available_filter_options(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """Returns available date bounds and country list for UI filters."""
    query_dates = "SELECT MIN(SUBSTR(invoice_date, 1, 10)), MAX(SUBSTR(invoice_date, 1, 10)) FROM retail_transactions;"
    df_dates = execute_query(query_dates, db_path=db_path, conn=conn)
    min_date = df_dates.iloc[0, 0] or "2010-12-01"
    max_date = df_dates.iloc[0, 1] or "2011-12-09"
    
    query_countries = "SELECT DISTINCT country FROM retail_transactions ORDER BY country ASC;"
    df_countries = execute_query(query_countries, db_path=db_path, conn=conn)
    countries = ["All"] + df_countries["country"].dropna().tolist()
    
    return {
        "min_date": min_date,
        "max_date": max_date,
        "countries": countries
    }


def get_filtered_sales_kpis(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    country: Optional[str] = None,
    search_query: Optional[str] = None
) -> Dict[str, Any]:
    """Calculates KPI card metrics matching any active sidebar filters."""
    clause, params = build_filter_clause(start_date, end_date, country, search_query)
    query = f"""
    SELECT
        COUNT(*) AS total_rows,
        COALESCE(SUM(CASE WHEN is_duplicate = 0 THEN 1 ELSE 0 END), 0) AS non_duplicate_lines,
        COUNT(DISTINCT invoice_no) AS total_invoices,
        COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END) AS sales_invoices,
        COUNT(DISTINCT CASE WHEN is_cancelled = 1 THEN invoice_no END) AS cancel_invoices,
        COALESCE(SUM(CASE WHEN is_normal_sale = 1 THEN quantity ELSE 0 END), 0) AS units_sold,
        COALESCE(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN quantity ELSE 0 END), 0) AS units_returned,
        COALESCE(ROUND(SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END), 2), 0.0) AS gross_sales_revenue,
        COALESCE(ROUND(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2), 0.0) AS cancellations_offset,
        COALESCE(ROUND(SUM(CASE WHEN is_negative_price = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2), 0.0) AS bad_debt_adjustments,
        COALESCE(ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2), 0.0) AS net_revenue,
        COUNT(DISTINCT customer_id) AS identified_customers
    FROM retail_transactions
    {clause};
    """
    df = execute_query(query, params=tuple(params) if params else None, db_path=db_path, conn=conn)
    row = df.iloc[0].to_dict()
    sales_inv = row["sales_invoices"] or 0
    row["gross_aov"] = round(row["gross_sales_revenue"] / sales_inv, 2) if sales_inv > 0 else 0.0
    return row


def get_filtered_monthly_sales(
    db_path: Path = DEFAULT_DB_PATH,
    conn: Optional[sqlite3.Connection] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    country: Optional[str] = None,
    search_query: Optional[str] = None
) -> pd.DataFrame:
    """Returns monthly aggregated sales responding to filters."""
    clause, params = build_filter_clause(start_date, end_date, country, search_query)
    query = f"""
    WITH monthly_aggregations AS (
        SELECT
            SUBSTR(invoice_date, 1, 7)                                      AS sales_month,
            COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END) AS order_count,
            COALESCE(SUM(CASE WHEN is_normal_sale = 1 THEN quantity ELSE 0 END), 0)       AS units_sold,
            COALESCE(ROUND(SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END), 2), 0.0) AS gross_revenue,
            COALESCE(ROUND(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2), 0.0) AS returns_offset,
            COALESCE(ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2), 0.0) AS net_revenue
        FROM retail_transactions
        {clause}
        GROUP BY SUBSTR(invoice_date, 1, 7)
    )
    SELECT
        sales_month,
        order_count,
        units_sold,
        gross_revenue,
        returns_offset,
        net_revenue,
        LAG(net_revenue) OVER (ORDER BY sales_month ASC) AS prev_month_net_revenue,
        ROUND(
            (net_revenue - LAG(net_revenue) OVER (ORDER BY sales_month ASC)) / 
            NULLIF(LAG(net_revenue) OVER (ORDER BY sales_month ASC), 0) * 100, 
            2
        ) AS mom_growth_percent
    FROM monthly_aggregations
    ORDER BY sales_month ASC;
    """
    return execute_query(query, params=tuple(params) if params else None, db_path=db_path, conn=conn)

