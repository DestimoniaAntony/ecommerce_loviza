import json
import csv
import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.db import transaction, models as db_models
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from decimal import Decimal

from core.mixins import VendorLoginRequiredMixin
from storefront.models import Order, OrderItem
from inventory.models import BranchInventory, StockAdjustmentLog
from branches.models import Branch


# ────────────────────────────────────────────────────────────────
# ANALYTICS HELPER
# ────────────────────────────────────────────────────────────────

def _get_date_range(range_param):
    """Return (start_date, end_date, label) for a range parameter."""
    today = timezone.now().date()
    if range_param == '7d':
        start = today - datetime.timedelta(days=6)
        return start, today, '7 Days'
    elif range_param == '12m':
        start = (today.replace(day=1) - datetime.timedelta(days=335)).replace(day=1)
        return start, today, '12 Months'
    else:  # default: 30d
        start = today - datetime.timedelta(days=29)
        return start, today, '30 Days'


def _build_dashboard_context(vendor, range_param='30d'):
    """Compute all analytics context for the vendor dashboard."""
    start_date, end_date, range_label = _get_date_range(range_param)
    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(end_date, datetime.time.max)

    all_orders = Order.objects.filter(vendor=vendor)
    range_orders = all_orders.filter(created_at__range=(start_dt, end_dt))
    paid_orders = all_orders.filter(payment_status='paid')
    range_paid_orders = range_orders.filter(payment_status='paid')

    # ── KPI Cards ──
    total_revenue = paid_orders.aggregate(t=Sum('total_amount'))['t'] or Decimal('0.00')
    range_revenue = range_paid_orders.aggregate(t=Sum('total_amount'))['t'] or Decimal('0.00')
    total_orders = all_orders.count()
    range_orders_count = range_orders.count()
    pending_orders = all_orders.filter(status__in=['pending', 'awaiting_approval']).count()
    active_customers = all_orders.values('customer').distinct().count()

    # ── Revenue Chart (grouped by date or month) ──
    if range_param == '12m':
        chart_qs = range_paid_orders.annotate(
            period=TruncMonth('created_at')
        ).values('period').annotate(revenue=Sum('total_amount')).order_by('period')
        chart_labels = [r['period'].strftime('%b %Y') for r in chart_qs]
        chart_data = [float(r['revenue']) for r in chart_qs]
    else:
        chart_qs = range_paid_orders.annotate(
            period=TruncDate('created_at')
        ).values('period').annotate(revenue=Sum('total_amount')).order_by('period')
        # Fill in missing days with 0
        revenue_by_date = {r['period']: float(r['revenue']) for r in chart_qs}
        delta = (end_date - start_date).days
        chart_labels = []
        chart_data = []
        for i in range(delta + 1):
            d = start_date + datetime.timedelta(days=i)
            chart_labels.append(d.strftime('%d %b'))
            chart_data.append(revenue_by_date.get(d, 0.0))

    # ── Order Status Donut ──
    status_counts = all_orders.values('status').annotate(count=Count('id'))
    status_labels = []
    status_data = []
    status_color_map = {
        'pending': '#fbbf24',
        'awaiting_approval': '#f97316',
        'processing': '#38bdf8',
        'shipped': '#818cf8',
        'delivered': '#34d399',
        'cancelled': '#f87171',
    }
    status_colors = []
    for row in status_counts:
        label = dict(Order.STATUS_CHOICES).get(row['status'], row['status'])
        status_labels.append(label)
        status_data.append(row['count'])
        status_colors.append(status_color_map.get(row['status'], '#94a3b8'))

    # ── Top 5 Products by Revenue ──
    top_products = (
        OrderItem.objects
        .filter(order__vendor=vendor)
        .values('product_variant__product__name', 'product_variant__sku')
        .annotate(units_sold=Sum('quantity'), revenue=Sum('total_cost'))
        .order_by('-revenue')[:5]
    )

    # ── Recent Orders ──
    recent_orders = all_orders.select_related('customer').order_by('-created_at')[:10]

    # ── CRM Snapshot ──
    crm_context = {}
    try:
        from crm.models import Coupon, LoyaltyLedger, Wallet
        active_coupons = Coupon.objects.filter(vendor=vendor, is_active=True).count()
        total_redemptions = Coupon.objects.filter(vendor=vendor).aggregate(t=Sum('used_count'))['t'] or 0
        loyalty_participants = LoyaltyLedger.objects.filter(vendor=vendor).values('customer').distinct().count()
        total_wallet_credits = Wallet.objects.filter(vendor=vendor).aggregate(t=Sum('balance'))['t'] or Decimal('0.00')
        crm_context = {
            'active_coupons': active_coupons,
            'total_redemptions': total_redemptions,
            'loyalty_participants': loyalty_participants,
            'total_wallet_credits': total_wallet_credits,
        }
    except Exception:
        pass

    # ── Low Stock Alerts ──
    vendor_branches = Branch.objects.filter(vendor=vendor, is_active=True)
    low_stock_items = (
        BranchInventory.objects
        .filter(branch__in=vendor_branches)
        .filter(stock_qty__lte=db_models.F('reorder_level'))
        .select_related('product_variant__product', 'branch')
        .order_by('stock_qty')[:20]
    )

    return {
        # Meta
        'range_param': range_param,
        'range_label': range_label,
        'range_start': start_date,
        'range_end': end_date,
        # KPIs
        'total_revenue': total_revenue,
        'range_revenue': range_revenue,
        'total_orders': total_orders,
        'range_orders_count': range_orders_count,
        'pending_orders': pending_orders,
        'active_customers': active_customers,
        # Charts (JSON)
        'chart_labels_json': json.dumps(chart_labels),
        'chart_data_json': json.dumps(chart_data),
        'status_labels_json': json.dumps(status_labels),
        'status_data_json': json.dumps(status_data),
        'status_colors_json': json.dumps(status_colors),
        # Tables
        'top_products': list(top_products),
        'recent_orders': recent_orders,
        'low_stock_items': low_stock_items,
        # CRM
        **crm_context,
    }


