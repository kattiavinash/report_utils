"""Focused tests for report attempt classification and retry decisions."""

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import constants
from report_utils import (
    EmailEscalator,
    ReportJobAnalyzer,
    RetryPolicy,
    load_jobs_dataframe,
    main,
)


class ReportJobAnalyzerTests(unittest.TestCase):
    """Verify attempt-level inputs become safe run-level decisions."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the supplied sample once for tests that exercise its history."""
        cls.sample = load_jobs_dataframe(constants.DEFAULT_DATA_PATH)

    def test_sample_outcomes_and_attempt_counts(self) -> None:
        """A prior completion makes a run successful despite an earlier failure."""
        analysis = ReportJobAnalyzer().analyze(self.sample)

        self.assertEqual(len(analysis.attempts), 15)
        self.assertEqual(len(analysis.runs), 12)
        self.assertEqual(
            set(analysis.attempts["normalized_status"]),
            {"completed", "failed", "timed_out", "error"},
        )
        self.assertEqual(
            analysis.runs["run_outcome"].value_counts().to_dict(),
            {constants.OUTCOME_SUCCEEDED: 10, constants.OUTCOME_FAILED: 2},
        )

        runs = analysis.runs.set_index("run_id")
        self.assertEqual(runs.loc["R-003", "run_outcome"], constants.OUTCOME_SUCCEEDED)
        self.assertEqual(runs.loc["R-005", "latest_status"], "failed")
        self.assertEqual(runs.loc["R-010", "latest_status"], "error")
        self.assertEqual(len(analysis.escalations), 2)
        beta_attempts = analysis.attempts[analysis.attempts["run_id"] == "R-003"]
        self.assertEqual(beta_attempts["is_latest_attempt"].tolist(), [False, True])

    def test_timeout_below_limit_gets_a_proposed_attempt_only(self) -> None:
        """A timeout under the cap yields a plan, not a fabricated job result."""
        attempt = self.sample.iloc[[0]].copy()
        attempt.loc[:, "job_id"] = "J-test"
        attempt.loc[:, "run_id"] = "R-test"
        attempt.loc[:, "status"] = "timed_out"
        attempt.loc[:, "attempt_number"] = 1

        analysis = ReportJobAnalyzer().analyze(attempt)

        decision = analysis.retry_plan.iloc[0]
        self.assertEqual(decision["retry_disposition"], constants.RETRY_CANDIDATE)
        self.assertEqual(decision["proposed_attempt_number"], 2)
        self.assertEqual(decision["proposed_status"], constants.RETRY_PLANNED_STATUS)
        self.assertTrue(decision["is_simulated"])
        self.assertEqual(len(analysis.attempts), 1)

    def test_timeout_at_attempt_limit_is_escalated(self) -> None:
        """The configured cap counts the original attempt and prevents attempt 4."""
        attempt = self.sample.iloc[[0]].copy()
        attempt.loc[:, "job_id"] = "J-test"
        attempt.loc[:, "run_id"] = "R-test"
        attempt.loc[:, "status"] = "timed_out"
        attempt.loc[:, "attempt_number"] = constants.MAX_TOTAL_ATTEMPTS

        analysis = ReportJobAnalyzer().analyze(attempt)

        self.assertEqual(
            analysis.retry_plan.iloc[0]["retry_disposition"],
            constants.RETRY_EXHAUSTED,
        )
        self.assertEqual(len(analysis.escalations), 1)

    def test_non_retryable_and_unknown_statuses_need_manual_review(self) -> None:
        """Error and unrecognized statuses are visible but never auto-retried."""
        attempts = self.sample.iloc[[0, 0]].copy()
        attempts.loc[:, "job_id"] = ["J-error", "J-unknown"]
        attempts.loc[:, "run_id"] = ["R-error", "R-unknown"]
        attempts.loc[:, "status"] = ["error", "mystery"]
        attempts.loc[:, "attempt_number"] = 1

        analysis = ReportJobAnalyzer().analyze(attempts)
        decisions = analysis.retry_plan.set_index("run_id")

        self.assertEqual(
            decisions.loc["R-error", "retry_disposition"],
            constants.RETRY_MANUAL_REVIEW,
        )
        self.assertEqual(
            decisions.loc["R-unknown", "run_outcome"],
            constants.OUTCOME_UNKNOWN,
        )
        self.assertEqual(
            decisions.loc["R-unknown", "retry_disposition"],
            constants.RETRY_MANUAL_REVIEW,
        )

    def test_empty_history_returns_empty_analysis(self) -> None:
        """An empty but well-formed history has stable empty output tables."""
        attempts = pd.DataFrame(columns=constants.REQUIRED_JOB_COLUMNS)

        analysis = ReportJobAnalyzer().analyze(attempts)

        self.assertTrue(analysis.attempts.empty)
        self.assertTrue(analysis.runs.empty)
        self.assertTrue(analysis.retry_plan.empty)
        self.assertTrue(analysis.escalations.empty)

    def test_loader_rejects_malformed_payload(self) -> None:
        """Malformed JSON structures fail explicitly rather than appearing empty."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "malformed.json"
            path.write_text(json.dumps({"records": []}), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "top-level 'jobs' list"):
                load_jobs_dataframe(path)

    def test_dry_run_does_not_open_an_smtp_connection(self) -> None:
        """Default email behavior logs the escalation without contacting SMTP."""
        escalations = ReportJobAnalyzer().analyze(self.sample).escalations

        with patch("report_utils.smtplib.SMTP") as smtp:
            result = EmailEscalator(enabled=False).send_escalation_email(escalations)

        self.assertEqual(result, "dry_run")
        smtp.assert_not_called()

    def test_cli_writes_all_csv_reports(self) -> None:
        """The command-line workflow emits the four documented report files."""
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            with redirect_stdout(output):
                result = main(["--output-dir", directory])

            self.assertEqual(result, 0)
            self.assertIn("12 logical report runs", output.getvalue())
            for name in (
                "attempts_audit.csv",
                "run_summary.csv",
                "retry_plan.csv",
                "escalations.csv",
            ):
                self.assertTrue((Path(directory) / name).is_file())

    def test_retry_policy_rejects_non_failure_statuses(self) -> None:
        """Policy configuration cannot make success eligible for automatic retry."""
        with self.assertRaisesRegex(ValueError, "recognized failures"):
            RetryPolicy(retryable_statuses=frozenset({"completed"}))


if __name__ == "__main__":
    unittest.main()
