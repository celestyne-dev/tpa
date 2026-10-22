import pytest

from app import create_app
from app.auth.passwords import hash_password
from app.auth.roles import set_user_roles, sync_roles
from app.extensions import db, limiter
from app.models import User
from app.services.seed_service import seed_cms_defaults, seed_sample_content

PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        db.drop_all()
        db.create_all()
        sync_roles()
        db.session.commit()
    limiter.reset()
    yield app
    with app.app_context():
        db.session.remove()
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


@pytest.fixture()
def as_role(admin_factory):
    def factory(*roles, email=None):
        return Api(admin_factory(list(roles), email=email))

    return factory
