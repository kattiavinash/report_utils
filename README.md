# Report Delivery Reliability Analyzer

**Version:** 1.0.0
**Runtime:** Python 3.10+ and pandas

This prototype reads attempt records from `data/report_jobs.json`, summarizes
each logical report run, and can simulate retries. It does not execute or
connect to a real job runner.

## Status and retry rules

- `completed`: the logical run is successful.
- `failed` or `error`: stop and require manual review.
- `timed_out`: retry while the total attempt count is below the configured
  maximum (default: 3, including the original).
- `timed_out` at the maximum: stop and escalate.

The dummy retry method returns one random status from `completed`, `failed`,
`error`, or `timed_out`. A retry that times out repeats while attempts remain;
completion stops the loop, and `failed`/`error` stop for manual review.

## Setup and run

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python report_utils.py
```

The script uses the settings in `constants.py`. To run simulated retries and
export CSV summaries, set the relevant values there before running:

```python
RUN_RETRIES = True
MAX_TOTAL_ATTEMPTS = 3
OUTPUT_DIR = PROJECT_ROOT / "output"
RETRY_SEED = 7
```

Run the script again with `python report_utils.py`. The default is
`RUN_RETRIES = False`, so the sample data is not modified unless retries are
explicitly enabled in `constants.py`. Each generated attempt is marked
`simulated: true`; its synthetic log is written separately. `RETRY_SEED` makes
the random sequence reproducible. The retry-log file is ignored by git. If the
retry limit is exhausted or a retry returns `failed`/`error`, the run is
included in the escalation summary. Email stays in dry-run mode; no SMTP
server is configured.
Before retrying, the analyzer selects runs whose action is `retry` and passes
only those run records to the retry loop. The loop does not reload or classify
the entire jobs file to decide eligibility; after attempts are appended, the
full file is reloaded to generate the final summary.

When `OUTPUT_DIR` is set, the output directory contains `run_summary.csv` and
`escalations.csv`. The same workflow can be called from another Python module
with parameters such as `main(run_retries=True, max_attempts=3)`.

## Optional AI API

All model client logic is in
[`bin/ai_integration.py`](./bin/ai_integration.py). AI is triggered only through
the local HTTP API, not through the report command-line options. The API reads
the job and retry-log JSON files locally, selects logs belonging to attempts
whose status is not `completed`, and sends only sanitized log strings to GitHub
Models. It does not send job IDs, tenant information, statuses, durations, or
the source files. Requests contain at most 20 logs each.

The supplied historical sample has no log text for its non-completed attempts,
so those records are skipped and no model request is made for them. AI
suggestions from generated retry logs are advisory, not a confirmed diagnosis.

Start the local API:

```bash
export GITHUB_TOKEN="<token authorized for GitHub Models inference>"
export GITHUB_MODELS_INFERENCE_ENABLED=true
python api.py
```

Request analysis over HTTP:

```bash
curl -X POST http://127.0.0.1:8000/api/root-cause \
  -H "Content-Type: application/json" \
  -d '{}'
```

The API binds to localhost by default. Set `REPORT_API_HOST` and
`REPORT_API_PORT` to change the bind address/port. Do not expose it to an
untrusted network without adding authentication and access controls.

Do not commit a token into `constants.py`. A public-repository read-only token
does not by itself authorize model inference; use the minimum inference
permission approved for your environment. Review log data handling before
sending operational evidence to an external model. If AI opt-in is absent, the
API returns a disabled response and does not send a model request.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use temporary files and mock model/retry outcomes; they do not call a
real runner, modify the sample dataset, or send email. The HTTP API test uses
loopback only and mocks the model client.

## Limitations

- Retries are randomized demonstrations, not real job executions.
- JSON is a single-process demo store. Atomic file replacement does not provide
  multi-writer transactions or production-grade durability.
- Retry safety depends on idempotent report generation; confirm this before
  connecting a real runner.
- The sample lacks log messages for historical failures.
- SMTP is deliberately dry-run. Configure a real email service separately.
