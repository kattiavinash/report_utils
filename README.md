# Report Delivery Reliability Analyzer

**Application version:** 1.0.0
**Runtime used for this implementation:** Python 3.14.3, pandas 3.1.1
**Supported runtime:** Python 3.10 or newer

This prototype reads report-job attempt history from JSON, summarizes each
logical report run, identifies runs that never completed, and proposes
conservative retries. It does not connect to or execute jobs on an external
job runner.

## What the sample shows

The supplied dataset has 15 attempts across 12 logical runs. `completed` means
an attempt succeeded. A `run_id` is considered successful if any attempt
completed, even if an earlier attempt failed. `failed`, `error`, and
`timed_out` are non-success outcomes. Unknown statuses are surfaced for manual
review.

Only a latest `timed_out` status can be proposed for retry. The default limit is
three total attempts, including the original attempt. A retry proposal is
marked `retry_planned`; it is not an executed job attempt, and no result is
invented. The sample's unsuccessful runs are surfaced for escalation, but it
does not currently contain a latest timeout that is below the retry limit.

## Setup

From the project directory, create and activate a virtual environment, then
install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate`.

## Run

Analyze the bundled data:

```bash
python report_utils.py
```

Use another JSON file and export CSV reports:

```bash
python report_utils.py \
  --data data/report_jobs.json \
  --output-dir output \
  --max-attempts 3
```

The command prints runs that never completed, retry decisions, and the email
notification mode. When `--output-dir` is supplied, it writes:

- `attempts_audit.csv` — all source attempts plus classification and latest-run
  decision fields.
- `run_summary.csv` — one outcome row per logical `run_id`.
- `retry_plan.csv` — the proposed retry disposition and, where eligible, the
  next attempt number.
- `escalations.csv` — unresolved runs that have exhausted retry policy or need
  manual review.

The input JSON must contain a top-level `jobs` array with the fields in the
sample. The loader rejects malformed records, duplicate job IDs, duplicate
attempt numbers within a run, and invalid attempt numbers.

## Email behavior and test safety

No email is sent during testing or a default run. `constants.py` sets
`EMAIL_ENABLED = False`; in this mode the notifier logs a dry-run message.
SMTP host, sender, and recipient values in `constants.py` are placeholders,
not working server credentials. There is no SMTP server configured here.

For a real integration, confirm retry idempotency first, configure an
authorized SMTP host, set `EMAIL_ENABLED = True`, and provide credentials via
`REPORTS_SMTP_USERNAME` and `REPORTS_SMTP_PASSWORD`. The optional recipient
override is `REPORTS_ESCALATION_RECIPIENT`. SMTP/configuration failures are
surfaced to the caller.

## Tests

Run the standard-library unit tests:

```bash
python -m unittest discover -s tests -v
```

The tests cover sample outcome aggregation, timeout retry decisions and limits,
unknown/non-retryable statuses, empty input, malformed input, dry-run email,
and report exports. They do not contact an SMTP server.

## Known limitations

- Retry safety is not proven by a timeout status. The report-generation side
  effect must be idempotent or deduplicated before enabling a real retry
  executor.
- This is a local, in-memory pandas analysis and simulator. It has no durable
  attempt ledger, scheduler, distributed locking, concurrency control, or
  integration with a job runner.
- The JSON file is loaded in full. This is appropriate for the supplied
  exercise dataset, not an unlimited two-week production history. See
  [SOLUTION_DESIGN.md](./SOLUTION_DESIGN.md) for a scale-up path.
- The attempt schema does not include error details, report delivery
  confirmation, or an explicit retryability/idempotency key.
