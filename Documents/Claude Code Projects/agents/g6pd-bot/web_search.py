import anthropic


_SEARCH_PROMPT = """\
Is "{ingredient}" a known trigger for G6PD deficiency (glucose-6-phosphate dehydrogenase deficiency)?
Could it cause hemolysis in a G6PD-deficient person?

Search for the most current medical information and answer concisely:
1. Is there any known G6PD hemolytic risk? (yes / no / uncertain)
2. What is the risk level if any? (high / medium / low / none)
3. Source or basis for your answer

Keep your answer under 100 words.
"""


def search_ingredient(ingredient: str, api_key: str) -> dict:
    """
    Use Claude with web_search tool to check a single unknown ingredient.
    Returns dict: {ingredient, risk_assessment, source}
    """
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[
            {
                "role": "user",
                "content": _SEARCH_PROMPT.format(ingredient=ingredient),
            }
        ],
    )

    # Extract the final text response (after any tool use)
    risk_text = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            risk_text = block.text
            break

    return {
        "ingredient": ingredient,
        "risk_assessment": risk_text.strip() if risk_text else "No information found.",
        "source": "web",
    }


def search_unknowns(
    unknowns: list[str],
    api_key: str,
    max_results: int = 5,
) -> list[dict]:
    """
    Run web search for each unknown ingredient up to max_results.
    Returns list of {ingredient, risk_assessment, source} dicts.
    """
    if not unknowns:
        return []

    results = []
    for ingredient in unknowns[:max_results]:
        result = search_ingredient(ingredient, api_key=api_key)
        results.append(result)

    return results
