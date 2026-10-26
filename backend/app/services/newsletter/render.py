# ruff: noqa: E501  (email HTML keeps inline styles on one line per element)
"""Email rendering: safe, mobile-friendly HTML plus a plain-text alternative.

Email HTML is generated here from validated blocks, never copied from the website:
table layout, inline styles, web-safe fonts, no scripts, no external stylesheets, no
web fonts and no tracking pixels. Every email ends with the sender identity, why the
recipient gets it, a preferences link and a one-click unsubscribe link.

Per-recipient values are filled in at send time from placeholders, so a campaign is
rendered once (its snapshot) and personalised per message:
``{{first_name}}`` (merge tag authors may use), ``{{tpa:unsubscribe_url}}`` and
``{{tpa:preferences_url}}``.
"""

from __future__ import annotations

import re
from html import escape
from typing import Any

from flask import current_app
from sqlalchemy import select

from ...cms.blocks import validate_blocks
from ...extensions import db
from ...models import Article, MediaAsset, Product
from ...utils.errors import ValidationError
from .config import NEWSLETTER_NAME, NEWSLETTER_TAGLINE, get_settings

EMAIL_BLOCK_TYPES = (
    "paragraph",
    "heading",
    "quote",
    "callout",
    "list",
    "divider",
    "image",
    "button",
    "cta",
)
UNSUBSCRIBE = "{{tpa:unsubscribe_url}}"
PREFERENCES = "{{tpa:preferences_url}}"
FIRST_NAME = "{{first_name}}"

# Brand palette (matches the website tokens).
SAGE = "#45593c"
SAGE_DARK = "#364631"
GOLD = "#dcc28a"
IVORY = "#faf6ee"
CREAM = "#f4ede0"
CHARCOAL = "#24221f"
MUTED = "#6b665d"
SERIF = "Georgia, 'Times New Roman', serif"
SANS = "Arial, Helvetica, sans-serif"
CALLOUT_COLORS = {"info": "#eef2ea", "tip": "#f6efdc", "warning": "#fbeee6", "success": "#e9f1e4"}


def validate_email_blocks(blocks: Any) -> list[dict[str, Any]]:
    cleaned = validate_blocks(blocks)
    bad = {
        str(i): [f"“{b['type']}” blocks can't be used in email."]
        for i, b in enumerate(cleaned)
        if b["type"] not in EMAIL_BLOCK_TYPES
    }
    if bad:
        raise ValidationError(
            "Some content blocks are not supported in email.", details={"body": bad}
        )
    return cleaned


def site_url() -> str:
    return current_app.config["SITE_URL"].rstrip("/")


def absolute(href: str) -> str:
    return href if re.match(r"^https?://", href or "") else f"{site_url()}{href or '/'}"


def _text(value: str) -> str:
    return escape(value or "").replace("\n", "<br>")


