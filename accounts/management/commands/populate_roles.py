from django.core.management.base import BaseCommand
from accounts.models import ModulePermission, Role


class Command(BaseCommand):
    help = 'Populate default permissions and system roles'

    def handle(self, *args, **kwargs):
        # 1. Define permissions
        permissions_data = [
            # Catalog/Products
            ('View Catalog', 'view_catalog', 'Can view products, categories, attributes, and brands.'),
            ('Manage Catalog', 'manage_catalog', 'Can create, edit, and delete products, categories, attributes, and brands.'),
            # Orders
            ('View Orders', 'view_orders', 'Can view store orders and transactions.'),
            ('Process Orders', 'process_orders', 'Can accept, update status, and manage refunds/returns on orders.'),
            # Customers
            ('View Customers', 'view_customers', 'Can view customer profiles and wallet details.'),
            ('Manage Customers', 'manage_customers', 'Can manage customer profiles, tier assignments, and wallet actions.'),
            # Branches
            ('View Branches', 'view_branches', 'Can view vendor branches and franchises.'),
            ('Manage Branches', 'manage_branches', 'Can add, edit, and deactivate vendor branches and franchises.'),
            # Staff
            ('View Staff', 'view_staff', 'Can view staff profiles and role assignments.'),
            ('Manage Staff', 'manage_staff', 'Can invite, edit, and deactivate staff members.'),
            # Roles
            ('View Roles', 'view_roles', 'Can view custom roles and permissions.'),
            ('Manage Roles', 'manage_roles', 'Can create, edit, and delete custom store roles.'),
            # Reports
            ('View Reports', 'view_reports', 'Can view financial, sales, inventory, and activity reports.'),
            # Settings
            ('View Settings', 'view_settings', 'Can view basic store settings.'),
            ('Manage Settings', 'manage_settings', 'Can edit store settings, visual themes, custom domain, and payment setups.'),
            # Inventory
            ('View Inventory', 'view_inventory', 'Can view branch inventory, suppliers, purchase orders, and stock transfers.'),
            ('Manage Inventory', 'manage_inventory', 'Can adjust stock levels, manage suppliers, process purchase orders, and handle stock transfers.'),
        ]

        perms_dict = {}
        for name, codename, description in permissions_data:
            perm, created = ModulePermission.objects.get_or_create(
                codename=codename,
                defaults={'name': name, 'description': description}
            )
            perms_dict[codename] = perm
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created permission: {codename}'))

        # 2. Define default system roles (vendor=None, is_custom=False)
        roles_data = [
            ('Administrator', 'Full access to all system modules and settings.', list(perms_dict.keys())),
            ('Manager', 'Can manage catalog, orders, customers, branches, and view reports, but cannot manage roles/settings.', [
                'view_catalog', 'manage_catalog',
                'view_orders', 'process_orders',
                'view_customers', 'manage_customers',
                'view_branches', 'manage_branches',
                'view_staff', 'manage_staff',
                'view_roles',
                'view_reports',
                'view_settings',
                'view_inventory',
                'manage_inventory',
            ]),
            ('Cashier', 'Can view catalog, view and process orders.', [
                'view_catalog',
                'view_orders', 'process_orders'
            ]),
            ('Delivery Staff', 'Can view assigned orders and update delivery status.', [
                'view_orders', 'process_orders'
            ]),
        ]

        for name, description, codenames in roles_data:
            role, created = Role.objects.get_or_create(
                vendor=None,
                name=name,
                defaults={'description': description, 'is_custom': False}
            )
            role_perms = [perms_dict[code] for code in codenames]
            role.permissions.set(role_perms)
            role.save()
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created default role: {name}'))
            else:
                self.stdout.write(f'Updated default role: {name}')
