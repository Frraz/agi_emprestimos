# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão geral

Sistema Django de gestão de empréstimos (crédito informal): clientes, empréstimos, pagamentos, garantias (penhoras), dashboard financeiro. Serve uma interface web (Django Templates + HTMX) e uma API REST versionada (DRF + JWT) destinada a um futuro app Flutter offline-first. Código, models e documentação em português.

## Comandos

Settings padrão é `config.settings.development` (definido em `manage.py` e `pytest.ini`). Produção usa `config.settings.production` via `DJANGO_SETTINGS_MODULE`.

```bash
# Desenvolvimento local (venv + Postgres local)
python manage.py runserver
python manage.py makemigrations && python manage.py migrate
python manage.py popular_sistema            # seed de dados (--limpar, --clientes N)
python manage.py atualizar_inadimplencia    # cron diário (--dry-run, --data YYYY-MM-DD)

# Testes (pytest-django)
pytest                                       # todos
pytest loans/tests/test_calculators.py -v   # arquivo único
pytest loans/tests/test_calculators.py::TestCalculadoraEmprestimoComum::test_x  # teste único
pytest --cov=loans/domain --cov-report=term-missing
```

Docker (produção) é dirigido pelo `Makefile`: `make up|down|build|migrate|seed|shell|logs|createsuperuser`. Os comandos `make` rodam dentro do container `web` via `docker compose exec`.

## Arquitetura em camadas

Cada app de domínio (`customers`, `loans`, `payments`, `collaterals`, `dashboard`) segue a mesma estrutura de pastas, separando responsabilidades:

- `domain/` — lógica pura, sem Django. `calculators.py`, `entities.py`, `value_objects.py`, `exceptions.py`.
- `application/services.py` — orquestração: chama o domínio, persiste via ORM, grava AuditLog, dispara efeitos colaterais (ex: reclassificar cliente).
- `infrastructure/models.py` — models Django (a fonte real). `repositories.py` quando existe.
- `interfaces/` — pontos de entrada. `views.py`/`serializers.py`/`urls.py` (API REST) e `web_views.py`/`forms.py`/`web_urls.py` (web HTMX).

**Convenção importante:** o `models.py` na raiz de cada app é apenas um re-export de `infrastructure/models.py` (para o Django descobrir os models). Edite sempre `infrastructure/models.py`, nunca o re-export.

### Regra absoluta: lógica financeira só no domínio

Toda matemática de juros, amortização, saldo devedor, parcelas e inadimplência vive **exclusivamente** em `loans/domain/calculators.py`. Views, serializers, services e templates apenas orquestram e exibem — nunca calculam. As três modalidades têm calculadoras dedicadas:
- `CalculadoraEmprestimoComum` — juros simples mensais, sem parcela fixa; juros são pagos antes do capital; pagamento abaixo dos juros capitaliza.
- `CalculadoraEmprestimoParceladoFixo` — parcelas iguais, juros sobre o capital inicial.
- `CalculadoraEmprestimoParceladoSAC` — amortização constante, parcelas decrescentes.
- `CalculadoraInadimplencia` — classificação do cliente e exposição ajustada por garantia.

Toda a documentação detalhada das regras e fórmulas está em `logica_de_negocio.md` — consulte-o antes de mexer em cálculos.

### Fluxo típico (pagamento)

`interfaces` (view/viewset) → `application/services.py` → `domain/calculators.py` (cálculo puro) → ORM + AuditLog → reclassificação do cliente → response.

## Convenções de dados (todos os models)

- Herdam de `core.models.BaseModel` (UUID v4 como PK, `created_at`/`updated_at`/`deleted_at`) ou `SoftDeleteModel`.
- **Soft delete (padrão):** a operação reversível "Desativar/Ativar" da UI usa `.soft_delete()`/`.restore()`. Em `SoftDeleteModel`, `.objects` já filtra deletados; use `.all_objects` para incluí-los. (Cliente/Empréstimo/Pagamento herdam de `BaseModel`, cujo `.objects` **inclui** deletados — filtre `deleted_at__isnull=True` explicitamente, como já fazem as views.)
- **Hard delete (exceção, opt-in):** a UI também oferece "Apagar" — exclusão **definitiva em cascata** (cliente → empréstimos → pagamentos/parcelas/garantias/movimentações de capital), com confirmação explícita de irreversibilidade. Decisão do cliente (jun/2026). Orquestrado **só** nas services (`ClienteService.apagar_cliente`, `EmprestimoService.apagar_emprestimo`/`apagar_pagamento` + helper `_hard_delete_emprestimo`), respeitando a ordem das FKs PROTECT (apaga pagamentos antes das parcelas). O `AuditLog` (GenericFK, sem constraint) sobrevive ao hard delete. Remover um pagamento/empréstimo **recalcula o saldo** do empréstimo via `recalcular_emprestimo`; o caixa se corrige sozinho (as agregações de `CapitalOperacional` filtram `deleted_at`).
- **`updated_at`** é o vetor de sincronização do app Flutter — preserve esse comportamento.
- **Dinheiro/taxas:** sempre `Decimal` com `ROUND_HALF_UP`. A precisão global está em 28 casas (`getcontext().prec = 28` em `base.py`). Taxas armazenadas como decimal (`0.05` = 5% a.m.).
- **Auditoria:** mutações financeiras devem gerar `AuditLog` (app `audit`, append-only via `GenericForeignKey`), feito na camada de services.

## API e auth

- API em `/api/v1/`, montada em `api/v1/urls.py`, que inclui os `interfaces/urls.py` de cada app.
- Web auth = sessão Django; API auth = JWT (simplejwt) com access 8h, refresh 7d, rotação + blacklist. Login/refresh/logout em `/api/v1/auth/`.
- DRF usa `COERCE_DECIMAL_TO_STRING = False` (decimais como número, não string) por causa do cliente Flutter — não reverta.
- `core/models_config.py` tem `CapitalOperacional`, um singleton com o capital total da operação, base de vários cálculos do dashboard (`dashboard/application/metrics.py`).
