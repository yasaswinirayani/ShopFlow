-- ==============================================================================
-- ShopFlow - Customer Segmentation & Lifetime Spend Analysis
-- Analyzes identified, registered customers (excluding guest checkouts).
-- Computes order counts, return activity, and net lifetime spend.
-- ==============================================================================

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
WHERE customer_id IS NOT NULL -- Exclude anonymous guest checkouts from customer cohorts
GROUP BY customer_id
ORDER BY net_lifetime_spend DESC
LIMIT 50;
