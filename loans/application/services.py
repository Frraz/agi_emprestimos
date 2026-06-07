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
        data_vencimento: date,
        observacoes: str = '',
        usuario=None,
    ):
        """Cria um empréstimo do tipo COMUM (sem parcelas fixas)."""
        from loans.infrastructure.models import Emprestimo

        _validar_financeiro(capital, taxa_mensal)
        cliente = _get_cliente(cliente_id)

        # Lança o juros do primeiro ciclo já na criação (sem capitalização):
        # a dívida total passa a ser capital + juros_acumulados desde o início.
        juros_primeiro_ciclo = CalculadoraEmprestimoComum.calcular_juros_mes(
            capital, taxa_mensal
        )

        emprestimo = Emprestimo.objects.create(
            cliente=cliente,
            tipo='comum',
            capital_inicial=capital,
            capital_atual=capital,
            taxa_juros_mensal=taxa_mensal,
            juros_acumulados=juros_primeiro_ciclo,
            data_ultimo_acumulo=data_vencimento,
            data_inicio=data_inicio,
            data_vencimento=data_vencimento,
            status='ativo',
            observacoes=observacoes,
            registrado_por=usuario,
            owner=usuario,
        )
        _audit(emprestimo, 'create', usuario)
        _registrar_movimento_emprestimo(emprestimo, usuario)
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
                owner=usuario,
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
        _registrar_movimento_emprestimo(emprestimo, usuario)
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

        # Domínio puro: sem acesso ao banco. Sem capitalização — paga juros
        # acumulados primeiro, depois abate o capital.
        resultado = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=emprestimo.capital_atual,
            valor_pago=valor,
            juros_acumulados=emprestimo.juros_acumulados,
        )

        novo_status = (
            'quitado' if resultado.capital_restante <= Decimal('0')
            else emprestimo.status
        )

        # Determina tipo de pagamento para relatório
        if resultado.capital_restante <= Decimal('0'):
            tipo = 'capital_total'
        elif resultado.capital_pago > Decimal('0'):
            tipo = 'capital_parcial'
        else:
            tipo = 'juros'

        with transaction.atomic():
            emprestimo.capital_atual = resultado.capital_restante
            emprestimo.juros_acumulados = resultado.juros_acumulados_restante
            emprestimo.status = novo_status
            if novo_status == 'quitado':
                emprestimo.data_quitacao = data_pagamento
            emprestimo.save(update_fields=[
                'capital_atual', 'juros_acumulados', 'status',
                'data_quitacao', 'updated_at',
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
                owner=usuario,
            )

        # Atualiza classificação do cliente (fora do atomic para não bloquear)
        _atualizar_classificacao_cliente(str(emprestimo.cliente_id))
        _audit(emprestimo, 'payment', usuario, {'pagamento_id': str(pagamento.id)})
        _registrar_movimento_recebimento(emprestimo, valor, usuario)

        return pagamento

    # ── Edição de pagamento (P4) ─────────────────────────────────────────────

    @staticmethod
    def editar_pagamento(
        pagamento_id: str,
        valor: Decimal,
        data_pagamento: date,
        observacoes: str = '',
        usuario=None,
    ):
        """
        Edita um pagamento (valor/data/observações) e recalcula o saldo do
        empréstimo. Sobrescreve a regra histórica de imutabilidade (decisão do
        cliente — sem senha, controle pelo usuário autenticado). Registra
        AuditLog da alteração.
        """
        from payments.infrastructure.models import Pagamento

        try:
            pag = Pagamento.objects.select_related('emprestimo', 'parcela').get(
                id=pagamento_id, deleted_at__isnull=True,
            )
        except Pagamento.DoesNotExist:
            raise EntidadeNaoEncontradaError(f'Pagamento não encontrado: {pagamento_id}')

        emp = pag.emprestimo
        antes = {'valor': str(pag.valor), 'data': str(pag.data_pagamento)}

        with transaction.atomic():
            pag.valor = _money(valor)
            pag.data_pagamento = data_pagamento
            pag.observacoes = observacoes
            pag.save(update_fields=['valor', 'data_pagamento', 'observacoes', 'updated_at'])

            if emp.tipo == 'comum':
                capital, juros = reconstruir_saldo_comum(emp, date.today())
                emp.capital_atual = capital
                emp.juros_acumulados = juros
                if capital <= Decimal('0'):
                    emp.status = 'quitado'
                    emp.data_quitacao = data_pagamento
                elif emp.status == 'quitado':
                    emp.status = 'ativo'
                    emp.data_quitacao = None
                emp.save(update_fields=[
                    'capital_atual', 'juros_acumulados', 'status',
                    'data_quitacao', 'updated_at',
                ])
            else:
                if pag.parcela_id:
                    _recompute_split_pagamento(pag)
                    _recompute_parcela_from_payments(pag.parcela)
                _recalcular_capital_parcelado(emp, data_pagamento)

        _atualizar_classificacao_cliente(str(emp.cliente_id))
        _audit(pag, 'update', usuario, {
            'antes': antes, 'depois': {'valor': str(pag.valor), 'data': str(pag.data_pagamento)},
        })
        return pag

    # ── Pagamento de PARCELAS (empréstimo parcelado) ─────────────────────────

    @staticmethod
    def registrar_pagamento_parcelas(
        emprestimo_id: str,
        parcela_ids: list,
        valor: Decimal,
        data_pagamento: date,
        observacoes: str = '',
        usuario=None,
        aplicar_excedente: bool = True,
    ) -> dict:
        """
        Registra pagamento de uma ou mais parcelas de um empréstimo PARCELADO.

        Distribui `valor` nas parcelas selecionadas (em ordem de número),
        suportando pagamento parcial e total. Se sobrar (excedente) e
        aplicar_excedente=True, o restante é aplicado automaticamente nas
        próximas parcelas em aberto. Retorna metadados para feedback visual.
        """
        from loans.domain.exceptions import EmprestimoInativoError

        emp = _get_emprestimo(emprestimo_id)
        if emp.tipo != 'parcelado':
            raise EmprestimoInativoError('Este empréstimo não é parcelado.')
        _validar_status_para_pagamento(emp)

        selecionadas = list(
            emp.parcelas.filter(id__in=parcela_ids, status__in=_PARCELA_ABERTA)
            .order_by('numero')
        )
        if not selecionadas:
            raise EntidadeNaoEncontradaError('Nenhuma parcela em aberto selecionada.')

        valor = _money(valor)
        restante = valor
        afetadas = []        # parcelas pagas dentro da seleção
        excedente_info = []  # parcelas afetadas pelo excedente automático

        with transaction.atomic():
            for p in selecionadas:
                if restante <= Decimal('0'):
                    break
                aplicado = min(restante, p.valor_em_aberto)
                _aplicar_em_parcela(emp, p, aplicado, data_pagamento, usuario, observacoes)
                restante = _money(restante - aplicado)
                afetadas.append({'numero': p.numero, 'valor_aplicado': aplicado})

            if restante > Decimal('0') and aplicar_excedente:
                ids_sel = [p.id for p in selecionadas]
                proximas = (
                    emp.parcelas.filter(status__in=_PARCELA_ABERTA)
                    .exclude(id__in=ids_sel).order_by('numero')
                )
                for p in proximas:
                    if restante <= Decimal('0'):
                        break
                    aplicado = min(restante, p.valor_em_aberto)
                    _aplicar_em_parcela(
                        emp, p, aplicado, data_pagamento, usuario,
                        'Excedente aplicado automaticamente',
                    )
                    restante = _money(restante - aplicado)
                    p.refresh_from_db()
                    excedente_info.append({
                        'numero': p.numero,
                        'valor_aplicado': aplicado,
                        'novo_em_aberto': p.valor_em_aberto,
                    })

            _recalcular_capital_parcelado(emp, data_pagamento)

        _atualizar_classificacao_cliente(str(emp.cliente_id))
        _audit(emp, 'payment', usuario, {'parcelas': [a['numero'] for a in afetadas]})
        _registrar_movimento_recebimento(emp, valor, usuario)

        return {
            'afetadas': afetadas,
            'excedente_info': excedente_info,
            'excedente_nao_aplicado': restante,
            'valor_total': valor,
            'quitado': emp.status == 'quitado',
        }

    # ── Remoção / restauração de PAGAMENTO ───────────────────────────────────

    @staticmethod
    def desativar_pagamento(pagamento_id: str, usuario=None):
        """Soft delete reversível de um pagamento + recálculo do saldo."""
        pag = _get_pagamento(pagamento_id, incluir_deletados=False)
        emp = pag.emprestimo
        with transaction.atomic():
            pag.soft_delete(usuario=usuario)
            recalcular_emprestimo(emp, date.today())
        _atualizar_classificacao_cliente(str(emp.cliente_id))
        _audit(pag, 'soft_delete', usuario)
        return pag

    @staticmethod
    def ativar_pagamento(pagamento_id: str, usuario=None):
        """Restaura um pagamento desativado + recálculo do saldo."""
        pag = _get_pagamento(pagamento_id, incluir_deletados=True)
        emp = pag.emprestimo
        with transaction.atomic():
            pag.restore()
            recalcular_emprestimo(emp, date.today())
        _atualizar_classificacao_cliente(str(emp.cliente_id))
        _audit(pag, 'restore', usuario)
        return pag

    @staticmethod
    def apagar_pagamento(pagamento_id: str, usuario=None):
        """Exclusão DEFINITIVA (hard delete) de um pagamento + recálculo do saldo."""
        pag = _get_pagamento(pagamento_id, incluir_deletados=True)
        emp = pag.emprestimo
        pag_id = str(pag.id)
        with transaction.atomic():
            _audit(pag, 'delete', usuario)
            pag.delete()
            recalcular_emprestimo(emp, date.today())
        _atualizar_classificacao_cliente(str(emp.cliente_id))
        return pag_id

    # ── Remoção / restauração de EMPRÉSTIMO ──────────────────────────────────

    @staticmethod
    def desativar_emprestimo(emprestimo_id: str, usuario=None):
        """Soft delete reversível do empréstimo + dos seus pagamentos (saem do
        caixa/juros recebidos enquanto desativados)."""
        emp = _get_emprestimo(emprestimo_id)
        with transaction.atomic():
            for pag in emp.pagamentos.filter(deleted_at__isnull=True):
                pag.soft_delete(usuario=usuario)
            emp.soft_delete(usuario=usuario)
        _atualizar_classificacao_cliente(str(emp.cliente_id))
        _audit(emp, 'soft_delete', usuario)
        return emp

    @staticmethod
    def ativar_emprestimo(emprestimo_id: str, usuario=None):
        """Restaura um empréstimo desativado + os seus pagamentos."""
        from loans.infrastructure.models import Emprestimo
        try:
            emp = Emprestimo.objects.get(id=emprestimo_id)
        except Emprestimo.DoesNotExist:
            raise EntidadeNaoEncontradaError(f'Empréstimo não encontrado: {emprestimo_id}')
        with transaction.atomic():
            emp.restore()
            for pag in emp.pagamentos.filter(deleted_at__isnull=False):
                pag.restore()
            recalcular_emprestimo(emp, date.today())
        _atualizar_classificacao_cliente(str(emp.cliente_id))
        _audit(emp, 'restore', usuario)
        return emp

    @staticmethod
    def apagar_emprestimo(emprestimo_id: str, usuario=None):
        """Exclusão DEFINITIVA (hard delete) em cascata de um empréstimo:
        pagamentos, movimentações de capital, parcelas e garantias."""
        from loans.infrastructure.models import Emprestimo
        try:
            emp = Emprestimo.objects.get(id=emprestimo_id)
        except Emprestimo.DoesNotExist:
            raise EntidadeNaoEncontradaError(f'Empréstimo não encontrado: {emprestimo_id}')
        with transaction.atomic():
            _audit(emp, 'delete', usuario)
            _hard_delete_emprestimo(emp)
        _atualizar_classificacao_cliente(str(emp.cliente_id))
        return str(emprestimo_id)

    # ── Edição de EMPRÉSTIMO ─────────────────────────────────────────────────

    @staticmethod
    def editar_emprestimo(
        emprestimo_id: str, usuario=None, observacoes=None,
        data_vencimento=None, taxa_mensal=None,
    ):
        """Edita campos seguros de um empréstimo. Para COMUM, taxa nova dispara
        recálculo do saldo. Parcelado ignora taxa (regeraria a tabela)."""
        emp = _get_emprestimo(emprestimo_id)
        antes = {
            'observacoes': emp.observacoes,
            'data_vencimento': str(emp.data_vencimento),
            'taxa': str(emp.taxa_juros_mensal),
        }
        with transaction.atomic():
            if observacoes is not None:
                emp.observacoes = observacoes
            if data_vencimento is not None:
                emp.data_vencimento = data_vencimento
            campos = ['observacoes', 'data_vencimento', 'updated_at']
            recalc = False
            if taxa_mensal is not None and emp.tipo == 'comum':
                _validar_financeiro(emp.capital_inicial, taxa_mensal)
                emp.taxa_juros_mensal = taxa_mensal
                campos.append('taxa_juros_mensal')
                recalc = True
            emp.save(update_fields=campos)
            if recalc:
                recalcular_emprestimo(emp, date.today())
        _audit(emp, 'update', usuario, {'antes': antes})
        return emp


# ── Helpers privados do módulo ─────────────────────────────────────────────

_PARCELA_ABERTA = ('pendente', 'parcialmente_pago', 'atrasado')


def _money(v) -> Decimal:
    from decimal import ROUND_HALF_UP
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def reconstruir_saldo_comum(emp, data_ref: date):
    """
    Reproduz a vida financeira de um empréstimo COMUM e devolve
    (capital_atual, juros_acumulados) corretos, sem capitalização (juros
    simples). Lança o 1º ciclo na criação e um ciclo por vencimento mensal,
    intercalando os pagamentos por data. Reutilizado pelo command
    recalcular_saldos e pela edição de pagamentos.
    """
    from dateutil.relativedelta import relativedelta

    taxa = emp.taxa_juros_mensal
    capital = emp.capital_inicial
    juros_acum = CalculadoraEmprestimoComum.calcular_juros_mes(capital, taxa)

    ancora = emp.data_vencimento or (emp.data_inicio + relativedelta(months=1))
    ciclos = []
    d = ancora + relativedelta(months=1)
    while d <= data_ref:
        ciclos.append(d)
        d += relativedelta(months=1)

    pagamentos = list(
        emp.pagamentos.filter(deleted_at__isnull=True)
        .order_by('data_pagamento', 'created_at')
    )
    i = 0
    for pag in pagamentos:
        while i < len(ciclos) and ciclos[i] <= pag.data_pagamento:
            juros_acum += CalculadoraEmprestimoComum.calcular_juros_mes(capital, taxa)
            i += 1
        res = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=capital, valor_pago=pag.valor, juros_acumulados=juros_acum,
        )
        capital = res.capital_restante
        juros_acum = res.juros_acumulados_restante
    while i < len(ciclos):
        juros_acum += CalculadoraEmprestimoComum.calcular_juros_mes(capital, taxa)
        i += 1

    return (max(Decimal('0'), capital), juros_acum)


