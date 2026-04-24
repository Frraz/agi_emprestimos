from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from loans.infrastructure.models import Emprestimo
from loans.application.services import EmprestimoService
from loans.interfaces.serializers import (
    EmprestimoSerializer, EmprestimoListSerializer,
    CriarEmprestimoComumSerializer, CriarEmprestimoParceladoSerializer,
    PagamentoComumSerializer,
)
from core.exceptions import AgiBaseException


class EmprestimoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Leitura via ViewSet padrão.
    Criação via actions customizadas (separa entrada por tipo).

    GET  /api/v1/emprestimos/                      → lista
    GET  /api/v1/emprestimos/{id}/                 → detalhe
    POST /api/v1/emprestimos/criar-comum/          → novo empréstimo comum
    POST /api/v1/emprestimos/criar-parcelado/      → novo empréstimo parcelado
    POST /api/v1/emprestimos/{id}/pagar/           → registra pagamento (comum)
    POST /api/v1/emprestimos/{id}/soft-delete/     → soft delete
    GET  /api/v1/emprestimos/{id}/simular-parcelas/→ simula sem persistir
    """
    queryset = Emprestimo.objects.filter(
        deleted_at__isnull=True
    ).select_related('cliente').prefetch_related('parcelas').order_by('-data_inicio')

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['tipo', 'status', 'subtipo_parcelado']
    search_fields = ['cliente__nome', 'cliente__cpf']
    ordering_fields = ['data_inicio', 'capital_inicial', 'capital_atual', 'status']

    def get_serializer_class(self):
        if self.action == 'list':
            return EmprestimoListSerializer
        return EmprestimoSerializer

    # ── Criação ────────────────────────────────────────────────────────────

    @action(detail=False, methods=['post'], url_path='criar-comum')
    def criar_comum(self, request):
        serializer = CriarEmprestimoComumSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        try:
            emp = EmprestimoService.criar_emprestimo_comum(
                cliente_id=str(d['cliente_id']),
                capital=d['capital'],
                taxa_mensal=d['taxa_mensal'],
                data_inicio=d['data_inicio'],
                observacoes=d.get('observacoes', ''),
                usuario=request.user,
            )
        except AgiBaseException as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EmprestimoSerializer(emp).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='criar-parcelado')
    def criar_parcelado(self, request):
        serializer = CriarEmprestimoParceladoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        try:
            emp = EmprestimoService.criar_emprestimo_parcelado(
                cliente_id=str(d['cliente_id']),
                capital=d['capital'],
                taxa_mensal=d['taxa_mensal'],
                n_parcelas=d['n_parcelas'],
                subtipo=d['subtipo'],
                data_inicio=d['data_inicio'],
                data_primeira_parcela=d['data_primeira_parcela'],
                observacoes=d.get('observacoes', ''),
                usuario=request.user,
            )
        except AgiBaseException as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(EmprestimoSerializer(emp).data, status=status.HTTP_201_CREATED)

    # ── Pagamento ──────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='pagar')
    def pagar(self, request, pk=None):
        emprestimo = self.get_object()
        if emprestimo.tipo != 'comum':
            return Response(
                {'detail': 'Use o endpoint de parcelas para empréstimos parcelados.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PagamentoComumSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        try:
            pagamento = EmprestimoService.registrar_pagamento_comum(
                emprestimo_id=str(emprestimo.id),
                valor=d['valor'],
                data_pagamento=d['data_pagamento'],
                observacoes=d.get('observacoes', ''),
                usuario=request.user,
            )
        except AgiBaseException as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        from payments.interfaces.serializers import PagamentoSerializer
        return Response(PagamentoSerializer(pagamento).data, status=status.HTTP_201_CREATED)

    # ── Simulação (sem persistir) ──────────────────────────────────────────

    @action(detail=False, methods=['post'], url_path='simular-parcelas')
    def simular_parcelas(self, request):
        """
        Retorna tabela de amortização sem criar nenhum registro.
        Útil para o Flutter mostrar a simulação antes de confirmar.
        """
        serializer = CriarEmprestimoParceladoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        from loans.domain.calculators import (
            CalculadoraEmprestimoParceladoFixo,
            CalculadoraEmprestimoParceladoSAC,
        )
        calc = (
            CalculadoraEmprestimoParceladoFixo
            if d['subtipo'] == 'fixo'
            else CalculadoraEmprestimoParceladoSAC
        )
        tabela = calc.gerar_tabela_amortizacao(
            capital=d['capital'],
            taxa_mensal=d['taxa_mensal'],
            n_parcelas=d['n_parcelas'],
            data_primeira_parcela=d['data_primeira_parcela'],
        )
        total_juros = sum(p.valor_juros for p in tabela)
        total_pago = sum(p.valor_parcela for p in tabela)

        return Response({
            'capital': d['capital'],
            'taxa_mensal': d['taxa_mensal'],
            'n_parcelas': d['n_parcelas'],
            'subtipo': d['subtipo'],
            'total_juros': total_juros,
            'total_a_pagar': total_pago,
            'parcelas': [
                {
                    'numero': p.numero,
                    'data_vencimento': p.data_vencimento,
                    'valor_parcela': p.valor_parcela,
                    'valor_principal': p.valor_principal,
                    'valor_juros': p.valor_juros,
                    'saldo_devedor_depois': p.saldo_devedor_depois,
                }
                for p in tabela
            ],
        })

    # ── Soft Delete ────────────────────────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='cancelar')
    def cancelar(self, request, pk=None):
        emp = self.get_object()
        if emp.status not in ('ativo',):
            return Response(
                {'detail': f"Não é possível cancelar empréstimo com status '{emp.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        emp.status = 'cancelado'
        emp.save(update_fields=['status', 'updated_at'])
        emp.soft_delete(usuario=request.user)
        return Response({'detail': 'Empréstimo cancelado.'}, status=status.HTTP_200_OK)