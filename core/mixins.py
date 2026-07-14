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
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:vendor_login')
        if request.user.is_super_admin:
            messages.warning(request, 'Please use the admin panel.')
            return redirect('adminapp:dashboard')
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
            if user.role:
                has_perm = user.role.permissions.filter(codename=self.permission_codename).exists()
                if not has_perm:
                    messages.error(request, 'Access denied. You do not have permission to access this module.')
                    return redirect('commercehub_app:dashboard')
        return res
