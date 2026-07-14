from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User
from tenants.models import Vendor
from branches.models import Branch
from catalog.models import Product, ProductVariant
from .models import (
    Supplier, BranchInventory, StockAdjustmentLog,
    PurchaseOrder, PurchaseOrderItem, StockTransfer, StockTransferItem
)


class InventoryTestCase(TestCase):

    def setUp(self):
        # 1. Create two test vendors
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

        # 2. Create physical branches for Vendor A
        self.branch_a_main = Branch.objects.create(
            vendor=self.vendor_a,
            name="A Main Branch",
            code="AMAIN",
            phone="1111111111",
            is_main_branch=True,
            is_active=True
        )
        self.branch_a_sub = Branch.objects.create(
            vendor=self.vendor_a,
            name="A Sub Branch",
            code="ASUB",
            phone="1111111112",
            is_main_branch=False,
            is_active=True
        )

        # Create physical branches for Vendor B
        self.branch_b_main = Branch.objects.create(
            vendor=self.vendor_b,
            name="B Main Branch",
            code="BMAIN",
            phone="2222222222",
            is_main_branch=True,
            is_active=True
        )

        # 3. Create users for both vendors
        self.user_a = User.objects.create_user(
            phone="1111111111",
            password="password",
            vendor=self.vendor_a,
            user_type="vendor_staff",
            is_active=True
        )
        self.user_b = User.objects.create_user(
            phone="2222222222",
            password="password",
            vendor=self.vendor_b,
            user_type="vendor_staff",
            is_active=True
        )

        # Clients for requests
        self.client_a = Client()
        self.client_a.force_login(self.user_a)

        self.client_b = Client()
        self.client_b.force_login(self.user_b)

        # 4. Create initial products for Vendor A
        self.product_a = Product.objects.create(
            vendor=self.vendor_a,
            name="Product A",
            slug="product-a",
            status="published",
            has_variants=False
        )
        self.variant_a = ProductVariant.objects.create(
            product=self.product_a,
            sku="SKU-A",
            price="100.00",
            stock_qty=10.00
        )

    def test_branch_inventory_autoseed_on_creation(self):
        """
        Tests that when a product variant is created,
        a BranchInventory is auto-seeded for the main branch.
        """
        # A BranchInventory row should have been auto-seeded in setUp
        bi = BranchInventory.objects.filter(
            branch=self.branch_a_main,
            product_variant=self.variant_a
        ).first()

        self.assertIsNotNone(bi)
        self.assertEqual(float(bi.stock_qty), 10.00)

    def test_stock_sync_signals(self):
        """
        Tests that updating BranchInventory stock levels updates
        the aggregated ProductVariant.stock_qty.
        """
        # Fetch the auto-seeded inventory
        bi_main = BranchInventory.objects.get(
            branch=self.branch_a_main,
            product_variant=self.variant_a
        )

        # Create inventory on sub branch
        bi_sub = BranchInventory.objects.create(
            branch=self.branch_a_sub,
            product_variant=self.variant_a,
            stock_qty=15.00
        )

        # Total stock of self.variant_a should now be bi_main (10) + bi_sub (15) = 25
        self.variant_a.refresh_from_db()
        self.assertEqual(float(self.variant_a.stock_qty), 25.00)

        # Update sub branch stock to 20
        bi_sub.stock_qty = 20.00
        bi_sub.save()

        self.variant_a.refresh_from_db()
        self.assertEqual(float(self.variant_a.stock_qty), 30.00)

    def test_purchase_order_receiving_flow(self):
        """
        Verifies purchase order flow:
        - Creation of PO
        - Verification that status is Draft
        - Transitioning status to Received adds inventory to the branch
        """
        supplier = Supplier.objects.create(
            vendor=self.vendor_a,
            name="Supplier A",
            is_active=True
        )

        # Post to create PO
        url = reverse('inventory:purchase_order_create')
        data = {
            'supplier_id': supplier.id,
            'branch_id': self.branch_a_main.id,
            'order_date': '2026-06-24',
            'notes': 'Test PO',
            'variant_id[]': [self.variant_a.id],
            'quantity[]': ['12.50'],
            'unit_cost[]': ['50.00']
        }
        
        # Should redirect to detail view
        response = self.client_a.post(url, data)
        self.assertEqual(response.status_code, 302)

        # Verify PO created as draft
        po = PurchaseOrder.objects.get(vendor=self.vendor_a, supplier=supplier)
        self.assertEqual(po.status, 'draft')
        self.assertEqual(float(po.total_amount), 625.00)

        # Receive PO items (post to status update view)
        status_url = reverse('inventory:purchase_order_status_update', args=[po.id])
        status_response = self.client_a.post(status_url, {'action': 'receive'})
        self.assertEqual(status_response.status_code, 302)

        # Re-fetch branch inventory and variant
        bi = BranchInventory.objects.get(branch=self.branch_a_main, product_variant=self.variant_a)
        # Seeded (10.00) + PO Received (12.50) = 22.50
        self.assertEqual(float(bi.stock_qty), 22.50)

        po.refresh_from_db()
        self.assertEqual(po.status, 'received')
        self.assertIsNotNone(po.received_date)

        # Check stock log
        log = StockAdjustmentLog.objects.filter(vendor=self.vendor_a, branch=self.branch_a_main).first()
        self.assertIsNotNone(log)
        self.assertEqual(float(log.quantity_changed), 12.50)

    def test_stock_transfer_dispatch_and_complete(self):
        """
        Verifies stock transfer flow:
        - Dispatch: deducts quantity from source branch
        - Complete: adds quantity to destination branch
        """
        # Initial stocks: A main = 10, A sub = 0
        bi_main = BranchInventory.objects.get(branch=self.branch_a_main, product_variant=self.variant_a)
        bi_sub, _ = BranchInventory.objects.get_or_create(
            branch=self.branch_a_sub,
            product_variant=self.variant_a,
            defaults={'stock_qty': 0.00}
        )

        # Create transfer
        transfer = StockTransfer.objects.create(
            vendor=self.vendor_a,
            from_branch=self.branch_a_main,
            to_branch=self.branch_a_sub,
            transfer_number="TR-999"
        )
        StockTransferItem.objects.create(
            stock_transfer=transfer,
            product_variant=self.variant_a,
            quantity=3.00
        )

        # Dispatch transfer
        status_url = reverse('inventory:stock_transfer_status_update', args=[transfer.id])
        self.client_a.post(status_url, {'action': 'dispatch'})

        # Stock at source should be deducted: 10 - 3 = 7
        bi_main.refresh_from_db()
        self.assertEqual(float(bi_main.stock_qty), 7.00)

        # Stock at destination should still be 0 (in-transit)
        bi_sub.refresh_from_db()
        self.assertEqual(float(bi_sub.stock_qty), 0.00)

        # Complete transfer
        self.client_a.post(status_url, {'action': 'complete'})

        # Stock at destination should now be 3
        bi_sub.refresh_from_db()
        self.assertEqual(float(bi_sub.stock_qty), 3.00)

        transfer.refresh_from_db()
        self.assertEqual(transfer.status, 'completed')

    def test_multi_tenant_isolation(self):
        """
        Confirms Vendor B user cannot view Vendor A's POs or suppliers.
        """
        supplier_a = Supplier.objects.create(
            vendor=self.vendor_a,
            name="Supplier A",
            is_active=True
        )

        # Try to view Supplier list as Vendor B
        url = reverse('inventory:supplier_list')
        response_b = self.client_b.get(url)
        self.assertNotIn(supplier_a, response_b.context['suppliers'])

        # Try to access edit page of Supplier A directly as Vendor B
        edit_url = reverse('inventory:supplier_edit', args=[supplier_a.id])
        edit_response_b = self.client_b.get(edit_url)
        # Should raise 404 since get_object_or_404 filters on vendor=request.user.vendor
        self.assertEqual(edit_response_b.status_code, 404)

    def test_stock_list_page_render(self):
        """
        Verify that the stock levels page renders successfully.
        """
        url = reverse('inventory:branch_inventory_list')
        response = self.client_a.get(url)
        self.assertEqual(response.status_code, 200)

