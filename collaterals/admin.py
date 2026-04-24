from django.contrib import admin
from collaterals.infrastructure.models import Garantia, DocumentoGarantia


class DocumentoGarantiaInline(admin.TabularInline):
    model = DocumentoGarantia
    extra = 0


@admin.register(Garantia)
class GarantiaAdmin(admin.ModelAdmin):
    list_display = [
        'emprestimo', 'tipo', 'descricao',
        'valor_estimado', 'percentual_recuperacao',
    ]
    list_filter = ['tipo']
    search_fields = ['emprestimo__cliente__nome', 'descricao']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [DocumentoGarantiaInline]