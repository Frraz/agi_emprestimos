from core.exceptions import AgiBaseException


class CustomerDomainException(AgiBaseException):
    pass


class CPFInvalidoError(CustomerDomainException):
    pass


class ClienteJaExisteError(CustomerDomainException):
    pass


class ClienteNaoEncontradoError(CustomerDomainException):
    pass