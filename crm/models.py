from django.db import models
from django.conf import settings
from tenants.models import Vendor
from storefront.models import Order

class Coupon(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage (%)'),
        ('flat', 'Flat Amount'),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='coupons')
    code = models.CharField(max_length=50)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPE_CHOICES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_purchase = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    start_date = models.DateField()
    end_date = models.DateField()
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ch_coupons'
        verbose_name = 'Coupon'
        verbose_name_plural = 'Coupons'
        unique_together = ('vendor', 'code')

    def __str__(self):
        return f"{self.code} — {self.vendor.business_name} ({self.get_discount_type_display()}: {self.discount_value})"

    def save(self, *args, **kwargs):
        # Force code to uppercase and strip
        if self.code:
            self.code = self.code.upper().strip()
        super().save(*args, **kwargs)


class Wallet(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='wallets')
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallets'
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ch_wallets'
        verbose_name = 'Customer Wallet'
        verbose_name_plural = 'Customer Wallets'
        unique_together = ('vendor', 'customer')

    def __str__(self):
        return f"Wallet for {self.customer} — Balance: {self.balance}"

    def credit(self, amount, reason, order=None):
        from decimal import Decimal
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Credit amount must be positive.")
        self.balance = Decimal(str(self.balance)) + amount
        self.save()
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='credit',
            amount=amount,
            reason=reason,
            reference_order=order
        )

    def debit(self, amount, reason, order=None):
        from decimal import Decimal
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError("Debit amount must be positive.")
        if self.balance < amount:
            raise ValueError("Insufficient wallet balance.")
        self.balance = Decimal(str(self.balance)) - amount
        self.save()
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='debit',
            amount=amount,
            reason=reason,
            reference_order=order
        )


class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    reference_order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wallet_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ch_wallet_transactions'
        verbose_name = 'Wallet Transaction'
        verbose_name_plural = 'Wallet Transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type.upper()} — {self.amount} for {self.wallet.customer.phone}"


class LoyaltyProgram(models.Model):
    vendor = models.OneToOneField(Vendor, on_delete=models.CASCADE, related_name='loyalty_program')
    is_enabled = models.BooleanField(default=False)
    points_per_currency = models.DecimalField(max_digits=6, decimal_places=4, default=0.01) # 1 point per 100 spent (0.01 points per 1 unit)
    currency_per_point = models.DecimalField(max_digits=6, decimal_places=2, default=0.10)   # 1 point = 0.10 currency value
    min_points_to_redeem = models.PositiveIntegerField(default=100)

    class Meta:
        db_table = 'ch_loyalty_programs'
        verbose_name = 'Loyalty Program'
        verbose_name_plural = 'Loyalty Programs'

    def __str__(self):
        enabled_str = "Enabled" if self.is_enabled else "Disabled"
        return f"Loyalty Settings — {self.vendor.business_name} ({enabled_str})"


class LoyaltyLedger(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('earn', 'Points Earned'),
        ('redeem', 'Points Redeemed'),
        ('expiry', 'Points Expired'),
        ('manual_adjustment', 'Manual Adjustment'),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='loyalty_ledger')
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='loyalty_ledger_entries'
    )
    points = models.IntegerField()
    transaction_type = models.CharField(max_length=25, choices=TRANSACTION_TYPE_CHOICES)
    reference_order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loyalty_transactions'
    )
    reason = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ch_loyalty_ledgers'
        verbose_name = 'Loyalty Ledger Entry'
        verbose_name_plural = 'Loyalty Ledger Entries'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.points} pts ({self.transaction_type}) — {self.customer.phone}"


# ─────────────────────────────────────────────────────────────
# NEWSLETTER SUBSCRIBER
# ─────────────────────────────────────────────────────────────

class NewsletterSubscriber(models.Model):
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='newsletter_subscribers')
    email = models.EmailField()
    first_name = models.CharField(max_length=100, blank=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ch_newsletter_subscribers'
        verbose_name = 'Newsletter Subscriber'
        verbose_name_plural = 'Newsletter Subscribers'
        unique_together = ('vendor', 'email')

    def __str__(self):
        return f"{self.email} ({self.vendor.business_name})"
