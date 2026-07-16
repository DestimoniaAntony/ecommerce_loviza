"""
Accounts Models — CommerceHub

Custom User model with:
- Phone + Email authentication
- OTP verification
- Role-based access (super admin, vendor staff, customer)
- Login history and device tracking
- Account lockout on failed attempts
"""
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.conf import settings
import datetime


# ─────────────────────────────────────────────────────────────
# USER MANAGER
# ─────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):

    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError('Phone number is required.')
        user = self.model(phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_super_admin', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', 'super_admin')
        return self.create_user(phone, password, **extra_fields)


# ─────────────────────────────────────────────────────────────
# ROLE & MODULE PERMISSIONS
# ─────────────────────────────────────────────────────────────

class ModulePermission(models.Model):
    """
    Permissions mapped to specific system modules (e.g. products, orders, settings).
    """
    name = models.CharField(max_length=100)
    codename = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'ch_module_permissions'
        verbose_name = 'Module Permission'
        verbose_name_plural = 'Module Permissions'

    def __str__(self):
        return f'{self.name} ({self.codename})'


class Role(models.Model):
    """
    Tenant-scoped role definitions for staff users.
    System default roles have vendor = None.
    """
    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='roles',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(ModulePermission, blank=True, related_name='roles')
    is_custom = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ch_roles'
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'
        unique_together = ('vendor', 'name')

    def __str__(self):
        if self.vendor:
            return f'{self.vendor.business_name} — {self.name}'
        return f'System Default — {self.name}'


# ─────────────────────────────────────────────────────────────
# USER MODEL
# ─────────────────────────────────────────────────────────────

class User(AbstractBaseUser, PermissionsMixin):
    """
    Central User model for CommerceHub.

    Types:
        super_admin  — Platform owner / CommerceHub team
        vendor_staff — Business owners, partners, staff
        customer     — End customers of a store
    """

    USER_TYPE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('vendor_staff', 'Vendor Staff'),
        ('customer', 'Customer'),
    ]

    # Identity
    phone = models.CharField(max_length=15, unique=True)
    email = models.EmailField(blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    profile_photo = models.ImageField(upload_to='users/profile/', blank=True, null=True)

    # Type & Role
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='vendor_staff')
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )

    # Vendor link (null for super admins and standalone customers)
    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_users',
    )

    # Status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)          # Django admin access
    is_super_admin = models.BooleanField(default=False)    # CommerceHub super admin
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    # Account Security
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # Timestamps
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = 'ch_users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        name = self.get_full_name()
        return f'{name} ({self.phone})' if name else self.phone

    def has_vendor_perm(self, perm_codename):
        """
        Check if the vendor user has permission to access a module.
        It verifies BOTH the active subscription plan AND the user's role.
        """
        if self.is_super_admin:
            return True
        if not self.vendor or not self.vendor.active_plan:
            return False

        # Map specific sub-module view/manage permissions to the broad module permissions
        permission_map = {
            'view_catalog': 'manage_catalog',
            'view_inventory': 'manage_inventory',
            'view_roles': 'manage_organization',
            'manage_roles': 'manage_organization',
            'view_staff': 'manage_organization',
            'manage_staff': 'manage_organization',
            'view_branches': 'manage_organization',
            'manage_branches': 'manage_organization',
        }
        perm_codename = permission_map.get(perm_codename, perm_codename)

        # Check Subscription Plan Limits
        plan = self.vendor.active_plan
        plan_checks = {
            'manage_analytics': plan.has_analytics,
            'manage_store_settings': plan.has_store_settings,
            'manage_catalog': plan.has_catalog_management,
            'manage_orders': plan.has_order_management,
            'manage_inventory': plan.has_inventory_management,
            'manage_organization': plan.has_organization_management,
            'manage_whatsapp': plan.has_whatsapp,
            'manage_loyalty': plan.has_loyalty,
            'manage_crm': plan.has_crm,
            'manage_marketing': plan.has_marketing,
            'manage_api': plan.has_api_access,
            'manage_white_label': plan.has_white_label,
            'manage_advanced_reports': plan.has_advanced_reports,
        }
        
        # If the plan doesn't support it, completely block access
        if perm_codename in plan_checks and not plan_checks[perm_codename]:
            return False

        # If user has no role, they are the primary owner. They get everything the plan allows.
        if not self.role:
            return True
            
        # If user has a role, check the role's permissions
        return self.role.permissions.filter(codename=perm_codename).exists()

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def get_short_name(self):
        return self.first_name or self.phone

    @property
    def is_locked(self):
        """Check if account is currently locked due to failed login attempts."""
        if self.locked_until and self.locked_until > timezone.now():
            return True
        return False

    def record_failed_login(self):
        """Increment failed login counter; lock account if threshold reached."""
        max_attempts = getattr(settings, 'LOGIN_MAX_ATTEMPTS', 5)
        lockout_minutes = getattr(settings, 'LOGIN_LOCKOUT_MINUTES', 30)
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = timezone.now() + datetime.timedelta(minutes=lockout_minutes)
        self.save(update_fields=['failed_login_attempts', 'locked_until'])

    def reset_failed_login(self):
        """Reset login failure counter after successful login."""
        self.failed_login_attempts = 0
        self.locked_until = None
        self.save(update_fields=['failed_login_attempts', 'locked_until'])


# ─────────────────────────────────────────────────────────────
# OTP VERIFICATION
# ─────────────────────────────────────────────────────────────

class OTPVerification(models.Model):
    """
    Stores OTP codes for phone number verification and login.
    """

    PURPOSE_CHOICES = [
        ('login', 'Login'),
        ('register', 'Register'),
        ('password_reset', 'Password Reset'),
        ('phone_change', 'Phone Change'),
    ]

    phone = models.CharField(max_length=15)
    otp = models.CharField(max_length=10)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='login')
    is_verified = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'ch_otp_verifications'
        verbose_name = 'OTP Verification'
        ordering = ['-created_at']

    def __str__(self):
        return f'OTP for {self.phone} [{self.purpose}]'

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_expired and not self.is_verified and self.attempts < 5


# ─────────────────────────────────────────────────────────────
# LOGIN HISTORY
# ─────────────────────────────────────────────────────────────

class LoginHistory(models.Model):
    """
    Tracks every login attempt for security monitoring.
    """

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('locked', 'Account Locked'),
        ('otp_sent', 'OTP Sent'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='login_history',
        null=True,
        blank=True,
    )
    phone = models.CharField(max_length=15, blank=True)   # Store even if user not found
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    device_type = models.CharField(max_length=50, blank=True)   # mobile, desktop, tablet
    location = models.CharField(max_length=200, blank=True)     # City, Country (from IP)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ch_login_history'
        verbose_name = 'Login History'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.phone} — {self.status} @ {self.created_at:%Y-%m-%d %H:%M}'
