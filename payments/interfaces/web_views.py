from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from payments.infrastructure.models import Pagamento


@login_required
def pagamento_list(request):
    qs = Pagamento.objects.select_related(
        'emprestimo__cliente'
    ).order_by('-data_pagamento', '-created_at')
    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'payments/list.html', {'page': page})