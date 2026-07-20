from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.db import transaction
from django.utils.text import slugify
from django.db.models import Q
import datetime
import json

from core.mixins import PermissionRequiredMixin
from .models import Category, AttributeGroup, Attribute, AttributeOption, Product, ProductVariant, ProductImage, ProductInfoSection


# ─────────────────────────────────────────────────────────────
# CATEGORIES MANAGEMENT
# ─────────────────────────────────────────────────────────────

class CategoryListView(PermissionRequiredMixin, View):
    permission_codename = 'view_catalog'
    template_name = 'vendor/catalog/category_list.html'

    def get(self, request):
        categories = Category.objects.filter(vendor=request.user.vendor)
        context = {
            'categories': categories,
            'page_title': 'Categories Tree',
        }
        return render(request, self.template_name, context)


class CategoryCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'
    template_name = 'vendor/catalog/category_form.html'

    def get(self, request):
        categories = Category.objects.filter(vendor=request.user.vendor)
        context = {
            'categories': categories,
            'page_title': 'Create Category',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent_id')
        slug = request.POST.get('slug', '').strip()
        description = request.POST.get('description', '').strip()
        image = request.FILES.get('image')
        is_active = request.POST.get('is_active') == 'true'

        if not name:
            messages.error(request, 'Category name is required.')
            return redirect('catalog:category_create')

        if not slug:
            slug = slugify(name)

        vendor = request.user.vendor

        if Category.objects.filter(vendor=vendor, slug=slug).exists():
            messages.error(request, f'A category with slug "{slug}" already exists.')
            return redirect('catalog:category_create')

        parent = None
        if parent_id:
            parent = get_object_or_404(Category, vendor=vendor, pk=parent_id)

        Category.objects.create(
            vendor=vendor,
            parent=parent,
            name=name,
            slug=slug,
            description=description,
            image=image,
            is_active=is_active
        )

        messages.success(request, f'Category "{name}" created successfully!')
        return redirect('catalog:category_list')


class CategoryEditView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'
    template_name = 'vendor/catalog/category_form.html'

    def get(self, request, category_id):
        vendor = request.user.vendor
        category = get_object_or_404(Category, vendor=vendor, pk=category_id)
        descendants = category.get_descendants(include_self=True)
        categories = Category.objects.filter(vendor=vendor).exclude(pk__in=descendants)

        context = {
            'category': category,
            'categories': categories,
            'page_title': f'Edit Category — {category.name}',
        }
        return render(request, self.template_name, context)

    def post(self, request, category_id):
        vendor = request.user.vendor
        category = get_object_or_404(Category, vendor=vendor, pk=category_id)
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent_id')
        slug = request.POST.get('slug', '').strip()
        description = request.POST.get('description', '').strip()
        image = request.FILES.get('image')
        is_active = request.POST.get('is_active') == 'true'

        if not name:
            messages.error(request, 'Category name is required.')
            return redirect('catalog:category_edit', category_id=category.pk)

        if not slug:
            slug = slugify(name)

        if Category.objects.filter(vendor=vendor, slug=slug).exclude(pk=category.pk).exists():
            messages.error(request, f'A category with slug "{slug}" already exists.')
            return redirect('catalog:category_edit', category_id=category.pk)

        parent = None
        if parent_id:
            descendants = category.get_descendants(include_self=True)
            if int(parent_id) in [d.pk for d in descendants]:
                messages.error(request, 'Cannot set parent to self or a child category.')
                return redirect('catalog:category_edit', category_id=category.pk)
            parent = get_object_or_404(Category, vendor=vendor, pk=parent_id)

        category.name = name
        category.parent = parent
        category.slug = slug
        category.description = description
        if image:
            category.image = image
        category.is_active = is_active
        category.save()

        messages.success(request, f'Category "{name}" updated successfully!')
        return redirect('catalog:category_list')


class CategoryDeleteView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'

    def post(self, request, category_id):
        category = get_object_or_404(Category, vendor=request.user.vendor, pk=category_id)
        name = category.name
        category.delete()
        messages.success(request, f'Category "{name}" and its subcategories removed successfully.')
        return redirect('catalog:category_list')


# ─────────────────────────────────────────────────────────────
# ATTRIBUTES & SPECIFICATIONS
# ─────────────────────────────────────────────────────────────

class AttributeListView(PermissionRequiredMixin, View):
    permission_codename = 'view_catalog'
    template_name = 'vendor/catalog/attribute_list.html'

    def get(self, request):
        vendor = request.user.vendor
        groups = AttributeGroup.objects.filter(vendor=vendor).order_by('name')
        attributes = Attribute.objects.filter(vendor=vendor).order_by('name').select_related('group')
        context = {
            'groups': groups,
            'attributes': attributes,
            'page_title': 'Attributes & Specifications',
        }
        return render(request, self.template_name, context)


class AttributeGroupCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'

    def post(self, request):
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'Attribute Group name is required.')
            return redirect('catalog:attribute_list')
        
        vendor = request.user.vendor
        if AttributeGroup.objects.filter(vendor=vendor, name__iexact=name).exists():
            messages.error(request, f'An attribute group named "{name}" already exists.')
            return redirect('catalog:attribute_list')

        AttributeGroup.objects.create(
            vendor=vendor,
            name=name,
            description=description
        )
        messages.success(request, f'Attribute Group "{name}" created successfully!')
        return redirect('catalog:attribute_list')


