from django.core.management.base import BaseCommand
from tenants.models import Vendor, SupportedCurrency
from core.middleware import COUNTRY_CURRENCY_MAP

class Command(BaseCommand):
    help = 'Populates the database with all 150+ global currencies for active vendors.'

    def handle(self, *args, **options):
        vendors = Vendor.objects.filter(is_active=True, status='approved')
        if not vendors.exists():
            self.stdout.write(self.style.ERROR('No active vendors found. Please create a vendor first.'))
            return
            
        unique_currencies = set(COUNTRY_CURRENCY_MAP.values())
        
        for vendor in vendors:
            existing_currencies = set(vendor.supported_currencies.values_list('code', flat=True))
            missing = unique_currencies - existing_currencies
            
            if not missing:
                self.stdout.write(self.style.SUCCESS(f'All currencies already exist for {vendor.business_name}.'))
                continue
                
            for code in missing:
                SupportedCurrency.objects.create(
                    vendor=vendor,
                    code=code,
                    symbol=code, # using code as symbol fallback
                    is_active=True
                )
            
            self.stdout.write(self.style.SUCCESS(f'Successfully added {len(missing)} missing currencies to {vendor.business_name}.'))
        
        self.stdout.write(self.style.SUCCESS('Finished global currency setup. Please run "python manage.py update_exchange_rates" next!'))
