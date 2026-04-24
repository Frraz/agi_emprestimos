"""Utilitários compartilhados por todo o sistema."""
import re
from decimal import Decimal, ROUND_HALF_UP


# ── CPF ────────────────────────────────────────────────────────────────────

def formatar_cpf(cpf: str) -> str:
    """Remove qualquer formatação do CPF, retorna apenas 11 dígitos."""
    return re.sub(r'[^0-9]', '', cpf or '')


def validar_cpf(cpf: str) -> bool:
    """Validação de CPF pelo algoritmo oficial da Receita Federal."""
    cpf = formatar_cpf(cpf)

    if len(cpf) != 11:
        return False
    # Rejeita sequências óbvias como 00000000000, 11111111111, etc.
    if cpf == cpf[0] * 11:
        return False

    def _digito(cpf_parcial: str, peso_inicial: int) -> int:
        soma = sum(int(d) * p for d, p in zip(cpf_parcial, range(peso_inicial, 1, -1)))
        resto = (soma * 10) % 11
        return 0 if resto >= 10 else resto

    if _digito(cpf[:9], 10) != int(cpf[9]):
        return False
    if _digito(cpf[:10], 11) != int(cpf[10]):
        return False

    return True


def exibir_cpf(cpf: str) -> str:
    """Formata CPF para exibição: 000.000.000-00"""
    cpf = formatar_cpf(cpf)
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if len(cpf) == 11 else cpf


# ── Moeda ──────────────────────────────────────────────────────────────────

def formatar_moeda(valor: Decimal) -> str:
    """R$ 1.234,56"""
    valor_fmt = f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return f"R$ {valor_fmt}"


def arredondar_financeiro(valor: Decimal, casas: int = 2) -> Decimal:
    """Arredondamento padrão financeiro brasileiro (ROUND_HALF_UP)."""
    quantizer = Decimal(10) ** -casas
    return valor.quantize(quantizer, rounding=ROUND_HALF_UP)


def calcular_percentual(parte: Decimal, total: Decimal) -> Decimal:
    """Retorna percentual com segurança contra divisão por zero."""
    if not total or total == Decimal('0'):
        return Decimal('0')
    return arredondar_financeiro((parte / total) * 100)