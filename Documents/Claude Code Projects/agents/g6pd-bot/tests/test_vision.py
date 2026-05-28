import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vision import build_system_prompt, parse_response, scan_photo


def test_build_system_prompt_contains_database():
    db_str = json.dumps({"drugs": {"primaquine": {"risk": "high", "notes": "test", "aliases": []}}})
    prompt = build_system_prompt(db_str)
    assert "primaquine" in prompt
    assert "JSON" in prompt
    assert "matches" in prompt


def test_parse_response_valid_json():
    raw = '{"product_name": "Test Cream", "total_ingredients": 3, "matches": [], "unknowns": [], "clean": ["water"]}'
    result = parse_response(raw)
    assert result["product_name"] == "Test Cream"
    assert result["total_ingredients"] == 3


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"product_name": null, "total_ingredients": 0, "matches": [], "unknowns": [], "clean": []}\n```'
    result = parse_response(raw)
    assert result["product_name"] is None


def test_parse_response_error_key():
    raw = '{"error": "no_ingredients_visible"}'
    result = parse_response(raw)
    assert "error" in result


def test_parse_response_invalid_json_raises():
    with pytest.raises(ValueError, match="Could not parse Claude response"):
        parse_response("This is not JSON at all")


@patch("vision.anthropic.Anthropic")
def test_scan_photo_calls_api(mock_anthropic_class):
    """Verify scan_photo calls the Anthropic client with correct structure."""
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    expected_json = '{"product_name": "Baby cream", "total_ingredients": 5, "matches": [{"ingredient": "camphor", "matched_as": "camphor", "category": "cosmetics", "risk": "high", "notes": "Dangerous for infants"}], "unknowns": ["glycerin"], "clean": ["water", "zinc oxide"]}'
    mock_client.messages.create.return_value.content = [MagicMock(text=expected_json)]

    result = scan_photo(
        image_bytes=b"fake_image_data",
        media_type="image/jpeg",
        db_str='{"drugs": {}}',
        api_key="test-key"
    )

    assert mock_client.messages.create.called
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-5"
    assert result["product_name"] == "Baby cream"
    assert result["matches"][0]["ingredient"] == "camphor"
    assert result["unknowns"] == ["glycerin"]
