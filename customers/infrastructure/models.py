from django.db import models
from core.models import BaseModel
from core.validators import validate_cpf


class Cliente(BaseModel):

    CLASSIFICACAO_CHOICES = [
        ('verde', '🟢 Bom Pagador'),
        ('amarelo', '🟡 Regular'),
        ('vermelho', '🔴 Mau Pagador'),
    ]

    ORIGEM_CHOICES = [
        ('indicacao', 'Indicação'),
        ('proprio', 'Prospecção Própria'),
        ('redes_sociais', 'Redes Sociais'),
        ('boato', 'Boato / Divulgação Informal'),
        ('outro', 'Outro'),
    ]

    ESTADO_CIVIL_CHOICES = [
        ('solteiro', 'Solteiro(a)'),
        ('casado', 'Casado(a)'),
        ('divorciado', 'Divorciado(a)'),
        ('viuvo', 'Viúvo(a)'),
        ('uniao_estavel', 'União Estável'),
    ]

    TIPO_RESIDENCIA_CHOICES = [
        ('propria', 'Própria'),
        ('alugada', 'Alugada'),
        ('familiar', 'Casa de Familiar'),
        ('financiada', 'Financiada'),
        ('outros', 'Outros'),
    ]

    # ── Dados pessoais ─────────────────────────────────────────────────────
    nome = models.CharField(max_length=200, db_index=True)
    cpf = models.CharField(
        max_length=14, unique=True, db_index=True, validators=[validate_cpf]
    )
    rg = models.CharField(max_length=30, blank=True, null=True)
    cnh = models.CharField(max_length=20, blank=True, null=True, verbose_name='CNH')
    data_nascimento = models.DateField(blank=True, null=True)
    foto = models.ImageField(upload_to='clientes/fotos/', blank=True, null=True)

    # ── Dados socioeconômicos ──────────────────────────────────────────────
    profissao = models.CharField(max_length=100, blank=True, null=True, verbose_name='Profissão')
    estado_civil = models.CharField(
        max_length=20, choices=ESTADO_CIVIL_CHOICES, blank=True, null=True
    )
    tipo_residencia = models.CharField(
        max_length=15, choices=TIPO_RESIDENCIA_CHOICES, blank=True, null=True
    )

    # ── Contato ────────────────────────────────────────────────────────────
    telefone_principal = models.CharField(max_length=20)
    telefone_secundario = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # ── Endereço ───────────────────────────────────────────────────────────
    cep = models.CharField(max_length=10, blank=True, null=True)
    logradouro = models.CharField(max_length=300, blank=True, null=True)
    numero = models.CharField(max_length=20, blank=True, null=True)
    complemento = models.CharField(max_length=100, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=2, blank=True, null=True)

    # ── Redes sociais ──────────────────────────────────────────────────────
    instagram = models.CharField(max_length=100, blank=True, null=True)
    facebook = models.CharField(max_length=100, blank=True, null=True)
    redes_sociais = models.JSONField(default=dict, blank=True)

    # ── Origem ─────────────────────────────────────────────────────────────
    origem = models.CharField(max_length=20, choices=ORIGEM_CHOICES, default='proprio')
    indicador = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='indicados',
    )

    # ── Análise de risco ───────────────────────────────────────────────────
    perfil_psicologico = models.TextField(blank=True, null=True)
    observacoes = models.TextField(blank=True, null=True)
    classificacao = models.CharField(
        max_length=10, choices=CLASSIFICACAO_CHOICES,
        default='verde', db_index=True,
    )

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        ordering = ['nome']
        indexes = [
            models.Index(fields=['classificacao', 'deleted_at']),
            models.Index(fields=['cidade', 'estado']),
        ]

    def __str__(self):
        return f"{self.nome} ({self.cpf})"

    @property
    def tem_emprestimo_ativo(self) -> bool:
        return self.emprestimos.filter(
            status__in=['ativo', 'inadimplente'],
            deleted_at__isnull=True,
        ).exists()

    @property
    def saldo_devedor_total(self):
        from django.db.models import Sum
        return self.emprestimos.filter(
            status__in=['ativo', 'inadimplente'],
            deleted_at__isnull=True,
        ).aggregate(total=Sum('capital_atual'))['total'] or 0


class DocumentoCliente(BaseModel):

    TIPO_CHOICES = [
        ('rg', 'RG'),
        ('cnh', 'CNH'),
        ('cpf', 'CPF'),
        ('comprovante_renda', 'Comprovante de Renda'),
        ('comprovante_residencia', 'Comprovante de Residência'),
        ('contrato', 'Contrato Assinado'),
        ('outro', 'Outro'),
    ]

    cliente = models.ForeignKey(
        Cliente, on_delete=models.CASCADE, related_name='documentos'
    )
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES)
    arquivo = models.FileField(upload_to='clientes/documentos/%Y/%m/')
    descricao = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        verbose_name = 'Documento do Cliente'
        verbose_name_plural = 'Documentos dos Clientes'

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.cliente.nome}"