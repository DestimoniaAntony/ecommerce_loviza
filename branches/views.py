from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.db.models import Q
from core.mixins import PermissionRequiredMixin
from .models import Branch, Franchise, Partner
from tenants.models import Vendor
import datetime


class BranchListView(PermissionRequiredMixin, View):
    permission_codename = 'view_branches'
    template_name = 'vendor/branches/list.html'

    def get(self, request):
        vendor = request.user.vendor
        branches = Branch.objects.filter(vendor=vendor).order_by('-is_main_branch', 'name')
        
        # Partners related to this vendor
        partners = Partner.objects.filter(vendor=vendor).order_by('name')
        
        # If this vendor is a parent, get all their child franchises
        franchises_as_parent = Franchise.objects.filter(parent_vendor=vendor).select_related('child_vendor')
        
        # If this vendor is a franchise store, get their parent relationship
        franchise_as_child = Franchise.objects.filter(child_vendor=vendor).select_related('parent_vendor').first()

        # Check branch limit
        can_add_branch = True
        active_sub = vendor.subscriptions.filter(is_active=True).first()
        if active_sub:
            if branches.count() >= active_sub.plan.max_branches:
                can_add_branch = False

        context = {
            'branches': branches,
            'partners': partners,
            'franchises_as_parent': franchises_as_parent,
            'franchise_as_child': franchise_as_child,
            'can_add_branch': can_add_branch,
            'page_title': 'Branches & Franchise',
        }
        return render(request, self.template_name, context)


class BranchCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_branches'
    template_name = 'vendor/branches/form.html'

    def get(self, request):
        context = {
            'page_title': 'Add New Branch',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        address_line1 = request.POST.get('address_line1', '').strip()
        address_line2 = request.POST.get('address_line2', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        pincode = request.POST.get('pincode', '').strip()
        country = request.POST.get('country', 'India').strip()
        is_main_branch = request.POST.get('is_main_branch') == 'true'

        if not name or not code or not phone:
            messages.error(request, 'Name, code, and phone are required.')
            return redirect('branches:branch_create')

        vendor = request.user.vendor

        active_sub = vendor.subscriptions.filter(is_active=True).first()
        if active_sub:
            max_branches = active_sub.plan.max_branches
            current_count = Branch.objects.filter(vendor=vendor).count()
            if current_count >= max_branches:
                messages.error(request, f'Your subscription plan limits you to a maximum of {max_branches} branch(es). Please upgrade your plan to add more.')
                return redirect('branches:branch_list')

        if Branch.objects.filter(vendor=vendor, code=code).exists():
            messages.error(request, f'A branch with code "{code}" already exists.')
            return redirect('branches:branch_create')

        # If setting this branch as main, deactivate other main branches of this vendor
        if is_main_branch:
            Branch.objects.filter(vendor=vendor, is_main_branch=True).update(is_main_branch=False)

        Branch.objects.create(
            vendor=vendor,
            name=name,
            code=code,
            phone=phone,
            email=email,
            address_line1=address_line1,
            address_line2=address_line2,
            city=city,
            state=state,
            pincode=pincode,
            country=country,
            is_main_branch=is_main_branch,
            is_active=True
        )

        messages.success(request, f'Branch "{name}" added successfully!')
        return redirect('branches:branch_list')


class BranchEditView(PermissionRequiredMixin, View):
    permission_codename = 'manage_branches'
    template_name = 'vendor/branches/form.html'

    def get(self, request, branch_id):
        branch = get_object_or_404(Branch, vendor=request.user.vendor, pk=branch_id)
        context = {
            'branch': branch,
            'page_title': f'Edit Branch — {branch.name}',
        }
        return render(request, self.template_name, context)

    def post(self, request, branch_id):
        branch = get_object_or_404(Branch, vendor=request.user.vendor, pk=branch_id)
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().upper()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        address_line1 = request.POST.get('address_line1', '').strip()
        address_line2 = request.POST.get('address_line2', '').strip()
        city = request.POST.get('city', '').strip()
        state = request.POST.get('state', '').strip()
        pincode = request.POST.get('pincode', '').strip()
        country = request.POST.get('country', 'India').strip()
        is_main_branch = request.POST.get('is_main_branch') == 'true'
        is_active = request.POST.get('is_active') == 'true'

        if not name or not code or not phone:
            messages.error(request, 'Name, code, and phone are required.')
            return redirect('branches:branch_edit', branch_id=branch.pk)

        if Branch.objects.filter(vendor=request.user.vendor, code=code).exclude(pk=branch.pk).exists():
            messages.error(request, f'A branch with code "{code}" already exists.')
            return redirect('branches:branch_edit', branch_id=branch.pk)

        if is_main_branch:
            Branch.objects.filter(vendor=request.user.vendor, is_main_branch=True).update(is_main_branch=False)

        branch.name = name
        branch.code = code
        branch.phone = phone
        branch.email = email
        branch.address_line1 = address_line1
        branch.address_line2 = address_line2
        branch.city = city
        branch.state = state
        branch.pincode = pincode
        branch.country = country
        branch.is_main_branch = is_main_branch
        branch.is_active = is_active
        branch.save()

        messages.success(request, f'Branch "{name}" updated successfully!')
        return redirect('branches:branch_list')


class BranchDeleteView(PermissionRequiredMixin, View):
    permission_codename = 'manage_branches'

    def post(self, request, branch_id):
        branch = get_object_or_404(Branch, vendor=request.user.vendor, pk=branch_id)
        
        if branch.is_main_branch:
            messages.error(request, 'You cannot delete the main branch.')
            return redirect('branches:branch_list')

        name = branch.name
        branch.delete()
        messages.success(request, f'Branch "{name}" removed successfully.')
        return redirect('branches:branch_list')


# ─────────────────────────────────────────────────────────────
# PARTNER MANAGEMENT
# ─────────────────────────────────────────────────────────────

class PartnerCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_branches'
    template_name = 'vendor/branches/partner_form.html'

    def get(self, request):
        context = {
            'page_title': 'Add Business Partner',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()

        if not name or not phone:
            messages.error(request, 'Name and phone are required.')
            return redirect('branches:partner_create')

        Partner.objects.create(
            vendor=request.user.vendor,
            name=name,
            phone=phone,
            email=email
        )

        messages.success(request, f'Partner "{name}" added successfully!')
        return redirect('branches:branch_list')


class PartnerEditView(PermissionRequiredMixin, View):
    permission_codename = 'manage_branches'
    template_name = 'vendor/branches/partner_form.html'

    def get(self, request, partner_id):
        partner = get_object_or_404(Partner, vendor=request.user.vendor, pk=partner_id)
        context = {
            'partner': partner,
            'page_title': f'Edit Partner — {partner.name}',
        }
        return render(request, self.template_name, context)

    def post(self, request, partner_id):
        partner = get_object_or_404(Partner, vendor=request.user.vendor, pk=partner_id)
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()

        if not name or not phone:
            messages.error(request, 'Name and phone are required.')
            return redirect('branches:partner_edit', partner_id=partner.pk)

        partner.name = name
        partner.phone = phone
        partner.email = email
        partner.save()

        messages.success(request, f'Partner "{name}" updated successfully!')
        return redirect('branches:branch_list')


class PartnerDeleteView(PermissionRequiredMixin, View):
    permission_codename = 'manage_branches'

    def post(self, request, partner_id):
        partner = get_object_or_404(Partner, vendor=request.user.vendor, pk=partner_id)
        name = partner.name
        partner.delete()
        messages.success(request, f'Partner "{name}" removed successfully.')
        return redirect('branches:branch_list')


# ─────────────────────────────────────────────────────────────
# FRANCHISE MANAGEMENT
# ─────────────────────────────────────────────────────────────

class FranchiseCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_branches'
    template_name = 'vendor/branches/franchise_form.html'

    def get(self, request):
        existing_child_ids = Franchise.objects.values_list('child_vendor_id', flat=True)
        available_vendors = Vendor.objects.filter(
            status='approved',
            is_active=True
        ).exclude(pk=request.user.vendor.pk).exclude(pk__in=existing_child_ids)

        context = {
            'available_vendors': available_vendors,
            'page_title': 'Establish Franchise Agreement',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        child_vendor_id = request.POST.get('child_vendor_id')
        start_date_str = request.POST.get('agreement_start_date')
        end_date_str = request.POST.get('agreement_end_date')
        royalty_pct = request.POST.get('royalty_percentage', '0.00')

        if not child_vendor_id or not start_date_str or not end_date_str:
            messages.error(request, 'All agreement fields are required.')
            return redirect('branches:franchise_create')

        child_vendor = get_object_or_404(Vendor, pk=child_vendor_id)
        parent_vendor = request.user.vendor

        if Franchise.objects.filter(child_vendor=child_vendor).exists():
            messages.error(request, f'Vendor "{child_vendor.business_name}" is already bound to a franchise agreement.')
            return redirect('branches:franchise_create')

        Franchise.objects.create(
            parent_vendor=parent_vendor,
            child_vendor=child_vendor,
            agreement_start_date=start_date_str,
            agreement_end_date=end_date_str,
            royalty_percentage=royalty_pct,
            is_active=True
        )

        messages.success(request, f'Franchise agreement with "{child_vendor.business_name}" created successfully!')
        return redirect('branches:branch_list')
