"""Pins and Instagram feed posts made from Media Library images.

Lifecycle: ``scheduled`` -> ``publishing`` -> ``published``. A definite refusal ends in
``failed`` (an administrator can retry it); a transient failure (rate limit, outage) is
retried automatically with backoff; an attempt whose outcome is unknown (timeout, 5xx while
creating) moves to ``checking`` and the platform is searched for the post before anything
is sent again, so a retry never creates a duplicate. ``cancelled`` posts are never sent.

Posts are only ever created by an administrator (publish now, or a time they choose);
publishing an article or a quote collection on TPA never posts to a platform by itself.
"""

from __future__ import annotations

import re
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import current_app
from sqlalchemy import func, or_, select, update

from ...extensions import db
from ...models import Article, MediaAsset, SocialPost, User
from ...utils.errors import ConflictError, NotFoundError, ValidationError
from ...utils.validation import plain_text_problem
from .. import audit_service
from ..seo_service import article_url
from ..serializers import iso
from . import accounts, instagram, pinterest
from .http import SocialError

ACTIVE = ("scheduled", "publishing", "checking")
VIEWS = {
    "queue": ACTIVE,
    "published": ("published",),
    "failed": ("failed", "cancelled"),
}
MAX_ATTEMPTS = 5
STALE_PUBLISHING = timedelta(minutes=15)
CONTAINER_POLLS = 10  # Instagram: give up on a container that is not ready after ~10 runs
LIMITS = {
    "pinterest": {"title": 100, "text": 800, "alt_text": 500},
    "instagram": {"text": 2200},
}
_HASHTAG = re.compile(r"(?<!\w)#\w+")
_MENTION = re.compile(r"(?<!\w)@[\w.]+")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _site() -> str:
    return current_app.config.get("SITE_URL", "").rstrip("/")


# ---- images and destinations --------------------------------------------------------------


def _absolute(url: str) -> str:
    return (
        url
        if re.match(r"^https?://", url)
        else f"{_site()}{url if url.startswith('/') else '/' + url}"
    )


def image_url(asset: MediaAsset, platform: str) -> str:
    """Largest existing optimised rendition the platform accepts (Instagram: JPEG only)."""
    if asset.status != "active" or asset.visibility != "public":
        raise ValidationError(
            "Choose an active, public image from the Media Library.",
            details={"media_asset_id": ["This image is archived or private."]},
        )
    formats = ("jpeg",) if platform == "instagram" else ("jpeg", "png")
    from ...storage import public_url

    variants = [
        v
        for v in (asset.current_variants("responsive") or asset.current_variants())
        if v.format in formats
    ]
    width, height = asset.width, asset.height
    if variants:
        best = max(variants, key=lambda v: v.width)
        url = _absolute(public_url(best.storage_key))
        width, height = best.width, best.height
    else:
        mime = (asset.mime_type or "").lower()
        allowed = {"image/jpeg"} if platform == "instagram" else {"image/jpeg", "image/png"}
        if mime not in allowed or not asset.public_url:
            need = "a JPEG" if platform == "instagram" else "a JPEG or PNG"
            raise ValidationError(
                f"{accounts.LABELS[platform]} needs {need} version of this image, and the Media "
                "Library has none (images with transparency are kept as PNG). Upload a JPEG.",
                details={"media_asset_id": [f"No {need} rendition."]},
            )
        url = _absolute(asset.public_url)
    if platform == "instagram" and width and height and not 0.8 <= width / height <= 1.91:
        raise ValidationError(
            "Instagram feed images must be between 4:5 (portrait) and 1.91:1 (landscape). "
            "Crop this image or choose another.",
            details={"media_asset_id": ["Unsupported aspect ratio for Instagram."]},
        )
    if not url.startswith("https://"):
        raise ValidationError(
            "Images must be served from a public https:// address for the platform to fetch "
            "them (check SITE_URL / MEDIA_PUBLIC_BASE_URL).",
            details={"media_asset_id": ["Not a public https:// image address."]},
        )
    return url


