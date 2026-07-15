from django.urls import path
from . import views
from crm.views import CouponApplyView

app_name = 'storefront'

urlpatterns = [
    # Browsing
    path('', views.StorefrontHomeView.as_view(), name='home'),
    path('collections/', views.CollectionsListView.as_view(), name='collections'),
    path('catalog/', views.ProductCatalogView.as_view(), name='catalog'),
    path('api/search/', views.StorefrontSearchAPIView.as_view(), name='api_search'),
    path('product/<slug:slug>/', views.ProductDetailView.as_view(), name='product_detail'),
    path('contact/', views.ContactView.as_view(), name='contact'),
    
    # Static Pages
    path('pages/privacy-policy/', views.PrivacyPolicyView.as_view(), name='privacy_policy'),
    path('pages/returns-and-refunds/', views.ReturnsRefundsView.as_view(), name='returns_refunds'),
    path('pages/shipping-delivery/', views.ShippingDeliveryView.as_view(), name='shipping_delivery'),
    path('pages/terms-of-service/', views.TermsOfServiceView.as_view(), name='terms_of_service'),
    path('pages/about-us/', views.AboutUsView.as_view(), name='about_us'),

    # Newsletter
    path('subscribe/', views.NewsletterSubscriptionView.as_view(), name='subscribe'),

    # Cart operations
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/add/', views.CartAddView.as_view(), name='cart_add'),
    path('cart/update/', views.CartUpdateView.as_view(), name='cart_update'),
    path('cart/remove/', views.CartRemoveView.as_view(), name='cart_remove'),
    path('cart/note/', views.CartNoteUpdateView.as_view(), name='cart_note_update'),
    path('cart/coupon/apply/', CouponApplyView.as_view(), name='coupon_apply'),

    # Customer Authentication
    path('login/', views.CustomerLoginView.as_view(), name='login'),
    path('register/', views.CustomerRegisterView.as_view(), name='register'),
    path('logout/', views.CustomerLogoutView.as_view(), name='logout'),
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot_password'),

    # Checkout & Orders
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('checkout/place/', views.PlaceOrderView.as_view(), name='place_order'),
    path('checkout/verify-payment/', views.PaymentVerifyView.as_view(), name='verify_payment'),
    path('checkout/stripe/webhook/', views.StripeWebhookView.as_view(), name='stripe_webhook'),
    path('order/<int:order_id>/success/', views.OrderSuccessView.as_view(), name='order_success'),

    # Customer Dashboard
    path('profile/', views.CustomerProfileView.as_view(), name='profile'),
    path('profile/password-reset/', views.CustomerPasswordResetView.as_view(), name='password_reset'),
    path('profile/address/create/', views.CustomerAddressCreateView.as_view(), name='address_create'),
    
    # Currency
    path('set-currency/', views.SetCurrencyView.as_view(), name='set_currency'),
]
