"""Summarize report runs and apply the configured retry rules."""

import pandas as pd

import constants
from model import ReportAnalysis


class ReportJobAnalyzer:
    """Apply success, manual-review, retry, and exhaustion rules per run."""

    def __init__(self, max_attempts: int = constants.MAX_TOTAL_ATTEMPTS) -> None:
        """Set the maximum number of total attempts, including the original."""
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.max_attempts = max_attempts

    def analyze(self, attempts: pd.DataFrame) -> ReportAnalysis:
        """Create one concise status/action row for each logical run."""
        records = []
        for run_id, group in attempts.groupby("run_id", sort=False, dropna=False):
            ordered = group.sort_values("attempt_number", kind="stable")
            latest = ordered.iloc[-1]
            latest_status = str(latest["status"]).strip().lower()
            attempt_count = len(ordered)
            has_completed = (
                ordered["status"].astype("string").str.strip().str.lower()
                == constants.SUCCESS_STATUS
            ).any()

            if has_completed:
                action = constants.ACTION_SUCCESS
                reason = "A completed attempt exists."
            elif latest_status in constants.MANUAL_REVIEW_STATUSES:
                action = constants.ACTION_MANUAL_REVIEW
                reason = "This failure status requires manual review."
            elif latest_status == constants.RETRY_STATUS:
                if attempt_count < self.max_attempts:
                    action = constants.ACTION_RETRY
                    reason = "Timed out below the maximum attempt count."
                else:
                    action = constants.ACTION_ESCALATE
                    reason = "Maximum attempts exhausted."
            else:
                action = constants.ACTION_MANUAL_REVIEW
                reason = f"Unrecognized status '{latest_status}' requires review."

            first = ordered.iloc[0]
            records.append(
                {
                    "run_id": run_id,
                    "tenant_id": first["tenant_id"],
                    "tenant_name": first["tenant_name"],
                    "report_name": first["report_name"],
                    "latest_job_id": latest["job_id"],
                    "attempt_count": attempt_count,
                    "latest_attempt_number": int(latest["attempt_number"]),
                    "latest_status": latest_status,
                    "action": action,
                    "reason": reason,
                }
            )

        columns = [
            "run_id",
            "tenant_id",
            "tenant_name",
            "report_name",
            "latest_job_id",
            "attempt_count",
            "latest_attempt_number",
            "latest_status",
            "action",
            "reason",
        ]
        runs = pd.DataFrame(records, columns=columns)
        return ReportAnalysis(attempts=attempts.copy(), runs=runs)
