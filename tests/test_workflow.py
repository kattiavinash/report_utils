"""Tests for retry persistence, non-completed output, and AI API behavior."""

import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

import constants
from api import collect_uncompleted_logs, create_handler
from bin.ai_integration import GitHubModelsAI
from bin.retry_processor import DummyRetryProcessor
from report_utils import load_jobs_dataframe, main


class ReportWorkflowTests(unittest.TestCase):
    """Keep all integration-test writes inside temporary directories."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.jobs_path = self.directory / "jobs.json"
        self.logs_path = self.directory / "retry_logs.json"
        source = load_jobs_dataframe(constants.DEFAULT_DATA_PATH)
        retryable = source.iloc[[0]].copy()
        retryable.loc[:, "job_id"] = "J-timeout"
        retryable.loc[:, "run_id"] = "R-timeout"
        retryable.loc[:, "status"] = constants.RETRY_STATUS
        retryable.loc[:, "attempt_number"] = 1
        self.jobs_path.write_text(
            json.dumps({"jobs": retryable.to_dict(orient="records")}),
            encoding="utf-8",
        )

    def run_workflow(self, max_attempts: int = constants.MAX_TOTAL_ATTEMPTS) -> int:
        """Run main with test-local files and retry settings."""
        with patch.multiple(
            constants,
            DEFAULT_DATA_PATH=self.jobs_path,
            DEFAULT_RETRY_LOG_PATH=self.logs_path,
            MAX_TOTAL_ATTEMPTS=max_attempts,
            RUN_RETRIES=True,
            OUTPUT_DIR=None,
            RETRY_SEED=None,
        ):
            return main()

    def test_dummy_retry_returns_a_supported_status(self) -> None:
        """The simulator only returns statuses configured for job records."""
        self.assertIn(
            DummyRetryProcessor(seed=4).retry_job(),
            constants.DUMMY_RETRY_STATUSES,
        )

    def test_retry_attempts_are_logged_and_persisted_until_success(self) -> None:
        """Timeouts repeat with visible attempt numbers; completion stops retries."""
        output = StringIO()
        with (
            patch.object(
                DummyRetryProcessor, "retry_job", side_effect=["timed_out", "completed"]
            ),
            redirect_stdout(output),
        ):
            result = self.run_workflow(max_attempts=4)

        payload = json.loads(self.jobs_path.read_text(encoding="utf-8"))
        statuses = [job["status"] for job in payload["jobs"]]
        self.assertEqual(result, 0)
        self.assertEqual(statuses, ["timed_out", "timed_out", "completed"])
        self.assertIn("attempt 2/4", output.getvalue())
        self.assertIn("attempt 3/4", output.getvalue())
        self.assertNotIn("R-timeout", output.getvalue().split("Non-completed runs:")[-1].split(
            "Escalations / manual review:"
        )[0])

    def test_retry_failure_stops_and_shows_only_noncompleted_runs(self) -> None:
        """A failed retry stops and only unresolved entries appear in the report."""
        output = StringIO()
        with (
            patch.object(DummyRetryProcessor, "retry_job", return_value="failed"),
            redirect_stdout(output),
        ):
            self.run_workflow()

        jobs = json.loads(self.jobs_path.read_text(encoding="utf-8"))["jobs"]
        report_section = output.getvalue().split("Non-completed runs:")[-1].split(
            "Escalations / manual review:"
        )[0]
        self.assertEqual(len(jobs), 2)
        self.assertIn("manual_review", report_section)
        self.assertNotIn("completed", report_section)

    def test_exhausted_timeout_is_escalated(self) -> None:
        """A timeout at the total-attempt cap produces an escalation."""
        output = StringIO()
        with (
            patch.object(DummyRetryProcessor, "retry_job", return_value="timed_out"),
            redirect_stdout(output),
        ):
            self.run_workflow(max_attempts=3)
        self.assertIn("Retry attempts exhausted", output.getvalue())
        self.assertIn("escalation required", output.getvalue())

    def test_only_preselected_retry_records_are_passed_to_retry_function(self) -> None:
        """The retry function receives only runs classified as retryable."""
        jobs = json.loads(self.jobs_path.read_text(encoding="utf-8"))
        completed = dict(jobs["jobs"][0])
        completed.update({
            "job_id": "J-completed",
            "run_id": "R-completed",
            "status": constants.SUCCESS_STATUS,
        })
        jobs["jobs"].append(completed)
        self.jobs_path.write_text(json.dumps(jobs), encoding="utf-8")

        with (
            patch("report_utils._run_dummy_retries") as retry_function,
            patch.multiple(
                constants,
                DEFAULT_DATA_PATH=self.jobs_path,
                DEFAULT_RETRY_LOG_PATH=self.logs_path,
                MAX_TOTAL_ATTEMPTS=3,
                RUN_RETRIES=True,
                OUTPUT_DIR=None,
                RETRY_SEED=None,
            ),
            redirect_stdout(StringIO()),
        ):
            main()

        retry_records = retry_function.call_args.args[0]
        self.assertEqual(len(retry_records), 1)
        self.assertEqual(retry_records[0]["run_id"], "R-timeout")
        self.assertEqual(retry_records[0]["action"], constants.ACTION_RETRY)

    def test_collector_returns_only_logs_for_noncompleted_attempts(self) -> None:
        """Completed attempts and all job metadata are excluded from AI evidence."""
        jobs = {
            "jobs": [
                {"job_id": "done", "run_id": "R-1", "attempt_number": 1, "status": "completed"},
                {"job_id": "failed", "run_id": "R-2", "attempt_number": 1, "status": "failed"},
            ]
        }
        logs = {
            "logs": [
                {"job_id": "done", "run_id": "R-1", "attempt_number": 1, "message": "success log"},
                {"job_id": "failed", "run_id": "R-2", "attempt_number": 1, "message": "timeout stack trace"},
            ]
        }
        self.jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
        self.logs_path.write_text(json.dumps(logs), encoding="utf-8")

        self.assertEqual(
            collect_uncompleted_logs(self.jobs_path, self.logs_path),
            ["timeout stack trace"],
        )

    def test_ai_request_payload_contains_logs_only(self) -> None:
        """The outbound model request contains no attempt or tenant metadata."""
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return json.dumps({
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "findings": [{
                                    "index": 0,
                                    "category": "resource",
                                    "confidence": "medium",
                                    "summary": "Possible memory pressure.",
                                    "suggested_check": "Review worker memory metrics.",
                                }]
                            })
                        }
                    }]
                }).encode()

        captured = {}

        def fake_urlopen(request, timeout):
            captured.update(json.loads(request.data))
            return FakeResponse()

        with (
            patch.dict("os.environ", {constants.GITHUB_MODELS_TOKEN_ENV_VAR: "test"}),
            patch("bin.ai_integration.urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            findings = GitHubModelsAI().analyze_logs(
                ["error occurred for tenant secret=abc123"]
            )

        user_content = json.loads(captured["messages"][1]["content"])
        self.assertEqual(set(user_content), {"logs"})
        self.assertEqual(len(user_content["logs"]), 1)
        self.assertIsInstance(user_content["logs"][0], str)
        self.assertNotIn("abc123", user_content["logs"][0])
        self.assertEqual(findings[0]["category"], "resource")

    def test_http_api_triggers_ai_with_noncompleted_logs_only(self) -> None:
        """The API endpoint invokes the AI client, without a CLI AI option."""
        jobs = {
            "jobs": [
                {"job_id": "done", "run_id": "R-1", "attempt_number": 1, "status": "completed"},
                {"job_id": "failed", "run_id": "R-2", "attempt_number": 1, "status": "error"},
            ]
        }
        logs = {
            "logs": [
                {"job_id": "done", "run_id": "R-1", "attempt_number": 1, "message": "do not send"},
                {"job_id": "failed", "run_id": "R-2", "attempt_number": 1, "message": "worker allocation failed"},
            ]
        }
        self.jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
        self.logs_path.write_text(json.dumps(logs), encoding="utf-8")

        class FakeAI:
            def is_enabled(self):
                return True

            def analyze_logs(self, messages):
                self.messages = messages
                return [{"index": 0, "category": "resource"}]

        ai = FakeAI()
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), create_handler(self.jobs_path, self.logs_path, ai)
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)

        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/root-cause",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read())

        self.assertEqual(ai.messages, ["worker allocation failed"])
        self.assertEqual(result["analyzed_log_count"], 1)
        self.assertEqual(result["findings"][0]["category"], "resource")


if __name__ == "__main__":
    unittest.main()
