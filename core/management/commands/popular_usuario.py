"""
Seed FOCADO EM USUÁRIO(S) ESPECÍFICO(S) — não aplica a todos.

Diferente de `popular_sistema` (que usa o capital legado global e deixa garantias
sem dono), este comando cria uma operação COMPLETA e realista isolada por dono:
todos os registros (clientes, empréstimos, pagamentos, garantias, tags, capital,
movimentações, documentos, notificações) recebem `owner = <usuário alvo>`.

Uso:
  python manage.py popular_usuario joao                 # popula o usuário "joao"
  python manage.py popular_usuario joao maria           # popula dois usuários
  python manage.py popular_usuario joao --limpar        # apaga só os dados do joao antes
  python manage.py popular_usuario joao --clientes 60   # 60 clientes
  python manage.py popular_usuario joao --seed 7        # reprodutível
  python manage.py popular_usuario joao --capital 300000

Os usuários precisam existir (crie com `createsuperuser`). Para criar na hora,
use --criar-se-faltar (cria usuário comum com a senha de --senha).
"""
import random
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction

# Reaproveita os dados realistas e geradores já existentes.
from core.management.commands.popular_sistema import (
    NOMES_MASCULINOS, NOMES_FEMININOS, SOBRENOMES,
    CIDADES_PA, CIDADES_OUTRAS, PROFISSOES, BANCOS_LOGRADOUROS,
    PERFIS_PSICOLOGICOS, OBSERVACOES, DESCRICOES_GARANTIAS,
    gerar_cpf, gerar_telefone,
)

# ── Dados extras para deixar a operação bem rica ────────────────────────────

BAIRROS = [
    "Centro", "Nova Marabá", "Cidade Nova", "Jardim América", "São Félix",
    "Palmares", "Liberdade", "Cidade Jardim", "Beira Rio", "Morada Nova",
    "Rio Verde", "Bela Vista", "Industrial", "Vila Rica", "Primavera",
]

TAGS_PADRAO = [
    ("VIP", "purple"),
    ("Bom pagador", "green"),
    ("Renegociação", "yellow"),
    ("Atenção", "yellow"),
    ("Inadimplente", "red"),
    ("Indicador", "blue"),
    ("Comércio", "slate"),
    ("Funcionário público", "blue"),
    ("Primeira vez", "slate"),
]

DOCS_CLIENTE = [
    ("rg", "RG (frente e verso)"),
    ("cpf", "CPF"),
    ("cnh", "CNH digital"),
    ("comprovante_residencia", "Conta de energia do mês"),
    ("comprovante_renda", "Extrato bancário / holerite"),
    ("contrato", "Contrato de empréstimo assinado"),
]

OBS_EMPRESTIMO = [
    "Capital de giro para o comércio.", "Compra de mercadoria.",
    "Reforma da casa.", "Pagamento de dívida urgente.",
    "Material de construção.", "Conserto do veículo de trabalho.",
    "Investimento na roça.", "Despesa médica da família.",
    "", "", "Renegociado de um empréstimo anterior.",
]


