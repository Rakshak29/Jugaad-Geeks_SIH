"""
Confluence storage format -> clean text + sections.

Confluence returns page bodies as "storage format": XHTML with Confluence's
own `ac:` / `ri:` namespaced elements for macros and resource links. This
module flattens that into readable plain text and splits it on the author's
own headings.

Splitting on headings (rather than a fixed token window) means every section
boundary is one a human deliberately placed, so an extracted section is always
a coherent unit -- a whole procedure, not the back half of one.

Stdlib only: html.parser is forgiving about the namespaced tags and the
occasional unclosed element, which a strict XML parser is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

# Macro configuration -- attributes, not prose. Dropped with their subtree.
_SKIP_SUBTREE_TAGS = {
    "ac:parameter",
    "ri:page",
    "ri:attachment",
    "ri:user",
    "ri:url",
    "ri:space",
}

# Tags that end the current line when they open or close.
_BLOCK_TAGS = {
    "p", "div", "li", "tr", "pre", "blockquote", "table", "ul", "ol",
    "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
    "ac:layout", "ac:layout-section", "ac:layout-cell",
}

_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

# Collapse 3+ blank lines down to one blank line.
_EXCESS_BLANKS = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+\n")
_LEADING_WS = re.compile(r"\n[ \t]+")

# Marks a span of CDATA (code-block / noformat macro bodies). Whitespace is
# meaningful inside those -- an indented YAML block or shell heredoc is part of
# the procedure -- so normalization steps over guarded spans instead of
# flattening them. The guards never survive into stored text.
_CODE_GUARD = "\x00"


@dataclass
class ParsedSection:
    """One heading-delimited chunk of a page."""

    ordinal: int
    heading: str | None  # None for the lead-in text before the first heading
    level: int           # 1..6; 0 for the lead-in
    text: str


class _StorageFormatParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections: list[ParsedSection] = []

        self._parts: list[str] = []
        self._heading: str | None = None
        self._level: int = 0

        self._skip_depth = 0
        self._skip_tag: str | None = None

        self._in_heading = False
        self._heading_parts: list[str] = []
        self._pending_level = 0

    # -- section bookkeeping ------------------------------------------------

    def _flush_section(self) -> None:
        text = _normalize("".join(self._parts))
        # A heading with no body still matters -- it may be a pointer to a
        # child page -- but an empty lead-in with no heading is just noise.
        if text or self._heading:
            self.sections.append(
                ParsedSection(
                    ordinal=len(self.sections),
                    heading=self._heading,
                    level=self._level,
                    text=text,
                )
            )
        self._parts = []

    def _emit(self, s: str) -> None:
        if self._in_heading:
            self._heading_parts.append(s)
        else:
            self._parts.append(s)

    # -- HTMLParser hooks ---------------------------------------------------

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return

        if tag in _SKIP_SUBTREE_TAGS:
            self._skip_tag = tag
            self._skip_depth = 1
            return

        if tag in _HEADING_TAGS:
            self._flush_section()
            self._in_heading = True
            self._heading_parts = []
            self._pending_level = _HEADING_TAGS[tag]
            return

        if tag == "br":
            self._emit("\n")
        elif tag in ("td", "th"):
            self._emit(" | ")
        elif tag in _BLOCK_TAGS:
            self._emit("\n")

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self._skip_depth:
            return
        if tag == "br":
            self._emit("\n")
        # Self-closing macros and resource links carry no text.

    def handle_endtag(self, tag):
        tag = tag.lower()

        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth -= 1
                if self._skip_depth == 0:
                    self._skip_tag = None
            return

        if tag in _HEADING_TAGS:
            self._heading = _normalize("".join(self._heading_parts)) or None
            self._level = self._pending_level
            self._in_heading = False
            self._heading_parts = []
            return

        if tag in _BLOCK_TAGS:
            self._emit("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        self._emit(data)

    def unknown_decl(self, data):
        # CDATA sections: `<![CDATA[ ... ]]>` arrives here as "CDATA[ ... ".
        # Confluence puts code-block and noformat macro bodies in CDATA, which
        # is exactly the shell commands a runbook is worth reading for.
        if self._skip_depth:
            return
        if data.startswith("CDATA["):
            code = data[len("CDATA["):]
            self._emit("\n" + _CODE_GUARD + code + _CODE_GUARD + "\n")

    # -- result -------------------------------------------------------------

    def result(self) -> list[ParsedSection]:
        self._flush_section()
        return self.sections


def _normalize(text: str) -> str:
    """
    Collapse whitespace runs without destroying paragraph structure.

    Storage-format bodies carry the source XHTML's own indentation, which
    would otherwise show up as ragged leading spaces in the transfer package.
    Guarded code spans are passed through untouched.
    """
    if not text:
        return ""

    parts = text.split(_CODE_GUARD)
    out: list[str] = []
    for index, part in enumerate(parts):
        # Odd indices are the inside of a guarded pair: verbatim code.
        if index % 2 == 1:
            out.append(part.strip("\n"))
        else:
            out.append(_normalize_prose(part))

    return "\n".join(p for p in out if p).strip()


def _normalize_prose(text: str) -> str:
    if not text:
        return ""
    # Normalize newlines and non-breaking spaces first.
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    # Squash runs of spaces/tabs, but leave newlines alone.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = _TRAILING_WS.sub("\n", text)
    text = _LEADING_WS.sub("\n", text)
    text = _EXCESS_BLANKS.sub("\n\n", text)
    return text.strip()


def parse_storage_format(body: str) -> list[ParsedSection]:
    """Split a Confluence storage-format body into heading-delimited sections."""
    if not body:
        return []
    parser = _StorageFormatParser()
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        # A malformed body should degrade to "no sections", never abort a sync.
        # The caller still stores the page and can fall back to raw text.
        return []
    return parser.result()


def sections_to_text(sections: list[ParsedSection]) -> str:
    """Rejoin parsed sections into the page's full plain text."""
    out: list[str] = []
    for s in sections:
        if s.heading:
            out.append(s.heading)
        if s.text:
            out.append(s.text)
    return _normalize("\n\n".join(out))


def storage_to_text(body: str) -> str:
    """Convenience: storage format straight to flat text."""
    return sections_to_text(parse_storage_format(body))
