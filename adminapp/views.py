"""
Admin App Views — CommerceHub Super Admin Dashboard

Provides the fully custom Super Admin panel:
  - Dashboard with platform analytics
  - Vendor management (list, detail, create, approve, suspend)
  - Subscription plan management
  - Platform statistics
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views import View
from django.db.models import Count, Q
from django.utils import timezone
import datetime

from core.mixins import SuperAdminRequiredMixin
from tenants.models import Vendor, SubscriptionPlan, VendorSubscription, SupportedCurrency
from accounts.models import User, LoginHistory
from core.utils import generate_unique_slug
from core.middleware import COUNTRY_CURRENCY_MAP


# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────

class DashboardView(SuperAdminRequiredMixin, View):
    template_name = 'admin/dashboard.html'

    def get(self, request):
        today = timezone.now().date()
        thirty_days_ago = today - datetime.timedelta(days=30)

        stats = {
            'total_vendors': Vendor.objects.count(),
            'active_vendors': Vendor.objects.filter(status='approved', is_active=True).count(),
            'pending_vendors': Vendor.objects.filter(status='pending').count(),
            'suspended_vendors': Vendor.objects.filter(status='suspended').count(),
            'new_vendors_this_month': Vendor.objects.filter(
                created_at__date__gte=thirty_days_ago
            ).count(),
            'total_users': User.objects.filter(user_type='vendor_staff').count(),
            'total_plans': SubscriptionPlan.objects.filter(is_active=True).count(),
            'active_subscriptions': VendorSubscription.objects.filter(
                is_active=True, end_date__gte=today
            ).count(),
        }

        recent_vendors = Vendor.objects.order_by('-created_at')[:10]
        pending_vendors = Vendor.objects.filter(status='pending').order_by('-created_at')[:5]
        recent_logins = LoginHistory.objects.filter(
            status='success'
        ).select_related('user').order_by('-created_at')[:10]

        context = {
            'stats': stats,
            'recent_vendors': recent_vendors,
            'pending_vendors': pending_vendors,
            'recent_logins': recent_logins,
            'page_title': 'Super Admin Dashboard',
        }
        return render(request, self.template_name, context)


# ─────────────────────────────────────────────────────────────
# VENDOR LIST
# ─────────────────────────────────────────────────────────────

class VendorListView(SuperAdminRequiredMixin, View):
    template_name = 'admin/vendors/list.html'

    def get(self, request):
        status_filter = request.GET.get('status', '')
        search = request.GET.get('q', '')

        vendors = Vendor.objects.all().order_by('-created_at')

        if status_filter:
            vendors = vendors.filter(status=status_filter)
        if search:
            vendors = vendors.filter(
                Q(business_name__icontains=search) |
                Q(phone__icontains=search) |
                Q(email__icontains=search) |
                Q(slug__icontains=search)
            )

        context = {
            'vendors': vendors,
            'status_filter': status_filter,
            'search': search,
            'total_count': vendors.count(),
            'page_title': 'Vendor Management',
        }
        return render(request, self.template_name, context)


# ─────────────────────────────────────────────────────────────
# VENDOR DETAIL
# ─────────────────────────────────────────────────────────────

class VendorDetailView(SuperAdminRequiredMixin, View):
    template_name = 'admin/vendors/detail.html'

    def get(self, request, vendor_id):
        vendor = get_object_or_404(Vendor, pk=vendor_id)
        subscriptions = vendor.subscriptions.select_related('plan').order_by('-start_date')
        staff_count = User.objects.filter(vendor=vendor).count()

        context = {
            'vendor': vendor,
            'subscriptions': subscriptions,
            'staff_count': staff_count,
            'plans': SubscriptionPlan.objects.filter(is_active=True),
            'page_title': f'{vendor.business_name} — Vendor Detail',
        }
        return render(request, self.template_name, context)


# ─────────────────────────────────────────────────────────────
# VENDOR CREATE
# ─────────────────────────────────────────────────────────────

class VendorCreateView(SuperAdminRequiredMixin, View):
    template_name = 'admin/vendors/create.html'

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True)
        
        meta = {
          'USD': {'symbol': '$', 'tz': 'America/New_York'},
          'EUR': {'symbol': '€', 'tz': 'Europe/Paris'},
          'GBP': {'symbol': '£', 'tz': 'Europe/London'},
          'INR': {'symbol': '₹', 'tz': 'Asia/Kolkata'},
          'AED': {'symbol': 'AED', 'tz': 'Asia/Dubai'},
          'SAR': {'symbol': 'SAR', 'tz': 'Asia/Riyadh'},
          'QAR': {'symbol': 'QAR', 'tz': 'Asia/Qatar'},
          'BHD': {'symbol': 'BHD', 'tz': 'Asia/Bahrain'},
          'KWD': {'symbol': 'KWD', 'tz': 'Asia/Kuwait'},
          'OMR': {'symbol': 'OMR', 'tz': 'Asia/Muscat'},
          'AUD': {'symbol': 'A$', 'tz': 'Australia/Sydney'},
          'CAD': {'symbol': 'C$', 'tz': 'America/Toronto'},
          'SGD': {'symbol': 'S$', 'tz': 'Asia/Singapore'},
        }
        all_global_currencies = sorted(list(set(COUNTRY_CURRENCY_MAP.values())))
        for c in all_global_currencies:
            if c not in meta:
                meta[c] = {'symbol': c, 'tz': 'UTC'}
        import json
        import zoneinfo
        
        context = {
            'plans': plans,
            'page_title': 'Add New Vendor',
            'all_global_currencies': all_global_currencies,
            'currency_metadata_json': json.dumps(meta),
            'all_timezones': sorted(zoneinfo.available_timezones()),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        # ── Required fields ──
        business_name = request.POST.get('business_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()

        if not business_name or not phone or not password:
            messages.error(request, 'Business name, phone number, and password are required.')
            return redirect('adminapp:vendor_create')

        if Vendor.objects.filter(phone=phone).exists():
            messages.error(request, f'A vendor with phone {phone} already exists.')
            return redirect('adminapp:vendor_create')

        if User.objects.filter(phone=phone).exists():
            messages.error(request, f'A user account with phone {phone} already exists.')
            return redirect('adminapp:vendor_create')

        # ── Build vendor ──
        slug = generate_unique_slug(Vendor, business_name)
        initial_status = request.POST.get('initial_status', 'pending')

        vendor = Vendor(
            # Identity
            business_name=business_name,
            slug=slug,
            business_type=request.POST.get('business_type', 'single_store'),
            gst_number=request.POST.get('gst_number', '').strip(),
            pan_number=request.POST.get('pan_number', '').strip(),
            # Contact
            phone=phone,
            whatsapp_number=request.POST.get('whatsapp_number', '').strip(),
            email=request.POST.get('email', '').strip(),
            website=request.POST.get('website', '').strip(),
            # Address
            address_line1=request.POST.get('address_line1', '').strip(),
            address_line2=request.POST.get('address_line2', '').strip(),
            city=request.POST.get('city', '').strip(),
            state=request.POST.get('state', '').strip(),
            pincode=request.POST.get('pincode', '').strip(),
            country=request.POST.get('country', 'India').strip(),
            # Store Settings
            currency=request.POST.get('currency', 'INR'),
            currency_symbol=request.POST.get('currency_symbol', '₹').strip(),
            timezone=request.POST.get('timezone', 'Asia/Kolkata'),
            checkout_workflow=request.POST.get('checkout_workflow', 'online_payment'),
            track_inventory=(request.POST.get('track_inventory') == '1'),
            # Branding Colors
            primary_color=request.POST.get('primary_color', '#6366f1').strip(),
            secondary_color=request.POST.get('secondary_color', '#8b5cf6').strip(),
            # Social Media
            facebook_url=request.POST.get('facebook_url', '').strip(),
            instagram_url=request.POST.get('instagram_url', '').strip(),
            twitter_url=request.POST.get('twitter_url', '').strip(),
            youtube_url=request.POST.get('youtube_url', '').strip(),
            # SEO
            meta_title=request.POST.get('meta_title', '').strip(),
            meta_description=request.POST.get('meta_description', '').strip(),
            # Status
            status=initial_status if initial_status in ('pending', 'approved') else 'pending',
            is_active=(initial_status == 'approved'),
        )



        # ── File uploads ──
        if request.FILES.get('logo'):
            vendor.logo = request.FILES['logo']
        if request.FILES.get('banner'):
            vendor.banner = request.FILES['banner']
        if request.FILES.get('favicon'):
            vendor.favicon = request.FILES['favicon']

        # ── Set approved_by if auto-approved ──
        if initial_status == 'approved':
            vendor.approved_at = timezone.now()
            vendor.approved_by = request.user

        vendor.save()

        # ── Create user account ──
        User.objects.create_user(
            phone=phone,
            password=password,
            email=vendor.email,
            user_type='vendor_staff',
            vendor=vendor,
            is_active=(initial_status == 'approved'),
        )

        # ── Assign subscription plan ──
        plan_id = request.POST.get('plan_id')
        if plan_id:
            try:
                plan = SubscriptionPlan.objects.get(pk=plan_id)
                today = timezone.now().date()
                trial_days = plan.trial_days if plan.trial_days else 14
                is_trial = (plan.price == 0)
                VendorSubscription.objects.create(
                    vendor=vendor,
                    plan=plan,
                    start_date=today,
                    end_date=today + datetime.timedelta(days=trial_days if is_trial else 30),
                    is_trial=is_trial,
                    is_active=True,
                    amount_paid=0 if is_trial else plan.price,
                )
            except SubscriptionPlan.DoesNotExist:
                messages.warning(request, 'Selected plan not found. Vendor created without a subscription.')

        # ── Automatically setup all global currencies ──
        unique_currencies = set(COUNTRY_CURRENCY_MAP.values())
        for code in unique_currencies:
            SupportedCurrency.objects.create(
                vendor=vendor,
                code=code,
                symbol=code,
                is_active=True
            )

        messages.success(request, f'Vendor "{business_name}" created successfully!')
        return redirect('adminapp:vendor_detail', vendor_id=vendor.pk)


# ─────────────────────────────────────────────────────────────
# VENDOR EDIT
# ─────────────────────────────────────────────────────────────

class VendorEditView(SuperAdminRequiredMixin, View):
    template_name = 'admin/vendors/edit.html'

    def get(self, request, vendor_id):
        vendor = get_object_or_404(Vendor, pk=vendor_id)
        plans = SubscriptionPlan.objects.filter(is_active=True)
        active_sub = vendor.active_subscription
        active_plan_id = active_sub.plan.pk if active_sub else None

        active_currencies = list(vendor.supported_currencies.filter(is_active=True).values_list('code', flat=True))

        meta = {
          'USD': {'symbol': '$', 'tz': 'America/New_York'},
          'EUR': {'symbol': '€', 'tz': 'Europe/Paris'},
          'GBP': {'symbol': '£', 'tz': 'Europe/London'},
          'INR': {'symbol': '₹', 'tz': 'Asia/Kolkata'},
          'AED': {'symbol': 'AED', 'tz': 'Asia/Dubai'},
          'SAR': {'symbol': 'SAR', 'tz': 'Asia/Riyadh'},
          'QAR': {'symbol': 'QAR', 'tz': 'Asia/Qatar'},
          'BHD': {'symbol': 'BHD', 'tz': 'Asia/Bahrain'},
          'KWD': {'symbol': 'KWD', 'tz': 'Asia/Kuwait'},
          'OMR': {'symbol': 'OMR', 'tz': 'Asia/Muscat'},
          'AUD': {'symbol': 'A$', 'tz': 'Australia/Sydney'},
          'CAD': {'symbol': 'C$', 'tz': 'America/Toronto'},
          'SGD': {'symbol': 'S$', 'tz': 'Asia/Singapore'},
        }
        all_global_currencies = sorted(list(set(COUNTRY_CURRENCY_MAP.values())))
        for c in all_global_currencies:
            if c not in meta:
                meta[c] = {'symbol': c, 'tz': 'UTC'}
        import json
        import zoneinfo

        context = {
            'vendor': vendor,
            'plans': plans,
            'active_plan_id': active_plan_id,
            'active_currencies': active_currencies,
            'all_global_currencies': all_global_currencies,
            'currency_metadata_json': json.dumps(meta),
            'all_timezones': sorted(zoneinfo.available_timezones()),
            'page_title': f'Edit Vendor — {vendor.business_name}',
        }
        return render(request, self.template_name, context)

    def post(self, request, vendor_id):
        vendor = get_object_or_404(Vendor, pk=vendor_id)

        business_name = request.POST.get('business_name', '').strip()
        phone = request.POST.get('phone', '').strip()

        if not business_name or not phone:
            messages.error(request, 'Business name and phone number are required.')
            return redirect('adminapp:vendor_edit', vendor_id=vendor.pk)

        # Check phone uniqueness excluding current vendor
        if Vendor.objects.filter(phone=phone).exclude(pk=vendor.pk).exists():
            messages.error(request, f'A vendor with phone {phone} already exists.')
            return redirect('adminapp:vendor_edit', vendor_id=vendor.pk)

        # Check user uniqueness excluding the current vendor's user account
        if User.objects.filter(phone=phone).exclude(vendor=vendor).exists():
            messages.error(request, f'A user account with phone {phone} already exists.')
            return redirect('adminapp:vendor_edit', vendor_id=vendor.pk)

        # Slug validation
        slug = request.POST.get('slug', '').strip()
        if not slug:
            slug = generate_unique_slug(Vendor, business_name)
        else:
            from django.utils.text import slugify
            slug = slugify(slug)
            if Vendor.objects.filter(slug=slug).exclude(pk=vendor.pk).exists():
                slug = generate_unique_slug(Vendor, slug)

        # Update fields
        vendor.business_name = business_name
        vendor.slug = slug
        vendor.business_type = request.POST.get('business_type', 'single_store')
        vendor.gst_number = request.POST.get('gst_number', '').strip()
        vendor.pan_number = request.POST.get('pan_number', '').strip()
        
        vendor.phone = phone
        vendor.whatsapp_number = request.POST.get('whatsapp_number', '').strip()
        vendor.email = request.POST.get('email', '').strip()
        vendor.website = request.POST.get('website', '').strip()
        
        vendor.address_line1 = request.POST.get('address_line1', '').strip()
        vendor.address_line2 = request.POST.get('address_line2', '').strip()
        vendor.city = request.POST.get('city', '').strip()
        vendor.state = request.POST.get('state', '').strip()
        vendor.pincode = request.POST.get('pincode', '').strip()
        vendor.country = request.POST.get('country', 'India').strip()

        vendor.currency = request.POST.get('currency', 'INR')
        vendor.currency_symbol = request.POST.get('currency_symbol', '₹').strip()
        vendor.timezone = request.POST.get('timezone', 'Asia/Kolkata')
        vendor.checkout_workflow = request.POST.get('checkout_workflow', 'online_payment')
        vendor.track_inventory = (request.POST.get('track_inventory') == '1')

        vendor.primary_color = request.POST.get('primary_color', '#6366f1').strip()
        vendor.secondary_color = request.POST.get('secondary_color', '#8b5cf6').strip()

        vendor.facebook_url = request.POST.get('facebook_url', '').strip()
        vendor.instagram_url = request.POST.get('instagram_url', '').strip()
        vendor.twitter_url = request.POST.get('twitter_url', '').strip()
        vendor.youtube_url = request.POST.get('youtube_url', '').strip()

        vendor.meta_title = request.POST.get('meta_title', '').strip()
        vendor.meta_description = request.POST.get('meta_description', '').strip()



        # Handle files
        if request.FILES.get('logo'):
            vendor.logo = request.FILES['logo']
        if request.FILES.get('banner'):
            vendor.banner = request.FILES['banner']
        if request.FILES.get('favicon'):
            vendor.favicon = request.FILES['favicon']

        # Handle status
        status = request.POST.get('status', vendor.status)
        if status in ('pending', 'approved', 'suspended', 'cancelled'):
            if status == 'approved' and vendor.status != 'approved':
                vendor.approved_at = timezone.now()
                vendor.approved_by = request.user
            vendor.status = status
            vendor.is_active = (status == 'approved')

        vendor.save()

        # Update Supported Currencies
        supported_currencies_codes = request.POST.getlist('supported_currencies')
        # We need a predefined list of symbols, or default to the code if unknown
        symbols_map = {
            'USD': '$', 'EUR': '€', 'GBP': '£', 'INR': '₹', 'AED': 'AED',
            'SAR': 'SAR', 'QAR': 'QAR', 'BHD': 'BHD', 'KWD': 'KWD', 'OMR': 'OMR',
            'AUD': 'A$', 'CAD': 'C$', 'SGD': 'S$'
        }
        
        # Deactivate all first
        vendor.supported_currencies.all().update(is_active=False)
        
        for code in supported_currencies_codes:
            code = code.strip().upper()
            if code:
                # Add or update
                SupportedCurrency.objects.update_or_create(
                    vendor=vendor, code=code,
                    defaults={'symbol': symbols_map.get(code, code), 'is_active': True}
                )

        # Instantly update exchange rates for the new currencies
        from django.core.management import call_command
        try:
            call_command('update_exchange_rates')
        except Exception as e:
            print(f"Failed to update exchange rates: {e}")
        
        # Ensure all associated staff users match the vendor's active state
        User.objects.filter(vendor=vendor).update(is_active=vendor.is_active)

        # ── Update/create user account ──
        user = User.objects.filter(vendor=vendor).first()
        if not user:
            user = User.objects.filter(phone=phone).first()

        password = request.POST.get('password', '').strip()

        if user:
            user.phone = phone
            user.email = vendor.email
            user.vendor = vendor
            user.user_type = 'vendor_staff'
            if password:
                user.set_password(password)
            user.save()
        else:
            user = User.objects.create_user(
                phone=phone,
                email=vendor.email,
                vendor=vendor,
                user_type='vendor_staff',
                is_active=(status == 'approved'),
            )
            if password:
                user.set_password(password)
                user.save()

        # Handle Subscription Plan
        plan_id = request.POST.get('plan_id')
        active_sub = vendor.active_subscription
        current_plan_id = active_sub.plan.pk if active_sub else None

        if plan_id and str(plan_id) != str(current_plan_id):
            try:
                plan = SubscriptionPlan.objects.get(pk=plan_id)
                if active_sub:
                    active_sub.is_active = False
                    active_sub.save(update_fields=['is_active'])

                today = timezone.now().date()
                trial_days = plan.trial_days if plan.trial_days else 14
                is_trial = (plan.price == 0)
                VendorSubscription.objects.create(
                    vendor=vendor,
                    plan=plan,
                    start_date=today,
                    end_date=today + datetime.timedelta(days=trial_days if is_trial else 30),
                    is_trial=is_trial,
                    is_active=True,
                    amount_paid=0 if is_trial else plan.price,
                )
            except SubscriptionPlan.DoesNotExist:
                messages.warning(request, 'Selected plan not found. Subscription was not updated.')

        messages.success(request, f'Vendor "{vendor.business_name}" updated successfully!')
        return redirect('adminapp:vendor_detail', vendor_id=vendor.pk)


# ─────────────────────────────────────────────────────────────
# VENDOR APPROVE
# ─────────────────────────────────────────────────────────────

class VendorApproveView(SuperAdminRequiredMixin, View):
    def post(self, request, vendor_id):
        vendor = get_object_or_404(Vendor, pk=vendor_id)
        vendor.approve(approved_by_user=request.user)
        messages.success(request, f'"{vendor.business_name}" has been approved.')
        return redirect('adminapp:vendor_detail', vendor_id=vendor.pk)


# ─────────────────────────────────────────────────────────────
# VENDOR SUSPEND
# ─────────────────────────────────────────────────────────────

class VendorSuspendView(SuperAdminRequiredMixin, View):
    def post(self, request, vendor_id):
        vendor = get_object_or_404(Vendor, pk=vendor_id)
        reason = request.POST.get('reason', '').strip()
        vendor.suspend(reason=reason)
        messages.warning(request, f'"{vendor.business_name}" has been suspended.')
        return redirect('adminapp:vendor_detail', vendor_id=vendor.pk)


# ─────────────────────────────────────────────────────────────
# SUBSCRIPTION PLAN LIST
# ─────────────────────────────────────────────────────────────

class PlanListView(SuperAdminRequiredMixin, View):
    template_name = 'admin/plans/list.html'

    def get(self, request):
        plans = SubscriptionPlan.objects.all().order_by('sort_order')
        context = {
            'plans': plans,
            'page_title': 'Subscription Plans',
        }
        return render(request, self.template_name, context)

class PlanCreateView(SuperAdminRequiredMixin, View):
    template_name = 'admin/plans/form.html'

    def get(self, request):
        context = {
            'page_title': 'Create Subscription Plan',
            'plan_choices': SubscriptionPlan.PLAN_CHOICES,
            'billing_choices': SubscriptionPlan.BILLING_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        name = request.POST.get('name', '').strip()
        plan_type = request.POST.get('plan_type')
        billing_cycle = request.POST.get('billing_cycle', 'monthly')
        
        if not name or not plan_type:
            messages.error(request, 'Name and Plan Type are required.')
            return redirect('adminapp:plan_create')

        if SubscriptionPlan.objects.filter(plan_type=plan_type).exists():
            # If standard ones already exist, they might just want a custom type or they might be editing. 
            # In create, if they use the same plan_type (which has unique=True), it will fail.
            # We should handle it or just let DB throw integrity error, but let's be graceful.
            pass

        try:
            plan = SubscriptionPlan.objects.create(
                name=name,
                plan_type=plan_type,
                billing_cycle=billing_cycle,
                price=request.POST.get('price') or 0,
                annual_price=request.POST.get('annual_price') or 0,
                trial_days=request.POST.get('trial_days') or 14,
                description=request.POST.get('description', '').strip(),
                is_active=request.POST.get('is_active') == 'true',
                sort_order=request.POST.get('sort_order') or 0,
                max_products=request.POST.get('max_products') or 100,
                max_branches=request.POST.get('max_branches') or 1,
                max_staff=request.POST.get('max_staff') or 3,
                max_monthly_orders=request.POST.get('max_monthly_orders') or 500,
                has_whatsapp=request.POST.get('has_whatsapp') == 'on',
                has_loyalty=request.POST.get('has_loyalty') == 'on',
                has_crm=request.POST.get('has_crm') == 'on',
                has_marketing=request.POST.get('has_marketing') == 'on',
                has_api_access=request.POST.get('has_api_access') == 'on',
                has_white_label=request.POST.get('has_white_label') == 'on',
                has_advanced_reports=request.POST.get('has_advanced_reports') == 'on',
            )
            messages.success(request, f'Subscription Plan "{plan.name}" created successfully.')
        except Exception as e:
            messages.error(request, f'Error creating plan: {str(e)}')
            return redirect('adminapp:plan_create')

        return redirect('adminapp:plan_list')

class PlanEditView(SuperAdminRequiredMixin, View):
    template_name = 'admin/plans/form.html'

    def get(self, request, plan_id):
        plan = get_object_or_404(SubscriptionPlan, pk=plan_id)
        context = {
            'plan': plan,
            'page_title': f'Edit Plan — {plan.name}',
            'plan_choices': SubscriptionPlan.PLAN_CHOICES,
            'billing_choices': SubscriptionPlan.BILLING_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request, plan_id):
        plan = get_object_or_404(SubscriptionPlan, pk=plan_id)
        
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'Name is required.')
            return redirect('adminapp:plan_edit', plan_id=plan.pk)

        plan.name = name
        plan.billing_cycle = request.POST.get('billing_cycle', 'monthly')
        plan.price = request.POST.get('price') or 0
        plan.annual_price = request.POST.get('annual_price') or 0
        plan.trial_days = request.POST.get('trial_days') or 14
        plan.description = request.POST.get('description', '').strip()
        plan.is_active = request.POST.get('is_active') == 'true'
        plan.sort_order = request.POST.get('sort_order') or 0
        
        plan.max_products = request.POST.get('max_products') or 100
        plan.max_branches = request.POST.get('max_branches') or 1
        plan.max_staff = request.POST.get('max_staff') or 3
        plan.max_monthly_orders = request.POST.get('max_monthly_orders') or 500
        
        plan.has_whatsapp = request.POST.get('has_whatsapp') == 'on'
        plan.has_loyalty = request.POST.get('has_loyalty') == 'on'
        plan.has_crm = request.POST.get('has_crm') == 'on'
        plan.has_marketing = request.POST.get('has_marketing') == 'on'
        plan.has_api_access = request.POST.get('has_api_access') == 'on'
        plan.has_white_label = request.POST.get('has_white_label') == 'on'
        plan.has_advanced_reports = request.POST.get('has_advanced_reports') == 'on'
        
        try:
            plan.save()
            messages.success(request, f'Subscription Plan "{plan.name}" updated successfully.')
        except Exception as e:
            messages.error(request, f'Error updating plan: {str(e)}')
            return redirect('adminapp:plan_edit', plan_id=plan.pk)

        return redirect('adminapp:plan_list')
