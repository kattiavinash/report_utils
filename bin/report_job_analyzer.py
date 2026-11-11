import pandas as pd

from bin.utils import Utils
from constants import RETRY_EXHAUSTED, RETRY_MANUAL_REVIEW
from model import ReportAnalysis, RetryPolicy


class ReportJobAnalyzer:
    """Analyze job history and derive run, retry, and escalation views."""

    def __init__(self, retry_policy: RetryPolicy | None = None) -> None:
        """Create an analyzer with the supplied policy or conservative defaults."""
        self.retry_policy = retry_policy or RetryPolicy()

    def analyze(self, attempts: pd.DataFrame) -> ReportAnalysis:
        """Build all analysis tables from validated attempt-level records."""
        utils = Utils()
        classified = utils.classify_attempts(attempts)
        runs = utils._build_run_summary(classified)
        retry_plan = utils._build_retry_plan(runs, self.retry_policy)
        escalations = retry_plan[
            retry_plan["retry_disposition"].isin({RETRY_EXHAUSTED, RETRY_MANUAL_REVIEW})
        ].copy()

        audit = classified.merge(
            retry_plan[
                [
                    "run_id",
                    "latest_attempt_number",
                    "retry_disposition",
                    "proposed_attempt_number",
                    "is_simulated",
                ]
            ],
            on="run_id",
            how="left",
            validate="many_to_one",
        )
        audit["is_latest_attempt"] = audit["attempt_number"].eq(
            audit["latest_attempt_number"]
        )

        return ReportAnalysis(
            attempts=audit,
            runs=runs,
            retry_plan=retry_plan,
            escalations=escalations,
        )
