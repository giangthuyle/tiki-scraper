from __future__ import annotations

import unicodedata
from html import unescape
from html.parser import HTMLParser

_BLOCK_TAGS = {"p", "br", "li", "div", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}


_BLOCK_BREAK = "\x00"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _BLOCK_TAGS:
            self._chunks.append(_BLOCK_BREAK)

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._chunks.append(_BLOCK_BREAK)

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    text = unescape(parser.get_text())
    text = unicodedata.normalize("NFC", text)
    # Block-tag boundaries are marked with _BLOCK_BREAK, not "\n" — a "\n"
    # occurring naturally inside a text node (just HTML whitespace) must
    # collapse like any other whitespace, not be read as a paragraph break.
    paragraphs = [" ".join(chunk.split()) for chunk in text.split(_BLOCK_BREAK)]
    paragraphs = [p for p in paragraphs if p]
    return "\n".join(paragraphs)
