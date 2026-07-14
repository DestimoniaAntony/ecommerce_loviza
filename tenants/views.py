from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
import datetime

from tenants.models import Vendor, SubscriptionPlan, VendorSubscription
from accounts.models import User
from branches.models import Branch
from core.utils import generate_unique_slug


class VendorOnboardingView(View):
    template_name = 'auth/onboarding.html'

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True)
        context = {
            'plans': plans,
            'page_title': 'Vendor Onboarding On CommerceHub',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        # ── Step 1 & 2 Required identity fields ──
        business_name = request.POST.get('business_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()
        plan_id = request.POST.get('plan_id')

        if not business_name or not phone or not password or not plan_id:
            messages.error(request, 'Please complete all required fields.')
            return redirect('vendor_onboarding')

        # Check uniqueness in both models
        if Vendor.objects.filter(phone=phone).exists() or User.objects.filter(phone=phone).exists():
            messages.error(request, f'An account with the phone number {phone} already exists.')
            return redirect('vendor_onboarding')

        # ── Address fields ──
        address_line1 = request.POST.get('address_line1', '').strip()
        address_line2 = request.POST.get('address_line2', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        pincode = request.POST.get('pincode', '').strip()
        country = request.POST.get('country', 'India').strip()

        # ── Plan validation ──
        try:
            plan = SubscriptionPlan.objects.get(pk=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            messages.error(request, 'Selected subscription plan is invalid.')
            return redirect('vendor_onboarding')

        # ── Create everything in a database transaction ──
        try:
            with transaction.atomic():
                # 1. Create Vendor (starts as pending approval by default)
                slug = generate_unique_slug(Vendor, business_name)
                vendor = Vendor(
                    business_name=business_name,
                    slug=slug,
                    business_type=request.POST.get('business_type', 'single_store'),
                    gst_number=request.POST.get('gst_number', '').strip(),
                    pan_number=request.POST.get('pan_number', '').strip(),
                    # Contact
                    phone=phone,
                    whatsapp_number=request.POST.get('whatsapp_number', '').strip() or phone,
                    email=request.POST.get('email', '').strip(),
                    website=request.POST.get('website', '').strip(),
                    # Address
                    address_line1=address_line1,
                    address_line2=address_line2,
                    city=city,
                    state=state,
                    pincode=pincode,
                    country=country,
                    # Settings
                    currency=request.POST.get('currency', 'INR'),
                    currency_symbol=request.POST.get('currency_symbol', '₹'),
                    timezone=request.POST.get('timezone', 'Asia/Kolkata'),
                    checkout_workflow=request.POST.get('checkout_workflow', 'online_payment'),
                    # Branding
                    primary_color=request.POST.get('primary_color', '#6366f1'),
                    secondary_color=request.POST.get('secondary_color', '#8b5cf6'),
                    # SEO
                    meta_title=business_name,
                    meta_description=f'Welcome to {business_name} store powered by CommerceHub.',
                    status='pending',
                    is_active=True,
                )

                # File uploads if provided
                if request.FILES.get('logo'):
                    vendor.logo = request.FILES['logo']
                if request.FILES.get('banner'):
                    vendor.banner = request.FILES['banner']
                if request.FILES.get('favicon'):
                    vendor.favicon = request.FILES['favicon']

                vendor.save()

                # 2. Create the main Branch
                branch = Branch.objects.create(
                    vendor=vendor,
                    name='Main Branch',
                    code='MAIN',
                    phone=phone,
                    email=vendor.email,
                    address_line1=address_line1,
                    address_line2=address_line2,
                    city=city,
                    state=state,
                    pincode=pincode,
                    country=country,
                    is_main_branch=True,
                    is_active=True,
                )

                # 3. Create the Owner User account
                User.objects.create_user(
                    phone=phone,
                    password=password,
                    email=vendor.email,
                    first_name=request.POST.get('owner_first_name', 'Store').strip(),
                    last_name=request.POST.get('owner_last_name', 'Admin').strip(),
                    user_type='vendor_staff',
                    vendor=vendor,
                    branch=branch,
                    is_active=True,
                )

                # 4. Create the Subscription
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

            messages.success(request, f'Registration successful! Your store "{business_name}" is pending approval. You can try logging in once approved.')
            return redirect('accounts:vendor_login')

        except Exception as e:
            messages.error(request, f'An error occurred during onboarding: {str(e)}')
            return redirect('vendor_onboarding')
