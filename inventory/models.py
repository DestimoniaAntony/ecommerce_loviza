from django.db import models
from django.conf import settings
from django.utils import timezone
from core.models import TimestampModel
from tenants.models import Vendor
from branches.models import Branch
from catalog.models import ProductVariant


class Supplier(TimestampModel):
    """
    Represents a third-party supplier from whom inventory can be purchased.
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=150)
    contact_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    email = models.EmailField(blank=True)
    gstin = models.CharField(max_length=15, blank=True, verbose_name="GSTIN")
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ch_suppliers'
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'

    def __str__(self):
        return f"{self.name} ({self.vendor.business_name})"


class BranchInventory(TimestampModel):
    """
    Tracks inventory quantities for a product variant at a specific branch.
    """
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='branch_inventories')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='branch_inventories')
    stock_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        db_table = 'ch_branch_inventories'
        verbose_name = 'Branch Inventory'
        verbose_name_plural = 'Branch Inventories'
        unique_together = ('branch', 'product_variant')

    def __str__(self):
        return f"{self.branch.name} — {self.product_variant.sku}: {self.stock_qty}"


class StockAdjustmentLog(models.Model):
    """
    Audit log of manual inventory adjustments (stock-takes, damage, theft, etc.)
    """
    REASON_CHOICES = [
        ('correction', 'Stock Correction'),
        ('damaged', 'Damaged Goods'),
        ('theft', 'Theft / Loss'),
        ('promotion', 'Promotion / Giveaway'),
        ('other', 'Other'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='stock_adjustments')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='stock_adjustments')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='stock_adjustments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    quantity_changed = models.DecimalField(max_digits=10, decimal_places=2)  # Diff (e.g., -5 or +12)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default='correction')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ch_stock_adjustment_logs'
        verbose_name = 'Stock Adjustment Log'
        verbose_name_plural = 'Stock Adjustment Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product_variant.sku} adjusted by {self.quantity_changed} at {self.branch.name}"


class PurchaseOrder(TimestampModel):
    """
    Purchase Order (PO) issued to a Supplier to receive stock at a specific Branch.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='purchase_orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='purchase_orders')
    po_number = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    order_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField(null=True, blank=True)
    received_date = models.DateTimeField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'ch_purchase_orders'
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'
        unique_together = ('vendor', 'po_number')

    def __str__(self):
        return f"{self.po_number} — {self.supplier.name} ({self.status})"


class PurchaseOrderItem(models.Model):
    """
    Individual items inside a Purchase Order.
    """
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name='po_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        db_table = 'ch_purchase_order_items'
        verbose_name = 'Purchase Order Item'
        verbose_name_plural = 'Purchase Order Items'

    def save(self, *args, **kwargs):
        self.total_cost = self.quantity * self.unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_variant.sku} x {self.quantity}"


class StockTransfer(TimestampModel):
    """
    Tracks moving inventory items from one branch to another.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('transit', 'In-Transit'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='stock_transfers')
    from_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='transfers_out')
    to_branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='transfers_in')
    transfer_number = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    sent_date = models.DateTimeField(null=True, blank=True)
    received_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'ch_stock_transfers'
        verbose_name = 'Stock Transfer'
        verbose_name_plural = 'Stock Transfers'
        unique_together = ('vendor', 'transfer_number')

    def __str__(self):
        return f"{self.transfer_number}: {self.from_branch.name} → {self.to_branch.name} ({self.status})"


class StockTransferItem(models.Model):
    """
    Individual items inside a Stock Transfer.
    """
    stock_transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name='transfer_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'ch_stock_transfer_items'
        verbose_name = 'Stock Transfer Item'
        verbose_name_plural = 'Stock Transfer Items'

    def __str__(self):
        return f"{self.product_variant.sku} x {self.quantity}"
