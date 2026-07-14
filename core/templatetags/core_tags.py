from django import template

register = template.Library()


@register.filter
def dict_get(dictionary, key):
    """
    Looks up a key in a dictionary dynamically.
    Handles type conversion if keys are mixed (int/str).
    """
    if not dictionary:
        return None

    # Try exact match
    val = dictionary.get(key)
    if val is not None:
        return val

    # Try string version
    try:
        val = dictionary.get(str(key))
        if val is not None:
            return val
    except Exception:
        pass

    # Try integer version
    try:
        val = dictionary.get(int(key))
        if val is not None:
            return val
    except Exception:
        pass

    return None
