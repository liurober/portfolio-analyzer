import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from checker import load_db, lookup, normalize

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "g6pd_triggers.json")


def test_load_db_returns_dict():
    db = load_db(DB_PATH)
    assert isinstance(db, dict)
    assert "drugs" in db
    assert "foods" in db
    assert "cosmetics" in db


def test_normalize_lowercases_and_strips():
    assert normalize("  Primaquine  ") == "primaquine"
    assert normalize("Fava-Beans") == "fava beans"
    assert normalize("E220") == "e220"


def test_lookup_exact_match():
    db = load_db(DB_PATH)
    result = lookup("primaquine", db)
    assert result is not None
    assert result["risk"] == "high"
    assert result["category"] == "drugs"


def test_lookup_case_insensitive():
    db = load_db(DB_PATH)
    result = lookup("DAPSONE", db)
    assert result is not None
    assert result["risk"] == "high"


def test_lookup_alias_match():
    db = load_db(DB_PATH)
    # "bactrim" is an alias for trimethoprim sulfamethoxazole
    result = lookup("Bactrim", db)
    assert result is not None
    assert result["risk"] == "high"


def test_lookup_alias_trade_name():
    db = load_db(DB_PATH)
    # "tylenol" is an alias for paracetamol
    result = lookup("Tylenol", db)
    assert result is not None
    assert result["risk"] == "medium"


def test_lookup_unknown_returns_none():
    db = load_db(DB_PATH)
    result = lookup("glycerin", db)
    assert result is None


def test_lookup_food_trigger():
    db = load_db(DB_PATH)
    result = lookup("broad beans", db)
    assert result is not None
    assert result["risk"] == "high"
    assert result["category"] == "foods"


def test_lookup_cosmetic_trigger():
    db = load_db(DB_PATH)
    result = lookup("camphor", db)
    assert result is not None
    assert result["category"] == "cosmetics"


def test_lookup_e_number():
    db = load_db(DB_PATH)
    result = lookup("E220", db)
    assert result is not None
    assert result["category"] == "food_additives"
