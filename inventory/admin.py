from django.contrib import admin
from .models import (
    Supplier, BranchInventory, StockAdjustmentLog,
    PurchaseOrder, PurchaseOrderItem, StockTransfer, StockTransferItem
)

admin.site.register(Supplier)
admin.site.register(BranchInventory)
admin.site.register(StockAdjustmentLog)
admin.site.register(PurchaseOrder)
admin.site.register(PurchaseOrderItem)
admin.site.register(StockTransfer)
admin.site.register(StockTransferItem)
