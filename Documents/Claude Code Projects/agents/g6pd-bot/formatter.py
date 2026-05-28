RISK_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}
CATEGORY_EMOJI = {
    "drugs": "💊",
    "foods": "🥦",
    "food_additives": "🧪",
    "cosmetics": "💄",
    "herbals": "🌿",
    "chemicals": "☣️",
}
RISK_LABEL = {
    "high": "HIGH RISK — DO NOT USE",
    "medium": "MEDIUM RISK — Consult doctor",
    "low": "LOW RISK — Use caution",
}
DISCLAIMER = "\n⚠️ Reference tool only — always confirm with a doctor or pharmacist before use."


def format_scan_result(scan: dict, web_results: list[dict]) -> str:
    """Format scan result dict into a Telegram message string."""

    # Handle error responses
    if "error" in scan:
        error = scan["error"]
        if error == "no_ingredients_visible":
            return "⚠️ I couldn't read the ingredients clearly. Try a clearer, closer photo of the ingredients list."
        if error == "not_a_product_label":
            return "⚠️ This doesn't look like a product label. Please send a close-up photo of an ingredient list."
        return f"⚠️ Scan error: {error}. Please try again."

    product = scan.get("product_name") or "product"
    total = scan.get("total_ingredients", 0)
    matches = scan.get("matches", [])

    lines = [f"🔍 Scanned: *{product}* ({total} ingredient{'s' if total != 1 else ''})\n"]

    if not matches and not web_results:
        lines.append("✅ All clear — no G6PD triggers found.")
        lines.append(DISCLAIMER)
        return "\n".join(lines)

    # Group matches by risk level
    for risk_level in ["high", "medium", "low"]:
        level_matches = [m for m in matches if m.get("risk") == risk_level]
        if not level_matches:
            continue
        emoji = RISK_EMOJI[risk_level]
        label = RISK_LABEL[risk_level]
        lines.append(f"\n{emoji} *{label}*")
        for m in level_matches:
            cat_emoji = CATEGORY_EMOJI.get(m.get("category", ""), "•")
            lines.append(f"  {cat_emoji} {m['ingredient']}")
            if m.get("notes"):
                lines.append(f"     ↳ _{m['notes']}_")

    # Clean count
    clean_count = len(scan.get("clean", []))
    if clean_count > 0:
        lines.append(f"\n✅ {clean_count} other ingredient{'s' if clean_count != 1 else ''}: no triggers found")

    # Web search results
    if web_results:
        lines.append("\n🌐 *Web-searched (not in local database):*")
        for r in web_results:
            lines.append(f"  • *{r['ingredient']}* — {r['risk_assessment']}")

    # Unsearched unknowns
    unknowns = scan.get("unknowns", [])
    searched_names = {r["ingredient"] for r in web_results}
    unsearched = [u for u in unknowns if u not in searched_names]
    if unsearched:
        lines.append(f"\n⚠️ {len(unsearched)} ingredient(s) not checked — verify manually: {', '.join(unsearched)}")

    lines.append(DISCLAIMER)
    return "\n".join(lines)
