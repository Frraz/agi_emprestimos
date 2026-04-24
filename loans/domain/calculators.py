"""
Calculadoras financeiras do sistema Agi Empréstimos.

REGRA ABSOLUTA: nenhuma lógica de juros, amortização, saldo devedor ou
parcelas pode existir fora deste módulo. Views, serializers e services
apenas orquestram — nunca calculam.

Todos os cálculos usam Decimal com ROUND_HALF_UP (padrão financeiro BR).
"""
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from datetime import date
from typing import List


# ── Utilitário central ─────────────────────────────────────────────────────

def _r(valor: Decimal, casas: int = 2) -> Decimal:
    """Arredondamento financeiro padrão. Alias curto para uso interno."""
    quantizer = Decimal(10) ** -casas
    return valor.quantize(quantizer, rounding=ROUND_HALF_UP)


# ── Data Transfer Objects ──────────────────────────────────────────────────

@dataclass
class ParcelaCalculada:
    """DTO com dados de uma parcela gerada pela tabela de amortização."""
    numero: int
    data_vencimento: date
    valor_parcela: Decimal
    valor_principal: Decimal   # Amortização do capital
    valor_juros: Decimal
    saldo_devedor_antes: Decimal
    saldo_devedor_depois: Decimal


@dataclass
class ResultadoPagamento:
    """DTO com resultado de um pagamento aplicado a um empréstimo COMUM."""
    capital_restante: Decimal
    juros_pagos: Decimal
    capital_pago: Decimal
    excedente: Decimal   # Valor pago além do necessário (troco)
    capital_antes: Decimal


# ── Empréstimo COMUM ───────────────────────────────────────────────────────

class CalculadoraEmprestimoComum:
    """
    EMPRÉSTIMO COMUM — sem parcela fixa.

    Regras:
    1. Juros simples mensais: J = capital_atual × taxa_mensal
    2. Pagamento cobre juros PRIMEIRO, depois abate capital.
    3. Se valor_pago < juros_devidos → diferença capitaliza no saldo.
    4. capital_atual ≥ 0 sempre (nunca negativo).
    """

    @staticmethod
    def calcular_juros_mes(capital: Decimal, taxa_mensal: Decimal) -> Decimal:
        """Juros do mês corrente sobre o capital em aberto."""
        return _r(capital * taxa_mensal)

    @staticmethod
    def calcular_total_quitacao(capital: Decimal, taxa_mensal: Decimal) -> Decimal:
        """Valor exato para quitar: capital + juros do mês."""
        juros = CalculadoraEmprestimoComum.calcular_juros_mes(capital, taxa_mensal)
        return _r(capital + juros)

    @staticmethod
    def aplicar_pagamento(
        capital_atual: Decimal,
        taxa_mensal: Decimal,
        valor_pago: Decimal,
    ) -> ResultadoPagamento:
        """
        Aplica um pagamento ao empréstimo e retorna o novo estado.

        Comportamento:
        - valor_pago cobre juros primeiro.
        - O excedente abate o capital.
        - Se valor_pago < juros → diferença é adicionada ao capital (capitalização).
        - Nunca retorna capital negativo.
        """
        juros_devidos = CalculadoraEmprestimoComum.calcular_juros_mes(
            capital_atual, taxa_mensal
        )
        capital_antes = capital_atual

        if valor_pago >= juros_devidos:
            # Pagamento cobre os juros — abate capital com o restante
            juros_pagos = juros_devidos
            capital_abatido = _r(valor_pago - juros_devidos)
            capital_abatido = min(capital_abatido, capital_atual)
            novo_capital = _r(capital_atual - capital_abatido)
            excedente = _r(valor_pago - juros_pagos - capital_abatido)
        else:
            # Pagamento insuficiente para cobrir os juros
            # Juros não pagos capitalizam no saldo devedor
            juros_pagos = valor_pago
            juros_nao_cobertos = _r(juros_devidos - valor_pago)
            capital_abatido = Decimal('0')
            novo_capital = _r(capital_atual + juros_nao_cobertos)
            excedente = Decimal('0')

        return ResultadoPagamento(
            capital_restante=novo_capital,
            juros_pagos=juros_pagos,
            capital_pago=capital_abatido,
            excedente=excedente,
            capital_antes=capital_antes,
        )


# ── Empréstimo PARCELADO — Parcela Fixa ───────────────────────────────────

