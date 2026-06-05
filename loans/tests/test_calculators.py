"""
Testes unitários das calculadoras financeiras.
São os testes mais importantes do sistema — cobrem o coração do negócio.
Execute: pytest loans/tests/test_calculators.py -v
"""
from decimal import Decimal
from datetime import date
import pytest

from loans.domain.calculators import (
    CalculadoraEmprestimoComum,
    CalculadoraEmprestimoParceladoFixo,
    CalculadoraEmprestimoParceladoSAC,
    CalculadoraInadimplencia,
    CalculadoraAtraso,
    CalculadoraRisco,
)


class TestCalculadoraEmprestimoComum:

    def test_juros_basico(self):
        assert CalculadoraEmprestimoComum.calcular_juros_mes(
            Decimal('1000'), Decimal('0.05')
        ) == Decimal('50.00')

    def test_total_quitacao(self):
        # total = capital + juros já lançados (acumulados)
        assert CalculadoraEmprestimoComum.calcular_total_quitacao(
            Decimal('1000'), Decimal('50')
        ) == Decimal('1050.00')

    def test_pagamento_total_quita_emprestimo(self):
        r = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=Decimal('1000'),
            valor_pago=Decimal('1050'),
            juros_acumulados=Decimal('50'),
        )
        assert r.capital_restante == Decimal('0.00')
        assert r.juros_pagos == Decimal('50.00')
        assert r.capital_pago == Decimal('1000.00')
        assert r.excedente == Decimal('0.00')
        assert r.juros_acumulados_restante == Decimal('0.00')

    def test_pagamento_so_juros_mantem_capital(self):
        r = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=Decimal('1000'),
            valor_pago=Decimal('50'),
            juros_acumulados=Decimal('50'),
        )
        assert r.capital_restante == Decimal('1000.00')
        assert r.capital_pago == Decimal('0.00')
        assert r.juros_acumulados_restante == Decimal('0.00')

    def test_pagamento_parcial_abate_capital(self):
        r = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=Decimal('1000'),
            valor_pago=Decimal('550'),
            juros_acumulados=Decimal('50'),
        )
        assert r.capital_restante == Decimal('500.00')
        assert r.capital_pago == Decimal('500.00')
        assert r.juros_pagos == Decimal('50.00')

    def test_pagamento_insuficiente_nao_capitaliza(self):
        """Pagar menos que os juros NÃO aumenta o capital (sem juros sobre juros).
        O que falta permanece em juros_acumulados."""
        r = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=Decimal('1000'),
            valor_pago=Decimal('30'),       # juros em aberto = 50, faltam 20
            juros_acumulados=Decimal('50'),
        )
        assert r.capital_restante == Decimal('1000.00')           # capital intacto
        assert r.juros_pagos == Decimal('30.00')
        assert r.juros_acumulados_restante == Decimal('20.00')    # 20 ficam em aberto
        assert r.capital_pago == Decimal('0.00')

    def test_excedente_calculado_corretamente(self):
        r = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=Decimal('1000'),
            valor_pago=Decimal('1100'),     # 50 a mais
            juros_acumulados=Decimal('50'),
        )
        assert r.excedente == Decimal('50.00')
        assert r.capital_restante == Decimal('0.00')

    # ── Cenários do bug relatado pelo cliente ──────────────────────────────

    def test_bug_600_20pct_paga_719_99_deixa_um_centavo(self):
        """Capital 600, juros 20% → total 720. Pagar 719,99 deixa 0,01 (não 18,01)."""
        capital = Decimal('600')
        juros = CalculadoraEmprestimoComum.calcular_juros_mes(capital, Decimal('0.20'))
        assert juros == Decimal('120.00')
        total = CalculadoraEmprestimoComum.calcular_total_quitacao(capital, juros)
        assert total == Decimal('720.00')

        r = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=capital,
            valor_pago=Decimal('719.99'),
            juros_acumulados=juros,
        )
        assert r.capital_restante == Decimal('0.01')
        assert r.juros_acumulados_restante == Decimal('0.00')

    def test_bug_pagamentos_fracionados_sem_recobrar_juros(self):
        """Pagar 400 e depois 319,99 de uma dívida de 720 deixa 0,01 —
        os juros não são recobrados a cada pagamento."""
        capital = Decimal('600')
        juros_acum = CalculadoraEmprestimoComum.calcular_juros_mes(capital, Decimal('0.20'))

        r1 = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=capital, valor_pago=Decimal('400'), juros_acumulados=juros_acum,
        )
        # 120 de juros quitados + 280 abatem capital
        assert r1.capital_restante == Decimal('320.00')
        assert r1.juros_acumulados_restante == Decimal('0.00')

        r2 = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=r1.capital_restante, valor_pago=Decimal('319.99'),
            juros_acumulados=r1.juros_acumulados_restante,
        )
        assert r2.capital_restante == Decimal('0.01')

    def test_juros_atraso_acumulam_sem_compor(self):
        """90 a 10%: 2 ciclos vencidos acumulam 9+9=18 de juros, capital intacto."""
        capital = Decimal('90')
        taxa = Decimal('0.10')
        juros_acum = Decimal('0')
        for _ in range(2):  # dois ciclos lançados pelo cron
            juros_acum += CalculadoraEmprestimoComum.calcular_juros_mes(capital, taxa)
        assert juros_acum == Decimal('18.00')   # 9 + 9, sem juros sobre juros
        # capital nunca muda por causa dos juros
        assert capital == Decimal('90')

    # ── Juros zero (P9) ────────────────────────────────────────────────────

    def test_juros_zero_total_igual_capital(self):
        juros = CalculadoraEmprestimoComum.calcular_juros_mes(
            Decimal('1000'), Decimal('0')
        )
        assert juros == Decimal('0.00')
        total = CalculadoraEmprestimoComum.calcular_total_quitacao(
            Decimal('1000'), juros
        )
        assert total == Decimal('1000.00')

    def test_juros_zero_pagamento_abate_so_capital(self):
        r = CalculadoraEmprestimoComum.aplicar_pagamento(
            capital_atual=Decimal('1000'),
            valor_pago=Decimal('1000'),
            juros_acumulados=Decimal('0'),
        )
        assert r.capital_restante == Decimal('0.00')
        assert r.juros_pagos == Decimal('0.00')
        assert r.capital_pago == Decimal('1000.00')


