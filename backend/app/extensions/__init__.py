"""Flask extension instances, initialised in the application factory."""

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names keep Alembic migrations portable (SQLite batch mode, PostgreSQL).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _render_item(type_, obj, autogen_context):
    """Render custom column types as plain SQLAlchemy types so migrations stay self-contained."""
    from ..models.types import UTCDateTime

    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


db = SQLAlchemy(model_class=Base)
migrate = Migrate(render_as_batch=True, render_item=_render_item, compare_type=True)
cors = CORS()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address)
