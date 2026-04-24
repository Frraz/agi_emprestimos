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
    metricas = calcular_metricas_dashboard()
    emprestimos_recentes = Emprestimo.objects.filter(
        deleted_at__isnull=True
    ).select_related('cliente').order_by('-created_at')[:8]
    return render(request, 'dashboard/index.html', {
        'metricas': metricas,
        'emprestimos_recentes': emprestimos_recentes,
    })


@login_required
def capital_config(request):
    """Tela para o operador informar seu capital total disponível."""
    from core.models_config import CapitalOperacional
    from decimal import Decimal

    config = CapitalOperacional.get_instance()

    if request.method == 'POST':
        try:
            valor = Decimal(request.POST.get('total_capital', '0').replace(',', '.'))
            if valor < 0:
                raise ValueError
            config.total_capital = valor
            config.observacoes = request.POST.get('observacoes', '')
            config.save(update_fields=['total_capital', 'observacoes', 'updated_at'])
            flash.success(request, f'Capital total atualizado para R$ {valor:,.2f}')
            return redirect('dashboard:dashboard-index')
        except (ValueError, Exception):
            flash.error(request, 'Valor inválido.')

    return render(request, 'dashboard/capital_config.html', {'config': config})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def metricas_api(request):
    return Response(calcular_metricas_dashboard())