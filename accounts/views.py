"""
Accounts Views — CommerceHub
Handles all authentication flows:
  - Super Admin login (phone+password)
  - Vendor Staff login (OTP or phone+password)
  - OTP send and verify
  - Logout
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.views import View
from django.utils import timezone
from django.db.models import Q
from django.db import transaction
import datetime

from .models import User, OTPVerification, LoginHistory, Role, ModulePermission
from core.utils import generate_otp, send_otp_sms, get_client_ip, get_user_agent, mask_phone
from django.conf import settings


# ─────────────────────────────────────────────────────────────
# SUPER ADMIN LOGIN
# ─────────────────────────────────────────────────────────────

class AdminLoginView(View):
    template_name = 'auth/admin_login.html'

    def get(self, request):
        if request.user.is_authenticated and request.user.is_super_admin:
            return redirect('adminapp:dashboard')
        return render(request, self.template_name)

    def post(self, request):
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()
        ip = get_client_ip(request)
        ua = get_user_agent(request)

        if not phone or not password:
            messages.error(request, 'Phone and password are required.')
            return render(request, self.template_name)

        try:
            user = User.objects.get(phone=phone, is_super_admin=True)
        except User.DoesNotExist:
            LoginHistory.objects.create(phone=phone, status='failed', ip_address=ip, user_agent=ua)
            messages.error(request, 'Invalid credentials.')
            return render(request, self.template_name)

        if user.is_locked:
            LoginHistory.objects.create(user=user, phone=phone, status='locked', ip_address=ip, user_agent=ua)
            minutes_left = int((user.locked_until - timezone.now()).seconds / 60) + 1
            messages.error(request, f'Account locked. Try again in {minutes_left} minute(s).')
            return render(request, self.template_name)

        # Authenticate via PhonePasswordBackend (phone + password)
        auth_user = authenticate(request, phone=phone, password=password)

        if auth_user:
            auth_user.reset_failed_login()
            login(request, auth_user)  # backend is auto-set by authenticate()
            LoginHistory.objects.create(user=auth_user, phone=phone, status='success', ip_address=ip, user_agent=ua)
            return redirect('adminapp:dashboard')
        else:
            user.record_failed_login()
            LoginHistory.objects.create(user=user, phone=phone, status='failed', ip_address=ip, user_agent=ua)
            remaining = getattr(settings, 'LOGIN_MAX_ATTEMPTS', 5) - user.failed_login_attempts
            messages.error(request, f'Invalid credentials. {max(0, remaining)} attempt(s) remaining.')
            return render(request, self.template_name)


# ─────────────────────────────────────────────────────────────
# VENDOR OTP LOGIN — STEP 1: Send OTP
# ─────────────────────────────────────────────────────────────

class VendorLoginView(View):
    template_name = 'auth/vendor_login.html'

    def get(self, request):
        if request.user.is_authenticated and not request.user.is_super_admin:
            return redirect('commercehub_app:dashboard')
        return render(request, self.template_name)

    def post(self, request):
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()
        login_method = request.POST.get('login_method', 'otp') # 'otp' or 'password'
        ip = get_client_ip(request)
        ua = get_user_agent(request)

        if not phone:
            messages.error(request, 'Please enter your phone number.')
            return render(request, self.template_name)

        try:
            user = User.objects.get(phone=phone, is_active=True)
        except User.DoesNotExist:
            messages.error(request, 'No active account found with this phone number.')
            return render(request, self.template_name)

        if user.is_locked:
            messages.error(request, 'Account is temporarily locked. Please contact support.')
            return render(request, self.template_name)

        if login_method == 'password':
            if not password:
                messages.error(request, 'Please enter your password.')
                return render(request, self.template_name)

            auth_user = authenticate(request, phone=phone, password=password)
            if auth_user:
                auth_user.reset_failed_login()
                if not hasattr(auth_user, 'backend'):
                    auth_user.backend = 'accounts.backends.PhonePasswordBackend'
                login(request, auth_user)
                LoginHistory.objects.create(user=auth_user, phone=phone, status='success', ip_address=ip, user_agent=ua)
                messages.success(request, f'Welcome back, {auth_user.get_short_name()}!')
                return redirect('commercehub_app:dashboard')
            else:
                user.record_failed_login()
                LoginHistory.objects.create(user=user, phone=phone, status='failed', ip_address=ip, user_agent=ua)
                remaining = getattr(settings, 'LOGIN_MAX_ATTEMPTS', 5) - user.failed_login_attempts
                messages.error(request, f'Invalid password. {max(0, remaining)} attempt(s) remaining.')
                return render(request, self.template_name)
        else:
            # Generate and send OTP
            otp = generate_otp()
            expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 10)
            expires_at = timezone.now() + datetime.timedelta(minutes=expiry_minutes)

            OTPVerification.objects.create(
                phone=phone,
                otp=otp,
                purpose='login',
                expires_at=expires_at,
            )

            send_otp_sms(phone, otp)
            LoginHistory.objects.create(user=user, phone=phone, status='otp_sent', ip_address=ip, user_agent=ua)

            request.session['otp_phone'] = phone
            messages.success(request, f'OTP sent to {mask_phone(phone)}. Valid for {expiry_minutes} minutes.')
            return redirect('accounts:otp_verify')


# ─────────────────────────────────────────────────────────────
# VENDOR OTP LOGIN — STEP 2: Verify OTP
# ─────────────────────────────────────────────────────────────

class OTPVerifyView(View):
    template_name = 'auth/otp_verify.html'

    def get(self, request):
        phone = request.session.get('otp_phone')
        if not phone:
            return redirect('accounts:vendor_login')
        return render(request, self.template_name, {'masked_phone': mask_phone(phone)})

    def post(self, request):
        phone = request.session.get('otp_phone')
        if not phone:
            return redirect('accounts:vendor_login')

        entered_otp = request.POST.get('otp', '').strip()
        ip = get_client_ip(request)
        ua = get_user_agent(request)

        # Find latest valid OTP
        otp_obj = OTPVerification.objects.filter(
            phone=phone,
            purpose='login',
            is_verified=False,
        ).order_by('-created_at').first()

        if not otp_obj:
            messages.error(request, 'OTP expired or not found. Please request a new one.')
            return redirect('accounts:vendor_login')

        if otp_obj.is_expired:
            messages.error(request, 'OTP has expired. Please request a new one.')
            return redirect('accounts:vendor_login')

        otp_obj.attempts += 1
        otp_obj.save(update_fields=['attempts'])

        if otp_obj.attempts > getattr(settings, 'OTP_MAX_ATTEMPTS', 5):
            messages.error(request, 'Too many incorrect attempts. Please request a new OTP.')
            return redirect('accounts:vendor_login')

        if otp_obj.otp != entered_otp:
            messages.error(request, f'Incorrect OTP. {max(0, 5 - otp_obj.attempts)} attempt(s) remaining.')
            return render(request, self.template_name, {'masked_phone': mask_phone(phone)})

        # OTP correct — mark as verified and log in
        otp_obj.is_verified = True
        otp_obj.save(update_fields=['is_verified'])

        try:
            user = User.objects.get(phone=phone, is_active=True)
        except User.DoesNotExist:
            messages.error(request, 'Account not found.')
            return redirect('accounts:vendor_login')

        user.is_phone_verified = True
        user.reset_failed_login()
        user.save(update_fields=['is_phone_verified', 'failed_login_attempts', 'locked_until'])

        auth_user = authenticate(request, phone=phone, otp_verified=True)
        if auth_user:
            # Ensure backend attribute is set (required with multiple backends)
            if not hasattr(auth_user, 'backend'):
                auth_user.backend = 'accounts.backends.PhoneOTPBackend'
            login(request, auth_user)
            request.session.pop('otp_phone', None)
            LoginHistory.objects.create(user=auth_user, phone=phone, status='success', ip_address=ip, user_agent=ua)
            messages.success(request, f'Welcome back, {auth_user.get_short_name()}!')
            return redirect('commercehub_app:dashboard')

        messages.error(request, 'Login failed. Please try again.')
        return redirect('accounts:vendor_login')


# ─────────────────────────────────────────────────────────────
# RESEND OTP
# ─────────────────────────────────────────────────────────────

class ResendOTPView(View):
    def post(self, request):
        phone = request.session.get('otp_phone')
        if not phone:
            return redirect('accounts:vendor_login')

        otp = generate_otp()
        expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 10)
        expires_at = timezone.now() + datetime.timedelta(minutes=expiry_minutes)

        OTPVerification.objects.create(
            phone=phone,
            otp=otp,
            purpose='login',
            expires_at=expires_at,
        )
        send_otp_sms(phone, otp)
        messages.success(request, f'New OTP sent to {mask_phone(phone)}.')
        return redirect('accounts:otp_verify')


# ─────────────────────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────────────────────

class LogoutView(View):
    def get(self, request):
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('accounts:admin_login')


# ─────────────────────────────────────────────────────────────
# ROLE MANAGEMENT
# ─────────────────────────────────────────────────────────────

from core.mixins import PermissionRequiredMixin

class RoleListView(PermissionRequiredMixin, View):
    permission_codename = 'view_roles'
    template_name = 'vendor/roles/list.html'

    def get(self, request):
        roles = Role.objects.filter(Q(vendor=request.user.vendor) | Q(vendor=None)).order_by('is_custom', 'name')
        context = {
            'roles': roles,
            'page_title': 'Roles & Permissions',
        }
        return render(request, self.template_name, context)


class RoleCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_roles'
    template_name = 'vendor/roles/form.html'

    def get(self, request):
        permissions = ModulePermission.objects.all().order_by('name')
        context = {
            'permissions': permissions,
            'page_title': 'Create Custom Role',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        selected_permission_ids = request.POST.getlist('permissions')

        if not name:
            messages.error(request, 'Role name is required.')
            return redirect('accounts:role_create')

        vendor = request.user.vendor

        if Role.objects.filter(vendor=vendor, name__iexact=name).exists():
            messages.error(request, f'A custom role named "{name}" already exists.')
            return redirect('accounts:role_create')

        with transaction.atomic():
            role = Role.objects.create(
                vendor=vendor,
                name=name,
                description=description,
                is_custom=True
            )
            if selected_permission_ids:
                perms = ModulePermission.objects.filter(pk__in=selected_permission_ids)
                role.permissions.set(perms)
                
        messages.success(request, f'Role "{name}" created successfully!')
        return redirect('accounts:role_list')


class RoleEditView(PermissionRequiredMixin, View):
    permission_codename = 'manage_roles'
    template_name = 'vendor/roles/form.html'

    def get(self, role_id, request=None, *args, **kwargs):
        # Allow class-based view signature handling
        # standard call signature is (self, request, role_id) or (self, request, *args, **kwargs)
        # In Django View, dispatch will call get(self, request, role_id)
        pass

    def dispatch(self, request, *args, **kwargs):
        # We override standard dispatch or define normal get/post
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, role_id):
        role = get_object_or_404(Role, pk=role_id, vendor=request.user.vendor)
        permissions = ModulePermission.objects.all().order_by('name')
        role_permission_ids = role.permissions.values_list('pk', flat=True)
        context = {
            'role': role,
            'permissions': permissions,
            'role_permission_ids': role_permission_ids,
            'page_title': f'Edit Role — {role.name}',
        }
        return render(request, self.template_name, context)

    def post(self, request, role_id):
        role = get_object_or_404(Role, pk=role_id, vendor=request.user.vendor)
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        selected_permission_ids = request.POST.getlist('permissions')

        if not name:
            messages.error(request, 'Role name is required.')
            return redirect('accounts:role_edit', role_id=role.pk)

        if Role.objects.filter(vendor=request.user.vendor, name__iexact=name).exclude(pk=role.pk).exists():
            messages.error(request, f'A custom role named "{name}" already exists.')
            return redirect('accounts:role_edit', role_id=role.pk)

        with transaction.atomic():
            role.name = name
            role.description = description
            role.save()
            if selected_permission_ids:
                perms = ModulePermission.objects.filter(pk__in=selected_permission_ids)
                role.permissions.set(perms)
            else:
                role.permissions.clear()

        messages.success(request, f'Role "{name}" updated successfully!')
        return redirect('accounts:role_list')


# ─────────────────────────────────────────────────────────────
# STAFF MANAGEMENT
# ─────────────────────────────────────────────────────────────

class StaffListView(PermissionRequiredMixin, View):
    permission_codename = 'view_staff'
    template_name = 'vendor/staff/list.html'

    def get(self, request):
        staff_users = User.objects.filter(vendor=request.user.vendor).exclude(pk=request.user.pk).select_related('role', 'branch')
        context = {
            'staff_users': staff_users,
            'page_title': 'Staff Management',
        }
        return render(request, self.template_name, context)


class StaffCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_staff'
    template_name = 'vendor/staff/form.html'

    def get(self, request):
        roles = Role.objects.filter(Q(vendor=request.user.vendor) | Q(vendor=None)).order_by('is_custom', 'name')
        branches = request.user.vendor.branches.filter(is_active=True)
        context = {
            'roles': roles,
            'branches': branches,
            'page_title': 'Add New Staff',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role_id = request.POST.get('role_id')
        branch_id = request.POST.get('branch_id')

        if not phone or not password or not first_name or not role_id:
            messages.error(request, 'Phone, password, first name, and role are required.')
            return redirect('accounts:staff_create')

        if User.objects.filter(phone=phone).exists():
            messages.error(request, f'A user with phone number {phone} already exists.')
            return redirect('accounts:staff_create')

        vendor = request.user.vendor
        role = get_object_or_404(Role, Q(vendor=vendor) | Q(vendor=None), pk=role_id)
        
        branch = None
        if branch_id:
            from branches.models import Branch
            branch = get_object_or_404(Branch, vendor=vendor, pk=branch_id)

        user = User.objects.create_user(
            phone=phone,
            password=password,
            email=email or None,
            first_name=first_name,
            last_name=last_name,
            user_type='vendor_staff',
            vendor=vendor,
            role=role,
            branch=branch,
            is_active=True
        )

        messages.success(request, f'Staff member "{user.get_full_name()}" added successfully!')
        return redirect('accounts:staff_list')


class StaffEditView(PermissionRequiredMixin, View):
    permission_codename = 'manage_staff'
    template_name = 'vendor/staff/form.html'

    def get(self, request, staff_id):
        staff_user = get_object_or_404(User, pk=staff_id, vendor=request.user.vendor)
        roles = Role.objects.filter(Q(vendor=request.user.vendor) | Q(vendor=None)).order_by('is_custom', 'name')
        branches = request.user.vendor.branches.filter(is_active=True)
        context = {
            'staff_user': staff_user,
            'roles': roles,
            'branches': branches,
            'page_title': f'Edit Staff — {staff_user.get_full_name()}',
        }
        return render(request, self.template_name, context)

    def post(self, request, staff_id):
        staff_user = get_object_or_404(User, pk=staff_id, vendor=request.user.vendor)
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role_id = request.POST.get('role_id')
        branch_id = request.POST.get('branch_id')
        is_active = request.POST.get('is_active') == 'true'

        if not phone or not first_name or not role_id:
            messages.error(request, 'Phone, first name, and role are required.')
            return redirect('accounts:staff_edit', staff_id=staff_user.pk)

        if User.objects.filter(phone=phone).exclude(pk=staff_user.pk).exists():
            messages.error(request, f'A user with phone number {phone} already exists.')
            return redirect('accounts:staff_edit', staff_id=staff_user.pk)

        role = get_object_or_404(Role, Q(vendor=request.user.vendor) | Q(vendor=None), pk=role_id)
        
        branch = None
        if branch_id:
            from branches.models import Branch
            branch = get_object_or_404(Branch, vendor=request.user.vendor, pk=branch_id)

        staff_user.phone = phone
        staff_user.email = email or None
        staff_user.first_name = first_name
        staff_user.last_name = last_name
        staff_user.role = role
        staff_user.branch = branch
        staff_user.is_active = is_active
        if password:
            staff_user.set_password(password)
        staff_user.save()

        messages.success(request, f'Staff member "{staff_user.get_full_name()}" updated successfully!')
        return redirect('accounts:staff_list')
