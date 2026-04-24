"""
Entidades de domínio para Clientes.
Classes puras Python — sem dependência de Django.
Representam o estado e as regras de negócio do cliente.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from enum import Enum


class ClassificacaoCliente(str, Enum):
    VERDE = 'verde'        # Bom pagador
    AMARELO = 'amarelo'    # Regular — possui atrasos pontuais
    VERMELHO = 'vermelho'  # Mau pagador — inadimplente


class OrigemCliente(str, Enum):
    INDICACAO = 'indicacao'
    PROPRIO = 'proprio'
    REDES_SOCIAIS = 'redes_sociais'
    OUTRO = 'outro'


@dataclass
class EnderecoEntity:
    cep: str
    logradouro: str
    numero: str
    bairro: str
    cidade: str
    estado: str
    complemento: Optional[str] = None


@dataclass
class ClienteEntity:
    """
    Representa um cliente no domínio.
    Regra de classificação:
      - verde:    sem parcelas atrasadas
      - amarelo:  1–2 parcelas atrasadas em toda a carteira
      - vermelho: 3+ parcelas atrasadas OU empréstimo com status 'inadimplente'
    """
    nome: str
    cpf: str
    telefone_principal: str

    id: Optional[str] = None
    rg: Optional[str] = None
    data_nascimento: Optional[date] = None
    telefone_secundario: Optional[str] = None
    email: Optional[str] = None
    endereco: Optional[EnderecoEntity] = None
    foto: Optional[str] = None
    redes_sociais: dict = field(default_factory=dict)
    origem: OrigemCliente = OrigemCliente.PROPRIO
    indicador_id: Optional[str] = None
    perfil_psicologico: Optional[str] = None
    observacoes: Optional[str] = None
    classificacao: ClassificacaoCliente = ClassificacaoCliente.VERDE
    ativo: bool = True