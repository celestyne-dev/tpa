"""Local Paystack stand-in for development and browser end-to-end tests only.

It implements the small part of Paystack's REST API this app uses
(initialize, verify, refund) plus a fake hosted payment page, and sends
webhooks signed exactly like Paystack (HMAC-SHA512 of the raw body keyed with
the secret key). No money moves and nothing leaves this machine.

    PAYSTACK_SECRET_KEY=sk_test_local_mock \\
    python scripts/paystack_mock.py --port 8765 \\
        --webhook http://127.0.0.1:5000/api/v1/payments/paystack/webhook

Point the app at it with ``PAYSTACK_API_BASE=http://127.0.0.1:8765`` and the
same ``sk_test_`` key. Production configuration refuses any API base other
than https://api.paystack.co, so this mock can never be used there.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import itertools
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TRANSACTIONS: dict[str, dict] = {}
REFUNDS: dict[str, dict] = {}
_ids = itertools.count(1000)
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Handler(BaseHTTPRequestHandler):
    server_version = "PaystackMock/1.0"
    secret = ""
    webhook = ""
    base = ""

    # ---- helpers ------------------------------------------------------------------------

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self) -> bool:
        if self.headers.get("Authorization") == f"Bearer {self.secret}":
            return True
        self._json(401, {"status": False, "message": "Invalid key"})
        return False

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
            return dict(urllib.parse.parse_qsl(raw.decode()))
        return json.loads(raw or b"{}")

    def _send_webhook(self, event: str, data: dict) -> None:
        if not self.webhook:
            return
        raw = json.dumps({"event": event, "data": data}).encode()
        signature = hmac.new(self.secret.encode(), raw, hashlib.sha512).hexdigest()
        request = urllib.request.Request(
            self.webhook,
            data=raw,
            method="POST",
            headers={"Content-Type": "application/json", "x-paystack-signature": signature},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                print(f"webhook {event} -> {response.status}", flush=True)
        except Exception as err:  # noqa: BLE001 - development logging only
            print(f"webhook {event} failed: {err}", flush=True)

    @staticmethod
    def _public(tx: dict) -> dict:
        return {
            k: tx[k]
            for k in (
                "id",
                "domain",
                "status",
                "reference",
                "amount",
                "currency",
                "channel",
                "paid_at",
                "gateway_response",
            )
            if k in tx
        }

    # ---- routes -------------------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/transaction/initialize":
            if not self._authorised():
                return
            body = self._body()
            reference = body["reference"]
            with _lock:
                if reference in TRANSACTIONS:
                    self._json(400, {"status": False, "message": "Duplicate Transaction Reference"})
                    return
                TRANSACTIONS[reference] = {
                    "id": next(_ids),
                    "domain": "test",
                    "status": "abandoned",
                    "reference": reference,
                    "amount": int(body["amount"]),
                    "currency": body.get("currency", "NGN"),
                    "email": body.get("email"),
                    "callback_url": body.get("callback_url"),
                    "channel": None,
                    "paid_at": None,
                    "gateway_response": "",
                }
            self._json(
                200,
                {
                    "status": True,
                    "message": "Authorization URL created",
                    "data": {
                        "authorization_url": f"{self.base}/pay/{urllib.parse.quote(reference)}",
                        "access_code": f"mock_{reference}",
                        "reference": reference,
                    },
                },
            )
            return
        if path.startswith("/pay/"):
            parts = path.split("/")
            reference, outcome = urllib.parse.unquote(parts[2]), parts[3] if len(parts) > 3 else ""
            tx = TRANSACTIONS.get(reference)
            if not tx or outcome not in ("success", "failed"):
                self._json(404, {"status": False, "message": "Not found"})
                return
            tx.update(
                status=outcome,
                channel="card",
                gateway_response="Approved" if outcome == "success" else "Declined",
                paid_at=_now() if outcome == "success" else None,
            )
            if outcome == "success":
                self._send_webhook("charge.success", self._public(tx))
            target = tx["callback_url"] or "/"
            sep = "&" if "?" in target else "?"
            self.send_response(302)
            self.send_header("Location", f"{target}{sep}reference={urllib.parse.quote(reference)}")
            self.end_headers()
            return
        if path == "/refund":
            if not self._authorised():
                return
            body = self._body()
            tx = next(
                (t for t in TRANSACTIONS.values() if str(t["id"]) == str(body["transaction"])), None
            )
            if not tx:
                self._json(404, {"status": False, "message": "Transaction not found"})
                return
            refund = {
                "id": next(_ids),
                "status": "pending",
                "currency": tx["currency"],
                "amount": int(body.get("amount") or tx["amount"]),
                "transaction": {"id": tx["id"], "reference": tx["reference"]},
            }
            REFUNDS[str(refund["id"])] = refund
            self._json(200, {"status": True, "message": "Refund has been queued", "data": refund})
            return
        self._json(404, {"status": False, "message": "Not found"})

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/transaction/verify/"):
            if not self._authorised():
                return
            tx = TRANSACTIONS.get(urllib.parse.unquote(path.rsplit("/", 1)[1]))
            if not tx:
                self._json(400, {"status": False, "message": "Transaction reference not found"})
                return
            self._json(
                200,
                {"status": True, "message": "Verification successful", "data": self._public(tx)},
            )
            return
        if path.startswith("/refund/"):
            if not self._authorised():
                return
            refund = REFUNDS.get(path.rsplit("/", 1)[1])
            if not refund:
                self._json(404, {"status": False, "message": "Refund not found"})
                return
            self._json(200, {"status": True, "message": "Refund retrieved", "data": refund})
            return
        if path.startswith("/pay/"):
            reference = urllib.parse.unquote(path.split("/")[2])
            tx = TRANSACTIONS.get(reference)
            if not tx:
                self._json(404, {"status": False, "message": "Not found"})
                return
            ref = html.escape(urllib.parse.quote(reference))
            amount = f"{tx['currency']} {tx['amount'] / 100:.2f}"
            page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Paystack mock</title>
<style>body{{font-family:system-ui;max-width:28rem;margin:3rem auto;padding:0 1rem}}
button{{font-size:1rem;padding:.6rem 1rem;margin:.25rem}}</style></head><body>
<p><strong>LOCAL PAYSTACK MOCK — no money moves.</strong></p>
<h1>Pay {html.escape(amount)}</h1><p>Reference: {html.escape(reference)}</p>
<form method="post" action="/pay/{ref}/success"><button>Simulate successful payment</button></form>
<form method="post" action="/pay/{ref}/failed"><button>Simulate declined payment</button></form>
</body></html>""".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        self._json(404, {"status": False, "message": "Not found"})

    def log_message(self, fmt: str, *args) -> None:
        print(
            f"mock {self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--webhook", default="", help="App webhook URL to notify")
    args = parser.parse_args()
    secret = os.environ.get("PAYSTACK_SECRET_KEY", "")
    if not secret.startswith("sk_test_"):
        print("Refusing to start: PAYSTACK_SECRET_KEY must be a sk_test_ key.", file=sys.stderr)
        return 2
    Handler.secret = secret
    Handler.webhook = args.webhook
    Handler.base = f"http://127.0.0.1:{args.port}"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)  # loopback only
    print(f"Paystack mock on {Handler.base} (test mode only)", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
