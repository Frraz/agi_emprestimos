from django.contrib import admin
from audit.infrastructure.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'content_type', 'object_id', 'usuario', 'created_at']
    list_filter = ['action', 'content_type']
    search_fields = ['object_id', 'usuario__username']
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False