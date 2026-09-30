"""
ShopFlow - Analytics Runner Script
Executes all analytical queries against data/processed/shopflow.db,
formats real metric tables, and saves reports/analytics_summary.txt.
"""

import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

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
    DEFAULT_DB_PATH
)

REPORT_PATH = BASE_DIR / "reports" / "analytics_summary.txt"


def main():
    lines = []
    def log(msg=""):
        lines.append(str(msg))
        print(msg)

    log("=" * 80)
    log("SHOPFLOW — BUSINESS ANALYTICS & SQL METRICS REPORT")
    log("=" * 80)
    log(f"Database Source: {DEFAULT_DB_PATH}")
    log()

    # 1. Sales Overview
    log("--- 1. PLATFORM SALES OVERVIEW ---")
    df_overview = get_sales_overview()
    row = df_overview.iloc[0]
    log(f"  Total Transaction Lines:          {row['total_transaction_lines']:>12,}")
    log(f"  Non-Duplicate Lines:              {row['non_duplicate_lines']:>12,}")
    log(f"  Exact Duplicate Lines (Excluded): {row['duplicate_lines']:>12,}")
    log()
    log(f"  Total Distinct Invoices:          {row['total_distinct_invoices']:>12,}")
    log(f"  Sales Invoices (Completed):       {row['sales_invoices']:>12,}")
    log(f"  Cancellation Invoices:            {row['cancellation_invoices']:>12,}")
    log()
    log(f"  Total Units Sold:                 {row['units_sold']:>12,}")
    log(f"  Units Returned / Refunded:        {row['units_returned']:>12,}")
    log()
    log(f"  Gross Sales Revenue:              GBP {row['gross_sales_revenue']:>15,.2f}")
    log(f"  Cancellations / Returns Offset:   GBP {row['cancellations_revenue_offset']:>15,.2f}")
    log(f"  Bad Debt Accounting Adjustments:  GBP {row['bad_debt_adjustments']:>15,.2f}")
    log(f"  Net Commercial Revenue:           GBP {row['net_revenue']:>15,.2f}")
    log()
    log(f"  Gross AOV (per Sales Invoice):    GBP {row['gross_aov_per_sales_order']:>15,.2f}")
    log(f"  Net AOV (per Distinct Invoice):   GBP {row['net_aov_per_distinct_order']:>15,.2f}")
    log()

    # 2. Financial Reconciliation
    log("--- 2. FINANCIAL RECONCILIATION ---")
    recon = verify_financial_reconciliation()
    log(f"  (A) Gross Normal Sales:           GBP {recon['gross_normal_sales']:>15,.2f}")
    log(f"  (B) Cancellations Non-Duplicate:  GBP {recon['cancellations_non_dup']:>15,.2f}")
    log(f"  (C) Bad Debt Adjustments:         GBP {recon['bad_debt_adjustments']:>15,.2f}")
    log(f"  (D) Other Negative Qty (price=0): GBP {recon['other_neg_qty']:>15,.2f}")
    log("  -------------------------------------------------------------")
    log(f"  (E) Component Sum (A+B+C+D):      GBP {recon['component_sum']:>15,.2f}")
    log(f"  (F) Net Revenue (All Non-Dup):    GBP {recon['net_revenue_non_duplicate']:>15,.2f}")
    log(f"  Discrepancy (E - F):              GBP {recon['discrepancy']:>15,.4f}")
    log()

    # 3. Monthly Sales & Growth
    log("--- 3. MONTHLY SALES TRENDS & GROWTH (MoM) ---")
    df_monthly = get_monthly_sales()
    log(df_monthly.to_string(index=False))
    log()

    # 4. Top 10 Products by Revenue
    log("--- 4. TOP 10 PRODUCTS BY REVENUE ---")
    df_top_rev = get_top_products(order_by="revenue", limit=10)
    log(df_top_rev[["stock_code", "product_name", "gross_revenue", "gross_units_sold", "order_count"]].to_string(index=False))
    log()

    # 5. Top 10 Products by Quantity Sold
    log("--- 5. TOP 10 PRODUCTS BY QUANTITY SOLD ---")
    df_top_qty = get_top_products(order_by="quantity", limit=10)
    log(df_top_qty[["stock_code", "product_name", "gross_units_sold", "gross_revenue", "order_count"]].to_string(index=False))
    log()

    # 6. Top 10 Countries by Net Revenue
    log("--- 6. TOP 10 COUNTRIES BY REVENUE ---")
    df_country = get_country_analysis(limit=10)
    log(df_country[["country", "net_revenue", "pct_of_global_net_revenue", "sales_orders", "identified_customers", "guest_orders"]].to_string(index=False))
    log()

    # 7. Customer Metrics
    log("--- 7. CUSTOMER ANALYSIS & SEGMENTATION ---")
    cust_kpis = get_customer_summary_metrics()
    log(f"  Total Identified Customers:       {cust_kpis['total_identified_customers']:>12,}")
    log(f"  Repeat Customers (>1 order):      {cust_kpis['repeat_customers']:>12,} ({cust_kpis['repeat_customer_rate_pct']:.2f}%)")
    log(f"  One-Time Customers:               {cust_kpis['one_time_customers']:>12,}")
    log(f"  Avg Spend per Identified Customer:GBP {cust_kpis['avg_spend_per_customer']:>15,.2f}")
    log()
    log("Top 10 Highest-Value Customers:")
    df_top_cust = get_customer_analysis(limit=10)
    log(df_top_cust[["customer_id", "primary_country", "net_lifetime_spend", "completed_orders", "cancellation_orders", "customer_type"]].to_string(index=False))
    log()

    # 8. Returns, Cancellations & Non-Standard Records
    log("--- 8. RETURNS, CANCELLATIONS & ANOMALIES ---")
    df_returns = get_returns_and_cancellations()
    log(df_returns.to_string(index=False))
    log()

    # 9. Daily Velocity Preview
    log("--- 9. DAILY SALES SUMMARY (First 5 and Last 5 Days) ---")
    df_daily = get_daily_sales()
    log("First 5 Days:")
    log(df_daily.head(5).to_string(index=False))
    log("Last 5 Days:")
    log(df_daily.tail(5).to_string(index=False))
    log()

    # 10. Data Limitations & Documentation
    log("--- 10. BUSINESS ASSUMPTIONS & LIMITATIONS ---")
    log("1. Guest Checkouts: 135,080 transaction lines have no CustomerID. They are")
    log("   preserved in all aggregate sales, daily velocity, and country revenue calculations,")
    log("   but strictly omitted from customer lifetime value (LTV) rankings.")
    log("2. Returns Treatment: Cancellations (InvoiceNo with 'C') represent £893,979.73 in refunds.")
    log("   Net revenue sums positive sales plus returns offset across non-duplicate transactions.")
    log("3. Non-product items: System codes ('POST' postage, 'BANK CHARGES', 'D' discount)")
    log("   are excluded from product catalog rankings to preserve merchandising insights.")
    log("=" * 80)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nAnalytics summary report successfully saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
