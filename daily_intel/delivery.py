"""Delivery: send briefs via Gmail, Slack webhook, or Substack."""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from daily_intel.config import Config

logger = logging.getLogger("daily_intel")


def deliver(config: Config, brief: dict) -> dict[str, bool]:
    """Deliver a brief using all configured channels.

    Returns dict of {channel: success} results.
    """
    results = {}
    method = config.delivery.method

    if method in ("gmail", "all"):
        results["gmail"] = _send_gmail(config, brief)

    if method in ("slack", "all"):
        results["slack"] = _send_slack(config, brief)

    if method in ("substack", "all"):
        results["substack"] = _send_substack(config, brief)

    return results


def _send_gmail(config: Config, brief: dict) -> bool:
    """Send HTML brief via Gmail SMTP.

    Requires GMAIL_APP_PASSWORD env var (Google App Password, not regular password).
    """
    import os

    address = config.delivery.gmail_address
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not address or not app_password:
        logger.warning("Gmail delivery skipped: missing address or GMAIL_APP_PASSWORD")
        return False

    headline = brief.get("metadata", {}).get("editorial_headline", "Intelligence Brief")
    signal_count = brief.get("metadata", {}).get("signal_count", 0)
    subject = f"Daily Intel: {headline} ({signal_count} signals)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = address
    msg["To"] = address  # Sending to self

    # Plain text fallback
    msg.attach(MIMEText(brief.get("markdown", "No brief content"), "plain"))

    # HTML version
    if brief.get("html"):
        msg.attach(MIMEText(brief["html"], "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(address, app_password)
            server.send_message(msg)
        logger.info(f"Gmail brief sent to {address}")
        return True
    except Exception as e:
        logger.error(f"Gmail delivery failed: {e}")
        return False


def _send_slack(config: Config, brief: dict) -> bool:
    """Send brief to Slack via incoming webhook."""
    webhook_url = config.delivery.slack_webhook_url

    if not webhook_url:
        logger.warning("Slack delivery skipped: no webhook URL configured")
        return False

    payload = brief.get("slack_blocks", {})
    if not payload:
        # Fallback to simple text
        headline = brief.get("metadata", {}).get("editorial_headline", "Brief")
        payload = {"text": f"*{headline}*\n\n{brief.get('markdown', '')[:3000]}"}

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if response.status_code == 200:
            logger.info("Slack brief delivered")
            return True
        else:
            logger.error(f"Slack delivery failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Slack delivery failed: {e}")
        return False


def _send_substack(config: Config, brief: dict) -> bool:
    """Create a draft post on Substack via API.

    Note: Substack's API is limited. This creates a draft that
    you publish manually or via their scheduled publishing.
    """
    api_key = config.delivery.substack_api_key
    pub_id = config.delivery.substack_publication_id

    if not api_key or not pub_id:
        logger.warning("Substack delivery skipped: missing API key or publication ID")
        return False

    headline = brief.get("metadata", {}).get("editorial_headline", "Intelligence Brief")

    try:
        response = requests.post(
            f"https://substack.com/api/v1/post",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "publication_id": pub_id,
                "title": headline,
                "body_html": brief.get("html", brief.get("markdown", "")),
                "draft": True,
                "type": "newsletter",
            },
            timeout=30,
        )
        if response.status_code in (200, 201):
            logger.info("Substack draft created")
            return True
        else:
            logger.error(f"Substack delivery failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Substack delivery failed: {e}")
        return False
