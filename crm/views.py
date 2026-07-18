from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.http import JsonResponse
from django.contrib import messages
from django.urls import reverse
from django.db import transaction, models
from decimal import Decimal
import datetime

from core.mixins import VendorLoginRequiredMixin
from accounts.models import User
from crm.models import Coupon, Wallet, WalletTransaction, LoyaltyProgram, LoyaltyLedger
from storefront.views import get_or_create_cart


class CouponApplyView(View):
    """
    AJAX endpoint to apply a coupon code to the storefront shopping cart.
    """
    def post(self, request):
        vendor = request.tenant
        if not vendor:
            return JsonResponse({'status': 'error', 'message': 'Store context not found.'}, status=400)

        code = request.POST.get('coupon_code', '').strip().upper()
        
        # If code is blank, clear any active coupon from the session
        if not code:
            if 'applied_coupon_id' in request.session:
                del request.session['applied_coupon_id']
            return JsonResponse({'status': 'success', 'message': 'Coupon cleared.', 'discount_amount': '0.00'})

        cart = get_or_create_cart(request)
        if not cart or cart.items.count() == 0:
            return JsonResponse({'status': 'error', 'message': 'Your cart is empty.'}, status=400)

        try:
            coupon = Coupon.objects.get(vendor=vendor, code=code, is_active=True)
        except Coupon.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Invalid coupon code.'}, status=400)

        # Validate active date range
        today = datetime.date.today()
        if coupon.start_date > today:
            return JsonResponse({'status': 'error', 'message': 'This coupon is not active yet.'}, status=400)
        if coupon.end_date < today:
            return JsonResponse({'status': 'error', 'message': 'This coupon has expired.'}, status=400)

        # Validate usage limits
        if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
            return JsonResponse({'status': 'error', 'message': 'This coupon usage limit has been reached.'}, status=400)

        # Validate minimum purchase subtotal
        subtotal = cart.total_price
        if subtotal < coupon.min_purchase:
            symbol = vendor.currency_symbol or '₹'
            return JsonResponse({
                'status': 'error',
                'message': f'Minimum purchase of {symbol}{coupon.min_purchase} is required to apply this coupon.'
            }, status=400)

        # Calculate discount
        if coupon.discount_type == 'percentage':
            discount = (subtotal * coupon.discount_value) / Decimal('100.00')
        else:
            discount = coupon.discount_value

        if discount > subtotal:
            discount = subtotal

        # Store applied coupon in session
        request.session['applied_coupon_id'] = coupon.id

        return JsonResponse({
            'status': 'success',
            'message': f'Coupon "{coupon.code}" applied successfully!',
            'discount_amount': f'{discount:.2f}',
            'grand_total': f'{subtotal - discount:.2f}'
        })


# ── VENDOR SIDE: COUPONS CRUD ──

class CouponListView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/crm/coupons/list.html'

    def get(self, request):
        vendor = request.user.vendor
        coupons = Coupon.objects.filter(vendor=vendor).order_by('-created_at')
        context = {
            'page_title': 'Promo Coupons',
            'coupons': coupons
        }
        return render(request, self.template_name, context)


