-- ==============================================================================
-- ShopFlow - Daily Sales & Order Velocity
-- Daily time-series breakdown of orders, units, gross revenue, and net revenue.
-- Optimized to feed interactive daily trend visualizations in Streamlit.
-- ==============================================================================

SELECT
    SUBSTR(invoice_date, 1, 10)                                         AS sales_date,
    COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END)      AS order_count,
    SUM(CASE WHEN is_normal_sale = 1 THEN quantity ELSE 0 END)            AS units_sold,
    SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN quantity ELSE 0 END) AS units_returned,
    ROUND(SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END), 2) AS gross_revenue,
    ROUND(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS returns_offset,
    ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS net_revenue
FROM retail_transactions
GROUP BY SUBSTR(invoice_date, 1, 10)
ORDER BY sales_date ASC;
