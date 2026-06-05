"""
Serviço de Cobranças — apenas leitura/agregação sobre empréstimos.

Reutiliza o predicado de atraso central (EmprestimoQuerySet/CalculadoraAtraso):
um "item de cobrança" é um vencimento em aberto — o próprio empréstimo comum
ou cada parcela em aberto de um parcelado. Os itens são agrupados em baldes
(atrasados, hoje, amanhã, esta semana) e por cliente.
"""
import calendar as _calendar
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal


class CobrancaService:

    STATUS_PARCELA_ABERTA = ('pendente', 'parcialmente_pago', 'atrasado')

    @staticmethod
    def _emprestimos_abertos(user=None):
        from loans.infrastructure.models import Emprestimo
        from core.ownership import escopo_opcional
        return (
            escopo_opcional(Emprestimo.objects.ativos(), user)
            .select_related('cliente')
            .prefetch_related('parcelas')
        )

    @classmethod
    def itens(cls, ref: date = None, user=None) -> list:
        """
        Lista unificada de vencimentos em aberto. Cada item:
          {cliente, emprestimo, tipo, numero, data_vencimento, valor,
           juros_mes, total_quitacao, dias_atraso}
        `valor` = valor a receber naquele vencimento (comum: total de quitação;
        parcela: valor em aberto). `user` escopa por dono (None = global).
        """
        from loans.domain.calculators import CalculadoraAtraso

        ref = ref or date.today()
        itens = []
        for emp in cls._emprestimos_abertos(user):
            if emp.tipo == 'comum':
                if emp.data_vencimento is None:
                    continue
                itens.append({
                    'cliente': emp.cliente,
                    'emprestimo': emp,
                    'tipo': 'comum',
                    'numero': None,
                    'data_vencimento': emp.data_vencimento,
                    'valor': emp.total_quitacao,
                    'juros_mes': emp.juros_mes,
                    'total_quitacao': emp.total_quitacao,
                    'dias_atraso': CalculadoraAtraso.dias_atraso(
                        emp.data_vencimento, ref
                    ),
                })
            elif emp.tipo == 'parcelado':
                for p in emp.parcelas.all():
                    if p.status in cls.STATUS_PARCELA_ABERTA:
                        itens.append({
                            'cliente': emp.cliente,
                            'emprestimo': emp,
                            'tipo': 'parcelado',
                            'numero': p.numero,
                            'data_vencimento': p.data_vencimento,
                            'valor': p.valor_em_aberto,
                            'juros_mes': None,
                            'total_quitacao': None,
                            'dias_atraso': CalculadoraAtraso.dias_atraso(
                                p.data_vencimento, ref
                            ),
                        })
        return itens

    @classmethod
    def vencimentos_por_bucket(cls, ref: date = None, data_especifica: date = None,
                               user=None) -> dict:
        """Agrupa os itens em baldes a partir da data de referência."""
        ref = ref or date.today()
        amanha = ref + timedelta(days=1)
        fim_semana = ref + timedelta(days=(6 - ref.weekday()))  # próximo domingo

        baldes = {
            'atrasados': [],
            'hoje': [],
            'amanha': [],
            'esta_semana': [],
            'data_especifica': [],
        }

        for item in cls.itens(ref, user=user):
            d = item['data_vencimento']
            if data_especifica and d == data_especifica:
                baldes['data_especifica'].append(item)
            if d < ref:
                baldes['atrasados'].append(item)
            elif d == ref:
                baldes['hoje'].append(item)
            elif d == amanha:
                baldes['amanha'].append(item)
            elif amanha < d <= fim_semana:
                baldes['esta_semana'].append(item)

        for chave, lista in baldes.items():
            lista.sort(key=lambda i: (i['data_vencimento'], i['cliente'].nome))

        baldes['totais'] = {
            chave: sum((i['valor'] for i in lista), Decimal('0'))
            for chave, lista in baldes.items() if chave != 'totais'
        }
        return baldes

    @classmethod
    def total_atraso_por_cliente(cls, ref: date = None, user=None) -> list:
        """
        Total em ATRASO por cliente (apenas vencidos), ordenado por
        prioridade de cobrança (Essencial primeiro) e depois pelo maior valor.
        """
        ref = ref or date.today()
        por_cliente = defaultdict(lambda: {
            'cliente': None, 'total': Decimal('0'),
            'qtd': 0, 'dias_max': 0,
        })
        for item in cls.itens(ref, user=user):
            if item['data_vencimento'] >= ref:
                continue
            cli = item['cliente']
            agg = por_cliente[cli.id]
            agg['cliente'] = cli
            agg['total'] += item['valor']
            agg['qtd'] += 1
            agg['dias_max'] = max(agg['dias_max'], item['dias_atraso'])

        linhas = list(por_cliente.values())
        linhas.sort(key=lambda r: (
            0 if r['cliente'].prioridade_cobranca == 'essencial' else 1,
            -r['total'],
        ))
        return linhas

    @classmethod
    def eventos_calendario(cls, ano: int, mes: int, ref: date = None, user=None) -> dict:
        """
        Mapa {dia(date): {'count', 'total', 'atrasado'}} para os vencimentos
        do mês informado, para montar a grade do calendário.
        """
        ref = ref or date.today()
        eventos = defaultdict(lambda: {
            'count': 0, 'total': Decimal('0'), 'atrasado': False,
        })
        for item in cls.itens(ref, user=user):
            d = item['data_vencimento']
            if d.year == ano and d.month == mes:
                ev = eventos[d]
                ev['count'] += 1
                ev['total'] += item['valor']
                if d < ref:
                    ev['atrasado'] = True
        return dict(eventos)

    @staticmethod
    def grade_calendario(ano: int, mes: int) -> list:
        """Semanas do mês como listas de dias (date), com padding (None)."""
        cal = _calendar.Calendar(firstweekday=0)  # segunda-feira
        semanas = []
        for semana in cal.monthdatescalendar(ano, mes):
            semanas.append([
                (d if d.month == mes else None) for d in semana
            ])
        return semanas
