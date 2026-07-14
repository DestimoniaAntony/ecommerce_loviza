"""
Core Context Processors — CommerceHub
Injects platform-wide context variables into all Django templates.
"""
from django.conf import settings
from catalog.models import Category

def tenant_context(request):
    """
    Injects the current tenant (vendor) and platform settings
    into every template context.
    """
    tenant = getattr(request, 'tenant', None)
    
    # Pre-fetch category tree for storefront navigation if tenant exists
    storefront_categories = []
    if tenant:
        try:
            storefront_categories = Category.objects.filter(vendor=tenant, is_active=True).get_cached_trees()
        except Exception:
            storefront_categories = []
            
    return {
        'current_tenant': tenant,
        'platform_name': getattr(settings, 'PLATFORM_NAME', 'CommerceHub'),
        'platform_domain': getattr(settings, 'PLATFORM_DOMAIN', 'commercehub.in'),
        'storefront_categories': storefront_categories,
    }
