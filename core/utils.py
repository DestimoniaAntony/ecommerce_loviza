"""
Core Utilities — CommerceHub
"""
import random
import string
from django.conf import settings
from django.utils.text import slugify


def generate_otp(length=None):
    """Generate a numeric OTP of specified length."""
    length = length or getattr(settings, 'OTP_LENGTH', 6)
    return ''.join(random.choices(string.digits, k=length))


def generate_unique_slug(model_class, value, slug_field='slug'):
    """
    Generate a unique slug for a model instance.
    Appends numeric suffix if slug already exists.
    """
    base_slug = slugify(value)
    slug = base_slug
    counter = 1
    while model_class.objects.filter(**{slug_field: slug}).exists():
        slug = f'{base_slug}-{counter}'
        counter += 1
    return slug


def generate_order_number(vendor_id):
    """Generate a unique order number: ORD-{VENDORID}-{RANDOM6DIGIT}"""
    suffix = ''.join(random.choices(string.digits, k=6))
    return f'ORD-{vendor_id:04d}-{suffix}'


def generate_sku(product_id, variant_index):
    """Generate a default SKU for a product variant."""
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f'SKU-{product_id:05d}-{variant_index:03d}-{suffix}'


def mask_phone(phone):
    """Mask a phone number for display: 9876543210 → 98****3210"""
    if len(phone) >= 6:
        return phone[:2] + '*' * (len(phone) - 4) + phone[-4:]
    return phone


def mask_email(email):
    """Mask an email: john@example.com → j***@example.com"""
    try:
        local, domain = email.split('@')
        masked_local = local[0] + '*' * (len(local) - 1) if len(local) > 1 else local
        return f'{masked_local}@{domain}'
    except ValueError:
        return email


def send_otp_sms(phone, otp):
    """
    Send OTP via configured backend.
    OTP_BACKEND options: 'console', 'twilio', 'msg91', 'fast2sms'
    """
    backend = getattr(settings, 'OTP_BACKEND', 'console')

    if backend == 'console':
        print(f'[OTP CONSOLE] Phone: {phone} | OTP: {otp}')
        return True

    # Future: integrate Twilio, MSG91, Fast2SMS here
    return False


def get_client_ip(request):
    """Extract the real client IP from a Django request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def get_user_agent(request):
    """Extract user agent string from a request."""
    return request.META.get('HTTP_USER_AGENT', '')[:500]
