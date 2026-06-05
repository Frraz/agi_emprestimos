from rest_framework import viewsets
from collaterals.infrastructure.models import Garantia
from collaterals.interfaces.serializers import GarantiaSerializer
from core.ownership import OwnedViewSetMixin


class GarantiaViewSet(OwnedViewSetMixin, viewsets.ModelViewSet):
    queryset = Garantia.objects.filter(
        deleted_at__isnull=True
    ).select_related('emprestimo__cliente').prefetch_related('documentos')
    serializer_class = GarantiaSerializer
    filterset_fields = ['tipo', 'emprestimo']

    def perform_destroy(self, instance):
        instance.soft_delete()