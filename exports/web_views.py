"""
Backup / Extrato (P7): exporta os dados do operador (do usuário logado) em
CSV, JSON e PDF. Permite que o usuário leve todos os seus dados.

Todos os datasets são escopados por dono via core.ownership.filtrar_por_usuario.
PDF é gerado com WeasyPrint (HTML → PDF).
"""
import csv
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib import messages as flash
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string

from core.ownership import filtrar_por_usuario


# ── Datasets do usuário ─────────────────────────────────────────────────────

def _clientes(user):
    from customers.infrastructure.models import Cliente
    return filtrar_por_usuario(
        Cliente.objects.filter(deleted_at__isnull=True), user
    ).prefetch_related('tags').order_by('nome')


def _emprestimos(user):
    from loans.infrastructure.models import Emprestimo
    return filtrar_por_usuario(
        Emprestimo.objects.filter(deleted_at__isnull=True), user
    ).select_related('cliente').order_by('-data_inicio')


def _pagamentos(user):
    from payments.infrastructure.models import Pagamento
    return filtrar_por_usuario(
        Pagamento.objects.filter(deleted_at__isnull=True), user
    ).select_related('emprestimo__cliente').order_by('-data_pagamento')


# ── Serialização ────────────────────────────────────────────────────────────

def _row_cliente(c):
    return {
        'nome': c.nome, 'cpf': c.cpf, 'telefone': c.telefone_principal,
        'email': c.email or '', 'cidade': c.cidade or '', 'estado': c.estado or '',
        'classificacao': c.get_classificacao_display(),
        'tags': ', '.join(t.nome for t in c.tags.all()),
        'saldo_devedor': c.saldo_devedor_total,
    }


def _row_emprestimo(e):
    return {
        'cliente': e.cliente.nome, 'tipo': e.get_tipo_display(),
        'capital_inicial': e.capital_inicial, 'saldo_devedor': e.capital_atual,
        'juros_acumulados': e.juros_acumulados,
        'taxa_mensal_pct': (e.taxa_juros_mensal * 100),
        'status': e.get_status_display(),
        'data_inicio': e.data_inicio, 'data_vencimento': e.data_vencimento or '',
    }


def _row_pagamento(p):
    return {
        'cliente': p.emprestimo.cliente.nome, 'data': p.data_pagamento,
        'tipo': p.get_tipo_display(), 'valor': p.valor,
        'juros': p.valor_juros_pagos, 'capital': p.valor_capital_pago,
    }


_DATASETS = {
    'clientes': (
        'Clientes', _clientes, _row_cliente,
        ['nome', 'cpf', 'telefone', 'email', 'cidade', 'estado', 'classificacao', 'tags', 'saldo_devedor'],
    ),
    'emprestimos': (
        'Empréstimos', _emprestimos, _row_emprestimo,
        ['cliente', 'tipo', 'capital_inicial', 'saldo_devedor', 'juros_acumulados', 'taxa_mensal_pct', 'status', 'data_inicio', 'data_vencimento'],
    ),
    'pagamentos': (
        'Pagamentos', _pagamentos, _row_pagamento,
        ['cliente', 'data', 'tipo', 'valor', 'juros', 'capital'],
    ),
}


def _json_default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, date):
        return o.isoformat()
    return str(o)


def _csv_bytes(titulo, rows, campos):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=campos, extrasaction='ignore')
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode('utf-8-sig')  # BOM p/ Excel pt-BR


# ── Views ───────────────────────────────────────────────────────────────────

@login_required
def backup_index(request):
    counts = {
        'clientes': _clientes(request.user).count(),
        'emprestimos': _emprestimos(request.user).count(),
        'pagamentos': _pagamentos(request.user).count(),
    }
    return render(request, 'exports/index.html', {'counts': counts})


@login_required
def exportar(request, dataset, fmt):
    if dataset not in _DATASETS:
        flash.error(request, 'Conjunto de dados inválido.')
        return redirect('exports:index')

    titulo, fetch, row_fn, campos = _DATASETS[dataset]
    objetos = list(fetch(request.user))
    rows = [row_fn(o) for o in objetos]
    nome_arq = f'{dataset}_{date.today():%Y%m%d}'

    if fmt == 'csv':
        resp = HttpResponse(_csv_bytes(titulo, rows, campos), content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="{nome_arq}.csv"'
        return resp

    if fmt == 'json':
        payload = json.dumps({titulo: rows}, default=_json_default, ensure_ascii=False, indent=2)
        resp = HttpResponse(payload, content_type='application/json; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="{nome_arq}.json"'
        return resp

    if fmt == 'pdf':
        return _pdf_response(request, 'exports/pdf_tabela.html', {
            'titulo': titulo, 'campos': campos, 'rows': rows, 'hoje': date.today(),
            'operador': request.user.get_username(),
        }, nome_arq)

    flash.error(request, 'Formato inválido.')
    return redirect('exports:index')


@login_required
def exportar_backup(request, fmt):
    """Backup completo: clientes + empréstimos + pagamentos + configurações."""
    user = request.user
    blocos = {
        nome: [row_fn(o) for o in fetch(user)]
        for nome, (titulo, fetch, row_fn, campos) in _DATASETS.items()
    }
    from core.models_config import CapitalOperacional
    cfg = CapitalOperacional.get_for_user(user)
    configuracoes = {
        'capital_total': cfg.total_capital,
        'capital_emprestado': cfg.capital_emprestado,
        'capital_em_caixa': cfg.capital_em_caixa,
        'capital_em_operacao': cfg.capital_em_operacao,
    }
    nome_arq = f'backup_agi_{date.today():%Y%m%d}'

    if fmt == 'json':
        payload = json.dumps(
            {'gerado_em': date.today().isoformat(), 'operador': user.get_username(),
             **blocos, 'configuracoes': configuracoes},
            default=_json_default, ensure_ascii=False, indent=2,
        )
        resp = HttpResponse(payload, content_type='application/json; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="{nome_arq}.json"'
        return resp

    if fmt == 'csv':
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, 'w', zipfile.ZIP_DEFLATED) as zf:
            for nome, (titulo, fetch, row_fn, campos) in _DATASETS.items():
                zf.writestr(f'{nome}.csv', _csv_bytes(titulo, blocos[nome], campos))
        mem.seek(0)
        resp = HttpResponse(mem.read(), content_type='application/zip')
        resp['Content-Disposition'] = f'attachment; filename="{nome_arq}.zip"'
        return resp

    if fmt == 'pdf':
        return _pdf_response(request, 'exports/pdf_backup.html', {
            'blocos': blocos, 'configuracoes': configuracoes,
            'datasets': _DATASETS, 'hoje': date.today(), 'operador': user.get_username(),
        }, nome_arq)

    flash.error(request, 'Formato inválido.')
    return redirect('exports:index')


def _pdf_response(request, template, ctx, nome_arq):
    try:
        from weasyprint import HTML
    except Exception:
        flash.error(request, 'Geração de PDF indisponível (WeasyPrint não instalado no servidor).')
        return redirect('exports:index')
    html = render_to_string(template, ctx, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf()
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{nome_arq}.pdf"'
    return resp
