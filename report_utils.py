"""Analyze report attempts and optionally run the dummy retry workflow."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

import constants
from bin.email_escalator import EmailEscalator
from bin.report_job_analyzer import ReportJobAnalyzer
from bin.retry_processor import DummyRetryProcessor, append_json_record
from model import ReportAnalysis


def load_jobs_dataframe(path: str | Path) -> pd.DataFrame:
    """Load the top-level jobs array and validate the small required schema."""
    with Path(path).open(encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise ValueError("Input JSON must contain a top-level 'jobs' list")

    attempts = pd.DataFrame(payload["jobs"])
    missing = set(constants.REQUIRED_JOB_COLUMNS) - set(attempts.columns)
    if missing and not attempts.empty:
        raise ValueError(
            f"Job data is missing required columns: {', '.join(sorted(missing))}"
        )
    if attempts.empty:
        return pd.DataFrame(columns=constants.REQUIRED_JOB_COLUMNS)
    attempts["attempt_number"] = pd.to_numeric(
        attempts["attempt_number"], errors="raise"
    )
    print("When performing numeric")
    print(attempts)
    if (
        attempts["attempt_number"].isna().any()
        or (attempts["attempt_number"] < 1).any()
        or (attempts["attempt_number"] % 1 != 0).any()
    ):
        raise ValueError("attempt_number must be a positive integer")
    attempts["attempt_number"] = attempts["attempt_number"].astype("int64")
    if attempts["job_id"].isna().any() or attempts["run_id"].isna().any():
        raise ValueError("job_id and run_id must not be empty")
    if attempts["job_id"].duplicated().any():
        raise ValueError("job_id values must be unique")
    if attempts.duplicated(["run_id", "attempt_number"]).any():
        raise ValueError("attempt_number values must be unique within each run_id")
    return attempts.sort_values(
        ["run_id", "attempt_number"], kind="stable"
    ).reset_index(drop=True)


def _write_reports(analysis: ReportAnalysis, output_dir: Path) -> None:
    """Write the run summary and escalation list as simple CSV reports."""
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis.runs.to_csv(output_dir / "run_summary.csv", index=False)
    analysis.escalations.to_csv(output_dir / "escalations.csv", index=False)


def _run_dummy_retries(
    retry_records: list[dict[str, Any]],
    data_path: Path,
    log_path: Path,
    max_attempts: int,
    seed: int | None,
) -> None:
    """Run retries for preselected eligible runs and persist each new attempt."""
    if data_path.resolve() == log_path.resolve():
        raise ValueError("The retry log path must be separate from the jobs JSON file")

    processor = DummyRetryProcessor(seed)

    for run in retry_records:
        attempt_count = int(run["attempt_count"])
        current_job_id = run["latest_job_id"]
        status = constants.RETRY_STATUS

        while attempt_count < max_attempts:
            next_number = attempt_count + 1
            job_id = f"{run['run_id']}-attempt-{next_number}"
            print(
                f"Retrying attempt {next_number}/{max_attempts} for run "
                f"{run['run_id']} | prior job {current_job_id} | new job {job_id} | "
                f"tenant {run['tenant_name']} | report {run['report_name']} | "
            )
            status = processor.retry_job()
            timestamp = datetime.now(UTC).isoformat()
            attempt = {
                "job_id": job_id,
                "run_id": run["run_id"],
                "tenant_id": run["tenant_id"],
                "tenant_name": run["tenant_name"],
                "report_name": run["report_name"],
                "scheduled_at": timestamp,
                "status": status,
                "attempt_number": next_number,
                "duration_seconds": (300 if status == constants.RETRY_STATUS else 1),
                "row_count": None,
                "simulated": True,
            }
            log_record = {
                "job_id": job_id,
                "run_id": run["run_id"],
                "attempt_number": next_number,
                "timestamp": timestamp,
                "message": constants.DUMMY_RETRY_LOGS[status],
                "simulated": True,
            }
            append_json_record(data_path, "jobs", attempt)
            append_json_record(
                log_path, constants.RETRY_LOGS_COLLECTION_KEY, log_record
            )
            attempt_count += 1
            print(
                f"Retry result: {job_id} finished with status '{status}'. "
                f"{log_record['message']}"
            )
            current_job_id = job_id
            if status in constants.MANUAL_REVIEW_STATUSES:
                print(f"Manual review required for run {run['run_id']}.")
            if status != constants.RETRY_STATUS:
                break

        if status == constants.RETRY_STATUS and attempt_count >= max_attempts:
            print(
                f"Retry attempts exhausted for run {run['run_id']}; "
                "escalation required."
            )

    if not retry_records:
        print("No runs are eligible for a retry.")


def main() -> int:
    """Run analysis and optional retries using Python settings, not CLI options."""
    data_path: str = constants.DEFAULT_DATA_PATH
    output_dir: str = constants.OUTPUT_DIR
    max_attempts: int = constants.MAX_TOTAL_ATTEMPTS
    run_retries: bool = constants.RUN_RETRIES
    retry_logs_path: str | Path = constants.DEFAULT_RETRY_LOG_PATH
    seed: int | None = constants.RETRY_SEED
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    data_path = Path(data_path)
    retry_logs_path = Path(retry_logs_path)
    attempts = load_jobs_dataframe(data_path)
    print(attempts)
    analysis = ReportJobAnalyzer(max_attempts).analyze(attempts)
    if run_retries:
        retry_records = analysis.runs[
            analysis.runs["action"] == constants.ACTION_RETRY
        ].to_dict(orient="records")
        _run_dummy_retries(
            retry_records, data_path, retry_logs_path, max_attempts, seed
        )
        attempts = load_jobs_dataframe(data_path)
        print(attempts)
        analysis = ReportJobAnalyzer(max_attempts).analyze(attempts)

    print(f"Report reliability analyzer v{constants.APP_VERSION}")
    print(f"Loaded {len(attempts)} attempts across {len(analysis.runs)} report runs.")
    non_completed = analysis.runs[analysis.runs["action"] != constants.ACTION_SUCCESS]
    print("\nNon-completed runs:")
    print(non_completed.to_string(index=False) if not non_completed.empty else "None")
    print("\nEscalations / manual review:")
    print(
        analysis.escalations.to_string(index=False)
        if not analysis.escalations.empty
        else "None"
    )
    print(
        f"\nEmail escalation: {EmailEscalator().send_escalation_email(analysis.escalations)}"
    )

    if output_dir:
        output_dir = Path(output_dir)
        _write_reports(analysis, output_dir)
        print(f"\nCSV reports written to {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
