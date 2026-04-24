"""
Exceções base do sistema Agi Empréstimos.
Todas as exceções de domínio e aplicação devem herdar daqui.
"""


class AgiBaseException(Exception):
    """Raiz de todas as exceções customizadas do sistema."""

    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code
        super().__init__(message)

    def __str__(self):
        return self.message


class EntidadeNaoEncontradaError(AgiBaseException):
    """Entidade não existe ou foi deletada."""
    pass


class PermissaoNegadaError(AgiBaseException):
    """Usuário não tem permissão para esta operação."""
    pass


class ValidacaoError(AgiBaseException):
    """Dados inválidos para a operação solicitada."""
    pass


class OperacaoInvalidaError(AgiBaseException):
    """Operação inválida no estado atual da entidade."""
    pass


class IntegridadeFinanceiraError(AgiBaseException):
    """
    Violação de regra financeira crítica.
    Ex: pagamento que tornaria saldo negativo sem justificativa.
    """
    pass