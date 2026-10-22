from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_any_permission, require_permission
from ...auth.permissions import Permission as P
from ...extensions import db
from ...schemas.admin import RoleQuerySchema, RoleWriteSchema
from ...services.admin import role_admin
from ...utils.responses import success
from .._validation import load_body, load_query

# Account managers need to read roles to assign them; changing roles needs roles.manage.
ROLE_READ = (P.ROLES_MANAGE, P.ROLES_ASSIGN, P.USERS_VIEW)


class RoleListResource(Resource):
    @require_any_permission(*ROLE_READ)
    def get(self):
        args = load_query(RoleQuerySchema())
        items = role_admin.list_roles(include_inactive=args["include_inactive"])
        return success(items, {"total": len(items)})

    @require_permission(P.ROLES_MANAGE)
    def post(self):
        role = role_admin.create_role(load_body(RoleWriteSchema()), current_user)
        db.session.commit()
        return success(role_admin.role_detail(role), status=201)


class RoleResource(Resource):
    @require_any_permission(*ROLE_READ)
    def get(self, role_id: int):
        return success(role_admin.role_detail(role_admin.get_role(role_id)))

    @require_permission(P.ROLES_MANAGE)
    def patch(self, role_id: int):
        role = role_admin.get_role(role_id)
        role_admin.update_role(role, load_body(RoleWriteSchema(), partial=True), current_user)
        db.session.commit()
        return success(role_admin.role_detail(role))

    @require_permission(P.ROLES_MANAGE)
    def delete(self, role_id: int):
        role_admin.delete_role(role_admin.get_role(role_id), current_user)
        db.session.commit()
        return success({"deleted": True})


class PermissionListResource(Resource):
    @require_any_permission(*ROLE_READ)
    def get(self):
        return success(role_admin.permission_catalogue())