class TestCalculadoraParceladoFixo:

    def test_valor_parcela(self):
        # Capital=1000, taxa=5%, 10x
        # Total juros = 1000 * 0.05 * 10 = 500
        # Parcela = 1500 / 10 = 150
        p = CalculadoraEmprestimoParceladoFixo.calcular_valor_parcela(
            Decimal('1000'), Decimal('0.05'), 10
        )
        assert p == Decimal('150.00')

    def test_tabela_tem_n_parcelas(self):
        tabela = CalculadoraEmprestimoParceladoFixo.gerar_tabela_amortizacao(
            Decimal('1000'), Decimal('0.05'), 10, date(2024, 1, 1)
        )
        assert len(tabela) == 10

    def test_saldo_final_zero(self):
        tabela = CalculadoraEmprestimoParceladoFixo.gerar_tabela_amortizacao(
            Decimal('1000'), Decimal('0.05'), 10, date(2024, 1, 1)
        )
        assert tabela[-1].saldo_devedor_depois == Decimal('0.00')

    def test_parcelas_valor_fixo(self):
        tabela = CalculadoraEmprestimoParceladoFixo.gerar_tabela_amortizacao(
            Decimal('1000'), Decimal('0.05'), 10, date(2024, 1, 1)
        )
        valores = [p.valor_parcela for p in tabela[:-1]]
        assert len(set(valores)) == 1, "Todas as parcelas devem ter o mesmo valor"

    def test_datas_sequenciais(self):
        tabela = CalculadoraEmprestimoParceladoFixo.gerar_tabela_amortizacao(
            Decimal('1000'), Decimal('0.05'), 3, date(2024, 1, 1)
        )
        assert tabela[0].data_vencimento.month == 1
        assert tabela[1].data_vencimento.month == 2
        assert tabela[2].data_vencimento.month == 3

    def test_juros_zero_parcelado(self):
        """P9: parcelado com 0% de juros → total = capital, parcela = capital/n."""
        p = CalculadoraEmprestimoParceladoFixo.calcular_valor_parcela(
            Decimal('1000'), Decimal('0'), 5
        )
        assert p == Decimal('200.00')
        tabela = CalculadoraEmprestimoParceladoFixo.gerar_tabela_amortizacao(
            Decimal('1000'), Decimal('0'), 5, date(2024, 1, 1)
        )
        assert sum(pp.valor_juros for pp in tabela) == Decimal('0.00')
        assert sum(pp.valor_parcela for pp in tabela) == Decimal('1000.00')
        assert tabela[-1].saldo_devedor_depois == Decimal('0.00')


