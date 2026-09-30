-- ==============================================================================
-- ShopFlow - Sales Overview & High-Level KPIs
-- Computes core platform health metrics, transaction counts, and revenue.
-- ==============================================================================

SELECT
    -- Row and transaction line counts
    COUNT(*)                                                            AS total_transaction_lines,
    SUM(CASE WHEN is_duplicate = 0 THEN 1 ELSE 0 END)                   AS non_duplicate_lines,
    SUM(CASE WHEN is_duplicate = 1 THEN 1 ELSE 0 END)                   AS duplicate_lines,

    -- Distinct invoice counts
    COUNT(DISTINCT invoice_no)                                          AS total_distinct_invoices,
    COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END)     AS sales_invoices,
    COUNT(DISTINCT CASE WHEN is_cancelled = 1 THEN invoice_no END)       AS cancellation_invoices,

    -- Unit volume metrics
    SUM(CASE WHEN is_normal_sale = 1 THEN quantity ELSE 0 END)          AS units_sold,
    SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN quantity ELSE 0 END) AS units_returned,

    -- Financial Revenue Totals (GBP)
    ROUND(SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END), 2) AS gross_sales_revenue,
    ROUND(SUM(CASE WHEN is_cancelled = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS cancellations_revenue_offset,
    ROUND(SUM(CASE WHEN is_negative_price = 1 AND is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS bad_debt_adjustments,
    ROUND(SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END), 2) AS net_revenue,

    -- Average Order Value (AOV) Metrics
    -- Gross AOV Denominator: Distinct normal sales invoices (19,960)
    ROUND(
        SUM(CASE WHEN is_normal_sale = 1 THEN line_revenue ELSE 0 END) / 
        NULLIF(COUNT(DISTINCT CASE WHEN is_normal_sale = 1 THEN invoice_no END), 0),
        2
    ) AS gross_aov_per_sales_order,

    -- Net AOV Denominator: Distinct non-duplicate invoices (25,900)
    ROUND(
        SUM(CASE WHEN is_duplicate = 0 THEN line_revenue ELSE 0 END) / 
        NULLIF(COUNT(DISTINCT CASE WHEN is_duplicate = 0 THEN invoice_no END), 0),
        2
    ) AS net_aov_per_distinct_order
FROM retail_transactions;
