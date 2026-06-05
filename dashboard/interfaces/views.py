from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages as flash
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from dashboard.application.metrics import calcular_metricas_dashboard


@login_required
def dashboard_view(request):
    from loans.infrastructure.models import Emprestimo
    from core.ownership import filtrar_por_usuario
    metricas = calcular_metricas_dashboard(user=request.user)
    emprestimos_recentes = filtrar_por_usuario(
        Emprestimo.objects.filter(deleted_at__isnull=True), request.user
    ).select_related('cliente').order_by('-created_at')[:8]
    return render(request, 'dashboard/index.html', {
        'metricas': metricas,
        'emprestimos_recentes': emprestimos_recentes,
    })


@login_required
def capital_config(request):
    """Gestão de capital: saldo, aportes/retiradas e histórico."""
    from core.models_config import CapitalOperacional, MovimentacaoCapital
    from core.capital import registrar_aporte, registrar_retirada
    from core.ownership import filtrar_por_usuario
    from decimal import Decimal, InvalidOperation

    config = CapitalOperacional.get_for_user(request.user)

    if request.method == 'POST':
        acao = request.POST.get('acao', '')
        descricao = request.POST.get('descricao', '')
        try:
            valor = Decimal((request.POST.get('valor', '0') or '0').replace(',', '.'))
            if valor <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            flash.error(request, 'Informe um valor válido.')
            return redirect('dashboard:capital-config')

        if acao == 'aporte':
            registrar_aporte(request.user, valor, descricao)
            flash.success(request, f'Crédito de R$ {valor:.2f} adicionado ao capital.')
        elif acao == 'retirada':
            registrar_retirada(request.user, valor, descricao)
            flash.success(request, f'Retirada de R$ {valor:.2f} registrada.')
        else:
            flash.error(request, 'Ação inválida.')
        return redirect('dashboard:capital-config')

    movimentacoes = filtrar_por_usuario(
        MovimentacaoCapital.objects.filter(deleted_at__isnull=True), request.user
    ).select_related('emprestimo__cliente')[:50]

    return render(request, 'dashboard/capital_config.html', {
        'config': config,
        'movimentacoes': movimentacoes,
    })


@login_required
def notificacoes_config(request):
    """Configurações > Notificações (estrutura — sem envio automático)."""
    from core.models_config import ConfiguracaoNotificacao

    cfg = ConfiguracaoNotificacao.get_for_user(request.user)
    if request.method == 'POST':
        cfg.ativo = bool(request.POST.get('ativo'))
        cfg.notificar_1_dia = bool(request.POST.get('notificar_1_dia'))
        cfg.notificar_3_dias = bool(request.POST.get('notificar_3_dias'))
        cfg.notificar_7_dias = bool(request.POST.get('notificar_7_dias'))
        cfg.save(update_fields=[
            'ativo', 'notificar_1_dia', 'notificar_3_dias', 'notificar_7_dias', 'updated_at',
        ])
        flash.success(request, 'Preferências de notificação salvas.')
        return redirect('dashboard:notificacoes-config')

    return render(request, 'dashboard/notificacoes.html', {'cfg': cfg})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def metricas_api(request):
    return Response(calcular_metricas_dashboard(user=request.user))