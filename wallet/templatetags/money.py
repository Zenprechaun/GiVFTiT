from django import template

register = template.Library()


@register.filter
def cents(value):
    """Format integer cents as dollars: 1234 -> $12.34, -500 -> -$5.00."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return ""
    sign = "-" if value < 0 else ""
    value = abs(value)
    return f"{sign}${value // 100:,}.{value % 100:02d}"
