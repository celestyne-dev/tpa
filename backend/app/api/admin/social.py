"""Admin API for Pinterest / Instagram connections, social publishing and Instagram imports.

- Connecting or disconnecting an account requires ``social.connect`` (Super Admin only).
- Creating, retrying and cancelling posts requires ``social.publish``; importing from
  Instagram also requires ``media.upload``.
- Viewing accounts, boards and posts requires ``social.view``.
Tokens and client secrets are never returned.
"""

from __future__ import annotations

from flask import current_app, request
from flask_jwt_extended import current_user
from flask_restful import Resource

from ...auth.decorators import require_permission
from ...auth.permissions import Permission as P
from ...extensions import db, limiter
from ...services.admin import media_admin
from ...services.social import accounts, imports, pinterest, posts
from ...services.social.http import SocialError
from ...utils.errors import ValidationError
from ...utils.responses import success

_limit = [limiter.limit(lambda: current_app.config["RATELIMIT_SENSITIVE"])]


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("Send a JSON object in the request body.")
    return data


def _page_args() -> dict:
    args = {k: v for k, v in request.args.items() if len(v) <= 40}
    for name, default, high in (("page", 1, 10000), ("page_size", 25, 100)):
        raw = args.get(name)
        try:
            args[name] = max(1, min(high, int(raw))) if raw else default
        except ValueError:
            raise ValidationError(details={name: ["Must be a number."]}) from None
    return args


class SocialAccountsResource(Resource):
    @require_permission(P.SOCIAL_VIEW)
    def get(self):
        return success(accounts.all_accounts())


class SocialConnectResource(Resource):
    decorators = _limit

    @require_permission(P.SOCIAL_CONNECT)
    def post(self, platform: str):
        return success(accounts.start_connect(accounts.check_platform(platform), current_user))


class SocialCallbackResource(Resource):
    decorators = _limit

    @require_permission(P.SOCIAL_CONNECT)
    def post(self, platform: str):
        body = _body()
        if body.get("error"):
            reason = str(body.get("error_description") or body["error"])[:200]
            raise ValidationError(f"The connection was not approved on the platform: {reason}")
        result = accounts.complete_connect(
            accounts.check_platform(platform),
            str(body.get("code") or ""),
            str(body.get("state") or ""),
            current_user,
        )
        db.session.commit()
        return success(result)


class SocialAccountResource(Resource):
    @require_permission(P.SOCIAL_CONNECT)
    def delete(self, platform: str):
        result = accounts.disconnect(accounts.check_platform(platform), current_user)
        db.session.commit()
        return success(result)


class PinterestBoardsResource(Resource):
    @require_permission(P.SOCIAL_VIEW)
    def get(self):
        try:
            _, token = accounts.access_token("pinterest")
            boards = pinterest.boards(token)
        except SocialError as exc:
            db.session.commit()  # keep the account's error state
            raise ValidationError(
                exc.message, details={"reconnect": True} if exc.reconnect else None
            ) from None
        db.session.commit()
        return success(boards)


class SocialPostListResource(Resource):
    @require_permission(P.SOCIAL_VIEW)
    def get(self):
        args = _page_args()
        items, total = posts.list_posts(args)
        return success(
            items, {"total": total, "page": args["page"], "page_size": args["page_size"]}
        )

    @require_permission(P.SOCIAL_PUBLISH)
    def post(self):
        body = _body()
        post = posts.create(body, current_user)
        if body.get("scheduled_at"):
            db.session.commit()
        else:
            post = posts.publish_now(post)
        return success(posts.post_dict(post), status=201)


class SocialPostResource(Resource):
    @require_permission(P.SOCIAL_VIEW)
    def get(self, post_id: int):
        return success(posts.post_dict(posts.get_post(post_id)))


class SocialPostRetryResource(Resource):
    @require_permission(P.SOCIAL_PUBLISH)
    def post(self, post_id: int):
        post = posts.retry(posts.get_post(post_id), current_user)
        post = posts.publish_now(post)
        return success(posts.post_dict(post))


class SocialPostCancelResource(Resource):
    @require_permission(P.SOCIAL_PUBLISH)
    def post(self, post_id: int):
        post = posts.cancel(posts.get_post(post_id), current_user)
        db.session.commit()
        return success(posts.post_dict(post))


class InstagramMediaResource(Resource):
    @require_permission(P.SOCIAL_PUBLISH, P.MEDIA_UPLOAD)
    def get(self):
        after = request.args.get("after") or None
        if after and len(after) > 500:
            raise ValidationError(details={"after": ["Invalid cursor."]})
        return success(imports.list_media(after))


class InstagramImportResource(Resource):
    decorators = [limiter.limit("30 per hour")]

    @require_permission(P.SOCIAL_PUBLISH, P.MEDIA_UPLOAD)
    def post(self):
        asset, created = imports.import_media(_body(), current_user)
        return success(
            {**media_admin.asset_detail(asset), "duplicate": not created},
            status=201 if created else 200,
        )


SOCIAL_ROUTES = [
    (SocialAccountsResource, "/admin/social/accounts"),
    (SocialConnectResource, "/admin/social/<string:platform>/connect"),
    (SocialCallbackResource, "/admin/social/<string:platform>/callback"),
    (SocialAccountResource, "/admin/social/<string:platform>/account"),
    (PinterestBoardsResource, "/admin/social/pinterest/boards"),
    (SocialPostListResource, "/admin/social/posts"),
    (SocialPostResource, "/admin/social/posts/<int:post_id>"),
    (SocialPostRetryResource, "/admin/social/posts/<int:post_id>/retry"),
    (SocialPostCancelResource, "/admin/social/posts/<int:post_id>/cancel"),
    (InstagramMediaResource, "/admin/social/instagram/media"),
    (InstagramImportResource, "/admin/social/instagram/import"),
]
