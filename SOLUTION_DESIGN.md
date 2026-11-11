# Report Delivery Reliability — Solution Design

## Problem

Meridian Payments needs to identify scheduled report runs that have not
successfully completed, distinguish successful runs from failed attempts, and
surface safe retry opportunities before customers report a missing statement.
The supplied log is attempt-level: several attempts can belong to one logical
run, keyed by `run_id`. Treating each failed row as a failed report would
misclassify runs that later completed.

## Findings and assumptions

The sample has 15 attempts, 12 logical runs, and four distinct statuses:
`completed`, `failed`, `timed_out`, and `error`.

- `completed` is the only success status. A run succeeds if any of its
  attempts is completed.
- `failed`, `error`, and `timed_out` are unsuccessful attempt statuses.
- The latest attempt determines the current unresolved reason when the run has
  no completed attempt. Unrecognized or missing statuses are marked unknown
  and sent for manual review.
- Only a latest `timed_out` attempt is a retry candidate. The limit is three
  total attempts, including the original attempt. `failed` and `error` are
  surfaced, not automatically retried, until their semantics and side effects
  are understood.
- Retry safety is not established by the sample. This policy must remain
  disabled from real execution until report generation is confirmed
  idempotent or protected with a deduplication key.
- The prototype's retry plan is a simulation. It proposes a next attempt and
  marks it `retry_planned`; it does not call a runner or claim a result.
- Email is implemented as an SMTP notifier but disabled by default. Local
  tests and standard runs use dry-run logging only.

## Proposed approach

`load_jobs_dataframe` parses and validates the JSON `jobs` array, then builds a
pandas DataFrame. It rejects malformed payloads, duplicate `job_id` values,
duplicate attempt numbers per run, and invalid IDs/attempt numbers. Statuses
are normalized before classification so casing and surrounding whitespace do
not produce false unknowns.

`ReportJobAnalyzer` creates four views:

1. An attempt audit retaining every source attempt.
2. One run summary per `run_id`, with success determined across all attempts.
3. A retry plan with the latest status, proposed next attempt (when eligible),
   and a human-readable decision reason.
4. An escalation list for exhausted retries, non-retryable failures, and
   unknown statuses.

The CLI prints unresolved runs and retry decisions. An optional output
directory receives CSV copies of the four views. `EmailEscalator` reports
escalations in dry-run mode by default and can use Python's standard SMTP
client when explicitly enabled and configured.

## Trade-offs

- **Pandas and a full-file JSON read:** simple, transparent, and appropriate
  for the supplied 15-row dataset and an initially bounded two-week report.
  Memory and startup cost grow with the full history, so this is not an
  unlimited-volume design.
- **Timeout-only retry:** conservative about duplicate financial statement
  generation. It may miss retryable transient failures, but avoids assuming
  that every failure is safe to repeat.
- **Three total attempts:** a clear initial cap with human escalation rather
  than unbounded retry loops. It is configurable and should be tuned using
  actual retry success rates, cost, and delivery objectives.
- **CSV outputs and no database:** easy to inspect and reproduce without
  introducing infrastructure. They do not provide durable coordination or
  exactly-once behavior.
- **SMTP dry-run default:** makes escalation logic testable without a server
  or accidental customer-facing messages. Production delivery requires
  secured credentials, provider configuration, retry/alerting for email
  failures, and ownership of the escalation destination.

## What to consider next

With more time, data, and budget:

- Confirm status meanings, job lifecycle guarantees, report idempotency, and
  how a late completion interacts with retries.
- Add error codes/messages, start/end timestamps, tenant delivery
  acknowledgements, retry lineage, idempotency keys, and an explicit terminal
  state to the event schema.
- Measure timeout and retry success rates by report type and tenant; choose
  capped exponential backoff with jitter and a retry budget based on those
  observations.
- Move attempt history to a durable database or event store with unique
  constraints, transactional claims/leases, and audit records. Use a
  scheduler/queue and idempotent runner adapter to perform retries safely.
- For larger histories, ingest partitioned JSONL/Parquet or query the durable
  store incrementally by scheduled-time window, aggregate in batches, and
  avoid repeatedly loading the complete two-week dataset into memory.
- Add metrics and alerting for unresolved runs, retry exhaustion, processing
  lag, duplicate suppression, and notification failures, with dashboards and
  an operator runbook.
- Replace placeholder email settings with a managed notification provider,
  secrets manager, delivery monitoring, and tested escalation ownership.
