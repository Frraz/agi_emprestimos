from core.exceptions import AgiBaseException, OperacaoInvalidaError


class LoanDomainException(AgiBaseException):
    pass


class CapitalInvalidoError(LoanDomainException):
    """Capital deve ser um valor positivo."""
    pass


class TaxaInvalidaError(LoanDomainException):
    """Taxa de juros fora do intervalo permitido (0 < taxa < 1)."""
    pass


class ParcelasInsuficientesError(LoanDomainException):
    """Número de parcelas inválido para o tipo de empréstimo."""
    pass


class EmprestimoJaQuitadoError(OperacaoInvalidaError):
    """Tentativa de operação em empréstimo já quitado."""
    pass


class EmprestimoInativoError(OperacaoInvalidaError):
    """Operação não permitida no status atual do empréstimo."""
    pass


class PagamentoExcedeCapitalError(LoanDomainException):
    """Valor de pagamento excede o capital em aberto."""
    pass