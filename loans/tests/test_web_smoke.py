"""
Smoke de renderização das principais páginas web (pega erros de template que
o `manage.py check` não detecta). Usa RequestFactory (o test client mascara
erros 500 no Python 3.14 — ver memória do projeto).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def _user_com_dados(django_user_model):
    from customers.infrastructure.models import Cliente, TagCliente
    from loans.application.services import EmprestimoService

    user = django_user_model.objects.create_user('opsmoke', 'x')
    c = Cliente.objects.create(
        nome='Smoke', cpf='11122233344', telefone_principal='(11) 90000-0000', owner=user,
    )
    TagCliente.objects.create(owner=user, nome='VIP', cor='purple')
    EmprestimoService.criar_emprestimo_comum(
        cliente_id=str(c.id), capital=Decimal('1000'), taxa_mensal=Decimal('0.10'),
        data_inicio=date.today(), data_vencimento=date.today() + timedelta(days=10), usuario=user,
    )
    emp_p = EmprestimoService.criar_emprestimo_parcelado(
        cliente_id=str(c.id), capital=Decimal('1000'), taxa_mensal=Decimal('0.05'),
        n_parcelas=5, subtipo='fixo', data_inicio=date.today(),
        data_primeira_parcela=date.today(), usuario=user,
    )
    return user, c, emp_p


def _get(view, user, htmx=False, **kwargs):
    from django.test import RequestFactory
    req = RequestFactory().get('/')
    req.user = user
    req.htmx = htmx
    return view(req, **kwargs)


def test_paginas_principais_renderizam(django_user_model):
    from dashboard.interfaces import views as dash
    from customers.interfaces import web_views as cust
    from loans.interfaces import web_views as loans
    from payments.interfaces import web_views as pays
    from cobrancas.interfaces import web_views as cob
    from exports import web_views as exp

    user, c, emp_p = _user_com_dados(django_user_model)

    assert _get(dash.dashboard_view, user).status_code == 200
    assert _get(dash.capital_config, user).status_code == 200
    assert _get(dash.notificacoes_config, user).status_code == 200
    assert _get(cust.cliente_list, user, htmx=False).status_code == 200
    assert _get(cust.cliente_detail, user, pk=c.id).status_code == 200
    assert _get(cust.tag_manage, user).status_code == 200
    assert _get(loans.emprestimo_list, user).status_code == 200
    assert _get(loans.emprestimo_detail, user, pk=emp_p.id).status_code == 200
    assert _get(pays.pagamento_list, user, htmx=False).status_code == 200
    assert _get(cob.cobrancas_index, user, htmx=False).status_code == 200
    assert _get(exp.backup_index, user).status_code == 200
