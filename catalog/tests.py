from django.test import TestCase, Client
from django.urls import reverse
from django.utils.text import slugify
from accounts.models import User
from tenants.models import Vendor
from .models import Category, AttributeGroup, Attribute, AttributeOption, Product, ProductVariant


class CatalogTestCase(TestCase):

    def setUp(self):
        # 1. Create two test vendors
        self.vendor_a = Vendor.objects.create(
            business_name="Vendor A",
            slug="vendora",
            phone="1111111111",
            status="approved",
            is_active=True
        )
        self.vendor_b = Vendor.objects.create(
            business_name="Vendor B",
            slug="vendorb",
            phone="2222222222",
            status="approved",
            is_active=True
        )

        # 2. Create users for both vendors
        self.user_a = User.objects.create_user(
            phone="1111111111",
            password="password",
            vendor=self.vendor_a,
            user_type="vendor_owner",
            is_active=True
        )
        self.user_b = User.objects.create_user(
            phone="2222222222",
            password="password",
            vendor=self.vendor_b,
            user_type="vendor_owner",
            is_active=True
        )

        # Clients for requests
        self.client_a = Client()
        self.client_a.force_login(self.user_a)

        self.client_b = Client()
        self.client_b.force_login(self.user_b)

    def test_category_creation_and_mptt_hierarchy(self):
        # Create a root category for Vendor A
        root = Category.objects.create(
            vendor=self.vendor_a,
            name="Clothing",
            slug="clothing"
        )
        # Create a child category
        child = Category.objects.create(
            vendor=self.vendor_a,
            parent=root,
            name="Shirts",
            slug="shirts"
        )

        self.assertEqual(child.parent, root)
        self.assertIn(child, root.get_descendants())

    def test_single_product_and_default_variant_post(self):
        # Category
        cat = Category.objects.create(
            vendor=self.vendor_a,
            name="Shoes",
            slug="shoes"
        )

        # Post to create product
        url = reverse('catalog:product_create')
        data = {
            'name': 'Running Shoes',
            'slug': 'running-shoes',
            'category_id': cat.pk,
            'description': 'Comfortable running shoes',
            'status': 'published',
            'has_variants': 'false',
            'sku': 'SHOE-RUN-01',
            'price': '1499.00',
            'compare_at_price': '1999.00',
            'stock_qty': '10.00'
        }
        
        response = self.client_a.post(url, data)
        self.assertEqual(response.status_code, 302)  # redirects back to product list

        # Verify product created
        product = Product.objects.get(vendor=self.vendor_a, slug='running-shoes')
        self.assertFalse(product.has_variants)
        self.assertEqual(product.name, 'Running Shoes')

        # Verify single default variant auto-created
        variant = product.variants.first()
        self.assertIsNotNone(variant)
        self.assertEqual(variant.sku, 'SHOE-RUN-01')
        self.assertEqual(float(variant.price), 1499.00)
        self.assertEqual(float(variant.stock_qty), 10.00)

    def test_multi_variant_product_post(self):
        # Create select attributes
        color_attr = Attribute.objects.create(
            vendor=self.vendor_a,
            name="Color",
            code="color",
            type="select"
        )
        size_attr = Attribute.objects.create(
            vendor=self.vendor_a,
            name="Size",
            code="size",
            type="select"
        )

        # Post to create product with 2 variants
        url = reverse('catalog:product_create')
        data = {
            'name': 'Polo T-Shirt',
            'slug': 'polo-tshirt',
            'description': 'Dynamic product description',
            'status': 'published',
            'has_variants': 'true',
            'variant_sku[]': ['POLO-RED-L', 'POLO-BLK-M'],
            'variant_price[]': ['799.00', '899.00'],
            'variant_compare_at_price[]': ['', '999.00'],
            'variant_stock_qty[]': ['5.00', '15.00'],
            'variant_attributes_json[]': [
                '{"color":"Red","size":"L"}',
                '{"color":"Black","size":"M"}'
            ]
        }

        response = self.client_a.post(url, data)
        self.assertEqual(response.status_code, 302)

        # Verify product and variants
        product = Product.objects.get(vendor=self.vendor_a, slug='polo-tshirt')
        self.assertTrue(product.has_variants)
        self.assertEqual(product.variants.count(), 2)

        v1 = product.variants.get(sku='POLO-RED-L')
        self.assertEqual(float(v1.price), 799.00)
        self.assertEqual(v1.attributes_data, {"color": "Red", "size": "L"})

        v2 = product.variants.get(sku='POLO-BLK-M')
        self.assertEqual(float(v2.price), 899.00)
        self.assertEqual(v2.attributes_data, {"color": "Black", "size": "M"})

    def test_multi_tenant_isolation(self):
        # Vendor A creates a category
        cat_a = Category.objects.create(
            vendor=self.vendor_a,
            name="Category A",
            slug="category-a"
        )
        # Vendor B creates a category
        cat_b = Category.objects.create(
            vendor=self.vendor_b,
            name="Category B",
            slug="category-b"
        )

        # Client A requests Categories List
        url = reverse('catalog:category_list')
        response_a = self.client_a.get(url)
        
        # Verify Vendor A only sees Category A
        self.assertIn(cat_a, response_a.context['categories'])
        self.assertNotIn(cat_b, response_a.context['categories'])

        # Client B requests Categories List
        response_b = self.client_b.get(url)
        
        # Verify Vendor B only sees Category B
        self.assertIn(cat_b, response_b.context['categories'])
        self.assertNotIn(cat_a, response_b.context['categories'])

    def test_product_creation_with_gallery_images(self):
        """
        Verify creating a product with multiple gallery images.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile
        # Mock image files
        img1 = SimpleUploadedFile("image1.jpg", b"file_content_1", content_type="image/jpeg")
        img2 = SimpleUploadedFile("image2.jpg", b"file_content_2", content_type="image/jpeg")

        url = reverse('catalog:product_create')
        data = {
            'name': 'Fudge Cake',
            'slug': 'fudge-cake',
            'status': 'published',
            'has_variants': 'false',
            'sku': 'FUDGE-01',
            'price': '450.00',
            'stock_qty': '10.00',
            'gallery_images': [img1, img2]
        }
        response = self.client_a.post(url, data)
        self.assertEqual(response.status_code, 302)

        product = Product.objects.get(vendor=self.vendor_a, slug='fudge-cake')
        self.assertEqual(product.images.count(), 2)
        self.assertTrue(product.images.filter(image__contains='image1').exists())
        self.assertTrue(product.images.filter(image__contains='image2').exists())

    def test_product_edit_gallery_images(self):
        """
        Verify editing a product to add new gallery images and delete existing ones.
        """
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import ProductImage
        
        product = Product.objects.create(
            vendor=self.vendor_a,
            name='Brownie',
            slug='brownie',
            status='published'
        )
        # Pre-create a gallery image object
        img_obj = ProductImage.objects.create(
            product=product,
            image='products/gallery/dummy.jpg'
        )

        self.assertEqual(product.images.count(), 1)

        # Edit view post: delete first image and add a new one
        url = reverse('catalog:product_edit', kwargs={'product_id': product.id})
        new_img = SimpleUploadedFile("new_img.jpg", b"new_file_content", content_type="image/jpeg")
        data = {
            'name': 'Brownie Deluxe',
            'slug': 'brownie-deluxe',
            'status': 'published',
            'has_variants': 'false',
            'sku': 'BROWNIE-01',
            'price': '50.00',
            'stock_qty': '10.00',
            'delete_images[]': [img_obj.id],
            'gallery_images': [new_img]
        }
        response = self.client_a.post(url, data)
        self.assertEqual(response.status_code, 302)

        product.refresh_from_db()
        self.assertEqual(product.name, 'Brownie Deluxe')
        self.assertEqual(product.images.count(), 1)
        self.assertFalse(ProductImage.objects.filter(pk=img_obj.id).exists())
        self.assertTrue(product.images.filter(image__contains='new_img').exists())
