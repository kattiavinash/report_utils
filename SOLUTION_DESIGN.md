# Report Delivery Reliability — Solution Design

## Problem and assumptions

The input stores one row per attempt, and `run_id` identifies a logical report
run. A run is successful if any attempt has status `completed`. The latest
attempt controls the next action when there is no success:

- `failed` or `error` stops automated processing and requires manual review.
- `timed_out` is retried while total attempt count is below the configured
  maximum (3 by default, including the original attempt).
- A timeout at the limit is escalated.
- The retry implementation is a simulator: it randomly returns one of the
  existing statuses (`completed`, `failed`, `error`, `timed_out`).

The supplied records contain no historical log text and do not establish that
real statement generation is idempotent. Simulated retry outcomes and their
synthetic logs are explicitly marked; they must not be interpreted as real job
history.

## Approach

`ReportJobAnalyzer` produces one concise row per `run_id`: latest job/status,
attempt count, action, and reason. `DummyRetryProcessor.retry_job()` only
chooses and returns a status. The Python script workflow handles the loop and
persists each simulated attempt to the configured jobs JSON file; a separate
JSON file stores its generated log. The loop stops at success, a non-timeout
failure, or the attempt limit. Exhausted timeouts and `failed`/`error` cases
are passed to the existing email escalation component, which is dry-run by
default. Before calling the retry function, the analyzer selects only records
whose action is `retry`; the retry function does not reload or reclassify the
full dataset. After writing attempts, the full JSON file is reloaded for the
final report. Settings live in `constants.py`; retries are disabled by default.

Optional AI analysis is triggered through a localhost HTTP endpoint,
`POST /api/root-cause`, rather than the reporting CLI. The API filters job
attempts to those whose status is not `completed`, joins their log strings, and
sends only sanitized log strings to the model in batches of at most 20. Job
IDs, tenant data, statuses, duration/count metadata, and source files are not
sent. Attempts with no log text are skipped; the supplied historical sample
therefore produces no AI request. The client lives in
`bin/ai_integration.py`. Calls require explicit opt-in and a GitHub token
authorized for model inference; repository read access alone is insufficient.
Model output is advisory.

The CLI can write `run_summary.csv` and `escalations.csv` for inspection.

## Trade-offs and limitations

- A small, direct classifier and loop are easier to inspect than a separate
  multi-stage planning model. The simulator does not provide runner execution,
  backoff, concurrency control, or exactly-once behavior.
- JSON is convenient for this exercise and keeps attempt records inspectable.
  Atomic replacement helps avoid partial writes but does not support concurrent
  writers or database transactions.
- The three-attempt default and timeout-only retry are conservative starting
  points. A timeout does not prove a retry is safe: production integration
  requires idempotency or a deduplication key.
- Random outcomes make retry demonstrations simple, not predictive. A seeded
  run helps reproduce a demo.
- AI batching reduces request count, but remote inference still has privacy,
  cost, and correctness trade-offs. Redaction is best-effort, not a guarantee.
  Logs without usable text are excluded rather than analyzed from unrelated
  job metadata.
- The HTTP API binds to localhost by default. It should not be exposed to an
  untrusted network without authentication and access controls.
- Email is not delivered in tests or default runs; SMTP details remain
  placeholders and dry-run mode is enabled.

## With more time, data, or budget

Connect the workflow to the actual job runner and persist structured lifecycle
events in a transactional store. Add an idempotency key, retry scheduling with
bounded backoff, deduplication, and concurrency-safe claims. Collect real
failure logs, resource metrics, and delivery confirmations; validate retry
policy against historical outcomes. For AI, evaluate suggestions against
labeled incidents, apply a data privacy review, monitor output quality, and
retain model/prompt versions. Replace placeholder SMTP with a managed
notification service and operational alerting.