class AttributeGroupEditView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'
    template_name = 'vendor/catalog/attribute_group_form.html'

    def get(self, request, group_id):
        group = get_object_or_404(AttributeGroup, vendor=request.user.vendor, pk=group_id)
        context = {
            'group': group,
            'page_title': f'Edit Attribute Group — {group.name}'
        }
        return render(request, self.template_name, context)

    def post(self, request, group_id):
        group = get_object_or_404(AttributeGroup, vendor=request.user.vendor, pk=group_id)
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, 'Attribute Group name is required.')
            return redirect('catalog:attribute_group_edit', group_id=group.pk)

        if AttributeGroup.objects.filter(vendor=request.user.vendor, name__iexact=name).exclude(pk=group.pk).exists():
            messages.error(request, f'An attribute group named "{name}" already exists.')
            return redirect('catalog:attribute_group_edit', group_id=group.pk)

        group.name = name
        group.description = description
        group.save()
        messages.success(request, f'Attribute Group "{name}" updated successfully!')
        return redirect('catalog:attribute_list')


class AttributeGroupDeleteView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'

    def post(self, request, group_id):
        group = get_object_or_404(AttributeGroup, vendor=request.user.vendor, pk=group_id)
        name = group.name
        group.delete()
        messages.success(request, f'Attribute Group "{name}" removed successfully.')
        return redirect('catalog:attribute_list')


class AttributeCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'
    template_name = 'vendor/catalog/attribute_form.html'

    def get(self, request):
        vendor = request.user.vendor
        groups = AttributeGroup.objects.filter(vendor=vendor).order_by('name')
        context = {
            'groups': groups,
            'types': Attribute.TYPE_CHOICES,
            'page_title': 'Add Attribute / Specification',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().lower()
        group_id = request.POST.get('group_id')
        type_choice = request.POST.get('type', 'text')
        is_required = request.POST.get('is_required') == 'true'
        is_filterable = request.POST.get('is_filterable') == 'true'
        options_text = request.POST.get('options_text', '').strip()

        if not name or not code:
            messages.error(request, 'Name and code are required.')
            return redirect('catalog:attribute_create')

        vendor = request.user.vendor
        if Attribute.objects.filter(vendor=vendor, code=code).exists():
            messages.error(request, f'An attribute with code "{code}" already exists.')
            return redirect('catalog:attribute_create')

        group = None
        if group_id:
            group = get_object_or_404(AttributeGroup, vendor=vendor, pk=group_id)

        with transaction.atomic():
            attribute = Attribute.objects.create(
                vendor=vendor,
                group=group,
                name=name,
                code=code,
                type=type_choice,
                is_required=is_required,
                is_filterable=is_filterable,
                is_active=True
            )

            if type_choice == 'select' and options_text:
                options = [val.strip() for val in options_text.split(',') if val.strip()]
                for idx, val in enumerate(options):
                    AttributeOption.objects.create(
                        attribute=attribute,
                        value=val,
                        sort_order=idx
                    )

        messages.success(request, f'Attribute "{name}" created successfully!')
        return redirect('catalog:attribute_list')


class AttributeEditView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'
    template_name = 'vendor/catalog/attribute_form.html'

    def get(self, request, attribute_id):
        vendor = request.user.vendor
        attribute = get_object_or_404(Attribute, vendor=vendor, pk=attribute_id)
        groups = AttributeGroup.objects.filter(vendor=vendor).order_by('name')
        options = attribute.options.all().order_by('sort_order', 'value')
        options_text = ", ".join([o.value for o in options])

        context = {
            'attribute': attribute,
            'groups': groups,
            'types': Attribute.TYPE_CHOICES,
            'options_text': options_text,
            'page_title': f'Edit Attribute — {attribute.name}',
        }
        return render(request, self.template_name, context)

    def post(self, request, attribute_id):
        vendor = request.user.vendor
        attribute = get_object_or_404(Attribute, vendor=vendor, pk=attribute_id)
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip().lower()
        group_id = request.POST.get('group_id')
        type_choice = request.POST.get('type', 'text')
        is_required = request.POST.get('is_required') == 'true'
        is_filterable = request.POST.get('is_filterable') == 'true'
        options_text = request.POST.get('options_text', '').strip()

        if not name or not code:
            messages.error(request, 'Name and code are required.')
            return redirect('catalog:attribute_edit', attribute_id=attribute.pk)

        if Attribute.objects.filter(vendor=vendor, code=code).exclude(pk=attribute.pk).exists():
            messages.error(request, f'An attribute with code "{code}" already exists.')
            return redirect('catalog:attribute_edit', attribute_id=attribute.pk)

        group = None
        if group_id:
            group = get_object_or_404(AttributeGroup, vendor=vendor, pk=group_id)

        with transaction.atomic():
            attribute.name = name
            attribute.code = code
            attribute.group = group
            attribute.type = type_choice
            attribute.is_required = is_required
            attribute.is_filterable = is_filterable
            attribute.save()

            if type_choice == 'select':
                existing_options = {o.value: o for o in attribute.options.all()}
                new_values = [val.strip() for val in options_text.split(',') if val.strip()]

                attribute.options.exclude(value__in=new_values).delete()

                for idx, val in enumerate(new_values):
                    if val in existing_options:
                        opt = existing_options[val]
                        opt.sort_order = idx
                        opt.save()
                    else:
                        AttributeOption.objects.create(
                            attribute=attribute,
                            value=val,
                            sort_order=idx
                        )
            else:
                attribute.options.all().delete()

        messages.success(request, f'Attribute "{name}" updated successfully!')
        return redirect('catalog:attribute_list')


class AttributeDeleteView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'

    def post(self, request, attribute_id):
        attribute = get_object_or_404(Attribute, vendor=request.user.vendor, pk=attribute_id)
        name = attribute.name
        attribute.delete()
        messages.success(request, f'Attribute "{name}" removed successfully.')
        return redirect('catalog:attribute_list')


# ─────────────────────────────────────────────────────────────
# PRODUCTS MANAGEMENT
# ─────────────────────────────────────────────────────────────

class ProductListView(PermissionRequiredMixin, View):
    permission_codename = 'view_catalog'
    template_name = 'vendor/catalog/product_list.html'

    def get(self, request):
        products = Product.objects.filter(vendor=request.user.vendor).select_related('category').prefetch_related('variants').order_by('-created_at')
        
        from django.core.paginator import Paginator
        paginator = Paginator(products, 20)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'products': page_obj,
            'page_title': 'Product Catalog',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        vendor = request.user.vendor
        action = request.POST.get('action')
        
        if action == 'bulk_delete':
            product_ids = request.POST.getlist('product_ids')
            if product_ids:
                Product.objects.filter(vendor=vendor, id__in=product_ids).delete()
                messages.success(request, f'Successfully deleted {len(product_ids)} product(s).')
            else:
                messages.warning(request, 'No products selected for deletion.')
                
        return redirect('catalog:product_list')


class ProductCreateView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'
    template_name = 'vendor/catalog/product_form.html'

    def get(self, request):
        vendor = request.user.vendor
        categories = Category.objects.filter(vendor=vendor)
        attributes = Attribute.objects.filter(vendor=vendor, type='select', is_active=True).prefetch_related('options')
        general_attributes = Attribute.objects.filter(vendor=vendor, is_active=True).exclude(type='select').order_by('name')
        
        context = {
            'categories': categories,
            'attributes': attributes,
            'general_attributes': general_attributes,
            'page_title': 'Add Product',
        }
        return render(request, self.template_name, context)

    def post(self, request):
        vendor = request.user.vendor
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip()
        category_id = request.POST.get('category_id')
        description = request.POST.get('description', '').strip()
        status = request.POST.get('status', 'draft')
        has_variants = request.POST.get('has_variants') == 'true'

        if not name:
            messages.error(request, 'Product name is required.')
            return redirect('catalog:product_create')

        if not slug:
            slug = slugify(name)

        if Product.objects.filter(vendor=vendor, slug=slug).exists():
            messages.error(request, f'A product with slug "{slug}" already exists.')
            return redirect('catalog:product_create')

        category = None
        if category_id:
            category = get_object_or_404(Category, vendor=vendor, pk=category_id)

        with transaction.atomic():
            product = Product.objects.create(
                vendor=vendor,
                category=category,
                name=name,
                slug=slug,
                description=description,
                status=status,
                has_variants=has_variants
            )

            # Process gallery images
            gallery_files = request.FILES.getlist('gallery_images')
            for f in gallery_files:
                ProductImage.objects.create(product=product, image=f)

            # Process info sections
            info_ids = request.POST.getlist('info_id[]')
            info_headings = request.POST.getlist('info_heading[]')
            info_contents = request.POST.getlist('info_content[]')
            for idx, sid in enumerate(info_ids):
                heading = info_headings[idx].strip() if idx < len(info_headings) else ''
                content = info_contents[idx].strip() if idx < len(info_contents) else ''
                image = request.FILES.get(f'info_image_{sid}')
                if heading or content or image:
                    ProductInfoSection.objects.create(
                        product=product,
                        heading=heading,
                        content=content,
                        image=image,
                        sort_order=idx
                    )

            # Process general attributes
            general_attrs = Attribute.objects.filter(vendor=vendor, is_active=True).exclude(type='select')
            attrs_data = {}
            for attr in general_attrs:
                val = request.POST.get(f'attr_{attr.code}')
                if attr.type == 'boolean':
                    attrs_data[attr.code] = 'true' if val == 'true' else 'false'
                elif val is not None and str(val).strip():
                    attrs_data[attr.code] = str(val).strip()
            custom_option_enabled = request.POST.get('custom_option_enabled') == 'true'
            if custom_option_enabled:
                attrs_data['custom_option_enabled'] = True
                attrs_data['custom_fee'] = request.POST.get('custom_fee', '0.00').strip()
                custom_fields = request.POST.get('custom_fields', '').strip()
                if custom_fields:
                    attrs_data['custom_fields'] = custom_fields

            attrs_data['base_price'] = request.POST.get('base_price', '0.00').strip()
            attrs_data['base_compare_price'] = request.POST.get('base_compare_price', '').strip()
            apply_base_price_to_variants = request.POST.get('apply_base_price_to_variants') == 'true'

            product.attributes_data = attrs_data
            product.save()

            if not has_variants:
                sku = request.POST.get('sku', '').strip()
                price = attrs_data.get('base_price', '0.00')
                compare_at_price = attrs_data.get('base_compare_price', '')
                stock_qty = request.POST.get('stock_qty', '0.00').strip()
                image = request.FILES.get('image')

                if not sku:
                    sku = f"{slugify(name)[:30]}-{datetime.datetime.now().strftime('%y%m%d%H%M')}".upper()

                ProductVariant.objects.create(
                    product=product,
                    name='',
                    sku=sku.upper().strip(),
                    price=price or '0.00',
                    compare_at_price=compare_at_price or None,
                    stock_qty=stock_qty or '0.00',
                    image=image
                )
            else:
                variant_skus = request.POST.getlist('variant_sku[]')
                variant_prices = request.POST.getlist('variant_price[]')
                variant_compare_at_prices = request.POST.getlist('variant_compare_at_price[]')
                variant_stock_qtys = request.POST.getlist('variant_stock_qty[]')
                variant_attrs_jsons = request.POST.getlist('variant_attributes_json[]')
                variant_row_indices = request.POST.getlist('variant_row_index[]')

                for idx, sku in enumerate(variant_skus):
                    if not sku:
                        continue
                    
                    if apply_base_price_to_variants:
                        price = attrs_data.get('base_price', '0.00')
                        compare_at = attrs_data.get('base_compare_price', '')
                    else:
                        price = variant_prices[idx] if idx < len(variant_prices) else '0.00'
                        compare_at = variant_compare_at_prices[idx] if idx < len(variant_compare_at_prices) else ''
                    
                    stock = variant_stock_qtys[idx] if idx < len(variant_stock_qtys) else '0.00'
                    attrs_json_str = variant_attrs_jsons[idx] if idx < len(variant_attrs_jsons) else '{}'
                    
                    try:
                        attrs_data = json.loads(attrs_json_str)
                    except Exception:
                        attrs_data = {}

                    variant_name = ", ".join(attrs_data.values())
                    
                    row_idx = variant_row_indices[idx] if idx < len(variant_row_indices) else None
                    img = None
                    if row_idx is not None:
                        img = request.FILES.get(f'variant_image_{row_idx}')

                    sku_clean = sku.upper().strip()
                    import uuid
                    while ProductVariant.objects.filter(sku=sku_clean).exists():
                        sku_clean = f"{sku_clean}-{uuid.uuid4().hex[:4].upper()}"

                    ProductVariant.objects.create(
                        product=product,
                        name=variant_name,
                        sku=sku_clean,
                        price=price or '0.00',
                        compare_at_price=compare_at or None,
                        stock_qty=stock or '0.00',
                        attributes_data=attrs_data,
                        image=img
                    )

        messages.success(request, f'Product "{name}" added successfully!')
        return redirect('catalog:product_list')


class ProductEditView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'
    template_name = 'vendor/catalog/product_form.html'

    def get(self, request, product_id):
        vendor = request.user.vendor
        product = get_object_or_404(Product, vendor=vendor, pk=product_id)
        categories = Category.objects.filter(vendor=vendor)
        attributes = Attribute.objects.filter(vendor=vendor, type='select', is_active=True).prefetch_related('options')
        
        variants = product.variants.all()
        default_variant = None
        if not product.has_variants:
            default_variant = variants.first()

        general_attributes = Attribute.objects.filter(vendor=vendor, is_active=True).exclude(type='select').order_by('name')

        context = {
            'product': product,
            'categories': categories,
            'attributes': attributes,
            'general_attributes': general_attributes,
            'variants': variants,
            'default_variant': default_variant,
            'page_title': f'Edit Product — {product.name}',
        }
        return render(request, self.template_name, context)

    def post(self, request, product_id):
        vendor = request.user.vendor
        product = get_object_or_404(Product, vendor=vendor, pk=product_id)
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip()
        category_id = request.POST.get('category_id')
        description = request.POST.get('description', '').strip()
        status = request.POST.get('status', 'draft')
        has_variants = request.POST.get('has_variants') == 'true'

        if not name:
            messages.error(request, 'Product name is required.')
            return redirect('catalog:product_edit', product_id=product.pk)

        if not slug:
            slug = slugify(name)

        if Product.objects.filter(vendor=vendor, slug=slug).exclude(pk=product.pk).exists():
            messages.error(request, f'A product with slug "{slug}" already exists.')
            return redirect('catalog:product_edit', product_id=product.pk)

        category = None
        if category_id:
            category = get_object_or_404(Category, vendor=vendor, pk=category_id)

        with transaction.atomic():
            product.name = name
            product.slug = slug
            product.category = category
            product.description = description
            product.status = status
            
            if not has_variants and product.has_variants:
                product.variants.all().delete()
                product.has_variants = False
            
            elif has_variants and not product.has_variants:
                product.variants.all().delete()
                product.has_variants = True

            # Process general attributes
            general_attrs = Attribute.objects.filter(vendor=vendor, is_active=True).exclude(type='select')
            attrs_data = {}
            for attr in general_attrs:
                val = request.POST.get(f'attr_{attr.code}')
                # For boolean, it will only be present if checked, but wait, a checkbox value is only sent if checked.
                # However, if we use a hidden input before checkbox, we can handle it, or just use boolean check.
                if attr.type == 'boolean':
                    attrs_data[attr.code] = 'true' if val == 'true' else 'false'
                elif val is not None and str(val).strip():
                    attrs_data[attr.code] = str(val).strip()
            custom_option_enabled = request.POST.get('custom_option_enabled') == 'true'
            if custom_option_enabled:
                attrs_data['custom_option_enabled'] = True
                attrs_data['custom_fee'] = request.POST.get('custom_fee', '0.00').strip()
                custom_fields = request.POST.get('custom_fields', '').strip()
                if custom_fields:
                    attrs_data['custom_fields'] = custom_fields
            
            attrs_data['base_price'] = request.POST.get('base_price', '0.00').strip()
            attrs_data['base_compare_price'] = request.POST.get('base_compare_price', '').strip()
            apply_base_price_to_variants = request.POST.get('apply_base_price_to_variants') == 'true'

            product.attributes_data = attrs_data
            product.save()

            # Process gallery deletions
            delete_image_ids = request.POST.getlist('delete_images[]')
            if delete_image_ids:
                product.images.filter(pk__in=delete_image_ids).delete()

            # Process new gallery uploads
            gallery_files = request.FILES.getlist('gallery_images')
            for f in gallery_files:
                ProductImage.objects.create(product=product, image=f)

            # Process info sections
            info_ids = request.POST.getlist('info_id[]')
            info_headings = request.POST.getlist('info_heading[]')
            info_contents = request.POST.getlist('info_content[]')
            
            submitted_existing_ids = []
            
            for idx, sid in enumerate(info_ids):
                heading = info_headings[idx].strip() if idx < len(info_headings) else ''
                content = info_contents[idx].strip() if idx < len(info_contents) else ''
                image = request.FILES.get(f'info_image_{sid}')
                
                if str(sid).startswith('new_'):
                    if heading or content or image:
                        new_section = ProductInfoSection.objects.create(
                            product=product,
                            heading=heading,
                            content=content,
                            image=image,
                            sort_order=idx
                        )
                        submitted_existing_ids.append(new_section.id)
                else:
                    try:
                        section = ProductInfoSection.objects.get(id=sid, product=product)
                        section.heading = heading
                        section.content = content
                        section.sort_order = idx
                        if image:
                            section.image = image
                        elif request.POST.get(f'delete_info_image_{sid}') == 'true':
                            if section.image:
                                section.image.delete(save=False)
                                section.image = None
                        section.save()
                        submitted_existing_ids.append(section.id)
                    except ProductInfoSection.DoesNotExist:
                        pass
                        
            # Delete any existing sections that were not submitted
            product.info_sections.exclude(id__in=submitted_existing_ids).delete()

            if not has_variants:
                sku = request.POST.get('sku', '').strip()
                price = attrs_data.get('base_price', '0.00')
                compare_at_price = attrs_data.get('base_compare_price', '')
                stock_qty = request.POST.get('stock_qty', '0.00').strip()
                image = request.FILES.get('image')

                if not sku:
                    sku = f"{slugify(name)[:30]}-{datetime.datetime.now().strftime('%y%m%d%H%M')}".upper()

                variant = product.variants.first()
                if variant:
                    variant.sku = sku.upper().strip()
                    variant.price = price or '0.00'
                    variant.compare_at_price = compare_at_price or None
                    variant.stock_qty = stock_qty or '0.00'
                    if image:
                        variant.image = image
                    variant.name = ''
                    variant.save()
                else:
                    ProductVariant.objects.create(
                        product=product,
                        name='',
                        sku=sku.upper().strip(),
                        price=price or '0.00',
                        compare_at_price=compare_at_price or None,
                        stock_qty=stock_qty or '0.00',
                        image=image
                    )
            else:
                variant_skus = request.POST.getlist('variant_sku[]')
                variant_prices = request.POST.getlist('variant_price[]')
                variant_compare_at_prices = request.POST.getlist('variant_compare_at_price[]')
                variant_stock_qtys = request.POST.getlist('variant_stock_qty[]')
                variant_attrs_jsons = request.POST.getlist('variant_attributes_json[]')
                variant_ids = request.POST.getlist('variant_id[]')
                variant_row_indices = request.POST.getlist('variant_row_index[]')

                keep_variant_ids = []

                for idx, sku in enumerate(variant_skus):
                    if not sku:
                        continue

                    if apply_base_price_to_variants:
                        price = attrs_data.get('base_price', '0.00')
                        compare_at = attrs_data.get('base_compare_price', '')
                    else:
                        price = variant_prices[idx] if idx < len(variant_prices) else '0.00'
                        compare_at = variant_compare_at_prices[idx] if idx < len(variant_compare_at_prices) else ''
                    
                    stock = variant_stock_qtys[idx] if idx < len(variant_stock_qtys) else '0.00'
                    attrs_json_str = variant_attrs_jsons[idx] if idx < len(variant_attrs_jsons) else '{}'
                    v_id = variant_ids[idx] if (idx < len(variant_ids) and variant_ids[idx]) else None
                    
                    try:
                        variant_attrs = json.loads(attrs_json_str)
                    except Exception:
                        variant_attrs = {}

                    variant_name = ", ".join(variant_attrs.values())
                    
                    row_idx = variant_row_indices[idx] if idx < len(variant_row_indices) else None
                    img = None
                    if row_idx is not None:
                        img = request.FILES.get(f'variant_image_{row_idx}')

                    sku_clean = sku.upper().strip()
                    v = None
                    if v_id:
                        v = product.variants.filter(pk=v_id).first()
                    
                    if not v:
                        v = ProductVariant.objects.filter(sku=sku_clean).first()
                        if v and v.product != product:
                            import uuid
                            sku_clean = f"{sku_clean}-{uuid.uuid4().hex[:4].upper()}"
                            v = None

                    if v:
                        v.name = variant_name
                        v.sku = sku_clean
                        v.price = price or '0.00'
                        v.compare_at_price = compare_at or None
                        v.stock_qty = stock or '0.00'
                        v.attributes_data = variant_attrs
                        if img:
                            v.image = img
                        v.save()
                        keep_variant_ids.append(v.pk)
                    else:
                        import uuid
                        while ProductVariant.objects.filter(sku=sku_clean).exists():
                            sku_clean = f"{sku_clean}-{uuid.uuid4().hex[:4].upper()}"
                            
                        new_v = ProductVariant.objects.create(
                            product=product,
                            name=variant_name,
                            sku=sku_clean,
                            price=price or '0.00',
                            compare_at_price=compare_at or None,
                            stock_qty=stock or '0.00',
                            attributes_data=variant_attrs,
                            image=img
                        )
                        keep_variant_ids.append(new_v.pk)

                product.variants.exclude(pk__in=keep_variant_ids).delete()

        messages.success(request, f'Product "{name}" updated successfully!')
        return redirect('catalog:product_list')


class ProductDeleteView(PermissionRequiredMixin, View):
    permission_codename = 'manage_catalog'

    def post(self, request, product_id):
        product = get_object_or_404(Product, vendor=request.user.vendor, pk=product_id)
        name = product.name
        product.delete()
        messages.success(request, f'Product "{name}" removed successfully.')
        return redirect('catalog:product_list')
