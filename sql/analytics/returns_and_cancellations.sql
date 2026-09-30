-- ==============================================================================
-- ShopFlow - Returns, Cancellations, and Accounting Adjustments
-- Categorizes unusual records and distinguishes empirical observations
-- from business assumptions.
-- ==============================================================================

SELECT
    'Cancelled Invoices (Starts with C)'                                AS anomaly_category,
    COUNT(*)                                                            AS record_count,
    COUNT(DISTINCT invoice_no)                                          AS distinct_invoices,
    SUM(quantity)                                                       AS net_units_impact,
    ROUND(SUM(line_revenue), 2)                                         AS net_revenue_impact,
    'Definitive order cancellation or return initiated by customer'     AS observed_behavior
FROM retail_transactions
WHERE is_cancelled = 1 AND is_duplicate = 0

UNION ALL

SELECT
    'Other Negative Quantity (Non-Cancelled)',
    COUNT(*),
    COUNT(DISTINCT invoice_no),
    SUM(quantity),
    ROUND(SUM(line_revenue), 2),
    'Inventory write-offs, damaged stock, or manual corrections (UnitPrice = 0)'
FROM retail_transactions
WHERE is_negative_quantity = 1 AND is_cancelled = 0 AND is_duplicate = 0

UNION ALL

SELECT
    'Negative Price Adjustments (Bad Debt)',
    COUNT(*),
    COUNT(DISTINCT invoice_no),
    SUM(quantity),
    ROUND(SUM(line_revenue), 2),
    'Accounting ledger adjustment (e.g. Adjust bad debt) rather than item sale'
FROM retail_transactions
WHERE is_negative_price = 1 AND is_duplicate = 0

UNION ALL

SELECT
    'Zero Price Promotional / Gift Items',
    COUNT(*),
    COUNT(DISTINCT invoice_no),
    SUM(quantity),
    ROUND(SUM(line_revenue), 2),
    'Free samples, gifts, or zero-priced line items'
FROM retail_transactions
WHERE is_zero_price = 1 AND is_negative_quantity = 0 AND is_duplicate = 0;
