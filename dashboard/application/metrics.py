from decimal import Decimal
from django.db.models import Sum, Avg, Count, Q


def calcular_metricas_dashboard() -> dict:
    from loans.infrastructure.models import Emprestimo, ParcelaEmprestimo
    from core.models_config import CapitalOperacional

    capital_op = CapitalOperacional.get_instance()

    ativos = Emprestimo.objects.filter(
        status__in=['ativo', 'inadimplente'],
        deleted_at__isnull=True,
    )

    # ── Capital ────────────────────────────────────────────────────────────
    capital_emprestado = ativos.aggregate(
        total=Sum('capital_atual')
    )['total'] or Decimal('0')

    capital_por_tipo = {
        tipo: ativos.filter(tipo=tipo).aggregate(
            total=Sum('capital_atual')
        )['total'] or Decimal('0')
        for tipo in ['comum', 'parcelado', 'diaria']
    }

    # ── Inadimplência ──────────────────────────────────────────────────────
    total = ativos.count()
    inadimplentes = ativos.filter(status='inadimplente').count()
    taxa_inadimplencia = (
        Decimal(inadimplentes) / Decimal(total) * 100
        if total > 0 else Decimal('0')
    )

    # ── Juros ──────────────────────────────────────────────────────────────
    taxa_media = (
        ativos.aggregate(media=Avg('taxa_juros_mensal'))['media'] or Decimal('0')
    ) * 100

    # ── Parcelas atrasadas ─────────────────────────────────────────────────
    parcelas_info = ParcelaEmprestimo.objects.filter(
        status='atrasado',
        emprestimo__deleted_at__isnull=True,
    ).aggregate(
        total_valor=Sum('valor_parcela'),
        quantidade=Count('id'),
    )

    # ── Custo da inadimplência ajustado por penhora ────────────────────────
    custo_inadimplencia = _calcular_custo_inadimplencia_ajustado()

    # ── Projeções ──────────────────────────────────────────────────────────
    projecoes = _calcular_projecoes(ativos, taxa_inadimplencia)

    # ── Taxa de risco ──────────────────────────────────────────────────────
    taxa_risco = _calcular_taxa_risco(
        capital_emprestado,
        custo_inadimplencia['perda_ajustada_total'],
        taxa_inadimplencia,
    )

    return {
        'capital_total_operador': capital_op.total_capital,
        'capital_emprestado': capital_emprestado,
        'capital_em_caixa': capital_op.capital_em_caixa,
        'capital_por_tipo': capital_por_tipo,
        'total_emprestimos_ativos': total,
        'inadimplentes': inadimplentes,
        'taxa_inadimplencia': round(taxa_inadimplencia, 2),
        'taxa_juros_media_mensal': round(taxa_media, 2),
        'parcelas_atrasadas_valor': parcelas_info['total_valor'] or Decimal('0'),
        'parcelas_atrasadas_qtd': parcelas_info['quantidade'] or 0,
        'projecoes_lucro': projecoes,
        'custo_inadimplencia': custo_inadimplencia,
        'taxa_risco_operacao': taxa_risco,
    }


def _calcular_custo_inadimplencia_ajustado() -> dict:
    """
    Para cada empréstimo inadimplente:
      exposicao_real = saldo_devedor - (valor_garantias × percentual_recuperacao)
    
    Retorna totais consolidados.
    """
    from loans.infrastructure.models import Emprestimo
    from django.db.models import Sum

    inadimplentes = Emprestimo.objects.filter(
        status='inadimplente',
        deleted_at__isnull=True,
    ).prefetch_related('garantias')

    saldo_total = Decimal('0')
    garantia_total = Decimal('0')
    recuperacao_estimada = Decimal('0')
    perda_ajustada_total = Decimal('0')

    for emp in inadimplentes:
        saldo = emp.capital_atual
        valor_garantias = sum(
            g.valor_estimado for g in emp.garantias.filter(deleted_at__isnull=True)
        )
        recuperacao = sum(
            g.valor_estimado * g.percentual_recuperacao
            for g in emp.garantias.filter(deleted_at__isnull=True)
        )
        perda = max(Decimal('0'), saldo - recuperacao)

        saldo_total += saldo
        garantia_total += valor_garantias
        recuperacao_estimada += recuperacao
        perda_ajustada_total += perda

    return {
        'saldo_devedor_inadimplentes': saldo_total,
        'valor_garantias_total': garantia_total,
        'recuperacao_estimada': recuperacao_estimada,
        'perda_ajustada_total': perda_ajustada_total,
        'cobertura_percentual': (
            round(recuperacao_estimada / saldo_total * 100, 1)
            if saldo_total > 0 else Decimal('100')
        ),
    }


def _calcular_projecoes(emprestimos_qs, taxa_inadimplencia: Decimal) -> dict:
    from core.utils import arredondar_financeiro

    lucro_base = Decimal('0')
    for emp in emprestimos_qs.only('capital_atual', 'taxa_juros_mensal'):
        lucro_base += emp.capital_atual * emp.taxa_juros_mensal

    lucro_base = arredondar_financeiro(lucro_base)
    fator_real = min(Decimal('1'), taxa_inadimplencia / 100)
    fator_pess = min(Decimal('1'), taxa_inadimplencia / 100 * Decimal('1.5'))

    return {
        'otimista': lucro_base,
        'realista': arredondar_financeiro(lucro_base * (1 - fator_real)),
        'pessimista': arredondar_financeiro(lucro_base * (1 - fator_pess)),
    }


def _calcular_taxa_risco(
    capital_emprestado: Decimal,
    perda_ajustada: Decimal,
    taxa_inadimplencia: Decimal,
) -> Decimal:
    """
    Taxa de risco composta:
    - 50% peso: inadimplência
    - 50% peso: exposição real (perda / capital)
    """
    from core.utils import arredondar_financeiro

    exposicao = (
        perda_ajustada / capital_emprestado * 100
        if capital_emprestado > 0 else Decimal('0')
    )
    taxa = (taxa_inadimplencia * Decimal('0.5')) + (exposicao * Decimal('0.5'))
    return arredondar_financeiro(taxa)