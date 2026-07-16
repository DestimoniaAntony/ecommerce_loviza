"""
Core Mixins — CommerceHub

Provides class-based view mixins for:
  - Super admin access control
  - Vendor (authenticated business user) access control
  - Tenant-scoped queryset filtering
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.contrib import messages


class SuperAdminRequiredMixin(LoginRequiredMixin):
    """
    Restricts view access to super admin users only.
    Redirects non-super-admins to the login page.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:admin_login')
        if not request.user.is_super_admin:
            messages.error(request, 'Access denied. Super Admin privileges required.')
            return redirect('accounts:admin_login')
        return super().dispatch(request, *args, **kwargs)


class VendorLoginRequiredMixin(LoginRequiredMixin):
    """
    Restricts view access to authenticated vendor staff only.
    Ensures the vendor is active, approved, and has an active subscription.
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:vendor_login')
        if request.user.is_super_admin:
            messages.warning(request, 'Please use the admin panel.')
            return redirect('adminapp:dashboard')
            
        vendor = getattr(request.user, 'vendor', None)
        if vendor:
            if not vendor.is_active or vendor.status != 'approved':
                from django.contrib.auth import logout
                logout(request)
                messages.error(request, 'Your vendor account is not active or has been suspended.')
                return redirect('accounts:vendor_login')
                
            if not vendor.active_subscription:
                from django.contrib.auth import logout
                logout(request)
                messages.error(request, 'Your subscription has expired or is inactive. Please contact the administrator.')
                return redirect('accounts:vendor_login')

        return super().dispatch(request, *args, **kwargs)


class TenantQuerysetMixin:
    """
    Mixin for views that automatically filter querysets to the current vendor.
    Use in combination with LoginRequiredMixin.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if hasattr(user, 'vendor') and user.vendor:
            return qs.filter(vendor=user.vendor)
        return qs.none()


class PermissionRequiredMixin(VendorLoginRequiredMixin):
    """
    Checks that the logged-in vendor staff user has a specific permission codename.
    Primary owner (no role) bypasses checks and gets full access.
    """
    permission_codename = None

    def dispatch(self, request, *args, **kwargs):
        res = super().dispatch(request, *args, **kwargs)
        # If response was a redirect, return it
        if res.status_code in (301, 302):
            return res

        user = request.user
        if user.is_authenticated and not user.is_super_admin:
            if not user.has_vendor_perm(self.permission_codename):
                messages.error(request, 'Access denied. You do not have permission or your active subscription plan does not support this module.')
                return redirect('commercehub_app:dashboard')
        return res