class TestCalculadoraParceladoSAC:

    def test_tabela_tem_n_parcelas(self):
        tabela = CalculadoraEmprestimoParceladoSAC.gerar_tabela_amortizacao(
            Decimal('1000'), Decimal('0.05'), 5, date(2024, 1, 1)
        )
        assert len(tabela) == 5

    def test_parcelas_decrescentes(self):
        tabela = CalculadoraEmprestimoParceladoSAC.gerar_tabela_amortizacao(
            Decimal('1000'), Decimal('0.05'), 5, date(2024, 1, 1)
        )
        for i in range(len(tabela) - 2):
            assert tabela[i].valor_parcela > tabela[i + 1].valor_parcela

    def test_amortizacao_constante(self):
        tabela = CalculadoraEmprestimoParceladoSAC.gerar_tabela_amortizacao(
            Decimal('1000'), Decimal('0.05'), 5, date(2024, 1, 1)
        )
        # Exclui última parcela (pode ter ajuste de centavo)
        amortizacoes = [p.valor_principal for p in tabela[:-1]]
        assert len(set(amortizacoes)) == 1, "Amortização deve ser constante"

    def test_saldo_final_zero(self):
        tabela = CalculadoraEmprestimoParceladoSAC.gerar_tabela_amortizacao(
            Decimal('1000'), Decimal('0.05'), 5, date(2024, 1, 1)
        )
        assert tabela[-1].saldo_devedor_depois == Decimal('0.00')

    def test_sac_paga_menos_juros_que_fixo(self):
        """SAC deve resultar em menos juros totais que o modelo Fixo."""
        capital = Decimal('1000')
        taxa = Decimal('0.05')
        n = 10

        tabela_fixo = CalculadoraEmprestimoParceladoFixo.gerar_tabela_amortizacao(
            capital, taxa, n, date(2024, 1, 1)
        )
        tabela_sac = CalculadoraEmprestimoParceladoSAC.gerar_tabela_amortizacao(
            capital, taxa, n, date(2024, 1, 1)
        )

        juros_fixo = sum(p.valor_juros for p in tabela_fixo)
        juros_sac = sum(p.valor_juros for p in tabela_sac)

        assert juros_sac < juros_fixo


class TestClassificacaoCliente:

    def test_sem_atrasos_verde(self):
        assert CalculadoraInadimplencia.classificar_cliente([
            {'status': 'ativo', 'parcelas_atrasadas': 0},
        ]) == 'verde'

    def test_um_atraso_amarelo(self):
        assert CalculadoraInadimplencia.classificar_cliente([
            {'status': 'ativo', 'parcelas_atrasadas': 1},
        ]) == 'amarelo'

    def test_tres_atrasos_vermelho(self):
        assert CalculadoraInadimplencia.classificar_cliente([
            {'status': 'ativo', 'parcelas_atrasadas': 3},
        ]) == 'vermelho'

    def test_inadimplente_vermelho(self):
        assert CalculadoraInadimplencia.classificar_cliente([
            {'status': 'inadimplente', 'parcelas_atrasadas': 0},
        ]) == 'vermelho'

    def test_exposicao_com_garantia_total(self):
        r = CalculadoraInadimplencia.calcular_exposicao_ajustada(
            saldo_devedor=Decimal('1000'),
            valor_garantia=Decimal('2000'),
            percentual_recuperacao=Decimal('0.70'),
        )
        assert r['perda_ajustada'] == Decimal('0.00')
        assert r['percentual_cobertura'] == Decimal('100.00')

    def test_exposicao_com_garantia_parcial(self):
        r = CalculadoraInadimplencia.calcular_exposicao_ajustada(
            saldo_devedor=Decimal('1000'),
            valor_garantia=Decimal('500'),
            percentual_recuperacao=Decimal('0.70'),
        )
        # Recuperacao = 500 * 0.70 = 350
        # Perda = 1000 - 350 = 650
        assert r['recuperacao_estimada'] == Decimal('350.00')
        assert r['perda_ajustada'] == Decimal('650.00')

class TestCalculadoraAtraso:

    def test_dias_atraso_vencido(self):
        assert CalculadoraAtraso.dias_atraso(
            date(2026, 1, 1), date(2026, 1, 11)
        ) == 10

    def test_dias_atraso_no_vencimento_eh_zero(self):
        # Vencer hoje ainda não é atraso
        assert CalculadoraAtraso.dias_atraso(
            date(2026, 1, 1), date(2026, 1, 1)
        ) == 0

    def test_dias_atraso_futuro_eh_zero(self):
        assert CalculadoraAtraso.dias_atraso(
            date(2026, 2, 1), date(2026, 1, 1)
        ) == 0

    def test_dias_atraso_sem_data_eh_zero(self):
        assert CalculadoraAtraso.dias_atraso(None, date(2026, 1, 1)) == 0

    def test_comum_vencido(self):
        assert CalculadoraAtraso.esta_vencido_comum(
            'ativo', date(2026, 1, 1), date(2026, 1, 2)
        ) is True

    def test_comum_sem_vencimento_nao_esta_vencido(self):
        assert CalculadoraAtraso.esta_vencido_comum(
            'ativo', None, date(2026, 1, 2)
        ) is False

    def test_comum_quitado_nao_esta_vencido(self):
        assert CalculadoraAtraso.esta_vencido_comum(
            'quitado', date(2026, 1, 1), date(2026, 1, 2)
        ) is False


