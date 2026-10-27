"""Stable text anchors for highlights and passage notes.

An anchor identifies a passage by meaning, not by browser selection offsets:

    {"block": "<block uid>", "quote": "exact text", "prefix": "...", "suffix": "...",
     "start": 12, "end": 40}

``quote``, ``prefix`` and ``suffix`` are taken from the block's whitespace-normalised
plain text (``content.block_text``); ``start``/``end`` are offsets in that text and only
used as a hint. When a lesson is republished every anchor is matched again:

1. same block, same offsets, same text → unchanged;
2. the quote still appears in the same block → the occurrence whose surrounding text best
   matches ``prefix``/``suffix`` (a tie means ambiguous → not matched);
3. the block was rewritten or moved: the quote appears exactly once elsewhere in the
   lesson (long quotes only), or one occurrence clearly wins on context;
4. otherwise the anchor is *orphaned*: the learner keeps the quote as a saved excerpt
   and it is never attached to a different passage by guesswork.

Lesson content is never modified by anchoring.
"""

from __future__ import annotations

from typing import Any

from ...utils.errors import ValidationError
from ...utils.validation import plain_text_problem
from . import content

CONTEXT = 32
MAX_QUOTE = 1000
# Quotes shorter than this are only re-matched inside their original block.
MIN_RELOCATE = 16


def _occurrences(text: str, quote: str) -> list[int]:
    out, start = [], text.find(quote)
    while start != -1:
        out.append(start)
        start = text.find(quote, start + 1)
    return out


def _common_suffix(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _common_prefix(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def _score(text: str, start: int, quote: str, prefix: str, suffix: str) -> int:
    before = text[max(0, start - CONTEXT) : start]
    after = text[start + len(quote) : start + len(quote) + CONTEXT]
    return _common_suffix(before, prefix) + _common_prefix(after, suffix)


def _best(text: str, starts: list[int], quote: str, prefix: str, suffix: str) -> int | None:
    """The occurrence with the best context score; None when two are equally good."""
    if len(starts) == 1:
        return starts[0]
    scored = sorted(((_score(text, s, quote, prefix, suffix), s) for s in starts), reverse=True)
    if scored[0][0] == 0 or scored[0][0] == scored[1][0]:
        return None
    return scored[0][1]


def _build(uid: str, text: str, start: int, quote: str) -> dict[str, Any]:
    end = start + len(quote)
    return {
        "block": uid,
        "quote": quote,
        "prefix": text[max(0, start - CONTEXT) : start],
        "suffix": text[end : end + CONTEXT],
        "start": start,
        "end": end,
    }


def _texts(blocks: list[dict[str, Any]]) -> dict[str, str]:
    return {
        b["uid"]: content.block_text(b)
        for b in blocks or []
        if b.get("uid") and b.get("type") in content.TEXT_BLOCKS
    }


def create(blocks: list[dict[str, Any]], data: Any) -> dict[str, Any]:
    """Validate a passage chosen by a learner against the live lesson text."""
    if not isinstance(data, dict):
        raise ValidationError(details={"anchor": ["Choose a passage in the lesson."]})
    uid = data.get("block")
    quote = data.get("quote")
    texts = _texts(blocks)
    if not isinstance(uid, str) or uid not in texts:
        raise ValidationError(details={"anchor": ["This passage can't be highlighted."]})
    if not isinstance(quote, str) or plain_text_problem(quote):
        raise ValidationError(details={"anchor": ["Choose some text in the lesson."]})
    quote = content.normalize(quote)
    if not quote or len(quote) > MAX_QUOTE:
        raise ValidationError(
            details={"anchor": [f"Choose between 1 and {MAX_QUOTE} characters of text."]}
        )
    prefix = content.normalize(str(data.get("prefix") or ""))[-CONTEXT:]
    suffix = content.normalize(str(data.get("suffix") or ""))[:CONTEXT]
    text = texts[uid]
    starts = _occurrences(text, quote)
    if not starts:
        raise ValidationError(details={"anchor": ["This text isn't in the lesson."]})
    hint = data.get("start")
    if isinstance(hint, int) and not isinstance(hint, bool) and hint in starts:
        start = hint
    else:
        start = _best(text, starts, quote, prefix, suffix)
        if start is None:
            start = starts[0]  # identical passages: either one is the learner's text
    return _build(uid, text, start, quote)


def resolve(anchor: dict[str, Any], blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Re-match an anchor against (new) lesson content; None when it can't be matched."""
    quote = anchor.get("quote") or ""
    if not quote:
        return None
    prefix, suffix = anchor.get("prefix") or "", anchor.get("suffix") or ""
    texts = _texts(blocks)
    uid = anchor.get("block")
    if uid in texts:
        text = texts[uid]
        start = anchor.get("start")
        if isinstance(start, int) and text[start : start + len(quote)] == quote:
            return _build(uid, text, start, quote)
        starts = _occurrences(text, quote)
        if starts:
            found = _best(text, starts, quote, prefix, suffix)
            return _build(uid, text, found, quote) if found is not None else None
    if len(quote) < MIN_RELOCATE:
        return None
    everywhere = [(other, s) for other, text in texts.items() for s in _occurrences(text, quote)]
    if len(everywhere) == 1:
        other, start = everywhere[0]
        return _build(other, texts[other], start, quote)
    if len(everywhere) > 1:
        scored = sorted(
            ((_score(texts[other], s, quote, prefix, suffix), other, s) for other, s in everywhere),
            reverse=True,
        )
        if scored[0][0] > 0 and scored[0][0] > scored[1][0]:
            _, other, start = scored[0]
            return _build(other, texts[other], start, quote)
    return None
