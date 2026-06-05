from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages as flash
from django.core.paginator import Paginator
from django.db.models import Q

from customers.infrastructure.models import Cliente, TagCliente
from customers.interfaces.forms import ClienteForm
from core.exceptions import AgiBaseException
from core.ownership import filtrar_por_usuario
import urllib.request
import json


def _tags_do_usuario(request):
    return filtrar_por_usuario(TagCliente.objects.all(), request.user)


@login_required
def cliente_list(request):
    q = request.GET.get('q', '').strip()
    classificacao = request.GET.get('classificacao', '')
    tag = request.GET.get('tag', '')

    qs = filtrar_por_usuario(
        Cliente.objects.filter(deleted_at__isnull=True), request.user
    ).prefetch_related('tags').order_by('nome')
    if q:
        qs = qs.filter(
            Q(nome__icontains=q) | Q(cpf__icontains=q) | Q(telefone_principal__icontains=q)
        )
    if classificacao:
        qs = qs.filter(classificacao=classificacao)
    if tag:
        qs = qs.filter(tags__id=tag)

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page', 1))

    ctx = {
        'page': page, 'q': q, 'classificacao': classificacao, 'tag': tag,
        'tags': _tags_do_usuario(request), 'total': qs.count(),
    }
    # HTMX: retorna só as linhas da tabela
    if request.htmx:
        return render(request, 'customers/_rows.html', ctx)
    return render(request, 'customers/list.html', ctx)


@login_required
def tag_manage(request):
    """Gerencia (lista + cria) tags do operador."""
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        cor = request.POST.get('cor', 'slate')
        if nome:
            TagCliente.objects.create(owner=request.user, nome=nome[:40], cor=cor)
            flash.success(request, f'Tag "{nome}" criada.')
        return redirect('web_customers:tags')
    return render(request, 'customers/tags.html', {
        'tags': _tags_do_usuario(request).order_by('nome'),
        'cores': TagCliente.CORES,
    })


@login_required
def tag_delete(request, pk):
    tag = get_object_or_404(_tags_do_usuario(request), pk=pk)
    if request.method == 'POST':
        nome = tag.nome
        tag.delete()
        flash.success(request, f'Tag "{nome}" removida.')
    return redirect('web_customers:tags')


@login_required
def cliente_set_tags(request, pk):
    """Define as tags de um cliente (checkboxes do detalhe)."""
    cliente = _cliente_do_usuario(request, pk)
    if request.method == 'POST':
        ids = request.POST.getlist('tags')
        tags = _tags_do_usuario(request).filter(id__in=ids)
        cliente.tags.set(tags)
        flash.success(request, 'Tags atualizadas.')
    return redirect('web_customers:detail', pk=cliente.id)


def _cliente_do_usuario(request, pk):
    """Cliente acessível ao usuário (dono ou legado). 404 caso contrário."""
    return get_object_or_404(
        filtrar_por_usuario(Cliente.objects.filter(deleted_at__isnull=True), request.user),
        pk=pk,
    )


@login_required
def cliente_detail(request, pk):
    cliente = _cliente_do_usuario(request, pk)
    emprestimos = cliente.emprestimos.filter(
        deleted_at__isnull=True
    ).order_by('-data_inicio')
    return render(request, 'customers/detail.html', {
        'cliente': cliente,
        'emprestimos': emprestimos,
        'tags': _tags_do_usuario(request).order_by('nome'),
        'tags_cliente_ids': list(cliente.tags.values_list('id', flat=True)),
    })


@login_required
def cliente_create(request):
    if request.method == 'POST':
        form = ClienteForm(request.POST, request.FILES)
        if form.is_valid():
            cliente = form.save(commit=False)
            cliente.owner = request.user
            cliente.save()
            _audit(cliente, 'create', request.user)
            flash.success(request, f'Cliente {cliente.nome} cadastrado com sucesso.')
            return redirect('web_customers:detail', pk=cliente.id)
    else:
        form = ClienteForm()
    return render(request, 'customers/form.html', {'form': form, 'acao': 'Cadastrar'})


@login_required
def cliente_update(request, pk):
    cliente = _cliente_do_usuario(request, pk)
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
    cliente = _cliente_do_usuario(request, pk)
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
        clientes = filtrar_por_usuario(
            Cliente.objects.filter(nome__icontains=q, deleted_at__isnull=True),
            request.user,
        )[:8]
    return render(request, 'customers/_indicador_results.html', {'clientes': clientes})