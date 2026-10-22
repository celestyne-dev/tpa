"""WSGI entry point.

Development:  flask --app wsgi run --debug
Production:   gunicorn --workers 3 --bind 127.0.0.1:8000 wsgi:app
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from app import create_app  # noqa: E402

app = create_app()
