from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages as flash
from django.core.paginator import Paginator

from loans.infrastructure.models import Emprestimo
from loans.application.services import EmprestimoService
from loans.interfaces.forms import (
    EmprestimoComumForm, EmprestimoParceladoForm, PagamentoComumForm
)
from customers.infrastructure.models import Cliente
from core.exceptions import AgiBaseException


@login_required
def emprestimo_list(request):
    tipo = request.GET.get('tipo', '')
    status_f = request.GET.get('status', '')

    qs = Emprestimo.objects.filter(
        deleted_at__isnull=True
    ).select_related('cliente').order_by('-data_inicio')
    if tipo:
        qs = qs.filter(tipo=tipo)
    if status_f:
        qs = qs.filter(status=status_f)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'loans/list.html', {
        'page': page, 'tipo': tipo, 'status_f': status_f,
    })


@login_required
def emprestimo_detail(request, pk):
    emp = get_object_or_404(
        Emprestimo.objects.select_related('cliente')
        .prefetch_related('parcelas', 'garantias', 'pagamentos'),
        pk=pk, deleted_at__isnull=True,
    )
    pagamento_form = None
    juros_mes = total_quitacao = None

    if emp.tipo == 'comum' and emp.status in ('ativo', 'inadimplente'):
        pagamento_form = PagamentoComumForm()
        from loans.domain.calculators import CalculadoraEmprestimoComum
        juros_mes = CalculadoraEmprestimoComum.calcular_juros_mes(
            emp.capital_atual, emp.taxa_juros_mensal
        )
        total_quitacao = CalculadoraEmprestimoComum.calcular_total_quitacao(
            emp.capital_atual, emp.taxa_juros_mensal
        )

    return render(request, 'loans/detail.html', {
        'emp': emp,
        'pagamento_form': pagamento_form,
        'juros_mes': juros_mes,
        'total_quitacao': total_quitacao,
    })


@login_required
def emprestimo_criar_comum(request, cliente_pk):
    cliente = get_object_or_404(Cliente, pk=cliente_pk, deleted_at__isnull=True)
    if request.method == 'POST':
        form = EmprestimoComumForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            try:
                emp = EmprestimoService.criar_emprestimo_comum(
                    cliente_id=str(cliente.id),
                    capital=d['capital'],
                    taxa_mensal=d['taxa_mensal'],
                    data_inicio=d['data_inicio'],
                    observacoes=d.get('observacoes', ''),
                    usuario=request.user,
                )
                flash.success(request, 'Empréstimo criado com sucesso.')
                return redirect('web_loans:detail', pk=emp.id)
            except AgiBaseException as e:
                form.add_error(None, str(e))
    else:
        form = EmprestimoComumForm()
    return render(request, 'loans/form_comum.html', {'form': form, 'cliente': cliente})


@login_required
def emprestimo_criar_parcelado(request, cliente_pk):
    cliente = get_object_or_404(Cliente, pk=cliente_pk, deleted_at__isnull=True)

    if request.method == 'POST':
        form = EmprestimoParceladoForm(request.POST)

        # HTMX: simulação sem persistir
        if request.htmx and request.POST.get('simular'):
            if form.is_valid():
                d = form.cleaned_data
                from loans.domain.calculators import (
                    CalculadoraEmprestimoParceladoFixo,
                    CalculadoraEmprestimoParceladoSAC,
                )
                calc = (
                    CalculadoraEmprestimoParceladoFixo if d['subtipo'] == 'fixo'
                    else CalculadoraEmprestimoParceladoSAC
                )
                tabela = calc.gerar_tabela_amortizacao(
                    d['capital'], d['taxa_mensal'],
                    d['n_parcelas'], d['data_primeira_parcela'],
                )
                total_juros = sum(p.valor_juros for p in tabela)
                total_pagar = sum(p.valor_parcela for p in tabela)
                return render(request, 'loans/_simular.html', {
                    'tabela': tabela,
                    'total_juros': total_juros,
                    'total_pagar': total_pagar,
                })
            return render(request, 'loans/_simular.html', {'erro': True})

        # POST normal: criar
        if form.is_valid():
            d = form.cleaned_data
            try:
                emp = EmprestimoService.criar_emprestimo_parcelado(
                    cliente_id=str(cliente.id),
                    capital=d['capital'],
                    taxa_mensal=d['taxa_mensal'],
                    n_parcelas=d['n_parcelas'],
                    subtipo=d['subtipo'],
                    data_inicio=d['data_inicio'],
                    data_primeira_parcela=d['data_primeira_parcela'],
                    observacoes=d.get('observacoes', ''),
                    usuario=request.user,
                )
                flash.success(request, f'Empréstimo parcelado criado com {d["n_parcelas"]}x.')
                return redirect('web_loans:detail', pk=emp.id)
            except AgiBaseException as e:
                form.add_error(None, str(e))
    else:
        form = EmprestimoParceladoForm()
    return render(request, 'loans/form_parcelado.html', {'form': form, 'cliente': cliente})


@login_required
def emprestimo_pagar(request, pk):
    emp = get_object_or_404(Emprestimo, pk=pk, deleted_at__isnull=True)
    if request.method == 'POST':
        form = PagamentoComumForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            try:
                EmprestimoService.registrar_pagamento_comum(
                    emprestimo_id=str(emp.id),
                    valor=d['valor'],
                    data_pagamento=d['data_pagamento'],
                    observacoes=d.get('observacoes', ''),
                    usuario=request.user,
                )
                flash.success(request, 'Pagamento registrado com sucesso.')
            except AgiBaseException as e:
                flash.error(request, str(e))
    return redirect('web_loans:detail', pk=emp.id)