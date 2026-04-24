# Lógica de Negócio — Agi Empréstimos

> **Versão:** 1.0  
> **Data:** Abril de 2026  
> **Finalidade:** Descrever toda a lógica de negócio do sistema para servir como referência em futuras alterações.

---

## Sumário

1. [Visão Geral do Sistema](#1-visão-geral-do-sistema)
2. [Clientes](#2-clientes)
3. [Tipos de Empréstimo](#3-tipos-de-empréstimo)
   - 3.1 Empréstimo Comum (Sem Parcela)
   - 3.2 Empréstimo Parcelado — Modalidade Fixa
   - 3.3 Empréstimo Parcelado — Modalidade SAC
   - 3.4 Empréstimo na Diária *(reservado)*
4. [Pagamentos](#4-pagamentos)
5. [Garantias e Penhoras](#5-garantias-e-penhoras)
6. [Classificação de Risco do Cliente](#6-classificação-de-risco-do-cliente)
7. [Dashboard e Métricas](#7-dashboard-e-métricas)
8. [Auditoria e Rastreabilidade](#8-auditoria-e-rastreabilidade)
9. [Regras Gerais do Sistema](#9-regras-gerais-do-sistema)
10. [Referência Rápida de Fórmulas](#10-referência-rápida-de-fórmulas)

---

## 1. Visão Geral do Sistema

O **Agi Empréstimos** é um sistema de administração de crédito informal. O operador (credor) empresta capital próprio a clientes (tomadores), controla pagamentos, registra garantias (penhoras) e monitora a saúde financeira da carteira pelo dashboard.

**Princípios fundamentais:**
- Toda lógica financeira (juros, amortização, saldo devedor, parcelas) vive exclusivamente no backend Django, nunca no frontend ou no app mobile.
- O app mobile funciona offline e sincroniza com o servidor ao reconectar.
- Nenhum dado financeiro é destruído — apenas soft delete (marcação de exclusão).
- Todo pagamento é imutável após o registro — para corrigir, cancela-se e registra novo.

---

## 2. Clientes

### 2.1 Dados cadastrais

| Campo | Obrigatório | Descrição |
|-------|-------------|-----------|
| Nome completo | ✅ | Nome do tomador |
| CPF | ✅ | Validado pelo algoritmo da Receita Federal. Único no sistema. |
| RG | ❌ | Documento de identidade |
| CNH | ❌ | Carteira de habilitação |
| Data de nascimento | ❌ | |
| Foto do rosto | ❌ | Upload de imagem |
| Profissão | ❌ | Ocupação atual do cliente |
| Estado civil | ❌ | Solteiro / Casado / Divorciado / Viúvo / União Estável |
| Tipo de residência | ❌ | Própria / Alugada / Financiada / Casa de familiar / Outros |
| Telefone principal | ✅ | |
| Telefone secundário | ❌ | |
| E-mail | ❌ | |
| Instagram | ❌ | |
| Facebook | ❌ | |
| CEP / Endereço completo | ❌ | Preenchido automaticamente via ViaCEP ao digitar CEP |
| Origem | ✅ | Como o cliente chegou: Indicação / Prospecção própria / Redes sociais / Boato / Outro |
| Indicador | ❌ | Se origem = Indicação, qual cliente indicou (FK para outro cliente) |
| Perfil psicológico | ❌ | Campo livre para o operador descrever o comportamento do cliente |
| Observações | ❌ | Campo livre descritivo |

### 2.2 Regras de CPF
- Apenas dígitos são armazenados internamente (11 caracteres).
- O sistema formata automaticamente para exibição: `000.000.000-00`.
- CPF inválido ou duplicado é rejeitado no cadastro.

### 2.3 Exclusão de clientes
- Clientes nunca são deletados fisicamente.
- Soft delete: campo `deleted_at` é preenchido com a data/hora da exclusão.
- Clientes com empréstimos ativos não devem ser excluídos (proteção de integridade).

---

## 3. Tipos de Empréstimo

### Status possíveis de um empréstimo

| Status | Descrição |
|--------|-----------|
| `ativo` | Em andamento, dentro do prazo |
| `inadimplente` | Em atraso — cliente não pagou no vencimento |
| `quitado` | Capital zerado — empréstimo encerrado |
| `cancelado` | Cancelado antes de qualquer pagamento |
| `renegociado` | Substituído por novo empréstimo (renegociação) |

---

### 3.1 Empréstimo Comum (Sem Parcela)

**Conceito:** O cliente pega um valor de capital e paga juros mensais sobre esse capital. Não há número fixo de parcelas. O empréstimo continua até que o cliente quite o capital total.

#### Parâmetros obrigatórios
- Capital inicial (valor emprestado)
- Taxa de juros mensal (ex: 10% = 0.10)
- Data de início
- Data de vencimento (data combinada de pagamento mensal)

#### Cálculo dos juros mensais

```
Juros do mês = Capital atual × Taxa mensal

Exemplo: R$ 1.000,00 × 10% = R$ 100,00 de juros
```

#### As 3 opções de pagamento

**Opção 1 — Quitação total**
```
Valor pago = Capital atual + Juros do mês
Resultado: empréstimo encerrado, status → "quitado"

Exemplo: R$ 1.000 + R$ 100 = R$ 1.100,00
Após pagamento: capital_atual = R$ 0,00
```

**Opção 2 — Pagamento apenas dos juros**
```
Valor pago = Juros do mês (exatamente)
Resultado: capital permanece igual, juros quitados para o mês

Exemplo: paga R$ 100,00
Após pagamento: capital_atual = R$ 1.000,00 (sem alteração)
O mês seguinte reinicia o ciclo com os mesmos R$ 100 de juros
```

**Opção 3 — Pagamento parcial (juros + parte do capital)**
```
Valor pago > Juros do mês
Resultado: juros cobertos primeiro, excedente abate o capital

Exemplo: João paga R$ 600,00
  - R$ 100,00 cobrem os juros
  - R$ 500,00 abate o capital
  - Capital restante: R$ 1.000 - R$ 500 = R$ 500,00
  - No mês seguinte, juros = R$ 500 × 10% = R$ 50,00
```

#### Regra de capitalização (pagamento insuficiente)
```
Se valor_pago < juros_devidos:
  juros_não_cobertos = juros_devidos - valor_pago
  capital_atual = capital_atual + juros_não_cobertos

Exemplo: juros = R$ 100, cliente paga R$ 30
  Diferença: R$ 70 é adicionada ao capital
  Novo capital: R$ 1.000 + R$ 70 = R$ 1.070,00
```

> ⚠️ **Atenção:** A capitalização aumenta a dívida. Usar com consciência.

#### Fluxo de aplicação de pagamento
```
1. Calcular juros_devidos = capital_atual × taxa_mensal
2. Se valor_pago >= juros_devidos:
     juros_pagos = juros_devidos
     capital_abatido = min(valor_pago - juros_devidos, capital_atual)
     novo_capital = capital_atual - capital_abatido
     excedente = valor_pago - juros_pagos - capital_abatido
3. Se valor_pago < juros_devidos:
     juros_pagos = valor_pago
     juros_nao_cobertos = juros_devidos - valor_pago
     capital_abatido = 0
     novo_capital = capital_atual + juros_nao_cobertos
4. Se novo_capital == 0: status → "quitado"
```

---

### 3.2 Empréstimo Parcelado — Modalidade Fixa

**Conceito:** O capital é dividido em N parcelas iguais. Os juros são calculados sobre o **capital inicial** em todas as parcelas (não sobre o saldo devedor). Por isso, o valor da parcela é fixo do início ao fim.

#### Parâmetros obrigatórios
- Capital inicial
- Taxa de juros mensal
- Número de parcelas (1 a 360)
- Data de início
- Data da primeira parcela (as demais seguem mensalmente)

#### Fórmulas

```
Juros por parcela   = Capital inicial × Taxa mensal
                    = R$ 1.000 × 10% = R$ 100,00 (constante em todas)

Amortização         = Capital inicial ÷ N parcelas
                    = R$ 1.000 ÷ 6 = R$ 166,67

Valor da parcela    = Amortização + Juros por parcela
                    = R$ 166,67 + R$ 100,00 = R$ 266,67

Total a pagar       = Valor da parcela × N
                    = R$ 266,67 × 6 = R$ 1.600,02

Total de juros      = Juros por parcela × N
                    = R$ 100,00 × 6 = R$ 600,00
```

#### Tabela de exemplo (R$ 1.000 × 10% × 6x)

| # | Vencimento | Parcela | Juros | Capital | Saldo |
|---|-----------|---------|-------|---------|-------|
| 1 | 01/02/26 | R$ 266,67 | R$ 100,00 | R$ 166,67 | R$ 833,33 |
| 2 | 01/03/26 | R$ 266,67 | R$ 100,00 | R$ 166,67 | R$ 666,67 |
| 3 | 01/04/26 | R$ 266,67 | R$ 100,00 | R$ 166,67 | R$ 500,00 |
| 4 | 01/05/26 | R$ 266,67 | R$ 100,00 | R$ 166,67 | R$ 333,33 |
| 5 | 01/06/26 | R$ 266,67 | R$ 100,00 | R$ 166,67 | R$ 166,67 |
| 6 | 01/07/26 | R$ 266,67 | R$ 100,00 | R$ 166,67 | R$ 0,00 |

> **Característica:** Os juros são R$ 100,00 em todas as parcelas porque são calculados sempre sobre R$ 1.000,00 (capital inicial), não sobre o saldo devedor. Isso resulta em juros totais maiores que no SAC.

---

### 3.3 Empréstimo Parcelado — Modalidade SAC

**Conceito:** Sistema de Amortização Constante. A amortização do capital é igual em todas as parcelas, mas os juros são calculados sobre o **saldo devedor restante**. Como o saldo cai a cada mês, os juros diminuem e a parcela total decresce.

#### Parâmetros obrigatórios
- Mesmos do Parcelado Fixo

#### Fórmulas

```
Amortização constante = Capital inicial ÷ N parcelas (igual em todas)
                      = R$ 1.000 ÷ 10 = R$ 100,00

Juros(i)             = Saldo devedor(i) × Taxa mensal  ← decresce a cada mês
Parcela(i)           = Amortização + Juros(i)           ← decresce a cada mês
```

#### Tabela de exemplo (R$ 1.000 × 10% × 10x)

| # | Parcela | Juros | Capital (amort.) | Saldo |
|---|---------|-------|-----------------|-------|
| 1 | R$ 200,00 | R$ 100,00 | R$ 100,00 | R$ 900,00 |
| 2 | R$ 190,00 | R$ 90,00 | R$ 100,00 | R$ 800,00 |
| 3 | R$ 180,00 | R$ 80,00 | R$ 100,00 | R$ 700,00 |
| 4 | R$ 170,00 | R$ 70,00 | R$ 100,00 | R$ 600,00 |
| 5 | R$ 160,00 | R$ 60,00 | R$ 100,00 | R$ 500,00 |
| 6 | R$ 150,00 | R$ 50,00 | R$ 100,00 | R$ 400,00 |
| 7 | R$ 140,00 | R$ 40,00 | R$ 100,00 | R$ 300,00 |
| 8 | R$ 130,00 | R$ 30,00 | R$ 100,00 | R$ 200,00 |
| 9 | R$ 120,00 | R$ 20,00 | R$ 100,00 | R$ 100,00 |
| 10 | R$ 110,00 | R$ 10,00 | R$ 100,00 | R$ 0,00 |

**Total de juros SAC: R$ 550,00**  
**Total de juros Fixo (mesma base): R$ 1.000,00**

> ✅ **O SAC sempre resulta em menos juros totais que a modalidade Fixa**, pois os juros incidem sobre o saldo devedor real, que diminui a cada mês.

#### Quando usar cada modalidade

| Critério | Modalidade Fixa | SAC |
|---------|----------------|-----|
| Previsibilidade | ✅ Parcela igual todos os meses | ❌ Parcela muda |
| Total de juros | Maior | Menor |
| Facilidade de explicação | Mais simples | Requer explicação |
| Benefício para o tomador | Menor | Maior |

---

### 3.4 Empréstimo na Diária *(reservado para implementação futura)*

**Conceito previsto:** Modalidade voltada para empresários e comerciantes. O capital é emprestado com juros calculados por dia (não por mês).

**Status atual:** Estrutura de dados criada (tipo `diaria` existe no model), mas a lógica de cálculo ainda não foi implementada.

**Campos reservados:**
- `tipo = 'diaria'` no model `Emprestimo`
- A calculadora `CalculadoraEmprestimoDiaria` deve ser criada em `loans/domain/calculators.py` quando implementada.

---

## 4. Pagamentos

### 4.1 Regras gerais
- Todo pagamento é **imutável** após o registro (append-only).
- Para corrigir um pagamento errado: registrar estorno manual como novo pagamento com observação, ou soft delete do pagamento original seguido de novo registro.
- O sistema guarda snapshot do saldo antes e depois de cada pagamento (`capital_antes`, `capital_depois`).

### 4.2 Tipos de pagamento registrados automaticamente

| Tipo interno | Quando ocorre |
|-------------|---------------|
| `juros` | Valor pago cobre apenas os juros, sem abater capital |
| `capital_parcial` | Valor pago cobre juros + parte do capital |
| `capital_total` | Valor pago quita o capital inteiro (empréstimo encerrado) |
| `parcela` | Pagamento de parcela em empréstimo parcelado |

### 4.3 Fluxo de quitação automática
```
Se após o pagamento capital_atual == 0:
  → status do empréstimo = "quitado"
  → data_quitacao = data do pagamento
  → classificação do cliente é recalculada automaticamente
```

### 4.4 Excedente (troco)
```
Se valor_pago > (capital + juros):
  excedente = valor_pago - capital - juros
  O excedente é registrado mas não é devolvido automaticamente.
  O operador deve decidir o destino (abater próximo empréstimo, devolver, etc.)
```

---

## 5. Garantias e Penhoras

### 5.1 Conceito
Cada empréstimo pode ter zero ou mais bens vinculados como garantia (penhora). Em caso de inadimplência prolongada, o contrato é executado e o bem é tomado.

### 5.2 Tipos de garantia suportados

| Tipo | Campos adicionais |
|------|------------------|
| `veiculo` | Placa, Modelo, Ano, Chassi |
| `imovel` | Matrícula, Endereço do imóvel |
| `eletronico` | Descrição livre |
| `joia` | Descrição livre |
| `outro` | Descrição livre |

### 5.3 Campos de uma garantia

| Campo | Descrição |
|-------|-----------|
| Tipo | Categoria do bem |
| Descrição | Texto livre descrevendo o bem |
| Valor estimado | Valor de mercado estimado do bem |
| Percentual de recuperação | Quanto se espera recuperar em caso de execução (padrão: 70%) |
| Detalhes | JSON com dados específicos do tipo (placa, chassi, matrícula, etc.) |
| Documentos | Upload de fotos, contratos, notas fiscais |

### 5.4 Cálculo de exposição real

A exposição real é o quanto o operador pode efetivamente perder em um empréstimo inadimplente, considerando o valor recuperável das garantias.

```
Recuperação estimada = Valor da garantia × Percentual de recuperação
                     = R$ 5.000,00 × 70% = R$ 3.500,00

Perda ajustada       = max(0, Saldo devedor - Recuperação estimada)
                     = max(0, R$ 4.000,00 - R$ 3.500,00) = R$ 500,00

Cobertura (%)        = min(100%, Recuperação / Saldo devedor × 100)
                     = min(100%, R$ 3.500 / R$ 4.000 × 100) = 87,5%
```

#### Cenários de cobertura

| Situação | Cobertura | Perda ajustada |
|----------|-----------|----------------|
| Garantia cobre tudo | ≥ 100% | R$ 0,00 |
| Garantia cobre parcialmente | Entre 0% e 100% | Diferença |
| Sem garantia | 0% | = Saldo devedor |

### 5.5 Quando o percentual de recuperação é alterado
O percentual padrão de 70% pode ser ajustado por garantia. Exemplos:
- Carro popular com documentação: 70%
- Carro de luxo sem documentação: 40%
- Imóvel regularizado: 80%
- Eletrônico usado: 30%

### 5.6 Múltiplas garantias por empréstimo
```
Total de garantias       = Soma dos valores estimados
Total de recuperação     = Soma das recuperações estimadas de cada garantia
Perda ajustada total     = max(0, Saldo devedor - Total de recuperação)
```

---

## 6. Classificação de Risco do Cliente

A classificação é calculada automaticamente após cada pagamento ou marcação de inadimplência.

### 6.1 Regras de classificação

| Classificação | Critério |
|-------------|---------|
| 🟢 **Verde** — Bom Pagador | Nenhuma parcela atrasada em nenhum empréstimo ativo |
| 🟡 **Amarelo** — Regular | 1 ou 2 parcelas atrasadas no total da carteira |
| 🔴 **Vermelho** — Mau Pagador | 3 ou mais parcelas atrasadas OU qualquer empréstimo com status `inadimplente` |

### 6.2 Quando é recalculada
- Após qualquer pagamento registrado
- Quando um empréstimo é marcado como `inadimplente`
- Quando um empréstimo é quitado
- Ao acionar manualmente via botão "Recalcular Classificação" no perfil do cliente

### 6.3 Impacto da classificação
A classificação é visual e informativa. Ela **não bloqueia** automaticamente novos empréstimos — é o operador quem decide se empresta para clientes amarelos ou vermelhos. Serve como guia de análise de crédito.

---

## 7. Dashboard e Métricas

### 7.1 Capital

| Métrica | Fórmula |
|---------|---------|
| Capital total do operador | Valor informado manualmente pelo operador na tela "⚙ Capital Total" |
| Capital emprestado | Soma de `capital_atual` de todos os empréstimos com status `ativo` ou `inadimplente` |
| Capital em caixa | Capital total do operador − Capital emprestado |

> ⚠️ O capital em caixa pode ser negativo se o operador não atualizar o capital total cadastrado.

### 7.2 Capital por modalidade
Soma do `capital_atual` filtrado por tipo:
- Comum: empréstimos `tipo = 'comum'`
- Parcelado: empréstimos `tipo = 'parcelado'`
- Diária: empréstimos `tipo = 'diaria'`

### 7.3 Inadimplência

```
Taxa de inadimplência (%) = (Qtd empréstimos inadimplentes ÷ Total de empréstimos ativos) × 100
```

### 7.4 Taxa média de juros
```
Taxa média = Média aritmética de taxa_juros_mensal de todos os empréstimos ativos
           (em percentual: × 100)
```

> Melhoria futura: usar média ponderada pelo capital (empréstimos maiores têm mais peso).

### 7.5 Projeções de lucro mensal

Lucro base = soma dos juros esperados se todos pagarem:
```
Lucro base = Σ (capital_atual × taxa_juros_mensal) para cada empréstimo ativo
```

| Cenário | Fórmula | Interpretação |
|---------|---------|---------------|
| Otimista | Lucro base | Zero inadimplência nova |
| Realista | Lucro base × (1 − taxa_inadimplência_atual) | Mantém o nível atual de perdas |
| Pessimista | Lucro base × (1 − taxa_inadimplência × 1,5) | Inadimplência cresce 50% |

### 7.6 Custo da inadimplência ajustado por penhora

Esta é a métrica mais crítica do sistema. Mostra a **perda real esperada** considerando o que pode ser recuperado pelas garantias.

```
Para cada empréstimo inadimplente:
  recuperacao = Σ (valor_garantia × percentual_recuperacao)
  perda       = max(0, saldo_devedor - recuperacao)

Totais:
  Saldo em aberto          = Σ saldo_devedor de inadimplentes
  Recuperação estimada     = Σ recuperacao de inadimplentes
  Perda real ajustada      = Σ perda de inadimplentes
  Cobertura (%)            = Recuperação estimada ÷ Saldo em aberto × 100
```

**Exemplo:**

| Empréstimo | Saldo | Garantia | Recuperação (70%) | Perda |
|-----------|-------|---------|------------------|-------|
| João | R$ 2.000 | Moto R$ 3.000 | R$ 2.100 | R$ 0 |
| Maria | R$ 5.000 | Sem garantia | R$ 0 | R$ 5.000 |
| Pedro | R$ 3.000 | TV R$ 800 | R$ 560 | R$ 2.440 |
| **Total** | **R$ 10.000** | | **R$ 2.660** | **R$ 7.440** |

Cobertura = R$ 2.660 ÷ R$ 10.000 = 26,6%

### 7.7 Taxa de risco da operação

Métrica composta que combina inadimplência com exposição real:

```
Exposição real (%) = Perda ajustada ÷ Capital emprestado × 100

Taxa de risco      = (Taxa de inadimplência × 0,5) + (Exposição real × 0,5)
```

| Faixa | Avaliação |
|-------|-----------|
| 0% – 10% | 🟢 Operação saudável |
| 10% – 20% | 🟡 Atenção — revisar política de crédito |
| > 20% | 🔴 Risco elevado — ação imediata necessária |

---

## 8. Auditoria e Rastreabilidade

### 8.1 O que é auditado
Todo evento relevante gera um registro em `AuditLog`:

| Ação | Quando |
|------|--------|
| `create` | Criação de qualquer entidade |
| `update` | Alteração de dados |
| `delete` | Soft delete |
| `restore` | Restauração de registro deletado |
| `payment` | Registro de pagamento |
| `status_change` | Mudança de status do empréstimo |
| `classification_change` | Mudança de classificação do cliente |

### 8.2 Dados registrados por log
- Qual entidade (tabela + ID do registro)
- Qual ação foi executada
- Quem executou (usuário)
- IP e user-agent do requisitante
- Timestamp exato
- `changes`: JSON com os valores antes e depois da alteração

### 8.3 Imutabilidade dos logs
Registros de auditoria **nunca são editados ou deletados**. O admin bloqueia essas operações explicitamente.

---

## 9. Regras Gerais do Sistema

### 9.1 Identificadores
- Todos os registros usam **UUID v4** como chave primária.
- UUIDs evitam IDs sequenciais previsíveis e facilitam a sincronização offline do app Flutter.

### 9.2 Soft Delete
- Nenhuma entidade financeira é deletada fisicamente.
- Exclusão = preencher `deleted_at` com o timestamp atual.
- Registros com `deleted_at != null` são invisíveis nas listagens, mas existem no banco.
- Queries padrão filtram `deleted_at__isnull=True` automaticamente via `ActiveManager`.

### 9.3 Timestamps de sincronização
- `created_at`: preenchido automaticamente na criação (imutável).
- `updated_at`: atualizado automaticamente em qualquer alteração.
- `updated_at` é o vetor de sincronização do app Flutter: o app pede registros alterados após sua última sincronização.

### 9.4 Precisão financeira
- Todos os valores monetários usam `Decimal` (não `float`) para evitar erros de arredondamento.
- Precisão do contexto Decimal: 28 casas.
- Arredondamento: `ROUND_HALF_UP` (padrão financeiro brasileiro).
- Campos no banco: `DecimalField(max_digits=12, decimal_places=2)` para valores monetários.
- Taxas: `DecimalField(max_digits=8, decimal_places=6)` — ex: `0.050000` = 5% a.m.

### 9.5 Taxas de juros
- Armazenadas como decimal entre 0 e 1: `0.05` = 5% ao mês.
- Nunca armazenar como percentual (evita ambiguidade nos cálculos).
- Exibição: multiplicar por 100 apenas na camada de apresentação.

### 9.6 Autenticação
- Interface web: sessão Django com login/logout.
- API REST (Flutter): JWT (JSON Web Token) via `djangorestframework-simplejwt`.
  - Access token: válido por 8 horas.
  - Refresh token: válido por 7 dias, rotacionado a cada uso.
  - Logout invalida o refresh token via blacklist.

---

## 10. Referência Rápida de Fórmulas

```
──────────────────────────────────────────────────────────
EMPRÉSTIMO COMUM
──────────────────────────────────────────────────────────
Juros do mês          = Capital atual × Taxa mensal
Total para quitar     = Capital atual + Juros do mês
Após pagar juros só   = Capital não muda
Após pagar parcial    = Capital -= (Valor pago - Juros)
Capitalização         = Capital += (Juros - Valor pago)   [só se pagar menos que juros]

──────────────────────────────────────────────────────────
PARCELADO FIXO
──────────────────────────────────────────────────────────
Amortização           = Capital inicial ÷ N parcelas
Juros por parcela     = Capital inicial × Taxa mensal      [constante]
Valor da parcela      = Amortização + Juros por parcela    [constante]
Total de juros        = Juros por parcela × N

──────────────────────────────────────────────────────────
PARCELADO SAC
──────────────────────────────────────────────────────────
Amortização           = Capital inicial ÷ N parcelas       [constante]
Juros(i)              = Saldo devedor(i) × Taxa mensal     [decresce]
Parcela(i)            = Amortização + Juros(i)             [decresce]
Total de juros        = Σ Juros(i) para i=1..N

──────────────────────────────────────────────────────────
GARANTIAS
──────────────────────────────────────────────────────────
Recuperação estimada  = Valor do bem × % de recuperação
Perda ajustada        = max(0, Saldo devedor - Recuperação estimada)
Cobertura (%)         = min(100%, Recuperação ÷ Saldo × 100)

──────────────────────────────────────────────────────────
DASHBOARD
──────────────────────────────────────────────────────────
Capital em caixa      = Capital total operador - Capital emprestado
Taxa inadimplência    = Inadimplentes ÷ Total ativos × 100
Lucro base            = Σ (capital_atual × taxa_mensal)
Projeção otimista     = Lucro base
Projeção realista     = Lucro base × (1 - taxa_inadimplência)
Projeção pessimista   = Lucro base × (1 - taxa_inadimplência × 1,5)
Taxa de risco         = (Taxa_inadimplência × 0,5) + (Exposição_real × 0,5)
```

---

*Documento gerado em 22/04/2026. Para propor alterações na lógica de negócio, editar este arquivo e abrir discussão com o desenvolvedor antes de modificar o código.*