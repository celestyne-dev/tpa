import pytest

from app import create_app
from app.auth.passwords import hash_password
from app.auth.roles import set_user_roles, sync_roles
from app.extensions import db, limiter
from app.models import User
from app.services.mail import MemoryBackend
from app.services.seed_service import seed_cms_defaults, seed_sample_content

PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        "testing",
        {
            "MEDIA_ROOT": str(tmp_path / "media"),
            "PRODUCT_FILES_ROOT": str(tmp_path / "product-files"),
            "UPLOAD_TEMP_ROOT": str(tmp_path / "tmp-uploads"),
            "PRODUCT_FILES_MIN_FREE_MB": 0,
            "PUBLISH_RELEASES_DIR": str(tmp_path / "site" / "releases"),
            "PUBLISH_CURRENT_LINK": str(tmp_path / "site" / "current"),
        },
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        sync_roles()
        db.session.commit()
    limiter.reset()
    MemoryBackend.outbox.clear()
    yield app
    with app.app_context():
        db.session.remove()
        if db.engine.dialect.name == "sqlite":
            # Entitlement rows reference each other (bundles) with ON DELETE RESTRICT,
            # which SQLite enforces while dropping a populated table.
            with db.engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def seeded(app):
    with app.app_context():
        seed_sample_content()
        seed_cms_defaults()
        db.session.commit()
    return app


def make_user(app, email, roles, *, password=PASSWORD, status="active", name=None):
    with app.app_context():
        user = User(
            email=email.lower(),
            display_name=name or email.split("@")[0],
            password_hash=hash_password(password),
            status=status,
        )
        db.session.add(user)
        db.session.flush()
        set_user_roles(user, roles, assigned_by=None)
        db.session.commit()
        return user.id


def login(client, email, password=PASSWORD):
    return client.post("/api/v1/admin/auth/login", json={"email": email, "password": password})


def csrf(client, kind="access"):
    cookie = client.get_cookie(f"csrf_{kind}_token")
    return {"X-CSRF-TOKEN": cookie.value if cookie else ""}


@pytest.fixture()
def admin_factory(app):
    """Create a user with the given roles and return a logged-in test client."""

    def factory(roles, email=None):
        email = email or f"{'-'.join(roles) or 'none'}@example.org"
        make_user(app, email, roles)
        c = app.test_client()
        res = login(c, email)
        assert res.status_code == 200, res.get_json()
        return c

    return factory


class Api:
    """Small helper that sends CSRF headers for mutations."""

    def __init__(self, client):
        self.c = client

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None):
        return self.c.post(url, json=json if json is not None else {}, headers=csrf(self.c))

    def patch(self, url, json=None):
        return self.c.patch(url, json=json or {}, headers=csrf(self.c))

    def put(self, url, json=None):
        return self.c.put(url, json=json or {}, headers=csrf(self.c))

    def delete(self, url):
        return self.c.delete(url, headers=csrf(self.c))

    def upload(self, url, data: bytes, filename="photo.jpg", **form):
        import io

        payload = {"file": (io.BytesIO(data), filename), **form}
        return self.c.post(
            url, data=payload, headers=csrf(self.c), content_type="multipart/form-data"
        )


@pytest.fixture()
def as_role(admin_factory):
    def factory(*roles, email=None):
        return Api(admin_factory(list(roles), email=email))

    return factory


# ---- image fixtures ------------------------------------------------------------------


def make_photo(width=1800, height=1200, *, fmt="JPEG", exif_orientation=None, gps=False, seed=1):
    """A photo-like image (smooth gradients plus fine noise) as encoded bytes."""
    import io
    import random

    from PIL import Image, ImageDraw, ImageFilter

    rnd = random.Random(seed)
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / height
        draw.line([(0, y), (width, y)], fill=(int(40 + 160 * t), int(90 + 80 * (1 - t)), 170))
    for _ in range(60):
        x, y, r = rnd.randrange(width), rnd.randrange(height), rnd.randrange(20, 200)
        color = (rnd.randrange(255), rnd.randrange(255), rnd.randrange(255))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    img = img.filter(ImageFilter.GaussianBlur(3))
    noise = Image.effect_noise((width, height), 18).convert("RGB")
    img = Image.blend(img, noise, 0.08)
    exif = Image.Exif()
    if exif_orientation:
        exif[0x0112] = exif_orientation
    if gps:
        exif[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0), 3: "W", 4: (0.0, 7.0, 0.0)}
        exif[0x010F] = "SecretCam"
    buf = io.BytesIO()
    kwargs = {"exif": exif.tobytes()} if (exif_orientation or gps) else {}
    img.save(buf, fmt, quality=95, **kwargs)
    return buf.getvalue()


