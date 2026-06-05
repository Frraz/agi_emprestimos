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
    juros_acumulados_restante: Decimal = Decimal('0')  # Juros em atraso ainda em aberto


# ── Empréstimo COMUM ───────────────────────────────────────────────────────

class CalculadoraEmprestimoComum:
    """
    EMPRÉSTIMO COMUM — sem parcela fixa. JUROS SIMPLES, SEM capitalização.

    Regras:
    1. Juros de um ciclo: J = capital_atual × taxa_mensal. Incidem SEMPRE sobre o
       capital em aberto (que nunca cresce) — nunca sobre juros já lançados.
    2. Os juros de cada ciclo são LANÇADOS uma única vez por ciclo no acumulador
       `juros_acumulados` (na criação do empréstimo e a cada vencimento, pelo cron).
       `juros_acumulados` NÃO rende juros → não existe "juros sobre juros".
    3. Um pagamento quita primeiro os juros acumulados, depois abate o capital.
    4. Pagamento insuficiente NÃO aumenta o capital: o que falta apenas permanece
       em `juros_acumulados` (saldo de juros em atraso).
    5. capital_atual ≥ 0 sempre.

    Consequência: a dívida total (capital + juros_acumulados) é fixa entre
    lançamentos de juros. Pagar R$719,99 de uma dívida de R$720 deixa exatamente
    R$0,01, independentemente de quantos pagamentos parciais forem feitos.
    """

    @staticmethod
    def calcular_juros_mes(capital: Decimal, taxa_mensal: Decimal) -> Decimal:
        """Juros de um ciclo sobre o capital em aberto (projeção / lançamento)."""
        return _r(capital * taxa_mensal)

    @staticmethod
    def calcular_total_quitacao(
        capital: Decimal, juros_acumulados: Decimal = Decimal('0')
    ) -> Decimal:
        """Valor exato para quitar agora: capital + juros já lançados (acumulados)."""
        return _r(capital + juros_acumulados)

    @staticmethod
    def aplicar_pagamento(
        capital_atual: Decimal,
        valor_pago: Decimal,
        juros_acumulados: Decimal = Decimal('0'),
    ) -> ResultadoPagamento:
        """
        Aplica um pagamento ao empréstimo e retorna o novo estado.

        Ordem de quitação: juros acumulados → capital → excedente.
        NÃO lança novos juros (isso ocorre na criação e a cada ciclo, pelo cron),
        portanto o saldo nunca cresce por pagar em partes nem por atraso.
        """
        capital_antes = capital_atual
        juros_acumulados = _r(juros_acumulados)

        if valor_pago >= juros_acumulados:
            # Cobre todos os juros em aberto — o restante abate o capital
            juros_pagos = juros_acumulados
            sobra = _r(valor_pago - juros_acumulados)
            capital_abatido = min(sobra, capital_atual)
            novo_capital = _r(capital_atual - capital_abatido)
            excedente = _r(sobra - capital_abatido)
            novo_juros_acumulados = Decimal('0')
        else:
            # Pagamento insuficiente para os juros em aberto.
            # SEM capitalização: o capital permanece intacto e o que falta de
            # juros continua em juros_acumulados (não vira capital, não rende juros).
            juros_pagos = valor_pago
            capital_abatido = Decimal('0')
            novo_capital = capital_atual
            excedente = Decimal('0')
            novo_juros_acumulados = _r(juros_acumulados - valor_pago)

        return ResultadoPagamento(
            capital_restante=novo_capital,
            juros_pagos=juros_pagos,
            capital_pago=capital_abatido,
            excedente=excedente,
            capital_antes=capital_antes,
            juros_acumulados_restante=novo_juros_acumulados,
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


# ── Atraso (detecção baseada em data) ──────────────────────────────────────

class CalculadoraAtraso:
    """
    Regras puras de atraso. Fonte única da definição de "vencido".

    A detecção é baseada em DATA (não no status persistido), para que
    dashboard, cobranças e listas concordem mesmo que o cron diário
    (atualizar_inadimplencia) ainda não tenha rodado. O ORM espelha esses
    mesmos predicados em EmprestimoQuerySet.vencidos().
    """

    STATUS_ABERTO = ('ativo', 'inadimplente')
    STATUS_PARCELA_ABERTA = ('pendente', 'parcialmente_pago', 'atrasado')

    @staticmethod
    def dias_atraso(data_vencimento: date, ref: date) -> int:
        """Dias corridos de atraso (0 se ainda não venceu ou venceu hoje)."""
        if data_vencimento is None:
            return 0
        return max(0, (ref - data_vencimento).days)

    @staticmethod
    def esta_vencido_comum(status: str, data_vencimento: date, ref: date) -> bool:
        """Empréstimo COMUM vencido: tem data, está em aberto e a data passou."""
        return (
            status in CalculadoraAtraso.STATUS_ABERTO
            and data_vencimento is not None
            and data_vencimento < ref
        )


# ── Risco da Operação (composto e ponderado) ───────────────────────────────

class CalculadoraRisco:
    """
    Taxa de risco da operação como média ponderada de quatro subfatores,
    cada um normalizado em 0–100 (0 = sem risco, 100 = risco máximo):

      • Cobertura da penhora ...... peso 40%
      • Histórico do cliente ...... peso 30%
      • Comprometimento do capital  peso 20%
      • Tempo de exposição ........ peso 10%

    Todos os métodos são puros (sem Django). A camada de métricas apenas
    reúne os insumos via ORM e chama estes cálculos.
    """

    PESO_COBERTURA = Decimal('0.40')
    PESO_HISTORICO = Decimal('0.30')
    PESO_COMPROMETIMENTO = Decimal('0.20')
    PESO_TEMPO = Decimal('0.10')

    # Mapa de risco por classificação do cliente
    _RISCO_CLASSIFICACAO = {
        'verde': Decimal('0'),
        'amarelo': Decimal('50'),
        'vermelho': Decimal('100'),
    }

    # Tempo (em dias) a partir do qual a exposição é considerada risco máximo
    TETO_DIAS_EXPOSICAO = 180

    @staticmethod
    def fator_cobertura_penhora(
        saldo_devedor: Decimal,
        valor_garantia: Decimal,
        percentual_recuperacao: Decimal = Decimal('0.70'),
    ) -> Decimal:
        """
        Quanto MENOR a cobertura da penhora, MAIOR o risco.
        risco = 100 − percentual_cobertura.
        """
        exposicao = CalculadoraInadimplencia.calcular_exposicao_ajustada(
            saldo_devedor, valor_garantia, percentual_recuperacao
        )
        return _r(max(Decimal('0'), Decimal('100') - exposicao['percentual_cobertura']))

    @staticmethod
    def fator_historico_cliente(distribuicao_capital: dict) -> Decimal:
        """
        Risco do histórico ponderado pelo capital exposto em cada
        classificação. distribuicao_capital: {'verde': cap, 'amarelo': cap,
        'vermelho': cap}. Sem capital → 0.
        """
        total = sum(distribuicao_capital.values())
        if total <= Decimal('0'):
            return Decimal('0')
        soma = Decimal('0')
        for classe, capital in distribuicao_capital.items():
            risco = CalculadoraRisco._RISCO_CLASSIFICACAO.get(classe, Decimal('50'))
            soma += risco * capital
        return _r(soma / total)

    @staticmethod
    def fator_comprometimento_capital(
        capital_emprestado: Decimal,
        capital_total: Decimal,
    ) -> Decimal:
        """Percentual do capital total que está na rua (cap em 100)."""
        if capital_total is None or capital_total <= Decimal('0'):
            return Decimal('0')
        return _r(min(Decimal('100'), capital_emprestado / capital_total * 100))

    @staticmethod
    def fator_tempo_exposicao(dias_lista: list) -> Decimal:
        """
        Média do tempo de exposição (dias) dos empréstimos vencidos,
        normalizada para 0–100 com teto em TETO_DIAS_EXPOSICAO dias.
        Lista vazia → 0.
        """
        dias_validos = [d for d in dias_lista if d and d > 0]
        if not dias_validos:
            return Decimal('0')
        media = Decimal(sum(dias_validos)) / Decimal(len(dias_validos))
        normalizado = media / Decimal(CalculadoraRisco.TETO_DIAS_EXPOSICAO) * 100
        return _r(min(Decimal('100'), normalizado))

    @staticmethod
    def fator_comprometimento_renda(obrigacao_mensal, renda_mensal):
        """
        Percentual da renda mensal do cliente consumido pelas obrigações
        mensais de empréstimo (0–100, com teto em 100). Quanto MAIOR o
        comprometimento, MAIOR o risco.

        Retorna None quando a renda não está informada (campo opcional) —
        sinalizando à camada de apresentação que não há indicador a exibir.
        """
        if not renda_mensal or renda_mensal <= Decimal('0'):
            return None
        return _r(min(Decimal('100'), Decimal(obrigacao_mensal) / renda_mensal * 100))

    @staticmethod
    def calcular_taxa_risco(
        cobertura: Decimal,
        historico: Decimal,
        comprometimento: Decimal,
        tempo: Decimal,
    ) -> Decimal:
        """Média ponderada final (0–100)."""
        return _r(
            cobertura * CalculadoraRisco.PESO_COBERTURA
            + historico * CalculadoraRisco.PESO_HISTORICO
            + comprometimento * CalculadoraRisco.PESO_COMPROMETIMENTO
            + tempo * CalculadoraRisco.PESO_TEMPO
        )