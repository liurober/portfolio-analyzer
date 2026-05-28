import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from formatter import format_scan_result, RISK_EMOJI, CATEGORY_EMOJI


def test_risk_emoji_mapping():
    assert RISK_EMOJI["high"] == "🔴"
    assert RISK_EMOJI["medium"] == "🟡"
    assert RISK_EMOJI["low"] == "🟢"


def test_format_all_clear():
    scan = {
        "product_name": "Baby Lotion",
        "total_ingredients": 5,
        "matches": [],
        "unknowns": [],
        "clean": ["water", "zinc oxide", "shea butter", "glycerin", "vitamin e"],
    }
    result = format_scan_result(scan, web_results=[])
    assert "✅" in result
    assert "Baby Lotion" in result
    assert "no g6pd triggers" in result.lower()


def test_format_with_high_risk_match():
    scan = {
        "product_name": "Cooling Gel",
        "total_ingredients": 3,
        "matches": [
            {"ingredient": "Camphor", "matched_as": "camphor", "category": "cosmetics",
             "risk": "high", "notes": "Dangerous for infants transdermally"}
        ],
        "unknowns": [],
        "clean": ["water", "carbomer"],
    }
    result = format_scan_result(scan, web_results=[])
    assert "🔴" in result
    assert "Camphor" in result
    assert "HIGH RISK" in result.upper() or "high risk" in result.lower()


def test_format_with_web_results():
    scan = {
        "product_name": None,
        "total_ingredients": 2,
        "matches": [],
        "unknowns": ["lactobacillus rhamnosus"],
        "clean": ["inulin"],
    }
    web_results = [
        {"ingredient": "lactobacillus rhamnosus", "risk_assessment": "No known G6PD risk.", "source": "web"}
    ]
    result = format_scan_result(scan, web_results=web_results)
    assert "🌐" in result
    assert "lactobacillus rhamnosus" in result.lower()


def test_format_error_no_ingredients():
    scan = {"error": "no_ingredients_visible"}
    result = format_scan_result(scan, web_results=[])
    assert "couldn't read" in result.lower() or "no ingredient" in result.lower()


def test_format_error_not_product_label():
    scan = {"error": "not_a_product_label"}
    result = format_scan_result(scan, web_results=[])
    assert "product label" in result.lower()


def test_disclaimer_always_present():
    scan = {"product_name": "X", "total_ingredients": 0,
            "matches": [], "unknowns": [], "clean": []}
    result = format_scan_result(scan, web_results=[])
    assert "doctor" in result.lower() or "pharmacist" in result.lower()
