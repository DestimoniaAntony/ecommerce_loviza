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
from catalog.models import Product, Category


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

    total_products_count = Product.objects.filter(vendor=vendor).count()

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
        'total_products_count': total_products_count,
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

        new_phone = request.POST.get('phone', vendor.phone).strip()
        new_email = request.POST.get('email', vendor.email).strip()

        if new_phone != request.user.phone:
            from accounts.models import User
            if User.objects.filter(phone=new_phone).exclude(id=request.user.id).exists():
                messages.error(request, 'This phone number is already registered by another account. Store phone updated, but login phone remains unchanged.')
            else:
                request.user.phone = new_phone
                request.user.save()

        if new_email and new_email != request.user.email:
            request.user.email = new_email
            request.user.save()

        vendor.business_name = request.POST.get('business_name', vendor.business_name).strip()
        vendor.email = new_email
        vendor.phone = new_phone
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

        orders_qs = Order.objects.filter(vendor=vendor)
        if status_filter:
            orders_qs = orders_qs.filter(status=status_filter)
        orders_qs = orders_qs.order_by('-created_at')

        from django.core.paginator import Paginator
        paginator = Paginator(orders_qs, 20)
        page_number = request.GET.get('page')
        orders = paginator.get_page(page_number)

        context = {
            'page_title': 'Customer Orders',
            'orders': orders,
            'status_filter': status_filter,
            'status_choices': Order.STATUS_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        vendor = request.user.vendor
        action = request.POST.get('action')
        
        if action == 'bulk_delete':
            order_ids = request.POST.getlist('order_ids')
            if order_ids:
                deleted_count, _ = Order.objects.filter(vendor=vendor, id__in=order_ids, status='pending').delete()
                if deleted_count == len(order_ids):
                    messages.success(request, f'Successfully deleted {deleted_count} order(s).')
                elif deleted_count > 0:
                    messages.warning(request, f'Deleted {deleted_count} pending order(s). Some orders were not deleted because they are not in Pending status.')
                else:
                    messages.error(request, 'Could not delete the selected orders because they are not in Pending status.')
            else:
                messages.warning(request, 'No orders selected for deletion.')
                
        return redirect('commercehub_app:order_list')


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
                
                # Prevent backward status flow
                status_order = ['pending', 'awaiting_approval', 'processing', 'shipped', 'delivered']
                if new_status != 'cancelled' and old_status != 'cancelled':
                    old_idx = status_order.index(old_status) if old_status in status_order else -1
                    new_idx = status_order.index(new_status) if new_status in status_order else -1
                    
                    if new_idx < old_idx and new_idx != -1 and old_idx != -1:
                        messages.error(request, f'Cannot revert order status from {order.get_status_display()} to {dict(Order.STATUS_CHOICES).get(new_status)}.')
                        return redirect('commercehub_app:order_detail', pk=pk)

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


# ────────────────────────────────────────────────────────────────
# CAROUSEL SETTINGS
# ────────────────────────────────────────────────────────────────

from storefront.models import CarouselSlide

class VendorCarouselListView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/settings/carousel_list.html'

    def get(self, request):
        slides = CarouselSlide.objects.filter(vendor=request.user.vendor)
        return render(request, self.template_name, {
            'page_title': 'Carousel Settings',
            'slides': slides
        })


class VendorCarouselCreateView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/settings/carousel_form.html'

    def get(self, request):
        categories = Category.objects.filter(vendor=request.user.vendor, is_active=True).order_by('name')
        products = Product.objects.filter(vendor=request.user.vendor, status='published').order_by('name')
        return render(request, self.template_name, {
            'page_title': 'Add Carousel Slide',
            'categories': categories,
            'products': products
        })

    def post(self, request):
        vendor = request.user.vendor
        label = request.POST.get('label', '').strip()
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        button_text = request.POST.get('button_text', '').strip()
        button_link = request.POST.get('button_link', '').strip()
        order = request.POST.get('order', 0)
        is_active = request.POST.get('is_active') == 'on'
        
        image = request.FILES.get('image')
        if not image:
            messages.error(request, 'Image is required for a carousel slide.')
            return redirect('commercehub_app:carousel_create')
            
        try:
            order = int(order)
        except ValueError:
            order = 0

        CarouselSlide.objects.create(
            vendor=vendor,
            label=label,
            title=title,
            description=description,
            button_text=button_text,
            button_link=button_link,
            order=order,
            is_active=is_active,
            image=image
        )
        messages.success(request, 'Carousel slide created successfully.')
        return redirect('commercehub_app:carousel_list')


class VendorCarouselEditView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/settings/carousel_form.html'

    def get(self, request, pk):
        slide = get_object_or_404(CarouselSlide, pk=pk, vendor=request.user.vendor)
        categories = Category.objects.filter(vendor=request.user.vendor, is_active=True).order_by('name')
        products = Product.objects.filter(vendor=request.user.vendor, status='published').order_by('name')
        return render(request, self.template_name, {
            'page_title': 'Edit Carousel Slide',
            'slide': slide,
            'categories': categories,
            'products': products
        })

    def post(self, request, pk):
        slide = get_object_or_404(CarouselSlide, pk=pk, vendor=request.user.vendor)
        
        slide.label = request.POST.get('label', '').strip()
        slide.title = request.POST.get('title', '').strip()
        slide.description = request.POST.get('description', '').strip()
        slide.button_text = request.POST.get('button_text', '').strip()
        slide.button_link = request.POST.get('button_link', '').strip()
        slide.is_active = request.POST.get('is_active') == 'on'
        
        try:
            slide.order = int(request.POST.get('order', slide.order))
        except ValueError:
            pass
            
        if 'image' in request.FILES:
            slide.image = request.FILES['image']
            
        slide.save()
        messages.success(request, 'Carousel slide updated successfully.')
        return redirect('commercehub_app:carousel_list')


class VendorCarouselDeleteView(VendorLoginRequiredMixin, View):
    def post(self, request, pk):
        slide = get_object_or_404(CarouselSlide, pk=pk, vendor=request.user.vendor)
        slide.delete()
        messages.success(request, 'Carousel slide deleted successfully.')
        return redirect('commercehub_app:carousel_list')
