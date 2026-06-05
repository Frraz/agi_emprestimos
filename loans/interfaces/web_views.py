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
from core.ownership import filtrar_por_usuario


@login_required
def emprestimo_list(request):
    from django.db.models import Q
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '')
    status_f = request.GET.get('status', '')
    vencido = request.GET.get('vencido', '')

    qs = filtrar_por_usuario(
        Emprestimo.objects.filter(deleted_at__isnull=True), request.user
    ).select_related('cliente').prefetch_related('parcelas').order_by('-data_inicio')
    if q:
        qs = qs.filter(
            Q(cliente__nome__icontains=q) | Q(cliente__cpf__icontains=q)
            | Q(cliente__telefone_principal__icontains=q)
        )
    if tipo:
        qs = qs.filter(tipo=tipo)
    if status_f:
        qs = qs.filter(status=status_f)
    if vencido:
        qs = qs.vencidos()

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page', 1))
    return render(request, 'loans/list.html', {
        'page': page, 'q': q, 'tipo': tipo, 'status_f': status_f, 'vencido': vencido,
    })


@login_required
def emprestimo_detail(request, pk):
    emp = get_object_or_404(
        filtrar_por_usuario(
            Emprestimo.objects.select_related('cliente')
            .prefetch_related('parcelas', 'garantias', 'pagamentos')
            .filter(deleted_at__isnull=True),
            request.user,
        ),
        pk=pk,
    )
    pagamento_form = None
    juros_mes = total_quitacao = juros_acumulados = None

    if emp.tipo == 'comum' and emp.status in ('ativo', 'inadimplente'):
        pagamento_form = PagamentoComumForm()
        juros_mes = emp.juros_mes                # juros do próximo ciclo (projeção)
        juros_acumulados = emp.juros_acumulados  # juros já lançados, em aberto
        total_quitacao = emp.total_quitacao      # capital + juros acumulados

    return render(request, 'loans/detail.html', {
        'emp': emp,
        'pagamento_form': pagamento_form,
        'juros_mes': juros_mes,
        'juros_acumulados': juros_acumulados,
        'total_quitacao': total_quitacao,
    })


@login_required
def emprestimo_criar_comum(request, cliente_pk):
    cliente = get_object_or_404(
        filtrar_por_usuario(Cliente.objects.filter(deleted_at__isnull=True), request.user),
        pk=cliente_pk,
    )
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
                    data_vencimento=d['data_vencimento'],
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
    cliente = get_object_or_404(
        filtrar_por_usuario(Cliente.objects.filter(deleted_at__isnull=True), request.user),
        pk=cliente_pk,
    )

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
    emp = get_object_or_404(
        filtrar_por_usuario(Emprestimo.objects.filter(deleted_at__isnull=True), request.user),
        pk=pk,
    )
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


@login_required
def emprestimo_pagar_parcelas(request, pk):
    """Registra pagamento de uma ou mais parcelas (parcial/total/excedente)."""
    from datetime import datetime, date
    from decimal import Decimal, InvalidOperation

    emp = get_object_or_404(
        filtrar_por_usuario(Emprestimo.objects.filter(deleted_at__isnull=True), request.user),
        pk=pk,
    )
    if request.method != 'POST':
        return redirect('web_loans:detail', pk=emp.id)

    parcela_ids = request.POST.getlist('parcelas')
    valor_str = (request.POST.get('valor', '') or '').replace(',', '.').strip()
    data_str = request.POST.get('data_pagamento', '')
    observacoes = request.POST.get('observacoes', '')

    try:
        valor = Decimal(valor_str)
        if valor <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        flash.error(request, 'Informe um valor de pagamento válido.')
        return redirect('web_loans:detail', pk=emp.id)

    try:
        data_pag = datetime.strptime(data_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        data_pag = date.today()

    if not parcela_ids:
        flash.error(request, 'Selecione ao menos uma parcela para pagar.')
        return redirect('web_loans:detail', pk=emp.id)

    try:
        resultado = EmprestimoService.registrar_pagamento_parcelas(
            emprestimo_id=str(emp.id),
            parcela_ids=parcela_ids,
            valor=valor,
            data_pagamento=data_pag,
            observacoes=observacoes,
            usuario=request.user,
        )
    except AgiBaseException as e:
        flash.error(request, str(e))
        return redirect('web_loans:detail', pk=emp.id)

    # Feedback visual da movimentação
    n_pagas = len(resultado['afetadas'])
    flash.success(request, f'Pagamento de R$ {valor:.2f} registrado em {n_pagas} parcela(s).')
    for info in resultado['excedente_info']:
        flash.info(
            request,
            f"Excedente de R$ {info['valor_aplicado']:.2f} aplicado na parcela "
            f"{info['numero']} (novo saldo: R$ {info['novo_em_aberto']:.2f}).",
        )
    if resultado['excedente_nao_aplicado'] > 0:
        flash.info(
            request,
            f"Sobrou R$ {resultado['excedente_nao_aplicado']:.2f} sem parcela em aberto para aplicar.",
        )
    if resultado['quitado']:
        flash.success(request, '🎉 Empréstimo quitado!')

    return redirect('web_loans:detail', pk=emp.id)