def _media(ids: set[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    assets = db.session.scalars(select(MediaAsset).where(MediaAsset.id.in_(ids)))
    out = {}
    for asset in assets:
        image = asset.as_image()
        if image:
            out[asset.id] = {**image, "src": absolute(image["src"])}
    return out


def _button(label: str, href: str, style: str = "primary") -> str:
    bg, fg = (SAGE, IVORY) if style == "primary" else (CREAM, CHARCOAL)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:8px 0 16px"><tr>'
        f'<td style="border-radius:999px;background:{bg}">'
        f'<a href="{escape(absolute(href))}" style="display:inline-block;padding:12px 24px;'
        f"font-family:{SANS};font-size:15px;font-weight:bold;color:{fg};text-decoration:none;"
        f'border-radius:999px">{escape(label)}</a></td></tr></table>'
    )


def _block_html(block: dict[str, Any], media: dict[int, dict[str, Any]]) -> str:
    kind = block["type"]
    p = f"margin:0 0 16px;font-family:{SANS};font-size:16px;line-height:1.6;color:{CHARCOAL}"
    if kind == "paragraph":
        return f'<p style="{p}">{_text(block["text"])}</p>'
    if kind == "heading":
        size = 24 if block.get("level", 2) == 2 else 19
        return (
            f'<h{block.get("level", 2)} style="margin:24px 0 12px;font-family:{SERIF};'
            f'font-size:{size}px;line-height:1.3;font-weight:normal;color:{CHARCOAL}">'
            f"{escape(block['text'])}</h{block.get('level', 2)}>"
        )
    if kind == "quote":
        cite = (
            f'<br><span style="font-size:14px;color:{MUTED}">— {escape(block["cite"])}</span>'
            if block.get("cite")
            else ""
        )
        return (
            f'<blockquote style="margin:0 0 16px;padding:4px 0 4px 16px;border-left:3px solid '
            f'{GOLD};font-family:{SERIF};font-size:18px;line-height:1.5;color:{CHARCOAL}">'
            f"{_text(block['text'])}{cite}</blockquote>"
        )
    if kind == "callout":
        title = (
            f'<strong style="display:block;margin-bottom:4px">{escape(block["title"])}</strong>'
            if block.get("title")
            else ""
        )
        bg = CALLOUT_COLORS.get(block.get("tone", "info"), CREAM)
        return (
            f'<div style="margin:0 0 16px;padding:16px;border-radius:12px;background:{bg};'
            f'font-family:{SANS};font-size:15px;line-height:1.6;color:{CHARCOAL}">'
            f"{title}{_text(block['text'])}</div>"
        )
    if kind == "list":
        tag = "ol" if block.get("ordered") else "ul"
        items = "".join(
            f'<li style="margin:0 0 6px">{_text(item)}</li>' for item in block.get("items", [])
        )
        return f'<{tag} style="{p};padding-left:24px">{items}</{tag}>'
    if kind == "divider":
        return '<hr style="border:0;border-top:1px solid #e3dccd;margin:24px 0">'
    if kind == "image":
        image = media.get(block.get("media_id"))
        if not image:
            return ""
        caption = (
            f'<p style="margin:6px 0 0;font-family:{SANS};font-size:13px;color:{MUTED}">'
            f"{escape(block['caption'])}</p>"
            if block.get("caption")
            else ""
        )
        alt = escape(block.get("alt") or image.get("alt") or "")
        return (
            f'<div style="margin:0 0 16px"><img src="{escape(image["src"])}" alt="{alt}" '
            'width="552" style="display:block;width:100%;max-width:552px;height:auto;'
            f'border:0;border-radius:12px">{caption}</div>'
        )
    if kind == "button":
        return _button(block["label"], block["href"], block.get("style", "primary"))
    if kind == "cta":
        text = f'<p style="{p}">{_text(block["text"])}</p>' if block.get("text") else ""
        return (
            f'<div style="margin:8px 0 16px;padding:20px;border-radius:16px;background:{CREAM}">'
            f'<h3 style="margin:0 0 8px;font-family:{SERIF};font-size:20px;font-weight:normal;'
            f'color:{CHARCOAL}">{escape(block["title"])}</h3>{text}'
            f"{_button(block['button_label'], block['button_href'])}</div>"
        )
    return ""


def _block_text(block: dict[str, Any]) -> str:
    kind = block["type"]
    if kind in ("paragraph",):
        return block["text"]
    if kind == "heading":
        return block["text"].upper()
    if kind == "quote":
        return f"“{block['text']}”" + (f" — {block['cite']}" if block.get("cite") else "")
    if kind == "callout":
        return (f"{block['title']}: " if block.get("title") else "") + block["text"]
    if kind == "list":
        return "\n".join(
            f"{i + 1}. {item}" if block.get("ordered") else f"- {item}"
            for i, item in enumerate(block.get("items", []))
        )
    if kind == "divider":
        return "---"
    if kind == "image":
        return f"[{block['alt']}]" if block.get("alt") else ""
    if kind == "button":
        return f"{block['label']}: {absolute(block['href'])}"
    if kind == "cta":
        parts = [block["title"], block.get("text") or "", absolute(block["button_href"])]
        return "\n".join(p for p in parts if p)
    return ""


def featured_articles(ids: list[int]) -> list[dict[str, Any]]:
    """Published articles only, in the chosen order."""
    if not ids:
        return []
    from ..article_service import published_filter

    rows = {
        a.id: a
        for a in db.session.scalars(select(Article).where(Article.id.in_(ids), published_filter()))
    }
    return [
        {
            "id": a.id,
            "title": a.title,
            "excerpt": a.excerpt,
            "url": absolute(f"/articles/{a.slug}"),
        }
        for i in ids
        if (a := rows.get(i))
    ]


def featured_products(ids: list[int]) -> list[dict[str, Any]]:
    """Published products only, with honest availability (prices only when on sale)."""
    if not ids:
        return []
    from ..commerce.catalogue import public_product

    rows = {p.id: p for p in db.session.scalars(select(Product).where(Product.id.in_(ids)))}
    out = []
    for i in ids:
        product = rows.get(i)
        data = public_product(product) if product else None
        if not data:
            continue
        price = ""
        if data["is_free"] and data["purchasable"]:
            price = "Free"
        elif data["prices"] and data["purchasable"]:
            price = data["prices"][0]["formatted"]
        elif data["availability"] == "coming-soon":
            price = "Coming soon"
        out.append(
            {
                "id": product.id,
                "title": data["title"],
                "description": data["description"],
                "price": price,
                "url": absolute(f"/shop/{data['slug']}"),
            }
        )
    return out


def _cards_html(heading: str, cards: list[dict[str, Any]], label: str) -> str:
    if not cards:
        return ""
    rows = []
    for card in cards:
        meta = (
            f'<p style="margin:0 0 6px;font-family:{SANS};font-size:13px;font-weight:bold;'
            f'color:{SAGE}">{escape(card["price"])}</p>'
            if card.get("price")
            else ""
        )
        body = card.get("excerpt") or card.get("description") or ""
        rows.append(
            f'<div style="margin:0 0 12px;padding:16px;border:1px solid #e3dccd;border-radius:12px">'
            f'<h3 style="margin:0 0 6px;font-family:{SERIF};font-size:18px;font-weight:normal">'
            f'<a href="{escape(card["url"])}" style="color:{CHARCOAL};text-decoration:none">'
            f"{escape(card['title'])}</a></h3>{meta}"
            f'<p style="margin:0 0 8px;font-family:{SANS};font-size:14px;line-height:1.5;'
            f'color:{MUTED}">{escape(body)}</p>'
            f'<a href="{escape(card["url"])}" style="font-family:{SANS};font-size:14px;'
            f'font-weight:bold;color:{SAGE}">{escape(label)} →</a></div>'
        )
    return (
        f'<h2 style="margin:28px 0 12px;font-family:{SERIF};font-size:22px;font-weight:normal;'
        f'color:{CHARCOAL}">{escape(heading)}</h2>' + "".join(rows)
    )


def _cards_text(heading: str, cards: list[dict[str, Any]]) -> str:
    if not cards:
        return ""
    lines = [heading.upper()]
    for card in cards:
        lines.append(f"* {card['title']}" + (f" ({card['price']})" if card.get("price") else ""))
        lines.append(f"  {card['url']}")
    return "\n".join(lines)


def _footer(reason: str, *, manage: bool) -> tuple[str, str]:
    settings = get_settings()
    address = str(settings["email.postal_address"] or "").strip()
    sender = settings["email.from_name"] or "Think Positive Always"
    links_html = (
        f'<a href="{PREFERENCES}" style="color:{SAGE}">Update your preferences</a> · '
        f'<a href="{UNSUBSCRIBE}" style="color:{SAGE}">Unsubscribe</a>'
        if manage
        else ""
    )
    html = (
        f'<p style="margin:0 0 8px">{escape(reason)}</p>'
        + (f'<p style="margin:0 0 8px">{links_html}</p>' if links_html else "")
        + f'<p style="margin:0">{escape(sender)}'
        + (f" · {escape(address)}" if address else "")
        + "</p>"
    )
    text_lines = ["--", reason]
    if manage:
        text_lines += [f"Update your preferences: {PREFERENCES}", f"Unsubscribe: {UNSUBSCRIBE}"]
    text_lines.append(sender + (f" · {address}" if address else ""))
    return html, "\n".join(text_lines)


def build_email(
    *,
    subject: str,
    preheader: str = "",
    blocks: list[dict[str, Any]],
    article_ids: list[int] | None = None,
    product_ids: list[int] | None = None,
    ctas: list[dict[str, str]] | None = None,
    reason: str = "You are receiving this because you subscribed to The Positive Reset.",
    manage_links: bool = True,
    sponsor: dict[str, str] | None = None,
) -> dict[str, str]:
    """Render a complete email (with placeholders) from validated blocks."""
    media = _media({b["media_id"] for b in blocks if b["type"] == "image" and b.get("media_id")})
    articles = featured_articles(article_ids or [])
    products = featured_products(product_ids or [])
    body_html = ""
    if sponsor:
        # Sponsored issues open with a clear disclosure, before any promotional content.
        body_html += (
            f'<p style="margin:0 0 20px;padding:10px 14px;border-radius:10px;background:{CREAM};'
            f'font-family:{SANS};font-size:13px;color:{CHARCOAL}"><strong>Sponsored by '
            f"{escape(sponsor['name'])}.</strong> {escape(sponsor['disclosure'])}</p>"
        )
    body_html += "".join(_block_html(b, media) for b in blocks)
    body_html += _cards_html("Featured reading", articles, "Read the article")
    body_html += _cards_html("From the shop", products, "Take a look")
    body_html += "".join(_button(c["label"], c["href"]) for c in ctas or [])
    footer_html, footer_text = _footer(reason, manage=manage_links)
    hidden = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">'
        f"{escape(preheader)}&#8199;&#65279;&#847;</div>"
        if preheader
        else ""
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:{IVORY}">
{hidden}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{IVORY}">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px">
<tr><td style="padding:24px 24px 20px;background:{SAGE_DARK};border-radius:20px 20px 0 0;text-align:center">
<p style="margin:0;font-family:{SANS};font-size:12px;letter-spacing:2px;text-transform:uppercase;color:{GOLD}">Think Positive Always</p>
<p style="margin:6px 0 0;font-family:{SERIF};font-size:26px;color:{IVORY}">{escape(NEWSLETTER_NAME)}</p>
<p style="margin:4px 0 0;font-family:{SANS};font-size:13px;color:#d9e0d3">{escape(NEWSLETTER_TAGLINE)}</p>
</td></tr>
<tr><td style="padding:28px 24px 12px;background:#ffffff">{body_html}</td></tr>
<tr><td style="padding:20px 24px 28px;background:{CREAM};border-radius:0 0 20px 20px;font-family:{SANS};font-size:12px;line-height:1.6;color:{MUTED}">{footer_html}</td></tr>
</table></td></tr></table></body></html>"""
    text_parts = [NEWSLETTER_NAME + " — " + NEWSLETTER_TAGLINE, ""]
    if preheader:
        text_parts += [preheader, ""]
    if sponsor:
        text_parts += [f"SPONSORED BY {sponsor['name'].upper()}. {sponsor['disclosure']}", ""]
    text_parts += [t for t in (_block_text(b) for b in blocks) if t]
    for part in (_cards_text("Featured reading", articles), _cards_text("From the shop", products)):
        if part:
            text_parts += ["", part]
    for cta in ctas or []:
        text_parts.append(f"{cta['label']}: {absolute(cta['href'])}")
    text_parts += ["", footer_text]
    return {
        "subject": subject,
        "html": html,
        "text": "\n\n".join(text_parts).replace("\n\n\n", "\n\n"),
    }


def personalise(
    rendered: dict[str, str],
    *,
    first_name: str = "",
    unsubscribe_url: str = "",
    preferences_url: str = "",
) -> dict[str, str]:
    name = (first_name or "").strip() or "friend"
    html = (
        rendered["html"]
        .replace(FIRST_NAME, escape(name))
        .replace(UNSUBSCRIBE, escape(unsubscribe_url))
        .replace(PREFERENCES, escape(preferences_url))
    )
    text = (
        rendered["text"]
        .replace(FIRST_NAME, name)
        .replace(UNSUBSCRIBE, unsubscribe_url)
        .replace(PREFERENCES, preferences_url)
    )
    return {"subject": rendered["subject"].replace(FIRST_NAME, name), "html": html, "text": text}


def simple_email(
    subject: str, paragraphs: list[str], button: tuple[str, str] | None = None, *, reason: str
) -> dict[str, str]:
    """Transactional message (confirmation, resource delivery): no marketing links."""
    blocks: list[dict[str, Any]] = [{"type": "paragraph", "text": p} for p in paragraphs]
    if button:
        blocks.append({"type": "button", "label": button[0], "href": button[1], "style": "primary"})
    return build_email(subject=subject, blocks=blocks, reason=reason, manage_links=False)
