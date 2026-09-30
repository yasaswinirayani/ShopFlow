"""
ShopFlow - Data Transformation Module
Provides separate, documented transformation and classification functions
for e-commerce retail data without modifying the raw source dataset.
"""

from typing import List, Optional
import pandas as pd
import numpy as np

REQUIRED_COLUMNS: List[str] = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country"
]


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Strips leading/trailing whitespace from column names and validates
    that all required columns are present.
    """
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in dataset: {missing_cols}")
    
    return df


def clean_text_fields(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans string/text fields carefully without changing meaningful product codes.
    - Strips whitespace from InvoiceNo, StockCode, Country, and Description.
    - Preserves case in StockCode (e.g., '85123A', 'POST', 'M') to maintain integrity.
    - Standardizes missing Description with 'UNSPECIFIED' and adds an audit flag.
    """
    df = df.copy()
    
    # Clean text columns
    for col in ["InvoiceNo", "Country"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    if "StockCode" in df.columns:
        # Convert to string and strip without altering character casing
        df["StockCode"] = df["StockCode"].astype(str).str.strip()

    if "Description" in df.columns:
        is_missing_desc = df["Description"].isna() | (df["Description"].astype(str).str.strip() == "")
        df["is_missing_description"] = is_missing_desc
        df["Description"] = df["Description"].fillna("UNSPECIFIED").astype(str).str.strip()
    
    return df


def convert_data_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converts InvoiceDate to datetime, Quantity and UnitPrice to numeric types,
    and CustomerID to nullable integer type.
    """
    df = df.copy()

    # Convert InvoiceDate
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")

    # Convert Quantity to numeric integer
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce").fillna(0).astype("int64")

    # Convert UnitPrice to float
    df["UnitPrice"] = pd.to_numeric(df["UnitPrice"], errors="coerce").fillna(0.0).astype("float64")

    # CustomerID as nullable integer (Int64 allows NA without converting to float)
    df["CustomerID"] = pd.to_numeric(df["CustomerID"], errors="coerce").astype("Int64")

    return df


def calculate_line_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates LineRevenue = Quantity * UnitPrice.
    
    Note on financial calculations:
    - LineRevenue represents the nominal monetary value for each line item.
    - For normal sales, Quantity > 0 and UnitPrice > 0, producing positive revenue.
    - For cancellations or returns (negative quantity), LineRevenue is negative,
      offsetting gross revenue when summing net sales.
    - Zero or negative unit price rows produce zero or negative line revenue.
    """
    df = df.copy()
    df["LineRevenue"] = (df["Quantity"] * df["UnitPrice"]).round(4)
    return df


def detect_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identifies exact duplicate rows across all original business columns.
    Marks subsequent occurrences with is_duplicate = True while keeping
    the first occurrence as is_duplicate = False.
    """
    df = df.copy()
    cols_to_check = [col for col in REQUIRED_COLUMNS if col in df.columns]
    df["is_duplicate"] = df.duplicated(subset=cols_to_check, keep="first")
    return df


def classify_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies explicit transaction classifications and audit flags.
    
    Flags added:
    - is_cancelled: InvoiceNo starts with 'C' (customer cancellation or return).
    - is_negative_quantity: Quantity < 0.
    - is_zero_quantity: Quantity == 0.
    - is_negative_price: UnitPrice < 0 (accounting adjustments like bad debt).
    - is_zero_price: UnitPrice == 0 (free samples, gifts, or adjustments).
    - is_missing_customer: CustomerID is null (guest checkout).
    - is_normal_sale: Standard commercial sale (positive qty, positive price,
                      not cancelled, not duplicate).
    - transaction_category: High-level category label for auditing and reporting.
    """
    df = df.copy()
    
    # Invoices starting with 'C'
    invoice_str = df["InvoiceNo"].astype(str)
    is_cancelled = invoice_str.str.startswith("C", na=False)
    
    is_neg_qty = df["Quantity"] < 0
    is_zero_qty = df["Quantity"] == 0
    is_neg_price = df["UnitPrice"] < 0
    is_zero_price = df["UnitPrice"] == 0
    is_missing_cust = df["CustomerID"].isna()
    is_dup = df.get("is_duplicate", pd.Series(False, index=df.index))

    # Set boolean flags
    df["is_cancelled"] = is_cancelled
    df["is_negative_quantity"] = is_neg_qty
    df["is_zero_quantity"] = is_zero_qty
    df["is_negative_price"] = is_neg_price
    df["is_zero_price"] = is_zero_price
    df["is_missing_customer"] = is_missing_cust

    # Normal sale: positive quantity, positive price, not cancelled, not duplicate
    df["is_normal_sale"] = (
        (df["Quantity"] > 0) &
        (df["UnitPrice"] > 0) &
        (~df["is_cancelled"]) &
        (~is_dup)
    )

    # Multi-category label (ordered evaluation for primary classification)
    conditions = [
        is_dup,
        is_cancelled,
        is_neg_price,
        is_zero_price,
        is_neg_qty,
        is_zero_qty,
        df["is_normal_sale"]
    ]
    choices = [
        "DUPLICATE",
        "CANCELLED_INVOICE",
        "NEGATIVE_PRICE_ADJUSTMENT",
        "ZERO_PRICE_ITEM",
        "NEGATIVE_QUANTITY_OTHER",
        "ZERO_QUANTITY",
        "NORMAL_SALE"
    ]
    df["transaction_category"] = np.select(conditions, choices, default="OTHER")

    return df


def transform_retail_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Full pipeline orchestrator:
    1. Validates and standardizes column names.
    2. Cleans text fields and handles missing descriptions.
    3. Converts data types (dates, numerics, nullable customer IDs).
    4. Detects exact duplicates.
    5. Calculates line-item revenue.
    6. Classifies transactions and sets audit flags.
    
    Row count is 100% preserved so that every raw record remains auditable.
    """
    df_transformed = standardize_columns(df)
    df_transformed = clean_text_fields(df_transformed)
    df_transformed = convert_data_types(df_transformed)
    df_transformed = detect_duplicates(df_transformed)
    df_transformed = calculate_line_revenue(df_transformed)
    df_transformed = classify_transactions(df_transformed)
    return df_transformed