class CalculadoraEmprestimoParceladoFixo:
    """
    PARCELADO FIXO — juros simples sobre capital inicial.

    Fórmula:
      total_juros  = capital × taxa × n_parcelas
      total        = capital + total_juros
      valor_parcela = total / n_parcelas

    Diferença em relação à Tabela Price (juros compostos):
    - Aqui os juros são calculados sobre o capital INICIAL em cada parcela.
    - Mais simples de explicar ao tomador e comum em crédito informal.
    - Componente de capital por parcela = capital / n (constante).
    - Componente de juros por parcela   = capital × taxa (constante).
    """

    @staticmethod
    def calcular_valor_parcela(
        capital: Decimal,
        taxa_mensal: Decimal,
        n_parcelas: int,
    ) -> Decimal:
        total_juros = _r(capital * taxa_mensal * n_parcelas)
        return _r((capital + total_juros) / n_parcelas)

    @staticmethod
    def gerar_tabela_amortizacao(
        capital: Decimal,
        taxa_mensal: Decimal,
        n_parcelas: int,
        data_primeira_parcela: date,
    ) -> List[ParcelaCalculada]:
        from dateutil.relativedelta import relativedelta

        valor_parcela = CalculadoraEmprestimoParceladoFixo.calcular_valor_parcela(
            capital, taxa_mensal, n_parcelas
        )
        juros_por_parcela = _r(capital * taxa_mensal)
        amort_por_parcela = _r(valor_parcela - juros_por_parcela)

        parcelas: List[ParcelaCalculada] = []
        saldo = capital

        for i in range(1, n_parcelas + 1):
            data_venc = data_primeira_parcela + relativedelta(months=i - 1)
            saldo_antes = saldo

            if i == n_parcelas:
                # Última parcela: quitar o saldo restante para zerar possíveis
                # diferenças de arredondamento acumuladas
                amort = saldo
                juros = _r(valor_parcela - amort)
                if juros < Decimal('0'):
                    juros = Decimal('0')
                valor = amort + juros
            else:
                amort = amort_por_parcela
                juros = juros_por_parcela
                valor = valor_parcela

            saldo_depois = _r(max(Decimal('0'), saldo_antes - amort))

            parcelas.append(ParcelaCalculada(
                numero=i,
                data_vencimento=data_venc,
                valor_parcela=_r(valor),
                valor_principal=_r(amort),
                valor_juros=_r(juros),
                saldo_devedor_antes=_r(saldo_antes),
                saldo_devedor_depois=saldo_depois,
            ))
            saldo = saldo_depois

        return parcelas


# ── Empréstimo PARCELADO — SAC (Parcela Decrescente) ──────────────────────

class CalculadoraEmprestimoParceladoSAC:
    """
    PARCELADO SAC — Sistema de Amortização Constante.

    Fórmula:
      amortização    = capital / n_parcelas  (CONSTANTE em todas as parcelas)
      juros(i)       = saldo_devedor(i) × taxa  (DECRESCE a cada parcela)
      parcela(i)     = amortização + juros(i)   (DECRESCE a cada parcela)

    Vantagem para o tomador: total de juros pago é menor que no modelo Fixo.
    """

    @staticmethod
    def calcular_amortizacao_constante(
        capital: Decimal, n_parcelas: int
    ) -> Decimal:
        return _r(capital / n_parcelas)

    @staticmethod
    def gerar_tabela_amortizacao(
        capital: Decimal,
        taxa_mensal: Decimal,
        n_parcelas: int,
        data_primeira_parcela: date,
    ) -> List[ParcelaCalculada]:
        from dateutil.relativedelta import relativedelta

        amort_constante = _r(capital / n_parcelas)
        parcelas: List[ParcelaCalculada] = []
        saldo = capital

        for i in range(1, n_parcelas + 1):
            data_venc = data_primeira_parcela + relativedelta(months=i - 1)
            saldo_antes = saldo
            juros = _r(saldo * taxa_mensal)

            # Na última parcela, quitamos o saldo exato (evita R$ 0,01 sobrando)
            amort = saldo if i == n_parcelas else amort_constante
            valor_parcela = _r(amort + juros)
            saldo_depois = _r(max(Decimal('0'), saldo - amort))

            parcelas.append(ParcelaCalculada(
                numero=i,
                data_vencimento=data_venc,
                valor_parcela=valor_parcela,
                valor_principal=_r(amort),
                valor_juros=juros,
                saldo_devedor_antes=_r(saldo_antes),
                saldo_devedor_depois=saldo_depois,
            ))
            saldo = saldo_depois

        return parcelas


# ── Inadimplência e Classificação ─────────────────────────────────────────

class CalculadoraInadimplencia:
    """
    Centraliza as regras de classificação de risco do cliente e da operação.
    """

    @staticmethod
    def classificar_cliente(emprestimos: list) -> str:
        """
        Recebe lista de dicts com {'status': str, 'parcelas_atrasadas': int}.
        Retorna: 'verde' | 'amarelo' | 'vermelho'

        Regras:
          vermelho: qualquer empréstimo com status 'inadimplente'
                    OU soma de parcelas atrasadas ≥ 3
          amarelo:  soma de parcelas atrasadas entre 1 e 2
          verde:    sem atrasos
        """
        total_atrasadas = sum(e.get('parcelas_atrasadas', 0) for e in emprestimos)
        tem_inadimplente = any(e.get('status') == 'inadimplente' for e in emprestimos)

        if tem_inadimplente or total_atrasadas >= 3:
            return 'vermelho'
        if total_atrasadas >= 1:
            return 'amarelo'
        return 'verde'

    @staticmethod
    def calcular_exposicao_ajustada(
        saldo_devedor: Decimal,
        valor_garantia: Decimal,
        percentual_recuperacao: Decimal = Decimal('0.70'),
    ) -> dict:
        """
        Exposição real considerando o valor recuperável das garantias.

        perda_ajustada = max(0, saldo_devedor − valor_garantia × percentual_recuperacao)
        cobertura      = min(1, recuperacao_estimada / saldo_devedor)
        """
        recuperacao = _r(valor_garantia * percentual_recuperacao)
        perda = _r(max(Decimal('0'), saldo_devedor - recuperacao))
        cobertura = (
            _r(min(Decimal('1'), recuperacao / saldo_devedor) * 100)
            if saldo_devedor > Decimal('0') else Decimal('100')
        )

        return {
            'saldo_devedor': saldo_devedor,
            'valor_garantia': valor_garantia,
            'recuperacao_estimada': recuperacao,
            'perda_ajustada': perda,
            'percentual_cobertura': cobertura,
        }