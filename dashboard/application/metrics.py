from decimal import Decimal
from django.db.models import Sum, Avg, Count


def calcular_metricas_dashboard() -> dict:
    from loans.infrastructure.models import Emprestimo
    from core.models_config import CapitalOperacional

    capital_op = CapitalOperacional.get_instance()

    ativos = Emprestimo.objects.ativos()
    # Atraso por DATA (independe do cron diário já ter rodado).
    vencidos = Emprestimo.objects.vencidos()

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

    # ── Inadimplência (baseada em data) ────────────────────────────────────
    total = ativos.count()
    inadimplentes = vencidos.count()
    taxa_inadimplencia = (
        Decimal(inadimplentes) / Decimal(total) * 100
        if total > 0 else Decimal('0')
    )

    # ── Juros ──────────────────────────────────────────────────────────────
    taxa_media = (
        ativos.aggregate(media=Avg('taxa_juros_mensal'))['media'] or Decimal('0')
    ) * 100

    # ── Valor em atraso (comum + parcelado) ────────────────────────────────
    atraso = _calcular_valor_em_atraso(vencidos)

    # ── Custo da inadimplência ajustado por penhora ────────────────────────
    custo_inadimplencia = _calcular_custo_inadimplencia_ajustado(vencidos)

    # ── Projeções ──────────────────────────────────────────────────────────
    projecoes = _calcular_projecoes(ativos, taxa_inadimplencia)

    # ── Taxa de risco da operação (composta e ponderada) ───────────────────
    taxa_risco = _calcular_taxa_risco(
        ativos=ativos,
        vencidos=vencidos,
        capital_emprestado=capital_emprestado,
        capital_total=capital_op.total_capital,
        custo_inadimplencia=custo_inadimplencia,
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
        'valor_em_atraso': atraso['valor'],
        'qtd_em_atraso': atraso['quantidade'],
        # Aliases retrocompatíveis (templates antigos)
        'parcelas_atrasadas_valor': atraso['valor'],
        'parcelas_atrasadas_qtd': atraso['quantidade'],
        'projecoes_lucro': projecoes,
        'custo_inadimplencia': custo_inadimplencia,
        'taxa_risco_operacao': taxa_risco['total'],
        'risco_composicao': taxa_risco,
    }


def _calcular_valor_em_atraso(vencidos) -> dict:
    """
    Soma o valor em atraso dos empréstimos vencidos.
    Comum: saldo devedor atual. Parcelado: soma das parcelas em aberto vencidas.
    """
    valor = Decimal('0')
    quantidade = 0
    for emp in vencidos.prefetch_related('parcelas'):
        valor += emp.valor_em_atraso
        quantidade += 1
    return {'valor': valor, 'quantidade': quantidade}


def _calcular_custo_inadimplencia_ajustado(vencidos) -> dict:
    """
    Para cada empréstimo vencido:
      exposicao_real = saldo_devedor - (valor_garantias × percentual_recuperacao)

    Retorna totais consolidados.
    """
    saldo_total = Decimal('0')
    garantia_total = Decimal('0')
    recuperacao_estimada = Decimal('0')
    perda_ajustada_total = Decimal('0')

    for emp in vencidos.prefetch_related('garantias'):
        saldo = emp.capital_atual
        garantias = list(emp.garantias.filter(deleted_at__isnull=True))
        valor_garantias = sum((g.valor_estimado for g in garantias), Decimal('0'))
        recuperacao = sum(
            (g.valor_estimado * g.percentual_recuperacao for g in garantias),
            Decimal('0'),
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
    ativos,
    vencidos,
    capital_emprestado: Decimal,
    capital_total: Decimal,
    custo_inadimplencia: dict,
) -> dict:
    """
    Reúne os insumos via ORM e delega o cálculo à CalculadoraRisco (domínio).
    Composição: cobertura 40% · histórico 30% · comprometimento 20% · tempo 10%.
    """
    from loans.domain.calculators import CalculadoraRisco

    # Cobertura da penhora (sobre os vencidos)
    fator_cobertura = CalculadoraRisco.fator_cobertura_penhora(
        custo_inadimplencia['saldo_devedor_inadimplentes'],
        custo_inadimplencia['valor_garantias_total'],
    )

    # Histórico do cliente — capital exposto ponderado pela classificação
    distribuicao = {'verde': Decimal('0'), 'amarelo': Decimal('0'), 'vermelho': Decimal('0')}
    por_classe = ativos.values('cliente__classificacao').annotate(
        capital=Sum('capital_atual')
    )
    for row in por_classe:
        classe = row['cliente__classificacao'] or 'verde'
        distribuicao[classe] = distribuicao.get(classe, Decimal('0')) + (
            row['capital'] or Decimal('0')
        )
    fator_historico = CalculadoraRisco.fator_historico_cliente(distribuicao)

    # Comprometimento do capital
    fator_comprometimento = CalculadoraRisco.fator_comprometimento_capital(
        capital_emprestado, capital_total
    )

    # Tempo de exposição — dias de atraso dos vencidos
    dias_lista = [emp.dias_atraso for emp in vencidos.prefetch_related('parcelas')]
    fator_tempo = CalculadoraRisco.fator_tempo_exposicao(dias_lista)

    total = CalculadoraRisco.calcular_taxa_risco(
        fator_cobertura, fator_historico, fator_comprometimento, fator_tempo
    )

    return {
        'total': total,
        'cobertura': fator_cobertura,
        'historico': fator_historico,
        'comprometimento': fator_comprometimento,
        'tempo': fator_tempo,
    }
