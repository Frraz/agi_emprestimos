from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages as flash
from django.core.paginator import Paginator
from django.db.models import Q

from customers.infrastructure.models import Cliente
from customers.interfaces.forms import ClienteForm
from core.exceptions import AgiBaseException
import urllib.request
import json


@login_required
def cliente_list(request):
    q = request.GET.get('q', '').strip()
    classificacao = request.GET.get('classificacao', '')

    qs = Cliente.objects.filter(deleted_at__isnull=True).order_by('nome')
    if q:
        qs = qs.filter(
            Q(nome__icontains=q) | Q(cpf__icontains=q) | Q(telefone_principal__icontains=q)
        )
    if classificacao:
        qs = qs.filter(classificacao=classificacao)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    # HTMX: retorna só as linhas da tabela
    if request.htmx:
        return render(request, 'customers/_rows.html', {'page': page})

    return render(request, 'customers/list.html', {
        'page': page, 'q': q, 'classificacao': classificacao,
        'total': qs.count(),
    })


@login_required
def cliente_detail(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk, deleted_at__isnull=True)
    emprestimos = cliente.emprestimos.filter(
        deleted_at__isnull=True
    ).order_by('-data_inicio')
    return render(request, 'customers/detail.html', {
        'cliente': cliente,
        'emprestimos': emprestimos,
    })


@login_required
def cliente_create(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST, request.FILES)
        if form.is_valid():
            cliente = form.save()
            _audit(cliente, 'create', request.user)
            flash.success(request, f'Cliente {cliente.nome} cadastrado com sucesso.')
            return redirect('web_customers:detail', pk=cliente.id)
    else:
        form = ClienteForm()
    return render(request, 'customers/form.html', {'form': form, 'acao': 'Cadastrar'})


@login_required
def cliente_update(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk, deleted_at__isnull=True)
    if request.method == 'POST':
        form = ClienteForm(request.POST, request.FILES, instance=cliente)
        if form.is_valid():
            form.save()
            _audit(cliente, 'update', request.user)
            flash.success(request, 'Cliente atualizado com sucesso.')
            return redirect('web_customers:detail', pk=cliente.id)
    else:
        form = ClienteForm(instance=cliente)
    return render(request, 'customers/form.html', {
        'form': form, 'cliente': cliente, 'acao': 'Atualizar'
    })


@login_required
def cliente_delete(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk, deleted_at__isnull=True)
    if request.method == 'POST':
        nome = cliente.nome
        cliente.soft_delete(usuario=request.user)
        flash.success(request, f'Cliente {nome} removido.')
        return redirect('web_customers:list')
    return render(request, 'customers/confirm_delete.html', {'cliente': cliente})


def _audit(obj, action, usuario):
    try:
        from audit.infrastructure.models import AuditLog
        from django.contrib.contenttypes.models import ContentType
        AuditLog.objects.create(
            content_type=ContentType.objects.get_for_model(type(obj)),
            object_id=str(obj.id),
            action=action,
            changes={},
            usuario=usuario,
        )
    except Exception:
        pass

@login_required
def buscar_cep(request):
    """Busca CEP via ViaCEP e retorna campos preenchidos via HTMX."""
    cep = request.GET.get('cep', '').replace('-', '').replace('.', '').strip()
    dados = {}
    if len(cep) == 8:
        try:
            url = f'https://viacep.com.br/ws/{cep}/json/'
            with urllib.request.urlopen(url, timeout=3) as resp:
                dados = json.loads(resp.read())
        except Exception:
            pass
    return render(request, 'customers/_cep_fields.html', {'dados': dados})


@login_required
def buscar_indicador(request):
    """HTMX — busca clientes para preencher campo de indicador."""
    q = request.GET.get('q_indicador', '').strip()
    clientes = []
    if len(q) >= 2:
        clientes = Cliente.objects.filter(
            nome__icontains=q,
            deleted_at__isnull=True,
        )[:8]
    return render(request, 'customers/_indicador_results.html', {'clientes': clientes})