from typing import Any

import pandas as pd

from constants import (
    FAILURE_STATUSES,
    OUTCOME_FAILED,
    OUTCOME_SUCCEEDED,
    OUTCOME_UNKNOWN,
    RETRY_CANDIDATE,
    RETRY_EXHAUSTED,
    RETRY_MANUAL_REVIEW,
    RETRY_NOT_NEEDED,
    RETRY_PLANNED_STATUS,
    SUCCESS_STATUSES,
)
from model import RetryPolicy


class Utils:
    """Utility methods used to analyze jobs"""

    def __init__(self) -> None:
        """Initializer without any variable and is not required."""

    def classify_attempts(self, attempts: pd.DataFrame) -> pd.DataFrame:
        """Add normalized status and outcome columns without changing input rows.

        Recognized success/failure values are mapped explicitly. Any unrecognized
        or missing status is marked unknown so it can be surfaced for review.
        """
        classified = attempts.copy()
        normalized_status = (
            classified["status"].astype("string").str.strip().str.lower().fillna("")
        )
        classified["normalized_status"] = normalized_status
        classified["attempt_outcome"] = "unknown"
        classified.loc[normalized_status.isin(SUCCESS_STATUSES), "attempt_outcome"] = (
            OUTCOME_SUCCEEDED
        )
        classified.loc[normalized_status.isin(FAILURE_STATUSES), "attempt_outcome"] = (
            OUTCOME_FAILED
        )
        classified.loc[normalized_status.eq(""), "normalized_status"] = "unknown"
        return classified

    def _build_run_summary(self, attempts: pd.DataFrame) -> pd.DataFrame:
        """Reduce attempt rows to one outcome record for each logical run."""
        run_records: list[dict[str, Any]] = []

        for run_id, run_attempts in attempts.groupby(
            "run_id", sort=False, dropna=False
        ):
            ordered = run_attempts.sort_values("attempt_number", kind="stable")
            latest = ordered.iloc[-1]
            has_success = ordered["normalized_status"].isin(SUCCESS_STATUSES).any()

            if has_success:
                outcome = OUTCOME_SUCCEEDED
                failure_reason = ""
            elif latest["normalized_status"] in FAILURE_STATUSES:
                outcome = OUTCOME_FAILED
                failure_reason = str(latest["normalized_status"])
            else:
                outcome = OUTCOME_UNKNOWN
                failure_reason = str(latest["normalized_status"])

            first = ordered.iloc[0]
            run_records.append(
                {
                    "run_id": run_id,
                    "tenant_id": first["tenant_id"],
                    "tenant_name": first["tenant_name"],
                    "report_name": first["report_name"],
                    "scheduled_at": first["scheduled_at"],
                    "attempt_count": len(ordered),
                    "latest_attempt_number": latest["attempt_number"],
                    "latest_status": latest["normalized_status"],
                    "run_outcome": outcome,
                    "failure_reason": failure_reason,
                }
            )

        return pd.DataFrame(
            run_records,
            columns=[
                "run_id",
                "tenant_id",
                "tenant_name",
                "report_name",
                "scheduled_at",
                "attempt_count",
                "latest_attempt_number",
                "latest_status",
                "run_outcome",
                "failure_reason",
            ],
        )

    def _retry_reason(
        self, disposition: str, latest_status: str, policy: RetryPolicy
    ) -> str:
        """Return a human-readable explanation for a retry decision."""
        if disposition == RETRY_NOT_NEEDED:
            return "A completed attempt exists for this run."
        if disposition == RETRY_CANDIDATE:
            return "Latest attempt timed out and is below the total-attempt limit."
        if disposition == RETRY_EXHAUSTED:
            return f"Retry limit reached ({policy.max_total_attempts} total attempts)."
        if latest_status in FAILURE_STATUSES:
            return f"Status '{latest_status}' is not enabled for automatic retry."
        return f"Unrecognized status '{latest_status}' requires manual review."

    def _build_retry_plan(
        self, runs: pd.DataFrame, policy: RetryPolicy
    ) -> pd.DataFrame:
        """Build a transparent retry decision for each logical report run.

        A retry plan is a proposal only. It never fabricates a job result or calls
        a runner; the ``retry_planned`` status denotes an unexecuted next attempt.
        """
        decisions: list[dict[str, Any]] = []

        for run in runs.to_dict(orient="records"):
            latest_status = str(run["latest_status"])
            latest_attempt = int(run["latest_attempt_number"])

            if run["run_outcome"] == OUTCOME_SUCCEEDED:
                disposition = RETRY_NOT_NEEDED
                proposed_attempt: int | None = None
            elif latest_status not in policy.retryable_statuses:
                disposition = RETRY_MANUAL_REVIEW
                proposed_attempt = None
            elif latest_attempt >= policy.max_total_attempts:
                disposition = RETRY_EXHAUSTED
                proposed_attempt = None
            else:
                disposition = RETRY_CANDIDATE
                proposed_attempt = latest_attempt + 1

            decisions.append(
                {
                    "run_id": run["run_id"],
                    "tenant_name": run["tenant_name"],
                    "report_name": run["report_name"],
                    "run_outcome": run["run_outcome"],
                    "latest_status": latest_status,
                    "latest_attempt_number": latest_attempt,
                    "retry_disposition": disposition,
                    "proposed_attempt_number": proposed_attempt,
                    "proposed_status": (
                        RETRY_PLANNED_STATUS if proposed_attempt is not None else ""
                    ),
                    "is_simulated": proposed_attempt is not None,
                    "reason": self._retry_reason(disposition, latest_status, policy),
                }
            )

        return pd.DataFrame(
            decisions,
            columns=[
                "run_id",
                "tenant_name",
                "report_name",
                "run_outcome",
                "latest_status",
                "latest_attempt_number",
                "retry_disposition",
                "proposed_attempt_number",
                "proposed_status",
                "is_simulated",
                "reason",
            ],
        )
