from django.contrib import admin
from payments.infrastructure.models import Pagamento


@admin.register(Pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = [
        'emprestimo', 'valor', 'tipo', 'data_pagamento',
        'valor_juros_pagos', 'valor_capital_pago',
        'capital_antes', 'capital_depois',
    ]
    list_filter = ['tipo', 'data_pagamento']
    search_fields = ['emprestimo__cliente__nome']
    readonly_fields = [f.name for f in Pagamento._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False