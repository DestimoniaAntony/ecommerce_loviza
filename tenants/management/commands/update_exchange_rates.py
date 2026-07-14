import json
import urllib.request
from django.core.management.base import BaseCommand
from tenants.models import Vendor, SupportedCurrency
from decimal import Decimal

class Command(BaseCommand):
    help = 'Fetches the latest exchange rates for all active supported currencies across vendors.'

    def handle(self, *args, **options):
        vendors = Vendor.objects.filter(is_active=True, supported_currencies__is_active=True).distinct()
        
        if not vendors.exists():
            self.stdout.write(self.style.WARNING('No active vendors with active supported currencies found.'))
            return
            
        for vendor in vendors:
            base_currency = vendor.currency.upper()
            try:
                url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response:
                    data = json.loads(response.read().decode())
                
                rates = data.get('rates', {})
                if not rates:
                    self.stdout.write(self.style.ERROR(f"No rates found for {base_currency}"))
                    continue
                    
                currencies = vendor.supported_currencies.filter(is_active=True)
                updated_count = 0
                for cur in currencies:
                    rate = rates.get(cur.code.upper())
                    if rate:
                        cur.exchange_rate = Decimal(str(rate))
                        cur.save(update_fields=['exchange_rate'])
                        updated_count += 1
                        
                self.stdout.write(self.style.SUCCESS(f"Updated {updated_count} currencies for {vendor.business_name} ({base_currency})"))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error updating currencies for {vendor.business_name}: {str(e)}"))
