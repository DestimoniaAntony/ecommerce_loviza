from django.test import TestCase
from django.urls import reverse
from django.conf import settings
from decimal import Decimal

from tenants.models import Vendor, SubscriptionPlan, VendorSubscription
from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import BranchInventory, StockAdjustmentLog
from accounts.models import User
from storefront.models import CustomerAddress, Cart, CartItem, Order, OrderItem
from unittest.mock import patch
import datetime


class StorefrontTestCase(TestCase):
    def setUp(self):
        # 1. Setup Subscription Plan
        self.plan = SubscriptionPlan.objects.create(
            name="Starter Plan",
            plan_type="starter",
            billing_cycle="monthly",
            price=Decimal("999.00"),
            is_active=True
        )

        # 2. Setup Vendors (Tenants)
        self.vendor_a = Vendor.objects.create(
            business_name="Acme Cakes",
            slug="acmecakes",
            phone="9876543210",
            status="approved",
            is_active=True
        )
        self.vendor_b = Vendor.objects.create(
            business_name="Baker Street",
            slug="bakerstreet",
            phone="9876543211",
            status="approved",
            is_active=True
        )

        # Create active subscriptions
        today = datetime.date.today()
        future_date = today + datetime.timedelta(days=30)
        VendorSubscription.objects.create(
            vendor=self.vendor_a,
            plan=self.plan,
            start_date=today,
            end_date=future_date,
            is_active=True
        )
        VendorSubscription.objects.create(
            vendor=self.vendor_b,
            plan=self.plan,
            start_date=today,
            end_date=future_date,
            is_active=True
        )

        # 3. Setup Branches (needed for order fulfillment)
        self.branch_a = Branch.objects.create(
            vendor=self.vendor_a,
            name="Acme Main Branch",
            code="ACME-MAIN",
            phone="9876543210",
            is_main_branch=True,
            is_active=True
        )
        self.branch_b = Branch.objects.create(
            vendor=self.vendor_b,
            name="Baker Main Branch",
            code="BAKER-MAIN",
            phone="9876543211",
            is_main_branch=True,
            is_active=True
        )

        # 4. Setup Categories
        self.category_a = Category.objects.create(
            vendor=self.vendor_a,
            name="Chocolate Cakes",
            slug="chocolate-cakes",
            is_active=True
        )
        self.category_b = Category.objects.create(
            vendor=self.vendor_b,
            name="Breads",
            slug="breads",
            is_active=True
        )

        # 5. Setup Products and Variants
        self.product_a = Product.objects.create(
            vendor=self.vendor_a,
            category=self.category_a,
            name="Fudge Cake",
            slug="fudge-cake",
            status="published"
        )
        self.variant_a = ProductVariant.objects.create(
            product=self.product_a,
            name="1kg",
            sku="ACME-FUDGE-1KG",
            price=Decimal("450.00"),
            stock_qty=Decimal("15.00"),
            is_active=True
        )

        self.product_b = Product.objects.create(
            vendor=self.vendor_b,
            category=self.category_b,
            name="Sourdough Bread",
            slug="sourdough-bread",
            status="published"
        )
        self.variant_b = ProductVariant.objects.create(
            product=self.product_b,
            name="Standard",
            sku="BAKER-SOURDOUGH",
            price=Decimal("150.00"),
            stock_qty=Decimal("10.00"),
            is_active=True
        )

        # Retrieve auto-created Branch Inventories (initialized via signals)
        self.inv_a = BranchInventory.objects.get(
            branch=self.branch_a,
            product_variant=self.variant_a
        )
        self.inv_b = BranchInventory.objects.get(
            branch=self.branch_b,
            product_variant=self.variant_b
        )

        # 6. Setup Customers (standard accounts.User with user_type='customer' scoped by vendor)
        self.customer_a = User.objects.create_user(
            phone="9000000001",
            password="customerpassword123",
            first_name="Alice",
            user_type="customer",
            vendor=self.vendor_a,
            is_active=True
        )
        self.customer_b = User.objects.create_user(
            phone="9000000002",
            password="customerpassword123",
            first_name="Bob",
            user_type="customer",
            vendor=self.vendor_b,
            is_active=True
        )

        # Address for Customer A
        self.address_a = CustomerAddress.objects.create(
            customer=self.customer_a,
            recipient_name="Alice Green",
            phone="9000000001",
            address_line1="Apartment 4B, Cake Towers",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            is_default=True
        )

        # Domain headers for request routing simulation
        self.host_a = f"{self.vendor_a.slug}.{getattr(settings, 'PLATFORM_DOMAIN', 'commercehub.in')}"
        self.host_b = f"{self.vendor_b.slug}.{getattr(settings, 'PLATFORM_DOMAIN', 'commercehub.in')}"
        self.platform_host = getattr(settings, 'PLATFORM_DOMAIN', 'commercehub.in')

    # ── 1. BROWSING & ACCESS CONTROL TESTS ──

    def test_homepage_subdomain_access(self):
        """
        Accessing the storefront homepage via a tenant's subdomain.
        """
        response = self.client.get(reverse('storefront:home'), HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.vendor_a.business_name)
        self.assertContains(response, "Fudge Cake")
        self.assertNotContains(response, "Sourdough Bread")

    def test_homepage_platform_root_redirect(self):
        """
        Accessing the bare platform domain redirects to the admin login page.
        """
        response = self.client.get(reverse('storefront:home'), HTTP_HOST=self.platform_host)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:admin_login'), response.url)

    def test_product_catalog_filters(self):
        """
        Verifies catalog filters (by category slug or query parameter).
        """
        # Catalog under Vendor A
        response = self.client.get(reverse('storefront:catalog'), HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fudge Cake")

        # Catalog filtered by Vendor A Category
        response_cat = self.client.get(
            reverse('storefront:catalog') + f"?category={self.category_a.slug}",
            HTTP_HOST=self.host_a
        )
        self.assertEqual(response_cat.status_code, 200)
        self.assertContains(response_cat, "Fudge Cake")

        # Search Query test
        response_search = self.client.get(
            reverse('storefront:catalog') + "?q=Fudge",
            HTTP_HOST=self.host_a
        )
        self.assertEqual(response_search.status_code, 200)
        self.assertContains(response_search, "Fudge Cake")

        # Empty search results
        response_empty = self.client.get(
            reverse('storefront:catalog') + "?q=Bread",
            HTTP_HOST=self.host_a
        )
        self.assertEqual(response_empty.status_code, 200)
        self.assertContains(response_empty, "No Products Found")

    def test_product_detail_page(self):
        """
        Product details page loads and contains the variant attributes.
        """
        response = self.client.get(
            reverse('storefront:product_detail', kwargs={'slug': self.product_a.slug}),
            HTTP_HOST=self.host_a
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fudge Cake")
        self.assertContains(response, "ACME-FUDGE-1KG")
        self.assertContains(response, "450.00")

    # ── 2. SHOPPING CART OPERATIONS TESTS ──

    def test_cart_operations_guest(self):
        """
        A guest can add, update, and remove items in their session-based cart.
        """
        # 1. Add item
        add_url = reverse('storefront:cart_add')
        response = self.client.post(
            add_url,
            {'variant_id': self.variant_a.id, 'quantity': 2},
            HTTP_HOST=self.host_a
        )
        self.assertEqual(response.status_code, 302) # Redirects to cart

        # Verify cart model is created
        cart = Cart.objects.filter(vendor=self.vendor_a, customer=None).first()
        self.assertIsNotNone(cart)
        self.assertEqual(cart.items.count(), 1)
        
        cart_item = cart.items.first()
        self.assertEqual(cart_item.product_variant, self.variant_a)
        self.assertEqual(cart_item.quantity, 2)
        self.assertEqual(cart.total_price, Decimal("900.00")) # 450 * 2

        # 2. Update quantity
        update_url = reverse('storefront:cart_update')
        self.client.post(
            update_url,
            {'item_id': cart_item.id, 'quantity': 5},
            HTTP_HOST=self.host_a
        )
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 5)

        # 3. Remove item
        remove_url = reverse('storefront:cart_remove')
        self.client.post(
            remove_url,
            {'item_id': cart_item.id},
            HTTP_HOST=self.host_a
        )
        self.assertEqual(cart.items.count(), 0)

    def test_cart_merging_on_login(self):
        """
        Guest cart items merge into customer's profile cart on successful login.
        """
        # Create a session cart for guest
        add_url = reverse('storefront:cart_add')
        self.client.post(
            add_url,
            {'variant_id': self.variant_a.id, 'quantity': 3},
            HTTP_HOST=self.host_a
        )

        # Verify guest cart exists
        guest_cart = Cart.objects.filter(vendor=self.vendor_a, customer=None).first()
        self.assertIsNotNone(guest_cart)
        self.assertEqual(guest_cart.items.first().quantity, 3)

        # Perform customer login
        login_url = reverse('storefront:login')
        response = self.client.post(
            login_url,
            {'phone': self.customer_a.phone, 'password': 'customerpassword123'},
            HTTP_HOST=self.host_a
        )
        self.assertEqual(response.status_code, 302)

        # Verify that guest cart was deleted and merged into customer_a's cart
        self.assertFalse(Cart.objects.filter(pk=guest_cart.pk).exists())

        customer_cart = Cart.objects.filter(vendor=self.vendor_a, customer=self.customer_a).first()
        self.assertIsNotNone(customer_cart)
        self.assertEqual(customer_cart.items.count(), 1)
        self.assertEqual(customer_cart.items.first().quantity, 3)

    # ── 3. CHECKOUT & ATOMIC ORDER TRANSACTIONS TESTS ──

    def test_checkout_validation_empty_cart(self):
        """
        A customer cannot check out if their cart is empty.
        """
        self.client.login(phone=self.customer_a.phone, password="customerpassword123")
        response = self.client.get(reverse('storefront:checkout'), HTTP_HOST=self.host_a)
        # Should redirect back to cart view with warning
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('storefront:cart'))

    def test_checkout_delivery_charge_calculation(self):
        """
        Test delivery charge calculations: under 1000 incurs 50, over 1000 is free.
        """
        self.client.login(phone=self.customer_a.phone, password="customerpassword123")
        
        # Add 1 item (Total: 450)
        self.client.post(reverse('storefront:cart_add'), {'variant_id': self.variant_a.id, 'quantity': 1}, HTTP_HOST=self.host_a)
        response_under = self.client.get(reverse('storefront:checkout'), HTTP_HOST=self.host_a)
        self.assertEqual(response_under.context['delivery_charge'], Decimal('50.00'))
        self.assertEqual(response_under.context['grand_total'], Decimal('500.00'))

        # Add 2 more items (Total: 1350)
        self.client.post(reverse('storefront:cart_add'), {'variant_id': self.variant_a.id, 'quantity': 2}, HTTP_HOST=self.host_a)
        response_over = self.client.get(reverse('storefront:checkout'), HTTP_HOST=self.host_a)
        self.assertEqual(response_over.context['delivery_charge'], Decimal('0.00'))
        self.assertEqual(response_over.context['grand_total'], Decimal('1350.00'))

    def test_atomic_order_placement_and_stock_deduction(self):
        """
        Successful checkout places order, deducts stock, adjusts audit logs, and clears cart.
        """
        self.client.login(phone=self.customer_a.phone, password="customerpassword123")
        
        # 1. Add item to cart
        self.client.post(reverse('storefront:cart_add'), {'variant_id': self.variant_a.id, 'quantity': 4}, HTTP_HOST=self.host_a)

        # 2. Place order using saved address
        place_url = reverse('storefront:place_order')
        response = self.client.post(
            place_url,
            {'address_id': self.address_a.id, 'payment_method': 'cod', 'notes': 'Handle with care'},
            HTTP_HOST=self.host_a
        )
        
        # Check order exists
        order = Order.objects.filter(vendor=self.vendor_a, customer=self.customer_a).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.subtotal_amount, Decimal('1800.00')) # 450 * 4
        self.assertEqual(order.delivery_charge, Decimal('0.00')) # free since > 1000
        self.assertEqual(order.total_amount, Decimal('1800.00'))
        self.assertEqual(order.shipping_name, "Alice Green")
        self.assertEqual(order.notes, "Handle with care")

        # Verify redirect to success screen
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('storefront:order_success', kwargs={'order_id': order.id}), response.url)

        # Verify order items are created
        self.assertEqual(order.items.count(), 1)
        order_item = order.items.first()
        self.assertEqual(order_item.product_variant, self.variant_a)
        self.assertEqual(order_item.quantity, 4)
        self.assertEqual(order_item.price, Decimal('450.00'))

        # Verify stock decrement at Acme Main Branch
        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.stock_qty, Decimal('11.00')) # 15 - 4

        # Verify stock adjustment log entry
        adjustment_log = StockAdjustmentLog.objects.filter(vendor=self.vendor_a, product_variant=self.variant_a).first()
        self.assertIsNotNone(adjustment_log)
        self.assertEqual(adjustment_log.quantity_changed, Decimal('-4.00'))
        self.assertEqual(adjustment_log.reason, 'other')
        self.assertIn(order.order_number, adjustment_log.notes)

        # Verify cart is now empty
        cart = Cart.objects.filter(vendor=self.vendor_a, customer=self.customer_a).first()
        self.assertEqual(cart.items.count(), 0)

    # ── 4. MULTI-TENANT ISOLATION TESTS ──

    def test_tenant_cart_isolation(self):
        """
        Customers cannot access or view carts of other vendors/tenants.
        """
        # Customer A logs in on Vendor B's storefront
        self.client.login(phone=self.customer_a.phone, password="customerpassword123")
        
        # Add item to Vendor B's storefront
        self.client.post(
            reverse('storefront:cart_add'),
            {'variant_id': self.variant_b.id, 'quantity': 1},
            HTTP_HOST=self.host_b
        )
        
        # Cart for Vendor B under customer_a should be separate
        cart_b = Cart.objects.filter(vendor=self.vendor_b, customer=self.customer_a).first()
        self.assertIsNotNone(cart_b)
        self.assertEqual(cart_b.items.first().product_variant, self.variant_b)

        # Verify cart_a does not show variant_b
        cart_a = Cart.objects.filter(vendor=self.vendor_a, customer=self.customer_a).first()
        self.assertIsNone(cart_a) # No cart created under Vendor A yet

    def test_tenant_order_isolation(self):
        """
        Verify that placing order on Vendor A storefront scope does not affect Vendor B.
        """
        self.client.login(phone=self.customer_a.phone, password="customerpassword123")
        self.client.post(reverse('storefront:cart_add'), {'variant_id': self.variant_a.id, 'quantity': 1}, HTTP_HOST=self.host_a)
        
        # Place order on Vendor A storefront
        self.client.post(
            reverse('storefront:place_order'),
            {'address_id': self.address_a.id, 'payment_method': 'cod'},
            HTTP_HOST=self.host_a
        )
        
        # Verify order belongs only to Vendor A
        self.assertEqual(Order.objects.filter(vendor=self.vendor_a).count(), 1)
        self.assertEqual(Order.objects.filter(vendor=self.vendor_b).count(), 0)

    @patch('razorpay.Client')
    def test_online_payment_workflow(self, mock_razorpay_client):
        """
        Verify that place_order initiates Razorpay checkout creation and returns JSON response.
        """
        # Setup mock behavior
        mock_instance = mock_razorpay_client.return_value
        mock_instance.order.create.return_value = {'id': 'rzp_test_order_123'}

        # Configure Vendor checkout settings
        self.vendor_a.checkout_workflow = 'online_payment'
        self.vendor_a.razorpay_key_id = 'test_key'
        self.vendor_a.razorpay_key_secret = 'test_secret'
        self.vendor_a.save()

        self.client.login(phone=self.customer_a.phone, password="customerpassword123")
        self.client.post(reverse('storefront:cart_add'), {'variant_id': self.variant_a.id, 'quantity': 2}, HTTP_HOST=self.host_a)

        # Place order using AJAX method online
        response = self.client.post(
            reverse('storefront:place_order'),
            {
                'address_id': self.address_a.id,
                'payment_method': 'online',
                'is_ajax': '1'
            },
            HTTP_HOST=self.host_a,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['checkout_type'], 'online')
        self.assertEqual(data['razorpay_order_id'], 'rzp_test_order_123')

        # Verify order was saved as pending but stock was NOT deducted yet
        order = Order.objects.get(pk=data['order_id'])
        self.assertEqual(order.payment_status, 'pending')
        self.assertEqual(order.gateway_order_id, 'rzp_test_order_123')
        
        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.stock_qty, Decimal('15.00')) # Stock remains unchanged

    @patch('razorpay.Client')
    def test_payment_verification_success(self, mock_razorpay_client):
        """
        Verify that PaymentVerifyView marks order as paid, deducts stock, and clears cart on signature success.
        """
        mock_instance = mock_razorpay_client.return_value
        mock_instance.order.create.return_value = {'id': 'rzp_test_order_123'}
        mock_instance.utility.verify_payment_signature.return_value = True

        self.vendor_a.checkout_workflow = 'online_payment'
        self.vendor_a.razorpay_key_id = 'test_key'
        self.vendor_a.razorpay_key_secret = 'test_secret'
        self.vendor_a.save()

        # Create a pending order
        self.client.login(phone=self.customer_a.phone, password="customerpassword123")
        self.client.post(reverse('storefront:cart_add'), {'variant_id': self.variant_a.id, 'quantity': 2}, HTTP_HOST=self.host_a)
        
        response = self.client.post(
            reverse('storefront:place_order'),
            {
                'address_id': self.address_a.id,
                'payment_method': 'online',
                'is_ajax': '1'
            },
            HTTP_HOST=self.host_a,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        order_id = response.json()['order_id']

        # Call verify endpoint
        json_data = {
            'order_id': order_id,
            'razorpay_payment_id': 'pay_123',
            'razorpay_order_id': 'rzp_test_order_123',
            'razorpay_signature': 'signature_123'
        }
        verify_response = self.client.post(
            reverse('storefront:verify_payment'),
            data=json_data,
            content_type='application/json',
            HTTP_HOST=self.host_a
        )
        self.assertEqual(verify_response.status_code, 200)
        verify_data = verify_response.json()
        self.assertEqual(verify_data['status'], 'success')

        # Verify order state is updated and stock is now deducted
        order = Order.objects.get(pk=order_id)
        self.assertEqual(order.payment_status, 'paid')
        self.assertEqual(order.status, 'processing')
        self.assertEqual(order.gateway_payment_id, 'pay_123')

        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.stock_qty, Decimal('13.00')) # 15 - 2

    def test_whatsapp_enquiry_workflow(self):
        """
        Verify that WhatsApp Enquiry workflow redirects correctly and compiles message placeholders.
        """
        self.vendor_a.checkout_workflow = 'whatsapp_enquiry'
        self.vendor_a.whatsapp_number = '919876543210'
        self.vendor_a.whatsapp_order_format = "Order Number: {order_number} and Total: {total_amount}"
        self.vendor_a.save()

        self.client.login(phone=self.customer_a.phone, password="customerpassword123")
        self.client.post(reverse('storefront:cart_add'), {'variant_id': self.variant_a.id, 'quantity': 2}, HTTP_HOST=self.host_a)

        # Place order
        response = self.client.post(
            reverse('storefront:place_order'),
            {
                'address_id': self.address_a.id,
                'payment_method': 'cod'
            },
            HTTP_HOST=self.host_a
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('wa.me/919876543210', response.url)
        self.assertIn('Order%20Number', response.url)
        
        # Verify order is saved, stock is deducted, cart is cleared
        order = Order.objects.filter(vendor=self.vendor_a, customer=self.customer_a).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.payment_status, 'pending')
        
        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.stock_qty, Decimal('13.00'))

    def test_approval_payment_workflow(self):
        """
        Verify that Approval then Payment workflow saves order as awaiting_approval and clears cart.
        """
        self.vendor_a.checkout_workflow = 'approval_payment'
        self.vendor_a.save()

        self.client.login(phone=self.customer_a.phone, password="customerpassword123")
        self.client.post(reverse('storefront:cart_add'), {'variant_id': self.variant_a.id, 'quantity': 2}, HTTP_HOST=self.host_a)

        # Place order
        response = self.client.post(
            reverse('storefront:place_order'),
            {
                'address_id': self.address_a.id,
                'payment_method': 'cod'
            },
            HTTP_HOST=self.host_a
        )
        self.assertEqual(response.status_code, 302)
        
        # Verify order is saved with awaiting_approval status, stock is NOT deducted, cart is cleared
        order = Order.objects.filter(vendor=self.vendor_a, customer=self.customer_a).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, 'awaiting_approval')
        self.assertEqual(order.payment_status, 'pending')
        
        self.inv_a.refresh_from_db()
        self.assertEqual(self.inv_a.stock_qty, Decimal('15.00')) # stock NOT deducted

        cart = Cart.objects.filter(vendor=self.vendor_a, customer=self.customer_a).first()
        self.assertEqual(cart.items.count(), 0) # cart is cleared
