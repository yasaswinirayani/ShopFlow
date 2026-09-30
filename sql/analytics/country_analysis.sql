-- ==============================================================================
-- ShopFlow - Country & Geographic Sales Performance
-- Aggregates revenue, distinct orders, and registered customers by country.
-- Missing Customer IDs are accounted for via guest_orders to avoid inflating
-- registered customer counts while capturing all geographic revenue.
-- ==============================================================================

SELECT
    country,
    COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END)      AS sales_orders,
    COUNT(DISTINCT customer_id)                                           AS identified_customers,
    COUNT(DISTINCT CASE WHEN is_normal_sale = 1 AND customer_id IS NULL THEN invoice_no END) AS guest_orders,
    SUM(CASE WHEN is_normal_sale = 1 THEN quantity ELSE 0 END)            AS units_sold,
    ROUND(SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END), 2) AS gross_revenue,
    ROUND(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS cancellations_offset,
    ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS net_revenue,
    ROUND(
        (SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END) / 
         (SELECT SUM(line_revenue) FROM retail_transactions WHERE is_duplicate = 0)) * 100, 
        2
    ) AS pct_of_global_net_revenue
FROM retail_transactions
GROUP BY country
ORDER BY net_revenue DESC;
