"""
Tenant Middleware — CommerceHub Single-Tenant Architecture with Franchise Support

Identifies the current tenant (vendor) on every request via:
  1. Default: The main brand vendor (the vendor with no parent franchise).
  2. Franchise Path: /f/<franchise_slug>/
  3. Franchise Subdomain: <franchise_slug>.domain.com

Injects:
  request.tenant  → Vendor object
"""
from django.utils.deprecation import MiddlewareMixin
import re

class TenantMiddleware(MiddlewareMixin):
    """
    Identifies and attaches the current vendor (tenant) to every request.
    Uses SCRIPT_NAME to seamlessly support path-based franchise routing.
    """

    def process_request(self, request):
        from tenants.models import Vendor
        
        request.tenant = None
        
        # 1. Determine the Main Vendor (the brand owner - not a franchise child)
        main_vendor = Vendor.objects.filter(is_active=True, status='approved', franchise_details__isnull=True).first()
        # Fallback to any active vendor if no franchise setup exists
        if not main_vendor:
            main_vendor = Vendor.objects.filter(is_active=True, status='approved').first()

        host = request.get_host().split(':')[0].lower()
        subdomain = host.split('.')[0] if '.' in host else None
        
        path_info = request.path_info
        franchise_slug_from_path = None
        
        # Check path for /f/<slug>/ pattern
        match = re.match(r'^/f/([^/]+)(/.*)?$', path_info)
        if match:
            franchise_slug_from_path = match.group(1)
            
        franchise_slug = franchise_slug_from_path or subdomain
        
        if franchise_slug:
            try:
                # Check if this slug belongs to an active vendor
                franchise = Vendor.objects.get(slug=franchise_slug, is_active=True, status='approved')
                request.tenant = franchise
                
                # If identified via path, rewrite PATH_INFO and SCRIPT_NAME
                # This ensures URL routing works seamlessly and reverse() prepends the prefix
                if franchise_slug_from_path:
                    prefix = f'/f/{franchise_slug_from_path}'
                    request.path_info = path_info[len(prefix):] or '/'
                    request.META['SCRIPT_NAME'] = request.META.get('SCRIPT_NAME', '') + prefix
            except Vendor.DoesNotExist:
                request.tenant = main_vendor
        else:
            request.tenant = main_vendor

import logging
import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

