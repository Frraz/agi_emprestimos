from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, get_object_or_404
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

    qs = filtrar_por_usuario(
        Pagamento.objects.filter(deleted_at__isnull=True), request.user
    ).select_related('emprestimo__cliente').order_by('-data_pagamento', '-created_at')

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
        'page': page, 'q': q, 'tipo': tipo, 'de': de, 'ate': ate,
        'tipo_choices': Pagamento.TIPO_CHOICES, 'total': qs.count(),
    }
    if request.htmx:
        return render(request, 'payments/_rows.html', ctx)
    return render(request, 'payments/list.html', ctx)


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
