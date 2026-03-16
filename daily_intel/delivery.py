"""Delivery: send briefs via Gmail/SMTP, Slack webhook, or Beehiiv API."""

from __future__ import annotations

import logging
import os
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
    """Deliver a brief using the configured channel.

    Returns dict of {channel: success} results.
    """
    results = {}
    method = config.delivery.method

    if method in ("gmail", "all"):
        results["gmail"] = _send_gmail(config, brief)

    if method in ("slack", "all"):
        results["slack"] = _send_slack(config, brief)

    if method in ("beehiiv", "all"):
        results["beehiiv"] = _send_beehiiv(config, brief)

    return results


def _send_gmail(config: Config, brief: dict) -> bool:
    """Send HTML brief via SMTP.

    Supports Gmail (default) or any SMTP server via smtp_host/smtp_port config.
    Requires GMAIL_APP_PASSWORD env var (or SMTP_PASSWORD for non-Gmail).
    """
    address = config.delivery.gmail_address
    app_password = os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("SMTP_PASSWORD", "")

    if not address or not app_password:
        logger.warning("Email delivery skipped: missing address or GMAIL_APP_PASSWORD/SMTP_PASSWORD")
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
        host = config.delivery.smtp_host
        port = config.delivery.smtp_port
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            server.login(address, app_password)
            server.send_message(msg)
        logger.info(f"Email brief sent to {address}")
        return True
    except Exception as e:
        logger.error(f"Email delivery failed: {e}")
        return False


def _send_slack(config: Config, brief: dict) -> bool:
    """Send brief to Slack via incoming webhook."""
    webhook_url = config.delivery.slack_webhook_url

    if not webhook_url:
        logger.warning("Slack delivery skipped: no webhook URL configured")
        return False

    payload = brief.get("slack_blocks", {})
    if not payload:
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


def _send_beehiiv(config: Config, brief: dict) -> bool:
    """Create a draft post on Beehiiv via their API.

    Creates a draft that appears in the Beehiiv dashboard for review
    and publishing. Does NOT auto-publish.
    """
    api_key = config.delivery.beehiiv_api_key
    pub_id = config.delivery.beehiiv_publication_id

    if not api_key or not pub_id:
        logger.warning("Beehiiv delivery skipped: missing API key or publication ID")
        return False

    headline = brief.get("metadata", {}).get("editorial_headline", "Intelligence Brief")
    html_content = brief.get("html", brief.get("markdown", ""))

    try:
        response = requests.post(
            f"https://api.beehiiv.com/v2/publications/{pub_id}/posts",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "title": headline,
                "subtitle": f"Daily Intel: {config.niche}",
                "status": "draft",
                "content_html": html_content,
            },
            timeout=30,
        )
        if response.status_code in (200, 201):
            post_data = response.json()
            post_id = post_data.get("data", {}).get("id", "unknown")
            logger.info(f"Beehiiv draft created: {post_id}")
            return True
        else:
            logger.error(f"Beehiiv delivery failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Beehiiv delivery failed: {e}")
        return False
