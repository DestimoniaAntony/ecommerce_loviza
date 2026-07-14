from django.contrib import admin
from .models import Vendor, SubscriptionPlan, VendorSubscription


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'plan_type', 'price', 'annual_price', 'is_active', 'sort_order']
    list_filter = ['is_active', 'plan_type']
    ordering = ['sort_order']


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ['business_name', 'slug', 'phone', 'status', 'business_type', 'created_at']
    list_filter = ['status', 'business_type', 'is_active']
    search_fields = ['business_name', 'phone', 'email', 'slug']
    readonly_fields = ['created_at', 'updated_at', 'approved_at']


@admin.register(VendorSubscription)
class VendorSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['vendor', 'plan', 'start_date', 'end_date', 'is_active', 'is_trial']
    list_filter = ['is_active', 'is_trial']
    search_fields = ['vendor__business_name']

from .models import SupportedCurrency

@admin.register(SupportedCurrency)
class SupportedCurrencyAdmin(admin.ModelAdmin):
    list_display = ['vendor', 'code', 'symbol', 'exchange_rate', 'is_active']
    list_filter = ['is_active', 'vendor']
    search_fields = ['code', 'vendor__business_name']
