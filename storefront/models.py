import uuid
from django.db import models
from django.conf import settings
from tenants.models import Vendor
from branches.models import Branch
from catalog.models import ProductVariant
from decimal import Decimal


class CustomerAddress(models.Model):
    """
    Stores delivery addresses for storefront customers.
    """
    ADDRESS_TYPE_CHOICES = [
        ('home', 'Home'),
        ('work', 'Work'),
        ('other', 'Other'),
    ]
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='addresses'
    )
    address_type = models.CharField(max_length=20, choices=ADDRESS_TYPE_CHOICES, default='home')
    recipient_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15)
    address_line1 = models.CharField(max_length=300)
    address_line2 = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    country = models.CharField(max_length=100, default='India')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ch_customer_addresses'
        verbose_name = 'Customer Address'
        verbose_name_plural = 'Customer Addresses'

    def __str__(self):
        return f"{self.recipient_name}: {self.address_line1}, {self.city}"

    def save(self, *args, **kwargs):
        if self.is_default:
            CustomerAddress.objects.filter(
                customer=self.customer,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class Cart(models.Model):
    """
    Persistent shopping cart. Associated with a Vendor (tenant).
    Supports logged-in customers as well as anonymous session-based carts.
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='carts')
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='carts',
        null=True,
        blank=True
    )
    session_key = models.CharField(max_length=255, null=True, blank=True)
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ch_carts'
        verbose_name = 'Cart'
        verbose_name_plural = 'Carts'

    def __str__(self):
        if self.customer:
            return f"Cart of {self.customer} ({self.vendor.business_name})"
        return f"Guest Cart {self.session_key[:8] if self.session_key else ''} ({self.vendor.business_name})"

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def total_price(self):
        return sum(item.total_cost for item in self.items.all())


class CartItem(models.Model):
    """
    Line items inside a shopping cart.
    """
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='cart_items')
    quantity = models.PositiveIntegerField(default=1)
    customization_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'ch_cart_items'
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'

    @property
    def unit_price(self):
        if self.customization_data and self.customization_data.get('is_customized'):
            try:
                from decimal import Decimal, InvalidOperation
                base = Decimal(str(self.customization_data.get('_base_price', self.product_variant.price)))
                fee = Decimal(str(self.customization_data.get('_custom_fee', '0.00')))
                return base + fee
            except (ValueError, TypeError, Exception):
                pass
        return self.product_variant.price

    @property
    def custom_fee(self):
        if self.customization_data:
            return self.customization_data.get('_custom_fee', '0.00')
        return '0.00'

    @property
    def total_cost(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.product_variant.sku} x {self.quantity}"


class Order(models.Model):
    """
    Customer orders placed on a storefront. Scoped per vendor.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('awaiting_approval', 'Awaiting Approval'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('cod', 'Cash on Delivery (COD)'),
        ('online', 'Online Payment'),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='orders')
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders'
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='orders')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    order_number = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Pricing fields
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    delivery_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    # Address snapshot
    shipping_name = models.CharField(max_length=150)
    shipping_phone = models.CharField(max_length=15)
    shipping_address = models.TextField()

    # Payment info
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cod')
    
    # Gateway tracking (Razorpay/Stripe details)
    gateway_order_id = models.CharField(max_length=100, blank=True, null=True)
    gateway_payment_id = models.CharField(max_length=100, blank=True, null=True)
    gateway_signature = models.CharField(max_length=255, blank=True, null=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ch_orders'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        unique_together = ('vendor', 'order_number')

    def __str__(self):
        name = self.customer.get_short_name()
        return f"{self.order_number} — {name} ({self.status})"


class OrderItem(models.Model):
    """
    Items fulfilled in a customer order.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name='order_items')
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Capture price at time of purchase
    total_cost = models.DecimalField(max_digits=12, decimal_places=2)
    customization_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'ch_order_items'
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def save(self, *args, **kwargs):
        self.total_cost = self.quantity * self.price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_variant.sku} x {self.quantity}"


class ContactMessage(models.Model):
    """
    Messages submitted via the Contact Us page on the storefront.
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='contact_messages')
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ch_contact_messages'
        verbose_name = 'Contact Message'
        verbose_name_plural = 'Contact Messages'
        ordering = ['-created_at']

    def __str__(self):
        return f"Message from {self.name} to {self.vendor.business_name}"

class CarouselSlide(models.Model):
    """
    Dynamic slides for the storefront hero section.
    """
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name='carousel_slides')
    label = models.CharField(max_length=100, blank=True, help_text="e.g. MAISON ATELIER — NEW COLLECTION")
    title = models.CharField(max_length=255, help_text="Main heading. You can use HTML like <br> and <span>.")
    description = models.TextField(blank=True)
    button_text = models.CharField(max_length=50, blank=True, default="Explore Details")
    button_link = models.CharField(max_length=255, blank=True, default="#")
    image = models.ImageField(upload_to='carousel_images/', help_text="Recommended size: 1920x1080px (16:9 Aspect Ratio) or 2000x1200px")
    order = models.PositiveIntegerField(default=0, help_text="Sequence order of the slide")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ch_carousel_slides'
        verbose_name = 'Carousel Slide'
        verbose_name_plural = 'Carousel Slides'
        ordering = ['order']

    def __str__(self):
        return f"Slide {self.order} ({self.vendor.business_name})"
