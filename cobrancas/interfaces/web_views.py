from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from cobrancas.application.services import CobrancaService


def _parse_data(valor):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _montar_semanas(ano: int, mes: int, ref: date, user=None):
    """Combina a grade do mês com os eventos em células prontas p/ template."""
    eventos = CobrancaService.eventos_calendario(ano, mes, ref=ref, user=user)
    semanas = []
    for semana in CobrancaService.grade_calendario(ano, mes):
        linha = []
        for dia in semana:
            linha.append({
                'dia': dia,
                'hoje': dia == ref if dia else False,
                'evento': eventos.get(dia) if dia else None,
            })
        semanas.append(linha)
    return semanas


def _contexto_calendario(request, ref: date):
    ano = int(request.GET.get('ano', ref.year))
    mes = int(request.GET.get('mes', ref.month))
    mes_anterior = (mes - 1) or 12
    ano_anterior = ano - 1 if mes == 1 else ano
    mes_seguinte = 1 if mes == 12 else mes + 1
    ano_seguinte = ano + 1 if mes == 12 else ano
    return {
        'semanas': _montar_semanas(ano, mes, ref, user=request.user),
        'mes_ref': date(ano, mes, 1),
        'nav_anterior': {'ano': ano_anterior, 'mes': mes_anterior},
        'nav_seguinte': {'ano': ano_seguinte, 'mes': mes_seguinte},
    }


@login_required
def cobrancas_index(request):
    hoje = date.today()
    data_especifica = _parse_data(request.GET.get('data'))
    q = request.GET.get('q', '').strip()

    buckets = CobrancaService.vencimentos_por_bucket(
        ref=hoje, data_especifica=data_especifica, user=request.user
    )
    por_cliente = CobrancaService.total_atraso_por_cliente(ref=hoje, user=request.user)

    # Busca por nome/CPF do cliente (filtra os baldes e o resumo por cliente)
    if q:
        ql = q.lower()
        def _match(it):
            cli = it['cliente']
            return ql in cli.nome.lower() or ql in (cli.cpf or '')
        for chave, lista in list(buckets.items()):
            if chave == 'totais':
                continue
            buckets[chave] = [it for it in lista if _match(it)]
        buckets['totais'] = {
            chave: sum((i['valor'] for i in lista), Decimal('0'))
            for chave, lista in buckets.items() if chave != 'totais'
        }
        por_cliente = [
            r for r in por_cliente
            if ql in r['cliente'].nome.lower() or ql in (r['cliente'].cpf or '')
        ]

    # HTMX: clique num dia do calendário → só a lista da data escolhida
    if request.htmx and 'data' in request.GET:
        return render(request, 'cobrancas/_lista.html', {
            'titulo': 'Vencimentos em ' + (
                data_especifica.strftime('%d/%m/%Y') if data_especifica else '—'
            ),
            'itens': buckets['data_especifica'],
            'data_especifica': data_especifica,
        })

    context = {
        'hoje': hoje,
        'q': q,
        'buckets': buckets,
        'totais': buckets['totais'],
        'por_cliente': por_cliente,
    }
    context.update(_contexto_calendario(request, hoje))
    return render(request, 'cobrancas/index.html', context)


@login_required
def cobrancas_calendario(request):
    """HTMX: navegação de mês do calendário."""
    hoje = date.today()
    return render(request, 'cobrancas/_calendario.html', _contexto_calendario(request, hoje))
