from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from core.models import TimestampModel


class Category(MPTTModel):
    """
    Represents a hierarchically-nested product category tree.
    Scoped per vendor/tenant.
    """
    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='categories'
    )
    parent = TreeForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ch_categories'
        unique_together = ('vendor', 'slug')
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'

    class MPTTMeta:
        order_insertion_by = ['name']

    def __str__(self):
        return f"{self.vendor.business_name} — {self.name}"


class AttributeGroup(TimestampModel):
    """
    Groups attributes together for structured display and classification.
    E.g. 'Specifications', 'Physical Dimensions'.
    """
    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='attribute_groups'
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'ch_attribute_groups'
        unique_together = ('vendor', 'name')
        verbose_name = 'Attribute Group'
        verbose_name_plural = 'Attribute Groups'

    def __str__(self):
        return f"{self.vendor.business_name} — {self.name}"


class Attribute(TimestampModel):
    """
    Defines a dynamic product specification field or variant option.
    E.g. 'Color', 'Size', 'Storage Capacity', 'RAM'.
    """
    TYPE_CHOICES = [
        ('text', 'Text Input'),
        ('number', 'Numeric Value'),
        ('select', 'Dropdown Select'),
        ('boolean', 'Toggle / True-False'),
    ]

    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='attributes'
    )
    group = models.ForeignKey(
        AttributeGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attributes'
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50)  # e.g., 'ram', 'color', 'size'
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='text')
    is_required = models.BooleanField(default=False)
    is_filterable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ch_attributes'
        unique_together = ('vendor', 'code')
        verbose_name = 'Attribute'
        verbose_name_plural = 'Attributes'

    def __str__(self):
        return f"{self.vendor.business_name} — {self.name} ({self.code})"


class AttributeOption(models.Model):
    """
    Pre-configured dropdown options for attributes of type 'select'.
    E.g. 'Red', 'Blue', 'Green' for attribute 'Color'.
    """
    attribute = models.ForeignKey(
        Attribute,
        on_delete=models.CASCADE,
        related_name='options'
    )
    value = models.CharField(max_length=100)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'ch_attribute_options'
        unique_together = ('attribute', 'value')
        ordering = ['sort_order', 'value']
        verbose_name = 'Attribute Option'
        verbose_name_plural = 'Attribute Options'

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"


class Product(TimestampModel):
    """
    Represents a master product catalog record scoped per vendor.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    vendor = models.ForeignKey(
        'tenants.Vendor',
        on_delete=models.CASCADE,
        related_name='products'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    has_variants = models.BooleanField(default=False)
    attributes_data = models.JSONField(default=dict, blank=True)  # Non-variant general attributes

    class Meta:
        db_table = 'ch_products'
        unique_together = ('vendor', 'slug')
        verbose_name = 'Product'
        verbose_name_plural = 'Products'

    def __str__(self):
        return f"{self.vendor.business_name} — {self.name}"

    @property
    def total_stock(self):
        return sum(variant.stock_qty for variant in self.variants.all())

    @property
    def price_range(self):
        first_variant = self.variants.filter(is_active=True).first()
        if first_variant:
            return first_variant.price
        return 0

    @property
    def compare_at_price_range(self):
        first_variant = self.variants.filter(is_active=True).first()
        if first_variant and first_variant.compare_at_price and first_variant.compare_at_price > first_variant.price:
            return first_variant.compare_at_price
        return None

    @property
    def max_discount_percentage(self):
        percentages = []
        for v in self.variants.all():
            if v.is_active and v.compare_at_price and v.compare_at_price > v.price:
                discount = ((v.compare_at_price - v.price) / v.compare_at_price) * 100
                percentages.append(discount)
        if percentages:
            return round(max(percentages))
        return 0


class ProductVariant(TimestampModel):
    """
    Represents a specific sellable stock-keeping unit (SKU) of a product.
    If a product has no variants, a single default variant represents it.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    name = models.CharField(max_length=250, blank=True)  # E.g. "T-Shirt - Red, L"
    sku = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    image = models.ImageField(upload_to='products/variants/', blank=True, null=True)
    attributes_data = models.JSONField(default=dict, blank=True)  # E.g. {"color": "Red", "size": "L"}
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ch_product_variants'
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'

    def __str__(self):
        if self.name:
            return f"{self.product.name} ({self.name}) [SKU: {self.sku}]"
        return f"{self.product.name} [SKU: {self.sku}]"

    @property
    def discount_percentage(self):
        if self.compare_at_price and self.compare_at_price > self.price:
            return round(((self.compare_at_price - self.price) / self.compare_at_price) * 100)
        return 0


class ProductImage(models.Model):
    """
    Holds multiple additional showcase images (gallery) for a product.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/gallery/')
    alt_text = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ch_product_images'
        ordering = ['sort_order', 'created_at']
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'

    def __str__(self):
        return f"Image for {self.product.name} ({self.pk if self.pk else 'new'})"


class ProductInfoSection(models.Model):
    """
    Dynamic informational sections (accordions) for a product.
    E.g., "Description & Fabric", "Shipping Info", "Care Instructions".
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='info_sections')
    heading = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    image = models.ImageField(upload_to='product_info/', null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'ch_product_info_sections'
        ordering = ['sort_order', 'id']
        verbose_name = 'Product Info Section'
        verbose_name_plural = 'Product Info Sections'

    def __str__(self):
        return f"{self.heading} for {self.product.name}"