def recalcular_emprestimo(emp, data_ref: date):
    """Recalcula o saldo armazenado de um empréstimo a partir dos seus pagamentos
    NÃO deletados. Usado depois de remover/restaurar pagamentos. Persiste
    capital_atual/juros_acumulados/status/data_quitacao (e status das parcelas)."""
    if emp.tipo == 'comum':
        capital, juros = reconstruir_saldo_comum(emp, data_ref)
        emp.capital_atual = capital
        emp.juros_acumulados = juros
        if capital <= Decimal('0'):
            emp.status = 'quitado'
            emp.data_quitacao = emp.data_quitacao or data_ref
        elif emp.status == 'quitado':
            emp.status = 'ativo'
            emp.data_quitacao = None
        emp.save(update_fields=[
            'capital_atual', 'juros_acumulados', 'status', 'data_quitacao', 'updated_at',
        ])
    else:
        for parcela in emp.parcelas.all():
            _recompute_parcela_from_payments(parcela)
        _recalcular_capital_parcelado(emp, data_ref)
        # _recalcular_capital_parcelado só quita; reverte se reabriu parcela/saldo.
        tem_aberta = emp.parcelas.filter(status__in=_PARCELA_ABERTA).exists()
        if emp.status == 'quitado' and tem_aberta and emp.capital_atual > Decimal('0'):
            emp.status = 'ativo'
            emp.data_quitacao = None
            emp.save(update_fields=['status', 'data_quitacao', 'updated_at'])


