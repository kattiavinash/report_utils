from dataclasses import dataclass

import pandas as pd

from constants import FAILURE_STATUSES, MAX_TOTAL_ATTEMPTS, RETRYABLE_STATUSES


@dataclass(frozen=True)
class RetryPolicy:
    """Define which outcomes are retryable and the total-attempt ceiling."""

    max_total_attempts: int = MAX_TOTAL_ATTEMPTS
    retryable_statuses: frozenset[str] = RETRYABLE_STATUSES

    def __post_init__(self) -> None:
        """Reject invalid policies before they can create retry plans."""
        if self.max_total_attempts < 1:
            raise ValueError("max_total_attempts must be at least 1")
        if not self.retryable_statuses.issubset(FAILURE_STATUSES):
            raise ValueError("retryable statuses must be recognized failures")


@dataclass(frozen=True)
class ReportAnalysis:
    """Hold the input-attempt audit and derived run-level decision tables."""

    attempts: pd.DataFrame
    runs: pd.DataFrame
    retry_plan: pd.DataFrame
    escalations: pd.DataFrame
