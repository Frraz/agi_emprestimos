from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from customers.infrastructure.models import Cliente
from customers.application.services import ClienteService
from customers.interfaces.serializers import ClienteSerializer, ClienteListSerializer
from core.exceptions import AgiBaseException


class ClienteViewSet(viewsets.ModelViewSet):
    """
    CRUD completo de clientes.
    GET    /api/v1/clientes/           → lista
    POST   /api/v1/clientes/           → cria
    GET    /api/v1/clientes/{id}/      → detalhe
    PUT    /api/v1/clientes/{id}/      → atualização completa
    PATCH  /api/v1/clientes/{id}/      → atualização parcial
    DELETE /api/v1/clientes/{id}/      → soft delete
    POST   /api/v1/clientes/{id}/recalcular_classificacao/
    """
    queryset = Cliente.objects.filter(deleted_at__isnull=True).order_by('nome')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['classificacao', 'origem', 'cidade', 'estado']
    search_fields = ['nome', 'cpf', 'telefone_principal', 'email']
    ordering_fields = ['nome', 'created_at', 'classificacao']

    def get_serializer_class(self):
        if self.action == 'list':
            return ClienteListSerializer
        return ClienteSerializer

    def perform_create(self, serializer):
        try:
            cliente = ClienteService.criar_cliente(
                dados=serializer.validated_data,
                usuario=self.request.user,
            )
            # Força o serializer a usar o objeto criado pelo service
            serializer.instance = cliente
        except AgiBaseException as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': str(e)})

    def perform_destroy(self, instance):
        instance.soft_delete(usuario=self.request.user)

    @action(detail=True, methods=['post'], url_path='recalcular-classificacao')
    def recalcular_classificacao(self, request, pk=None):
        """Força recálculo da classificação de risco do cliente."""
        cliente = self.get_object()
        nova = ClienteService.atualizar_classificacao(str(cliente.id))
        return Response({
            'id': str(cliente.id),
            'classificacao_anterior': cliente.classificacao,
            'classificacao_nova': nova,
        })