# ────────────────────────────────────────────────────────────────
# DASHBOARD VIEW
# ────────────────────────────────────────────────────────────────

class VendorDashboardView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/dashboard.html'

    def get(self, request):
        vendor = request.user.vendor
        range_param = request.GET.get('range', '30d')
        if range_param not in ('7d', '30d', '12m'):
            range_param = '30d'

        context = _build_dashboard_context(vendor, range_param)
        context['page_title'] = 'Analytics Dashboard'
        context['range_options'] = [('Last 7 Days', '7d'), ('Last 30 Days', '30d'), ('Last 12 Months', '12m')]
        return render(request, self.template_name, context)


# ────────────────────────────────────────────────────────────────
# CSV EXPORT VIEWS
# ────────────────────────────────────────────────────────────────

class ExportTopProductsView(VendorLoginRequiredMixin, View):
    """Export top-selling products by revenue as a CSV download."""

    def get(self, request):
        vendor = request.user.vendor
        range_param = request.GET.get('range', '30d')
        start_date, end_date, range_label = _get_date_range(range_param)
        start_dt = datetime.datetime.combine(start_date, datetime.time.min)
        end_dt = datetime.datetime.combine(end_date, datetime.time.max)

        products = (
            OrderItem.objects
            .filter(order__vendor=vendor, order__created_at__range=(start_dt, end_dt))
            .values('product_variant__product__name', 'product_variant__sku')
            .annotate(units_sold=Sum('quantity'), revenue=Sum('total_cost'))
            .order_by('-revenue')[:50]
        )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="top_products_{range_param}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Rank', 'Product Name', 'SKU', 'Units Sold', 'Revenue'])
        for i, row in enumerate(products, start=1):
            writer.writerow([
                i,
                row['product_variant__product__name'],
                row['product_variant__sku'],
                row['units_sold'],
                row['revenue'],
            ])
        return response


class ExportOrdersView(VendorLoginRequiredMixin, View):
    """Export recent orders for the selected date range as a CSV download."""

    def get(self, request):
        vendor = request.user.vendor
        range_param = request.GET.get('range', '30d')
        start_date, end_date, range_label = _get_date_range(range_param)
        start_dt = datetime.datetime.combine(start_date, datetime.time.min)
        end_dt = datetime.datetime.combine(end_date, datetime.time.max)

        orders = (
            Order.objects
            .filter(vendor=vendor, created_at__range=(start_dt, end_dt))
            .select_related('customer')
            .order_by('-created_at')
        )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="orders_{range_param}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Order #', 'Date', 'Customer Phone', 'Customer Name',
            'Status', 'Payment Status', 'Payment Method',
            'Subtotal', 'Delivery', 'Total',
        ])
        for order in orders:
            writer.writerow([
                order.order_number,
                order.created_at.strftime('%Y-%m-%d %H:%M'),
                order.customer.phone,
                order.customer.get_full_name() or '—',
                order.get_status_display(),
                order.get_payment_status_display(),
                order.get_payment_method_display(),
                order.subtotal_amount,
                order.delivery_charge,
                order.total_amount,
            ])
        return response


