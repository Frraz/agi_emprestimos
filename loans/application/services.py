"""
Application Service para Empréstimos.
Orquestra: validação → cálculo de domínio → persistência → auditoria.
"""
from decimal import Decimal
from datetime import date

from django.db import transaction

from core.exceptions import EntidadeNaoEncontradaError
from loans.domain.calculators import (
    CalculadoraEmprestimoComum,
    CalculadoraEmprestimoParceladoFixo,
    CalculadoraEmprestimoParceladoSAC,
)
from loans.domain.exceptions import (
    CapitalInvalidoError,
    TaxaInvalidaError,
    ParcelasInsuficientesError,
    EmprestimoJaQuitadoError,
    EmprestimoInativoError,
)


class EmprestimoService:

    # ── Criação ────────────────────────────────────────────────────────────

    @staticmethod
    def criar_emprestimo_comum(
        cliente_id: str,
        capital: Decimal,
        taxa_mensal: Decimal,
        data_inicio: date,
        observacoes: str = '',
        usuario=None,
    ):
        """Cria um empréstimo do tipo COMUM (sem parcelas fixas)."""
        from loans.infrastructure.models import Emprestimo

        _validar_financeiro(capital, taxa_mensal)
        cliente = _get_cliente(cliente_id)

        emprestimo = Emprestimo.objects.create(
            cliente=cliente,
            tipo='comum',
            capital_inicial=capital,
            capital_atual=capital,
            taxa_juros_mensal=taxa_mensal,
            data_inicio=data_inicio,
            status='ativo',
            observacoes=observacoes,
            registrado_por=usuario,
        )
        _audit(emprestimo, 'create', usuario)
        return emprestimo

    @staticmethod
    def criar_emprestimo_parcelado(
        cliente_id: str,
        capital: Decimal,
        taxa_mensal: Decimal,
        n_parcelas: int,
        subtipo: str,
        data_inicio: date,
        data_primeira_parcela: date,
        observacoes: str = '',
        usuario=None,
    ):
        """
        Cria empréstimo parcelado e persiste a tabela de amortização completa.
        subtipo: 'fixo' ou 'sac'
        """
        from loans.infrastructure.models import Emprestimo, ParcelaEmprestimo

        _validar_financeiro(capital, taxa_mensal)

        if not (1 <= n_parcelas <= 360):
            raise ParcelasInsuficientesError(
                f"n_parcelas deve ser entre 1 e 360. Recebido: {n_parcelas}"
            )
        if subtipo not in ('fixo', 'sac'):
            raise ValueError(f"Subtipo inválido: '{subtipo}'. Use 'fixo' ou 'sac'.")

        cliente = _get_cliente(cliente_id)

        # Cálculo puro no domínio — sem Django
        calc = (
            CalculadoraEmprestimoParceladoFixo
            if subtipo == 'fixo'
            else CalculadoraEmprestimoParceladoSAC
        )
        tabela = calc.gerar_tabela_amortizacao(
            capital=capital,
            taxa_mensal=taxa_mensal,
            n_parcelas=n_parcelas,
            data_primeira_parcela=data_primeira_parcela,
        )

        with transaction.atomic():
            emprestimo = Emprestimo.objects.create(
                cliente=cliente,
                tipo='parcelado',
                subtipo_parcelado=subtipo,
                capital_inicial=capital,
                capital_atual=capital,
                taxa_juros_mensal=taxa_mensal,
                n_parcelas=n_parcelas,
                data_inicio=data_inicio,
                data_vencimento=tabela[-1].data_vencimento,
                status='ativo',
                observacoes=observacoes,
                registrado_por=usuario,
            )

            ParcelaEmprestimo.objects.bulk_create([
                ParcelaEmprestimo(
                    emprestimo=emprestimo,
                    numero=p.numero,
                    valor_parcela=p.valor_parcela,
                    valor_principal=p.valor_principal,
                    valor_juros=p.valor_juros,
                    saldo_devedor_antes=p.saldo_devedor_antes,
                    saldo_devedor_depois=p.saldo_devedor_depois,
                    data_vencimento=p.data_vencimento,
                    status='pendente',
                )
                for p in tabela
            ])

        _audit(emprestimo, 'create', usuario)
        return emprestimo

    # ── Pagamentos ─────────────────────────────────────────────────────────

    @staticmethod
    def registrar_pagamento_comum(
        emprestimo_id: str,
        valor: Decimal,
        data_pagamento: date,
        observacoes: str = '',
        usuario=None,
    ):
        """
        Registra pagamento em empréstimo COMUM.
        Aplica lógica de domínio e atualiza saldo devedor.
        """
        from loans.infrastructure.models import Emprestimo
        from payments.infrastructure.models import Pagamento

        emprestimo = _get_emprestimo(emprestimo_id)
        _validar_status_para_pagamento(emprestimo)

        # Domínio puro: sem acesso ao banco
        resultado = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=emprestimo.capital_atual,
            taxa_mensal=emprestimo.taxa_juros_mensal,
            valor_pago=valor,
        )

        novo_status = (
            'quitado' if resultado.capital_restante <= Decimal('0')
            else emprestimo.status
        )

        # Determina tipo de pagamento para relatório
        if resultado.capital_pago > Decimal('0') and resultado.juros_pagos > Decimal('0'):
            tipo = 'capital_total'
        elif resultado.capital_pago > Decimal('0'):
            tipo = 'capital_parcial'
        else:
            tipo = 'juros'

        with transaction.atomic():
            emprestimo.capital_atual = resultado.capital_restante
            emprestimo.status = novo_status
            if novo_status == 'quitado':
                emprestimo.data_quitacao = data_pagamento
            emprestimo.save(update_fields=[
                'capital_atual', 'status', 'data_quitacao', 'updated_at'
            ])

            pagamento = Pagamento.objects.create(
                emprestimo=emprestimo,
                valor=valor,
                tipo=tipo,
                data_pagamento=data_pagamento,
                valor_juros_pagos=resultado.juros_pagos,
                valor_capital_pago=resultado.capital_pago,
                capital_antes=resultado.capital_antes,
                capital_depois=resultado.capital_restante,
                observacoes=observacoes,
                registrado_por=usuario,
            )

        # Atualiza classificação do cliente (fora do atomic para não bloquear)
        _atualizar_classificacao_cliente(str(emprestimo.cliente_id))
        _audit(emprestimo, 'payment', usuario, {'pagamento_id': str(pagamento.id)})

        return pagamento


