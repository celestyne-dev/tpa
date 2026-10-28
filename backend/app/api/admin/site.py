from flask_jwt_extended import current_user
from flask_restful import Resource
from sqlalchemy import select

from ...auth.decorators import require_any_permission, require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...models import AuditLog, User
from ...schemas.admin import (
    AuditQuerySchema,
    InvitationCreateSchema,
    InvitationQuerySchema,
    NavigationWriteSchema,
    ResetPasswordSchema,
    SettingsQuerySchema,
    SettingsWriteSchema,
    UserCreateSchema,
    UserQuerySchema,
    UserUpdateSchema,
)
from ...services import navigation_service, settings_service
from ...services.admin import account_tokens, dashboard, user_admin
from ...services.admin.auth_service import user_payload
from ...services.admin.common import get_or_404, paginate
from ...utils.responses import success
from .._validation import load_body, load_query


class DashboardResource(Resource):
    @require_permission(P.DASHBOARD_VIEW)
    def get(self):
        return success(dashboard.overview(current_user))


class AnalyticsResource(Resource):
    @require_permission(P.ANALYTICS_VIEW)
    def get(self):
        return success(dashboard.analytics_summary())


class AnalyticsTrafficResource(Resource):
    """Website traffic and content performance (Batch 11.1); reuses ``analytics.view``."""

    @require_permission(P.ANALYTICS_VIEW)
    def get(self):
        from flask import request

        from ...services.analytics.reports import traffic_report

        args = {k: request.args.get(k) for k in ("range", "date_from", "date_to", "granularity")}
        return success(traffic_report(args))


_COMMERCE_ARGS = ("range", "date_from", "date_to", "granularity", "mode", "currency")


class CommerceAnalyticsResource(Resource):
    """Commerce and revenue analytics (Batch 11.2): aggregates only, needs ``finance.view``."""

    @require_permission(P.FINANCE_VIEW)
    def get(self):
        from flask import request

        from ...services.analytics.commerce import commerce_report

        return success(commerce_report({k: request.args.get(k) for k in _COMMERCE_ARGS}))


class CommerceAnalyticsExportResource(Resource):
    @require_permission(P.FINANCE_EXPORT)
    def get(self):
        from flask import Response, request

        from ...services import audit_service
        from ...services.analytics.commerce import export_csv

        body = export_csv({k: request.args.get(k) for k in _COMMERCE_ARGS})
        audit_service.record("finance.commerce_analytics_exported", "finance", actor=current_user)
        db.session.commit()
        response = Response(body, mimetype="text/csv")
        response.headers["Content-Disposition"] = 'attachment; filename="commerce-analytics.csv"'
        return response


# ---- navigation & settings ------------------------------------------------------


class NavigationResource(Resource):
    @require_permission(P.NAVIGATION_MANAGE)
    def get(self):
        return success(navigation_service.admin_menus())


class NavigationMenuResource(Resource):
    @require_permission(P.NAVIGATION_MANAGE)
    def put(self, menu_key: str):
        items = load_body(NavigationWriteSchema())["items"]
        navigation_service.replace_menu(menu_key, items, current_user)
        db.session.commit()
        menu = next(m for m in navigation_service.admin_menus() if m["key"] == menu_key)
        return success(menu)


def _groups_filter() -> set[str] | None:
    groups = load_query(SettingsQuerySchema())["groups"]
    return {g.strip() for g in groups.split(",") if g.strip()} if groups else None


class SettingsResource(Resource):
    @require_any_permission(*settings_service.SETTING_PERMISSIONS)
    def get(self):
        return success(settings_service.admin_payload(current_user, _groups_filter()))

    @require_any_permission(*settings_service.SETTING_PERMISSIONS)
    def patch(self):
        result = settings_service.update_values(
            load_body(SettingsWriteSchema())["values"], current_user
        )
        db.session.commit()
        return success({**settings_service.admin_payload(current_user, _groups_filter()), **result})


# ---- users, roles, audit ----------------------------------------------------------


class UserListResource(Resource):
    @require_permission(P.USERS_VIEW)
    def get(self):
        users = user_admin.list_users(load_query(UserQuerySchema()))
        return success(users, {"total": len(users)})

    @require_permission(P.USERS_MANAGE)
    def post(self):
        user = user_admin.create_user(load_body(UserCreateSchema()), current_user)
        db.session.commit()
        return success(user_payload(user), status=201)


class UserResource(Resource):
    @require_permission(P.USERS_VIEW)
    def get(self, user_id: int):
        return success(user_admin.user_detail(user_admin.get_user(user_id)))

    @require_permission(P.USERS_MANAGE)
    def patch(self, user_id: int):
        user = user_admin.get_user(user_id)
        user_admin.update_user(user, load_body(UserUpdateSchema(), partial=True), current_user)
        db.session.commit()
        return success(user_payload(user))


class UserPasswordResource(Resource):
    @require_permission(P.USERS_MANAGE)
    def post(self, user_id: int):
        user = get_or_404(User, user_id, "User")
        user_admin.reset_password(user, load_body(ResetPasswordSchema())["password"], current_user)
        db.session.commit()
        return success({"reset": True})


class UserPasswordResetLinkResource(Resource):
    @require_permission(P.USERS_MANAGE)
    def post(self, user_id: int):
        user = user_admin.get_user(user_id)
        record = account_tokens.request_password_reset(user, current_user)
        db.session.commit()
        return success(account_tokens.token_dict(record), status=201)


class InvitationListResource(Resource):
    @require_permission(P.USERS_VIEW)
    def get(self):
        args = load_query(InvitationQuerySchema())
        items = account_tokens.list_invitations(args["status"])
        return success(items, {"total": len(items)})

    @require_permission(P.USERS_MANAGE)
    def post(self):
        invite = account_tokens.create_invitation(load_body(InvitationCreateSchema()), current_user)
        db.session.commit()
        return success(account_tokens.token_dict(invite), status=201)


class InvitationRevokeResource(Resource):
    @require_permission(P.USERS_MANAGE)
    def post(self, invite_id: int):
        invite = account_tokens.revoke_invitation(
            account_tokens.get_invitation(invite_id), current_user
        )
        db.session.commit()
        return success(account_tokens.token_dict(invite))


class InvitationResendResource(Resource):
    @require_permission(P.USERS_MANAGE)
    def post(self, invite_id: int):
        invite = account_tokens.resend_invitation(
            account_tokens.get_invitation(invite_id), current_user
        )
        db.session.commit()
        return success(account_tokens.token_dict(invite))


class AuditLogResource(Resource):
    @require_permission(P.AUDIT_VIEW)
    def get(self):
        args = load_query(AuditQuerySchema())
        stmt = select(AuditLog)
        if args["action"]:
            stmt = stmt.where(AuditLog.action.startswith(args["action"]))
        if args["resource_type"]:
            stmt = stmt.where(AuditLog.resource_type == args["resource_type"])
        if args["actor_id"]:
            stmt = stmt.where(AuditLog.actor_id == args["actor_id"])
        stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        items, pagination = paginate(stmt, args["page"], args["page_size"])
        return success([dashboard.audit_entry(e) for e in items], {"pagination": pagination})
