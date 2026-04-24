"""
Garantias (Penhor) vinculadas a empréstimos.
Usadas para calcular exposição real e perda ajustada.
"""
from decimal import Decimal
from django.db import models
from core.models import BaseModel


class Garantia(BaseModel):

    TIPO_CHOICES = [
        ('veiculo', 'Veículo (Carro/Moto)'),
        ('imovel', 'Imóvel'),
        ('eletronico', 'Eletrônico'),
        ('joia', 'Joia / Relógio'),
        ('outro', 'Outro'),
    ]

    emprestimo = models.ForeignKey(
        'loans.Emprestimo',
        on_delete=models.CASCADE,
        related_name='garantias',
    )
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    descricao = models.TextField()
    valor_estimado = models.DecimalField(max_digits=12, decimal_places=2)

    # Percentual estimado de recuperação em caso de inadimplência
    # 0.70 = 70% — padrão conservador para veículos
    percentual_recuperacao = models.DecimalField(
        max_digits=5, decimal_places=4,
        default=Decimal('0.7000'),
        help_text='Ex: 0.7000 = 70% de recuperação estimada',
    )

    # JSON flexível para detalhes específicos do bem
    # Veículo: {"placa": "ABC1234", "chassi": "...", "ano": 2020}
    # Imóvel:  {"matricula": "...", "endereco": "..."}
    detalhes = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Garantia'
        verbose_name_plural = 'Garantias'

    def __str__(self):
        return f"{self.get_tipo_display()} — R${self.valor_estimado} ({self.emprestimo})"

    @property
    def valor_recuperacao_estimado(self) -> Decimal:
        return self.valor_estimado * self.percentual_recuperacao

    def calcular_exposicao(self) -> dict:
        """Delega ao domínio — não calcula aqui."""
        from loans.domain.calculators import CalculadoraInadimplencia
        return CalculadoraInadimplencia.calcular_exposicao_ajustada(
            saldo_devedor=self.emprestimo.capital_atual,
            valor_garantia=self.valor_estimado,
            percentual_recuperacao=self.percentual_recuperacao,
        )


class DocumentoGarantia(BaseModel):
    garantia = models.ForeignKey(
        Garantia, on_delete=models.CASCADE, related_name='documentos'
    )
    arquivo = models.FileField(upload_to='garantias/documentos/%Y/%m/')
    descricao = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        verbose_name = 'Documento da Garantia'
        verbose_name_plural = 'Documentos das Garantias'