class CouponCreateView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/crm/coupons/form.html'

    def get(self, request):
        context = {
            'page_title': 'Create Coupon',
            'action_url': reverse('crm:coupon_create')
        }
        return render(request, self.template_name, context)

    def post(self, request):
        vendor = request.user.vendor
        code = request.POST.get('code', '').strip().upper()
        discount_type = request.POST.get('discount_type')
        discount_value = Decimal(request.POST.get('discount_value', '0.00'))
        min_purchase = Decimal(request.POST.get('min_purchase', '0.00'))
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        usage_limit = request.POST.get('usage_limit')
        is_active = request.POST.get('is_active') == 'on'

        if not code or not discount_type or not start_date or not end_date:
            messages.error(request, 'Please fill in all required fields.')
            return render(request, self.template_name, {'page_title': 'Create Coupon'})

        # Validation checks
        if Coupon.objects.filter(vendor=vendor, code=code).exists():
            messages.error(request, f'Coupon code "{code}" already exists.')
            return render(request, self.template_name, {'page_title': 'Create Coupon'})

        try:
            coupon = Coupon.objects.create(
                vendor=vendor,
                code=code,
                discount_type=discount_type,
                discount_value=discount_value,
                min_purchase=min_purchase,
                start_date=start_date,
                end_date=end_date,
                usage_limit=int(usage_limit) if usage_limit else None,
                is_active=is_active
            )
            
            # Trigger background email task
            from crm.utils import send_coupon_notification_emails
            send_coupon_notification_emails(vendor.id, coupon.id, request.get_host())
            
            messages.success(request, f'Coupon {code} created successfully!')
            return redirect('crm:coupon_list')
        except Exception as e:
            messages.error(request, f'Error creating coupon: {str(e)}')
            return render(request, self.template_name, {'page_title': 'Create Coupon'})


