"""Same-origin Workbench proxy and a bounded, signed remote-admin session."""
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
import os
import secrets
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import run_workbench

COOKIE = "__Host-pdp-workbench"
MAX_UPLOAD = 105 * 1024 * 1024


def local(handler):
    """Trust direct loopback access, never a public request forwarded from a local proxy."""
    return (handler.client_address[0] in ("127.0.0.1", "::1")
            and urlsplit("//" + handler.headers.get("Host", "")).hostname in ("127.0.0.1", "localhost", "::1"))


def same_origin(handler):
    """Require HTTPS for hosted writes and reject missing, foreign, or opaque origins."""
    scheme = "http" if local(handler) else "https"
    return (handler.headers.get("Origin") == f"{scheme}://{handler.headers.get('Host', '')}"
            and handler.headers.get("Sec-Fetch-Site", "same-origin") == "same-origin")


def authenticated(handler):
    """Validate the session without storing the admin credential in the browser."""
    if local(handler):
        return True
    token = os.environ.get("WORKBENCH_ADMIN_TOKEN", "")
    if len(token) < 32:
        return False
    try:
        cookies = SimpleCookie(handler.headers.get("Cookie", ""))
        value = cookies[COOKIE].value
        expires, nonce, signature = value.split(".")
        expected = hmac.new(token.encode(), f"{expires}.{nonce}".encode(), hashlib.sha256).hexdigest()
        return time.time() < int(expires) <= time.time() + 86400 and hmac.compare_digest(signature, expected)
    except (KeyError, ValueError, CookieError):
        return False


def authorize(handler):
    """Refuse remote access until the operator has signed in."""
    if authenticated(handler):
        return True
    handler._json({"error": "Unlock Workbench with its admin credential first."}, 401)
    return False


def login(handler, body):
    """Exchange a high-entropy operator secret for a one-day secure HttpOnly cookie."""
    if not same_origin(handler) or handler.headers.get("Content-Type") != "application/json":
        return handler._json({"error": "Sign in from this app's HTTPS page."}, 403)
    token = os.environ.get("WORKBENCH_ADMIN_TOKEN", "")
    if len(token) < 32:
        return handler._json({"error": "Set WORKBENCH_ADMIN_TOKEN (at least 32 random characters) on the server."}, 503)
    supplied = body.get("token")
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), token.encode()):
        return handler._json({"error": "The Workbench credential was not accepted."}, 401)
    payload = f"{int(time.time()) + 86400}.{secrets.token_hex(16)}"
    signature = hmac.new(token.encode(), payload.encode(), hashlib.sha256).hexdigest()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Set-Cookie", f"{COOKIE}={payload}.{signature}; Path=/; Max-Age=86400; HttpOnly; Secure; SameSite=Strict")
    handler.send_header("Content-Length", "11")
    handler.end_headers()
    handler.wfile.write(b'{"ok":true}')


def status(handler):
    """Report readiness and authentication separately, without exposing credentials."""
    return {"ready": run_workbench.ready(), "authenticated": authenticated(handler),
            "configured": local(handler) or len(os.environ.get("WORKBENCH_ADMIN_TOKEN", "")) >= 32}


def proxy(handler):
    """Forward only the Workbench UI or restricted API, after auth and write checks."""
    if not authorize(handler):
        return
    api = handler.path.startswith("/api/workbench-proxy/")
    if handler.command == "POST" and (not api or not same_origin(handler)):
        return handler._json({"error": "Workbench writes must come from this app."}, 403)
    body = None
    if handler.command == "POST":
        sizes = handler.headers.get_all("Content-Length", [])
        if len(sizes) != 1 or handler.headers.get("Transfer-Encoding"):
            return handler._json({"error": "A bounded Content-Length is required."}, 411)
        size = int(sizes[0])
        if size < 0 or size > MAX_UPLOAD:
            return handler._json({"error": "Workbench requests are limited to 105 MB."}, 413)
        handler.connection.settimeout(60)
        body = handler.rfile.read(size)
        if len(body) != size:
            raise ValueError("The upload was interrupted.")
    path = handler.path.removeprefix("/api/workbench-proxy") if api else handler.path
    port = 8100 if api else 3100
    headers = {name: handler.headers[name] for name in ("Content-Type", "Accept", "RSC", "Next-Router-State-Tree", "Next-Router-Prefetch", "Next-Router-Segment-Prefetch", "Next-Url")
               if name in handler.headers}
    request = Request(f"http://127.0.0.1:{port}{path}", data=body, headers=headers, method=handler.command)
    try:
        try:
            response = urlopen(request, timeout=120)
        except HTTPError as error:
            response = error
        with response:
            # Next's partial-prefetch client needs these to interpret its streamed payloads.
            forwarded = {name: response.headers[name] for name in
                         ("Vary", "X-Nextjs-Postponed", "X-Nextjs-Prerender", "X-Nextjs-Stale-Time", "X-Nextjs-Deployment-Id", "Content-Disposition")
                         if name in response.headers}
            handler._send(response.read(), response.headers.get("Content-Type", "application/octet-stream"),
                          status=response.status, extra_headers=forwarded)
    except OSError:
        handler._json({"error": "Workbench is unavailable. Restart the main app and check its service logs."}, 503)
