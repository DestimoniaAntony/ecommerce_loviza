from django.db import models


class TimestampModel(models.Model):
    """
    Abstract base model that provides created_at and updated_at timestamps.
    All CommerceHub models that don't need full tenant context extend this.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantModel(models.Model):
    """
    Abstract base model for ALL tenant-scoped data.
    Every major model must extend this to ensure multi-tenant data isolation.

    Fields:
        vendor      — The tenant (business) this record belongs to.
        branch      — Optional branch within the vendor.
        created_by  — User who created this record.
        updated_by  — User who last modified this record.
        created_at  — Auto timestamp on creation.
        updated_at  — Auto timestamp on update.
        is_active   — Soft enable/disable flag.
    """
    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='+',
    )
    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
