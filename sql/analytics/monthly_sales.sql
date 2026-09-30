-- ==============================================================================
-- ShopFlow - Monthly Sales Trends & Growth
-- Aggregates monthly revenue, orders, and Month-over-Month (MoM) growth rates.
-- ==============================================================================

WITH monthly_aggregations AS (
    SELECT
        SUBSTR(invoice_date, 1, 7)                                      AS sales_month,
        COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END) AS order_count,
        SUM(CASE WHEN is_normal_sale = 1 THEN quantity ELSE 0 END)       AS units_sold,
        ROUND(SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END), 2) AS gross_revenue,
        ROUND(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS returns_offset,
        ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS net_revenue
    FROM retail_transactions
    GROUP BY SUBSTR(invoice_date, 1, 7)
)
SELECT
    sales_month,
    order_count,
    units_sold,
    gross_revenue,
    returns_offset,
    net_revenue,
    LAG(net_revenue) OVER (ORDER BY sales_month ASC)                     AS prev_month_net_revenue,
    ROUND(
        (net_revenue - LAG(net_revenue) OVER (ORDER BY sales_month ASC)) / 
        NULLIF(LAG(net_revenue) OVER (ORDER BY sales_month ASC), 0) * 100, 
        2
    ) AS mom_growth_percent
FROM monthly_aggregations
ORDER BY sales_month ASC;
