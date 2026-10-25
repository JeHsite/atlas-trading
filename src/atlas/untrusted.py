"""Wrapping of external text before it is shown to a model.

News, filings, transcripts, speeches and social posts can contain text that
looks like instructions. The analyst prompt tells the model that anything
inside <untrusted_document> is data only; this module makes sure a document
cannot close that tag early and smuggle text outside of it.
"""

from __future__ import annotations

import html
import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG = re.compile(r"</?\s*untrusted_document[^>]*>", re.IGNORECASE)


def wrap_untrusted(text: str, *, source: str, url: str | None = None) -> str:
    cleaned = _CONTROL_CHARS.sub("", text)
    cleaned = _TAG.sub("[removed tag]", cleaned)
    attrs = f'source="{html.escape(source, quote=True)}"'
    if url:
        attrs += f' url="{html.escape(url, quote=True)}"'
    return f"<untrusted_document {attrs}>\n{cleaned}\n</untrusted_document>"
