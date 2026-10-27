"""Storage health for administrators (/api/v1/admin/storage)."""

from flask import request
from flask_restful import Resource

from ...auth.decorators import require_permission
from ...auth.permissions import Permission as P
from ...services import storage_health
from ...utils.responses import success


class StorageHealthResource(Resource):
    @require_permission(P.STORAGE_VIEW)
    def get(self):
        quick = request.args.get("quick") in ("1", "true")
        return success(storage_health.report(integrity=not quick))


class UploadErrorListResource(Resource):
    @require_permission(P.STORAGE_VIEW)
    def get(self):
        return success(storage_health.upload_errors())


STORAGE_ROUTES = [
    (StorageHealthResource, "/admin/storage"),
    (UploadErrorListResource, "/admin/storage/upload-errors"),
]