class TestCalculadoraRisco:

    def test_cobertura_total_zera_o_fator(self):
        # Garantia cobre tudo → cobertura 100% → fator de risco 0
        f = CalculadoraRisco.fator_cobertura_penhora(
            Decimal('1000'), Decimal('2000'), Decimal('0.70')
        )
        assert f == Decimal('0.00')

    def test_cobertura_zero_fator_maximo(self):
        # Sem garantia → cobertura 0% → fator 100
        f = CalculadoraRisco.fator_cobertura_penhora(
            Decimal('1000'), Decimal('0'), Decimal('0.70')
        )
        assert f == Decimal('100.00')

    def test_historico_ponderado_por_capital(self):
        dist = {'verde': Decimal('0'), 'amarelo': Decimal('0'), 'vermelho': Decimal('100')}
        assert CalculadoraRisco.fator_historico_cliente(dist) == Decimal('100.00')
        dist2 = {'verde': Decimal('100'), 'amarelo': Decimal('0'), 'vermelho': Decimal('100')}
        # média ponderada: (0*100 + 100*100) / 200 = 50
        assert CalculadoraRisco.fator_historico_cliente(dist2) == Decimal('50.00')

    def test_historico_sem_capital_eh_zero(self):
        dist = {'verde': Decimal('0'), 'amarelo': Decimal('0'), 'vermelho': Decimal('0')}
        assert CalculadoraRisco.fator_historico_cliente(dist) == Decimal('0')

    def test_comprometimento_capital(self):
        assert CalculadoraRisco.fator_comprometimento_capital(
            Decimal('5000'), Decimal('10000')
        ) == Decimal('50.00')
        # cap em 100 mesmo se emprestado > total
        assert CalculadoraRisco.fator_comprometimento_capital(
            Decimal('15000'), Decimal('10000')
        ) == Decimal('100.00')

    def test_comprometimento_sem_capital_total_eh_zero(self):
        assert CalculadoraRisco.fator_comprometimento_capital(
            Decimal('5000'), Decimal('0')
        ) == Decimal('0')

    def test_tempo_exposicao_normalizado(self):
        # média 90 dias / teto 180 = 50%
        assert CalculadoraRisco.fator_tempo_exposicao([90, 90]) == Decimal('50.00')
        # acima do teto satura em 100
        assert CalculadoraRisco.fator_tempo_exposicao([360]) == Decimal('100.00')

    def test_tempo_exposicao_vazio_eh_zero(self):
        assert CalculadoraRisco.fator_tempo_exposicao([]) == Decimal('0')

    def test_taxa_risco_ponderada(self):
        # 40%*100 + 30%*100 + 20%*100 + 10%*100 = 100
        assert CalculadoraRisco.calcular_taxa_risco(
            Decimal('100'), Decimal('100'), Decimal('100'), Decimal('100')
        ) == Decimal('100.00')
        # pesos: 0.4*50 + 0.3*100 + 0.2*0 + 0.1*0 = 20 + 30 = 50
        assert CalculadoraRisco.calcular_taxa_risco(
            Decimal('50'), Decimal('100'), Decimal('0'), Decimal('0')
        ) == Decimal('50.00')

    def test_comprometimento_renda_percentual(self):
        # obrigação 900 sobre renda 3000 = 30%
        assert CalculadoraRisco.fator_comprometimento_renda(
            Decimal('900'), Decimal('3000')
        ) == Decimal('30.00')

    def test_comprometimento_renda_satura_em_100(self):
        # obrigação acima da renda satura em 100
        assert CalculadoraRisco.fator_comprometimento_renda(
            Decimal('4000'), Decimal('3000')
        ) == Decimal('100.00')

    def test_comprometimento_renda_sem_renda_eh_none(self):
        # renda não informada (campo opcional) → None, sem indicador
        assert CalculadoraRisco.fator_comprometimento_renda(
            Decimal('900'), None
        ) is None
        assert CalculadoraRisco.fator_comprometimento_renda(
            Decimal('900'), Decimal('0')
        ) is None
