from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.contrib import messages
from django.db import transaction, models
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from decimal import Decimal
import datetime
import random
import string
from django.utils import timezone
from tenants.models import Vendor
from branches.models import Branch
from catalog.models import Product, ProductVariant, Category
from inventory.models import BranchInventory, StockAdjustmentLog
from accounts.models import User
from .models import CustomerAddress, Cart, CartItem, Order, OrderItem


def generate_order_number(vendor):
    today = datetime.date.today().strftime('%Y%m%d')
    prefix = f"ORD-{today}-"
    last_ord = Order.objects.filter(vendor=vendor, order_number__startswith=prefix).order_by('-order_number').first()
    if last_ord:
        try:
            seq = int(last_ord.order_number.split('-')[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def get_or_create_cart(request):
    """
    Utility to fetch or create a cart for the current session or customer.
    """
    vendor = request.tenant
    if not vendor:
        return None

    if request.user.is_authenticated and request.user.user_type == 'customer':
        cart, _ = Cart.objects.get_or_create(vendor=vendor, customer=request.user)
        return cart

    # Guest session cart
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    cart, _ = Cart.objects.get_or_create(vendor=vendor, session_key=session_key)
    return cart


def merge_carts(request, user):
    """
    Merges anonymous session cart into customer cart upon login.
    """
    vendor = request.tenant
    if not vendor or not request.session.session_key:
        return

    session_key = request.session.session_key
    guest_cart = Cart.objects.filter(vendor=vendor, session_key=session_key).first()
    if not guest_cart:
        return

    customer_cart, _ = Cart.objects.get_or_create(vendor=vendor, customer=user)

    with transaction.atomic():
        for item in guest_cart.items.all():
            cust_item, created = CartItem.objects.get_or_create(
                cart=customer_cart,
                product_variant=item.product_variant,
                defaults={'quantity': item.quantity}
            )
            if not created:
                cust_item.quantity += item.quantity
                cust_item.save()
        
        # Delete guest cart after merging
        guest_cart.delete()


# ─────────────────────────────────────────────────────────────
# BROWSING VIEWS
# ─────────────────────────────────────────────────────────────

class StorefrontHomeView(View):
    template_name = 'storefront/home.html'

    def get(self, request):
        vendor = request.tenant
        if not vendor:
            # Platform root access -> redirect to super admin login
            return redirect('accounts:admin_login')

        categories = Category.objects.filter(vendor=vendor, is_active=True).order_by('name')[:6]
        featured_products = Product.objects.filter(vendor=vendor, status='published').order_by('-created_at')[:8]
        from .models import CarouselSlide
        carousel_slides = CarouselSlide.objects.filter(vendor=vendor, is_active=True).order_by('order')

        context = {
            'page_title': vendor.business_name,
            'categories': categories,
            'featured_products': featured_products,
            'carousel_slides': carousel_slides,
            'cart': get_or_create_cart(request),
        }
        return render(request, self.template_name, context)


class CollectionsListView(View):
    template_name = 'storefront/collections.html'

    def get(self, request):
        vendor = request.tenant
        if not vendor:
            return redirect('accounts:admin_login')

        categories = Category.objects.filter(
            vendor=vendor, 
            is_active=True, 
            parent__isnull=True
        ).order_by('name')[:3]
        
        context = {
            'page_title': 'Collections',
            'categories': categories,
            'cart': get_or_create_cart(request),
        }
        return render(request, self.template_name, context)


class ContactView(View):
    template_name = 'storefront/contact.html'

    def get(self, request):
        vendor = request.tenant
        if not vendor:
            return redirect('accounts:admin_login')
            
        context = {
            'page_title': 'Contact Us',
            'cart': get_or_create_cart(request),
            'vendor': vendor,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        vendor = request.tenant
        if not vendor:
            return redirect('accounts:admin_login')

        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        message = request.POST.get('message', '').strip()

        if name and email and message:
            try:
                from .models import ContactMessage
                ContactMessage.objects.create(
                    vendor=vendor,
                    name=name,
                    email=email,
                    phone=phone,
                    message=message
                )
                messages.success(request, 'Your message has been sent successfully. We will get back to you soon!')
                return redirect('storefront:contact')
            except Exception as e:
                messages.error(request, 'An error occurred while sending your message. Please try again.')
        else:
            messages.error(request, 'Please fill in all required fields.')
        
        context = {
            'page_title': 'Contact Us',
            'cart': get_or_create_cart(request),
            'form_data': request.POST,
            'vendor': vendor,
        }
        return render(request, self.template_name, context)


class StorefrontSearchAPIView(View):
    def get(self, request):
        vendor = request.tenant
        if not vendor:
            return JsonResponse({'products': [], 'categories': []})

        q = request.GET.get('q', '').strip()
        if not q:
            return JsonResponse({'products': [], 'categories': []})

        # Match Categories (Suggestions)
        categories = Category.objects.filter(
            vendor=vendor,
            is_active=True,
            name__icontains=q
        ).order_by('name')[:5]

        cat_results = []
        for cat in categories:
            from django.urls import reverse
            cat_results.append({
                'title': cat.name,
                'url': reverse('storefront:catalog') + f'?category={cat.slug}'
            })

        # Match Products
        products = Product.objects.filter(
            vendor=vendor,
            status='published',
        ).filter(
            models.Q(name__icontains=q) |
            models.Q(description__icontains=q)
        ).order_by('-created_at')[:5]

        prod_results = []
        currency = getattr(vendor, 'currency_symbol', '₹')
        for prod in products:
            from django.urls import reverse
            url = reverse('storefront:product_detail', args=[prod.slug])
            
            # Use price_range / compare_at logic
            price_text = f"{currency}{prod.price_range.replace('₹', '')}" if '₹' in prod.price_range else prod.price_range
            
            compare_price_text = ""
            if prod.compare_at_price_range:
                compare_price_text = f"{currency}{prod.compare_at_price_range.replace('₹', '')}"
            
            # Find image
            img_url = ""
            if prod.variants.exists():
                variant = prod.variants.first()
                if variant.image:
                    img_url = variant.image.url
            if not img_url:
                from django.templatetags.static import static
                img_url = static('storefront/images/product_main.png')

            prod_results.append({
                'title': prod.name,
                'url': url,
                'price': price_text,
                'compare_at': compare_price_text,
                'image_url': img_url
            })

        return JsonResponse({
            'categories': cat_results,
            'products': prod_results,
        })


class ProductCatalogView(View):
    template_name = 'storefront/catalog.html'

    def get(self, request):
        vendor = request.tenant
        if not vendor:
            return redirect('accounts:admin_login')

        categories = Category.objects.filter(vendor=vendor, is_active=True).order_by('name')
        
        cat_slug = request.GET.get('category', '')
        q = request.GET.get('q', '').strip()

        products = Product.objects.filter(vendor=vendor, status='published')
        
        selected_category = None
        if cat_slug:
            selected_category = get_object_or_404(Category, vendor=vendor, slug=cat_slug, is_active=True)
            # Filter by category and its descendants
            descendant_ids = selected_category.get_descendants(include_self=True).values_list('id', flat=True)
            products = products.filter(category_id__in=descendant_ids)

        if q:
            products = products.filter(
                models.Q(name__icontains=q) |
                models.Q(description__icontains=q)
            )

        sort_by = request.GET.get('sort_by', 'created-descending')

        if sort_by == 'title-ascending':
            products = products.order_by('name')
        elif sort_by == 'title-descending':
            products = products.order_by('-name')
        elif sort_by == 'created-ascending':
            products = products.order_by('created_at')
        elif sort_by == 'price-ascending':
            from django.db.models import Min
            products = products.annotate(min_price=Min('variants__price')).order_by('min_price')
        elif sort_by == 'price-descending':
            from django.db.models import Min
            products = products.annotate(min_price=Min('variants__price')).order_by('-min_price')
        else:
            products = products.order_by('-created_at')

        from django.core.paginator import Paginator
        paginator = Paginator(products, 24)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        # Recently viewed products logic
        recently_viewed_ids = request.session.get('recently_viewed', [])
        recently_viewed_products = []
        if recently_viewed_ids:
            rv_prods = Product.objects.filter(id__in=recently_viewed_ids, vendor=vendor, status='published')
            rv_dict = {p.id: p for p in rv_prods}
            recently_viewed_products = [rv_dict[pid] for pid in recently_viewed_ids if pid in rv_dict][:10]
        else:
            # Fallback to show latest products if history is empty, so the section is always visible
            recently_viewed_products = Product.objects.filter(vendor=vendor, status='published')[:5]

        context = {
            'products': page_obj,
            'page_obj': page_obj,
            'recently_viewed_products': recently_viewed_products,
            'categories': categories,
            'selected_category': selected_category,
            'q': q,
            'sort_by': sort_by,
            'cart': get_or_create_cart(request),
            'page_title': f'All Products — {vendor.business_name}',
        }
        return render(request, self.template_name, context)

# --- Static Pages ---
class PrivacyPolicyView(View):
    def get(self, request):
        return render(request, 'storefront/pages/privacy_policy.html')

class ReturnsRefundsView(View):
    def get(self, request):
        return render(request, 'storefront/pages/returns_refunds.html')

class ShippingDeliveryView(View):
    def get(self, request):
        return render(request, 'storefront/pages/shipping_delivery.html')

class TermsOfServiceView(View):
    def get(self, request):
        return render(request, 'storefront/pages/terms_of_service.html')

class AboutUsView(View):
    def get(self, request):
        return render(request, 'storefront/pages/about_us.html')


class ProductDetailView(View):
    template_name = 'storefront/product_detail.html'

    def get(self, request, slug):
        vendor = request.tenant
        if not vendor:
            return redirect('accounts:admin_login')

        product = get_object_or_404(Product, vendor=vendor, slug=slug, status='published')
        
        # Track recently viewed products
        recently_viewed = request.session.get('recently_viewed', [])
        if product.id in recently_viewed:
            recently_viewed.remove(product.id)
        recently_viewed.insert(0, product.id)
        request.session['recently_viewed'] = recently_viewed[:10]

        variants = product.variants.filter(is_active=True)
        default_variant = variants.first()

        related_products = []
        if product.category:
            related_products = Product.objects.filter(
                vendor=vendor, 
                category=product.category, 
                status='published'
            ).exclude(id=product.id)[:4]

        general_attributes_display = []
        if product.attributes_data:
            from catalog.models import Attribute
            attr_codes = product.attributes_data.keys()
            attrs = Attribute.objects.filter(vendor=vendor, code__in=attr_codes)
            attr_map = {a.code: a for a in attrs}
            
            for code, val in product.attributes_data.items():
                if code in attr_map:
                    attr = attr_map[code]
                    display_val = "Yes" if val == 'true' else "No" if val == 'false' else val
                    general_attributes_display.append({
                        'name': attr.name,
                        'value': display_val
                    })

        # Process variants for grouped display
        import json
        variant_options_list = []
        variants_data = {}
        
        if product.has_variants and variants.exists():
            from catalog.models import Attribute
            all_attr_codes = set()
            for v in variants:
                all_attr_codes.update(v.attributes_data.keys())
            all_attr_codes.discard('is_customizable')
            
            ordered_codes = sorted(list(all_attr_codes))
            attrs = Attribute.objects.filter(vendor=vendor, code__in=ordered_codes).prefetch_related('options')
            attr_map = {a.code: a for a in attrs}
            
            for code in ordered_codes:
                name = attr_map[code].name if code in attr_map else code.title()
                variant_options_list.append({
                    'code': code,
                    'name': name,
                    'values': []
                })
            
            for v in variants:
                for code in ordered_codes:
                    val = v.attributes_data.get(code, '')
                    # Add to values list if not present
                    opt_dict = next(item for item in variant_options_list if item["code"] == code)
                    if val and val not in opt_dict['values']:
                        opt_dict['values'].append(val)
            
            # Sort the options to match the vendor panel sequence
            for opt_dict in variant_options_list:
                code = opt_dict['code']
                if code in attr_map:
                    db_options = [o.value for o in attr_map[code].options.all()]
                    if db_options:
                        opt_dict['values'].sort(key=lambda x: db_options.index(x) if x in db_options else 999)
            
            for v in variants:
                combo_key_parts = []
                for code in ordered_codes:
                    val = v.attributes_data.get(code, '')
                    combo_key_parts.append(val)
                
                combo_key = "|".join(combo_key_parts)
                
                img_url = ""
                if v.image:
                    img_url = v.image.url
                elif hasattr(product, 'image') and product.image:
                    img_url = product.image.url
                elif product.images.first():
                    img_url = product.images.first().image.url
                
                # Import convert_price locally to avoid circular import issues if any
                from storefront.templatetags.currency_tags import convert_price

                variants_data[combo_key] = {
                    'id': v.id,
                    'price': convert_price(request, v.price),
                    'compare_at_price': convert_price(request, v.compare_at_price) if v.compare_at_price else '',
                    'discount_percentage': v.discount_percentage,
                    'stock_qty': float(v.stock_qty),
                    'image_url': img_url,
                    'is_customizable': v.attributes_data.get('is_customizable', False)
                }

        custom_fields_list = []
        if product.attributes_data and 'custom_fields' in product.attributes_data:
            cf_str = product.attributes_data.get('custom_fields', '')
            custom_fields_list = [x.strip() for x in cf_str.split(',') if x.strip()]

        context = {
            'product': product,
            'variants': variants,
            'default_variant': default_variant,
            'variant_options': variant_options_list,
            'variants_data_json': json.dumps(variants_data),
            'related_products': related_products,
            'general_attributes_display': general_attributes_display,
            'custom_fields_list': custom_fields_list,
            'cart': get_or_create_cart(request),
            'page_title': f'{product.name} — {vendor.business_name}',
        }
        return render(request, self.template_name, context)


# ─────────────────────────────────────────────────────────────
# CUSTOMER AUTHENTICATION
# ─────────────────────────────────────────────────────────────

class CustomerLoginView(View):
    template_name = 'storefront/login.html'

    def get(self, request):
        if request.user.is_authenticated and getattr(request.user, 'user_type', '') == 'customer':
            return redirect('storefront:home')
        return render(request, self.template_name, {
            'page_title': 'Customer Login',
            'cart': get_or_create_cart(request)
        })

    def post(self, request):
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()

        if not email or not password:
            messages.error(request, 'Email and password are required.')
            return render(request, self.template_name, {
                'page_title': 'Customer Login',
                'cart': get_or_create_cart(request)
            })

        # Authenticate via EmailPasswordBackend
        user = authenticate(request, email=email, password=password)
        if user and user.user_type == 'customer' and user.vendor == request.tenant:
            merge_carts(request, user)
            login(request, user, backend='accounts.backends.EmailPasswordBackend')
            messages.success(request, f'Welcome back, {user.get_short_name()}!')
            next_url = request.GET.get('next')
            return redirect(next_url if next_url else 'storefront:home')
        else:
            messages.error(request, 'Invalid email address or password.')
            return render(request, self.template_name, {
                'page_title': 'Customer Login',
                'cart': get_or_create_cart(request)
            })

class ForgotPasswordView(View):
    def post(self, request):
        email = request.POST.get('email', '').strip()
        if not email:
            messages.error(request, 'Please provide an email address.')
            return redirect('storefront:login')

        user = User.objects.filter(email=email, user_type='customer', vendor=request.tenant).first()
        if user:
            import string, random
            # Generate new 8-character random password
            chars = string.ascii_letters + string.digits
            new_password = ''.join(random.choice(chars) for _ in range(8))
            
            # Update password
            user.set_password(new_password)
            user.save()

            # Send email
            try:
                from django.core.mail import EmailMessage
                from django.core.mail.backends.smtp import EmailBackend
                from django.template.loader import render_to_string
                from tenants.models import VendorEmailSettings
                
                settings_obj = VendorEmailSettings.objects.filter(vendor=request.tenant).first()
                if settings_obj and settings_obj.email_host_user:
                    backend = EmailBackend(
                        host=settings_obj.email_host,
                        port=settings_obj.email_port,
                        username=settings_obj.email_host_user,
                        password=settings_obj.email_host_password,
                        use_tls=settings_obj.use_tls,
                        fail_silently=False
                    )
                    context = {
                        'first_name': user.first_name,
                        'email': user.email,
                        'password': new_password,
                        'store_name': request.tenant.business_name
                    }
                    html_content = render_to_string('emails/password_reset.html', context)
                    
                    email_msg = EmailMessage(
                        subject=f"Your new password for {request.tenant.business_name}",
                        body=html_content,
                        from_email=settings_obj.default_from_email or settings_obj.email_host_user,
                        to=[user.email],
                        connection=backend
                    )
                    email_msg.content_subtype = "html"
                    email_msg.send()
                messages.success(request, 'A new password has been sent to your email address.')
            except Exception as e:
                print(f"Error sending password reset: {e}")
                messages.error(request, 'Failed to send password reset email. Please contact support.')
        else:
            messages.error(request, 'No customer account found with that email address.')
        
        return redirect('storefront:login')


class CustomerRegisterView(View):
    template_name = 'storefront/register.html'

    def get(self, request):
        if request.user.is_authenticated and getattr(request.user, 'user_type', '') == 'customer':
            return redirect('storefront:home')
        return render(request, self.template_name, {
            'page_title': 'Customer Register',
            'cart': get_or_create_cart(request)
        })

    def post(self, request):
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()

        if not first_name or not phone or not email or not password:
            messages.error(request, 'First name, phone number, email, and password are required.')
            return render(request, self.template_name, {
                'page_title': 'Customer Register',
                'cart': get_or_create_cart(request)
            })

        # Check if email exists
        if User.objects.filter(email=email).exists():
            messages.error(request, 'An account with this email address already exists. Please log in.')
            return redirect('storefront:login')

        # Check if phone exists
        if User.objects.filter(phone=phone).exists():
            messages.error(request, 'An account with this phone number already exists. Please log in.')
            return redirect('storefront:login')

        with transaction.atomic():
            user = User.objects.create_user(
                phone=phone,
                password=password,
                email=email,
                first_name=first_name,
                last_name=last_name,
                user_type='customer',
                vendor=request.tenant,
                is_active=True
            )
            
        # Send welcome email with credentials
        try:
            from django.core.mail import EmailMessage
            from django.core.mail.backends.smtp import EmailBackend
            from django.template.loader import render_to_string
            from tenants.models import VendorEmailSettings
            
            settings_obj = VendorEmailSettings.objects.filter(vendor=request.tenant).first()
            if settings_obj and settings_obj.email_host_user:
                backend = EmailBackend(
                    host=settings_obj.email_host,
                    port=settings_obj.email_port,
                    username=settings_obj.email_host_user,
                    password=settings_obj.email_host_password,
                    use_tls=settings_obj.use_tls,
                    fail_silently=False
                )
                context = {
                    'first_name': first_name,
                    'email': email,
                    'password': password,
                    'store_name': request.tenant.business_name
                }
                html_content = render_to_string('emails/welcome_with_credentials.html', context)
                
                email_msg = EmailMessage(
                    subject=f"Welcome to {request.tenant.business_name}! Your account details",
                    body=html_content,
                    from_email=settings_obj.default_from_email or settings_obj.email_host_user,
                    to=[email],
                    connection=backend
                )
                email_msg.content_subtype = "html"
                email_msg.send()
        except Exception as e:
            print(f"Error sending credentials: {e}")

        merge_carts(request, user)
        login(request, user, backend='accounts.backends.EmailPasswordBackend')
        messages.success(request, f'Welcome to our store, {first_name}!')
        return redirect('storefront:home')


class CustomerLogoutView(View):
    def get(self, request):
        logout(request)
        messages.success(request, 'Logged out successfully.')
        return redirect('storefront:home')


# ─────────────────────────────────────────────────────────────
# SHOPPING CART CRUD
# ─────────────────────────────────────────────────────────────

class CartView(View):
    template_name = 'storefront/cart.html'

    def get(self, request):
        cart = get_or_create_cart(request)
        
        # Get 4 random products for the "Recently Viewed / Recommended" section
        vendor = request.tenant
        recommended_products = Product.objects.filter(vendor=vendor, status='published').order_by('?')[:4]
        
        subtotal = cart.total_price
        from crm.utils import calculate_order_discounts
        discounts = calculate_order_discounts(request, subtotal, loyalty_redeemed=False)
        
        context = {
            'cart': cart,
            'recommended_products': recommended_products,
            'subtotal': subtotal,
            'coupon': discounts['coupon'],
            'coupon_discount': discounts['coupon_discount'],
            'grand_total': discounts['grand_total'],
            'page_title': 'Shopping Cart',
        }
        return render(request, self.template_name, context)


class CartAddView(View):
    def post(self, request):
        variant_id = request.POST.get('variant_id')
        qty_str = request.POST.get('quantity', '1')
        qty = int(qty_str) if qty_str.isdigit() else 1

        vendor = request.tenant
        variant = get_object_or_404(ProductVariant, product__vendor=vendor, pk=variant_id)
        
        cart = get_or_create_cart(request)
        
        # Check stock if tracking is enabled
        if vendor.track_inventory:
            current_cart_qty = sum(item.quantity for item in cart.items.filter(product_variant=variant))
            
            if (current_cart_qty + qty) > variant.stock_qty:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                    from django.http import JsonResponse
                    return JsonResponse({'status': 'error', 'message': f'Only {variant.stock_qty} items in stock.'})
                messages.error(request, f'Cannot add {qty} more items. Only {variant.stock_qty} items in stock.')
                return redirect('storefront:cart')

        custom_data = {}
        for key, value in request.POST.items():
            if key.startswith('custom_') and value.strip():
                clean_key = key[7:]
                custom_data[clean_key] = value.strip()
                
        is_customized = request.POST.get('is_customized') == 'true'
        if is_customized:
            custom_data['is_customized'] = True
            
            raw_base_price = variant.product.attributes_data.get('base_price', variant.price)
            custom_data['_base_price'] = str(raw_base_price)
            
            raw_custom_fee = variant.product.attributes_data.get('custom_fee', '0.00')
            custom_data['_custom_fee'] = str(raw_custom_fee)
                
        existing_items = cart.items.filter(product_variant=variant)
        found_item = None
        for i in existing_items:
            if i.customization_data == custom_data:
                found_item = i
                break
                
        if found_item:
            found_item.quantity += qty
            found_item.save()
        else:
            CartItem.objects.create(
                cart=cart,
                product_variant=variant,
                quantity=qty,
                customization_data=custom_data
            )

        # messages.success(request, f'"{variant.product.name}" added to cart.')
        
        referer = request.META.get('HTTP_REFERER')
        if referer:
            from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
            url_parts = list(urlparse(referer))
            query = dict(parse_qsl(url_parts[4]))
            query['cart_open'] = '1'
            url_parts[4] = urlencode(query)
            return redirect(urlunparse(url_parts))

        return redirect('storefront:cart')


class CartUpdateView(View):
    def post(self, request):
        item_id = request.POST.get('item_id')
        qty_str = request.POST.get('quantity', '1')
        qty = int(qty_str) if qty_str.isdigit() else 1

        cart = get_or_create_cart(request)
        item = get_object_or_404(CartItem, cart=cart, pk=item_id)
        
        referer = request.META.get('HTTP_REFERER')
        
        if qty <= 0:
            item.delete()
        else:
            if request.tenant.track_inventory and qty > item.product_variant.stock_qty:
                messages.error(request, f'Cannot update to {qty}. Only {item.product_variant.stock_qty} items in stock.')
                
                if referer:
                    from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
                    url_parts = list(urlparse(referer))
                    query = dict(parse_qsl(url_parts[4]))
                    query['cart_open'] = '1'
                    url_parts[4] = urlencode(query)
                    return redirect(urlunparse(url_parts))
                return redirect('storefront:cart')
            
            item.quantity = qty
            item.save()

        if referer:
            from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
            url_parts = list(urlparse(referer))
            query = dict(parse_qsl(url_parts[4]))
            query['cart_open'] = '1'
            url_parts[4] = urlencode(query)
            return redirect(urlunparse(url_parts))
            
        return redirect('storefront:cart')


class CartNoteUpdateView(View):
    def post(self, request):
        note = request.POST.get('note', '').strip()
        cart = get_or_create_cart(request)
        cart.note = note
        cart.save()
        
        referer = request.META.get('HTTP_REFERER')
        if referer:
            from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
            url_parts = list(urlparse(referer))
            from django.urls import reverse
            if url_parts[2] != reverse('storefront:cart'):
                query = dict(parse_qsl(url_parts[4]))
                query['cart_open'] = '1'
                url_parts[4] = urlencode(query)
            return redirect(urlunparse(url_parts))
            
        return redirect('storefront:cart')


class CartRemoveView(View):
    def post(self, request):
        item_id = request.POST.get('item_id')
        cart = get_or_create_cart(request)
        item = get_object_or_404(CartItem, cart=cart, pk=item_id)
        item.delete()
        # messages.success(request, 'Item removed from cart.')
        
        referer = request.META.get('HTTP_REFERER')
        if referer:
            from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
            url_parts = list(urlparse(referer))
            query = dict(parse_qsl(url_parts[4]))
            query['cart_open'] = '1'
            url_parts[4] = urlencode(query)
            return redirect(urlunparse(url_parts))
            
        return redirect('storefront:cart')


# ─────────────────────────────────────────────────────────────
# CHECKOUT & ORDER PLACEMENT
# ─────────────────────────────────────────────────────────────

class CustomerRequiredMixin(LoginRequiredMixin):
    """
    Restrict storefront checkout and dashboards to logged-in customers only.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Redirect to storefront login
            return redirect(f"{reverse('storefront:login')}?next={request.path}")
        return super().dispatch(request, *args, **kwargs)


class CheckoutView(View):
    template_name = 'storefront/checkout.html'

    def get(self, request):
        cart = get_or_create_cart(request)
        if not cart or cart.items.count() == 0:
            messages.warning(request, 'Your cart is empty.')
            return redirect('storefront:cart')

        if request.user.is_authenticated:
            addresses = CustomerAddress.objects.filter(customer=request.user).order_by('-is_default', '-created_at')
        else:
            addresses = []
        
        # Calculate standard shipping flat rate (e.g. ₹50 if total < ₹1000, else free shipping)
        subtotal = cart.total_price
        delivery = Decimal('50.00') if subtotal < Decimal('1000.00') else Decimal('0.00')
        
        # Get loyalty points details
        from crm.models import LoyaltyLedger, LoyaltyProgram
        loyalty_program = getattr(request.tenant, 'loyalty_program', None)
        loyalty_points = 0
        loyalty_discount_value = Decimal('0.00')
        if loyalty_program and loyalty_program.is_enabled and request.user.is_authenticated:
            points_agg = LoyaltyLedger.objects.filter(
                vendor=request.tenant,
                customer=request.user
            ).aggregate(total=models.Sum('points'))
            loyalty_points = points_agg['total'] or 0
            loyalty_discount_value = Decimal(str(loyalty_points)) * loyalty_program.currency_per_point

        # Get wallet balance details
        wallet_balance = Decimal('0.00')
        if request.user.is_authenticated:
            from crm.models import Wallet
            wallet, _ = Wallet.objects.get_or_create(vendor=request.tenant, customer=request.user)
            wallet_balance = wallet.balance

        # Applied coupon calculations
        from crm.utils import calculate_order_discounts
        discounts = calculate_order_discounts(request, subtotal, loyalty_redeemed=False)
        coupon = discounts['coupon']
        coupon_discount = discounts['coupon_discount']
        grand_total = discounts['grand_total'] + delivery

        context = {
            'cart': cart,
            'addresses': addresses,
            'subtotal': subtotal,
            'delivery_charge': delivery,
            'wallet_balance': wallet_balance,
            'loyalty_points': loyalty_points,
            'loyalty_program': loyalty_program,
            'loyalty_discount_value': loyalty_discount_value,
            'coupon': coupon,
            'coupon_discount': coupon_discount,
            'grand_total': grand_total,
            'page_title': 'Checkout Details',
        }
        return render(request, self.template_name, context)


class PlaceOrderView(View):
    def post(self, request):
        vendor = request.tenant
        cart = get_or_create_cart(request)
        if not cart or cart.items.count() == 0:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                return JsonResponse({'status': 'error', 'message': 'Your cart is empty.'})
            messages.warning(request, 'Your cart is empty.')
            return redirect('storefront:cart')

        # Double check stock before proceeding
        if vendor.track_inventory:
            for item in cart.items.all():
                if item.quantity > item.product_variant.stock_qty:
                    msg = f'Sorry, "{item.product_variant.product.name}" does not have enough stock ({item.product_variant.stock_qty} available).'
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                        return JsonResponse({'status': 'error', 'message': msg})
                    messages.error(request, msg)
                    return redirect('storefront:cart')

        address_id = request.POST.get('address_id')
        payment_method = request.POST.get('payment_method', 'cod')
        notes = request.POST.get('notes', '').strip()
        if not notes and cart.note:
            notes = cart.note

        # Handle address retrieval & user mapping
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        checkout_user = request.user if request.user.is_authenticated else None

        if address_id and request.user.is_authenticated:
            addr = get_object_or_404(CustomerAddress, customer=request.user, pk=address_id)
        else:
            # Inline address creation
            recipient_name = request.POST.get('recipient_name', '').strip()
            phone = request.POST.get('recipient_phone', '').strip()
            line1 = request.POST.get('address_line1', '').strip()
            line2 = request.POST.get('address_line2', '').strip()
            city = request.POST.get('city', '').strip()
            state = request.POST.get('state', '').strip()
            pincode = request.POST.get('pincode', '').strip()

            email = request.POST.get('email', '').strip()

            if not recipient_name or not phone or not line1 or not city or not state or not pincode or not email:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                    return JsonResponse({'status': 'error', 'message': 'Complete shipping address and email are required.'})
                messages.error(request, 'Complete shipping address and email are required.')
                return redirect('storefront:checkout')

            # Handle guest checkout auto-account linkage
            if not checkout_user:
                from django.db import models
                # Check if a user with this email or phone exists
                checkout_user = User.objects.filter(models.Q(email=email) | models.Q(phone=phone)).first()
                
                if not checkout_user:
                    import string, random
                    # Generate an 8-character random password
                    chars = string.ascii_letters + string.digits
                    random_password = ''.join(random.choice(chars) for _ in range(8))
                    
                    checkout_user = User.objects.create_user(
                        phone=phone, 
                        password=random_password, 
                        user_type='customer', 
                        first_name=recipient_name,
                        email=email,
                        vendor=vendor
                    )
                    
                    # Automatically log the NEW guest user in so they can view the success page
                    from django.contrib.auth import login
                    login(request, checkout_user, backend='accounts.backends.EmailPasswordBackend')

                    # Send welcome email with credentials
                    try:
                        from django.core.mail import EmailMessage
                        from django.core.mail.backends.smtp import EmailBackend
                        from django.template.loader import render_to_string
                        from tenants.models import VendorEmailSettings
                        
                        settings_obj = VendorEmailSettings.objects.filter(vendor=vendor).first()
                        if settings_obj and settings_obj.email_host_user:
                            backend = EmailBackend(
                                host=settings_obj.email_host,
                                port=settings_obj.email_port,
                                username=settings_obj.email_host_user,
                                password=settings_obj.email_host_password,
                                use_tls=settings_obj.use_tls,
                                fail_silently=False
                            )
                            context = {
                                'first_name': recipient_name,
                                'email': email,
                                'password': random_password,
                                'store_name': vendor.business_name
                            }
                            html_content = render_to_string('emails/welcome_with_credentials.html', context)
                            
                            email_msg = EmailMessage(
                                subject=f"Welcome to {vendor.business_name}! Your account details",
                                body=html_content,
                                from_email=settings_obj.default_from_email or settings_obj.email_host_user,
                                to=[email],
                                connection=backend
                            )
                            email_msg.content_subtype = "html"
                            email_msg.send()
                    except Exception as e:
                        print(f"Error sending credentials: {e}")
                else:
                    # Existing user found: do not log them in automatically.
                    # Just link the order and address to them.
                    pass

            addr = CustomerAddress.objects.create(
                customer=checkout_user,
                recipient_name=recipient_name,
                phone=phone,
                address_line1=line1,
                address_line2=line2,
                city=city,
                state=state,
                pincode=pincode,
                is_default=not CustomerAddress.objects.filter(customer=checkout_user).exists()
            )

        # Shipping address formatting snapshot
        address_str = f"{addr.recipient_name}\nPhone: {addr.phone}\n{addr.address_line1}\n"
        if addr.address_line2:
            address_str += f"{addr.address_line2}\n"
        address_str += f"{addr.city}, {addr.state} - {addr.pincode}\n{addr.country}"

        # Select branch for fulfillment (Main branch, or any active branch)
        branch = Branch.objects.filter(vendor=vendor, is_main_branch=True, is_active=True).first()
        if not branch:
            branch = Branch.objects.filter(vendor=vendor, is_active=True).first()
        if not branch:
            # Auto-create a default branch so checkout is not blocked for new/unconfigured vendors
            branch = Branch.objects.create(
                vendor=vendor,
                name="Main Branch",
                is_main_branch=True,
                is_active=True,
                email=vendor.email,
                phone=vendor.phone
            )

        subtotal = cart.total_price
        delivery = Decimal('50.00') if subtotal < Decimal('1000.00') else Decimal('0.00')

        # Get discounts from CRM module
        redeem_loyalty = (request.POST.get('redeem_loyalty') == '1')
        from crm.utils import calculate_order_discounts
        discounts = calculate_order_discounts(request, subtotal, loyalty_redeemed=redeem_loyalty)
        coupon = discounts['coupon']
        coupon_discount = discounts['coupon_discount']
        points_redeemed = discounts['points_redeemed']
        loyalty_discount = discounts['loyalty_discount']
        grand_total = discounts['grand_total'] + delivery

        # Wallet payment validation
        if payment_method == 'wallet':
            from crm.models import Wallet
            if not checkout_user:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                    return JsonResponse({'status': 'error', 'message': 'You must be logged in to use wallet.'})
                messages.error(request, 'You must be logged in to use wallet.')
                return redirect('storefront:checkout')
                
            wallet, _ = Wallet.objects.get_or_create(vendor=vendor, customer=checkout_user)
            if wallet.balance < grand_total:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                    return JsonResponse({'status': 'error', 'message': 'Insufficient wallet balance.'})
                messages.error(request, 'Insufficient wallet balance.')
                return redirect('storefront:checkout')

        # Dynamic workflow handling
        workflow = vendor.checkout_workflow
        is_online_payment = (workflow == 'online_payment' and payment_method == 'online')
        is_stripe_payment = (workflow == 'online_payment_stripe' and payment_method == 'online')

        try:
            with transaction.atomic():
                order_status = 'pending'
                payment_status = 'pending'
                if workflow == 'approval_payment':
                    order_status = 'awaiting_approval'
                elif payment_method == 'wallet' or is_online_payment:
                    order_status = 'processing'
                    payment_status = 'paid'
                elif is_stripe_payment:
                    order_status = 'pending'
                    payment_status = 'pending'

                order = Order.objects.create(
                    vendor=vendor,
                    customer=checkout_user,
                    branch=branch,
                    order_number=generate_order_number(vendor),
                    subtotal_amount=subtotal,
                    delivery_charge=delivery,
                    tax_amount=Decimal('0.00'),
                    total_amount=grand_total,
                    shipping_name=addr.recipient_name,
                    shipping_phone=addr.phone,
                    shipping_address=address_str,
                    payment_method=payment_method,
                    payment_status=payment_status,
                    notes=notes,
                    status=order_status
                )

                # Process line items
                for item in cart.items.all():
                    OrderItem.objects.create(
                        order=order,
                        product_variant=item.product_variant,
                        quantity=item.quantity,
                        price=item.product_variant.price,
                        customization_data=item.customization_data
                    )

                # If paying via wallet, process debit transaction
                if payment_method == 'wallet':
                    from crm.models import Wallet
                    wallet = Wallet.objects.get(vendor=vendor, customer=checkout_user)
                    wallet.debit(grand_total, f"Order Purchase: {order.order_number}", order=order)
                    # Credit loyalty points immediately for paid wallet order
                    from crm.utils import credit_loyalty_points
                    credit_loyalty_points(order)

                # If loyalty points redeemed, record ledger deduction
                if points_redeemed > 0:
                    from crm.models import LoyaltyLedger
                    LoyaltyLedger.objects.create(
                        vendor=vendor,
                        customer=checkout_user,
                        points=-points_redeemed,
                        transaction_type='redeem',
                        reference_order=order
                    )

                # If coupon code applied, increment usage limit
                if coupon:
                    coupon.used_count += 1
                    coupon.save()

                # Complete fulfillment steps immediately (Simulating successful online payment synchronously)
                if order_status != 'awaiting_approval' and not is_stripe_payment:
                    for item in cart.items.all():
                        bi, _ = BranchInventory.objects.get_or_create(
                            branch=branch,
                            product_variant=item.product_variant,
                            defaults={'stock_qty': Decimal('0.00')}
                        )
                        bi.stock_qty = Decimal(str(bi.stock_qty)) - Decimal(str(item.quantity))
                        bi.save()

                        # Audit trail log
                        StockAdjustmentLog.objects.create(
                            vendor=vendor,
                            branch=branch,
                            product_variant=item.product_variant,
                            user=checkout_user,
                            quantity_changed=-item.quantity,
                            reason='other',
                            notes=f'Sold via Storefront Order: {order.order_number}'
                        )

                # Clear shopping cart for non-stripe payments
                if not is_stripe_payment:
                    cart.items.all().delete()
                    if 'applied_coupon_id' in request.session:
                        del request.session['applied_coupon_id']

            # Process payment details outside database transaction
            if is_stripe_payment:
                import stripe
                stripe.api_key = vendor.stripe_secret_key
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=['card'],
                        line_items=[{
                            'price_data': {
                                'currency': vendor.currency.lower() if vendor.currency else 'inr',
                                'product_data': {
                                    'name': f'Order #{order.order_number}',
                                },
                                'unit_amount': int(order.total_amount * 100),
                            },
                            'quantity': 1,
                        }],
                        mode='payment',
                        success_url=request.build_absolute_uri(reverse('storefront:order_success', kwargs={'token': order.token})),
                        cancel_url=request.build_absolute_uri(reverse('storefront:checkout')),
                        metadata={'order_id': order.pk}
                    )
                    return redirect(session.url)
                except Exception as e:
                    messages.error(request, f'Stripe payment initiation failed: {str(e)}')
                    return redirect('storefront:checkout')

            elif is_online_payment:
                messages.success(request, 'Thank you! Your payment was successful and the order has been placed.')
                return redirect('storefront:order_success', token=order.token)

            elif workflow == 'whatsapp_enquiry':
                whatsapp_number = vendor.whatsapp_number or vendor.phone
                phone = ''.join(c for c in whatsapp_number if c.isdigit())

                msg_template = vendor.whatsapp_order_format
                if not msg_template:
                    msg_template = (
                        "Hello {store_name}! I would like to place an order:\n"
                        "Order Number: {order_number}\n"
                        "Customer Name: {customer_name}\n"
                        "Shipping Address:\n{shipping_address}\n\n"
                        "Items Ordered:\n{items}\n"
                        "Total Amount: {total_amount}"
                    )

                items_list = []
                for o_item in order.items.all():
                    items_list.append(f"- {o_item.product_variant.product.name} ({o_item.product_variant.name or 'Default'}) x {o_item.quantity}: {vendor.currency_symbol}{o_item.total_cost}")
                items_str = "\n".join(items_list)

                placeholders = {
                    '{order_number}': order.order_number,
                    '{customer_name}': order.shipping_name,
                    '{shipping_address}': order.shipping_address,
                    '{items}': items_str,
                    '{total_amount}': f"{vendor.currency_symbol}{order.total_amount}",
                    '{store_name}': vendor.business_name
                }

                msg = msg_template
                for k, v in placeholders.items():
                    msg = msg.replace(k, str(v))

                import urllib.parse
                encoded_msg = urllib.parse.quote(msg)
                whatsapp_url = f"https://wa.me/{phone}?text={encoded_msg}"
                return redirect(whatsapp_url)

            elif workflow == 'approval_payment':
                messages.success(request, 'Your order has been submitted for approval. Once approved, you will receive a payment link.')
                return redirect('storefront:order_success', token=order.token)

            else:
                messages.success(request, 'Thank you! Your order has been placed successfully.')
                return redirect('storefront:order_success', token=order.token)

        except Exception as e:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.POST.get('is_ajax'):
                return JsonResponse({'status': 'error', 'message': f'Fulfillment error: {str(e)}'})
            messages.error(request, f'Fulfillment error. Could not place order: {str(e)}')
            return redirect('storefront:checkout')


class PaymentVerifyView(CustomerRequiredMixin, View):
    def post(self, request):
        import json
        import razorpay

        try:
            data = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON request data.'}, status=400)

        order_id = data.get('order_id')
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_signature = data.get('razorpay_signature')

        if not all([order_id, razorpay_payment_id, razorpay_order_id, razorpay_signature]):
            return JsonResponse({'status': 'error', 'message': 'Missing verification signatures.'}, status=400)

        order = get_object_or_404(Order, customer=request.user, pk=order_id)
        vendor = order.vendor

        client = razorpay.Client(auth=(vendor.razorpay_key_id, vendor.razorpay_key_secret))

        params_dict = {
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        }

        try:
            client.utility.verify_payment_signature(params_dict)
        except razorpay.errors.SignatureVerificationError as verify_err:
            order.payment_status = 'failed'
            order.save(update_fields=['payment_status'])
            return JsonResponse({'status': 'error', 'message': f'Signature verification failed: {str(verify_err)}'}, status=400)

        with transaction.atomic():
            order.payment_status = 'paid'
            order.gateway_payment_id = razorpay_payment_id
            order.gateway_signature = razorpay_signature
            order.status = 'processing'
            order.save()

            # Credit loyalty points for the online payment
            from crm.utils import credit_loyalty_points
            credit_loyalty_points(order)

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
                    vendor=vendor,
                    branch=branch,
                    product_variant=o_item.product_variant,
                    user=request.user,
                    quantity_changed=-o_item.quantity,
                    reason='other',
                    notes=f'Sold via Storefront Order: {order.order_number} (Paid Online)'
                )

            cart = get_or_create_cart(request)
            if cart:
                cart.items.all().delete()

        messages.success(request, 'Payment completed successfully!')
        return JsonResponse({
            'status': 'success',
            'redirect_url': reverse('storefront:order_success', kwargs={'token': order.token})
        })


from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@method_decorator(csrf_exempt, name='dispatch')
class StripeWebhookView(View):
    def post(self, request):
        import stripe
        import json
        payload = request.body
        sig_header = request.headers.get('STRIPE_SIGNATURE', '')

        # We need the vendor to verify the signature. 
        # But we don't know the vendor until we parse the payload.
        # Stripe webhooks allow parsing without verification first.
        try:
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
        except ValueError as e:
            return HttpResponse(status=400)
            
        if event.type == 'checkout.session.completed':
            session = event.data.object
            order_id = getattr(session.metadata, 'order_id', None)
            
            if order_id:
                try:
                    order = Order.objects.get(pk=order_id)
                    vendor = order.vendor
                    
                    # Now verify signature properly using vendor's webhook secret
                    if vendor.stripe_webhook_secret:
                        try:
                            event = stripe.Webhook.construct_event(
                                payload, sig_header, vendor.stripe_webhook_secret
                            )
                        except stripe.error.SignatureVerificationError as e:
                            return HttpResponse(status=400)
                    
                    if session.payment_status == 'paid' and order.payment_status != 'paid':
                        with transaction.atomic():
                            order.payment_status = 'paid'
                            order.gateway_payment_id = session.payment_intent or session.id
                            order.status = 'processing'
                            order.save()

                            # Credit loyalty points
                            from crm.utils import credit_loyalty_points
                            credit_loyalty_points(order)

                            # Deduct inventory
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
                                    vendor=vendor,
                                    branch=branch,
                                    product_variant=o_item.product_variant,
                                    user=order.customer,
                                    quantity_changed=-o_item.quantity,
                                    reason='other',
                                    notes=f'Sold via Storefront Order: {order.order_number} (Stripe)'
                                )

                except Order.DoesNotExist:
                    pass

        return HttpResponse(status=200)

class OrderSuccessView(View):
    template_name = 'storefront/success.html'

    def get(self, request, token):
        order = get_object_or_404(Order, token=token)
        
        cart = get_or_create_cart(request)
        if cart and order.payment_status in ('paid', 'processing', 'pending'):
            # Clear cart if order is placed (or pending/paid via stripe success_url)
            cart.items.all().delete()
            if 'applied_coupon_id' in request.session:
                del request.session['applied_coupon_id']
                
        return render(request, self.template_name, {
            'order': order, 
            'page_title': 'Order Success',
            'cart': cart
        })


# ─────────────────────────────────────────────────────────────
# CUSTOMER DASHBOARD
# ─────────────────────────────────────────────────────────────

class CustomerProfileView(CustomerRequiredMixin, View):
    template_name = 'storefront/profile.html'

    def get(self, request):
        orders = Order.objects.filter(customer=request.user).order_by('-created_at')
        addresses = CustomerAddress.objects.filter(customer=request.user).order_by('-is_default', '-created_at')
        context = {
            'orders': orders,
            'addresses': addresses,
            'page_title': 'My Account',
            'cart': get_or_create_cart(request),
        }
        return render(request, self.template_name, context)

class CustomerPasswordResetView(CustomerRequiredMixin, View):
    def post(self, request):
        new_password = request.POST.get('new_password', '').strip()
        if new_password:
            request.user.set_password(new_password)
            request.user.save()
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Your password has been reset successfully.')
        else:
            messages.error(request, 'Please provide a valid new password.')
        return redirect('storefront:profile')


class SetCurrencyView(View):
    """
    Handles setting the user's preferred currency in the session.
    Expects a POST request with 'currency_code' or a GET request.
    """
    def post(self, request, *args, **kwargs):
        currency_code = request.POST.get('currency_code', '').strip().upper()
        if currency_code:
            request.session['currency_code'] = currency_code
        return redirect(request.META.get('HTTP_REFERER', 'storefront:home'))
        
    def get(self, request, *args, **kwargs):
        currency_code = request.GET.get('currency_code', '').strip().upper()
        if currency_code:
            request.session['currency_code'] = currency_code
        return redirect(request.META.get('HTTP_REFERER', 'storefront:home'))
class CustomerAddressCreateView(CustomerRequiredMixin, View):
    def post(self, request):
        recipient_name = request.POST.get('recipient_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        line1 = request.POST.get('address_line1', '').strip()
        line2 = request.POST.get('address_line2', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        pincode = request.POST.get('pincode', '').strip()

        if recipient_name and phone and line1 and city and state and pincode:
            CustomerAddress.objects.create(
                customer=request.user,
                recipient_name=recipient_name,
                phone=phone,
                address_line1=line1,
                address_line2=line2,
                city=city,
                state=state,
                pincode=pincode,
                is_default=not CustomerAddress.objects.filter(customer=request.user).exists()
            )
            messages.success(request, 'Address added successfully.')
        else:
            messages.error(request, 'Failed to add address. Missing fields.')

        return redirect('storefront:profile')

class CustomerAddressUpdateView(CustomerRequiredMixin, View):
    def post(self, request, pk):
        try:
            addr = CustomerAddress.objects.get(pk=pk, customer=request.user)
            addr.recipient_name = request.POST.get('recipient_name', '').strip()
            addr.phone = request.POST.get('phone', '').strip()
            addr.address_line1 = request.POST.get('address_line1', '').strip()
            addr.address_line2 = request.POST.get('address_line2', '').strip()
            addr.city = request.POST.get('city', '').strip()
            addr.state = request.POST.get('state', '').strip()
            addr.pincode = request.POST.get('pincode', '').strip()
            
            if request.POST.get('is_default') == 'on':
                CustomerAddress.objects.filter(customer=request.user).update(is_default=False)
                addr.is_default = True
            
            addr.save()
            messages.success(request, 'Address updated successfully.')
        except CustomerAddress.DoesNotExist:
            messages.error(request, 'Address not found.')
            
        return redirect('storefront:profile')

class CustomerAddressDeleteView(CustomerRequiredMixin, View):
    def post(self, request, pk):
        try:
            addr = CustomerAddress.objects.get(pk=pk, customer=request.user)
            addr.delete()
            messages.success(request, 'Address deleted successfully.')
        except CustomerAddress.DoesNotExist:
            messages.error(request, 'Address not found.')
        return redirect('storefront:profile')


# ─────────────────────────────────────────────────────────────
# NEWSLETTER SUBSCRIPTION
# ─────────────────────────────────────────────────────────────

from django.http import JsonResponse
import random
import string
from django.core.mail.backends.smtp import EmailBackend
from django.core.mail import EmailMessage

class NewsletterSubscriptionView(View):
    def post(self, request):
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        vendor = getattr(request, 'tenant', None)
        
        if not email or not vendor:
            return JsonResponse({'status': 'error', 'message': 'Email is required.'}, status=400)
            
        from crm.models import NewsletterSubscriber, Coupon
        from tenants.models import VendorEmailSettings
        
        # Check if already subscribed
        if NewsletterSubscriber.objects.filter(vendor=vendor, email=email).exists():
            return JsonResponse({'status': 'error', 'message': 'You are already subscribed!'})
            
        from accounts.models import User
        import string, random
        
        # Auto-create account if not exists
        checkout_user = User.objects.filter(email=email).first()
        random_password = None
        if not checkout_user:
            chars = string.ascii_letters + string.digits
            random_password = ''.join(random.choice(chars) for _ in range(8))
            dummy_phone = f"NL-{''.join(random.choices(string.digits, k=10))}"
            
            # Ensure dummy phone is unique
            while User.objects.filter(phone=dummy_phone).exists():
                dummy_phone = f"NL-{''.join(random.choices(string.digits, k=10))}"
                
            checkout_user = User.objects.create_user(
                phone=dummy_phone, 
                password=random_password, 
                user_type='customer', 
                first_name=first_name,
                email=email
            )
            
        # Get Email Settings
        settings_obj = VendorEmailSettings.objects.filter(vendor=vendor).first()
        if not settings_obj or not settings_obj.email_host_user or not settings_obj.email_host_password:
            # If settings are missing, we just record the subscriber but cannot send the coupon via email easily
            # But let's create it anyway so they are on the list
            sub = NewsletterSubscriber.objects.create(
                vendor=vendor,
                email=email,
                first_name=first_name
            )
            return JsonResponse({'status': 'success', 'message': 'Subscribed successfully (no welcome email configured).'})

        # Generate a unique coupon code
        code_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        coupon_code = f"WELCOME-{code_suffix}"
        
        # Create the coupon
        start_date = timezone.now().date()
        end_date = start_date + datetime.timedelta(days=30)
        
        coupon = Coupon.objects.create(
            vendor=vendor,
            code=coupon_code,
            discount_type=settings_obj.welcome_discount_type,
            discount_value=settings_obj.welcome_discount_value,
            usage_limit=1,
            start_date=start_date,
            end_date=end_date,
            is_active=True
        )
        
        # Create subscriber
        sub = NewsletterSubscriber.objects.create(
            vendor=vendor,
            email=email,
            first_name=first_name,
            coupon=coupon
        )
        
        # Send email
        try:
            from django.core.mail import EmailMessage
            from django.core.mail.backends.smtp import EmailBackend
            
            backend = EmailBackend(
                host=settings_obj.email_host,
                port=settings_obj.email_port,
                username=settings_obj.email_host_user,
                password=settings_obj.email_host_password,
                use_tls=settings_obj.use_tls,
                fail_silently=False
            )
            
            discount_text = f"{int(settings_obj.welcome_discount_value)}%" if settings_obj.welcome_discount_type == 'percentage' else f"{vendor.currency_symbol}{settings_obj.welcome_discount_value}"
            
            subject = f"Welcome to {vendor.business_name}! Here is your {discount_text} discount."
            body = f"Hi {first_name or 'there'},\n\nThank you for subscribing to our newsletter! As promised, here is your welcome discount code.\n\nCode: {coupon_code}\nDiscount: {discount_text} off your first order.\n\n"
            
            if random_password:
                body += f"We have also created an account for you to checkout faster!\nLogin ID (Email): {email}\nPassword: {random_password}\n\n"
                
            from django.core.signing import Signer
            signer = Signer()
            token = signer.sign(str(sub.id))
            unsubscribe_url = f"{request.build_absolute_uri('/unsubscribe/')}{token}/"
                
            body += f"Shop now: {request.build_absolute_uri('/')}\n\nCheers,\n{vendor.business_name}\n\nUnsubscribe from these emails: {unsubscribe_url}"
            from_email = settings_obj.default_from_email or settings_obj.email_host_user
            
            email_msg = EmailMessage(
                subject=subject,
                body=body,
                from_email=from_email,
                to=[email],
                connection=backend
            )
            email_msg.send()
        except Exception as e:
            # We don't want to fail the subscription if email fails, but we can log it
            print(f"Error sending welcome email: {e}")
            return JsonResponse({'status': 'success', 'message': 'Subscribed successfully, but failed to send welcome email.'})
            
        return JsonResponse({'status': 'success', 'message': 'Subscribed! Check your email for your discount code.'})

class NewsletterUnsubscribeView(View):
    def get(self, request, token):
        from django.core.signing import Signer, BadSignature
        from crm.models import NewsletterSubscriber
        
        signer = Signer()
        try:
            sub_id = signer.unsign(token)
            subscriber = NewsletterSubscriber.objects.get(id=sub_id)
            subscriber.delete()
            success = True
        except (BadSignature, NewsletterSubscriber.DoesNotExist):
            success = False
            
        context = {
            'success': success,
            'page_title': 'Unsubscribe from Newsletter'
        }
        return render(request, 'storefront/newsletter_unsubscribe.html', context)