def _site_host() -> str:
    return (urllib.parse.urlparse(_site()).hostname or "").lower()


def destination_problem(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return "Enter a valid address."
    host = (parsed.hostname or "").lower()
    site = _site_host()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        return "Use a full https:// address on the website."
    if host not in {site, f"www.{site}"} and f"www.{host}" != site:
        return "Pins may only link to pages on this website."
    path = parsed.path or "/"
    media_base = urllib.parse.urlparse(
        current_app.config.get("MEDIA_PUBLIC_BASE_URL", "/media")
    ).path.rstrip("/")
    if (media_base and path.startswith(media_base + "/")) or path.startswith(("/admin", "/api/")):
        return "Link to an article, quote collection or page, not to an image file or admin page."
    return None


def canonical_for(article: Article) -> str:
    return article_url(article.slug, article.content_type)


# ---- serialising --------------------------------------------------------------------------


def post_dict(post: SocialPost) -> dict[str, Any]:
    asset = post.media_asset
    article = post.article
    creator = db.session.get(User, post.created_by_id) if post.created_by_id else None
    return {
        "id": post.id,
        "platform": post.platform,
        "status": post.status,
        "media_asset": (
            {
                "id": asset.id,
                "title": asset.title or asset.filename,
                "url": asset.public_url,
                "alt_text": asset.alt_text,
            }
            if asset
            else None
        ),
        "article": (
            {
                "id": article.id,
                "title": article.title,
                "content_type": article.content_type,
                "url": canonical_for(article),
            }
            if article
            else None
        ),
        "title": post.title,
        "text": post.text,
        "alt_text": post.alt_text,
        "destination_url": post.destination_url,
        "board_id": post.board_id,
        "board_name": post.board_name,
        "scheduled_at": iso(post.scheduled_at),
        "published_at": iso(post.published_at),
        "next_attempt_at": iso(post.next_attempt_at),
        "external_id": post.external_id,
        "external_url": post.external_url,
        "attempts": post.attempts,
        "last_error": post.last_error,
        "created_by": creator.display_name if creator else None,
        "created_at": iso(post.created_at),
        "can_cancel": post.status == "scheduled",
        "can_retry": post.status == "failed",
    }


def list_posts(args: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    query = select(SocialPost)
    view = args.get("view")
    if view in VIEWS:
        query = query.where(SocialPost.status.in_(VIEWS[view]))
    if args.get("platform") in accounts.PLATFORMS:
        query = query.where(SocialPost.platform == args["platform"])
    for key in ("media_asset_id", "article_id"):
        if str(args.get(key) or "").isdigit():
            query = query.where(getattr(SocialPost, key) == int(args[key]))
    total = db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    order = (
        SocialPost.scheduled_at.asc()
        if view == "queue"
        else func.coalesce(SocialPost.published_at, SocialPost.updated_at).desc()
    )
    page, size = int(args.get("page", 1)), int(args.get("page_size", 25))
    rows = db.session.scalars(
        query.order_by(order, SocialPost.id.desc()).offset((page - 1) * size).limit(size)
    )
    return [post_dict(p) for p in rows], total


def get_post(post_id: int) -> SocialPost:
    post = db.session.get(SocialPost, post_id)
    if post is None:
        raise NotFoundError("Social post not found.")
    return post


# ---- creating -----------------------------------------------------------------------------


def _text(data: dict[str, Any], field: str, limit: int, errors: dict) -> str:
    value = data.get(field)
    value = "" if value is None else str(value).strip()
    if len(value) > limit:
        errors[field] = [f"At most {limit} characters."]
    elif value and (problem := plain_text_problem(value)):
        errors[field] = [problem]
    return value


def _when(raw: Any, errors: dict) -> datetime | None:
    if raw in (None, ""):
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        errors["scheduled_at"] = ["Use an ISO 8601 date and time."]
        return None
    value = _aware(value)
    if value < _now() - timedelta(minutes=5):
        errors["scheduled_at"] = ["Choose a time in the future (or publish now)."]
    elif value > _now() + timedelta(days=365):
        errors["scheduled_at"] = ["Schedule at most a year ahead."]
    return value


def _board(board_id: str) -> dict[str, Any]:
    try:
        _, token = accounts.access_token("pinterest")
        boards = pinterest.boards(token)
    except SocialError as exc:
        db.session.commit()  # keep the account's error / expired state
        raise ValidationError(exc.message) from None
    for board in boards:
        if board["id"] == board_id:
            return board
    raise ValidationError(details={"board_id": ["Choose one of the account's boards."]})


def create(data: dict[str, Any], user: User) -> SocialPost:
    platform = data.get("platform")
    if platform not in accounts.PLATFORMS:
        raise ValidationError(details={"platform": ["Choose Pinterest or Instagram."]})
    account = accounts.get_account(platform)
    if account is None or account.status != "connected":
        raise ValidationError(
            f"Connect {accounts.LABELS[platform]} first (Admin › Integrations).",
            details={"platform": ["Not connected."]},
        )
    errors: dict[str, list[str]] = {}
    limits = LIMITS[platform]
    asset = None
    raw_asset = data.get("media_asset_id")
    if isinstance(raw_asset, int) and not isinstance(raw_asset, bool):
        asset = db.session.get(MediaAsset, raw_asset)
    if asset is None:
        errors["media_asset_id"] = ["Choose an image from the Media Library."]
    article = None
    raw_article = data.get("article_id")
    if raw_article not in (None, ""):
        if isinstance(raw_article, int) and not isinstance(raw_article, bool):
            article = db.session.get(Article, raw_article)
        if article is None:
            errors["article_id"] = ["Choose an article or quote collection."]
        elif article.status != "published":
            errors["article_id"] = ["Publish this article or quote collection first."]
    text = _text(data, "text", limits["text"], errors)
    title = (
        _text(data, "title", limits.get("title", 100), errors) if platform == "pinterest" else ""
    )
    alt_text = (
        _text(data, "alt_text", limits.get("alt_text", 500), errors)
        if platform == "pinterest"
        else ""
    )
    destination = None
    board = None
    if platform == "pinterest":
        if not title:
            errors.setdefault("title", ["Give the Pin a title."])
        if article is not None:
            # Pins about an article or quote collection always link to its canonical page.
            destination = canonical_for(article)
        else:
            destination = str(data.get("destination_url") or "").strip()
            if not destination:
                errors["destination_url"] = [
                    "Choose the related article or quote collection, or enter a page address."
                ]
            elif len(destination) > 2048:
                errors["destination_url"] = ["At most 2048 characters."]
            elif problem := destination_problem(destination):
                errors["destination_url"] = [problem]
        board_id = str(data.get("board_id") or "").strip()
        if not board_id or len(board_id) > 100:
            errors["board_id"] = ["Choose a board."]
    else:
        if not text:
            errors["text"] = ["Write a caption."]
        if len(_HASHTAG.findall(text)) > 30:
            errors["text"] = ["Instagram allows at most 30 hashtags."]
        elif len(_MENTION.findall(text)) > 20:
            errors["text"] = ["Instagram allows at most 20 @mentions."]
        if data.get("destination_url"):
            errors["destination_url"] = [
                "Instagram feed posts have no clickable link; mention the page in the caption "
                "or your profile link instead."
            ]
    scheduled_at = _when(data.get("scheduled_at"), errors)
    if asset is not None and "media_asset_id" not in errors:
        try:
            image_url(asset, platform)
        except ValidationError as exc:
            errors.update(exc.details or {"media_asset_id": [exc.message]})
    if errors:
        raise ValidationError("Some details need attention.", details=errors)
    if platform == "pinterest":
        board = _board(board_id)
    # One pending post per image, platform and destination: no duplicate schedules.
    same = select(SocialPost.id).where(
        SocialPost.platform == platform,
        SocialPost.media_asset_id == asset.id,
        SocialPost.status.in_(ACTIVE),
    )
    if platform == "pinterest":
        same = same.where(SocialPost.board_id == board["id"])
    if db.session.scalar(same.limit(1)) is not None:
        raise ConflictError(
            "This image is already queued for this account"
            + (" and board." if platform == "pinterest" else ".")
            + " Edit or cancel the queued post instead."
        )
    published = select(SocialPost.id).where(
        SocialPost.platform == platform,
        SocialPost.media_asset_id == asset.id,
        SocialPost.status == "published",
    )
    if platform == "pinterest":
        published = published.where(
            SocialPost.board_id == board["id"], SocialPost.destination_url == destination
        )
    if db.session.scalar(published.limit(1)) is not None and data.get("allow_repeat") is not True:
        raise ConflictError(
            "This image has already been published here. Confirm to publish it again.",
            details={"allow_repeat": ["Already published."]},
        )
    post = SocialPost(
        platform=platform,
        status="scheduled",
        media_asset_id=asset.id,
        article_id=article.id if article else None,
        title=title or None,
        text=text,
        alt_text=alt_text or None,
        destination_url=destination,
        board_id=board["id"] if board else None,
        board_name=board["name"] if board else None,
        scheduled_at=scheduled_at or _now(),
        attempts=0,
        details={},
        created_by_id=user.id,
    )
    db.session.add(post)
    db.session.flush()
    audit_service.record(
        "social.post_scheduled" if scheduled_at else "social.post_requested",
        "social_post",
        post.id,
        actor=user,
        details={
            "platform": platform,
            "media_asset_id": asset.id,
            "article_id": post.article_id,
            "destination_url": destination,
            "board": post.board_name,
            "scheduled_at": iso(post.scheduled_at),
        },
    )
    return post


def cancel(post: SocialPost, user: User) -> SocialPost:
    if post.status != "scheduled":
        raise ConflictError("Only posts that are waiting to be published can be cancelled.")
    post.status = "cancelled"
    post.next_attempt_at = None
    audit_service.record(
        "social.post_cancelled", "social_post", post.id, actor=user,
        details={"platform": post.platform},
    )  # fmt: skip
    return post


def retry(post: SocialPost, user: User) -> SocialPost:
    if post.status != "failed":
        raise ConflictError("Only failed posts can be retried.")
    account = accounts.get_account(post.platform)
    if account is None or account.status != "connected":
        raise ValidationError(f"Reconnect {accounts.LABELS[post.platform]} first.")
    details = dict(post.details or {})
    # A post that may have been sent is looked for on the platform before re-sending.
    post.status = "checking" if details.get("maybe_sent") else "scheduled"
    details.pop("container_id", None)
    details.pop("polls", None)
    post.details = details
    post.attempts = 0
    post.last_error = None
    post.next_attempt_at = None
    post.scheduled_at = min(_aware(post.scheduled_at) or _now(), _now())
    audit_service.record(
        "social.post_retried", "social_post", post.id, actor=user,
        details={"platform": post.platform},
    )  # fmt: skip
    return post


# ---- publishing ---------------------------------------------------------------------------


def _claim(post: SocialPost) -> bool:
    """Atomically move a due post to "publishing" (two workers never send the same post)."""
    previous = post.status
    if previous not in ("scheduled", "checking"):
        return False
    result = db.session.execute(
        update(SocialPost)
        .where(SocialPost.id == post.id, SocialPost.status == previous)
        .values(status="publishing", started_at=_now(), updated_at=_now())
        .execution_options(synchronize_session=False)
    )
    db.session.commit()
    if result.rowcount != 1:
        db.session.refresh(post)
        return False
    db.session.refresh(post)
    details = dict(post.details or {})
    details["checking"] = previous == "checking"
    post.details = details
    return True


def _succeed(post: SocialPost, external_id: str, external_url: str | None) -> None:
    post.status = "published"
    post.external_id = str(external_id)[:100]
    post.external_url = (external_url or "")[:500] or None
    post.published_at = _now()
    post.last_error = None
    post.next_attempt_at = None
    details = dict(post.details or {})
    details.pop("maybe_sent", None)
    details.pop("checking", None)
    post.details = details
    audit_service.record(
        "social.post_published", "social_post", post.id,
        details={"platform": post.platform, "external_id": post.external_id,
                 "external_url": post.external_url},
    )  # fmt: skip


def _fail(post: SocialPost, exc: SocialError) -> None:
    details = dict(post.details or {})
    if exc.uncertain:
        details["maybe_sent"] = True
    post.details = details
    post.last_error = exc.message[:500]
    if exc.reconnect:
        accounts.mark_failure(post.platform, exc)
    retryable = (exc.transient or exc.uncertain) and not exc.reconnect and not exc.permission
    if retryable and post.attempts < MAX_ATTEMPTS:
        post.status = "checking" if details.get("maybe_sent") else "scheduled"
        delay = exc.retry_after or 60 * (2 ** max(0, post.attempts - 1)) * 5  # 5, 10, 20 min...
        post.next_attempt_at = _now() + timedelta(seconds=min(delay, 6 * 3600))
        return
    post.status = "failed"
    post.next_attempt_at = None
    audit_service.record(
        "social.post_failed", "social_post", post.id,
        details={"platform": post.platform, "error": post.last_error},
    )  # fmt: skip


def _wait(post: SocialPost, seconds: int, note: str | None = None) -> None:
    post.status = "scheduled"
    post.next_attempt_at = _now() + timedelta(seconds=seconds)
    if note:
        post.last_error = note


def _check_article(post: SocialPost) -> None:
    if post.article is not None and post.article.status != "published":
        raise SocialError(
            "The related article or quote collection is no longer published, so the Pin "
            "would link to a missing page."
        )


# Pinterest ---------------------------------------------------------------------------------


def _marker(post: SocialPost) -> str:
    return f"TPA social post {post.id}"


def _find_pin(post: SocialPost, token: str) -> dict[str, Any] | None:
    for pin in pinterest.board_pins(token, post.board_id or ""):
        if pin.get("note") == _marker(post):
            return pin
        if pin.get("link") == post.destination_url and pin.get("title") == post.title:
            created = pin.get("created_at")
            started = _aware(post.started_at) or _now()
            try:
                when = _aware(datetime.fromisoformat(str(created).replace("Z", "+00:00")))
            except ValueError:
                continue
            if when >= started - timedelta(days=1):
                return pin
    return None


def _publish_pinterest(post: SocialPost) -> None:
    _, token = accounts.access_token("pinterest")
    if (post.details or {}).get("checking"):
        found = _find_pin(post, token)
        if found:
            _succeed(post, found["id"], pinterest.pin_url(found["id"]))
            return
    _check_article(post)
    payload = {
        "board_id": post.board_id,
        "title": post.title or "",
        "description": post.text or "",
        "link": post.destination_url,
        "alt_text": post.alt_text or post.media_asset.alt_text or None,
        "note": _marker(post),
        "media_source": {
            "source_type": "image_url",
            "url": image_url(post.media_asset, "pinterest"),
        },
    }
    payload = {k: v for k, v in payload.items() if v not in (None, "")}
    pin = pinterest.create_pin(token, payload)
    _succeed(post, pin["id"], pinterest.pin_url(pin["id"]))


# Instagram ---------------------------------------------------------------------------------


def _find_media(post: SocialPost, token: str) -> dict[str, Any] | None:
    started = _aware(post.started_at) or _now()
    for item in instagram.media(token, limit=10)["items"]:
        if (item.get("caption") or "").strip() != (post.text or "").strip():
            continue
        try:
            when = _aware(
                datetime.fromisoformat(str(item.get("timestamp")).replace("+0000", "+00:00"))
            )
        except ValueError:
            continue
        if when >= started - timedelta(days=1):
            return item
    return None


def _publish_instagram(post: SocialPost) -> None:
    account, token = accounts.access_token("instagram")
    details = dict(post.details or {})
    if details.get("checking"):
        found = _find_media(post, token)
        if found:
            _succeed(post, found["id"], found.get("permalink"))
            return
    container = details.get("container_id")
    if not container:
        quota = instagram.publishing_quota(account.external_id, token)
        if quota and quota[0] >= quota[1]:
            _wait(post, 3600, "Instagram's 24-hour publishing limit is reached; waiting.")
            return
        container = instagram.create_container(
            account.external_id, token, image_url(post.media_asset, "instagram"), post.text
        )
        details["container_id"] = container
        details["polls"] = 0
        post.details = dict(details)
        db.session.commit()
    status = instagram.container_status(container, token)
    if status in ("ERROR", "EXPIRED"):
        details.pop("container_id", None)
        post.details = details
        raise SocialError(
            "Instagram could not process the image (it must be a JPEG with an aspect ratio "
            "between 4:5 and 1.91:1, at most 8 MB)."
            if status == "ERROR"
            else "The prepared Instagram post expired before it was published. Retry it."
        )
    if status == "PUBLISHED":
        found = _find_media(post, token)
        if found:
            _succeed(post, found["id"], found.get("permalink"))
            return
        raise SocialError("Instagram reports the post as published but it was not found.")
    if status != "FINISHED":
        details["polls"] = int(details.get("polls") or 0) + 1
        post.details = details
        if details["polls"] >= CONTAINER_POLLS:
            raise SocialError("Instagram is still processing the image. Retry later.")
        post.attempts = max(0, post.attempts - 1)  # waiting is not a failed attempt
        _wait(post, 60, None)
        return
    _check_article(post)
    media_id = instagram.publish_container(account.external_id, token, container)
    _succeed(post, media_id, instagram.permalink(media_id, token))


def publish(post: SocialPost) -> SocialPost:
    """Send one post now (if it is due and not already being sent)."""
    if not _claim(post):
        return post
    post.attempts += 1
    try:
        if post.platform == "pinterest":
            _publish_pinterest(post)
        else:
            _publish_instagram(post)
    except ValidationError as exc:  # the image is no longer usable
        _fail(post, SocialError(exc.message))
    except SocialError as exc:
        _fail(post, exc)
    if post.status == "publishing":  # defensive: never leave a post claimed
        post.status = "scheduled"
    details = dict(post.details or {})
    details.pop("checking", None)
    post.details = details
    db.session.commit()
    return post


def publish_now(post: SocialPost) -> SocialPost:
    db.session.commit()  # the request's changes (new post / retry) are saved first
    return publish(post)


def run_due(limit: int = 20) -> dict[str, Any]:
    """Publish due posts (called by the publishing timer). Never raises for one post."""
    now = _now()
    stale = db.session.scalars(
        select(SocialPost).where(
            SocialPost.status == "publishing", SocialPost.started_at < now - STALE_PUBLISHING
        )
    ).all()
    for post in stale:  # a crashed run: find out what happened before sending again
        post.status = "checking"
        post.details = {**(post.details or {}), "maybe_sent": True}
    db.session.commit()
    due = db.session.scalars(
        select(SocialPost)
        .where(
            SocialPost.status.in_(("scheduled", "checking")),
            SocialPost.scheduled_at <= now,
            or_(SocialPost.next_attempt_at.is_(None), SocialPost.next_attempt_at <= now),
        )
        .order_by(SocialPost.scheduled_at, SocialPost.id)
        .limit(limit)
    ).all()
    result: dict[str, Any] = {"published": [], "failed": [], "waiting": []}
    for post in due:
        try:
            publish(post)
        except Exception:  # noqa: BLE001 - one broken post must not stop the others
            db.session.rollback()
            current_app.logger.exception("social post %s could not be processed", post.id)
            result["failed"].append(post.id)
            continue
        key = {"published": "published", "failed": "failed"}.get(post.status, "waiting")
        result[key].append(post.id)
    result["tokens"] = accounts.refresh_due()
    db.session.commit()
    return result
