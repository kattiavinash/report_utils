"""Default policy and application settings for report reliability."""

from pathlib import Path

APP_VERSION = "1.0.0"

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "report_jobs.json"
DEFAULT_RETRY_LOG_PATH = PROJECT_ROOT / "data" / "retry_logs.json"
OUTPUT_DIR: Path | None = None
RUN_RETRIES = True
RETRY_SEED: int | None = None

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

SUCCESS_STATUS = "completed"
MANUAL_REVIEW_STATUSES = frozenset({"failed", "error"})
RETRY_STATUS = "timed_out"
MAX_TOTAL_ATTEMPTS = 3

ACTION_SUCCESS = "success"
ACTION_MANUAL_REVIEW = "manual_review"
ACTION_RETRY = "retry"
ACTION_ESCALATE = "escalate"

EMAIL_ENABLED = False
SMTP_HOST = "smtp.example.com"
SMTP_PORT = 587
SMTP_SENDER = "reports@example.com"
DEFAULT_ESCALATION_RECIPIENT = "ops@example.com"
SMTP_USERNAME_ENV_VAR = "REPORTS_SMTP_USERNAME"
SMTP_PASSWORD_ENV_VAR = "REPORTS_SMTP_PASSWORD"
ESCALATION_RECIPIENT_ENV_VAR = "REPORTS_ESCALATION_RECIPIENT"

# GitHub Models access is opt-in. The token value itself must only be supplied
# through the environment and must never be committed to this file.
GITHUB_MODELS_ENABLED_ENV_VAR = "GITHUB_MODELS_INFERENCE_ENABLED"
GITHUB_MODELS_TOKEN_ENV_VAR = "GITHUB_TOKEN"
GITHUB_MODELS_MODEL_ENV_VAR = "GITHUB_MODELS_MODEL"
GITHUB_MODELS_MODEL = "openai/gpt-4.1-mini"
GITHUB_MODELS_CHAT_COMPLETIONS_URL = (
    "https://models.github.ai/inference/chat/completions"
)
GITHUB_MODELS_TIMEOUT_SECONDS = 30
GITHUB_MODELS_MAX_CASES_PER_REQUEST = 20
GITHUB_MODELS_MAX_LOG_CHARACTERS = 1200
API_HOST = "127.0.0.1"
API_PORT = 8000
API_MAX_REQUEST_BYTES = 4096

DUMMY_RETRY_STATUSES = ("completed", "failed", "timed_out", "error")
DUMMY_RETRY_LOGS = {
    "completed": "Report generated successfully by the dummy retry processor.",
    "failed": "Dependency returned an error while preparing report data.",
    "timed_out": "Report generation exceeded the configured execution window.",
    "error": "Worker ran out of available memory while rendering the report.",
}
RETRY_LOGS_COLLECTION_KEY = "logs"
ROOT_CAUSE_RESULTS_COLLECTION_KEY = "findings"
