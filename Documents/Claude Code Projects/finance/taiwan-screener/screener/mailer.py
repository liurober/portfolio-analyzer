"""Gmail SMTP sender with inline CID image attachments.

Reads credentials from env:
  GMAIL_USER         - sender address
  GMAIL_APP_PASSWORD - 16-char Google app password
  EMAIL_TO           - comma-separated recipient list
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 465


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(HERE)),
        autoescape=select_autoescape(["html"]),
    )


def render_weekly_email(picks: list[dict], universe_count: int,
                        date_zh: str, params_version: str) -> tuple[str, list[tuple[str, bytes]]]:
    """Render the email HTML and return (html, [(cid, png_bytes), ...]).

    Each pick dict must include `chart_png` (bytes). This function assigns a
    fresh CID, mutates pick["chart_cid"] in place, and returns the attachments.
    """
    env = _jinja_env()
    tpl = env.get_template("email_template_tw.html")
    attachments: list[tuple[str, bytes]] = []
    for pick in picks:
        cid = make_msgid(domain="tw-screener.local")[1:-1]  # strip <>
        pick["chart_cid"] = cid
        attachments.append((cid, pick.pop("chart_png")))
    html = tpl.render(picks=picks, universe_count=universe_count,
                      date_zh=date_zh, pick_count=len(picks),
                      params_version=params_version)
    return html, attachments


def send_email(subject: str, html: str,
               attachments: Sequence[tuple[str, bytes]],
               to_addrs: Sequence[str] | None = None,
               dry_run: bool = False) -> int:
    user = os.environ.get("GMAIL_USER", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    recipients = list(to_addrs) if to_addrs else \
        [a.strip() for a in os.environ.get("EMAIL_TO", "").split(",") if a.strip()]

    if not recipients:
        raise RuntimeError("EMAIL_TO is empty")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user or "no-reply@local"
    msg["To"] = ", ".join(recipients)
    msg.set_content("此郵件需要支援 HTML 的郵件客戶端才能正確顯示。")
    msg.add_alternative(html, subtype="html")

    html_part = msg.get_payload()[1]
    for cid, png in attachments:
        html_part.add_related(png, maintype="image", subtype="png", cid=f"<{cid}>")

    size = len(msg.as_bytes())
    if size > 102_000:
        raise RuntimeError(f"Email payload {size} bytes exceeds 102KB Gmail cap")

    if dry_run:
        return size

    with smtplib.SMTP_SSL(GMAIL_HOST, GMAIL_PORT) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    return size
