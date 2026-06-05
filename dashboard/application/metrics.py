from decimal import Decimal
from django.db.models import Sum, Avg, Count
from django.db.models.functions import TruncMonth

# Abreviações de mês em pt-BR (índice 1–12) para os rótulos do gráfico de tendência.
_MESES_PT = [
    '', 'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
    'jul', 'ago', 'set', 'out', 'nov', 'dez',
]


def calcular_metricas_dashboard(user=None) -> dict:
    """Métricas do dashboard escopadas ao usuário (isolamento por dono).
    user=None → varredura global (uso interno/testes)."""
    from loans.infrastructure.models import Emprestimo
    from core.models_config import CapitalOperacional
    from core.ownership import escopo_opcional

    capital_op = (
        CapitalOperacional.get_for_user(user) if user is not None
        else CapitalOperacional.get_instance()
    )

    ativos = escopo_opcional(Emprestimo.objects.ativos(), user)
    # Atraso por DATA (independe do cron diário já ter rodado).
    vencidos = escopo_opcional(Emprestimo.objects.vencidos(), user)

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

    # ── Total em operação (capital aportado + juros recebidos) ─────────────
    capital_total = capital_op.capital_em_operacao

    # ── Taxa de risco da operação (composta e ponderada) ───────────────────
    taxa_risco = _calcular_taxa_risco(
        ativos=ativos,
        vencidos=vencidos,
        capital_emprestado=capital_emprestado,
        capital_total=capital_total,
        custo_inadimplencia=custo_inadimplencia,
    )

    # ── Tendência de recebimentos (últimos meses) ──────────────────────────
    recebimentos_mensais = _calcular_recebimentos_mensais(user=user)

    # ── Ocupação do capital (sem query adicional) ──────────────────────────
    taxa_ocupacao = (
        capital_emprestado / capital_total * 100
        if capital_total and capital_total > 0 else Decimal('0')
    )

    return {
        'capital_total_operador': capital_total,
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
        'recebimentos_mensais': recebimentos_mensais,
        'recebido_mes_atual': recebimentos_mensais[-1] if recebimentos_mensais else None,
        'taxa_ocupacao_capital': round(taxa_ocupacao, 1),
    }


def _calcular_recebimentos_mensais(meses: int = 6, user=None) -> list:
    """
    Série dos últimos `meses` meses (incluindo o atual), com total recebido e
    parcela de juros. Meses sem pagamento aparecem zerados, em ordem cronológica.
    Retorna: [{'label': 'jan/26', 'total': Decimal, 'juros': Decimal}, ...].
    """
    from datetime import date
    from payments.infrastructure.models import Pagamento
    from core.utils import arredondar_financeiro
    from core.ownership import escopo_opcional

    hoje = date.today()

    # Sequência contínua dos meses (do mais antigo ao atual) como (ano, mês).
    seq = []
    ano, mes = hoje.year, hoje.month
    for _ in range(meses):
        seq.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1
    seq.reverse()

    inicio = date(seq[0][0], seq[0][1], 1)

    agregado = (
        escopo_opcional(
            Pagamento.objects.filter(deleted_at__isnull=True, data_pagamento__gte=inicio),
            user,
        )
        .annotate(mes_ref=TruncMonth('data_pagamento'))
        .values('mes_ref')
        .annotate(total=Sum('valor'), juros=Sum('valor_juros_pagos'))
    )
    por_mes = {
        (row['mes_ref'].year, row['mes_ref'].month): row
        for row in agregado
    }

    serie = []
    for ano, mes in seq:
        row = por_mes.get((ano, mes))
        serie.append({
            'label': f'{_MESES_PT[mes]}/{ano % 100:02d}',
            'total': arredondar_financeiro((row['total'] if row else None) or Decimal('0')),
            'juros': arredondar_financeiro((row['juros'] if row else None) or Decimal('0')),
        })
    return serie


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
