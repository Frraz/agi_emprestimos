from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages as flash
from django.core.paginator import Paginator
from django.db.models import Q

from payments.infrastructure.models import Pagamento
from loans.application.services import EmprestimoService
from core.exceptions import AgiBaseException
from core.ownership import filtrar_por_usuario


@login_required
def pagamento_list(request):
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '')
    de = request.GET.get('de', '')
    ate = request.GET.get('ate', '')
    inativos = request.GET.get('inativos', '') == '1'

    base = Pagamento.objects.filter(deleted_at__isnull=not inativos)
    qs = filtrar_por_usuario(base, request.user).select_related(
        'emprestimo__cliente'
    ).order_by('-data_pagamento', '-created_at')

    if q:
        qs = qs.filter(
            Q(emprestimo__cliente__nome__icontains=q)
            | Q(emprestimo__cliente__cpf__icontains=q)
            | Q(emprestimo__cliente__telefone_principal__icontains=q)
        )
    if tipo:
        qs = qs.filter(tipo=tipo)
    if de:
        qs = qs.filter(data_pagamento__gte=de)
    if ate:
        qs = qs.filter(data_pagamento__lte=ate)

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page', 1))

    ctx = {
        'page': page, 'q': q, 'tipo': tipo, 'de': de, 'ate': ate, 'inativos': inativos,
        'inativos_qs': '&inativos=1' if inativos else '',
        'tipo_choices': Pagamento.TIPO_CHOICES, 'total': qs.count(),
    }
    if request.htmx:
        return render(request, 'payments/_rows.html', ctx)
    return render(request, 'payments/list.html', ctx)


def _pagamento_do_usuario(request, pk, incluir_deletados=False):
    base = Pagamento.objects.all()
    if not incluir_deletados:
        base = base.filter(deleted_at__isnull=True)
    return get_object_or_404(
        filtrar_por_usuario(base.select_related('emprestimo__cliente'), request.user),
        pk=pk,
    )


@login_required
def pagamento_desativar(request, pk):
    pag = _pagamento_do_usuario(request, pk)
    if request.method == 'POST':
        EmprestimoService.desativar_pagamento(str(pag.id), request.user)
        flash.success(request, 'Pagamento desativado e saldo recalculado.')
    return redirect(request.META.get('HTTP_REFERER') or reverse('web_payments:list'))


@login_required
def pagamento_ativar(request, pk):
    pag = _pagamento_do_usuario(request, pk, incluir_deletados=True)
    if request.method == 'POST':
        EmprestimoService.ativar_pagamento(str(pag.id), request.user)
        flash.success(request, 'Pagamento reativado e saldo recalculado.')
    return redirect(f"{reverse('web_payments:list')}?inativos=1")


@login_required
def pagamento_apagar(request, pk):
    pag = _pagamento_do_usuario(request, pk, incluir_deletados=True)
    if request.method == 'POST':
        EmprestimoService.apagar_pagamento(str(pag.id), request.user)
        flash.success(request, 'Pagamento apagado definitivamente e saldo recalculado.')
        return redirect('web_payments:list')
    return render(request, 'payments/confirm_apagar.html', {'pag': pag})


@login_required
def pagamento_editar(request, pk):
    """Slide-over de edição de pagamento (valor/data/observações)."""
    pag = get_object_or_404(
        filtrar_por_usuario(
            Pagamento.objects.select_related('emprestimo__cliente', 'parcela')
            .filter(deleted_at__isnull=True),
            request.user,
        ),
        pk=pk,
    )

    if request.method == 'POST':
        valor_str = (request.POST.get('valor', '') or '').replace(',', '.').strip()
        data_str = request.POST.get('data_pagamento', '')
        obs = request.POST.get('observacoes', '')
        try:
            valor = Decimal(valor_str)
            if valor <= 0:
                raise InvalidOperation
            data_pag = datetime.strptime(data_str, '%Y-%m-%d').date()
        except (InvalidOperation, ValueError, TypeError):
            return render(request, 'payments/_editar_pagamento.html',
                          {'pag': pag, 'erro': 'Informe valor e data válidos.'})

        try:
            EmprestimoService.editar_pagamento(
                pagamento_id=str(pag.id), valor=valor, data_pagamento=data_pag,
                observacoes=obs, usuario=request.user,
            )
        except AgiBaseException as e:
            return render(request, 'payments/_editar_pagamento.html',
                          {'pag': pag, 'erro': str(e)})

        flash.success(request, 'Pagamento atualizado e saldo recalculado.')
        resp = HttpResponse(status=204)
        resp['HX-Redirect'] = request.META.get('HTTP_REFERER') or reverse('web_payments:list')
        return resp

    return render(request, 'payments/_editar_pagamento.html', {'pag': pag})
