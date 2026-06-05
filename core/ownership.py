"""
Isolamento de dados por usuário (multi-tenant leve).

Cada registro de dados do operador pertence a um `owner` (User). Registros
LEGADOS — anteriores à introdução do isolamento — têm owner = NULL e são
tratados como COMPARTILHADOS: visíveis a todos os usuários existentes. Os
registros novos sempre recebem o usuário autenticado como owner, ficando
isolados dos demais.

Uso típico:
  - Web views:   qs = filtrar_por_usuario(Model.objects.all(), request.user)
  - DRF viewsets: herdar de OwnedViewSetMixin
  - Serviços/cron/testes (varredura global): escopo_opcional(qs, user=None)
"""
from django.conf import settings
from django.db import models


def owner_field(**kwargs):
    """FK padrão de propriedade.

    Nullable de propósito: NULL = registro legado compartilhado. on_delete
    SET_NULL para nunca destruir dado financeiro ao remover um usuário.
    """
    return models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        db_index=True,
        **kwargs,
    )


class OwnedModel(models.Model):
    """Mixin abstrato que adiciona `owner`. Útil para models novos."""
    owner = owner_field()

    class Meta:
        abstract = True


def filtrar_por_usuario(qs, user):
    """Restringe um queryset aos registros do usuário + legado (owner NULL).

    Usuário ausente/anônimo → queryset vazio (fail-safe).
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return qs.none()
    return qs.filter(models.Q(owner=user) | models.Q(owner__isnull=True))


def escopo_opcional(qs, user):
    """Como filtrar_por_usuario, mas user=None significa SEM filtro (todos).

    Para uso interno/cron/testes onde a varredura é global e intencional.
    """
    if user is None:
        return qs
    return filtrar_por_usuario(qs, user)


class OwnedViewSetMixin:
    """ViewSet DRF: filtra por dono e seta owner na criação."""

    def get_queryset(self):
        return filtrar_por_usuario(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
