"""
Log de auditoria — rastreabilidade completa de todas as operações relevantes.
Este model é append-only: nunca atualize ou delete registros de auditoria.
"""
import uuid
from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class AuditLog(models.Model):
    """
    Registra qualquer alteração relevante no sistema.
    Usa GenericForeignKey para apontar para qualquer entidade.
    """

    ACTION_CHOICES = [
        ('create', 'Criação'),
        ('update', 'Atualização'),
        ('delete', 'Exclusão (Soft Delete)'),
        ('restore', 'Restauração'),
        ('payment', 'Pagamento Registrado'),
        ('status_change', 'Mudança de Status'),
        ('classification_change', 'Mudança de Classificação'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Aponta para qualquer model do sistema
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=36, db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    action = models.CharField(max_length=25, choices=ACTION_CHOICES, db_index=True)

    # {'campo': ['valor_antes', 'valor_depois']} ou dados livres da operação
    changes = models.JSONField(default=dict)

    # Contexto da operação
    usuario = models.ForeignKey(
        'auth.User', null=True, on_delete=models.SET_NULL
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Log de Auditoria'
        verbose_name_plural = 'Logs de Auditoria'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['usuario', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]

    def __str__(self):
        return (
            f"[{self.get_action_display()}] "
            f"{self.content_type} #{self.object_id} "
            f"por {self.usuario} em {self.created_at:%d/%m/%Y %H:%M}"
        )