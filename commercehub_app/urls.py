from django.urls import path
from . import views

app_name = 'commercehub_app'

urlpatterns = [
    path('dashboard/', views.VendorDashboardView.as_view(), name='dashboard'),
    path('settings/', views.VendorSettingsView.as_view(), name='settings'),
    path('orders/', views.VendorOrderListView.as_view(), name='order_list'),
    path('orders/<int:pk>/', views.VendorOrderDetailView.as_view(), name='order_detail'),
    path('orders/<int:pk>/action/', views.VendorOrderActionView.as_view(), name='order_action'),
    path('email-settings/', views.VendorEmailSettingsView.as_view(), name='email_settings'),
    
    # Carousel Settings
    path('settings/carousel/', views.VendorCarouselListView.as_view(), name='carousel_list'),
    path('settings/carousel/create/', views.VendorCarouselCreateView.as_view(), name='carousel_create'),
    path('settings/carousel/<int:pk>/edit/', views.VendorCarouselEditView.as_view(), name='carousel_edit'),
    path('settings/carousel/<int:pk>/delete/', views.VendorCarouselDeleteView.as_view(), name='carousel_delete'),

    # Analytics CSV Exports
    path('analytics/export/products/', views.ExportTopProductsView.as_view(), name='export_products'),
    path('analytics/export/orders/', views.ExportOrdersView.as_view(), name='export_orders'),
]
