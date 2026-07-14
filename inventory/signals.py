from django.db.models import Sum
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from catalog.models import ProductVariant
from branches.models import Branch
from .models import BranchInventory

# Guards to prevent infinite recursion loop
_bi_syncing = False
_variant_syncing = False


@receiver(post_save, sender=BranchInventory)
@receiver(post_delete, sender=BranchInventory)
def update_product_variant_stock(sender, instance, **kwargs):
    """
    When branch inventory changes, update the ProductVariant's cached stock_qty.
    """
    global _bi_syncing, _variant_syncing
    if _bi_syncing or _variant_syncing:
        return

    _bi_syncing = True
    try:
        variant = instance.product_variant
        total = BranchInventory.objects.filter(product_variant=variant).aggregate(
            total=Sum('stock_qty')
        )['total'] or 0.00
        variant.stock_qty = total
        variant.save(update_fields=['stock_qty'])
    finally:
        _bi_syncing = False


@receiver(post_save, sender=ProductVariant)
def sync_variant_stock_to_branch(sender, instance, created, **kwargs):
    """
    When a product variant is saved (created or updated), ensure its stock
    is synced with the vendor's main branch inventory.
    """
    global _bi_syncing, _variant_syncing
    if _bi_syncing or _variant_syncing:
        return

    _variant_syncing = True
    try:
        vendor = instance.product.vendor
        main_branch = Branch.objects.filter(vendor=vendor, is_main_branch=True, is_active=True).first()
        if not main_branch:
            main_branch = Branch.objects.filter(vendor=vendor, is_active=True).first()

        if main_branch:
            if created:
                BranchInventory.objects.get_or_create(
                    branch=main_branch,
                    product_variant=instance,
                    defaults={'stock_qty': instance.stock_qty}
                )
            else:
                bi, bi_created = BranchInventory.objects.get_or_create(
                    branch=main_branch,
                    product_variant=instance,
                    defaults={'stock_qty': instance.stock_qty}
                )
                if not bi_created:
                    # Calculate total of other branches
                    total_others = BranchInventory.objects.filter(
                        product_variant=instance
                    ).exclude(id=bi.id).aggregate(total=Sum('stock_qty'))['total'] or 0.00

                    expected_main_stock = instance.stock_qty - total_others
                    if bi.stock_qty != expected_main_stock:
                        bi.stock_qty = expected_main_stock
                        bi.save(update_fields=['stock_qty'])
    except Exception:
        pass
    finally:
        _variant_syncing = False
