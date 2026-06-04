from datetime import date, datetime

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


def _montar_semanas(ano: int, mes: int, ref: date):
    """Combina a grade do mês com os eventos em células prontas p/ template."""
    eventos = CobrancaService.eventos_calendario(ano, mes, ref=ref)
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
        'semanas': _montar_semanas(ano, mes, ref),
        'mes_ref': date(ano, mes, 1),
        'nav_anterior': {'ano': ano_anterior, 'mes': mes_anterior},
        'nav_seguinte': {'ano': ano_seguinte, 'mes': mes_seguinte},
    }


@login_required
def cobrancas_index(request):
    hoje = date.today()
    data_especifica = _parse_data(request.GET.get('data'))

    buckets = CobrancaService.vencimentos_por_bucket(
        ref=hoje, data_especifica=data_especifica
    )

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
        'buckets': buckets,
        'totais': buckets['totais'],
        'por_cliente': CobrancaService.total_atraso_por_cliente(ref=hoje),
    }
    context.update(_contexto_calendario(request, hoje))
    return render(request, 'cobrancas/index.html', context)


@login_required
def cobrancas_calendario(request):
    """HTMX: navegação de mês do calendário."""
    hoje = date.today()
    return render(request, 'cobrancas/_calendario.html', _contexto_calendario(request, hoje))
