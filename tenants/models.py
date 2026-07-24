"""
Tenants Models — CommerceHub

Core multi-tenant models:
  - Vendor         → A business/tenant on the platform
  - SubscriptionPlan → Available plans (Trial, Starter, Standard, etc.)
  - VendorSubscription → A vendor's active plan subscription
"""
from django.db import models
from django.utils import timezone
from core.models import TimestampModel
import datetime


# ─────────────────────────────────────────────────────────────
# SUBSCRIPTION PLAN
# ─────────────────────────────────────────────────────────────

class SubscriptionPlan(TimestampModel):
    """
    Platform subscription plans available to vendors.
    Configured by the Super Admin.
    """

    PLAN_CHOICES = [
        ('trial', 'Trial'),
        ('starter', 'Starter'),
        ('standard', 'Standard'),
        ('professional', 'Professional'),
        ('enterprise', 'Enterprise'),
    ]

    BILLING_CHOICES = [
        ('monthly', 'Monthly'),
        ('annual', 'Annual'),
        ('lifetime', 'Lifetime'),
    ]

    name = models.CharField(max_length=50)
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES, unique=True)
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CHOICES, default='monthly')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    annual_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    trial_days = models.PositiveSmallIntegerField(default=14)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    # Feature Limits
    max_products = models.PositiveIntegerField(default=100)
    max_branches = models.PositiveSmallIntegerField(default=1)
    max_staff = models.PositiveSmallIntegerField(default=3)
    max_monthly_orders = models.PositiveIntegerField(default=500)

    # Feature Flags
    has_whatsapp = models.BooleanField(default=False)
    has_loyalty = models.BooleanField(default=False)
    has_crm = models.BooleanField(default=False)
    has_marketing = models.BooleanField(default=False)
    has_api_access = models.BooleanField(default=False)
    has_otp_login = models.BooleanField(default=False)
    has_white_label = models.BooleanField(default=False)
    has_advanced_reports = models.BooleanField(default=False)

    # Core Module Feature Flags
    has_analytics = models.BooleanField(default=True)
    has_store_settings = models.BooleanField(default=True)
    has_catalog_management = models.BooleanField(default=True)
    has_order_management = models.BooleanField(default=True)
    has_inventory_management = models.BooleanField(default=True)
    has_organization_management = models.BooleanField(default=True)

    class Meta:
        db_table = 'ch_subscription_plans'
        verbose_name = 'Subscription Plan'
        ordering = ['sort_order']

    def __str__(self):
        return f'{self.name} (₹{self.price}/mo)'


# ─────────────────────────────────────────────────────────────
# VENDOR (TENANT)
# ─────────────────────────────────────────────────────────────