def make_png(width=600, height=400, *, alpha=False, flat=False):
    import io

    from PIL import Image, ImageDraw

    mode = "RGBA" if alpha else "RGB"
    img = Image.new(mode, (width, height), (255, 255, 255, 0) if alpha else (250, 248, 240))
    draw = ImageDraw.Draw(img)
    if flat:
        draw.rectangle([20, 20, width - 20, height // 2], fill=(30, 60, 50, 255))
        draw.text((40, height // 2 + 20), "Think Positive Always", fill=(0, 0, 0, 255))
    else:
        for x in range(0, width, 7):
            draw.line([(x, 0), (width - x, height)], fill=(x % 255, 120, 200, 200), width=3)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def png_header_only(width, height):
    """A PNG whose header claims huge dimensions (decompression-bomb probe)."""
    import struct
    import zlib

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"\x00" * 64)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# ---- commerce fixtures -----------------------------------------------------------------

TEST_SECRET = "sk_test_not_a_real_key_0123456789"


class FakePaystack:
    """In-memory Paystack API used by the real PaystackProvider code (no network, no charges).

    Only ``_request`` is replaced, so request building, response parsing, signature
    verification and event parsing all run through the production provider class.
    """

    def __init__(self, app):
        from app.payments.paystack import PaystackProvider

        with app.app_context():
            self.provider = PaystackProvider(secret_key=TEST_SECRET)
        self.provider._request = self._request
        self.transactions = {}
        self.refunds = {}
        self.plans = {}
        self.subscriptions = {}
        self.fail_initialize = False
        self.fail_verify = False
        self.fail_disable = False
        self.fail_enable = False
        self.calls = []
        self._next_id = 5000

    def _id(self):
        self._next_id += 1
        return self._next_id

    def _request(self, method, path, body=None):
        from app.payments.base import ProviderError

        self.calls.append((method, path, body))
        if path == "/transaction/initialize":
            if self.fail_initialize:
                raise ProviderError("Paystack: Currency not supported by merchant")
            ref = body["reference"]
            self.transactions[ref] = {
                "id": self._id(),
                "reference": ref,
                "amount": int(body["amount"]),
                "currency": body["currency"],
                # What Paystack reports for an initialised transaction nobody has paid yet.
                "status": "abandoned",
                "domain": "test",
                "channel": "card",
                "paid_at": None,
                "email": body["email"],
            }
            if body.get("plan"):  # subscription checkout: Paystack charges the plan amount
                plan = self.plans[body["plan"]]
                self.transactions[ref].update(
                    amount=plan["amount"],
                    plan=body["plan"],
                    customer={"customer_code": f"CUS_{abs(hash(body['email'])) % 10**8}"},
                )
            return {
                "authorization_url": f"https://checkout.paystack.com/{ref.lower()}",
                "access_code": f"ac_{ref.lower()}",
                "reference": ref,
            }
        if path.startswith("/transaction/verify/"):
            if self.fail_verify:
                raise ProviderError("Paystack could not be reached. Please try again.")
            ref = path.rsplit("/", 1)[1]
            if ref not in self.transactions:
                raise ProviderError("Paystack: Transaction reference not found")
            return dict(self.transactions[ref])
        if path == "/plan":
            code = f"PLN_{self._id()}"
            self.plans[code] = {
                "plan_code": code,
                "name": body["name"],
                "amount": int(body["amount"]),
                "currency": body["currency"],
                "interval": body["interval"],
                "domain": "test",
            }
            return dict(self.plans[code])
        if path.startswith("/plan/"):
            code = path.rsplit("/", 1)[1]
            if code not in self.plans:
                raise ProviderError("Paystack: Plan not found")
            return dict(self.plans[code])
        if path in ("/subscription/disable", "/subscription/enable"):
            sub = self.subscriptions.get(body["code"])
            if sub is None or body["token"] != sub["email_token"]:
                raise ProviderError("Paystack: Subscription not found")
            if path.endswith("enable"):
                if self.fail_enable:
                    raise ProviderError("Paystack: Subscription cannot be enabled")
                sub["status"] = "active"
            else:
                if self.fail_disable:
                    raise ProviderError("Paystack could not be reached. Please try again.")
                sub["status"] = "non-renewing"
            return {}
        if path.startswith("/subscription/") and path.endswith("/manage/link"):
            code = path.split("/")[2]
            if code not in self.subscriptions:
                raise ProviderError("Paystack: Subscription not found")
            return {"link": f"https://paystack.com/manage/subscriptions/{code.lower()}?t=x"}
        if path.startswith("/subscription/"):
            code = path.rsplit("/", 1)[1]
            if code not in self.subscriptions:
                raise ProviderError("Paystack: Subscription not found")
            return dict(self.subscriptions[code])
        if path == "/refund":
            refund = {
                "id": self._id(),
                "status": "pending",
                "amount": int(body["amount"]),
                "currency": body["currency"],
                "transaction": body["transaction"],
            }
            self.refunds[str(refund["id"])] = refund
            return dict(refund)
        if path.startswith("/refund/"):
            return dict(self.refunds[path.rsplit("/", 1)[1]])
        raise AssertionError(f"unexpected Paystack call {method} {path}")

    def pay(self, reference, *, status="success", amount=None, currency=None, domain="test"):
        tx = self.transactions[reference]
        tx.update(status=status, domain=domain, paid_at="2026-10-23T10:00:00.000Z")
        if amount is not None:
            tx["amount"] = amount
        if currency is not None:
            tx["currency"] = currency
        return tx

    def subscribe(self, reference, *, email, domain="test"):
        """What Paystack creates after a plan checkout's first successful charge."""
        tx = self.transactions[reference]
        code = f"SUB_{self._id()}"
        self.subscriptions[code] = {
            "id": self._id(),
            "subscription_code": code,
            "email_token": f"tok_{code.lower()}",
            "status": "active",
            "domain": domain,
            "plan": {"plan_code": tx["plan"]},
            "customer": {"customer_code": tx["customer"]["customer_code"], "email": email},
            "next_payment_date": "2026-11-23T10:00:00.000Z",
        }
        return dict(self.subscriptions[code])

    def charge_renewal(self, subscription_code, *, amount=None, status="success", domain="test"):
        """A recurring charge Paystack makes on its own (its own reference, no checkout)."""
        sub = self.subscriptions[subscription_code]
        plan = self.plans[sub["plan"]["plan_code"]]
        ref = f"rnw_{self._id()}"
        self.transactions[ref] = {
            "id": self._id(),
            "reference": ref,
            "amount": plan["amount"] if amount is None else amount,
            "currency": plan["currency"],
            "status": status,
            "domain": domain,
            "channel": "card",
            "paid_at": "2026-11-23T10:00:00.000Z",
            "plan": plan["plan_code"],
            "customer": {"customer_code": sub["customer"]["customer_code"]},
        }
        return dict(self.transactions[ref])

    def webhook(self, event, data, secret=TEST_SECRET):
        import hashlib
        import hmac
        import json

        raw = json.dumps({"event": event, "data": data}).encode()
        signature = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
        return raw, {"x-paystack-signature": signature, "Content-Type": "application/json"}


@pytest.fixture()
def paystack(app):
    fake = FakePaystack(app)
    app.extensions["tpa_payment_provider"] = fake.provider
    return fake


def minimal_pdf(extra=b""):
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n" + extra + b"trailer\n<< >>\n%%EOF\n"


def make_zip(entries, *, epub=False):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        if epub:
            archive.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        for name, data in entries.items():
            archive.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


class Shopper:
    """A customer browser session (cookies + customer CSRF header)."""

    def __init__(self, client):
        self.c = client

    def headers(self):
        cookie = self.c.get_cookie("tpa_customer_csrf")
        return {"X-Customer-CSRF": cookie.value if cookie else ""}

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None):
        return self.c.post(url, json=json if json is not None else {}, headers=self.headers())

    def patch(self, url, json=None):
        return self.c.patch(url, json=json or {}, headers=self.headers())

    def put(self, url, json=None):
        return self.c.put(url, json=json or {}, headers=self.headers())


def register_customer(app, email="reader@example.com", *, verify=True, test_account=True):
    from app.models import Customer

    shopper = Shopper(app.test_client())
    res = shopper.c.post(
        "/api/v1/account/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Reader",
            "accept_terms": True,
        },
    )
    assert res.status_code == 201, res.get_json()
    if verify:
        message = [m for m in MemoryBackend.outbox if m.to == email.lower()][-1]
        token = message.text.split("#token=", 1)[1].split()[0]
        assert shopper.post("/api/v1/account/verify-email", {"token": token}).status_code == 200
    with app.app_context():
        customer = db.session.scalar(db.select(Customer).where(Customer.email == email.lower()))
        customer.is_test_account = test_account
        db.session.commit()
    return shopper


def enable_test_checkout(app, currencies=("USD", "KES")):
    from app.models import SiteSetting

    with app.app_context():
        for key, value in (
            ("payments.checkout_mode", "test"),
            ("payments.currencies", list(currencies)),
        ):
            record = db.session.get(SiteSetting, key) or SiteSetting(key=key)
            record.value = value
            db.session.add(record)
        db.session.commit()
