"""Default policy and application settings for report reliability."""

from pathlib import Path

APP_VERSION = "1.0.0"

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "report_jobs.json"

REQUIRED_JOB_COLUMNS = (
    "job_id",
    "run_id",
    "tenant_id",
    "tenant_name",
    "report_name",
    "scheduled_at",
    "status",
    "attempt_number",
    "duration_seconds",
    "row_count",
)

SUCCESS_STATUSES = frozenset({"completed"})
FAILURE_STATUSES = frozenset({"failed", "error", "timed_out"})
RETRYABLE_STATUSES = frozenset({"timed_out"})
MAX_TOTAL_ATTEMPTS = 3

OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_FAILED = "failed"
OUTCOME_UNKNOWN = "unknown"

RETRY_NOT_NEEDED = "not_needed"
RETRY_CANDIDATE = "retry_candidate"
RETRY_EXHAUSTED = "retry_exhausted"
RETRY_MANUAL_REVIEW = "manual_review"
RETRY_PLANNED_STATUS = "retry_planned"

EMAIL_ENABLED = False
SMTP_HOST = "smtp.example.com"
SMTP_PORT = 587
SMTP_SENDER = "reports@example.com"
DEFAULT_ESCALATION_RECIPIENT = "ops@example.com"
SMTP_USERNAME_ENV_VAR = "REPORTS_SMTP_USERNAME"
SMTP_PASSWORD_ENV_VAR = "REPORTS_SMTP_PASSWORD"
ESCALATION_RECIPIENT_ENV_VAR = "REPORTS_ESCALATION_RECIPIENT"
