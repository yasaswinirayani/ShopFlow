-- ==============================================================================
-- ShopFlow - Top Performing Products
-- Ranks products by Gross Revenue, Net Revenue, and Units Sold.
-- Resolves the canonical commercial product name from valid sales rather than
-- picking administrative inventory write-off notes (e.g. 'faulty', 'damaged').
-- Standardizes missing descriptions as 'UNSPECIFIED'.
-- ==============================================================================

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
    SUM(CASE WHEN t.is_normal_sale = 1 THEN t.quantity ELSE 0 END)       AS gross_units_sold,
    SUM(CASE WHEN t.is_cancelled = 1 AND t.is_duplicate = 0 THEN t.quantity ELSE 0 END) AS units_returned,
    SUM(CASE WHEN t.is_duplicate = 0 THEN t.quantity ELSE 0 END)         AS net_units_sold,
    ROUND(SUM(CASE WHEN t.is_normal_sale = 1 THEN t.line_revenue ELSE 0 END), 2) AS gross_revenue,
    ROUND(SUM(CASE WHEN t.is_duplicate = 0 THEN t.line_revenue ELSE 0 END), 2) AS net_revenue,
    COUNT(DISTINCT CASE WHEN t.is_normal_sale = 1 THEN t.invoice_no END)  AS order_count
FROM retail_transactions t
LEFT JOIN canonical_names cn ON t.stock_code = cn.stock_code AND cn.rn = 1
WHERE t.stock_code NOT IN ('POST', 'D', 'M', 'BANK CHARGES', 'PADS', 'DOT', 'CRUK') -- Exclude fee codes
GROUP BY t.stock_code
ORDER BY gross_revenue DESC
LIMIT 10;
