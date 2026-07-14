from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from decimal import Decimal
from core.mixins import PermissionRequiredMixin
from branches.models import Branch
from catalog.models import ProductVariant, Category
from .models import (
    Supplier, BranchInventory, StockAdjustmentLog,
    PurchaseOrder, PurchaseOrderItem, StockTransfer, StockTransferItem
)
import datetime


def generate_po_number(vendor):
    today = datetime.date.today().strftime('%Y%m%d')
    prefix = f"PO-{today}-"
    last_po = PurchaseOrder.objects.filter(vendor=vendor, po_number__startswith=prefix).order_by('-po_number').first()
    if last_po:
        try:
            seq = int(last_po.po_number.split('-')[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def generate_transfer_number(vendor):
    today = datetime.date.today().strftime('%Y%m%d')
    prefix = f"TR-{today}-"
    last_tr = StockTransfer.objects.filter(vendor=vendor, transfer_number__startswith=prefix).order_by('-transfer_number').first()
    if last_tr:
        try:
            seq = int(last_tr.transfer_number.split('-')[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


# ─────────────────────────────────────────────────────────────
# SUPPLIER VIEWS
# ─────────────────────────────────────────────────────────────

class SupplierListView(PermissionRequiredMixin, View):
    permission_codename = 'view_inventory'
    template_name = 'vendor/inventory/supplier_list.html'

    def get(self, request):
        vendor = request.user.vendor
        q = request.GET.get('q', '').strip()
        suppliers = Supplier.objects.filter(vendor=vendor)
        if q:
            suppliers = suppliers.filter(
                Q(name__icontains=q) |
                Q(contact_name__icontains=q) |
                Q(phone__icontains=q) |
                Q(email__icontains=q)
            )
        suppliers = suppliers.order_by('-is_active', 'name')
        context = {
            'suppliers': suppliers,
            'q': q,
            'page_title': 'Suppliers Management',
        }
        return render(request, self.template_name, context)


class SupplierCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_inventory'
    template_name = 'vendor/inventory/supplier_form.html'

    def get(self, request):
        context = {
            'page_title': 'Add Supplier',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        name = request.POST.get('name', '').strip()
        contact_name = request.POST.get('contact_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        gstin = request.POST.get('gstin', '').strip().upper()
        address = request.POST.get('address', '').strip()

        if not name:
            messages.error(request, 'Supplier name is required.')
            return redirect('inventory:supplier_create')

        Supplier.objects.create(
            vendor=request.user.vendor,
            name=name,
            contact_name=contact_name,
            phone=phone,
            email=email,
            gstin=gstin,
            address=address
        )
        messages.success(request, f'Supplier "{name}" added successfully.')
        return redirect('inventory:supplier_list')


class SupplierUpdateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_inventory'
    template_name = 'vendor/inventory/supplier_form.html'

    def get(self, request, supplier_id):
        supplier = get_object_or_404(Supplier, vendor=request.user.vendor, pk=supplier_id)
        context = {
            'supplier': supplier,
            'page_title': f'Edit Supplier — {supplier.name}',
        }
        return render(request, self.template_name, context)

    def post(self, request, supplier_id):
        supplier = get_object_or_404(Supplier, vendor=request.user.vendor, pk=supplier_id)
        name = request.POST.get('name', '').strip()
        contact_name = request.POST.get('contact_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        gstin = request.POST.get('gstin', '').strip().upper()
        address = request.POST.get('address', '').strip()
        is_active = request.POST.get('is_active') == 'true'

        if not name:
            messages.error(request, 'Supplier name is required.')
            return redirect('inventory:supplier_edit', supplier_id=supplier.pk)

        supplier.name = name
        supplier.contact_name = contact_name
        supplier.phone = phone
        supplier.email = email
        supplier.gstin = gstin
        supplier.address = address
        supplier.is_active = is_active
        supplier.save()

        messages.success(request, f'Supplier "{name}" updated successfully.')
        return redirect('inventory:supplier_list')


class SupplierDeleteView(PermissionRequiredMixin, View):
    permission_codename = 'manage_inventory'

    def post(self, request, supplier_id):
        supplier = get_object_or_404(Supplier, vendor=request.user.vendor, pk=supplier_id)
        # Check if supplier has POs
        if PurchaseOrder.objects.filter(supplier=supplier).exists():
            messages.error(request, f'Supplier "{supplier.name}" cannot be deleted as they have associated purchase orders. Deactivate them instead.')
        else:
            name = supplier.name
            supplier.delete()
            messages.success(request, f'Supplier "{name}" deleted successfully.')
        return redirect('inventory:supplier_list')


# ─────────────────────────────────────────────────────────────
# BRANCH INVENTORY VIEWS
# ─────────────────────────────────────────────────────────────

class BranchInventoryListView(PermissionRequiredMixin, View):
    permission_codename = 'view_inventory'
    template_name = 'vendor/inventory/stock_list.html'

    def get(self, request):
        vendor = request.user.vendor
        branches = Branch.objects.filter(vendor=vendor, is_active=True).order_by('-is_main_branch', 'name')
        categories = Category.objects.filter(vendor=vendor).order_by('name')

        branch_id = request.GET.get('branch', '')
        category_id = request.GET.get('category', '')
        alert_status = request.GET.get('alert', '')
        q = request.GET.get('q', '').strip()

        # Get active products/variants
        variants = ProductVariant.objects.filter(product__vendor=vendor, is_active=True).select_related('product')

        if q:
            variants = variants.filter(
                Q(product__name__icontains=q) |
                Q(sku__icontains=q) |
                Q(name__icontains=q)
            )

        if category_id:
            variants = variants.filter(product__category_id=category_id)

        # Build list mapping variants to their stocks per branch
        stock_data = []
        for variant in variants:
            # Get or create BranchInventory for the active branches
            branch_stocks = {}
            for b in branches:
                bi, _ = BranchInventory.objects.get_or_create(
                    branch=b,
                    product_variant=variant,
                    defaults={'stock_qty': Decimal('0.00'), 'reorder_level': Decimal('0.00')}
                )
                branch_stocks[b.id] = bi

            # Determine aggregate stats
            total_qty = sum((bi.stock_qty for bi in branch_stocks.values()), Decimal('0.00'))
            
            # Low stock logic
            is_low_stock = False
            for bi in branch_stocks.values():
                if bi.stock_qty <= bi.reorder_level and bi.reorder_level > 0:
                    is_low_stock = True
                    break

            if alert_status == 'low' and not is_low_stock:
                continue

            stock_data.append({
                'variant': variant,
                'branch_stocks': branch_stocks,
                'total_qty': total_qty,
                'is_low_stock': is_low_stock,
            })

        # Adjustment logs for history view
        logs = StockAdjustmentLog.objects.filter(vendor=vendor).select_related('branch', 'product_variant', 'user').order_by('-created_at')[:20]

        context = {
            'branches': branches,
            'categories': categories,
            'stock_data': stock_data,
            'logs': logs,
            'selected_branch': branch_id,
            'selected_category': category_id,
            'selected_alert': alert_status,
            'q': q,
            'page_title': 'Stock Levels',
        }
        return render(request, self.template_name, context)


class BranchInventoryAdjustmentView(PermissionRequiredMixin, View):
    permission_codename = 'manage_inventory'

    def post(self, request):
        branch_id = request.POST.get('branch_id')
        variant_id = request.POST.get('variant_id')
        qty_str = request.POST.get('qty', '0.00').strip()
        adjustment_type = request.POST.get('adjustment_type', 'set') # 'set' (override) or 'diff' (adjust by)
        reason = request.POST.get('reason', 'correction')
        notes = request.POST.get('notes', '').strip()

        vendor = request.user.vendor
        branch = get_object_or_404(Branch, vendor=vendor, pk=branch_id)
        variant = get_object_or_404(ProductVariant, product__vendor=vendor, pk=variant_id)

        try:
            qty = float(qty_str)
        except ValueError:
            messages.error(request, 'Invalid quantity value provided.')
            return redirect('inventory:branch_inventory_list')

        bi, _ = BranchInventory.objects.get_or_create(
            branch=branch,
            product_variant=variant,
            defaults={'stock_qty': Decimal('0.00')}
        )

        with transaction.atomic():
            old_qty = float(bi.stock_qty)
            if adjustment_type == 'set':
                new_qty = qty
                change = new_qty - old_qty
            else:
                change = qty
                new_qty = old_qty + change

            bi.stock_qty = new_qty
            bi.save()

            # Log adjustment
            StockAdjustmentLog.objects.create(
                vendor=vendor,
                branch=branch,
                product_variant=variant,
                user=request.user,
                quantity_changed=change,
                reason=reason,
                notes=notes
            )

        messages.success(request, f'Stock for {variant.sku} adjusted at branch "{branch.name}". New stock: {new_qty}.')
        return redirect('inventory:branch_inventory_list')


# ─────────────────────────────────────────────────────────────
# PURCHASE ORDER VIEWS
# ─────────────────────────────────────────────────────────────

class PurchaseOrderListView(PermissionRequiredMixin, View):
    permission_codename = 'view_inventory'
    template_name = 'vendor/inventory/po_list.html'

    def get(self, request):
        vendor = request.user.vendor
        suppliers = Supplier.objects.filter(vendor=vendor, is_active=True).order_by('name')
        
        status_filter = request.GET.get('status', '')
        supplier_filter = request.GET.get('supplier', '')

        pos = PurchaseOrder.objects.filter(vendor=vendor).select_related('supplier', 'branch').order_by('-created_at')
        if status_filter:
            pos = pos.filter(status=status_filter)
        if supplier_filter:
            pos = pos.filter(supplier_id=supplier_filter)

        context = {
            'purchase_orders': pos,
            'suppliers': suppliers,
            'status_filter': status_filter,
            'supplier_filter': supplier_filter,
            'page_title': 'Purchase Orders',
        }
        return render(request, self.template_name, context)


class PurchaseOrderCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_inventory'
    template_name = 'vendor/inventory/po_form.html'

    def get(self, request):
        vendor = request.user.vendor
        suppliers = Supplier.objects.filter(vendor=vendor, is_active=True).order_by('name')
        branches = Branch.objects.filter(vendor=vendor, is_active=True).order_by('-is_main_branch', 'name')
        variants = ProductVariant.objects.filter(product__vendor=vendor, is_active=True).select_related('product')
        
        context = {
            'suppliers': suppliers,
            'branches': branches,
            'variants': variants,
            'po_number': generate_po_number(vendor),
            'page_title': 'Create Purchase Order',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        vendor = request.user.vendor
        supplier_id = request.POST.get('supplier_id')
        branch_id = request.POST.get('branch_id')
        order_date_str = request.POST.get('order_date')
        expected_delivery_str = request.POST.get('expected_delivery_date')
        notes = request.POST.get('notes', '').strip()

        # Line items lists
        variant_ids = request.POST.getlist('variant_id[]')
        quantities = request.POST.getlist('quantity[]')
        unit_costs = request.POST.getlist('unit_cost[]')

        if not supplier_id or not branch_id or not variant_ids:
            messages.error(request, 'Supplier, Target Branch, and at least one item are required.')
            return redirect('inventory:purchase_order_create')

        supplier = get_object_or_404(Supplier, vendor=vendor, pk=supplier_id)
        branch = get_object_or_404(Branch, vendor=vendor, pk=branch_id)

        try:
            with transaction.atomic():
                po = PurchaseOrder.objects.create(
                    vendor=vendor,
                    supplier=supplier,
                    branch=branch,
                    po_number=generate_po_number(vendor),
                    order_date=order_date_str or timezone.now().date(),
                    expected_delivery_date=expected_delivery_str or None,
                    notes=notes,
                    status='draft',
                    total_amount=0.00
                )

                total_po_amount = 0.00
                for idx, v_id in enumerate(variant_ids):
                    variant = get_object_or_404(ProductVariant, product__vendor=vendor, pk=v_id)
                    qty = float(quantities[idx])
                    cost = float(unit_costs[idx])
                    total_item_cost = qty * cost

                    PurchaseOrderItem.objects.create(
                        purchase_order=po,
                        product_variant=variant,
                        quantity=qty,
                        unit_cost=cost,
                        total_cost=total_item_cost
                    )
                    total_po_amount += total_item_cost

                po.total_amount = total_po_amount
                po.save()

            messages.success(request, f'Purchase Order {po.po_number} created as Draft.')
            return redirect('inventory:purchase_order_detail', po_id=po.pk)
        except Exception as e:
            messages.error(request, f'Error creating Purchase Order: {str(e)}')
            return redirect('inventory:purchase_order_create')


class PurchaseOrderDetailView(PermissionRequiredMixin, View):
    permission_codename = 'view_inventory'
    template_name = 'vendor/inventory/po_detail.html'

    def get(self, request, po_id):
        po = get_object_or_404(PurchaseOrder, vendor=request.user.vendor, pk=po_id)
        items = po.items.select_related('product_variant__product')
        context = {
            'po': po,
            'items': items,
            'page_title': f'Purchase Order — {po.po_number}',
        }
        return render(request, self.template_name, context)


class PurchaseOrderStatusUpdateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_inventory'

    def post(self, request, po_id):
        po = get_object_or_404(PurchaseOrder, vendor=request.user.vendor, pk=po_id)
        action = request.POST.get('action')

        if po.status == 'received':
            messages.error(request, 'This Purchase Order has already been completed.')
            return redirect('inventory:purchase_order_detail', po_id=po.pk)

        with transaction.atomic():
            if action == 'send':
                if po.status == 'draft':
                    po.status = 'sent'
                    po.save()
                    messages.success(request, f'Purchase Order {po.po_number} marked as Sent.')
            elif action == 'receive':
                if po.status in ('draft', 'sent'):
                    # Load and update stock
                    for item in po.items.all():
                        bi, _ = BranchInventory.objects.get_or_create(
                            branch=po.branch,
                            product_variant=item.product_variant,
                            defaults={'stock_qty': Decimal('0.00')}
                        )
                        bi.stock_qty = float(bi.stock_qty) + float(item.quantity)
                        bi.save()

                        # Audit Log entry
                        StockAdjustmentLog.objects.create(
                            vendor=po.vendor,
                            branch=po.branch,
                            product_variant=item.product_variant,
                            user=request.user,
                            quantity_changed=item.quantity,
                            reason='correction',
                            notes=f'Received via PO: {po.po_number}'
                        )

                    po.status = 'received'
                    po.received_date = timezone.now()
                    po.save()
                    messages.success(request, f'Purchase Order {po.po_number} fully received. Branch stocks updated.')
            elif action == 'cancel':
                po.status = 'cancelled'
                po.save()
                messages.success(request, f'Purchase Order {po.po_number} marked as Cancelled.')

        return redirect('inventory:purchase_order_detail', po_id=po.pk)


# ─────────────────────────────────────────────────────────────
# STOCK TRANSFER VIEWS
# ─────────────────────────────────────────────────────────────

class StockTransferListView(PermissionRequiredMixin, View):
    permission_codename = 'view_inventory'
    template_name = 'vendor/inventory/transfer_list.html'

    def get(self, request):
        vendor = request.user.vendor
        transfers = StockTransfer.objects.filter(vendor=vendor).select_related('from_branch', 'to_branch').order_by('-created_at')
        context = {
            'transfers': transfers,
            'page_title': 'Stock Transfers',
        }
        return render(request, self.template_name, context)


class StockTransferCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_inventory'
    template_name = 'vendor/inventory/transfer_form.html'

    def get(self, request):
        vendor = request.user.vendor
        branches = Branch.objects.filter(vendor=vendor, is_active=True).order_by('-is_main_branch', 'name')
        variants = ProductVariant.objects.filter(product__vendor=vendor, is_active=True).select_related('product')
        context = {
            'branches': branches,
            'variants': variants,
            'transfer_number': generate_transfer_number(vendor),
            'page_title': 'Create Stock Transfer',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        vendor = request.user.vendor
        from_branch_id = request.POST.get('from_branch_id')
        to_branch_id = request.POST.get('to_branch_id')
        notes = request.POST.get('notes', '').strip()

        variant_ids = request.POST.getlist('variant_id[]')
        quantities = request.POST.getlist('quantity[]')

        if not from_branch_id or not to_branch_id or not variant_ids:
            messages.error(request, 'From Branch, To Branch, and at least one variant are required.')
            return redirect('inventory:stock_transfer_create')

        if from_branch_id == to_branch_id:
            messages.error(request, 'Source and destination branches cannot be the same.')
            return redirect('inventory:stock_transfer_create')

        from_branch = get_object_or_404(Branch, vendor=vendor, pk=from_branch_id)
        to_branch = get_object_or_404(Branch, vendor=vendor, pk=to_branch_id)

        try:
            with transaction.atomic():
                transfer = StockTransfer.objects.create(
                    vendor=vendor,
                    from_branch=from_branch,
                    to_branch=to_branch,
                    transfer_number=generate_transfer_number(vendor),
                    status='pending',
                    notes=notes
                )

                for idx, v_id in enumerate(variant_ids):
                    variant = get_object_or_404(ProductVariant, product__vendor=vendor, pk=v_id)
                    qty = float(quantities[idx])

                    StockTransferItem.objects.create(
                        stock_transfer=transfer,
                        product_variant=variant,
                        quantity=qty
                    )

            messages.success(request, f'Stock Transfer {transfer.transfer_number} created.')
            return redirect('inventory:stock_transfer_detail', transfer_id=transfer.pk)
        except Exception as e:
            messages.error(request, f'Error creating transfer: {str(e)}')
            return redirect('inventory:stock_transfer_create')


class StockTransferDetailView(PermissionRequiredMixin, View):
    permission_codename = 'view_inventory'
    template_name = 'vendor/inventory/transfer_detail.html'

    def get(self, request, transfer_id):
        transfer = get_object_or_404(StockTransfer, vendor=request.user.vendor, pk=transfer_id)
        items = transfer.items.select_related('product_variant__product')
        context = {
            'transfer': transfer,
            'items': items,
            'page_title': f'Stock Transfer — {transfer.transfer_number}',
        }
        return render(request, self.template_name, context)


class StockTransferStatusUpdateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_inventory'

    def post(self, request, transfer_id):
        transfer = get_object_or_404(StockTransfer, vendor=request.user.vendor, pk=transfer_id)
        action = request.POST.get('action')

        if transfer.status == 'completed':
            messages.error(request, 'This transfer has already been completed.')
            return redirect('inventory:stock_transfer_detail', transfer_id=transfer.pk)

        with transaction.atomic():
            if action == 'dispatch':
                if transfer.status == 'pending':
                    # Deduct from source branch inventory when dispatched
                    for item in transfer.items.all():
                        bi, _ = BranchInventory.objects.get_or_create(
                            branch=transfer.from_branch,
                            product_variant=item.product_variant,
                            defaults={'stock_qty': Decimal('0.00')}
                        )
                        
                        # Warning if stock is insufficient but allow as per onboarding strategy
                        if float(bi.stock_qty) < float(item.quantity):
                            messages.warning(request, f'Source branch has insufficient stock for {item.product_variant.sku}. Stock went negative.')

                        bi.stock_qty = float(bi.stock_qty) - float(item.quantity)
                        bi.save()

                        # Audit log out
                        StockAdjustmentLog.objects.create(
                            vendor=transfer.vendor,
                            branch=transfer.from_branch,
                            product_variant=item.product_variant,
                            user=request.user,
                            quantity_changed=-item.quantity,
                            reason='other',
                            notes=f'Dispatched via Transfer: {transfer.transfer_number}'
                        )

                    transfer.status = 'transit'
                    transfer.sent_date = timezone.now()
                    transfer.save()
                    messages.success(request, f'Stock Transfer {transfer.transfer_number} marked as In-Transit. Stock deducted from source branch.')

            elif action == 'complete':
                if transfer.status in ('pending', 'transit'):
                    # If direct skip to completed without dispatch, deduct from source first
                    if transfer.status == 'pending':
                        for item in transfer.items.all():
                            bi_from, _ = BranchInventory.objects.get_or_create(
                                branch=transfer.from_branch,
                                product_variant=item.product_variant,
                                defaults={'stock_qty': Decimal('0.00')}
                            )
                            bi_from.stock_qty = float(bi_from.stock_qty) - float(item.quantity)
                            bi_from.save()

                            StockAdjustmentLog.objects.create(
                                vendor=transfer.vendor,
                                branch=transfer.from_branch,
                                product_variant=item.product_variant,
                                user=request.user,
                                quantity_changed=-item.quantity,
                                reason='other',
                                notes=f'Dispatched via direct Complete: {transfer.transfer_number}'
                            )

                    # Add to destination branch inventory
                    for item in transfer.items.all():
                        bi_to, _ = BranchInventory.objects.get_or_create(
                            branch=transfer.to_branch,
                            product_variant=item.product_variant,
                            defaults={'stock_qty': Decimal('0.00')}
                        )
                        bi_to.stock_qty = float(bi_to.stock_qty) + float(item.quantity)
                        bi_to.save()

                        # Audit log in
                        StockAdjustmentLog.objects.create(
                            vendor=transfer.vendor,
                            branch=transfer.to_branch,
                            product_variant=item.product_variant,
                            user=request.user,
                            quantity_changed=item.quantity,
                            reason='correction',
                            notes=f'Received via Transfer: {transfer.transfer_number}'
                        )

                    transfer.status = 'completed'
                    transfer.received_date = timezone.now()
                    transfer.save()
                    messages.success(request, f'Stock Transfer {transfer.transfer_number} completed. Destination branch stocks updated.')

            elif action == 'cancel':
                # If cancelled from Transit, restore the deducted stock to source branch
                if transfer.status == 'transit':
                    for item in transfer.items.all():
                        bi, _ = BranchInventory.objects.get_or_create(
                            branch=transfer.from_branch,
                            product_variant=item.product_variant,
                            defaults={'stock_qty': Decimal('0.00')}
                        )
                        bi.stock_qty = float(bi.stock_qty) + float(item.quantity)
                        bi.save()

                        StockAdjustmentLog.objects.create(
                            vendor=transfer.vendor,
                            branch=transfer.from_branch,
                            product_variant=item.product_variant,
                            user=request.user,
                            quantity_changed=item.quantity,
                            reason='correction',
                            notes=f'Restored via Cancelled Transfer: {transfer.transfer_number}'
                        )

                transfer.status = 'cancelled'
                transfer.save()
                messages.success(request, f'Stock Transfer {transfer.transfer_number} marked as Cancelled.')

        return redirect('inventory:stock_transfer_detail', transfer_id=transfer.pk)
