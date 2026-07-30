import csv
import os

from backend.scout.parser import parse_csv


def _write_csv(tmp_path, rows, fieldnames):
    path = os.path.join(tmp_path, "test.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_parses_basic_row(tmp_path):
    path = _write_csv(
        tmp_path,
        [{"Property Address": "123 Main St", "Owner Phone": "(209) 555-1212", "Beds": "3"}],
        ["Property Address", "Owner Phone", "Beds"],
    )
    rows = parse_csv(str(path))
    assert len(rows) == 1
    assert rows[0]["address"] == "123 Main St"
    assert rows[0]["contact"]["phone"] == "(209) 555-1212"
    assert rows[0]["beds"] == 3


def test_skips_rows_without_address(tmp_path):
    path = _write_csv(
        tmp_path,
        [{"Property Address": "", "Beds": "3"}],
        ["Property Address", "Beds"],
    )
    rows = parse_csv(str(path))
    assert rows == []


def test_dedupes_by_apn(tmp_path):
    path = _write_csv(
        tmp_path,
        [
            {"Property Address": "123 Main St", "APN": "001-002-003"},
            {"Property Address": "456 Other St", "APN": "001-002-003"},
        ],
        ["Property Address", "APN"],
    )
    rows = parse_csv(str(path))
    assert len(rows) == 1


def test_money_fields_converted_to_cents(tmp_path):
    path = _write_csv(
        tmp_path,
        [{"Property Address": "123 Main St", "Last Sale Price": "$150,000"}],
        ["Property Address", "Last Sale Price"],
    )
    rows = parse_csv(str(path))
    assert rows[0]["last_sale_price"] == 15000000


def test_missing_file_returns_empty_list():
    assert parse_csv("/nonexistent/path.csv") == []
