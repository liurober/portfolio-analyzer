import pytest
import sys
import os
from unittest.mock import MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from web_search import search_ingredient, search_unknowns


@patch("web_search.anthropic.Anthropic")
def test_search_ingredient_safe_result(mock_anthropic_class):
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(type="text", text="Glycerin is a safe humectant with no known G6PD hemolytic risk.")
    ]
    mock_client.messages.create.return_value = mock_response

    result = search_ingredient("glycerin", api_key="test-key")

    assert result["ingredient"] == "glycerin"
    assert result["source"] == "web"
    assert "risk_assessment" in result
    assert result["risk_assessment"] is not None


@patch("web_search.anthropic.Anthropic")
def test_search_unknowns_respects_max_limit(mock_anthropic_class):
    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="No known G6PD risk.")]
    mock_client.messages.create.return_value = mock_response

    unknowns = ["a", "b", "c", "d", "e", "f", "g"]  # 7 items
    results = search_unknowns(unknowns, api_key="test-key", max_results=5)

    assert len(results) == 5  # capped at max_results
    assert mock_client.messages.create.call_count == 5


def test_search_unknowns_empty_list():
    results = search_unknowns([], api_key="test-key")
    assert results == []
