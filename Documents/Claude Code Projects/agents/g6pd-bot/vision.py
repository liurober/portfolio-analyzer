import anthropic
import base64
import json
import re


SYSTEM_PROMPT_TEMPLATE = """\
You are a G6PD deficiency safety scanner for a baby's parent.

Your job:
1. Extract ALL ingredients, E-numbers, active ingredients, inactive ingredients, \
and any chemical or food components visible in the product label photo.
2. Cross-check every extracted item against the G6PD TRIGGER DATABASE below.
3. Return ONLY a valid JSON object — no markdown, no commentary.

Return this exact JSON structure:
{{
  "product_name": "string or null if not visible",
  "total_ingredients": <number of ingredients you extracted>,
  "matches": [
    {{
      "ingredient": "<exact text from label>",
      "matched_as": "<canonical name in database>",
      "category": "drugs|foods|food_additives|cosmetics|herbals|chemicals",
      "risk": "high|medium|low",
      "notes": "<string>"
    }}
  ],
  "unknowns": ["<ingredient not in database and you are unsure about>"],
  "clean": ["<ingredient you are confident is safe>"]
}}

Rules:
- unknowns: ingredients not in the database AND you are not confident about G6PD safety
- clean: water, salt, and ingredients you are confident are G6PD-safe
- If no ingredients are visible, return: {{"error": "no_ingredients_visible"}}
- If the image is not a product label, return: {{"error": "not_a_product_label"}}
- Do not include markdown fences or any text outside the JSON object

G6PD TRIGGER DATABASE:
{db_str}
"""


def build_system_prompt(db_str: str) -> str:
    """Inject the trigger database into the system prompt."""
    return SYSTEM_PROMPT_TEMPLATE.format(db_str=db_str)


def parse_response(raw: str) -> dict:
    """
    Parse Claude's response into a dict.
    Strips markdown fences if present.
    Raises ValueError if not valid JSON.
    """
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse Claude response: {e}\nRaw: {raw[:200]}")


def scan_photo(
    image_bytes: bytes,
    media_type: str,
    db_str: str,
    api_key: str,
) -> dict:
    """
    Send product label photo to Claude Vision.
    Returns parsed scan result dict.
    """
    client = anthropic.Anthropic(api_key=api_key)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": build_system_prompt(db_str),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Scan this product label for G6PD triggers. Return the JSON response as instructed.",
                    },
                ],
            }
        ],
    )

    return parse_response(response.content[0].text)
