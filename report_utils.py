"""
Small utility module provided as an optional starting point for the
report delivery reliability case study.

Feel free to use, modify, replace, or ignore this entirely -- it is not
guaranteed to be complete or bug-free.
"""
import json

# Statuses that represent a failed job attempt.
FAILURE_STATUSES = {"failed", "timed_out"}

MAX_ATTEMPTS = 3


def load_jobs(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("jobs", [])


def is_failed(job):
    return job["status"] in FAILURE_STATUSES


def group_by_run(jobs):
    """Group job attempts by run_id, preserving attempt order."""
    runs = {}
    for job in jobs:
        runs.setdefault(job["run_id"], []).append(job)
    for run_id in runs:
        runs[run_id].sort(key=lambda j: j["attempt_number"])
    return runs


def latest_attempt(run_jobs):
    return max(run_jobs, key=lambda j: j["attempt_number"])


def needs_retry(job, max_attempts=MAX_ATTEMPTS):
    return is_failed(job) and job["attempt_number"] < max_attempts


def find_unresolved_runs(jobs, max_attempts=MAX_ATTEMPTS):
    """
    Return run_ids whose latest attempt is a failure and has exhausted
    (or is still within) the retry budget.
    """
    runs = group_by_run(jobs)
    unresolved = []
    for run_id, run_jobs in runs.items():
        latest = latest_attempt(run_jobs)
        if is_failed(latest):
            unresolved.append(run_id)
    return unresolved
