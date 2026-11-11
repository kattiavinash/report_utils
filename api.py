"""Local HTTP API for requesting root-cause suggestions on failed-job logs."""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import constants
from bin.ai_integration import GitHubModelsAI

LOGGER = logging.getLogger(__name__)


def collect_uncompleted_logs(jobs_path: Path, retry_logs_path: Path) -> list[str]:
    """Collect log strings only for attempts whose job status is not completed."""
    with jobs_path.open(encoding="utf-8") as source:
        jobs_payload = json.load(source)
    if not isinstance(jobs_payload, dict) or not isinstance(
        jobs_payload.get("jobs"), list
    ):
        raise ValueError(f"{jobs_path} must contain a top-level 'jobs' list")

    job_statuses = {
        str(job["job_id"]): str(job["status"]).strip().lower()
        for job in jobs_payload["jobs"]
    }
    logs_by_job: dict[str, list[str]] = {}
    logs_by_attempt: dict[tuple[str, int], list[str]] = {}

    if retry_logs_path.exists():
        with retry_logs_path.open(encoding="utf-8") as source:
            logs_payload = json.load(source)
        if not isinstance(logs_payload, dict) or not isinstance(
            logs_payload.get(constants.RETRY_LOGS_COLLECTION_KEY), list
        ):
            raise ValueError(f"{retry_logs_path} must contain a 'logs' list")
        for record in logs_payload[constants.RETRY_LOGS_COLLECTION_KEY]:
            message = record.get("message")
            if not isinstance(message, str) or not message.strip():
                continue
            if record.get("job_id") is not None:
                logs_by_job.setdefault(str(record["job_id"]), []).append(message)
            if record.get("run_id") is not None and record.get("attempt_number") is not None:
                key = (str(record["run_id"]), int(record["attempt_number"]))
                logs_by_attempt.setdefault(key, []).append(message)

    result: list[str] = []
    for job in jobs_payload["jobs"]:
        job_id = str(job["job_id"])
        status = job_statuses[job_id]
        if status == constants.SUCCESS_STATUS:
            continue
        direct_message = job.get("log_message")
        if isinstance(direct_message, str) and direct_message.strip():
            result.append(direct_message)
            continue
        if job_id in logs_by_job:
            result.extend(logs_by_job[job_id])
        else:
            key = (str(job["run_id"]), int(job["attempt_number"]))
            result.extend(logs_by_attempt.get(key, []))
    return result


def create_handler(
    jobs_path: Path,
    retry_logs_path: Path,
    ai_client: GitHubModelsAI | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Create an API handler bound to data paths and an optional AI client."""
    client = ai_client or GitHubModelsAI()

    class RootCauseHandler(BaseHTTPRequestHandler):
        """Serve the root-cause endpoint; bind only to localhost by default."""

        def do_POST(self) -> None:
            """Analyze unresolved logs when clients POST to the API route."""
            if self.path != "/api/root-cause":
                self._send_json(404, {"error": "Not found"})
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > constants.API_MAX_REQUEST_BYTES:
                self._send_json(413, {"error": "Request body is too large"})
                return
            try:
                body = self.rfile.read(content_length)
                if body and not isinstance(json.loads(body), dict):
                    self._send_json(400, {"error": "Request body must be a JSON object"})
                    return
                if not client.is_enabled():
                    self._send_json(503, {"error": "AI inference is not enabled"})
                    return
                logs = collect_uncompleted_logs(jobs_path, retry_logs_path)
                findings = client.analyze_logs(logs)
                self._send_json(
                    200,
                    {
                        "analyzed_log_count": len(logs),
                        "findings": findings,
                    },
                )
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Request body must be valid JSON"})
            except ValueError as error:
                self._send_json(503, {"error": str(error)})
            except (OSError, RuntimeError) as error:
                LOGGER.exception("Root-cause API request failed")
                self._send_json(502, {"error": str(error)})

        def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
            """Write a JSON response with a specific HTTP status."""
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            """Route access logs through Python logging."""
            LOGGER.info("%s - %s", self.address_string(), format % args)

    return RootCauseHandler


def serve(host: str = constants.API_HOST, port: int = constants.API_PORT) -> None:
    """Run the local API; AI runs only when its HTTP endpoint is requested."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    server = ThreadingHTTPServer(
        (host, port),
        create_handler(constants.DEFAULT_DATA_PATH, constants.DEFAULT_RETRY_LOG_PATH),
    )
    print(f"Root-cause API listening at http://{host}:{port}/api/root-cause")
    print("AI runs only on POST requests to /api/root-cause.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping API server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve(
        host=os.getenv("REPORT_API_HOST", constants.API_HOST),
        port=int(os.getenv("REPORT_API_PORT", str(constants.API_PORT))),
    )
