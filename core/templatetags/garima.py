from django import template


register = template.Library()


@register.filter
def npr(value):
    """Format a numeric amount as a compact Nepalese rupee value."""
    try:
        return f"NPR {float(value):,.0f}"
    except (TypeError, ValueError):
        return "NPR 0"
