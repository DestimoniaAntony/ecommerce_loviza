from decimal import Decimal
import datetime
from django.db import models
from crm.models import Coupon, LoyaltyProgram, LoyaltyLedger

def calculate_order_discounts(request, subtotal, loyalty_redeemed=False):
    """
    Calculates dynamic discounts from applied coupons and loyalty point redemptions.
    Returns: {
        'coupon': Coupon instance or None,
        'coupon_discount': Decimal,
        'points_redeemed': int,
        'loyalty_discount': Decimal,
        'grand_total': Decimal
    }
    """
    vendor = request.tenant
    user = request.user
    
    coupon = None
    coupon_discount = Decimal('0.00')
    points_redeemed = 0
    loyalty_discount = Decimal('0.00')
    
    # 1. Coupon Discount
    coupon_id = request.session.get('applied_coupon_id')
    if coupon_id:
        try:
            c = Coupon.objects.get(id=coupon_id, vendor=vendor, is_active=True)
            today = datetime.date.today()
            if c.start_date <= today <= c.end_date:
                if c.usage_limit is None or c.used_count < c.usage_limit:
                    if subtotal >= c.min_purchase:
                        coupon = c
                        if c.discount_type == 'percentage':
                            coupon_discount = (subtotal * c.discount_value) / Decimal('100.00')
                        else:
                            coupon_discount = c.discount_value
                        if coupon_discount > subtotal:
                            coupon_discount = subtotal
        except Coupon.DoesNotExist:
            if 'applied_coupon_id' in request.session:
                del request.session['applied_coupon_id']
                
    remaining_subtotal = subtotal - coupon_discount

    # 2. Loyalty Point Discount
    if loyalty_redeemed and user.is_authenticated and user.user_type == 'customer':
        loyalty_program = getattr(vendor, 'loyalty_program', None)
        if loyalty_program and loyalty_program.is_enabled:
            # Aggregate points from ledger
            points_agg = LoyaltyLedger.objects.filter(
                vendor=vendor,
                customer=user
            ).aggregate(total=models.Sum('points'))
            user_points = points_agg['total'] or 0
            
            if user_points >= loyalty_program.min_points_to_redeem:
                points_redeemed = user_points
                loyalty_discount = Decimal(str(points_redeemed)) * loyalty_program.currency_per_point
                
                # Cap discount at remaining subtotal
                if loyalty_discount > remaining_subtotal:
                    loyalty_discount = remaining_subtotal
                    # Recalculate actual points needed if discount was capped
                    if loyalty_program.currency_per_point > 0:
                        points_redeemed = int(loyalty_discount / loyalty_program.currency_per_point)

    grand_total = remaining_subtotal - loyalty_discount
    if grand_total < Decimal('0.00'):
        grand_total = Decimal('0.00')

    return {
        'coupon': coupon,
        'coupon_discount': coupon_discount,
        'points_redeemed': points_redeemed,
        'loyalty_discount': loyalty_discount,
        'grand_total': grand_total
    }


def credit_loyalty_points(order):
    """
    Credits loyalty points to a customer based on paid order total amount.
    """
    vendor = order.vendor
    customer = order.customer
    
    # Validation checks
    if getattr(customer, 'user_type', '') != 'customer':
        return
        
    loyalty_program = getattr(vendor, 'loyalty_program', None)
    if not loyalty_program or not loyalty_program.is_enabled:
        return
        
    # Check if points were already credited for this order
    already_credited = LoyaltyLedger.objects.filter(
        vendor=vendor,
        customer=customer,
        reference_order=order,
        transaction_type='earn'
    ).exists()
    
    if already_credited:
        return
        
    # Calculate earned points (points earned based on points_per_currency spent)
    points_earned = int(order.total_amount * loyalty_program.points_per_currency)
    
    if points_earned > 0 and not already_credited:
        LoyaltyLedger.objects.create(
            vendor=vendor,
            customer=customer,
            points=points_earned,
            transaction_type='earn',
            reference_order=order,
            reason=f'Earned from Order {order.order_number}'
        )

import threading
from django.core.signing import Signer
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.smtp import EmailBackend
from django.template.loader import render_to_string
from crm.models import NewsletterSubscriber
from tenants.models import VendorEmailSettings, Vendor

def _send_emails_thread(vendor_id, coupon_id, request_host):
    try:
        vendor = Vendor.objects.get(id=vendor_id)
        coupon = Coupon.objects.get(id=coupon_id)
        settings_obj = VendorEmailSettings.objects.filter(vendor=vendor).first()
        
        # If no SMTP settings configured, we can't send vendor-specific emails
        if not settings_obj or not settings_obj.email_host_user:
            return

        subscribers = NewsletterSubscriber.objects.filter(vendor=vendor, is_active=True)
        if not subscribers.exists():
            return

        backend = EmailBackend(
            host=settings_obj.email_host,
            port=settings_obj.email_port,
            username=settings_obj.email_host_user,
            password=settings_obj.email_host_password,
            use_tls=settings_obj.use_tls,
            fail_silently=True
        )

        signer = Signer()
        from_email = settings_obj.email_host_user

        messages = []
        for sub in subscribers:
            token = signer.sign(str(sub.id))
            unsubscribe_url = f"http://{request_host}/unsubscribe/{token}/"
            
            context = {
                'subscriber': sub,
                'coupon': coupon,
                'vendor': vendor,
                'unsubscribe_url': unsubscribe_url,
            }
            html_content = render_to_string('emails/new_coupon_notification.html', context)
            
            msg = EmailMultiAlternatives(
                subject=f"New Special Offer from {vendor.business_name}!",
                body=f"Use code {coupon.code} to get a discount. Unsubscribe here: {unsubscribe_url}",
                from_email=from_email,
                to=[sub.email],
            )
            msg.attach_alternative(html_content, "text/html")
            messages.append(msg)

        backend.send_messages(messages)
    except Exception as e:
        print(f"Failed to send coupon notifications: {e}")

def send_coupon_notification_emails(vendor_id, coupon_id, request_host):
    """
    Spawns a background thread to email all active subscribers about a new coupon.
    """
    thread = threading.Thread(target=_send_emails_thread, args=(vendor_id, coupon_id, request_host))
    thread.daemon = True
    thread.start()