# ────────────────────────────────────────────────────────────────
# SETTINGS VIEW
# ────────────────────────────────────────────────────────────────

class VendorSettingsView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/settings.html'

    def get(self, request):
        vendor = request.user.vendor
        context = {
            'page_title': 'Store Settings',
            'vendor': vendor,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        vendor = request.user.vendor

        vendor.business_name = request.POST.get('business_name', vendor.business_name).strip()
        vendor.email = request.POST.get('email', vendor.email).strip()
        vendor.phone = request.POST.get('phone', vendor.phone).strip()
        vendor.whatsapp_number = request.POST.get('whatsapp_number', vendor.whatsapp_number).strip()
        vendor.currency = request.POST.get('currency', vendor.currency).strip()
        vendor.currency_symbol = request.POST.get('currency_symbol', vendor.currency_symbol).strip()

        if vendor.checkout_workflow in ['online_payment', 'approval_payment', 'online_payment_stripe']:
            vendor.razorpay_key_id = request.POST.get('razorpay_key_id', vendor.razorpay_key_id).strip()
            vendor.razorpay_key_secret = request.POST.get('razorpay_key_secret', vendor.razorpay_key_secret).strip()
            vendor.stripe_public_key = request.POST.get('stripe_public_key', vendor.stripe_public_key).strip()
            vendor.stripe_secret_key = request.POST.get('stripe_secret_key', vendor.stripe_secret_key).strip()
            vendor.stripe_webhook_secret = request.POST.get('stripe_webhook_secret', vendor.stripe_webhook_secret).strip()
        elif vendor.checkout_workflow == 'whatsapp_enquiry':
            vendor.whatsapp_order_format = request.POST.get('whatsapp_order_format', '').strip()

        vendor.primary_color = request.POST.get('primary_color', vendor.primary_color).strip()
        vendor.secondary_color = request.POST.get('secondary_color', vendor.secondary_color).strip()
        vendor.top_announcement_text = request.POST.get('top_announcement_text', '')

        vendor.save()
        messages.success(request, 'Store settings updated successfully!')
        return redirect('commercehub_app:settings')


# ────────────────────────────────────────────────────────────────
# ORDER MANAGEMENT VIEWS
# ────────────────────────────────────────────────────────────────

class VendorOrderListView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/orders/list.html'

    def get(self, request):
        vendor = request.user.vendor
        status_filter = request.GET.get('status', '').strip()

        orders = Order.objects.filter(vendor=vendor)
        if status_filter:
            orders = orders.filter(status=status_filter)
        orders = orders.order_by('-created_at')

        context = {
            'page_title': 'Customer Orders',
            'orders': orders,
            'status_filter': status_filter,
            'status_choices': Order.STATUS_CHOICES,
        }
        return render(request, self.template_name, context)


class VendorOrderDetailView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/orders/detail.html'

    def get(self, request, pk):
        vendor = request.user.vendor
        order = get_object_or_404(Order, vendor=vendor, pk=pk)
        context = {
            'page_title': f'Order Details — {order.order_number}',
            'order': order,
        }
        return render(request, self.template_name, context)


class VendorOrderActionView(VendorLoginRequiredMixin, View):
    def post(self, request, pk):
        vendor = request.user.vendor
        order = get_object_or_404(Order, vendor=vendor, pk=pk)
        action = request.POST.get('action')

        if action == 'approve' and order.status == 'awaiting_approval':
            try:
                with transaction.atomic():
                    branch = order.branch
                    for o_item in order.items.all():
                        bi, _ = BranchInventory.objects.get_or_create(
                            branch=branch,
                            product_variant=o_item.product_variant,
                            defaults={'stock_qty': Decimal('0.00')}
                        )
                        bi.stock_qty = Decimal(str(bi.stock_qty)) - Decimal(str(o_item.quantity))
                        bi.save()
                        StockAdjustmentLog.objects.create(
                            vendor=vendor, branch=branch,
                            product_variant=o_item.product_variant, user=request.user,
                            quantity_changed=-o_item.quantity, reason='other',
                            notes=f'Sold via Storefront Order: {order.order_number} (Approved)'
                        )
                    order.status = 'pending'
                    order.save()
                messages.success(request, f'Order {order.order_number} approved successfully. Inventory stock levels updated.')
            except Exception as e:
                messages.error(request, f'Error approving order: {str(e)}')

        elif action == 'update_status':
            new_status = request.POST.get('status')
            if new_status in dict(Order.STATUS_CHOICES):
                old_status = order.status
                if new_status == 'cancelled' and old_status not in ['cancelled', 'awaiting_approval']:
                    try:
                        with transaction.atomic():
                            branch = order.branch
                            for o_item in order.items.all():
                                bi, _ = BranchInventory.objects.get_or_create(
                                    branch=branch,
                                    product_variant=o_item.product_variant,
                                    defaults={'stock_qty': Decimal('0.00')}
                                )
                                bi.stock_qty = Decimal(str(bi.stock_qty)) + Decimal(str(o_item.quantity))
                                bi.save()
                                StockAdjustmentLog.objects.create(
                                    vendor=vendor, branch=branch,
                                    product_variant=o_item.product_variant, user=request.user,
                                    quantity_changed=o_item.quantity, reason='other',
                                    notes=f'Restocked via Cancelled Order: {order.order_number}'
                                )
                            order.status = new_status
                            order.save()
                        messages.success(request, 'Order status updated to Cancelled. Inventory restocked.')
                    except Exception as e:
                        messages.error(request, f'Error updating status: {str(e)}')
                else:
                    order.status = new_status
                    order.save()
                    messages.success(request, f'Order status updated to {order.get_status_display()}.')

        elif action == 'update_payment_status':
            new_payment_status = request.POST.get('payment_status')
            if new_payment_status in dict(Order.PAYMENT_STATUS_CHOICES):
                order.payment_status = new_payment_status
                order.save()
                if new_payment_status == 'paid':
                    from crm.utils import credit_loyalty_points
                    credit_loyalty_points(order)
                messages.success(request, f'Order payment status updated to {order.get_payment_status_display()}.')
            else:
                messages.error(request, 'Invalid payment status selection.')

        return redirect('commercehub_app:order_detail', pk=order.pk)


# ────────────────────────────────────────────────────────────────
# EMAIL SETTINGS
# ────────────────────────────────────────────────────────────────

class VendorEmailSettingsView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/settings/email_settings.html'

    def get(self, request):
        from tenants.models import VendorEmailSettings
        settings_obj, created = VendorEmailSettings.objects.get_or_create(vendor=request.tenant)
        return render(request, self.template_name, {
            'page_title': 'Email Settings',
            'email_settings': settings_obj
        })

    def post(self, request):
        from tenants.models import VendorEmailSettings
        settings_obj, created = VendorEmailSettings.objects.get_or_create(vendor=request.tenant)

        settings_obj.email_host = request.POST.get('email_host', '').strip()
        
        try:
            settings_obj.email_port = int(request.POST.get('email_port', 587))
        except ValueError:
            settings_obj.email_port = 587
            
        settings_obj.email_host_user = request.POST.get('email_host_user', '').strip()
        settings_obj.email_host_password = request.POST.get('email_host_password', '').strip()
        settings_obj.use_tls = request.POST.get('use_tls') == 'on'
        settings_obj.default_from_email = request.POST.get('default_from_email', '').strip()
        
        settings_obj.welcome_discount_type = request.POST.get('welcome_discount_type', 'percentage')
        try:
            settings_obj.welcome_discount_value = Decimal(request.POST.get('welcome_discount_value', '10.00'))
        except:
            settings_obj.welcome_discount_value = Decimal('10.00')
            
        if 'popup_image' in request.FILES:
            settings_obj.popup_image = request.FILES['popup_image']

        settings_obj.save()
        messages.success(request, 'Email settings updated successfully.')
        return redirect('commercehub_app:email_settings')
