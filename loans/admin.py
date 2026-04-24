from django.contrib import admin
from loans.infrastructure.models import Emprestimo, ParcelaEmprestimo


class ParcelaInline(admin.TabularInline):
    model = ParcelaEmprestimo
    extra = 0
    readonly_fields = [
        'numero', 'valor_parcela', 'valor_principal', 'valor_juros',
        'saldo_devedor_antes', 'saldo_devedor_depois',
        'data_vencimento', 'valor_pago', 'status', 'data_pagamento',
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Emprestimo)
class EmprestimoAdmin(admin.ModelAdmin):
    list_display = [
        'cliente', 'tipo', 'subtipo_parcelado',
        'capital_inicial', 'capital_atual', 'taxa_percentual_display',
        'status', 'data_inicio', 'data_vencimento',
    ]
    list_filter = ['tipo', 'status', 'subtipo_parcelado']
    search_fields = ['cliente__nome', 'cliente__cpf']
    readonly_fields = [
        'id', 'capital_atual', 'created_at', 'updated_at',
        'taxa_percentual_display', 'total_pago', 'total_garantias',
    ]
    inlines = [ParcelaInline]
    raw_id_fields = ['cliente', 'registrado_por']