"""
report.py — Generate HTML portfolio analysis report using Jinja2.

Public API:
    generate_report(holdings, macro, metrics, picks, analysis, output_path, mode="analyze") -> str
"""
from __future__ import annotations

import webbrowser
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent / "templates"


def generate_report(
    holdings: dict,
    macro: dict,
    metrics: dict,
    picks: dict,
    analysis: dict,
    output_path: str,
    mode: str = "analyze",
) -> str:
    """
    Render the HTML report and write it to output_path.

    Args:
        holdings:    Holdings dict (positions, total_value, data_completeness)
        macro:       Macro context dict (regime, recommended_plan, etc.)
        metrics:     Metrics dict (concentration, risk, return_quality, etc.)
        picks:       Dict of {plan_type: [pick, ...]} for all 4 plan types
        analysis:    Claude analysis dict (implicit_bet, red_flags, green_flags, grades, plans)
        output_path: Where to write the HTML file
        mode:        "analyze" | "build"

    Returns:
        The absolute path of the written HTML file.
    """
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    template = env.get_template("report.html")

    html = template.render(
        holdings=holdings,
        macro=macro,
        metrics=metrics,
        picks=picks,
        analysis=analysis,
        mode=mode,
        recommended_plan=macro.get("recommended_plan", "balanced"),
    )

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    webbrowser.open_new(out.as_uri())

    return str(out)
