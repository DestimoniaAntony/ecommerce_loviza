from django.test import TestCase
from django.urls import reverse
from decimal import Decimal
from accounts.models import User
from tenants.models import Vendor
from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import BranchInventory, StockAdjustmentLog
from storefront.models import Order, OrderItem

class VendorOrdersTestCase(TestCase):
    def setUp(self):
        # 1. Create Vendors
        self.vendor_a = Vendor.objects.create(
            business_name="Vendor A",
            slug="vendora",
            phone="1111111111",
            status="approved",
            is_active=True
        )
        self.vendor_b = Vendor.objects.create(
            business_name="Vendor B",
            slug="vendorb",
            phone="2222222222",
            status="approved",
            is_active=True
        )

        # 2. Create Branches
        self.branch_a = Branch.objects.create(
            vendor=self.vendor_a,
            name="Branch A Main",
            code="AMAIN",
            phone="1111111111",
            is_main_branch=True,
            is_active=True
        )
        self.branch_b = Branch.objects.create(
            vendor=self.vendor_b,
            name="Branch B Main",
            code="BMAIN",
            phone="2222222222",
            is_main_branch=True,
            is_active=True
        )

        # 3. Create Vendor Users
        self.user_a = User.objects.create_user(
            phone="1111111111",
            password="password123",
            user_type="vendor",
            vendor=self.vendor_a
        )
        self.user_b = User.objects.create_user(
            phone="2222222222",
            password="password123",
            user_type="vendor",
            vendor=self.vendor_b
        )

        # 4. Create Customers
        self.customer_a = User.objects.create_user(
            phone="9000000001",
            password="password123",
            user_type="customer",
            vendor=self.vendor_a
        )

        # 5. Create Catalog & Stock for Vendor A
        self.category_a = Category.objects.create(
            vendor=self.vendor_a,
            name="Cakes",
            slug="cakes",
            is_active=True
        )
        self.product_a = Product.objects.create(
            vendor=self.vendor_a,
            category=self.category_a,
            name="Chocolate Cake",
            slug="chocolate-cake",
            status="published"
        )
        self.variant_a = ProductVariant.objects.create(
            product=self.product_a,
            name="1kg",
            sku="V-A-1KG",
            price=Decimal("500.00"),
            stock_qty=Decimal("10.00"),
            is_active=True
        )
        # Verify Branch Inventory setup (created automatically by signals)
        self.bi_a = BranchInventory.objects.get(
            branch=self.branch_a,
            product_variant=self.variant_a
        )
        self.bi_a.stock_qty = Decimal("10.00")
        self.bi_a.save()

        # 6. Create Orders
        self.order_awaiting = Order.objects.create(
            vendor=self.vendor_a,
            customer=self.customer_a,
            branch=self.branch_a,
            order_number="ORD-100",
            status="awaiting_approval",
            subtotal_amount=Decimal("500.00"),
            total_amount=Decimal("500.00"),
            shipping_name="Alice",
            shipping_phone="9000000001",
            shipping_address="Test Address",
            payment_method="cod",
            payment_status="pending"
        )
        self.item_awaiting = OrderItem.objects.create(
            order=self.order_awaiting,
            product_variant=self.variant_a,
            quantity=2,
            price=Decimal("500.00"),
            total_cost=Decimal("1000.00")
        )

        self.order_pending = Order.objects.create(
            vendor=self.vendor_a,
            customer=self.customer_a,
            branch=self.branch_a,
            order_number="ORD-101",
            status="pending",
            subtotal_amount=Decimal("500.00"),
            total_amount=Decimal("500.00"),
            shipping_name="Alice",
            shipping_phone="9000000001",
            shipping_address="Test Address",
            payment_method="cod",
            payment_status="pending"
        )
        self.item_pending = OrderItem.objects.create(
            order=self.order_pending,
            product_variant=self.variant_a,
            quantity=1,
            price=Decimal("500.00"),
            total_cost=Decimal("500.00")
        )

        # Order for Vendor B (to test tenant isolation)
        self.order_b = Order.objects.create(
            vendor=self.vendor_b,
            customer=self.customer_a,
            branch=self.branch_b,
            order_number="ORD-200",
            status="pending",
            subtotal_amount=Decimal("500.00"),
            total_amount=Decimal("500.00"),
            shipping_name="Bob",
            shipping_phone="9000000002",
            shipping_address="Test Address B",
            payment_method="cod",
            payment_status="pending"
        )

    def test_order_list_requires_login(self):
        response = self.client.get(reverse('commercehub_app:order_list'))
        self.assertRedirects(response, reverse('accounts:vendor_login'))

    def test_order_list_vendor_scoping_and_filtering(self):
        self.client.force_login(self.user_a)
        
        # 1. Access main list (should show Vendor A's orders, NOT Vendor B's)
        response = self.client.get(reverse('commercehub_app:order_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ORD-100")
        self.assertContains(response, "ORD-101")
        self.assertNotContains(response, "ORD-200")

        # 2. Filter by status 'awaiting_approval'
        response = self.client.get(reverse('commercehub_app:order_list') + '?status=awaiting_approval')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ORD-100")
        self.assertNotContains(response, "ORD-101")

    def test_order_detail_scoping(self):
        self.client.force_login(self.user_a)
        
        # 1. View own order
        response = self.client.get(reverse('commercehub_app:order_detail', kwargs={'pk': self.order_awaiting.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ORD-100")
        self.assertContains(response, "Awaiting Approval")

        # 2. View another vendor's order (should yield 404)
        response = self.client.get(reverse('commercehub_app:order_detail', kwargs={'pk': self.order_b.pk}))
        self.assertEqual(response.status_code, 404)

    def test_order_approval_action(self):
        self.client.force_login(self.user_a)
        
        # Verify initial branch stock is 10
        bi = BranchInventory.objects.get(branch=self.branch_a, product_variant=self.variant_a)
        self.assertEqual(bi.stock_qty, Decimal("10.00"))
        
        # Approve order ORD-100 (which has quantity 2 of variant_a)
        response = self.client.post(
            reverse('commercehub_app:order_action', kwargs={'pk': self.order_awaiting.pk}),
            {'action': 'approve'}
        )
        
        # Check redirect
        self.assertRedirects(response, reverse('commercehub_app:order_detail', kwargs={'pk': self.order_awaiting.pk}))
        
        # Verify order status became 'pending'
        self.order_awaiting.refresh_from_db()
        self.assertEqual(self.order_awaiting.status, 'pending')
        
        # Verify stock decreased by 2 (10 - 2 = 8)
        bi.refresh_from_db()
        self.assertEqual(bi.stock_qty, Decimal("8.00"))
        
        # Verify stock adjustment log was created
        log = StockAdjustmentLog.objects.filter(
            vendor=self.vendor_a,
            branch=self.branch_a,
            product_variant=self.variant_a,
            quantity_changed=-2
        )
        self.assertTrue(log.exists())

    def test_order_cancellation_restocks_inventory(self):
        self.client.force_login(self.user_a)

        # Deduct inventory first by setting order_pending status from pending to cancelled
        # (ORD-101 has quantity 1 of variant_a).
        # We start with 10 stock. Since ORD-101 was already placed as 'pending',
        # let's confirm cancelling it adds stock back (restocks it).
        # Wait, the views.py transitions from non-cancelled/non-awaiting_approval to cancelled by adding stock.
        # Let's verify:
        bi = BranchInventory.objects.get(branch=self.branch_a, product_variant=self.variant_a)
        self.assertEqual(bi.stock_qty, Decimal("10.00"))

        response = self.client.post(
            reverse('commercehub_app:order_action', kwargs={'pk': self.order_pending.pk}),
            {'action': 'update_status', 'status': 'cancelled'}
        )
        self.assertRedirects(response, reverse('commercehub_app:order_detail', kwargs={'pk': self.order_pending.pk}))

        self.order_pending.refresh_from_db()
        self.assertEqual(self.order_pending.status, 'cancelled')

        # Stock should increase from 10 to 11
        bi.refresh_from_db()
        self.assertEqual(bi.stock_qty, Decimal("11.00"))

        # Verify adjustment log
        log = StockAdjustmentLog.objects.filter(
            vendor=self.vendor_a,
            branch=self.branch_a,
            product_variant=self.variant_a,
            quantity_changed=1
        )
        self.assertTrue(log.exists())

    def test_order_payment_status_update(self):
        self.client.force_login(self.user_a)
        
        # Verify initial payment status is pending (unpaid)
        self.assertEqual(self.order_pending.payment_status, 'pending')
        
        # Update payment status to paid
        response = self.client.post(
            reverse('commercehub_app:order_action', kwargs={'pk': self.order_pending.pk}),
            {'action': 'update_payment_status', 'payment_status': 'paid'}
        )
        self.assertRedirects(response, reverse('commercehub_app:order_detail', kwargs={'pk': self.order_pending.pk}))
        
        self.order_pending.refresh_from_db()
        self.assertEqual(self.order_pending.payment_status, 'paid')


class AnalyticsDashboardTestCase(TestCase):
    """Tests for the Phase 8 Analytics Dashboard — KPIs, isolation, and CSV exports."""

    def setUp(self):
        self.vendor_a = Vendor.objects.create(
            business_name="Analytics Vendor A", slug="analyticsvendora",
            phone="7100000001", status="approved", is_active=True
        )
        self.vendor_b = Vendor.objects.create(
            business_name="Analytics Vendor B", slug="analyticsvendorb",
            phone="7200000001", status="approved", is_active=True
        )
        self.branch_a = Branch.objects.create(
            vendor=self.vendor_a, name="Branch A", code="ATEST",
            phone="7100000001", is_main_branch=True, is_active=True
        )
        self.user_a = User.objects.create_user(
            phone="7100000001", password="pass123",
            user_type="vendor", vendor=self.vendor_a
        )
        self.user_b = User.objects.create_user(
            phone="7200000001", password="pass123",
            user_type="vendor", vendor=self.vendor_b
        )
        self.customer = User.objects.create_user(
            phone="7300000001", password="pass123",
            user_type="customer", vendor=self.vendor_a
        )
        self.category = Category.objects.create(
            vendor=self.vendor_a, name="Pastries", slug="pastries-analytics", is_active=True
        )
        self.product = Product.objects.create(
            vendor=self.vendor_a, category=self.category,
            name="Croissant", slug="croissant-analytics", status="published"
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, name="Plain", sku="CRO-ANALYTICS-001",
            price=Decimal("150.00"), stock_qty=Decimal("20.00"), is_active=True
        )
        # 2 paid orders for Vendor A totalling ₹900
        for i, amt in enumerate([Decimal("400.00"), Decimal("500.00")], start=1):
            o = Order.objects.create(
                vendor=self.vendor_a, customer=self.customer,
                branch=self.branch_a, order_number=f"ANA-{i:03d}",
                status="delivered", subtotal_amount=amt, total_amount=amt,
                shipping_name="Test", shipping_phone="7300000001",
                shipping_address="Addr", payment_method="online",
                payment_status="paid"
            )
            OrderItem.objects.create(
                order=o, product_variant=self.variant,
                quantity=1, price=amt, total_cost=amt
            )

    def test_dashboard_requires_login(self):
        """Unauthenticated users are redirected to the vendor login page."""
        response = self.client.get(reverse('commercehub_app:dashboard'))
        self.assertRedirects(response, reverse('accounts:vendor_login'))

    def test_dashboard_kpi_values(self):
        """Dashboard context reflects correct revenue totals from seeded orders."""
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('commercehub_app:dashboard') + '?range=30d')
        self.assertEqual(response.status_code, 200)

        ctx = response.context
        # Total revenue should be sum of 2 paid orders = 900
        self.assertEqual(ctx['total_revenue'], Decimal('900.00'))
        # Total orders should be 2
        self.assertEqual(ctx['total_orders'], 2)
        # Pending orders should be 0
        self.assertEqual(ctx['pending_orders'], 0)
        # 1 distinct customer
        self.assertEqual(ctx['active_customers'], 1)
        # Top products should include our product
        self.assertTrue(len(ctx['top_products']) > 0)

    def test_dashboard_vendor_isolation(self):
        """Vendor B's dashboard shows zero data; Vendor A's data is not leaked."""
        self.client.force_login(self.user_b)
        response = self.client.get(reverse('commercehub_app:dashboard') + '?range=30d')
        self.assertEqual(response.status_code, 200)

        ctx = response.context
        # Vendor B has no orders — all KPIs should be zero
        self.assertEqual(ctx['total_revenue'], Decimal('0.00'))
        self.assertEqual(ctx['total_orders'], 0)
        self.assertEqual(ctx['active_customers'], 0)
        # Top products should be empty
        self.assertEqual(len(ctx['top_products']), 0)

    def test_export_orders_csv(self):
        """CSV export returns a valid CSV file with correct order data."""
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('commercehub_app:export_orders') + '?range=30d')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode('utf-8')
        self.assertIn('Order #', content)
        self.assertIn('ANA-001', content)
        self.assertIn('ANA-002', content)

    def test_export_products_csv(self):
        """Top products CSV export returns valid file with product names."""
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('commercehub_app:export_products') + '?range=30d')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        content = response.content.decode('utf-8')
        self.assertIn('Product Name', content)
        self.assertIn('Croissant', content)
        self.assertIn('CRO-ANALYTICS-001', content)
