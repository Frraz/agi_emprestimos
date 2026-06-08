"""
CPF é único POR USUÁRIO (isolamento entre operadores), não global.
"""
import pytest

pytestmark = pytest.mark.django_db


def _user(username):
    from django.contrib.auth.models import User
    return User.objects.create_user(username=username, password='x')


def test_dois_usuarios_podem_ter_o_mesmo_cpf():
    from customers.application.services import ClienteService
    from core.management.commands.popular_sistema import gerar_cpf
    a, b = _user('lender_a'), _user('lender_b')
    cpf = gerar_cpf()

    ca = ClienteService.criar_cliente(
        {'nome': 'Pessoa', 'cpf': cpf, 'telefone_principal': '(11) 90000-0000'}, usuario=a)
    cb = ClienteService.criar_cliente(
        {'nome': 'Pessoa', 'cpf': cpf, 'telefone_principal': '(11) 90000-0000'}, usuario=b)

    assert ca.owner_id == a.id and cb.owner_id == b.id
    assert ca.cpf == cb.cpf  # mesmo CPF, donos diferentes — permitido


def test_mesmo_usuario_nao_pode_duplicar_cpf():
    from customers.application.services import ClienteService
    from customers.domain.exceptions import ClienteJaExisteError
    from core.management.commands.popular_sistema import gerar_cpf
    a = _user('lender_c')
    cpf = gerar_cpf()
    ClienteService.criar_cliente(
        {'nome': 'X', 'cpf': cpf, 'telefone_principal': '(11) 90000-0000'}, usuario=a)
    with pytest.raises(ClienteJaExisteError):
        ClienteService.criar_cliente(
            {'nome': 'Y', 'cpf': cpf, 'telefone_principal': '(11) 90000-0000'}, usuario=a)


def test_constraint_no_banco_bloqueia_cpf_duplicado_do_mesmo_dono():
    from django.db import IntegrityError, transaction
    from customers.infrastructure.models import Cliente
    a = _user('lender_d')
    Cliente.objects.create(owner=a, nome='A', cpf='11111111111', telefone_principal='x')
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Cliente.objects.create(owner=a, nome='B', cpf='11111111111', telefone_principal='y')


def test_form_escopa_cpf_por_usuario():
    """O cliente de outro operador não deve bloquear o cadastro (nem vazar)."""
    from customers.infrastructure.models import Cliente
    from customers.interfaces.forms import ClienteForm
    from core.management.commands.popular_sistema import gerar_cpf
    a, b = _user('lender_e'), _user('lender_f')
    cpf = gerar_cpf()
    Cliente.objects.create(owner=a, nome='Da A', cpf=cpf, telefone_principal='x')

    # b tenta cadastrar o mesmo CPF — deve ser permitido (form válido).
    form = ClienteForm(
        data={'nome': 'Da B', 'cpf': cpf, 'telefone_principal': '(11) 90000-0000',
              'origem': 'proprio', 'prioridade_cobranca': 'preferencial'},
        owner=b,
    )
    assert form.is_valid(), form.errors

    # b tenta duplicar dentro da própria carteira — deve bloquear.
    Cliente.objects.create(owner=b, nome='Da B', cpf=cpf, telefone_principal='x')
    form2 = ClienteForm(
        data={'nome': 'Outro', 'cpf': cpf, 'telefone_principal': '(11) 90000-0000',
              'origem': 'proprio', 'prioridade_cobranca': 'preferencial'},
        owner=b,
    )
    assert not form2.is_valid()
    assert 'cpf' in form2.errors
