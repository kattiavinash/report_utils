# Starter Kit — Report Delivery Reliability

## Contents

- `data/report_jobs.json` — 15 synthetic report-job attempts across 6 tenants and 12 logical report runs, over a 2-week period.
- `report_utils.py` — a small, optional Python utility module with basic failure-detection and retry-eligibility helpers, provided as a rough starting point.

## A few notes

- You're free to use, modify, replace, or ignore `report_utils.py` entirely — it's not guaranteed to be complete, optimal, or bug-free.
- Some runs took more than one attempt (see `run_id` and `attempt_number`) — a few succeeded on retry, at least one never succeeded at all. Worth checking every distinct `status` value that shows up in the data and whether your (or the provided) logic accounts for all of them.