COUNTRY_CURRENCY_MAP = {
    'AF': 'AFN', 'AL': 'ALL', 'DZ': 'DZD', 'AS': 'USD', 'AD': 'EUR', 'AO': 'AOA', 'AI': 'XCD',
    'AQ': 'XCD', 'AG': 'XCD', 'AR': 'ARS', 'AM': 'AMD', 'AW': 'AWG', 'AU': 'AUD', 'AT': 'EUR',
    'AZ': 'AZN', 'BS': 'BSD', 'BH': 'BHD', 'BD': 'BDT', 'BB': 'BBD', 'BY': 'BYN', 'BE': 'EUR',
    'BZ': 'BZD', 'BJ': 'XOF', 'BM': 'BMD', 'BT': 'BTN', 'BO': 'BOB', 'BA': 'BAM', 'BW': 'BWP',
    'BV': 'NOK', 'BR': 'BRL', 'IO': 'USD', 'BN': 'BND', 'BG': 'BGN', 'BF': 'XOF', 'BI': 'BIF',
    'KH': 'KHR', 'CM': 'XAF', 'CA': 'CAD', 'CV': 'CVE', 'KY': 'KYD', 'CF': 'XAF', 'TD': 'XAF',
    'CL': 'CLP', 'CN': 'CNY', 'CX': 'AUD', 'CC': 'AUD', 'CO': 'COP', 'KM': 'KMF', 'CG': 'XAF',
    'CD': 'CDF', 'CK': 'NZD', 'CR': 'CRC', 'CI': 'XOF', 'HR': 'EUR', 'CU': 'CUP', 'CY': 'EUR',
    'CZ': 'CZK', 'DK': 'DKK', 'DJ': 'DJF', 'DM': 'XCD', 'DO': 'DOP', 'EC': 'USD', 'EG': 'EGP',
    'SV': 'USD', 'GQ': 'XAF', 'ER': 'ERN', 'EE': 'EUR', 'ET': 'ETB', 'FK': 'FKP', 'FO': 'DKK',
    'FJ': 'FJD', 'FI': 'EUR', 'FR': 'EUR', 'GF': 'EUR', 'PF': 'XPF', 'TF': 'EUR', 'GA': 'XAF',
    'GM': 'GMD', 'GE': 'GEL', 'DE': 'EUR', 'GH': 'GHS', 'GI': 'GIP', 'GR': 'EUR', 'GL': 'DKK',
    'GD': 'XCD', 'GP': 'EUR', 'GU': 'USD', 'GT': 'GTQ', 'GN': 'GNF', 'GW': 'XOF', 'GY': 'GYD',
    'HT': 'HTG', 'HM': 'AUD', 'VA': 'EUR', 'HN': 'HNL', 'HK': 'HKD', 'HU': 'HUF', 'IS': 'ISK',
    'IN': 'INR', 'ID': 'IDR', 'IR': 'IRR', 'IQ': 'IQD', 'IE': 'EUR', 'IL': 'ILS', 'IT': 'EUR',
    'JM': 'JMD', 'JP': 'JPY', 'JO': 'JOD', 'KZ': 'KZT', 'KE': 'KES', 'KI': 'AUD', 'KP': 'KPW',
    'KR': 'KRW', 'KW': 'KWD', 'KG': 'KGS', 'LA': 'LAK', 'LV': 'EUR', 'LB': 'LBP', 'LS': 'ZAR',
    'LR': 'LRD', 'LY': 'LYD', 'LI': 'CHF', 'LT': 'EUR', 'LU': 'EUR', 'MO': 'MOP', 'MK': 'MKD',
    'MG': 'MGA', 'MW': 'MWK', 'MY': 'MYR', 'MV': 'MVR', 'ML': 'XOF', 'MT': 'EUR', 'MH': 'USD',
    'MQ': 'EUR', 'MR': 'MRU', 'MU': 'MUR', 'YT': 'EUR', 'MX': 'MXN', 'FM': 'USD', 'MD': 'MDL',
    'MC': 'EUR', 'MN': 'MNT', 'MS': 'XCD', 'MA': 'MAD', 'MZ': 'MZN', 'MM': 'MMK', 'NA': 'NAD',
    'NR': 'AUD', 'NP': 'NPR', 'NL': 'EUR', 'NC': 'XPF', 'NZ': 'NZD', 'NI': 'NIO', 'NE': 'XOF',
    'NG': 'NGN', 'NU': 'NZD', 'NF': 'AUD', 'MP': 'USD', 'NO': 'NOK', 'OM': 'OMR', 'PK': 'PKR',
    'PW': 'USD', 'PA': 'PAB', 'PG': 'PGK', 'PY': 'PYG', 'PE': 'PEN', 'PH': 'PHP', 'PN': 'NZD',
    'PL': 'PLN', 'PT': 'EUR', 'PR': 'USD', 'QA': 'QAR', 'RE': 'EUR', 'RO': 'RON', 'RU': 'RUB',
    'RW': 'RWF', 'SH': 'SHP', 'KN': 'XCD', 'LC': 'XCD', 'PM': 'EUR', 'VC': 'XCD', 'WS': 'WST',
    'SM': 'EUR', 'ST': 'STN', 'SA': 'SAR', 'SN': 'XOF', 'CS': 'RSD', 'SC': 'SCR', 'SL': 'SLL',
    'SG': 'SGD', 'SK': 'EUR', 'SI': 'EUR', 'SB': 'SBD', 'SO': 'SOS', 'ZA': 'ZAR', 'GS': 'GBP',
    'ES': 'EUR', 'LK': 'LKR', 'SD': 'SDG', 'SR': 'SRD', 'SJ': 'NOK', 'SZ': 'SZL', 'SE': 'SEK',
    'CH': 'CHF', 'SY': 'SYP', 'TW': 'TWD', 'TJ': 'TJS', 'TZ': 'TZS', 'TH': 'THB', 'TL': 'USD',
    'TG': 'XOF', 'TK': 'NZD', 'TO': 'TOP', 'TT': 'TTD', 'TN': 'TND', 'TR': 'TRY', 'TM': 'TMT',
    'TC': 'USD', 'TV': 'AUD', 'UG': 'UGX', 'UA': 'UAH', 'AE': 'AED', 'GB': 'GBP', 'US': 'USD',
    'UM': 'USD', 'UY': 'UYU', 'UZ': 'UZS', 'VU': 'VUV', 'VE': 'VES', 'VN': 'VND', 'VG': 'USD',
    'VI': 'USD', 'WF': 'XPF', 'EH': 'MAD', 'YE': 'YER', 'ZM': 'ZMW', 'ZW': 'ZWL',
    'RS': 'RSD', 'ME': 'EUR', 'XK': 'EUR',
}

