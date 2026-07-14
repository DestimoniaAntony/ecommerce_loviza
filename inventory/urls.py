from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Suppliers
    path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/create/', views.SupplierCreateView.as_view(), name='supplier_create'),
    path('suppliers/<int:supplier_id>/edit/', views.SupplierUpdateView.as_view(), name='supplier_edit'),
    path('suppliers/<int:supplier_id>/delete/', views.SupplierDeleteView.as_view(), name='supplier_delete'),

    # Branch Inventory Stocks
    path('stock/', views.BranchInventoryListView.as_view(), name='branch_inventory_list'),
    path('stock/adjust/', views.BranchInventoryAdjustmentView.as_view(), name='branch_inventory_adjust'),

    # Purchase Orders
    path('purchase-orders/', views.PurchaseOrderListView.as_view(), name='purchase_order_list'),
    path('purchase-orders/create/', views.PurchaseOrderCreateView.as_view(), name='purchase_order_create'),
    path('purchase-orders/<int:po_id>/', views.PurchaseOrderDetailView.as_view(), name='purchase_order_detail'),
    path('purchase-orders/<int:po_id>/status-update/', views.PurchaseOrderStatusUpdateView.as_view(), name='purchase_order_status_update'),

    # Stock Transfers
    path('transfers/', views.StockTransferListView.as_view(), name='stock_transfer_list'),
    path('transfers/create/', views.StockTransferCreateView.as_view(), name='stock_transfer_create'),
    path('transfers/<int:transfer_id>/', views.StockTransferDetailView.as_view(), name='stock_transfer_detail'),
    path('transfers/<int:transfer_id>/status-update/', views.StockTransferStatusUpdateView.as_view(), name='stock_transfer_status_update'),
]
