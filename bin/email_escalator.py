import logging
import os
import smtplib
from email.message import EmailMessage

import pandas as pd

from constants import (
    DEFAULT_ESCALATION_RECIPIENT,
    EMAIL_ENABLED,
    ESCALATION_RECIPIENT_ENV_VAR,
    SMTP_HOST,
    SMTP_PASSWORD_ENV_VAR,
    SMTP_PORT,
    SMTP_SENDER,
    SMTP_USERNAME_ENV_VAR,
)

LOGGER = logging.getLogger(__name__)


class EmailEscalator:
    """Send unresolved-run escalations, or log them in safe dry-run mode."""

    def __init__(
        self,
        enabled: bool = EMAIL_ENABLED,
        smtp_host: str = SMTP_HOST,
        smtp_port: int = SMTP_PORT,
    ) -> None:
        """Configure email transport; sending is disabled unless explicitly enabled."""
        self.enabled = enabled
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    def send_escalation_email(self, escalations: pd.DataFrame) -> str:
        """Notify the configured operator about unresolved report runs.

        Returns ``not_needed`` for an empty escalation set, ``dry_run`` when
        sending is disabled, or ``sent`` after SMTP accepts the message.
        SMTP and configuration errors are deliberately allowed to surface.
        """
        if escalations.empty:
            return "not_needed"

        recipient = os.getenv(
            ESCALATION_RECIPIENT_ENV_VAR,
            DEFAULT_ESCALATION_RECIPIENT,
        )
        message = self._build_message(escalations, recipient)

        if not self.enabled:
            LOGGER.info(
                "Email dry run: would send escalation for %d report run(s) to %s",
                len(escalations),
                recipient,
            )
            LOGGER.info("Email subject: %s", message["Subject"])
            return "dry_run"

        username = os.getenv(SMTP_USERNAME_ENV_VAR)
        password = os.getenv(SMTP_PASSWORD_ENV_VAR)
        if not username or not password:
            raise ValueError(
                "SMTP is enabled but credentials are missing from the configured "
                "environment variables"
            )

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
        return "sent"

    @staticmethod
    def _build_message(escalations: pd.DataFrame, recipient: str) -> EmailMessage:
        """Format run identifiers, tenant names, and reasons into an email."""
        lines = [
            "The following report runs need operator attention:",
            "",
        ]
        for escalation in escalations.to_dict(orient="records"):
            lines.append(
                "- "
                f"{escalation['run_id']} ({escalation['tenant_name']}): "
                f"{escalation['latest_status']} after attempt "
                f"{escalation['latest_attempt_number']} "
                f"[{escalation['action']}] - {escalation['reason']}"
            )

        message = EmailMessage()
        message["Subject"] = "Report delivery reliability escalation"
        message["From"] = SMTP_SENDER
        message["To"] = recipient
        message.set_content("\n".join(lines))
        return message
