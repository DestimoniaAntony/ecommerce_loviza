from django.urls import path
from . import views

app_name = 'adminapp'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),

    # Vendor Management
    path('vendors/', views.VendorListView.as_view(), name='vendor_list'),
    path('vendors/create/', views.VendorCreateView.as_view(), name='vendor_create'),
    path('vendors/<int:vendor_id>/', views.VendorDetailView.as_view(), name='vendor_detail'),
    path('vendors/<int:vendor_id>/edit/', views.VendorEditView.as_view(), name='vendor_edit'),
    path('vendors/<int:vendor_id>/approve/', views.VendorApproveView.as_view(), name='vendor_approve'),
    path('vendors/<int:vendor_id>/suspend/', views.VendorSuspendView.as_view(), name='vendor_suspend'),

    # Subscription Plans
    path('plans/', views.PlanListView.as_view(), name='plan_list'),
    path('plans/create/', views.PlanCreateView.as_view(), name='plan_create'),
    path('plans/<int:plan_id>/edit/', views.PlanEditView.as_view(), name='plan_edit'),
]
