"""
Unit tests for src/pipeline.py
Tests end-to-end pipeline orchestration, missing files, validation failures,
idempotency, and database protection using temporary files.
"""

import pytest
import sqlite3
import pandas as pd
from pathlib import Path
from src.pipeline import run_pipeline, PipelineError
from src.load import query_database_audit_metrics, DEFAULT_SCHEMA_PATH


@pytest.fixture
def sample_csv_data(tmp_path):
    """Creates a temporary valid CSV dataset for fast pipeline testing."""
    csv_path = tmp_path / "test_retail.csv"
    df = pd.DataFrame({
        "InvoiceNo": ["536365", "C536366", "536367", "536367"],
        "StockCode": ["85123A", "85123A", "71053", "71053"],
        "Description": ["WHITE HEART", "WHITE HEART", "LANTERN", "LANTERN"],
        "Quantity": [6, -2, 4, 4],
        "InvoiceDate": ["2010-12-01 08:26:00", "2010-12-01 09:00:00", "2010-12-01 10:00:00", "2010-12-01 10:00:00"],
        "UnitPrice": [2.50, 2.50, 3.00, 3.00],
        "CustomerID": [17850.0, 17850.0, None, None],
        "Country": ["United Kingdom", "United Kingdom", "France", "France"]
    })
    df.to_csv(csv_path, index=False)
    return csv_path


def test_pipeline_successful_run(tmp_path, sample_csv_data):
    db_file = tmp_path / "pipeline_test.db"
    summary_file = tmp_path / "summary.txt"
    profile_file = tmp_path / "profile.txt"
    
    result = run_pipeline(
        raw_data_path=sample_csv_data,
        db_path=db_file,
        schema_path=DEFAULT_SCHEMA_PATH,
        profile_report_path=profile_file,
        summary_report_path=summary_file,
        full_refresh=True
    )
    
    assert result["status"] == "SUCCESS"
    assert result["raw_rows"] == 4
    assert result["loaded_rows"] == 4
    assert db_file.exists()
    assert summary_file.exists()
    assert "SUCCESS" in summary_file.read_text()


def test_pipeline_missing_raw_file(tmp_path):
    non_existent = tmp_path / "does_not_exist.xlsx"
    summary_file = tmp_path / "summary.txt"
    
    with pytest.raises(PipelineError, match="Raw dataset not found"):
        run_pipeline(
            raw_data_path=non_existent,
            summary_report_path=summary_file
        )
    assert summary_file.exists()
    assert "FAILED" in summary_file.read_text()


def test_pipeline_validation_failure(tmp_path):
    # CSV missing essential column
    bad_csv = tmp_path / "bad_retail.csv"
    bad_df = pd.DataFrame({
        "InvoiceNo": ["536365"],
        "StockCode": ["85123A"]
        # Missing Quantity, UnitPrice, etc.
    })
    bad_df.to_csv(bad_csv, index=False)
    
    db_file = tmp_path / "should_not_be_created.db"
    summary_file = tmp_path / "summary.txt"
    
    with pytest.raises(PipelineError, match="Validation failed|transformation failed"):
        run_pipeline(
            raw_data_path=bad_csv,
            db_path=db_file,
            summary_report_path=summary_file
        )
    assert not db_file.exists()


def test_pipeline_repeated_runs_idempotent(tmp_path, sample_csv_data):
    db_file = tmp_path / "repeat_test.db"
    summary_file = tmp_path / "summary.txt"
    
    # First execution
    r1 = run_pipeline(
        raw_data_path=sample_csv_data,
        db_path=db_file,
        summary_report_path=summary_file,
        profile_report_path=None,
        full_refresh=True
    )
    assert r1["loaded_rows"] == 4
    
    # Second execution
    r2 = run_pipeline(
        raw_data_path=sample_csv_data,
        db_path=db_file,
        summary_report_path=summary_file,
        profile_report_path=None,
        full_refresh=True
    )
    assert r2["loaded_rows"] == 4
    
    metrics = query_database_audit_metrics(db_file)
    assert metrics["total_rows"] == 4


def test_pipeline_protects_existing_valid_database_on_failure(tmp_path, sample_csv_data):
    db_file = tmp_path / "protected_db.db"
    summary_file = tmp_path / "summary.txt"
    
    # 1. Establish valid database with 4 rows
    run_pipeline(
        raw_data_path=sample_csv_data,
        db_path=db_file,
        summary_report_path=summary_file,
        profile_report_path=None,
        full_refresh=True
    )
    m_initial = query_database_audit_metrics(db_file)
    assert m_initial["total_rows"] == 4
    
    # 2. Corrupt raw file for next run
    corrupt_csv = tmp_path / "corrupt.csv"
    pd.DataFrame({"bad_column": [1, 2]}).to_csv(corrupt_csv, index=False)
    
    # 3. Pipeline must fail before touching the DB
    with pytest.raises(PipelineError):
        run_pipeline(
            raw_data_path=corrupt_csv,
            db_path=db_file,
            summary_report_path=summary_file,
            profile_report_path=None
        )
        
    # 4. Previously valid database remains 100% intact!
    m_after_failure = query_database_audit_metrics(db_file)
    assert m_after_failure["total_rows"] == 4
