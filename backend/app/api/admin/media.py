from flask import request
from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...schemas.admin import MediaQuerySchema, MediaUpdateSchema
from ...services.admin import media_admin
from ...utils.errors import ValidationError
from ...utils.responses import success
from .._validation import load_body, load_query

_META_FIELDS = ("alt_text", "title", "caption", "credit", "source_url", "filename")


def _uploaded_file():
    upload = request.files.get("file")
    if upload is None:
        raise ValidationError("Choose an image to upload.", details={"file": ["Required."]})
    data = upload.read()
    return data, upload.filename or ""


def _commit(written: media_admin.Written) -> None:
    """Commit, or remove every file written during this request if anything fails."""
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        written.cleanup()
        raise


class MediaListResource(Resource):
    @require_permission(P.MEDIA_VIEW)
    def get(self):
        items, pagination = media_admin.list_media(load_query(MediaQuerySchema()))
        return success(items, {"pagination": pagination})

    @require_permission(P.MEDIA_UPLOAD)
    def post(self):
        data, filename = _uploaded_file()
        meta = {k: request.form[k] for k in _META_FIELDS if k in request.form}
        written = media_admin.Written()
        try:
            asset, created = media_admin.upload(data, filename, meta, current_user, written)
        except Exception:
            db.session.rollback()
            written.cleanup()
            raise
        _commit(written)
        body = media_admin.asset_detail(asset)
        return success({**body, "duplicate": not created}, status=201 if created else 200)


class MediaStatsResource(Resource):
    @require_permission(P.MEDIA_VIEW)
    def get(self):
        return success(media_admin.storage_stats())


class MediaResource(Resource):
    @require_permission(P.MEDIA_VIEW)
    def get(self, media_id: int):
        return success(media_admin.asset_detail(media_admin.get_asset(media_id)))

    @require_permission(P.MEDIA_EDIT)
    def patch(self, media_id: int):
        asset = media_admin.get_asset(media_id)
        written = media_admin.Written()
        try:
            media_admin.update_metadata(
                asset, load_body(MediaUpdateSchema(), partial=True), current_user, written
            )
        except Exception:
            db.session.rollback()
            written.cleanup()
            raise
        _commit(written)
        return success(media_admin.asset_detail(asset))

    @require_permission(P.MEDIA_DELETE)
    def delete(self, media_id: int):
        keys = media_admin.delete(media_admin.get_asset(media_id), current_user)
        db.session.commit()
        media_admin.remove_files(keys)  # only after the record is gone
        return success({"deleted": True})


class MediaReplaceResource(Resource):
    @require_permission(P.MEDIA_REPLACE)
    def post(self, media_id: int):
        asset = media_admin.get_asset(media_id)
        data, filename = _uploaded_file()
        written = media_admin.Written()
        try:
            _, changed = media_admin.replace(asset, data, filename, current_user, written)
        except Exception:
            db.session.rollback()
            written.cleanup()
            raise
        _commit(written)
        return success({**media_admin.asset_detail(asset), "changed": changed})


def _state_action(name):
    class MediaStateResource(Resource):
        @require_permission(P.MEDIA_DELETE)
        def post(self, media_id: int):
            asset = getattr(media_admin, name)(media_admin.get_asset(media_id), current_user)
            db.session.commit()
            return success(media_admin.asset_detail(asset))

    MediaStateResource.__name__ = f"Media{name.capitalize()}Resource"
    return MediaStateResource


MediaArchiveResource = _state_action("archive")
MediaRestoreResource = _state_action("restore")
