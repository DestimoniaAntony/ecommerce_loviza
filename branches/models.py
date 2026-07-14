from django.db import models
from core.models import TimestampModel


class Branch(TimestampModel):
    """
    Represents a physical branch/location of a vendor.
    Supports multi-branch and franchise architectures.
    """
    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='branches',
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    address_line1 = models.CharField(max_length=300, blank=True)
    address_line2 = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=100, default='India')
    is_main_branch = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ch_branches'
        verbose_name = 'Branch'
        verbose_name_plural = 'Branches'
        unique_together = ('vendor', 'code')

    def __str__(self):
        return f'{self.vendor.business_name} — {self.name}'


class Franchise(TimestampModel):
    """
    Represents a franchise relationship where a child vendor is linked to a parent vendor.
    Allows catalog sharing but separate inventory/checkout.
    """
    parent_vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='franchises',
    )
    child_vendor = models.OneToOneField(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='franchise_details',
    )
    agreement_start_date = models.DateField()
    agreement_end_date = models.DateField()
    royalty_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ch_franchises'
        verbose_name = 'Franchise'
        verbose_name_plural = 'Franchises'

    def __str__(self):
        return f'Parent: {self.parent_vendor.business_name} → Franchise: {self.child_vendor.business_name}'


class Partner(TimestampModel):
    """
    Represents partners/co-owners associated with a vendor.
    """
    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='partners',
    )
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    email = models.EmailField(blank=True)

    class Meta:
        db_table = 'ch_partners'
        verbose_name = 'Partner'
        verbose_name_plural = 'Partners'

    def __str__(self):
        return f'{self.name} ({self.vendor.business_name})'
