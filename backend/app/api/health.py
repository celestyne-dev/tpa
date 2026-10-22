from flask import current_app
from flask_restful import Resource

from ..utils.responses import success


class HealthResource(Resource):
    def get(self):
        return success(
            {
                "status": "ok",
                "service": "tpa-api",
                "version": "v1",
                "environment": current_app.config.get("ENV_NAME", "unknown"),
            }
        )
