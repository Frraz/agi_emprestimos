# Agi Empréstimos

> Sistema profissional de gestão de crédito informal — controle completo de empréstimos, clientes, garantias e métricas financeiras.

![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)
![Django](https://img.shields.io/badge/Django-4.2-green?style=flat-square&logo=django)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?style=flat-square&logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker)
![License](https://img.shields.io/badge/license-Privado-red?style=flat-square)

---

## Sumário

- [Visão Geral](#visão-geral)
- [Funcionalidades](#funcionalidades)
- [Stack Tecnológica](#stack-tecnológica)
- [Arquitetura](#arquitetura)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Instalação Local](#instalação-local)
- [Deploy em Produção (Docker)](#deploy-em-produção-docker)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Comandos Úteis](#comandos-úteis)
- [Tipos de Empréstimo](#tipos-de-empréstimo)
- [API REST](#api-rest)
- [Testes](#testes)
- [Regras de Negócio](#regras-de-negócio)

---

## Visão Geral

O **Agi Empréstimos** é um sistema completo de administração de crédito desenvolvido para operadores de empréstimo informal. Permite controlar toda a carteira de crédito — desde o cadastro de clientes até o acompanhamento de pagamentos, gestão de garantias (penhoras) e análise de risco em tempo real.

### Principais diferenciais

- **Dashboard financeiro completo** com KPIs, inadimplência ajustada por penhora e projeções em 3 cenários
- **Interface web moderna** (HTMX + Tailwind) responsiva para desktop e mobile
- **API REST** com autenticação JWT — pronta para integração com app mobile Flutter (offline-first)
- **Auditoria total** de todas as operações com rastreabilidade completa
- **Lógica financeira robusta** — toda a matemática de juros, amortização e saldo devedor vive no backend, nunca no frontend

---

## Funcionalidades

### Clientes
- Cadastro completo (dados pessoais, profissão, estado civil, tipo de residência)
- Documentos: RG, CNH, comprovantes
- Contatos múltiplos, Instagram, Facebook
- Busca automática de endereço por CEP (ViaCEP)
- Perfil psicológico e observações livres
- Origem do cliente (indicação, redes sociais, boato, etc.)
- Classificação automática de risco: 🟢 Bom Pagador / 🟡 Regular / 🔴 Mau Pagador

### Empréstimos
| Tipo | Descrição |
|------|-----------|
| **Comum** | Sem parcelas fixas — juros mensais sobre capital. 3 opções de pagamento: só juros, parcial ou quitação total |
| **Parcelado Fixo** | Parcelas iguais com juros sobre o capital inicial |
| **Parcelado SAC** | Amortização constante — parcelas decrescentes com menos juros totais |
| **Diária** | Reservado para implementação futura |

### Pagamentos
- Registro histórico imutável (append-only)
- Snapshot do saldo antes/depois de cada pagamento
- Cálculo automático de juros, capital amortizado e excedente

### Garantias (Penhoras)
- Vinculação de bens ao empréstimo (veículos, imóveis, eletrônicos, joias, outros)
- Campos específicos por tipo (placa, chassi, matrícula)
- Cálculo de exposição real e perda ajustada por garantia
- Upload de documentos (fotos, contratos, notas)

### Dashboard
- Capital total, emprestado e disponível em caixa
- Taxa de inadimplência com barra de progresso visual
- Taxa de risco da operação (composta)
- Custo da inadimplência ajustado por penhoras
- Projeção de lucro em 3 cenários (otimista, realista, pessimista)
- Gráfico de capital por modalidade
- Lista de empréstimos recentes

### Operacional
- Comando de atualização automática de inadimplência (cron)
- Auditoria completa de todas as alterações
- Soft delete — nenhum dado financeiro é destruído
- UUID como chave primária (sincronização mobile-first)

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Backend | Django 4.2 + Django REST Framework 3.15 |
| Interface Web | Django Templates + HTMX 1.9 + Tailwind CSS |
| Banco de Dados | PostgreSQL 16 |
| Autenticação API | JWT (djangorestframework-simplejwt) |
| Servidor de Aplicação | Gunicorn |
| Proxy Reverso | Nginx |
| Containerização | Docker + Docker Compose |
| App Mobile (planejado) | Flutter (offline-first com Drift + sync) |

---

## Arquitetura

O projeto segue **Clean Architecture com DDD leve**, separando claramente as responsabilidades:

```
┌─────────────────────────────────────────────────────────────┐
│                      Interfaces                              │
│         (Views Web / ViewSets REST / Admin)                 │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                         │
│              (Services — orquestração)                      │
├─────────────────────────────────────────────────────────────┤
│                      Domain Layer                            │
│         (Calculadoras / Entities / Value Objects)           │
├─────────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                       │
│            (Models Django / Repositories)                   │
└─────────────────────────────────────────────────────────────┘
```

**Princípio central:** toda lógica financeira (juros, amortização, saldo devedor, parcelas, inadimplência) vive exclusivamente em `loans/domain/calculators.py` — nunca em views, serializers ou templates.

### Fluxo de um pagamento (exemplo)

```
View/API recebe request
    ↓
EmprestimoService.registrar_pagamento_comum()
    ↓
CalculadoraEmprestimoComum.aplicar_pagamento()   ← domínio puro
    ↓
Persistência (Django ORM) + Audit Log
    ↓
ClienteService.atualizar_classificacao()
    ↓
Response
```

---

## Estrutura do Projeto

```
agi_emprestimos/
│
├── api/v1/                    # Roteamento da API REST versionada
│
├── audit/                     # Auditoria e rastreabilidade
│   └── infrastructure/models.py   # AuditLog (append-only)
│
├── collaterals/               # Garantias e penhoras
│   ├── domain/
│   ├── application/services.py
│   ├── infrastructure/models.py
│   └── interfaces/            # API REST + Views Web
│
├── config/                    # Configurações Django
│   ├── settings/
│   │   ├── base.py            # Configurações compartilhadas
│   │   ├── development.py     # Desenvolvimento local
│   │   └── production.py      # Produção (Docker)
│   ├── urls.py
│   └── wsgi.py
│
├── core/                      # Base do sistema
│   ├── models.py              # BaseModel, SoftDeleteModel, ActiveManager
│   ├── models_config.py       # CapitalOperacional (singleton)
│   ├── exceptions.py          # Hierarquia de exceções
│   ├── utils.py               # Validação CPF, formatação moeda
│   └── management/commands/
│       ├── atualizar_inadimplencia.py   # Cron diário
│       └── popular_sistema.py           # Seed de dados
│
├── customers/                 # Clientes
│   ├── domain/entities.py
│   ├── application/services.py
│   ├── infrastructure/models.py
│   └── interfaces/            # API REST + Views Web + Forms
│
├── dashboard/                 # Dashboard e métricas
│   ├── application/metrics.py # Todos os cálculos do dashboard
│   └── interfaces/views.py
│
├── loans/                     # Empréstimos — núcleo do sistema
│   ├── domain/
│   │   ├── calculators.py     # ★ Toda a lógica financeira
│   │   ├── entities.py
│   │   ├── value_objects.py
│   │   └── exceptions.py
│   ├── application/services.py
│   ├── infrastructure/models.py
│   └── interfaces/            # API REST + Views Web + Forms
│
├── payments/                  # Histórico de pagamentos
│
├── templates/                 # Templates Django
│   ├── base/                  # base.html, login.html
│   ├── dashboard/
│   ├── customers/
│   ├── loans/
│   ├── payments/
│   └── collaterals/
│
├── static/                    # Arquivos estáticos
│   └── images/agi-logo.png
│
├── docker/
│   └── nginx/nginx.conf
│
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── Makefile
├── logica_de_negocio.md      # Documentação das regras de negócio
└── requirements.txt
```

---

## Instalação Local

### Pré-requisitos

- Python 3.12+
- PostgreSQL 16
- Git

### Passo a passo

```bash
# 1. Clone o repositório
git clone https://github.com/SEU_USUARIO/agi_emprestimos.git
cd agi_emprestimos

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure o ambiente
cp .env.example .env
# Edite .env com suas credenciais locais

# 5. Crie o banco de dados no PostgreSQL
psql -U postgres -c "CREATE DATABASE agi_emprestimos;"

# 6. Aplique as migrations
python manage.py migrate

# 7. Crie o superusuário
python manage.py createsuperuser

# 8. (Opcional) Popule com dados de demonstração
python manage.py popular_sistema

# 9. Inicie o servidor
python manage.py runserver
```

Acesse: http://127.0.0.1:8000

---

## Deploy em Produção (Docker)

### Pré-requisitos no VPS

- Docker + Docker Compose
- Nginx instalado no host (para proxy reverso e SSL)
- Domínio apontando para o IP do servidor

### Estrutura no VPS

```
/var/www/docker-instances/
└── agi_emprestimos/        ← repositório clonado aqui
```

### Deploy inicial

```bash
# 1. Acesse o diretório de instâncias Docker
cd /var/www/docker-instances

# 2. Clone o repositório
git clone https://github.com/SEU_USUARIO/agi_emprestimos.git
cd agi_emprestimos

# 3. Configure o ambiente de produção
cp .env.production.example .env
nano .env    # edite com credenciais reais

# 4. Gere uma SECRET_KEY segura
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
# Cole o resultado em SECRET_KEY no .env

# 5. Build e inicialização
make build

# 6. Verifique o status
make ps

# 7. Acompanhe os logs
make logs

# 8. Crie o superusuário
make createsuperuser
```

### Configuração do Nginx no host

```nginx
# /etc/nginx/sites-available/agiemprestimos.ferzion.com.br
server {
    listen 80;
    server_name agiemprestimos.ferzion.com.br;

    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Ative e recarregue
ln -s /etc/nginx/sites-available/agiemprestimos.ferzion.com.br \
      /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Configure HTTPS com Certbot
certbot --nginx -d agiemprestimos.ferzion.com.br
```

### Atualização (deploy contínuo)

```bash
cd /var/www/docker-instances/agi_emprestimos
git pull origin main
make build
```

### Arquitetura Docker

```
Internet (443/80)
      ↓
Nginx Host  ←── SSL termination (Certbot)
      ↓ proxy :8010
agi_nginx   ←── /static/ e /media/ direto
      ↓ proxy :8000
agi_web     ←── Gunicorn (3 workers)
      ↓
agi_db      ←── PostgreSQL 16
```

---

## Variáveis de Ambiente

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `SECRET_KEY` | Chave secreta Django (obrigatório, min. 50 chars) | `abc123...` |
| `DEBUG` | Modo debug | `False` |
| `ALLOWED_HOSTS` | Hosts permitidos (separado por vírgula) | `agiemprestimos.ferzion.com.br` |
| `DB_NAME` | Nome do banco de dados | `agi_emprestimos` |
| `DB_USER` | Usuário do PostgreSQL | `agi_user` |
| `DB_PASSWORD` | Senha do PostgreSQL | `senha_forte` |
| `DB_HOST` | Host do banco (Docker: `db`) | `db` |
| `DB_PORT` | Porta do PostgreSQL | `5432` |

---

## Comandos Úteis

### Desenvolvimento local

```bash
# Servidor de desenvolvimento
python manage.py runserver

# Criar migrations após alterar models
python manage.py makemigrations
python manage.py migrate

# Popular banco com dados de demonstração
python manage.py popular_sistema
python manage.py popular_sistema --limpar   # apaga antes de popular
python manage.py popular_sistema --clientes 50  # define quantidade

# Atualizar inadimplência manualmente
python manage.py atualizar_inadimplencia
python manage.py atualizar_inadimplencia --dry-run  # simula sem salvar
python manage.py atualizar_inadimplencia --data 2026-05-01  # data específica

# Executar testes
pytest
pytest loans/tests/test_calculators.py -v  # testes das calculadoras
pytest --tb=short  # traceback curto
```

### Docker (produção)

```bash
make up           # sobe todos os containers
make down         # para todos os containers
make restart      # reinicia web e nginx
make build        # rebuild completo + sobe
make logs         # logs em tempo real (todos)
make logs-web     # logs só do Django
make ps           # status dos containers
make shell        # Django shell
make bash         # bash no container
make migrate      # aplica migrations
make createsuperuser  # cria admin
make seed         # popula com dados de teste
make backup       # backup do banco de dados
make clean        # CUIDADO: remove todos os volumes
```

---

## Tipos de Empréstimo

### Empréstimo Comum (sem parcela fixa)

Juros simples mensais sobre o capital em aberto. O cliente escolhe como pagar a cada mês:

| Opção | O que acontece |
|-------|---------------|
| **Só os juros** | Capital permanece igual |
| **Juros + parte do capital** | Capital diminui proporcionalmente |
| **Quitação total** | Capital zerado, empréstimo encerrado |

```
Juros = Capital atual × Taxa mensal
Total para quitar = Capital atual + Juros do mês
```

### Empréstimo Parcelado — Modalidade Fixa

Parcelas iguais do início ao fim. Juros calculados sobre o capital **inicial** em todas as parcelas.

```
Parcela = (Capital / N) + (Capital × Taxa)   ← constante
```

### Empréstimo Parcelado — Modalidade SAC

Amortização constante, juros decrescentes — parcelas diminuem ao longo do tempo.

```
Amortização = Capital / N                    ← constante
Juros(i)    = Saldo devedor(i) × Taxa        ← decresce
Parcela(i)  = Amortização + Juros(i)         ← decresce
```

> O SAC sempre resulta em **menos juros totais** que a modalidade Fixa.

---

## API REST

A API segue REST com autenticação JWT. Base URL: `/api/v1/`

### Autenticação

```bash
# Login
POST /api/v1/auth/login/
{ "username": "admin", "password": "senha" }

# Refresh do token
POST /api/v1/auth/refresh/
{ "refresh": "<token>" }

# Logout (invalida o refresh token)
POST /api/v1/auth/logout/
```

### Endpoints principais

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/api/v1/clientes/` | Lista clientes |
| `POST` | `/api/v1/clientes/` | Cria cliente |
| `GET` | `/api/v1/clientes/{id}/` | Detalhe do cliente |
| `PUT/PATCH` | `/api/v1/clientes/{id}/` | Atualiza cliente |
| `POST` | `/api/v1/clientes/{id}/recalcular-classificacao/` | Recalcula risco |
| `GET` | `/api/v1/emprestimos/` | Lista empréstimos |
| `POST` | `/api/v1/emprestimos/criar-comum/` | Novo empréstimo comum |
| `POST` | `/api/v1/emprestimos/criar-parcelado/` | Novo empréstimo parcelado |
| `POST` | `/api/v1/emprestimos/simular-parcelas/` | Simula sem persistir |
| `POST` | `/api/v1/emprestimos/{id}/pagar/` | Registra pagamento |
| `POST` | `/api/v1/emprestimos/{id}/cancelar/` | Cancela empréstimo |
| `GET` | `/api/v1/pagamentos/` | Histórico de pagamentos |
| `GET` | `/api/v1/garantias/` | Lista garantias |
| `POST` | `/api/v1/garantias/` | Adiciona garantia |
| `GET` | `/api/v1/dashboard/metricas/` | Métricas do dashboard |

### Exemplo de uso

```bash
# Autenticar e obter token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access'])")

# Listar clientes
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/clientes/

# Criar empréstimo comum
curl -X POST http://localhost:8000/api/v1/emprestimos/criar-comum/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_id": "uuid-do-cliente",
    "capital": "1000.00",
    "taxa_mensal": "0.050000",
    "data_inicio": "2026-04-25"
  }'

# Simular parcelas (sem persistir)
curl -X POST http://localhost:8000/api/v1/emprestimos/simular-parcelas/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "cliente_id": "uuid-qualquer",
    "capital": "5000.00",
    "taxa_mensal": "0.080000",
    "n_parcelas": 12,
    "subtipo": "sac",
    "data_inicio": "2026-04-25",
    "data_primeira_parcela": "2026-05-25"
  }'
```

---

## Testes

O sistema possui testes unitários focados na lógica financeira (a parte mais crítica):

```bash
# Roda todos os testes
pytest

# Testes das calculadoras financeiras (23 testes)
pytest loans/tests/test_calculators.py -v

# Com cobertura
pip install pytest-cov
pytest --cov=loans/domain --cov-report=term-missing
```

### Cobertura dos testes

| Classe de Teste | O que testa | Testes |
|----------------|-------------|--------|
| `TestCalculadoraEmprestimoComum` | Juros, quitação, pagamento parcial, capitalização | 7 |
| `TestCalculadoraParceladoFixo` | Tabela de amortização, parcelas fixas, saldo zero | 5 |
| `TestCalculadoraParceladoSAC` | Parcelas decrescentes, amortização constante | 5 |
| `TestClassificacaoCliente` | Verde/amarelo/vermelho, exposição por garantia | 6 |
| **Total** | | **23** |

---

## Regras de Negócio

A documentação completa das regras de negócio está em [`logica_de_negocio.md`](logica_de_negocio.md), incluindo:

- Fluxo detalhado de cada tipo de empréstimo com fórmulas
- Regras de classificação de clientes
- Cálculo de exposição real ajustada por penhora
- Fórmulas de todas as métricas do dashboard
- Regras de inadimplência e capitalização

### Padrões técnicos

| Padrão | Implementação |
|--------|--------------|
| IDs | UUID v4 (todos os registros) |
| Exclusão | Soft delete via `deleted_at` |
| Timestamps | `created_at` e `updated_at` em todos os models |
| Precisão | `Decimal` com 28 casas + `ROUND_HALF_UP` |
| Taxas | Armazenadas como decimal (ex: `0.05` = 5% a.m.) |
| Auditoria | `AuditLog` via `GenericForeignKey` — append-only |
| Auth Web | Sessão Django |
| Auth API | JWT (access 8h + refresh 7d com blacklist) |

---

## Roadmap

- [x] Módulo de clientes completo
- [x] Empréstimo Comum
- [x] Empréstimo Parcelado (Fixo e SAC)
- [x] Garantias e penhoras
- [x] Dashboard com métricas financeiras
- [x] API REST com JWT
- [x] Interface web responsiva (HTMX + Tailwind)
- [x] Auditoria completa
- [x] Deploy Docker
- [ ] App Flutter offline-first
- [ ] Empréstimo na Diária
- [ ] Relatórios PDF (extrato do cliente, inadimplentes)
- [ ] Renegociação de empréstimos
- [ ] Notificações de vencimento (WhatsApp/SMS)
- [ ] Exportação de dados (Excel/CSV)

---

## Licença

Sistema privado — todos os direitos reservados.  
Desenvolvido para uso exclusivo do operador.

---

*Documentação atualizada em Abril de 2026.*