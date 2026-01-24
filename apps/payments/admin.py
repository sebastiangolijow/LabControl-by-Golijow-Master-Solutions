"""Admin configuration for payments app."""

from config.admin import admin
from config.admin import admin_site

from .models import Invoice
from .models import Payment


class InvoiceAdmin(admin.ModelAdmin):
    """Admin interface for Invoice model."""

    list_display = [
        "invoice_number",
        "patient",
        "total_amount",
        "paid_amount",
        "status",
        "issue_date",
        "due_date",
    ]
    list_filter = ["status", "issue_date", "due_date"]
    search_fields = ["invoice_number", "patient__email"]
    ordering = ["-issue_date"]
    readonly_fields = ["created_at", "updated_at"]


class PaymentAdmin(admin.ModelAdmin):
    """Admin interface for Payment model."""

    list_display = [
        "transaction_id",
        "invoice",
        "amount",
        "payment_method",
        "status",
        "created_at",
    ]
    list_filter = ["status", "payment_method", "created_at"]
    search_fields = ["transaction_id", "invoice__invoice_number"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "completed_at"]


# Register with custom admin site
admin_site.register(Invoice, InvoiceAdmin)
admin_site.register(Payment, PaymentAdmin)
