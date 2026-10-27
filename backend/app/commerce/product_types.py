"""Extensible product type registry.

A product type decides how a product is delivered. Types that are not yet
deliverable (courses, memberships) are registered as ``planned`` so editors see
them coming, but they cannot be selected until a later batch implements them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductType:
    key: str
    label: str
    delivery: str  # "files" | "bundle" | "planned"
    default_format: str = ""
    description: str = ""

    @property
    def available(self) -> bool:
        return self.delivery != "planned"


PRODUCT_TYPES: dict[str, ProductType] = {
    t.key: t
    for t in (
        ProductType("ebook", "eBook", "files", "PDF / EPUB"),
        ProductType("workbook", "Workbook", "files", "Printable PDF"),
        ProductType("journal", "Digital journal", "files", "Printable PDF"),
        ProductType("planner", "Planner", "files", "Printable PDF"),
        ProductType("reflection_guide", "Reflection guide", "files", "PDF"),
        ProductType("worksheet", "Downloadable worksheet", "files", "Printable PDF"),
        ProductType("resource_pack", "Digital resource pack", "files", "ZIP"),
        # Batch 08: written premium resources (all text-based; no video delivery).
        ProductType("guide", "Guide", "files", "PDF"),
        ProductType("template", "Template", "files", "DOCX / XLSX / PDF"),
        ProductType("checklist", "Checklist", "files", "Printable PDF"),
        ProductType("learning_pack", "Written learning pack", "files", "PDF / ZIP"),
        ProductType(
            "bundle",
            "Bundle",
            "bundle",
            "Multiple products",
            "Grants access to every included product.",
        ),
        ProductType("course", "Online course", "planned", description="Planned for a later batch."),
        ProductType(
            "membership", "Membership", "planned", description="Planned for a later batch."
        ),
    )
}
COVER_THEMES = ("sage", "gold", "olive", "charcoal", "cream", "blush")
TAX_CATEGORIES = {
    "digital_goods": "Digital goods (standard)",
    "ebooks": "Electronic publications",
    "exempt": "Exempt / not taxable",
}


def available_types() -> list[ProductType]:
    return [t for t in PRODUCT_TYPES.values() if t.available]


def type_label(key: str) -> str:
    t = PRODUCT_TYPES.get(key)
    return t.label if t else key
