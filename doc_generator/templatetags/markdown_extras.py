# generator/templatetags/markdown_extras.py
from django import template
from django.utils.safestring import mark_safe
import markdown
import bleach

register = template.Library()

# Build allowed tags as a set to avoid frozenset + list error
_base_tags = set(bleach.sanitizer.ALLOWED_TAGS)
_extra_tags = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "pre", "code", "blockquote", "hr", "br",
    "ul", "ol", "li", "strong", "em",
    "table", "thead", "tbody", "tr", "th", "td"
}
ALLOWED_TAGS = sorted(_base_tags.union(_extra_tags))

# Attributes: start from bleach defaults then extend safely
_base_attributes = dict(bleach.sanitizer.ALLOWED_ATTRIBUTES)
_extra_attributes = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title"],
    "th": ["align"],
    "td": ["align"],
}
# Merge attributes (union lists for same keys)
ALLOWED_ATTRIBUTES = _base_attributes.copy()
for k, v in _extra_attributes.items():
    if k in ALLOWED_ATTRIBUTES:
        # ensure unique
        existing = list(ALLOWED_ATTRIBUTES[k])
        for item in v:
            if item not in existing:
                existing.append(item)
        ALLOWED_ATTRIBUTES[k] = existing
    else:
        ALLOWED_ATTRIBUTES[k] = v

# Allowed protocols
ALLOWED_PROTOCOLS = set(bleach.sanitizer.ALLOWED_PROTOCOLS)
ALLOWED_PROTOCOLS.update({"mailto"})
ALLOWED_PROTOCOLS = sorted(ALLOWED_PROTOCOLS)


@register.filter(name="markdown_to_html")
def markdown_to_html(markdown_text):
    """
    Convert Markdown to safe HTML.
    - Uses python-markdown to convert to HTML.
    - Sanitizes HTML with bleach to remove unsafe tags/attributes.
    """
    if not markdown_text:
        return ""

    # Convert Markdown -> HTML (extensions chosen for useful behavior)
    html = markdown.markdown(markdown_text, extensions=["fenced_code", "tables", "nl2br", "sane_lists"])

    # Sanitize
    clean = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True
    )

    return mark_safe(clean)