def _money(v) -> Decimal:
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = 'Popula um ou mais usuários específicos com uma operação completa e realista.'

    def add_arguments(self, parser):
        parser.add_argument('usernames', nargs='+', help='Username(s) alvo do seed.')
        parser.add_argument('--limpar', action='store_true',
                            help='Apaga os dados existentes DESSE(S) usuário(s) antes.')
        parser.add_argument('--seed', type=int, default=2024, help='Seed reprodutível.')
        parser.add_argument('--clientes', type=int, default=40, help='Clientes por usuário.')
        parser.add_argument('--capital', type=str, default='200000',
                            help='Capital aportado inicial por usuário (R$).')
        parser.add_argument('--criar-se-faltar', action='store_true',
                            help='Cria o usuário (comum) se não existir.')
        parser.add_argument('--senha', type=str, default='trocar123',
                            help='Senha usada ao criar usuário com --criar-se-faltar.')

    def handle(self, *args, **options):
        usernames = options['usernames']
        # Cada usuário é populado isoladamente; uma seed derivada por username
        # mantém reprodutibilidade sem clonar exatamente os mesmos clientes.
        for idx, username in enumerate(usernames):
            usuario = self._resolver_usuario(username, options)
            random.seed(options['seed'] + idx * 1000)

            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n══════════════════════════════════════════════════'))
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'  Populando operação de: {usuario.username}'))
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'══════════════════════════════════════════════════'))

            with transaction.atomic():
                if options['limpar']:
                    self._limpar_usuario(usuario)
                self._popular(usuario, options)

        self.stdout.write(self.style.SUCCESS('\n✅  Concluído.\n'))

    # ── Usuário ─────────────────────────────────────────────────────────────

    def _resolver_usuario(self, username, options):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            if options['criar_se_faltar']:
                u = User.objects.create_user(username=username, password=options['senha'])
                self.stdout.write(self.style.WARNING(
                    f'  → Usuário "{username}" criado (senha: {options["senha"]}).'))
                return u
            raise CommandError(
                f'Usuário "{username}" não existe. Crie com createsuperuser '
                f'ou use --criar-se-faltar.'
            )

    # ── Limpeza isolada ─────────────────────────────────────────────────────

    def _limpar_usuario(self, usuario):
        from customers.application.services import ClienteService
        from customers.infrastructure.models import Cliente, TagCliente
        from core.models_config import (
            CapitalOperacional, MovimentacaoCapital, ConfiguracaoNotificacao,
        )

        self.stdout.write('  → Apagando dados anteriores deste usuário...')
        n = 0
        for cliente in Cliente.objects.filter(owner=usuario):
            ClienteService.apagar_cliente(str(cliente.id), usuario)
            n += 1
        TagCliente.objects.filter(owner=usuario).delete()
        MovimentacaoCapital.objects.filter(owner=usuario).delete()
        ConfiguracaoNotificacao.objects.filter(owner=usuario).delete()
        CapitalOperacional.objects.filter(owner=usuario).delete()
        self.stdout.write(self.style.WARNING(f'     {n} clientes (e dependentes) removidos.'))

    # ── Orquestração ────────────────────────────────────────────────────────

    def _popular(self, usuario, options):
        self._configurar_capital(usuario, options['capital'])
        tags = self._criar_tags(usuario)
        clientes = self._criar_clientes(options['clientes'], usuario, tags)
        self._criar_documentos_clientes(clientes)
        self._criar_emprestimos(clientes, usuario)
        self._configurar_notificacoes(usuario)
        self._desativar_alguns(clientes, usuario)
        self._reclassificar(clientes)

    # ── Capital ─────────────────────────────────────────────────────────────

    def _configurar_capital(self, usuario, capital_str):
        from core.capital import registrar_aporte, registrar_retirada

        capital = _money(capital_str)
        registrar_aporte(usuario, capital, 'Aporte inicial da operação',
                         quando=date.today() - relativedelta(months=18))
        # Alguns aportes e retiradas ao longo do tempo (histórico do caixa).
        for _ in range(random.randint(3, 6)):
            quando = date.today() - timedelta(days=random.randint(10, 500))
            if random.random() < 0.65:
                registrar_aporte(usuario, _money(random.uniform(2000, 25000)),
                                 'Reforço de capital', quando=quando)
            else:
                registrar_retirada(usuario, _money(random.uniform(1000, 12000)),
                                   'Retirada de lucro', quando=quando)
        self.stdout.write(f'  → Capital aportado: R$ {capital:,.2f} (+ movimentações)')

    # ── Tags ────────────────────────────────────────────────────────────────

    def _criar_tags(self, usuario):
        from customers.infrastructure.models import TagCliente
        tags = []
        for nome, cor in TAGS_PADRAO:
            tags.append(TagCliente.objects.create(owner=usuario, nome=nome, cor=cor))
        self.stdout.write(f'  → {len(tags)} tags criadas.')
        return tags

    # ── Clientes ────────────────────────────────────────────────────────────

    def _criar_clientes(self, n, usuario, tags):
        from customers.infrastructure.models import Cliente

        self.stdout.write(f'\n  Criando {n} clientes...')
        clientes, cpfs = [], set()

        classifs = (['verde'] * int(n * 0.5) + ['amarelo'] * int(n * 0.3)
                    + ['vermelho'] * int(n * 0.2))
        random.shuffle(classifs)
        classifs += ['verde'] * (n - len(classifs))

        for i in range(n):
            sexo = random.choice('MF')
            primeiro = random.choice(NOMES_MASCULINOS if sexo == 'M' else NOMES_FEMININOS)
            sobren = f"{random.choice(SOBRENOMES)} {random.choice(SOBRENOMES)}"
            nome = f"{primeiro} {sobren}"

            while True:
                cpf = gerar_cpf()
                if cpf not in cpfs:
                    cpfs.add(cpf)
                    break

            cidade, estado = random.choice(CIDADES_PA + CIDADES_OUTRAS)
            primeiro_sob = sobren.split()[0].lower()
            tem_email = random.random() < 0.7

            cliente = Cliente.objects.create(
                owner=usuario,
                nome=nome,
                cpf=cpf,
                rg=f"{random.randint(1,9)}.{random.randint(100,999)}.{random.randint(100,999)}" if random.random() < 0.7 else None,
                cnh=str(random.randint(10**10, 10**11 - 1)) if random.random() < 0.4 else None,
                data_nascimento=date(random.randint(1960, 2003), random.randint(1, 12), random.randint(1, 28)),
                profissao=random.choice(PROFISSOES),
                estado_civil=random.choice(['solteiro', 'casado', 'divorciado', 'viuvo', 'uniao_estavel']),
                tipo_residencia=random.choice(['propria', 'alugada', 'familiar', 'financiada']),
                renda_mensal=_money(random.choice([1412, 1800, 2200, 2500, 3000, 3500, 4200, 5000, 6500, 8000, 12000])) if random.random() < 0.75 else None,
                telefone_principal=gerar_telefone(),
                telefone_secundario=gerar_telefone() if random.random() < 0.5 else None,
                email=f"{primeiro.lower()}.{primeiro_sob}{random.randint(1,99)}@gmail.com" if tem_email else None,
                instagram=f"@{primeiro.lower()}{random.randint(10,99)}" if random.random() < 0.6 else None,
                facebook=f"facebook.com/{primeiro.lower()}.{primeiro_sob}" if random.random() < 0.35 else None,
                redes_sociais={'whatsapp': gerar_telefone()} if random.random() < 0.8 else {},
                cep=f"{random.randint(66,68)}{random.randint(100,999)}-{random.randint(100,999)}",
                logradouro=random.choice(BANCOS_LOGRADOUROS),
                numero=str(random.randint(10, 9999)),
                complemento=random.choice(['', '', 'Casa 2', 'Apto 101', 'Fundos', 'Bloco B']),
                bairro=random.choice(BAIRROS),
                cidade=cidade,
                estado=estado,
                origem=random.choices(['indicacao', 'proprio', 'redes_sociais', 'boato', 'outro'],
                                      weights=[35, 30, 20, 10, 5])[0],
                perfil_psicologico=random.choice(PERFIS_PSICOLOGICOS) if random.random() < 0.7 else None,
                observacoes=random.choice(OBSERVACOES),
                classificacao=classifs[i],
                prioridade_cobranca=random.choices(['preferencial', 'essencial'], weights=[75, 25])[0],
            )

            # Tags: 0–3 por cliente
            if tags and random.random() < 0.7:
                cliente.tags.set(random.sample(tags, random.randint(1, 3)))

            clientes.append(cliente)

        # Indicadores: clientes de indicação apontam para outro cliente.
        indicados = [c for c in clientes if c.origem == 'indicacao']
        outros = [c for c in clientes if c.origem != 'indicacao']
        for c in indicados:
            if outros:
                c.indicador = random.choice(outros)
                c.save(update_fields=['indicador'])

        self.stdout.write(self.style.SUCCESS(f'     {n} clientes criados.'))
        return clientes

    def _criar_documentos_clientes(self, clientes):
        from customers.infrastructure.models import DocumentoCliente
        total = 0
        for c in clientes:
            quantos = random.choices([0, 1, 2, 3, 4], weights=[10, 20, 30, 25, 15])[0]
            for tipo, descricao in random.sample(DOCS_CLIENTE, min(quantos, len(DOCS_CLIENTE))):
                DocumentoCliente.objects.create(
                    cliente=c, tipo=tipo, descricao=descricao,
                    arquivo=f'clientes/documentos/seed/{c.cpf}_{tipo}.pdf',
                )
                total += 1
        self.stdout.write(f'  → {total} documentos de clientes.')

    # ── Empréstimos + pagamentos ────────────────────────────────────────────

    def _criar_emprestimos(self, clientes, usuario):
        from loans.application.services import EmprestimoService

        self.stdout.write('\n  Criando empréstimos, pagamentos e garantias...')
        hoje = date.today()
        total_emp = total_gar = total_cancel = 0

        for cliente in clientes:
            # Maus pagadores tendem a ter menos crédito concedido.
            pesos = {'verde': [30, 40, 30], 'amarelo': [45, 40, 15], 'vermelho': [70, 25, 5]}
            n_emp = random.choices([1, 2, 3], weights=pesos[cliente.classificacao])[0]

            for _ in range(n_emp):
                tipo = random.choices(['comum', 'parcelado'], weights=[45, 55])[0]
                # Início: 90% antigos (com histórico), 10% recentes (limpos).
                if random.random() < 0.10:
                    data_inicio = hoje - timedelta(days=random.randint(1, 25))
                else:
                    data_inicio = hoje - timedelta(days=random.randint(40, 560))

                taxa = Decimal(str(round(random.uniform(0.04, 0.15), 4)))
                capital = Decimal(str(round(random.uniform(300, 9000) / 50) * 50))

                try:
                    if tipo == 'comum':
                        emp = EmprestimoService.criar_emprestimo_comum(
                            cliente_id=str(cliente.id), capital=capital, taxa_mensal=taxa,
                            data_inicio=data_inicio,
                            data_vencimento=data_inicio + relativedelta(months=1),
                            observacoes=random.choice(OBS_EMPRESTIMO), usuario=usuario,
                        )
                        self._pagamentos_comum(emp, usuario, hoje)
                    else:
                        n_parcelas = random.choice([3, 4, 5, 6, 8, 10, 12])
                        emp = EmprestimoService.criar_emprestimo_parcelado(
                            cliente_id=str(cliente.id), capital=capital, taxa_mensal=taxa,
                            n_parcelas=n_parcelas, subtipo=random.choice(['fixo', 'sac']),
                            data_inicio=data_inicio,
                            data_primeira_parcela=data_inicio + relativedelta(months=1),
                            observacoes=random.choice(OBS_EMPRESTIMO), usuario=usuario,
                        )
                        self._pagamentos_parcelado(emp, usuario, hoje)

                    # Cancela esporadicamente um empréstimo sem movimento (variedade).
                    emp.refresh_from_db()
                    if emp.status == 'ativo' and not emp.pagamentos.exists() and random.random() < 0.06:
                        emp.status = 'cancelado'
                        emp.save(update_fields=['status', 'updated_at'])
                        total_cancel += 1

                    if random.random() < 0.55:
                        self._criar_garantia(emp, usuario)
                        total_gar += 1
                    total_emp += 1
                except Exception as e:  # pragma: no cover - robustez do seed
                    self.stdout.write(self.style.WARNING(f'     ! empréstimo pulado: {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'     {total_emp} empréstimos · {total_gar} garantias · {total_cancel} cancelados.'))

    def _pagamentos_comum(self, emp, usuario, hoje):
        from loans.application.services import EmprestimoService
        from loans.domain.calculators import CalculadoraEmprestimoComum

        meses = max(0, (hoje - emp.data_inicio).days // 30)
        if meses == 0:
            return
        perfil = random.choices(['bom', 'regular', 'ruim', 'inadimplente'],
                                weights=[40, 30, 20, 10])[0]
        data_pag = emp.data_inicio + relativedelta(months=1)

        for mes in range(min(meses, 18)):
            if data_pag >= hoje or emp.capital_atual <= Decimal('0'):
                break
            # Inadimplente/ruim faltam alguns meses.
            if perfil in ('ruim', 'inadimplente') and random.random() < 0.35:
                data_pag += relativedelta(months=1)
                continue
            try:
                # Acumula o juros do ciclo (o 1º já saiu na criação).
                if mes > 0:
                    emp.juros_acumulados += CalculadoraEmprestimoComum.calcular_juros_mes(
                        emp.capital_atual, emp.taxa_juros_mensal)
                    emp.data_ultimo_acumulo = data_pag
                    emp.save(update_fields=['juros_acumulados', 'data_ultimo_acumulo', 'updated_at'])

                juros = emp.juros_acumulados
                total = emp.capital_atual + juros
                acao = random.choices(['quitar', 'juros', 'parcial'],
                                      weights={'bom': [18, 47, 35], 'regular': [8, 60, 32],
                                               'ruim': [3, 45, 22], 'inadimplente': [2, 25, 13]}[perfil])[0]
                if acao == 'quitar' and total <= Decimal('4000'):
                    valor = total
                elif acao == 'juros':
                    valor = juros
                else:
                    fator = Decimal(str(round(random.uniform(0.3, 0.8), 2)))
                    valor = _money(juros + emp.capital_atual * fator)
                if valor <= Decimal('0'):
                    data_pag += relativedelta(months=1)
                    continue

                EmprestimoService.registrar_pagamento_comum(
                    emprestimo_id=str(emp.id), valor=valor,
                    data_pagamento=data_pag, usuario=usuario)
                emp.refresh_from_db()
            except Exception:
                pass
            data_pag += relativedelta(months=1)

        # Vencido e ainda em aberto → marca inadimplente.
        emp.refresh_from_db()
        if (emp.status == 'ativo' and emp.data_vencimento and emp.data_vencimento < hoje
                and emp.capital_atual > Decimal('0') and random.random() < 0.5):
            emp.status = 'inadimplente'
            emp.save(update_fields=['status', 'updated_at'])

    def _pagamentos_parcelado(self, emp, usuario, hoje):
        from loans.application.services import EmprestimoService

        perfil = random.choices(['bom', 'regular', 'ruim'], weights=[45, 35, 20])[0]
        prob = {'bom': 0.92, 'regular': 0.72, 'ruim': 0.45}[perfil]

        vencidas = list(emp.parcelas.filter(
            data_vencimento__lt=hoje, status='pendente').order_by('numero'))

        for parcela in vencidas:
            emp.refresh_from_db()
            if emp.status in ('quitado', 'cancelado'):
                break
            if random.random() > prob:
                parcela.status = 'atrasado'
                parcela.save(update_fields=['status', 'updated_at'])
                continue
            atraso = random.randint(-2, 2) if perfil == 'bom' else random.randint(-3, 12)
            data_pag = parcela.data_vencimento + timedelta(days=max(0, atraso))
            if data_pag >= hoje:
                data_pag = parcela.data_vencimento
            # Às vezes paga parcial (perfil pior).
            if perfil != 'bom' and random.random() < 0.18:
                valor = _money(parcela.valor_em_aberto * Decimal(str(round(random.uniform(0.4, 0.8), 2))))
            else:
                valor = parcela.valor_em_aberto
            if valor <= Decimal('0'):
                continue
            try:
                EmprestimoService.registrar_pagamento_parcelas(
                    emprestimo_id=str(emp.id), parcela_ids=[str(parcela.id)],
                    valor=valor, data_pagamento=data_pag, usuario=usuario,
                    aplicar_excedente=False)
            except Exception:
                pass

        emp.refresh_from_db()
        if (emp.status == 'ativo' and emp.parcelas.filter(status='atrasado').exists()
                and random.random() < 0.6):
            emp.status = 'inadimplente'
            emp.save(update_fields=['status', 'updated_at'])

    def _criar_garantia(self, emp, usuario):
        from collaterals.infrastructure.models import Garantia, DocumentoGarantia

        if emp.capital_inicial >= Decimal('2000'):
            tipo = random.choices(['veiculo', 'imovel', 'eletronico', 'joia', 'outro'],
                                  weights=[50, 15, 20, 10, 5])[0]
        else:
            tipo = random.choices(['eletronico', 'joia', 'veiculo', 'outro'],
                                  weights=[40, 25, 25, 10])[0]
        opcao = random.choice(DESCRICOES_GARANTIAS.get(tipo, DESCRICOES_GARANTIAS['outro']))
        valor = Decimal(str(round(float(emp.capital_inicial * Decimal(str(round(random.uniform(0.8, 2.0), 2)))) / 100) * 100))
        garantia = Garantia.objects.create(
            owner=usuario,  # corrige o isolamento (o seed antigo deixava NULL)
            emprestimo=emp, tipo=tipo, descricao=opcao['descricao'],
            valor_estimado=valor,
            percentual_recuperacao=Decimal(str(round(random.uniform(0.50, 0.85), 2))),
            detalhes=opcao.get('detalhes', {}),
        )
        # Fotos/documentos da garantia em ~60% dos casos.
        if random.random() < 0.6:
            for k in range(random.randint(1, 3)):
                DocumentoGarantia.objects.create(
                    garantia=garantia, descricao=f'Foto {k + 1}',
                    arquivo=f'garantias/documentos/seed/{garantia.id}_{k}.jpg',
                )

    # ── Notificações ────────────────────────────────────────────────────────

    def _configurar_notificacoes(self, usuario):
        from core.models_config import ConfiguracaoNotificacao
        cfg = ConfiguracaoNotificacao.get_for_user(usuario)
        cfg.ativo = True
        cfg.notificar_1_dia = True
        cfg.notificar_3_dias = True
        cfg.notificar_7_dias = random.random() < 0.5
        cfg.save()
        self.stdout.write('  → Notificações configuradas.')

    # ── Desativados (demonstra o filtro "Mostrar desativados") ──────────────

    def _desativar_alguns(self, clientes, usuario):
        from loans.application.services import EmprestimoService
        from customers.application.services import ClienteService
        from payments.infrastructure.models import Pagamento
        from core.ownership import filtrar_por_usuario

        # Desativa 1–2 clientes sem empréstimo ativo.
        candidatos = [c for c in clientes if not c.tem_emprestimo_ativo]
        for c in random.sample(candidatos, min(len(candidatos), random.randint(1, 2))):
            ClienteService.desativar_cliente(str(c.id), usuario)

        # Desativa alguns pagamentos avulsos.
        pags = list(filtrar_por_usuario(
            Pagamento.objects.filter(deleted_at__isnull=True, tipo__in=['juros', 'capital_parcial']),
            usuario)[:50])
        for pag in random.sample(pags, min(len(pags), random.randint(1, 3))):
            try:
                EmprestimoService.desativar_pagamento(str(pag.id), usuario)
            except Exception:
                pass
        self.stdout.write('  → Alguns clientes/pagamentos desativados (para testar o filtro).')

    # ── Classificação ───────────────────────────────────────────────────────

    def _reclassificar(self, clientes):
        from customers.application.services import ClienteService
        for c in clientes:
            try:
                ClienteService.atualizar_classificacao(str(c.id))
            except Exception:
                pass
        self.stdout.write('  → Classificações recalculadas.')
