"""Smoke tests do módulo de Backup/Exportação (P7) — CSV, JSON e PDF."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def _setup(django_user_model):
    user = django_user_model.objects.create_user('opexport', 'x')
    from customers.infrastructure.models import Cliente
    from loans.application.services import EmprestimoService
    c = Cliente.objects.create(
        nome='Fulano Export', cpf='12312312312',
        telefone_principal='(11) 90000-0000', owner=user,
    )
    emp = EmprestimoService.criar_emprestimo_comum(
        cliente_id=str(c.id), capital=Decimal('600'), taxa_mensal=Decimal('0.20'),
        data_inicio=date.today(), data_vencimento=date.today() + timedelta(days=30),
        usuario=user,
    )
    EmprestimoService.registrar_pagamento_comum(
        emprestimo_id=str(emp.id), valor=Decimal('120'),
        data_pagamento=date.today(), usuario=user,
    )
    return user


def test_exportacoes_individuais(django_user_model):
    from django.test import RequestFactory
    from exports import web_views
    user = _setup(django_user_model)
    rf = RequestFactory()
    esperado = {'csv': 'text/csv', 'json': 'application/json', 'pdf': 'application/pdf'}
    for ds in ('clientes', 'emprestimos', 'pagamentos'):
        for fmt, ctype in esperado.items():
            req = rf.get(f'/backup/{ds}/{fmt}/')
            req.user = user
            resp = web_views.exportar(req, ds, fmt)
            assert resp.status_code == 200, f'{ds}/{fmt}'
            assert ctype in resp['Content-Type']
            assert resp.content  # não vazio


def test_backup_completo(django_user_model):
    from django.test import RequestFactory
    from exports import web_views
    user = _setup(django_user_model)
    rf = RequestFactory()
    for fmt, marcador in (('json', b'{'), ('csv', b'PK'), ('pdf', b'%PDF')):
        req = rf.get(f'/backup/backup/{fmt}/')
        req.user = user
        resp = web_views.exportar_backup(req, fmt)
        assert resp.status_code == 200, fmt
        assert resp.content[:4].startswith(marcador[:1]) or marcador in resp.content[:8]


def test_export_isolado_por_usuario(django_user_model):
    """Export de um usuário não inclui dados de outro."""
    import json
    from django.test import RequestFactory
    from exports import web_views
    user_a = _setup(django_user_model)
    # outro usuário com cliente próprio
    user_b = django_user_model.objects.create_user('opexport_b', 'x')
    from customers.infrastructure.models import Cliente
    Cliente.objects.create(nome='Secreto B', cpf='99999999999',
                           telefone_principal='1', owner=user_b)

    rf = RequestFactory()
    req = rf.get('/backup/clientes/json/')
    req.user = user_a
    resp = web_views.exportar(req, 'clientes', 'json')
    payload = json.loads(resp.content)
    nomes = [c['nome'] for c in payload['Clientes']]
    assert 'Fulano Export' in nomes
    assert 'Secreto B' not in nomes
