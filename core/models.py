"""
BaseModel e SoftDeleteModel — fundação de todos os models do sistema.

Decisões de design:
- UUID como PK: evita IDs sequenciais previsíveis e facilita sincronização offline (Flutter).
- Soft delete via deleted_at: preserva histórico financeiro — nunca destrua dados de pagamento.
- updated_at: usado como vetor de sincronização no app Flutter (offline-first).
"""
import uuid
from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """
    Model base com UUID, timestamps e soft delete.
    Todos os models do sistema devem herdar deste.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None

    def soft_delete(self, usuario=None) -> None:
        """Marca como deletado sem remover do banco."""
        self.deleted_at = timezone.now()
        self.save(update_fields=['deleted_at', 'updated_at'])

    def restore(self) -> None:
        """Restaura um registro deletado via soft delete."""
        self.deleted_at = None
        self.save(update_fields=['deleted_at', 'updated_at'])


class ActiveManager(models.Manager):
    """
    Manager padrão que retorna apenas registros não deletados.
    Use nos models onde o comportamento padrão deve ignorar deletados.
    """
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(BaseModel):
    """
    Extensão do BaseModel com manager que filtra soft deletes automaticamente.
    Use quando o `.objects.all()` deve ignorar registros deletados por padrão.
    Acesse todos (incluindo deletados) via `.all_objects.all()`.
    """
    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

from core.models_config import CapitalOperacional  # noqa