def _recompute_split_pagamento(pag):
    """Recalcula a divisão juros/capital de um pagamento de parcela a partir
    do seu valor atual (proporcional ao valor da parcela)."""
    parcela = pag.parcela
    if parcela.valor_parcela > Decimal('0'):
        prop = pag.valor / parcela.valor_parcela
    else:
        prop = Decimal('0')
    pag.valor_juros_pagos = _money(parcela.valor_juros * prop)
    pag.valor_capital_pago = _money(pag.valor - pag.valor_juros_pagos)
    pag.save(update_fields=['valor_juros_pagos', 'valor_capital_pago', 'updated_at'])


def _recompute_parcela_from_payments(parcela):
    """Recalcula valor_pago e status de uma parcela a partir dos seus
    pagamentos não deletados."""
    from django.db.models import Sum
    total = (
        parcela.pagamentos_parcela.filter(deleted_at__isnull=True)
        .aggregate(t=Sum('valor'))['t'] or Decimal('0')
    )
    parcela.valor_pago = _money(total)
    if parcela.valor_pago >= parcela.valor_parcela:
        parcela.status = 'pago'
    elif parcela.valor_pago > Decimal('0'):
        parcela.status = 'parcialmente_pago'
    else:
        parcela.status = 'pendente'
    parcela.save(update_fields=['valor_pago', 'status', 'updated_at'])


