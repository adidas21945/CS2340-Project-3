import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_CITE = re.compile(r"\[(\d+)\]")


@register.filter
def cite_links(value: str) -> str:
    """Escape the LLM text first, then turn each [n] into a link to source n."""
    return mark_safe(_CITE.sub(r'<a href="#src-\1" class="cite">[\1]</a>', escape(value)))
