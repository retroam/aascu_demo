"""Dependency-light local demo server. Run with ../.venv/bin/python server.py."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import analytics
import llm_chat
import dataset
import run_workbench
import workbench_host

ROOT = Path(__file__).resolve().parent
STATIC_SUFFIXES = {".html", ".js", ".css", ".svg", ".ico", ".png", ".jpg", ".jpeg", ".webp", ".woff", ".woff2"}
MAX_BODY = 16_384


class Handler(BaseHTTPRequestHandler):
    server_version = "PDPDemo/1.0"

    def _send(self, content, content_type="application/json; charset=utf-8", status=200, filename=None, etag=None, extra_headers=None):
        if isinstance(content, str):
            content = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if status != 304:
            self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "private, no-cache" if etag else "no-store")
        if etag:
            self.send_header("ETag", etag)
        self.send_header("Referrer-Policy", "same-origin")
        if getattr(self, "dataset_generation", None):
            self.send_header("X-PDP-Dataset", self.dataset_generation)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def _json(self, value, status=200):
        self._send(json.dumps(value, ensure_ascii=False, allow_nan=False), status=status)

    def _local_host(self):
        """Reject DNS rebinding hosts even when Origin equals the forged Host."""
        hosts = self.headers.get_all("Host", [])
        try:
            parsed = urlsplit("//" + hosts[0]) if len(hosts) == 1 else None
            public = os.environ.get("SANDBOX_PUBLIC_HOST", "").strip().lower()
            loopback = parsed is not None and parsed.hostname in ("localhost", "127.0.0.1", "::1") and parsed.port == self.server.server_address[1]
            published = parsed is not None and bool(public) and parsed.hostname == public and parsed.port in (None, 80, 443)
            valid = (parsed is not None and (loopback or published) and not parsed.username
                     and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment)
        except ValueError:
            valid = False
        if not valid:
            self._json({"error": "Use a local hostname and the server's actual port."}, 403)
        return valid

    def _query(self):
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if any(len(v) > 1 for v in query.values()):
            raise ValueError("Each query parameter must appear once.")
        return {k: v[0] for k, v in query.items()}

    def do_HEAD(self):
        self.do_GET()

    @dataset.guard_request
    def do_GET(self):
        try:
            if not self._local_host():
                return
            path = unquote(urlsplit(self.path).path)
            if path == "/workbench-ui" or path.startswith(("/workbench-ui/", "/api/workbench-proxy/")):
                return workbench_host.proxy(self)
            query = self._query()
            if path == "/api/health":
                return self._json({"status": "ok", "synthetic": True, "chat": llm_chat.config(), "dataset": dataset.identity()})
            if path == "/api/workbench/dataset":
                if not workbench_host.authorize(self):
                    return
                return self._json(dataset.preview())
            if path == "/api/workbench":
                return self._json(workbench_host.status(self))
            if path == "/api/dashboard":
                return self._json(analytics.get_dashboard(query))
            if path == "/api/students":
                from students import get_students
                return self._json(get_students(query))
            if path == "/api/student":
                from students import get_student
                try:
                    return self._json(get_student(query))
                except LookupError as exc:
                    return self._json({"error": str(exc)}, 404)
            if path == "/api/trends":
                return self._json(analytics.get_trends(query))
            if path == "/api/gaps":
                return self._json(analytics.get_gaps(query))
            if path == "/api/measures":
                return self._json(analytics.get_shared_measures(query))
            if path == "/api/definitions":
                if query:
                    raise ValueError("Definitions do not accept filters.")
                return self._json(analytics.foundations.documentation())
            if path == "/api/model":
                from modeling import get_model
                return self._json(get_model())
            if path == "/api/report":
                format_ = query.pop("format", "html")
                metrics = analytics.report_metrics(query.pop("metrics", None))
                f = analytics.normalize_filters(query)
                filename = f"pdp-evidence-{f['cohort']}-{f['population']}"
                if format_ == "csv":
                    return self._send(analytics.report_csv(f, metrics), "text/csv; charset=utf-8", filename=filename+".csv")
                if format_ == "html":
                    return self._send(analytics.report_html(f, metrics), "text/html; charset=utf-8", filename=filename+".html")
                raise ValueError("Report format must be html or csv.")
            if path.startswith("/api/"):
                return self._json({"error": "API route not found."}, 404)
            asset = (ROOT / (path.lstrip("/") or "index.html")).resolve()
            if ROOT not in asset.parents or asset.suffix.lower() not in STATIC_SUFFIXES or not asset.is_file():
                return self._json({"error": "File not found."}, 404)
            content = asset.read_bytes()
            etag = '"' + hashlib.sha256(content).hexdigest() + '"'
            if self.headers.get("If-None-Match") == etag:
                return self._send(b"", status=304, etag=etag)
            return self._send(content, mimetypes.guess_type(asset.name)[0] or "application/octet-stream", etag=etag)
        except dataset.SyncError as exc:
            self._json({"error": str(exc)}, exc.status)
        except ValueError as exc:
            self._json({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self.log_error("Request failed: %s", str(exc))
            self._json({"error": "The local analysis could not be completed. Check the server output."}, 500)

    @dataset.guard_request
    def do_POST(self):
        try:
            if not self._local_host():
                return
            path = urlsplit(self.path).path
            if path == "/workbench-ui" or path.startswith(("/workbench-ui/", "/api/workbench-proxy/")):
                return workbench_host.proxy(self)
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                return self._json({"error": "Cross-origin requests are not accepted."}, 403)
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > MAX_BODY:
                return self._json({"error": "Expected a JSON body smaller than 16 KB."}, 413)
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("The JSON body must be an object.")
            if path == "/api/workbench/login":
                return workbench_host.login(self, body)
            if path == "/api/workbench/sync":
                if not workbench_host.authorize(self):
                    return
                allowed = (workbench_host.same_origin(self)
                           and self.headers.get("Content-Type") == "application/json"
                           and self.headers.get("X-PDP-Action") == "replace-dashboard")
                if not allowed:
                    return self._json({"error": "Sync requires confirmation from this app's page."}, 403)
                if (set(body) != {"confirm", "synthetic", "workbench_run_id", "current_run_id"}
                        or body["confirm"] != "REPLACE ALL DASHBOARD DATA" or body["synthetic"] is not True
                        or not all(isinstance(body[key], str) for key in ("workbench_run_id", "current_run_id"))):
                    raise ValueError("Confirm the previewed dataset and attest that it contains only synthetic data.")
                return self._json({"dataset": dataset.sync(body["workbench_run_id"], body["current_run_id"])})
            if path == "/api/chat":
                if set(body) - {"question", "filters", "context", "concise"}:
                    raise ValueError("Only question, filters, context, and concise are accepted.")
                return self._json(llm_chat.answer_question(body.get("question"), body.get("filters"), body.get("context"), concise=body.get("concise", True)))
            if path == "/api/scenario":
                from modeling import get_scenario
                return self._json(get_scenario(body))
            return self._json({"error": "API route not found."}, 404)
        except dataset.SyncError as exc:
            self._json({"error": str(exc)}, exc.status)
        except llm_chat.ChatError as exc:
            self._json(llm_chat.error_response(str(exc), exc.attempts), exc.status)
        except (ValueError, json.JSONDecodeError) as exc:
            if urlsplit(self.path).path == "/api/chat":
                self._json(llm_chat.error_response("Invalid chat request. Check the question, filters, and prior context."), 400)
            else:
                self._json({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            # Never log prompts, provider errors, or credentials from chat failures.
            if urlsplit(self.path).path == "/api/chat":
                self._json(llm_chat.error_response("The local analysis could not be completed."), 500)
            else:
                self.log_error("Request failed: %s", type(exc).__name__)
                self._json({"error": "The local analysis could not be completed."}, 500)


class DemoServer(ThreadingHTTPServer):
    """Monitor the Workbench children during the normal HTTP serving loop."""
    def service_actions(self):
        """Stop on child failure instead of leaving a permanently broken sidebar page."""
        self.workbench.check()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDP institutional intelligence demo")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    from env_config import load_chat_env
    load_chat_env()
    def stop(_signal, _frame):
        """Let systemd and terminal termination clean up both private services."""
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    server = DemoServer((args.host, args.port), Handler)
    server.workbench = run_workbench.WorkbenchServices()
    try:
        analytics.load_data()
        server.workbench.start()
        print(f"PDP demo and Workbench ready at http://{args.host}:{args.port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PDP demo.")
    finally:
        server.server_close()
        server.workbench.close()
