"""Keep ``flask deploy check`` working when the application itself can't start.

The deploy command is registered by ``create_app``. If start-up fails (a setting that
``ProductionConfig.validate`` refuses, or an extension that can't initialise, such as a
Redis rate-limit store without the ``redis`` client), the Flask CLI used to print a
traceback to stderr, nothing to stdout, and exit 1, which the preflight contract reads
as "warnings only". ``wsgi.py`` uses this factory for ``deploy check`` only, so the
check reports those problems as errors (JSON, exit 2) and never prints secret values.
Every other entry point (Gunicorn, other ``flask`` commands) still refuses to start.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from flask import Flask

ERROR = "error"
_SECRET_NAME = re.compile(r"SECRET|PASSWORD|TOKEN|_KEY$|DATABASE_URL|_URI$|_URL$")
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/@\s]+@", re.I)


def is_deploy_check(argv: Sequence[str]) -> bool:
    """True for ``flask ... deploy check ...`` (Gunicorn never runs with these args)."""
    args = list(argv[1:])
    return any(a == "deploy" and b == "check" for a, b in zip(args, args[1:], strict=False))


def safe_error(exc: BaseException) -> str:
    """The exception type and message with credentials and secret settings removed."""
    message = _URL_CREDENTIALS.sub(r"\g<scheme>***@", str(exc))
    for name, value in os.environ.items():
        if len(value) >= 4 and _SECRET_NAME.search(name):
            message = message.replace(value, "***")
    message = " ".join(message.split())[:300]
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _result(check: str, message: str) -> dict[str, str]:
    return {"check": check, "level": ERROR, "message": message}


def create_preflight_app() -> Flask:
    """The normal app when it starts; otherwise an app that reports why it can't."""
    from . import create_app
    from .config import get_config

    startup: list[dict[str, str]] = []
    try:
        config = get_config(None)
        problems = config.problems() if hasattr(config, "problems") else []
    except Exception as exc:  # e.g. an unknown FLASK_CONFIG
        config, problems = None, []
        startup.append(_result("startup", f"Configuration can't be loaded: {safe_error(exc)}"))
    for problem in problems:
        startup.append(
            _result(problem.split(" ", 1)[0], f"{problem}: the application refuses to start.")
        )
    app = None
    if config is not None:
        try:
            # Same app Gunicorn builds; validation problems are reported above instead.
            app = create_app(validate=False)
        except Exception as exc:  # e.g. a Flask extension that can't initialise
            startup.append(_result("startup", f"The application can't start: {safe_error(exc)}"))
    if app is None:
        app = _minimal_app(config)
    app.config["DEPLOY_STARTUP_RESULTS"] = startup
    return app


def _minimal_app(config) -> Flask:
    """Settings and the deploy command only, without extensions (they failed to start)."""
    from .cli import deploy_cli
    from .config import INSTANCE_DIR

    app = Flask("app", instance_path=str(INSTANCE_DIR))
    if config is not None:
        app.config.from_object(config)
        app.config["ENV_NAME"] = config.__name__.removesuffix("Config").lower()
    app.config["DEPLOY_APP_UNAVAILABLE"] = True
    app.cli.add_command(deploy_cli)
    return app
