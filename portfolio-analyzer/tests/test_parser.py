"""Tests for portfolio-analyzer/parser.py"""
import importlib.util
import json
import os
import pathlib
import unittest
from unittest.mock import MagicMock, patch

import openpyxl

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
_PARSER_PATH = pathlib.Path(__file__).parent.parent / "parser.py"

# Load parser module from file path (avoids hyphen-in-package-name issue)
_spec = importlib.util.spec_from_file_location("parser", _PARSER_PATH)
parser = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parser)


def _make_excel_file(path: str) -> str:
    """Create a minimal Excel file with portfolio data and return its path."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Portfolio"
    ws.append(["Ticker", "Weight", "Value", "Cost Basis", "Shares"])
    rows = [
        ("NVDA", 0.12, 17076.0, 8000.0, None),
        ("AAPL", 0.10, 14230.0, 10000.0, None),
        ("MSFT", 0.09, 12807.0, 9000.0, None),
        ("JPM",  0.07, 9961.0,  8000.0, None),
        ("BND",  0.05, 7115.0,  7200.0, None),
    ]
    for row in rows:
        ws.append(list(row))
    wb.save(path)
    return path


class TestParserDictPassthrough(unittest.TestCase):

    def test_parse_dict_returns_valid_holdings(self):
        with open(FIXTURES / "sample_holdings.json") as f:
            data = json.load(f)
        result = parser.parse(data)
        self.assertEqual(result["data_completeness"], "full")
        self.assertEqual(len(result["positions"]), 5)
        self.assertEqual(result["total_value"], 142300.0)

    def test_parse_dict_position_fields(self):
        with open(FIXTURES / "sample_holdings.json") as f:
            data = json.load(f)
        result = parser.parse(data)
        pos = result["positions"][0]
        self.assertEqual(pos["ticker"], "NVDA")
        self.assertAlmostEqual(pos["weight"], 0.12)
        self.assertIn("value", pos)
        self.assertIn("cost_basis", pos)
        self.assertIn("shares", pos)

    def test_parse_weights_only_dict(self):
        with open(FIXTURES / "sample_weights_only.json") as f:
            data = json.load(f)
        result = parser.parse(data)
        self.assertEqual(result["data_completeness"], "ticker_weight_only")
        self.assertIsNone(result["total_value"])
        for pos in result["positions"]:
            self.assertIsNone(pos["value"])
            self.assertIsNone(pos["cost_basis"])


class TestParserExcel(unittest.TestCase):

    def setUp(self):
        self.excel_path = str(FIXTURES / "sample_excel.xlsx")
        _make_excel_file(self.excel_path)

    def tearDown(self):
        if os.path.exists(self.excel_path):
            os.remove(self.excel_path)

    def test_parse_excel_returns_5_positions(self):
        result = parser.parse(self.excel_path)
        self.assertEqual(len(result["positions"]), 5)

    def test_parse_excel_tickers_correct(self):
        result = parser.parse(self.excel_path)
        tickers = [p["ticker"] for p in result["positions"]]
        self.assertIn("NVDA", tickers)
        self.assertIn("BND", tickers)

    def test_parse_excel_weights_are_floats(self):
        result = parser.parse(self.excel_path)
        for pos in result["positions"]:
            self.assertIsInstance(pos["weight"], float)
            self.assertGreater(pos["weight"], 0)
            self.assertLessEqual(pos["weight"], 1)

    def test_parse_excel_completeness(self):
        result = parser.parse(self.excel_path)
        self.assertIn(result["data_completeness"], ("full", "partial"))


class TestParserPDF(unittest.TestCase):

    def test_parse_pdf_uses_pdfplumber(self):
        mock_page = MagicMock()
        mock_page.extract_tables.return_value = [
            [
                ["Ticker", "Weight", "Value", "Cost Basis", "Shares"],
                ["NVDA", "12%", "17076", "8000", ""],
                ["AAPL", "10%", "14230", "10000", ""],
            ]
        ]
        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parser.parse("/fake/path/portfolio.pdf")

        self.assertEqual(len(result["positions"]), 2)
        tickers = [p["ticker"] for p in result["positions"]]
        self.assertIn("NVDA", tickers)
        self.assertIn("AAPL", tickers)

    def test_parse_pdf_weight_percent_string_normalized(self):
        mock_page = MagicMock()
        mock_page.extract_tables.return_value = [
            [
                ["Symbol", "Allocation", "Market Value"],
                ["NVDA", "12%", "17076"],
                ["AAPL", "10%", "14230"],
            ]
        ]
        mock_pdf = MagicMock()
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdf.pages = [mock_page]

        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parser.parse("/fake/path/portfolio.pdf")

        nvda = next(p for p in result["positions"] if p["ticker"] == "NVDA")
        self.assertAlmostEqual(nvda["weight"], 0.12, places=4)


class TestParserEdgeCases(unittest.TestCase):

    def test_parse_raises_on_unknown_type(self):
        with self.assertRaises((ValueError, TypeError)):
            parser.parse(12345)

    def test_parse_empty_positions_list(self):
        data = {
            "positions": [],
            "total_value": None,
            "data_completeness": "ticker_weight_only"
        }
        result = parser.parse(data)
        self.assertEqual(result["positions"], [])


if __name__ == "__main__":
    unittest.main()
