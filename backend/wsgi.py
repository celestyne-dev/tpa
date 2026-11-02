"""WSGI entry point.

Development:  flask --app wsgi run --debug
Production:   gunicorn --workers 3 --bind 127.0.0.1:8000 wsgi:app
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# FLASK_SKIP_DOTENV=1 (Flask's own switch) runs with the process environment only.
if os.environ.get("FLASK_SKIP_DOTENV", "").lower() not in {"1", "true", "yes"}:
    load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402
from app.preflight import create_preflight_app, is_deploy_check  # noqa: E402

# `flask deploy check` must report start-up problems instead of crashing before it runs;
# everything else (Gunicorn included) refuses to start on them.
app = create_preflight_app() if is_deploy_check(sys.argv) else create_app()