# ── Helpers privados do módulo ─────────────────────────────────────────────

def _validar_financeiro(capital: Decimal, taxa: Decimal):
    if capital <= Decimal('0'):
        raise CapitalInvalidoError(f"Capital inválido: {capital}")
    if not (Decimal('0') < taxa < Decimal('1')):
        raise TaxaInvalidaError(f"Taxa inválida: {taxa}. Use decimal entre 0 e 1.")


def _get_cliente(cliente_id: str):
    from customers.infrastructure.models import Cliente
    try:
        return Cliente.objects.get(id=cliente_id, deleted_at__isnull=True)
    except Cliente.DoesNotExist:
        raise EntidadeNaoEncontradaError(f"Cliente não encontrado: {cliente_id}")


def _get_emprestimo(emprestimo_id: str):
    from loans.infrastructure.models import Emprestimo
    try:
        return Emprestimo.objects.get(id=emprestimo_id, deleted_at__isnull=True)
    except Emprestimo.DoesNotExist:
        raise EntidadeNaoEncontradaError(f"Empréstimo não encontrado: {emprestimo_id}")


def _validar_status_para_pagamento(emprestimo):
    if emprestimo.status == 'quitado':
        raise EmprestimoJaQuitadoError(f"Empréstimo {emprestimo.id} já quitado.")
    if emprestimo.status not in ('ativo', 'inadimplente'):
        raise EmprestimoInativoError(
            f"Empréstimo em status '{emprestimo.status}' não aceita pagamentos."
        )


def _atualizar_classificacao_cliente(cliente_id: str):
    try:
        from customers.application.services import ClienteService
        ClienteService.atualizar_classificacao(cliente_id)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Falha ao atualizar classificação do cliente %s", cliente_id
        )


def _audit(obj, action: str, usuario, changes: dict = None):
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
            "Falha no audit log: %s %s", type(obj).__name__, obj.id
        )