def _aplicar_em_parcela(emp, parcela, valor, data_pagamento, usuario, observacoes=''):
    """Aplica `valor` a uma parcela, atualiza seu status e grava o Pagamento.
    A divisão juros/capital é proporcional ao valor da parcela (apenas para
    relatório); o capital do empréstimo é recalculado à parte."""
    from payments.infrastructure.models import Pagamento

    valor = _money(valor)
    if parcela.valor_parcela > Decimal('0'):
        prop = valor / parcela.valor_parcela
    else:
        prop = Decimal('0')
    juros_part = _money(parcela.valor_juros * prop)
    capital_part = _money(valor - juros_part)

    parcela.valor_pago = _money(parcela.valor_pago + valor)
    parcela.data_pagamento = data_pagamento
    parcela.status = 'pago' if parcela.valor_pago >= parcela.valor_parcela else 'parcialmente_pago'
    parcela.save(update_fields=['valor_pago', 'data_pagamento', 'status', 'updated_at'])

    Pagamento.objects.create(
        emprestimo=emp,
        parcela=parcela,
        valor=valor,
        tipo='parcela',
        data_pagamento=data_pagamento,
        valor_juros_pagos=juros_part,
        valor_capital_pago=capital_part,
        capital_antes=emp.capital_atual,
        capital_depois=emp.capital_atual,
        observacoes=observacoes,
        registrado_por=usuario,
        owner=usuario,
    )


