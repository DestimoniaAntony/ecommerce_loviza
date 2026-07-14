"""
Management command: seed_plans
Creates the default CommerceHub subscription plans.
Run: python manage.py seed_plans
"""
from django.core.management.base import BaseCommand
from tenants.models import SubscriptionPlan


class Command(BaseCommand):
    help = 'Seed default subscription plans for CommerceHub'

    def handle(self, *args, **options):
        plans = [
            {
                'name': 'Trial',
                'plan_type': 'trial',
                'price': 0,
                'annual_price': 0,
                'trial_days': 14,
                'description': '14-day free trial with all Standard features.',
                'sort_order': 0,
                'max_products': 50,
                'max_branches': 1,
                'max_staff': 2,
                'max_monthly_orders': 100,
                'has_whatsapp': False,
                'has_loyalty': False,
                'has_crm': False,
                'has_marketing': False,
                'has_api_access': False,
                'has_white_label': False,
                'has_custom_domain': False,
                'has_advanced_reports': False,
            },
            {
                'name': 'Starter',
                'plan_type': 'starter',
                'price': 999,
                'annual_price': 9990,
                'trial_days': 0,
                'description': 'For small single-store businesses just getting started.',
                'sort_order': 1,
                'max_products': 200,
                'max_branches': 1,
                'max_staff': 5,
                'max_monthly_orders': 500,
                'has_whatsapp': True,
                'has_loyalty': False,
                'has_crm': False,
                'has_marketing': False,
                'has_api_access': False,
                'has_white_label': False,
                'has_custom_domain': False,
                'has_advanced_reports': False,
            },
            {
                'name': 'Standard',
                'plan_type': 'standard',
                'price': 2499,
                'annual_price': 24990,
                'trial_days': 0,
                'description': 'For growing businesses with multiple branches and staff.',
                'sort_order': 2,
                'max_products': 1000,
                'max_branches': 3,
                'max_staff': 15,
                'max_monthly_orders': 2000,
                'has_whatsapp': True,
                'has_loyalty': True,
                'has_crm': True,
                'has_marketing': False,
                'has_api_access': False,
                'has_white_label': False,
                'has_custom_domain': False,
                'has_advanced_reports': True,
            },
            {
                'name': 'Professional',
                'plan_type': 'professional',
                'price': 5999,
                'annual_price': 59990,
                'trial_days': 0,
                'description': 'For established businesses needing marketing and API access.',
                'sort_order': 3,
                'max_products': 5000,
                'max_branches': 10,
                'max_staff': 50,
                'max_monthly_orders': 10000,
                'has_whatsapp': True,
                'has_loyalty': True,
                'has_crm': True,
                'has_marketing': True,
                'has_api_access': True,
                'has_white_label': False,
                'has_custom_domain': True,
                'has_advanced_reports': True,
            },
            {
                'name': 'Enterprise',
                'plan_type': 'enterprise',
                'price': 14999,
                'annual_price': 149990,
                'trial_days': 0,
                'description': 'Full-featured platform with white label, custom domain, and unlimited scale.',
                'sort_order': 4,
                'max_products': 999999,
                'max_branches': 999,
                'max_staff': 999,
                'max_monthly_orders': 999999,
                'has_whatsapp': True,
                'has_loyalty': True,
                'has_crm': True,
                'has_marketing': True,
                'has_api_access': True,
                'has_white_label': True,
                'has_custom_domain': True,
                'has_advanced_reports': True,
            },
        ]

        created = 0
        updated = 0
        for plan_data in plans:
            plan_type = plan_data.pop('plan_type')
            obj, is_created = SubscriptionPlan.objects.update_or_create(
                plan_type=plan_type,
                defaults=plan_data,
            )
            if is_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  [OK] Created plan: {obj.name}'))
            else:
                updated += 1
                self.stdout.write(f'  [updated] plan: {obj.name}')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! {created} plan(s) created, {updated} plan(s) updated.'
        ))
