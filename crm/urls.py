from django.urls import path
from . import views

app_name = 'crm'

urlpatterns = [
    # Coupons CRUD
    path('coupons/', views.CouponListView.as_view(), name='coupon_list'),
    path('coupons/create/', views.CouponCreateView.as_view(), name='coupon_create'),
    path('coupons/<int:pk>/edit/', views.CouponEditView.as_view(), name='coupon_edit'),
    path('coupons/<int:pk>/delete/', views.CouponDeleteView.as_view(), name='coupon_delete'),

    # Loyalty settings
    path('loyalty/', views.LoyaltySettingsView.as_view(), name='loyalty_settings'),

    # Customer Profiles & CRM
    path('customers/', views.CRMCustomerListView.as_view(), name='customer_list'),
    path('customers/<int:pk>/', views.CRMCustomerDetailView.as_view(), name='customer_detail'),
    path('customers/<int:pk>/wallet/', views.CRMWalletAdjustmentView.as_view(), name='wallet_adjustment'),
    path('customers/<int:pk>/loyalty/', views.CRMLoyaltyAdjustmentView.as_view(), name='loyalty_adjustment'),

    # Contact Messages
    path('messages/', views.ContactMessageListView.as_view(), name='message_list'),

    # Newsletter Subscribers
    path('subscribers/', views.NewsletterSubscriberListView.as_view(), name='subscriber_list'),
]