class CouponEditView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/crm/coupons/form.html'

    def get(self, request, pk):
        vendor = request.user.vendor
        coupon = get_object_or_404(Coupon, vendor=vendor, pk=pk)
        context = {
            'page_title': f'Edit Coupon — {coupon.code}',
            'coupon': coupon,
            'action_url': reverse('crm:coupon_edit', kwargs={'pk': coupon.pk})
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        vendor = request.user.vendor
        coupon = get_object_or_404(Coupon, vendor=vendor, pk=pk)

        coupon.discount_type = request.POST.get('discount_type')
        coupon.discount_value = Decimal(request.POST.get('discount_value', '0.00'))
        coupon.min_purchase = Decimal(request.POST.get('min_purchase', '0.00'))
        coupon.start_date = request.POST.get('start_date')
        coupon.end_date = request.POST.get('end_date')
        
        usage_limit = request.POST.get('usage_limit')
        coupon.usage_limit = int(usage_limit) if usage_limit else None
        coupon.is_active = request.POST.get('is_active') == 'on'

        try:
            coupon.save()
            messages.success(request, f'Coupon {coupon.code} updated successfully!')
            return redirect('crm:coupon_list')
        except Exception as e:
            messages.error(request, f'Error updating coupon: {str(e)}')
            return render(request, self.template_name, {'page_title': 'Edit Coupon', 'coupon': coupon})


class CouponDeleteView(VendorLoginRequiredMixin, View):
    def post(self, request, pk):
        vendor = request.user.vendor
        coupon = get_object_or_404(Coupon, vendor=vendor, pk=pk)
        code = coupon.code
        coupon.delete()
        messages.success(request, f'Coupon {code} deleted successfully.')
        return redirect('crm:coupon_list')


# ── VENDOR SIDE: LOYALTY SETTINGS ──

class LoyaltySettingsView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/crm/loyalty/settings.html'

    def get(self, request):
        vendor = request.user.vendor
        program, _ = LoyaltyProgram.objects.get_or_create(vendor=vendor)
        context = {
            'page_title': 'Loyalty Rewards Program',
            'program': program
        }
        return render(request, self.template_name, context)

    def post(self, request):
        vendor = request.user.vendor
        program, _ = LoyaltyProgram.objects.get_or_create(vendor=vendor)

        program.is_enabled = request.POST.get('is_enabled') == 'on'
        program.points_per_currency = Decimal(request.POST.get('points_per_currency', '0.01'))
        program.currency_per_point = Decimal(request.POST.get('currency_per_point', '0.10'))
        program.min_points_to_redeem = int(request.POST.get('min_points_to_redeem', '100'))

        try:
            program.save()
            messages.success(request, 'Loyalty rewards configuration saved successfully!')
        except Exception as e:
            messages.error(request, f'Error saving loyalty program settings: {str(e)}')

        return redirect('crm:loyalty_settings')


# ── VENDOR SIDE: CRM CUSTOMERS & WALLETS ──

class CRMCustomerListView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/crm/customers/list.html'

    def get(self, request):
        vendor = request.user.vendor
        
        # Fetch customers registered under this vendor
        customers = User.objects.filter(user_type='customer', vendor=vendor).order_by('-date_joined')
        
        # Populate wallet and points balances dynamically
        for customer in customers:
            # Wallet balance
            wallet, _ = Wallet.objects.get_or_create(vendor=vendor, customer=customer)
            customer.wallet_balance = wallet.balance
            
            # Loyalty ledger points balance
            points_agg = LoyaltyLedger.objects.filter(
                vendor=vendor,
                customer=customer
            ).aggregate(total=models.Sum('points'))
            customer.loyalty_points = points_agg['total'] or 0

        context = {
            'page_title': 'CRM Customers',
            'customers': customers
        }
        return render(request, self.template_name, context)


class CRMCustomerDetailView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/crm/customers/detail.html'

    def get(self, request, pk):
        vendor = request.user.vendor
        customer = get_object_or_404(User, user_type='customer', vendor=vendor, pk=pk)
        
        wallet, _ = Wallet.objects.get_or_create(vendor=vendor, customer=customer)
        wallet_transactions = wallet.transactions.all().order_by('-created_at')[:50]
        
        loyalty_ledger = LoyaltyLedger.objects.filter(vendor=vendor, customer=customer).order_by('-created_at')[:50]
        
        # Aggregate points balance
        points_agg = LoyaltyLedger.objects.filter(
            vendor=vendor,
            customer=customer
        ).aggregate(total=models.Sum('points'))
        total_points = points_agg['total'] or 0

        # Orders placed by customer
        orders = customer.orders.filter(vendor=vendor).order_by('-created_at')

        context = {
            'page_title': f'Customer Profile — {customer.get_full_name() or customer.phone}',
            'customer': customer,
            'wallet': wallet,
            'wallet_transactions': wallet_transactions,
            'loyalty_ledger': loyalty_ledger,
            'total_points': total_points,
            'orders': orders
        }
        return render(request, self.template_name, context)


class CRMWalletAdjustmentView(VendorLoginRequiredMixin, View):
    """
    Handles manual vendor panel credit/debit adjustments on a customer's wallet.
    """
    def post(self, request, pk):
        vendor = request.user.vendor
        customer = get_object_or_404(User, user_type='customer', vendor=vendor, pk=pk)
        wallet, _ = Wallet.objects.get_or_create(vendor=vendor, customer=customer)

        action_type = request.POST.get('action_type')
        amount_str = request.POST.get('amount', '0.00').strip()
        reason = request.POST.get('reason', '').strip()

        if not amount_str or not reason:
            messages.error(request, 'Adjustment amount and adjustment reason are required.')
            return redirect('crm:customer_detail', pk=customer.pk)

        try:
            amount = Decimal(amount_str)
            with transaction.atomic():
                if action_type == 'credit':
                    wallet.credit(amount, f"Manual Credit: {reason}", order=None)
                    messages.success(request, f"Successfully credited {vendor.currency_symbol or '₹'}{amount} to customer's wallet.")
                elif action_type == 'debit':
                    wallet.debit(amount, f"Manual Debit: {reason}", order=None)
                    messages.success(request, f"Successfully debited {vendor.currency_symbol or '₹'}{amount} from customer's wallet.")
                else:
                    messages.error(request, 'Invalid action type selection.')
        except ValueError as val_err:
            messages.error(request, f'Wallet transaction failed: {str(val_err)}')
        except Exception as e:
            messages.error(request, f'Error applying adjustment: {str(e)}')

        return redirect('crm:customer_detail', pk=customer.pk)


class CRMLoyaltyAdjustmentView(VendorLoginRequiredMixin, View):
    """
    Handles manual vendor panel point credits/debits on a customer's loyalty ledger.
    """
    def post(self, request, pk):
        vendor = request.user.vendor
        customer = get_object_or_404(User, user_type='customer', vendor=vendor, pk=pk)

        points_str = request.POST.get('points', '').strip()
        reason = request.POST.get('reason', '').strip()

        if not points_str or not reason:
            messages.error(request, 'Adjustment points and reason description are required.')
            return redirect('crm:customer_detail', pk=customer.pk)

        try:
            points = int(points_str)
            LoyaltyLedger.objects.create(
                vendor=vendor,
                customer=customer,
                points=points,
                transaction_type='manual_adjustment',
                reason=reason
            )
            # Log the change as success
            action_str = "credited" if points >= 0 else "debited"
            messages.success(request, f"Successfully {action_str} {abs(points)} loyalty points to customer's ledger.")
        except ValueError:
            messages.error(request, 'Points must be a non-zero valid integer.')
        except Exception as e:
            messages.error(request, f'Error updating ledger: {str(e)}')

        return redirect('crm:customer_detail', pk=customer.pk)


class ContactMessageListView(VendorLoginRequiredMixin, View):
    """
    View to list all contact messages submitted via the storefront.
    """
    template_name = 'vendor/crm/messages/list.html'

    def post(self, request):
        vendor = request.user.vendor
        if 'bulk_delete' in request.POST:
            message_ids = request.POST.getlist('message_ids[]')
            if message_ids:
                from storefront.models import ContactMessage
                deleted_count, _ = ContactMessage.objects.filter(vendor=vendor, id__in=message_ids).delete()
                messages.success(request, f"{deleted_count} message(s) deleted successfully.")
            else:
                messages.warning(request, "No messages selected for deletion.")
        return redirect('crm:message_list')

    def get(self, request):
        vendor = request.user.vendor
        
        # Mark all unread as read if a parameter is passed, or handle individually in template
        if 'mark_read' in request.GET:
            from storefront.models import ContactMessage
            msg_id = request.GET.get('mark_read')
            try:
                msg = ContactMessage.objects.get(id=msg_id, vendor=vendor)
                msg.is_read = True
                msg.save()
                messages.success(request, "Message marked as read.")
            except ContactMessage.DoesNotExist:
                pass
            return redirect('crm:message_list')

        from storefront.models import ContactMessage
        from django.core.paginator import Paginator
        contact_messages_qs = ContactMessage.objects.filter(vendor=vendor).order_by('-created_at')
        
        paginator = Paginator(contact_messages_qs, 10)
        page_number = request.GET.get('page')
        contact_messages = paginator.get_page(page_number)
        
        context = {
            'page_title': 'Contact Messages',
            'contact_messages': contact_messages,
        }
        return render(request, self.template_name, context)

# ── VENDOR SIDE: NEWSLETTER SUBSCRIBERS ──

class NewsletterSubscriberListView(VendorLoginRequiredMixin, View):
    template_name = 'vendor/crm/subscribers/list.html'

    def post(self, request):
        vendor = request.user.vendor
        if 'bulk_delete' in request.POST:
            subscriber_ids = request.POST.getlist('subscriber_ids[]')
            if subscriber_ids:
                from crm.models import NewsletterSubscriber
                deleted_count, _ = NewsletterSubscriber.objects.filter(vendor=vendor, id__in=subscriber_ids).delete()
                messages.success(request, f"{deleted_count} subscriber(s) deleted successfully.")
            else:
                messages.warning(request, "No subscribers selected for deletion.")
        return redirect(request.path)

    def get(self, request):
        from crm.models import NewsletterSubscriber
        from django.core.paginator import Paginator
        vendor = request.user.vendor
        subscribers_qs = NewsletterSubscriber.objects.filter(vendor=vendor).select_related('coupon').order_by('-created_at')
        
        paginator = Paginator(subscribers_qs, 10)
        page_number = request.GET.get('page')
        subscribers = paginator.get_page(page_number)
        
        context = {
            'page_title': 'Newsletter Subscribers',
            'subscribers': subscribers,
        }
        return render(request, self.template_name, context)
