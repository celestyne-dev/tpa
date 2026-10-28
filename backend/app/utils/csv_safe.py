"""CSV writing that is safe to open in spreadsheet software.

Spreadsheet applications execute cells that start with ``=``, ``+``, ``-``, ``@`` (and
treat tab/carriage return prefixes the same way), so values that can contain user or
staff text are prefixed with an apostrophe (OWASP "CSV injection" guidance). Numbers,
including decimal strings such as a negative net amount ``"-3.00"``, are written
unchanged: a plain number is never evaluated as a formula.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

DANGEROUS = ("=", "+", "-", "@", "\t", "\r")
NUMBER = re.compile(r"[+-]?\d+(\.\d+)?")


def safe_cell(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(DANGEROUS) and not NUMBER.fullmatch(value):
        return "'" + value
    return value


class SafeWriter:
    """A ``csv.writer`` lookalike: ``writerow`` / ``row`` neutralise every cell."""

    def __init__(self) -> None:
        self.buffer = io.StringIO()
        self._writer = csv.writer(self.buffer)

    def writerow(self, cells) -> None:
        self._writer.writerow([safe_cell(c) for c in cells])

    def row(self, *cells: Any) -> None:
        self.writerow(cells)

    def value(self) -> str:
        return self.buffer.getvalue()