def _recalcular_capital_parcelado(emp, data_pagamento):
    """capital_atual = capital_inicial − principal pago. Quita o empréstimo
    quando não há mais parcelas em aberto."""
    from django.db.models import Sum

    principal_pago = (
        emp.pagamentos.filter(deleted_at__isnull=True)
        .aggregate(t=Sum('valor_capital_pago'))['t'] or Decimal('0')
    )
    emp.capital_atual = _money(max(Decimal('0'), emp.capital_inicial - principal_pago))

    tem_aberta = emp.parcelas.filter(status__in=_PARCELA_ABERTA).exists()
    if not tem_aberta or emp.capital_atual <= Decimal('0'):
        emp.status = 'quitado'
        emp.data_quitacao = data_pagamento
    emp.save(update_fields=['capital_atual', 'status', 'data_quitacao', 'updated_at'])

def _validar_financeiro(capital: Decimal, taxa: Decimal):
    if capital <= Decimal('0'):
        raise CapitalInvalidoError(f"Capital inválido: {capital}")
    # Taxa 0 é permitida (empréstimo sem juros); apenas negativos e >= 1 são inválidos.
    if not (Decimal('0') <= taxa < Decimal('1')):
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


def _get_pagamento(pagamento_id: str, incluir_deletados: bool = False):
    from payments.infrastructure.models import Pagamento
    qs = Pagamento.objects.select_related('emprestimo', 'parcela')
    if not incluir_deletados:
        qs = qs.filter(deleted_at__isnull=True)
    try:
        return qs.get(id=pagamento_id)
    except Pagamento.DoesNotExist:
        raise EntidadeNaoEncontradaError(f"Pagamento não encontrado: {pagamento_id}")


