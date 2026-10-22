from flask import Response
from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_any_permission, require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...schemas.admin import (
    JobQuerySchema,
    RedirectImportSchema,
    RedirectQuerySchema,
    RedirectWriteSchema,
)
from ...services import publication_service, publishing, redirect_service, seo_service
from ...utils.responses import success
from .._validation import load_body, load_query


class SeoOverviewResource(Resource):
    @require_any_permission(P.SEO_VIEW, P.SEO_MANAGE)
    def get(self):
        return success(seo_service.overview())


class RedirectListResource(Resource):
    @require_any_permission(P.REDIRECTS_MANAGE, P.SEO_VIEW)
    def get(self):
        items, pagination = redirect_service.list_redirects(load_query(RedirectQuerySchema()))
        return success(items, {"pagination": pagination})

    @require_permission(P.REDIRECTS_MANAGE)
    def post(self):
        r = redirect_service.create_redirect(load_body(RedirectWriteSchema()), current_user)
        db.session.commit()
        return success(redirect_service.redirect_dict(r), status=201)


class RedirectResource(Resource):
    @require_permission(P.REDIRECTS_MANAGE)
    def patch(self, redirect_id: int):
        r = redirect_service.get_redirect(redirect_id)
        redirect_service.update_redirect(
            r, load_body(RedirectWriteSchema(), partial=True), current_user
        )
        db.session.commit()
        return success(redirect_service.redirect_dict(r))

    @require_permission(P.REDIRECTS_MANAGE)
    def delete(self, redirect_id: int):
        redirect_service.delete_redirect(redirect_service.get_redirect(redirect_id), current_user)
        db.session.commit()
        return success({"deleted": True})


class RedirectImportResource(Resource):
    @require_permission(P.REDIRECTS_MANAGE)
    def post(self):
        args = load_body(RedirectImportSchema())
        rows = redirect_service.parse_csv(args["csv"])
        result = redirect_service.import_rows(rows, current_user, dry_run=args["dry_run"])
        if args["dry_run"]:
            db.session.rollback()
        else:
            db.session.commit()
        return success(result)


class RedirectExportResource(Resource):
    @require_any_permission(P.REDIRECTS_MANAGE, P.SEO_VIEW)
    def get(self):
        return Response(
            redirect_service.export_csv(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="tpa-redirects.csv"',
                "Cache-Control": "no-store",
            },
        )


class PublishingStatusResource(Resource):
    @require_any_permission(
        P.PUBLISHING_VIEW,
        P.ARTICLES_VIEW,
        P.ARTICLES_CREATE,
        P.ARTICLES_EDIT_OWN,
        P.ARTICLES_EDIT_ANY,
    )
    def get(self):
        return success(publication_service.status())


class PublishJobListResource(Resource):
    @require_permission(P.PUBLISHING_VIEW)
    def get(self):
        items, pagination = publishing.list_jobs(load_query(JobQuerySchema()))
        return success(items, {"pagination": pagination, "summary": publishing.summary()})

    @require_permission(P.PUBLISHING_MANAGE)
    def post(self):
        job = publishing.request_build("manual_request", current_user, trigger="manual")
        db.session.commit()
        return success(publishing.job_dict(job), status=201)


class PublishJobResource(Resource):
    @require_permission(P.PUBLISHING_VIEW)
    def get(self, job_id: int):
        return success(publishing.job_dict(publishing.get_job(job_id)))


class PublishJobRetryResource(Resource):
    @require_permission(P.PUBLISHING_MANAGE)
    def post(self, job_id: int):
        job = publishing.retry(publishing.get_job(job_id), current_user)
        db.session.commit()
        return success(publishing.job_dict(job), status=201)


class PublishJobCancelResource(Resource):
    @require_permission(P.PUBLISHING_MANAGE)
    def post(self, job_id: int):
        job = publishing.cancel(publishing.get_job(job_id), current_user)
        db.session.commit()
        return success(publishing.job_dict(job))
