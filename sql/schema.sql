-- ==============================================================================
-- ShopFlow - E-commerce Sales Platform Database Schema
-- SQLite Target: data/processed/shopflow.db
-- Table: retail_transactions
-- ==============================================================================

-- Drop existing objects for idempotent recreation
DROP TABLE IF EXISTS retail_transactions;

CREATE TABLE retail_transactions (
    -- Stable row identifier
    line_id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Source business columns
    invoice_no                  TEXT NOT NULL,
    stock_code                  TEXT NOT NULL,
    description                 TEXT,
    quantity                    INTEGER NOT NULL,
    invoice_date                TEXT NOT NULL, -- ISO-8601 string: YYYY-MM-DD HH:MM:SS
    unit_price                  REAL NOT NULL,
    customer_id                 INTEGER,       -- Nullable to preserve guest checkouts
    country                     TEXT NOT NULL,
    
    -- Computed financial metric
    line_revenue                REAL NOT NULL,
    
    -- Audit & transaction classification flags (0 = False, 1 = True)
    is_duplicate                INTEGER NOT NULL DEFAULT 0,
    is_cancelled                INTEGER NOT NULL DEFAULT 0,
    is_negative_quantity        INTEGER NOT NULL DEFAULT 0,
    is_zero_quantity            INTEGER NOT NULL DEFAULT 0,
    is_negative_price           INTEGER NOT NULL DEFAULT 0,
    is_zero_price               INTEGER NOT NULL DEFAULT 0,
    is_missing_customer         INTEGER NOT NULL DEFAULT 0,
    is_missing_description      INTEGER NOT NULL DEFAULT 0,
    is_normal_sale              INTEGER NOT NULL DEFAULT 0,
    transaction_category        TEXT NOT NULL,
    
    -- Audit timestamp
    loaded_at                   TEXT DEFAULT (datetime('now'))
);

-- Performance indexes for analytical queries and filtering
CREATE INDEX IF NOT EXISTS idx_tx_invoice_no ON retail_transactions(invoice_no);
CREATE INDEX IF NOT EXISTS idx_tx_invoice_date ON retail_transactions(invoice_date);
CREATE INDEX IF NOT EXISTS idx_tx_stock_code ON retail_transactions(stock_code);
CREATE INDEX IF NOT EXISTS idx_tx_customer_id ON retail_transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_tx_is_normal_sale ON retail_transactions(is_normal_sale);
CREATE INDEX IF NOT EXISTS idx_tx_is_duplicate ON retail_transactions(is_duplicate);
CREATE INDEX IF NOT EXISTS idx_tx_category ON retail_transactions(transaction_category);
