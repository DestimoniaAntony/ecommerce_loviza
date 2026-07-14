from django import template
from decimal import Decimal

register = template.Library()

@register.simple_tag(takes_context=True)
def convert_price(request, price):
    if not request or price is None:
        return price
    
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return price
        
    target_currency_code = request.session.get('currency_code', tenant.currency)
    
    if target_currency_code == tenant.currency:
        return f"{tenant.currency_symbol}{price}"
        
    supported = tenant.supported_currencies.filter(code=target_currency_code, is_active=True).first()
    if not supported:
        return f"{tenant.currency_symbol}{price}"
        
    try:
        converted_price = Decimal(str(price)) * supported.exchange_rate
        return f"{supported.symbol}{converted_price:.2f}"
    except (ValueError, TypeError, Decimal.InvalidOperation):
        return f"{tenant.currency_symbol}{price}"

@register.simple_tag(takes_context=True)
def format_price(context, price):
    """
    Formats the price according to the user's selected currency.
    Usage: {% format_price product.price %}
    """
    request = context.get('request')
    return convert_price(request, price)