class GeoCurrencyMiddleware(MiddlewareMixin):
    """
    Automatically sets the user's default currency based on their IP address
    on their first visit, supporting Cloudflare headers and a fast API fallback.
    """
    def process_request(self, request):
        # Only set if not already selected by the user
        if request.session.get('currency_code'):
            return

        if not hasattr(request, 'tenant') or not request.tenant:
            return

        # Extract Client IP
        ip = request.META.get('HTTP_CF_CONNECTING_IP')
        if not ip:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')
                
        # Skip local/private IPs in dev
        if not ip or ip in ('127.0.0.1', 'localhost', '::1'):
            return
            
        country_code = None

        # 1. Cloudflare IPCountry header (Fastest, 0 latency)
        cf_country = request.META.get('HTTP_CF_IPCOUNTRY')
        if cf_country and cf_country != 'XX':
            country_code = cf_country

        # 2. Fallback to free GeoJS API with caching
        if not country_code:
            cache_key = f'geoip_country_{ip}'
            country_code = cache.get(cache_key)
            if not country_code:
                try:
                    resp = requests.get(f'https://get.geojs.io/v1/ip/country/{ip}.json', timeout=2)
                    if resp.status_code == 200:
                        country_code = resp.json().get('country')
                        if country_code:
                            cache.set(cache_key, country_code, 86400 * 7) # Cache for 7 days
                except Exception as e:
                    logger.error(f"GeoIP fallback failed for {ip}: {e}")

        # Set default currency if mapped and supported by tenant
        if country_code:
            target_currency = COUNTRY_CURRENCY_MAP.get(country_code.upper())
            if target_currency:
                is_supported = request.tenant.supported_currencies.filter(
                    code=target_currency, is_active=True
                ).exists()
                if is_supported:
                    request.session['currency_code'] = target_currency


from django.utils import timezone

class TimezoneMiddleware(MiddlewareMixin):
    """
    Sets the active timezone based on the user's session.
    If no timezone is set, falls back to IP geolocation to find and set it.
    """
    def process_request(self, request):
        tzname = request.session.get('django_timezone')
        
        if not tzname:
            # Extract Client IP
            ip = request.META.get('HTTP_CF_CONNECTING_IP')
            if not ip:
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip = x_forwarded_for.split(',')[0].strip()
                else:
                    ip = request.META.get('REMOTE_ADDR')
                    
            if ip and ip not in ('127.0.0.1', 'localhost', '::1'):
                cache_key = f'geoip_tz_{ip}'
                tzname = cache.get(cache_key)
                
                if not tzname:
                    try:
                        resp = requests.get(f'https://get.geojs.io/v1/ip/geo/{ip}.json', timeout=2)
                        if resp.status_code == 200:
                            tzname = resp.json().get('timezone')
                            if tzname:
                                cache.set(cache_key, tzname, 86400 * 7) # Cache for 7 days
                    except Exception as e:
                        logger.error(f"GeoIP TZ fallback failed for {ip}: {e}")
                        
                if tzname:
                    request.session['django_timezone'] = tzname

        if tzname:
            try:
                timezone.activate(tzname)
            except Exception:
                timezone.deactivate()
        else:
            timezone.deactivate()