class Vendor(TimestampModel):
    """
    Represents a business/tenant on the CommerceHub platform.
    This is the central tenant model — all data belongs to a vendor.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ]

    BUSINESS_TYPE_CHOICES = [
        ('single_store', 'Single Store'),
        ('multi_branch', 'Multi Branch'),
        ('multi_partner', 'Multi Partner'),
        ('franchise', 'Franchise'),
        ('online_only', 'Online Store'),
        ('whatsapp_store', 'WhatsApp Store'),
        ('wholesale', 'Wholesale'),
    ]

    CHECKOUT_WORKFLOW_CHOICES = [
        ('online_payment', 'Online Payment (Razorpay)'),
        ('online_payment_stripe', 'Online Payment (Stripe)'),
        ('approval_payment', 'Approval then Payment'),
        ('whatsapp_enquiry', 'WhatsApp Enquiry'),
        ('cod_only', 'Cash on Delivery Only'),
    ]

    # ── Business Identity ──
    business_name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100, unique=True)
    business_type = models.CharField(max_length=30, choices=BUSINESS_TYPE_CHOICES, default='single_store')
    gst_number = models.CharField(max_length=20, blank=True)
    pan_number = models.CharField(max_length=20, blank=True)

    # ── Contact ──
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15)
    whatsapp_number = models.CharField(max_length=15, blank=True)
    website = models.URLField(blank=True)

    # ── Address ──
    address_line1 = models.CharField(max_length=300, blank=True)
    address_line2 = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=100, default='India')

    # ── Branding ──
    logo = models.ImageField(upload_to='vendors/logos/', blank=True, null=True)
    banner = models.ImageField(upload_to='vendors/banners/', blank=True, null=True)
    favicon = models.ImageField(upload_to='vendors/favicons/', blank=True, null=True)

    # ── Social Media ──
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)

    # ── Store Settings ──
    currency = models.CharField(max_length=5, default='INR')
    currency_symbol = models.CharField(max_length=5, default='₹')
    top_announcement_text = models.CharField(
        max_length=200, 
        blank=True, 
        null=True, 
        help_text="Text to display in the black top bar (e.g. Store Wide Summer Sale). Leave blank to hide."
    )
    timezone = models.CharField(max_length=50, default='Asia/Kolkata')
    checkout_workflow = models.CharField(
        max_length=30,
        choices=CHECKOUT_WORKFLOW_CHOICES,
        default='online_payment',
    )
    track_inventory = models.BooleanField(
        default=False,
        help_text="If enabled, product stock is tracked, preventing overselling."
    )
    gcc_shipping_charge = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=100.00,
        help_text="Shipping charge for GCC countries (UAE, Saudi Arabia, Qatar, Oman, Kuwait, Bahrain)"
    )
    non_gcc_shipping_charge = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=150.00,
        help_text="Shipping charge for non-GCC countries"
    )

    # ── White Label ──
    primary_color = models.CharField(max_length=7, default='#6366f1')
    secondary_color = models.CharField(max_length=7, default='#8b5cf6')
    custom_css = models.TextField(blank=True)

    # ── Payment & Integration Settings ──
    razorpay_key_id = models.CharField(max_length=150, blank=True)
    razorpay_key_secret = models.CharField(max_length=150, blank=True)
    stripe_public_key = models.CharField(max_length=150, blank=True)
    stripe_secret_key = models.CharField(max_length=150, blank=True)
    stripe_webhook_secret = models.CharField(max_length=150, blank=True)
    whatsapp_order_format = models.TextField(blank=True)

    # ── Status & Plan ──
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    active_plan = models.ForeignKey('tenants.SubscriptionPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='active_vendors')
    is_active = models.BooleanField(default=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_vendors',
    )
    suspension_reason = models.TextField(blank=True)

    # ── SEO ──
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)

    class Meta:
        db_table = 'ch_vendors'
        verbose_name = 'Vendor'
        verbose_name_plural = 'Vendors'
        ordering = ['-created_at']

    def __str__(self):
        return self.business_name

    @property
    def active_subscription(self):
        return self.subscriptions.filter(
            is_active=True,
            end_date__gte=timezone.now().date(),
        ).select_related('plan').first()

    @property
    def current_plan(self):
        sub = self.active_subscription
        return sub.plan if sub else None

    def approve(self, approved_by_user):
        self.status = 'approved'
        self.approved_at = timezone.now()
        self.approved_by = approved_by_user
        self.is_active = True
        self.save(update_fields=['status', 'approved_at', 'approved_by', 'is_active'])
        # Ensure all associated vendor staff are also activated so they can log in
        self.staff_users.update(is_active=True)

    def suspend(self, reason=''):
        self.status = 'suspended'
        self.is_active = False
        self.suspension_reason = reason
        self.save(update_fields=['status', 'is_active', 'suspension_reason'])
        # Ensure all associated vendor staff are suspended from logging in
        self.staff_users.update(is_active=False)


# ─────────────────────────────────────────────────────────────
# VENDOR SUPPORTED CURRENCIES
# ─────────────────────────────────────────────────────────────

class SupportedCurrency(TimestampModel):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='supported_currencies')
    code = models.CharField(max_length=5, help_text="e.g. USD, EUR")
    symbol = models.CharField(max_length=5, help_text="e.g. $, €")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=1.0000, help_text="Exchange rate relative to base currency")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ch_vendor_supported_currencies'
        verbose_name = 'Supported Currency'
        ordering = ['code']
        unique_together = ('vendor', 'code')

    def __str__(self):
        return f'{self.code} ({self.symbol}) - {self.vendor.business_name}'


# ─────────────────────────────────────────────────────────────
# VENDOR SUBSCRIPTION
# ─────────────────────────────────────────────────────────────

class VendorSubscription(TimestampModel):
    """
    A vendor's active subscription to a plan.
    Multiple records track subscription history.
    """

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='vendor_subscriptions')
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    is_trial = models.BooleanField(default=False)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_reference = models.CharField(max_length=200, blank=True)
    renewal_reminder_sent = models.BooleanField(default=False)

    class Meta:
        db_table = 'ch_vendor_subscriptions'
        verbose_name = 'Vendor Subscription'
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.vendor.business_name} — {self.plan.name}'

    @property
    def is_expired(self):
        return self.end_date < timezone.now().date()

    @property
    def days_remaining(self):
        delta = self.end_date - timezone.now().date()
        return max(0, delta.days)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Sync the vendor's active_plan field automatically
        if self.is_active and not self.is_expired:
            if self.vendor.active_plan != self.plan:
                self.vendor.active_plan = self.plan
                self.vendor.save(update_fields=['active_plan'])


# ─────────────────────────────────────────────────────────────
# VENDOR EMAIL SETTINGS
# ─────────────────────────────────────────────────────────────

class VendorEmailSettings(TimestampModel):
    """
    Stores SMTP credentials and newsletter welcome discount configuration for a vendor.
    """
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage (%)'),
        ('flat', 'Flat Amount'),
    ]

    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name='email_settings')
    
    # SMTP Settings
    email_host = models.CharField(max_length=255, default='smtp.gmail.com')
    email_port = models.PositiveIntegerField(default=587)
    email_host_user = models.CharField(max_length=255, blank=True)
    email_host_password = models.CharField(max_length=255, blank=True)
    use_tls = models.BooleanField(default=True)
    default_from_email = models.EmailField(blank=True)
    
    # Welcome Discount Settings
    welcome_discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='percentage')
    welcome_discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
    popup_image = models.ImageField(upload_to='vendors/popups/', blank=True, null=True, help_text="Image to display on the newsletter popup")

    class Meta:
        db_table = 'ch_vendor_email_settings'
        verbose_name = 'Vendor Email Settings'
        verbose_name_plural = 'Vendor Email Settings'

    def __str__(self):
        return f'Email Settings — {self.vendor.business_name}'
