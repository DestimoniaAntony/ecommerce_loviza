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
        try:
            rounded_price = int(round(Decimal(str(price))))
            return f"{tenant.currency_symbol}{rounded_price}"
        except (ValueError, TypeError, Decimal.InvalidOperation):
            return f"{tenant.currency_symbol}{price}"
        
    supported = tenant.supported_currencies.filter(code=target_currency_code, is_active=True).first()
    if not supported:
        try:
            rounded_price = int(round(Decimal(str(price))))
            return f"{tenant.currency_symbol}{rounded_price}"
        except (ValueError, TypeError, Decimal.InvalidOperation):
            return f"{tenant.currency_symbol}{price}"
        
    try:
        converted_price = Decimal(str(price)) * supported.exchange_rate
        rounded_price = int(round(converted_price))
        return f"{supported.symbol}{rounded_price}"
    except (ValueError, TypeError, Decimal.InvalidOperation):
        return f"{tenant.currency_symbol}{price}"

def convert_price_raw(request, price):
    """Returns the converted price as a raw Decimal without currency symbols."""
    if not request or price is None:
        return Decimal(str(price or 0))
    
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return Decimal(str(price or 0))
        
    target_currency_code = request.session.get('currency_code', tenant.currency)
    
    if target_currency_code == tenant.currency:
        try:
            return Decimal(str(int(round(Decimal(str(price))))))
        except (ValueError, TypeError, Decimal.InvalidOperation):
            return Decimal(str(price))
        
    supported = tenant.supported_currencies.filter(code=target_currency_code, is_active=True).first()
    if not supported:
        try:
            return Decimal(str(int(round(Decimal(str(price))))))
        except (ValueError, TypeError, Decimal.InvalidOperation):
            return Decimal(str(price))
        
    try:
        converted_price = Decimal(str(price)) * supported.exchange_rate
        return Decimal(str(int(round(converted_price))))
    except (ValueError, TypeError, Decimal.InvalidOperation):
        return Decimal(str(price))

@register.simple_tag(takes_context=True)
def format_price(context, price):
    """
    Formats the price according to the user's selected currency.
    Usage: {% format_price product.price %}
    """
    request = context.get('request')
    return convert_price(request, price)
