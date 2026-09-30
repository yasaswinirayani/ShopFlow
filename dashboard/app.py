"""
ShopFlow - Interactive E-commerce Sales Analytics Platform
Streamlit Web Dashboard powered by SQLite and Plotly.
"""

import sys
from pathlib import Path
from datetime import datetime, date
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.analytics import (
    DEFAULT_DB_PATH,
    get_available_filter_options,
    get_filtered_sales_kpis,
    get_daily_sales,
    get_filtered_monthly_sales,
    get_top_products,
    get_country_analysis,
    get_customer_analysis,
    get_customer_summary_metrics,
    get_returns_and_cancellations,
    verify_financial_reconciliation,
    format_currency,
    format_number,
    format_percent,
    AnalyticsError
)

# -----------------------------------------------------------------------------
# Streamlit Page Configuration & Theming
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="ShopFlow — E-commerce Sales Analytics",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich executive styling
st.markdown("""
<style>
    /* Metric Card Styling */
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    .metric-label {
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #f8fafc;
        line-height: 1.2;
    }
    .metric-subtitle {
        font-size: 0.75rem;
        color: #64748b;
        margin-top: 4px;
    }
    .highlight-net {
        color: #38bdf8 !important;
    }
    .highlight-gross {
        color: #4ade80 !important;
    }
    .highlight-orders {
        color: #a78bfa !important;
    }
    .highlight-aov {
        color: #f59e0b !important;
    }
    /* Section Headers */
    .section-header {
        font-size: 1.3rem;
        font-weight: 700;
        color: #e2e8f0;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
        border-bottom: 2px solid #334155;
        padding-bottom: 0.3rem;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Cached Data Fetchers
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_filter_options(db_path: Path):
    return get_available_filter_options(db_path)

@st.cache_data(show_spinner=False)
def load_kpis(db_path: Path, start_date, end_date, country, search_query):
    return get_filtered_sales_kpis(
        db_path=db_path,
        start_date=start_date,
        end_date=end_date,
        country=country,
        search_query=search_query
    )

@st.cache_data(show_spinner=False)
def load_daily(db_path: Path, start_date, end_date, country, search_query):
    return get_daily_sales(
        db_path=db_path,
        start_date=start_date,
        end_date=end_date,
        country=country,
        search_query=search_query
    )

@st.cache_data(show_spinner=False)
def load_monthly(db_path: Path, start_date, end_date, country, search_query):
    return get_filtered_monthly_sales(
        db_path=db_path,
        start_date=start_date,
        end_date=end_date,
        country=country,
        search_query=search_query
    )

@st.cache_data(show_spinner=False)
def load_products(db_path: Path, order_by, limit, start_date, end_date, country, search_query):
    return get_top_products(
        db_path=db_path,
        order_by=order_by,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
        country=country,
        search_query=search_query
    )

@st.cache_data(show_spinner=False)
def load_countries(db_path: Path, limit=None):
    return get_country_analysis(db_path=db_path, limit=limit)

@st.cache_data(show_spinner=False)
def load_customers(db_path: Path, limit=20):
    return get_customer_analysis(db_path=db_path, limit=limit)

@st.cache_data(show_spinner=False)
def load_customer_kpis(db_path: Path):
    return get_customer_summary_metrics(db_path=db_path)

@st.cache_data(show_spinner=False)
def load_returns(db_path: Path):
    return get_returns_and_cancellations(db_path=db_path)

@st.cache_data(show_spinner=False)
def load_reconciliation(db_path: Path):
    return verify_financial_reconciliation(db_path=db_path)


# -----------------------------------------------------------------------------
# Main Application Entry Point
# -----------------------------------------------------------------------------
def main():
    # Database existence check
    if not DEFAULT_DB_PATH.exists():
        st.error(
            f"⚠️ **Database Not Found**: `{DEFAULT_DB_PATH}` does not exist yet.\n\n"
            "Please run the ETL orchestration pipeline first from the project root:\n\n"
            "```powershell\n"
            ".venv\\Scripts\\python.exe -m src.pipeline\n"
            "```"
        )
        st.stop()

    try:
        filter_opts = load_filter_options(DEFAULT_DB_PATH)
    except Exception as exc:
        st.error(f"Failed to connect to database: {exc}")
        st.stop()

    min_date = datetime.strptime(filter_opts["min_date"], "%Y-%m-%d").date()
    max_date = datetime.strptime(filter_opts["max_date"], "%Y-%m-%d").date()
    country_list = filter_opts["countries"]

    # -------------------------------------------------------------------------
    # Sidebar Filters
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.title("🛍️ ShopFlow")
        st.caption("E-commerce Sales Analytics Platform")
        st.markdown("---")
        
        st.subheader("Filter Controls")
        
        # Date filter
        date_selection = st.date_input(
            "Select Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            help="Filter sales transactions by invoice date."
        )
        if isinstance(date_selection, tuple) and len(date_selection) == 2:
            start_date_str = date_selection[0].strftime("%Y-%m-%d")
            end_date_str = date_selection[1].strftime("%Y-%m-%d")
        else:
            start_date_str = min_date.strftime("%Y-%m-%d")
            end_date_str = max_date.strftime("%Y-%m-%d")

        # Country filter
        selected_country = st.selectbox(
            "Filter by Country",
            options=country_list,
            index=0,
            help="Select 'All' or a specific buyer market."
        )

        # Product search
        search_query = st.text_input(
            "Search Product / Stock Code",
            value="",
            placeholder="e.g. 85123A or HEART",
            help="Filter by product name substring or stock code."
        )

        # Reset button
        if st.button("🔄 Reset All Filters", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        st.markdown("---")
        st.markdown("### 📊 Active Scope")
        st.markdown(f"- **Dates:** `{start_date_str}` to `{end_date_str}`")
        st.markdown(f"- **Market:** `{selected_country}`")
        if search_query:
            st.markdown(f"- **Search:** `{search_query}`")

        st.caption("Powered by SQLite 3.11 & Plotly")

    # -------------------------------------------------------------------------
    # Header & Executive Summary
    # -------------------------------------------------------------------------
    st.title("ShopFlow — E-commerce Sales Analytics")
    st.caption(
        f"Real-time analytics over **541,909** retail transactions. "
        f"Active Filter: `{selected_country}` market | `{start_date_str}` to `{end_date_str}`"
    )

    kpis = load_kpis(
        DEFAULT_DB_PATH,
        start_date=start_date_str,
        end_date=end_date_str,
        country=selected_country,
        search_query=search_query
    )

    # Top KPI Row
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Net Revenue</div>
            <div class="metric-value highlight-net">{format_currency(kpis['net_revenue'])}</div>
            <div class="metric-subtitle">Sales minus returns & adjustments</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Gross Sales</div>
            <div class="metric-value highlight-gross">{format_currency(kpis['gross_sales_revenue'])}</div>
            <div class="metric-subtitle">Completed commercial sales</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Sales Orders</div>
            <div class="metric-value highlight-orders">{format_number(kpis['sales_invoices'])}</div>
            <div class="metric-subtitle">Completed distinct invoices</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Gross AOV</div>
            <div class="metric-value highlight-aov">{format_currency(kpis['gross_aov'])}</div>
            <div class="metric-subtitle">Gross Sales / Sales Orders</div>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        units_net = kpis['units_sold'] + kpis['units_returned']
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Units (Sold / Ret)</div>
            <div class="metric-value" style="color: #e2e8f0; font-size: 1.4rem;">
                {format_number(kpis['units_sold'])} <span style="color:#f87171; font-size:1.1rem;">({format_number(kpis['units_returned'])})</span>
            </div>
            <div class="metric-subtitle">Net: {format_number(units_net)} units</div>
        </div>
        """, unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # Analytics Tabs
    # -------------------------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Sales Trends",
        "🏆 Product Performance",
        "🌍 Geographic Markets",
        "👥 Customer Intelligence",
        "🔍 Data Quality & Audits"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Sales Trends & Velocity
    # -------------------------------------------------------------------------
    with tab1:
        st.subheader("Daily & Monthly Sales Velocity")

        df_daily = load_daily(
            DEFAULT_DB_PATH,
            start_date=start_date_str,
            end_date=end_date_str,
            country=selected_country,
            search_query=search_query
        )

        if df_daily.empty:
            st.info("No daily sales records match the selected filter criteria.")
        else:
            # 7-day rolling average for smoother trend line
            df_daily["net_revenue_7d_ma"] = df_daily["net_revenue"].rolling(window=7, min_periods=1).mean().round(2)

            fig_daily = go.Figure()
            fig_daily.add_trace(go.Bar(
                x=df_daily["sales_date"],
                y=df_daily["net_revenue"],
                name="Daily Net Revenue",
                marker_color="#38bdf8",
                opacity=0.6
            ))
            fig_daily.add_trace(go.Scatter(
                x=df_daily["sales_date"],
                y=df_daily["net_revenue_7d_ma"],
                name="7-Day Moving Avg",
                line=dict(color="#f59e0b", width=3)
            ))
            fig_daily.update_layout(
                title="Daily Net Revenue & 7-Day Moving Average",
                xaxis_title="Invoice Date",
                yaxis_title="Net Revenue (GBP £)",
                template="plotly_dark",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=40, r=20, t=60, b=40)
            )
            st.plotly_chart(fig_daily, use_container_width=True)

        col_m1, col_m2 = st.columns([2, 1])

        with col_m1:
            df_monthly = load_monthly(
                DEFAULT_DB_PATH,
                start_date=start_date_str,
                end_date=end_date_str,
                country=selected_country,
                search_query=search_query
            )
            if not df_monthly.empty:
                fig_monthly = px.bar(
                    df_monthly,
                    x="sales_month",
                    y="net_revenue",
                    text_auto=".2s",
                    title="Monthly Net Revenue Performance",
                    labels={"sales_month": "Month", "net_revenue": "Net Revenue (£)"},
                    template="plotly_dark",
                    color="net_revenue",
                    color_continuous_scale="Viridis"
                )
                fig_monthly.update_layout(coloraxis_showscale=False, margin=dict(l=40, r=20, t=60, b=40))
                st.plotly_chart(fig_monthly, use_container_width=True)

        with col_m2:
            st.markdown("#### Monthly Growth Breakdown")
            if not df_monthly.empty:
                display_monthly = df_monthly[[
                    "sales_month", "order_count", "net_revenue", "mom_growth_percent"
                ]].copy()
                display_monthly["net_revenue"] = display_monthly["net_revenue"].apply(format_currency)
                display_monthly["mom_growth_percent"] = display_monthly["mom_growth_percent"].apply(format_percent)
                display_monthly.columns = ["Month", "Orders", "Net Revenue", "MoM Growth"]
                st.dataframe(display_monthly, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 2: Product Performance
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("Top Products & Merchandising Insights")
        
        prod_col1, prod_col2 = st.columns([1, 1])

        with prod_col1:
            df_top_rev = load_products(
                DEFAULT_DB_PATH,
                order_by="revenue",
                limit=10,
                start_date=start_date_str,
                end_date=end_date_str,
                country=selected_country,
                search_query=search_query
            )
            if not df_top_rev.empty:
                fig_top_rev = px.bar(
                    df_top_rev.sort_values(by="gross_revenue", ascending=True),
                    x="gross_revenue",
                    y="product_name",
                    orientation="h",
                    title="Top 10 Products by Gross Revenue (£)",
                    labels={"gross_revenue": "Gross Revenue (£)", "product_name": "Product"},
                    template="plotly_dark",
                    color="gross_revenue",
                    color_continuous_scale="Teal"
                )
                fig_top_rev.update_layout(coloraxis_showscale=False, margin=dict(l=40, r=20, t=60, b=40))
                st.plotly_chart(fig_top_rev, use_container_width=True)

        with prod_col2:
            df_top_qty = load_products(
                DEFAULT_DB_PATH,
                order_by="quantity",
                limit=10,
                start_date=start_date_str,
                end_date=end_date_str,
                country=selected_country,
                search_query=search_query
            )
            if not df_top_qty.empty:
                fig_top_qty = px.bar(
                    df_top_qty.sort_values(by="gross_units_sold", ascending=True),
                    x="gross_units_sold",
                    y="product_name",
                    orientation="h",
                    title="Top 10 Products by Volume (Units Sold)",
                    labels={"gross_units_sold": "Units Sold", "product_name": "Product"},
                    template="plotly_dark",
                    color="gross_units_sold",
                    color_continuous_scale="Blues"
                )
                fig_top_qty.update_layout(coloraxis_showscale=False, margin=dict(l=40, r=20, t=60, b=40))
                st.plotly_chart(fig_top_qty, use_container_width=True)

        st.markdown("#### Merchandising Performance Data Table")
        if not df_top_rev.empty:
            table_df = df_top_rev.copy()
            table_df["gross_revenue"] = table_df["gross_revenue"].apply(format_currency)
            table_df["net_revenue"] = table_df["net_revenue"].apply(format_currency)
            table_df["gross_units_sold"] = table_df["gross_units_sold"].apply(format_number)
            table_df["units_returned"] = table_df["units_returned"].apply(format_number)
            table_df["net_units_sold"] = table_df["net_units_sold"].apply(format_number)
            table_df.columns = [
                "Stock Code", "Product Name", "Units Sold", "Units Returned", 
                "Net Units", "Gross Revenue", "Net Revenue", "Orders"
            ]
            st.dataframe(table_df, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 3: Geographic Markets
    # -------------------------------------------------------------------------
    with tab3:
        st.subheader("Global Geographic Sales Performance")
        df_country = load_countries(DEFAULT_DB_PATH, limit=15)
        
        geo_col1, geo_col2 = st.columns([3, 2])
        
        with geo_col1:
            fig_country = px.bar(
                df_country.head(10).sort_values(by="net_revenue", ascending=True),
                x="net_revenue",
                y="country",
                orientation="h",
                title="Top 10 International Markets by Net Revenue (£)",
                labels={"net_revenue": "Net Revenue (£)", "country": "Country"},
                template="plotly_dark",
                color="net_revenue",
                color_continuous_scale="Purples"
            )
            fig_country.update_layout(coloraxis_showscale=False, margin=dict(l=40, r=20, t=60, b=40))
            st.plotly_chart(fig_country, use_container_width=True)

        with geo_col2:
            fig_pie = px.pie(
                df_country.head(6),
                values="net_revenue",
                names="country",
                title="Market Share Concentration (Top 6 Countries)",
                template="plotly_dark",
                hole=0.4
            )
            fig_pie.update_layout(margin=dict(l=20, r=20, t=60, b=20))
            st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown("#### Geographic Market Breakdown")
        country_display = df_country.copy()
        country_display["gross_revenue"] = country_display["gross_revenue"].apply(format_currency)
        country_display["cancellations_offset"] = country_display["cancellations_offset"].apply(format_currency)
        country_display["net_revenue"] = country_display["net_revenue"].apply(format_currency)
        country_display["sales_orders"] = country_display["sales_orders"].apply(format_number)
        country_display["identified_customers"] = country_display["identified_customers"].apply(format_number)
        country_display["guest_orders"] = country_display["guest_orders"].apply(format_number)
        country_display.columns = [
            "Country", "Sales Orders", "Identified Customers", "Guest Orders", 
            "Units Sold", "Gross Revenue", "Returns Offset", "Net Revenue", "% Global Revenue"
        ]
        st.dataframe(country_display, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 4: Customer Intelligence
    # -------------------------------------------------------------------------
    with tab4:
        st.subheader("Customer Lifetime Value (LTV) & Retention")
        cust_kpis = load_customer_kpis(DEFAULT_DB_PATH)
        
        c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
        with c_kpi1:
            st.metric("Total Identified Customers", format_number(cust_kpis['total_identified_customers']))
        with c_kpi2:
            st.metric("Repeat Customer Rate", f"{cust_kpis['repeat_customer_rate_pct']:.1f}%")
        with c_kpi3:
            st.metric("Repeat Buyers (>1 order)", format_number(cust_kpis['repeat_customers']))
        with c_kpi4:
            st.metric("Avg Lifetime Spend", format_currency(cust_kpis['avg_spend_per_customer']))

        st.markdown("#### Top 20 Highest-Value Customers (LTV)")
        df_cust = load_customers(DEFAULT_DB_PATH, limit=20)
        cust_display = df_cust.copy()
        cust_display["gross_spend"] = cust_display["gross_spend"].apply(format_currency)
        cust_display["returns_refunded"] = cust_display["returns_refunded"].apply(format_currency)
        cust_display["net_lifetime_spend"] = cust_display["net_lifetime_spend"].apply(format_currency)
        cust_display.columns = [
            "Customer ID", "Country", "Completed Orders", "Cancellations", 
            "Units Purchased", "Gross Spend", "Refunds", "Net Lifetime Spend", "Segment"
        ]
        st.dataframe(cust_display, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # TAB 5: Data Quality & Audits
    # -------------------------------------------------------------------------
    with tab5:
        st.subheader("Data Quality, Anomaly Tracking & Financial Balance")
        
        st.markdown("""
        > **Audit Policy:** In strict adherence to data engineering best practices, unusual or 
        > non-standard transactions are preserved and tagged with auditable boolean flags rather than 
        > silently discarded.
        """)

        df_returns = load_returns(DEFAULT_DB_PATH)
        st.markdown("#### Transaction Classification Audit Table")
        returns_display = df_returns.copy()
        returns_display["net_revenue_impact"] = returns_display["net_revenue_impact"].apply(format_currency)
        returns_display["record_count"] = returns_display["record_count"].apply(format_number)
        returns_display["distinct_invoices"] = returns_display["distinct_invoices"].apply(format_number)
        returns_display["net_units_impact"] = returns_display["net_units_impact"].apply(format_number)
        returns_display.columns = [
            "Anomaly Category", "Records", "Invoices", "Net Units Impact", 
            "Net Revenue Impact", "Empirical Observation"
        ]
        st.dataframe(returns_display, use_container_width=True, hide_index=True)

        st.markdown("#### Exact SQL Financial Balance Reconciliation")
        recon = load_reconciliation(DEFAULT_DB_PATH)
        
        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            st.metric("Gross Normal Sales (A)", format_currency(recon['gross_normal_sales']))
            st.metric("Returns Offset (B)", format_currency(recon['cancellations_non_dup']))
        with col_r2:
            st.metric("Bad Debt Adjustments (C)", format_currency(recon['bad_debt_adjustments']))
            st.metric("Other Neg Qty Adjustments (D)", format_currency(recon['other_neg_qty']))
        with col_r3:
            st.metric("Reconciled Net Revenue (A+B+C+D)", format_currency(recon['component_sum']))
            st.metric("Discrepancy (E - F)", format_currency(recon['discrepancy']))

        if recon['discrepancy'] == 0.0:
            st.success("✅ **Perfect Financial Balance**: The database reconciles with £0.0000 discrepancy.")


if __name__ == "__main__":
    main()
