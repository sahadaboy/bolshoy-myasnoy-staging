from django.db import models


class CustomerCart(models.Model):
    customer = models.OneToOneField('storefront.Customer', on_delete=models.CASCADE, related_name='cart')
    revision = models.PositiveBigIntegerField(default=0)
    items = models.JSONField(default=dict)  # Product IDs -> quantities; never prices.
    updated_at = models.DateTimeField(auto_now=True)


class CartOperation(models.Model):
    cart = models.ForeignKey(CustomerCart, on_delete=models.CASCADE, related_name='operations')
    operation_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['cart', 'operation_id'], name='unique_cart_operation')]
