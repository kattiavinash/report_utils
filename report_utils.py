"""Analyze report-job attempts and produce conservative retry/escalation plans."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

import constants
from bin.email_escalator import EmailEscalator
from bin.report_job_analyzer import ReportJobAnalyzer
from model import ReportAnalysis, RetryPolicy

LOGGER = logging.getLogger(__name__)


def load_jobs_dataframe(path: str | Path) -> pd.DataFrame:
    """Load and validate the JSON job-attempt array as a pandas DataFrame.

    The provided file wraps its records in a top-level ``jobs`` key. A
    malformed document, missing key, non-list payload, or incomplete record
    raises an explicit exception instead of being interpreted as an empty
    history.
    """
    file_path = Path(path)
    with file_path.open(encoding="utf-8") as json_file:
        payload = json.load(json_file)

    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("Input JSON must contain a top-level 'jobs' list")

    jobs = payload["jobs"]
    if not jobs:
        return pd.DataFrame(columns=constants.REQUIRED_JOB_COLUMNS)
    if not all(isinstance(job, dict) for job in jobs):
        raise ValueError("Every item in 'jobs' must be a JSON object")

    attempts = pd.DataFrame(jobs)
    missing_columns = set(constants.REQUIRED_JOB_COLUMNS) - set(attempts.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Job data is missing required columns: {missing}")

    attempts["attempt_number"] = pd.to_numeric(
        attempts["attempt_number"], errors="raise"
    )
    valid_attempt_numbers = attempts["attempt_number"].map(
        lambda value: float(value).is_integer() and float(value) > 0
    )
    if attempts["attempt_number"].isna().any() or not valid_attempt_numbers.all():
        raise ValueError("attempt_number must be a positive integer")
    attempts["attempt_number"] = attempts["attempt_number"].astype("int64")
    if (
        attempts["job_id"].isna().any()
        or attempts["run_id"].isna().any()
        or attempts["job_id"].astype("string").str.strip().eq("").any()
        or attempts["run_id"].astype("string").str.strip().eq("").any()
    ):
        raise ValueError("job_id and run_id must not be empty")
    if attempts["job_id"].duplicated().any():
        raise ValueError("job_id values must be unique")
    if attempts.duplicated(["run_id", "attempt_number"]).any():
        raise ValueError("attempt_number values must be unique within each run_id")

    return attempts.sort_values(
        ["run_id", "attempt_number"], kind="stable"
    ).reset_index(drop=True)


def _write_reports(analysis: ReportAnalysis, output_dir: Path) -> None:
    """Write reproducible CSV views while preserving the original JSON input."""
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis.attempts.to_csv(output_dir / "attempts_audit.csv", index=False)
    analysis.runs.to_csv(output_dir / "run_summary.csv", index=False)
    analysis.retry_plan.to_csv(output_dir / "retry_plan.csv", index=False)
    analysis.escalations.to_csv(output_dir / "escalations.csv", index=False)


def main(argv: list[str] | None = None) -> int:
    """Run the report reliability analysis and optionally export its CSV views."""
    parser = argparse.ArgumentParser(
        description="Analyze report-job attempts and propose safe retry actions."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=constants.DEFAULT_DATA_PATH,
        help="Path to the JSON file containing the top-level jobs array.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional directory for attempt, run, retry, and escalation CSV files.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=constants.MAX_TOTAL_ATTEMPTS,
        help="Maximum total attempts, including the original attempt.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    policy = RetryPolicy(max_total_attempts=args.max_attempts)
    attempts = load_jobs_dataframe(args.data)
    analysis = ReportJobAnalyzer(policy).analyze(attempts)

    unresolved = analysis.runs[
        analysis.runs["run_outcome"] != constants.OUTCOME_SUCCEEDED
    ]
    retry_candidates = analysis.retry_plan[
        analysis.retry_plan["retry_disposition"] == constants.RETRY_CANDIDATE
    ]

    print(f"Report reliability analyzer v{constants.APP_VERSION}")
    print(
        f"Loaded {len(analysis.attempts)} attempts across "
        f"{len(analysis.runs)} logical report runs."
    )
    print("\nRuns that never completed:")
    if unresolved.empty:
        print("None")
    else:
        print(unresolved.to_string(index=False))

    print("\nRetry plan:")
    if retry_candidates.empty:
        print("No runs are eligible for an automatic retry.")
    else:
        print(retry_candidates.to_string(index=False))

    notification_status = EmailEscalator().send_escalation_email(analysis.escalations)
    print(f"\nEmail escalation: {notification_status}")

    if args.output_dir:
        _write_reports(analysis, args.output_dir)
        print(f"CSV reports written to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
