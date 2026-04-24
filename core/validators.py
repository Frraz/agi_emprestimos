"""Validators reutilizáveis para campos Django."""
from django.core.exceptions import ValidationError
from .utils import validar_cpf, formatar_cpf


def validate_cpf(value: str):
    """Validator para campo CPF no Django model/form."""
    cpf_limpo = formatar_cpf(value)
    if not validar_cpf(cpf_limpo):
        raise ValidationError(
            f'CPF inválido: %(value)s',
            params={'value': value},
        )


def validate_taxa_juros(value):
    """Taxa deve estar entre 0 e 1 (0% a 100%)."""
    from decimal import Decimal
    if value <= Decimal('0') or value >= Decimal('1'):
        raise ValidationError(
            'Taxa de juros deve estar entre 0 e 1. Ex: 0.05 para 5%.'
        )


def validate_capital_positivo(value):
    """Capital deve ser estritamente positivo."""
    from decimal import Decimal
    if value <= Decimal('0'):
        raise ValidationError('O valor do capital deve ser positivo.')