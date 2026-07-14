from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from tenants.views import VendorOnboardingView

urlpatterns = [
    # Django built-in admin (for emergency access)
    path('django-admin/', admin.site.urls),

    # Authentication (shared for all user types)
    path('auth/', include('accounts.urls', namespace='accounts')),

    # Public Vendor Onboarding
    path('onboarding/', VendorOnboardingView.as_view(), name='vendor_onboarding'),

    # Super Admin Panel
    path('sadmin/', include('adminapp.urls', namespace='adminapp')),

    # Vendor Panel (Admin)
    path('admin/', include('commercehub_app.urls', namespace='commercehub_app')),
    path('admin/branches/', include('branches.urls', namespace='branches')),
    path('admin/catalog/', include('catalog.urls', namespace='catalog')),
    path('admin/inventory/', include('inventory.urls', namespace='inventory')),
    path('admin/crm/', include('crm.urls', namespace='crm')),

    # Public Storefront (handles routing and redirection)
    path('', include('storefront.urls', namespace='storefront')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
