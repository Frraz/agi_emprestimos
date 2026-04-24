from django.contrib import admin
from customers.infrastructure.models import Cliente, DocumentoCliente


class DocumentoClienteInline(admin.TabularInline):
    model = DocumentoCliente
    extra = 0
    fields = ['tipo', 'arquivo', 'descricao']


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = [
        'nome', 'cpf', 'telefone_principal',
        'classificacao', 'cidade', 'estado',
        'created_at', 'deleted_at',
    ]
    list_filter = ['classificacao', 'origem', 'estado', 'deleted_at']
    search_fields = ['nome', 'cpf', 'telefone_principal', 'email']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [DocumentoClienteInline]
    fieldsets = (
        ('Dados Pessoais', {
            'fields': ('id', 'nome', 'cpf', 'rg', 'data_nascimento', 'foto')
        }),
        ('Contato', {
            'fields': ('telefone_principal', 'telefone_secundario', 'email')
        }),
        ('Endereço', {
            'fields': ('cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'estado'),
            'classes': ('collapse',),
        }),
        ('Análise', {
            'fields': ('classificacao', 'perfil_psicologico', 'observacoes',
                       'origem', 'indicador', 'redes_sociais'),
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at', 'deleted_at'),
            'classes': ('collapse',),
        }),
    )