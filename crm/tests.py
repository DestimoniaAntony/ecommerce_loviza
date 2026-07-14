from django.test import TestCase, Client
from django.urls import reverse
from django.db import models
from decimal import Decimal
import datetime
from accounts.models import User
from tenants.models import Vendor
from branches.models import Branch
from catalog.models import Category, Product, ProductVariant
from inventory.models import BranchInventory
from storefront.models import CustomerAddress, Cart, CartItem, Order, OrderItem
from crm.models import Coupon, Wallet, WalletTransaction, LoyaltyProgram, LoyaltyLedger

class CRMAppTestCase(TestCase):
    def setUp(self):
        # 1. Setup Vendors (A & B)
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

        # 2. Setup Main Branches
        self.branch_a = Branch.objects.create(
            vendor=self.vendor_a,
            name="Branch A",
            code="AMAIN",
            phone="1111111111",
            is_main_branch=True,
            is_active=True
        )
        self.branch_b = Branch.objects.create(
            vendor=self.vendor_b,
            name="Branch B",
            code="BMAIN",
            phone="2222222222",
            is_main_branch=True,
            is_active=True
        )

        # 3. Setup Staff and Customers
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
        self.customer_a = User.objects.create_user(
            phone="9000000001",
            password="password123",
            user_type="customer",
            vendor=self.vendor_a
        )
        self.address_a = CustomerAddress.objects.create(
            customer=self.customer_a,
            recipient_name="Alice",
            phone="9000000001",
            address_line1="Towers A",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            is_default=True
        )

        # 4. Setup Products and Variants
        self.category_a = Category.objects.create(vendor=self.vendor_a, name="Bakes", slug="bakes")
        self.product_a = Product.objects.create(vendor=self.vendor_a, category=self.category_a, name="Cake", slug="cake", status="published")
        self.variant_a = ProductVariant.objects.create(
            product=self.product_a,
            name="1kg",
            sku="V-A-1KG",
            price=Decimal("500.00"),
            stock_qty=Decimal("10.00"),
            is_active=True
        )

        # Setup Branch Inventory
        self.bi_a = BranchInventory.objects.get(branch=self.branch_a, product_variant=self.variant_a)
        self.bi_a.stock_qty = Decimal("10.00")
        self.bi_a.save()

        # Cart setup
        self.cart_a = Cart.objects.create(vendor=self.vendor_a, customer=self.customer_a)
        self.cart_item = CartItem.objects.create(cart=self.cart_a, product_variant=self.variant_a, quantity=2)

        # Host setups
        self.host_a = "vendora.localhost"
        self.host_b = "vendorb.localhost"

    def test_coupon_validation_and_application_ajax(self):
        # Create active coupon
        today = datetime.date.today()
        coupon = Coupon.objects.create(
            vendor=self.vendor_a,
            code="SAVE10",
            discount_type="percentage",
            discount_value=Decimal("10.00"),
            min_purchase=Decimal("200.00"),
            start_date=today - datetime.timedelta(days=1),
            end_date=today + datetime.timedelta(days=5),
            usage_limit=5
        )

        self.client.force_login(self.customer_a)
        
        # 1. Apply coupon via AJAX POST
        response = self.client.post(
            reverse('storefront:coupon_apply'),
            {'coupon_code': 'SAVE10'},
            HTTP_HOST=self.host_a,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(response.json()['discount_amount'], '100.00') # 10% of 1000 subtotal (2x500 variants)

        # 2. Check checkout page calculations
        response = self.client.get(reverse('storefront:checkout'), HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['coupon_discount'], Decimal('100.00'))
        self.assertEqual(response.context['grand_total'], Decimal('900.00')) # 1000 - 100 + 0 shipping (since >= 1000 is free)

        # 3. Check min purchase restriction
        coupon.min_purchase = Decimal("2000.00")
        coupon.save()
        response = self.client.post(
            reverse('storefront:coupon_apply'),
            {'coupon_code': 'SAVE10'},
            HTTP_HOST=self.host_a,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'error')

    def test_loyalty_earning_and_checkout_redemption(self):
        # Enable Loyalty Program
        program = LoyaltyProgram.objects.create(
            vendor=self.vendor_a,
            is_enabled=True,
            points_per_currency=Decimal("0.0200"), # 2 points per 1 unit spent (e.g. spend ₹100 = 2 points)
            currency_per_point=Decimal("0.50"),    # 1 point = ₹0.50 discount
            min_points_to_redeem=100
        )

        # Award points via LoyaltyLedger
        LoyaltyLedger.objects.create(
            vendor=self.vendor_a,
            customer=self.customer_a,
            points=200,
            transaction_type="earn"
        )

        self.client.force_login(self.customer_a)

        # Checkout page should list points
        response = self.client.get(reverse('storefront:checkout'), HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['loyalty_points'], 200)
        self.assertEqual(response.context['loyalty_discount_value'], Decimal("100.00")) # 200 * 0.50

        # Place order with points redemption (redeem_loyalty = 1)
        response = self.client.post(
            reverse('storefront:place_order'),
            {
                'address_id': self.address_a.pk,
                'payment_method': 'cod',
                'redeem_loyalty': '1'
            },
            HTTP_HOST=self.host_a
        )
        # Order total = 1000 subtotal. Discount = 100.00. Grand total = 900.00.
        order = Order.objects.get(vendor=self.vendor_a, customer=self.customer_a)
        self.assertEqual(order.total_amount, Decimal("900.00"))

        # Verify ledger entry created
        ledger_debit = LoyaltyLedger.objects.filter(
            vendor=self.vendor_a,
            customer=self.customer_a,
            points=-200,
            transaction_type="redeem"
        )
        self.assertTrue(ledger_debit.exists())

        # Verify points earning credited (since order status became pending and was paid/completed.
        # Wait, place_order credits points only if PAID immediately (like wallet). COD orders are credited when paid.
        # Let's mark COD as Paid manually via Vendor panel and check if points are earned!
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse('commercehub_app:order_action', kwargs={'pk': order.pk}),
            {'action': 'update_payment_status', 'payment_status': 'paid'}
        )
        self.assertEqual(response.status_code, 302)

        # Points earned: 900 total * 0.02 = 18 points.
        ledger_earn = LoyaltyLedger.objects.filter(
            vendor=self.vendor_a,
            customer=self.customer_a,
            points=18,
            transaction_type="earn"
        )
        self.assertTrue(ledger_earn.exists())

    def test_wallet_balance_and_order_checkout_payment(self):
        # Create wallet with credit balance
        wallet = Wallet.objects.create(vendor=self.vendor_a, customer=self.customer_a, balance=Decimal("1500.00"))

        self.client.force_login(self.customer_a)

        # Place order using wallet
        response = self.client.post(
            reverse('storefront:place_order'),
            {
                'address_id': self.address_a.pk,
                'payment_method': 'wallet'
            },
            HTTP_HOST=self.host_a
        )
        # Grand total is 1000.00. Wallet balance after purchase: 1500 - 1000 = 500.00.
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("500.00"))

        # Order should be marked processing and paid immediately
        order = Order.objects.get(vendor=self.vendor_a, customer=self.customer_a)
        self.assertEqual(order.payment_status, 'paid')
        self.assertEqual(order.status, 'processing')

        # Check transaction log
        tx = WalletTransaction.objects.filter(wallet=wallet, transaction_type='debit', amount=Decimal("1000.00"))
        self.assertTrue(tx.exists())

    def test_crm_vendor_isolation(self):
        # Check customer profiles access scoping
        self.client.force_login(self.user_a)

        # Vendor A staff can view customer A detail page
        response = self.client.get(reverse('crm:customer_detail', kwargs={'pk': self.customer_a.pk}))
        self.assertEqual(response.status_code, 200)

        # Vendor B staff cannot view customer A detail page (scoping isolates users)
        self.client.force_login(self.user_b)
        response = self.client.get(reverse('crm:customer_detail', kwargs={'pk': self.customer_a.pk}))
        self.assertEqual(response.status_code, 404)

    def test_manual_adjustments(self):
        # Log in as vendor A staff
        self.client.force_login(self.user_a)

        # 1. Test manual wallet credit
        response = self.client.post(
            reverse('crm:wallet_adjustment', kwargs={'pk': self.customer_a.pk}),
            {
                'action_type': 'credit',
                'amount': '150.00',
                'reason': 'Refund for damaged item'
            }
        )
        self.assertEqual(response.status_code, 302) # redirects to customer detail page
        wallet = Wallet.objects.get(vendor=self.vendor_a, customer=self.customer_a)
        self.assertEqual(wallet.balance, Decimal('150.00'))
        self.assertTrue(wallet.transactions.filter(transaction_type='credit', amount=Decimal('150.00')).exists())

        # 2. Test manual loyalty points adjustment
        response = self.client.post(
            reverse('crm:loyalty_adjustment', kwargs={'pk': self.customer_a.pk}),
            {
                'points': '50',
                'reason': 'Customer appreciation bonus'
            }
        )
        self.assertEqual(response.status_code, 302)
        # Check loyalty total
        points_agg = LoyaltyLedger.objects.filter(
            vendor=self.vendor_a,
            customer=self.customer_a
        ).aggregate(total=models.Sum('points'))
        self.assertEqual(points_agg['total'], 50)

