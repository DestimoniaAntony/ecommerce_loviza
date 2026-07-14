from django.contrib import admin
from .models import ContactMessage

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'vendor', 'email', 'phone', 'is_read', 'created_at')
    list_filter = ('is_read', 'vendor', 'created_at')
    search_fields = ('name', 'email', 'message')
    readonly_fields = ('created_at',)
