"""Small result model shared by the report workflow."""

from dataclasses import dataclass

import pandas as pd

import constants


@dataclass(frozen=True)
class ReportAnalysis:
    """Keep raw attempts and the concise per-run summary."""

    attempts: pd.DataFrame
    runs: pd.DataFrame

    @property
    def escalations(self) -> pd.DataFrame:
        """Return timed-out runs at the cap and runs needing manual review."""
        actions = {constants.ACTION_ESCALATE, constants.ACTION_MANUAL_REVIEW}
        return self.runs[self.runs["action"].isin(actions)].copy()