def _hard_delete_emprestimo(emp):
    """Remove DEFINITIVAMENTE um empréstimo e seus dependentes, respeitando as
    FKs PROTECT. Deve rodar dentro de transaction.atomic(). Não recalcula caixa
    (derivado de agregações que já ignoram o que foi apagado)."""
    from payments.infrastructure.models import Pagamento
    from core.models_config import MovimentacaoCapital
    # 1) pagamentos primeiro (PROTECT em emprestimo e parcela)
    Pagamento.objects.filter(emprestimo=emp).delete()
    # 2) movimentações de capital ligadas (senão virariam SET_NULL órfãs)
    MovimentacaoCapital.objects.filter(emprestimo=emp).delete()
    # 3) o empréstimo cascateia parcelas, garantias e documentos de garantia
    emp.delete()


def _validar_status_para_pagamento(emprestimo):
    if emprestimo.status == 'quitado':
        raise EmprestimoJaQuitadoError(f"Empréstimo {emprestimo.id} já quitado.")
    if emprestimo.status not in ('ativo', 'inadimplente'):
        raise EmprestimoInativoError(
            f"Empréstimo em status '{emprestimo.status}' não aceita pagamentos."
        )


def _registrar_movimento_emprestimo(emprestimo, usuario):
    if usuario is None:
        return
    try:
        from core.capital import registrar_movimento_emprestimo
        registrar_movimento_emprestimo(emprestimo, usuario, quando=emprestimo.data_inicio)
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Falha no movimento de capital (empréstimo)')


def _registrar_movimento_recebimento(emprestimo, valor, usuario):
    if usuario is None:
        return
    try:
        from core.capital import registrar_movimento_recebimento
        registrar_movimento_recebimento(emprestimo, valor, usuario)
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Falha no movimento de capital (recebimento)')


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