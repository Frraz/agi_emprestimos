"""
Application Service para Clientes.
Orquestra: validação de domínio → persistência → auditoria.
Nunca coloque esta lógica em views ou serializers.
"""
from django.db import models as dj_models
from core.exceptions import EntidadeNaoEncontradaError
from core.utils import validar_cpf, formatar_cpf
from customers.domain.exceptions import CPFInvalidoError, ClienteJaExisteError


class ClienteService:

    @staticmethod
    def criar_cliente(dados: dict, usuario=None):
        """
        Cria cliente com validação completa.
        dados: dict com campos do model Cliente.
        """
        from customers.infrastructure.models import Cliente

        cpf = formatar_cpf(dados.get('cpf', ''))

        if not validar_cpf(cpf):
            raise CPFInvalidoError(f"CPF inválido: {dados.get('cpf')}")

        if Cliente.objects.filter(cpf=cpf, deleted_at__isnull=True).exists():
            raise ClienteJaExisteError(f"CPF já cadastrado: {cpf}")

        dados = {**dados, 'cpf': cpf}
        cliente = Cliente.objects.create(**dados)

        _registrar_auditoria(cliente, 'create', usuario)
        return cliente

    @staticmethod
    def atualizar_classificacao(cliente_id: str) -> str:
        """
        Recalcula e persiste a classificação (verde/amarelo/vermelho)
        baseado no histórico atual de empréstimos e parcelas.
        Deve ser chamado após cada pagamento ou marcação de inadimplência.
        """
        from customers.infrastructure.models import Cliente
        from loans.domain.calculators import CalculadoraInadimplencia

        try:
            cliente = Cliente.objects.get(id=cliente_id, deleted_at__isnull=True)
        except Cliente.DoesNotExist:
            raise EntidadeNaoEncontradaError(f"Cliente não encontrado: {cliente_id}")

        emprestimos_data = list(
            cliente.emprestimos
            .filter(deleted_at__isnull=True)
            .annotate(
                parcelas_atrasadas=dj_models.Count(
                    'parcelas',
                    filter=dj_models.Q(parcelas__status='atrasado'),
                )
            )
            .values('status', 'parcelas_atrasadas')
        )

        classificacao = CalculadoraInadimplencia.classificar_cliente(emprestimos_data)

        if cliente.classificacao != classificacao:
            cliente.classificacao = classificacao
            cliente.save(update_fields=['classificacao', 'updated_at'])

        return classificacao


# ── Helper privado (módulo-level para não poluir a classe) ─────────────────

def _registrar_auditoria(obj, action: str, usuario, changes: dict = None):
    try:
        from audit.infrastructure.models import AuditLog
        from django.contrib.contenttypes.models import ContentType
        AuditLog.objects.create(
            content_type=ContentType.objects.get_for_model(type(obj)),
            object_id=str(obj.id),
            action=action,
            changes=changes or {},
            usuario=usuario,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Falha ao registrar auditoria para %s %s", type(obj).__name__, obj.id
        )