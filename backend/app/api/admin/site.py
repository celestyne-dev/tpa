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
    PageWriteSchema,
    ReorderSchema,
    ResetPasswordSchema,
    SectionCreateSchema,
    SectionWriteSchema,
    SettingsWriteSchema,
    UserCreateSchema,
    UserQuerySchema,
    UserUpdateSchema,
)
from ...services import navigation_service, settings_service
from ...services.admin import account_tokens, dashboard, page_admin, user_admin
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


# ---- pages --------------------------------------------------------------------


class PageListResource(Resource):
    @require_permission(P.PAGES_VIEW)
    def get(self):
        pages = page_admin.list_pages()
        return success(pages, {"total": len(pages)})


class PageResource(Resource):
    @require_permission(P.PAGES_VIEW)
    def get(self, page_id: int):
        return success(page_admin.page_dict(page_admin.get_page(page_id), with_sections=True))

    @require_permission(P.PAGES_EDIT)
    def patch(self, page_id: int):
        page = page_admin.get_page(page_id)
        page_admin.update_page(page, load_body(PageWriteSchema(), partial=True), current_user)
        db.session.commit()
        return success(page_admin.page_dict(page, with_sections=True))


class PageSectionListResource(Resource):
    @require_permission(P.PAGES_EDIT)
    def post(self, page_id: int):
        page = page_admin.get_page(page_id)
        section = page_admin.create_section(page, load_body(SectionCreateSchema()), current_user)
        db.session.commit()
        return success(page_admin.section_dict(section), status=201)


class PageSectionResource(Resource):
    @require_permission(P.PAGES_EDIT)
    def patch(self, page_id: int, section_id: int):
        page = page_admin.get_page(page_id)
        section = page_admin.get_section(page, section_id)
        page_admin.update_section(
            section, load_body(SectionWriteSchema(), partial=True), current_user
        )
        db.session.commit()
        return success(page_admin.section_dict(section))


class PageSectionOrderResource(Resource):
    @require_permission(P.PAGES_EDIT)
    def put(self, page_id: int):
        page = page_admin.get_page(page_id)
        page_admin.reorder_sections(page, load_body(ReorderSchema())["order"], current_user)
        db.session.commit()
        return success(page_admin.page_dict(page, with_sections=True))


class SectionTypesResource(Resource):
    @require_permission(P.PAGES_VIEW)
    def get(self):
        return success(page_admin.section_types())


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


class SettingsResource(Resource):
    @require_any_permission(P.SETTINGS_MANAGE, P.SEO_MANAGE)
    def get(self):
        return success(settings_service.admin_payload(current_user))

    @require_any_permission(P.SETTINGS_MANAGE, P.SEO_MANAGE)
    def patch(self):
        result = settings_service.update_values(
            load_body(SettingsWriteSchema())["values"], current_user
        )
        db.session.commit()
        return success({**settings_service.admin_payload(current_user), **result})


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
