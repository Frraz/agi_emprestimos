"""
Comando para popular o sistema Agi Empréstimos com dados realistas.

Uso:
  python manage.py popular_sistema
  python manage.py popular_sistema --limpar   (apaga tudo antes)
  python manage.py popular_sistema --seed 42  (resultado reproduzível)
"""
import random
from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction


# ── Dados realistas brasileiros ────────────────────────────────────────────

NOMES_MASCULINOS = [
    "João", "Pedro", "Carlos", "André", "Rafael", "Lucas", "Thiago",
    "Rodrigo", "Fernando", "Marcos", "Eduardo", "Bruno", "Felipe",
    "Diego", "Gustavo", "Henrique", "Leandro", "Matheus", "Vinicius",
    "Gabriel", "Daniel", "Alexandre", "Renato", "Flávio", "Sérgio",
]

NOMES_FEMININOS = [
    "Ana", "Maria", "Juliana", "Fernanda", "Patricia", "Camila", "Larissa",
    "Beatriz", "Amanda", "Aline", "Leticia", "Vanessa", "Priscila",
    "Carla", "Mariana", "Tatiana", "Claudia", "Sandra", "Simone",
    "Cristina", "Luciana", "Gabriela", "Isabela", "Rafaela", "Natalia",
]

SOBRENOMES = [
    "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira",
    "Alves", "Pereira", "Lima", "Gomes", "Costa", "Ribeiro", "Martins",
    "Carvalho", "Almeida", "Lopes", "Sousa", "Fernandes", "Vieira",
    "Barbosa", "Rocha", "Dias", "Nascimento", "Andrade", "Moreira",
    "Nunes", "Marques", "Machado", "Mendes", "Freitas",
]

CIDADES_PA = [
    ("Parauapebas", "PA"), ("Marabá", "PA"), ("Belém", "PA"),
    ("Altamira", "PA"), ("Santarém", "PA"), ("Ananindeua", "PA"),
    ("Castanhal", "PA"), ("Barcarena", "PA"), ("Tucuruí", "PA"),
    ("Xinguara", "PA"),
]

CIDADES_OUTRAS = [
    ("Goiânia", "GO"), ("Palmas", "TO"), ("Imperatriz", "MA"),
    ("Araguaína", "TO"), ("São Félix do Xingu", "PA"),
]

PROFISSOES = [
    "Comerciante", "Autônomo", "Motorista", "Pedreiro", "Eletricista",
    "Mecânico", "Vendedor", "Funcionário público", "Professor",
    "Agropecuarista", "Madeireiro", "Garimpeiro", "Agricultor",
    "Técnico em informática", "Serviços gerais", "Cozinheiro",
    "Borracheiro", "Marceneiro", "Pintor", "Empresário",
]

BANCOS_LOGRADOUROS = [
    "Rua das Flores", "Av. Brasil", "Travessa Central", "Rua São João",
    "Av. Marechal Rondon", "Rua Barão do Rio Branco", "Av. Independência",
    "Rua 7 de Setembro", "Av. Perimetral", "Rua Dom Pedro II",
]

PERFIS_PSICOLOGICOS = [
    "Cliente comunicativo, sempre mantém contato antes do vencimento. Demonstra preocupação com as dívidas.",
    "Perfil reservado, mas cumpre os compromissos. Preferência por pagamento em dinheiro.",
    "Muito organizado, solicita comprovantes sempre. Honra os prazos com precisão.",
    "Cliente influente na comunidade. Indicou vários outros clientes. Bom relacionamento.",
    "Histórico de atrasos pontuais, mas sempre regulariza. Precisa de lembretes.",
    "Empresário com fluxo de caixa irregular. Paga em grandes parcelas esporádicas.",
    "Perfil ansioso, liga frequentemente para verificar saldo. Não costuma atrasar.",
    "Cliente antigo da região. Confiável, mas costuma querer renegociar prazos.",
    "Jovem empreendedor, negócio em crescimento. Boa perspectiva de crédito.",
    "Trabalhador formal, desconto em folha seria o ideal. Pagamentos regulares.",
]

OBSERVACOES = [
    "Mora no mesmo endereço há mais de 10 anos. Referências na vizinhança.",
    "Possui terreno próprio como patrimônio. Situação financeira estável.",
    "Indicado pelo João Silva. Trabalha na mesma empresa há 5 anos.",
    "Cuidado: já tentou renegociar informalmente. Exigir documentação.",
    "Negócio sazonal — vende mais no segundo semestre. Considerar ao cobrar.",
    "Boa família na cidade, nome limpo. Primeira experiência com crédito.",
    "Usa o dinheiro para capital de giro. Retorno rápido geralmente.",
    "Possui carro próprio registrado no seu nome. Boa garantia potencial.",
    None, None,  # Alguns sem observação
]

DESCRICOES_GARANTIAS = {
    "veiculo": [
        {"descricao": "Honda CG 160 2020 prata", "detalhes": {"placa": "QRS-1A23", "modelo": "Honda CG 160 Fan", "ano": "2020", "chassi": "9C2JC4110LR001234"}},
        {"descricao": "Yamaha Fazer 250 2019 vermelha", "detalhes": {"placa": "MNO-2B45", "modelo": "Yamaha Fazer 250", "ano": "2019", "chassi": "9C6RG2110K0001567"}},
        {"descricao": "VW Gol 1.0 2017 branco", "detalhes": {"placa": "ABC-3C67", "modelo": "VW Gol 1.0", "ano": "2017", "chassi": "9BWZZZ377HT000789"}},
        {"descricao": "Fiat Strada 1.4 2018 prata", "detalhes": {"placa": "DEF-4D89", "modelo": "Fiat Strada Working", "ano": "2018", "chassi": "9BD158A5XJ2001234"}},
        {"descricao": "Chevrolet S10 2016 preta", "detalhes": {"placa": "GHI-5E12", "modelo": "Chevrolet S10 LS", "ano": "2016", "chassi": "9BGJG8EC0GB001234"}},
        {"descricao": "Honda Biz 125 2021 azul", "detalhes": {"placa": "JKL-6F34", "modelo": "Honda Biz 125", "ano": "2021", "chassi": "9C2JA0510MR002345"}},
    ],
    "eletronico": [
        {"descricao": "Notebook Dell Inspiron i5 8GB RAM", "detalhes": {}},
        {"descricao": "TV Samsung 55' QLED 4K", "detalhes": {}},
        {"descricao": "iPhone 13 128GB", "detalhes": {}},
        {"descricao": "PlayStation 5 + 2 controles", "detalhes": {}},
    ],
    "joia": [
        {"descricao": "Corrente de ouro 18k 50g", "detalhes": {}},
        {"descricao": "Par de brincos e anel de ouro", "detalhes": {}},
        {"descricao": "Relógio Casio G-Shock dourado", "detalhes": {}},
    ],
    "imovel": [
        {"descricao": "Terreno urbano 300m² com escritura", "detalhes": {"matricula": "Matrícula 45.123", "endereco_imovel": "Lot. Jardim das Flores, Qd 15 Lt 08"}},
        {"descricao": "Casa de alvenaria 2 quartos própria", "detalhes": {"matricula": "Matrícula 67.890", "endereco_imovel": "Rua das Acácias, 145"}},
    ],
    "outro": [
        {"descricao": "Geladeira Brastemp Frost Free 450L", "detalhes": {}},
        {"descricao": "Máquina de lavar roupas 12kg Electrolux", "detalhes": {}},
    ],
}


# ── Gerador de CPF válido ──────────────────────────────────────────────────

def gerar_cpf():
    def digito(base):
        soma = sum(d * p for d, p in zip(base, range(len(base) + 1, 1, -1)))
        resto = (soma * 10) % 11
        return 0 if resto >= 10 else resto

    while True:
        nums = [random.randint(0, 9) for _ in range(9)]
        if len(set(nums)) == 1:
            continue
        d1 = digito(nums)
        d2 = digito(nums + [d1])
        return ''.join(map(str, nums + [d1, d2]))


def gerar_telefone():
    ddd = random.choice(["94", "91", "93", "92", "62", "63"])
    numero = f"9{random.randint(1000,9999)}{random.randint(1000,9999)}"
    return f"({ddd}) {numero[:5]}-{numero[5:]}"


class Command(BaseCommand):
    help = 'Popula o sistema com dados realistas para demonstração.'

    def add_arguments(self, parser):
        parser.add_argument('--limpar', action='store_true', help='Remove dados existentes antes de popular')
        parser.add_argument('--seed', type=int, default=2024, help='Seed para reprodutibilidade')
        parser.add_argument('--clientes', type=int, default=35, help='Número de clientes')

    def handle(self, *args, **options):
        random.seed(options['seed'])
        n_clientes = options['clientes']

        self.stdout.write(self.style.MIGRATE_HEADING('\n══════════════════════════════════════'))
        self.stdout.write(self.style.MIGRATE_HEADING('  Agi Empréstimos — Popular Sistema'))
        self.stdout.write(self.style.MIGRATE_HEADING('══════════════════════════════════════\n'))

        with transaction.atomic():
            if options['limpar']:
                self._limpar_dados()

            usuario = self._get_or_create_usuario()
            self._configurar_capital()
            clientes = self._criar_clientes(n_clientes, usuario)
            self._criar_emprestimos(clientes, usuario)

        self.stdout.write(self.style.SUCCESS('\n✅  Sistema populado com sucesso!\n'))
        self.stdout.write('   Acesse: http://127.0.0.1:8000\n')

    # ── Limpar ──────────────────────────────────────────────────────────────

    def _limpar_dados(self):
        self.stdout.write('  → Removendo dados anteriores...')
        from payments.infrastructure.models import Pagamento
        from loans.infrastructure.models import Emprestimo, ParcelaEmprestimo
        from collaterals.infrastructure.models import Garantia, DocumentoGarantia
        from customers.infrastructure.models import Cliente, DocumentoCliente
        from audit.infrastructure.models import AuditLog
        from core.models_config import CapitalOperacional

        AuditLog.objects.all().delete()
        DocumentoGarantia.objects.all().delete()
        Garantia.objects.all().delete()
        Pagamento.objects.all().delete()
        ParcelaEmprestimo.objects.all().delete()
        Emprestimo.objects.all().delete()
        DocumentoCliente.objects.all().delete()
        Cliente.objects.all().delete()
        CapitalOperacional.objects.all().delete()
        self.stdout.write(self.style.WARNING('     Dados removidos.'))

    # ── Usuário ─────────────────────────────────────────────────────────────

    def _get_or_create_usuario(self):
        usuario, criado = User.objects.get_or_create(
            username='admin',
            defaults={'is_superuser': True, 'is_staff': True, 'email': 'admin@agi.com'}
        )
        if criado:
            usuario.set_password('admin123')
            usuario.save()
            self.stdout.write('  → Usuário admin criado (senha: admin123)')
        else:
            self.stdout.write('  → Usando usuário admin existente')
        return usuario

    # ── Capital operacional ─────────────────────────────────────────────────

    def _configurar_capital(self):
        from core.models_config import CapitalOperacional
        config = CapitalOperacional.get_instance()
        config.total_capital = Decimal('150000.00')
        config.observacoes = 'Capital inicial configurado pelo sistema de demonstração.'
        config.save()
        self.stdout.write('  → Capital operacional: R$ 150.000,00')

    # ── Clientes ────────────────────────────────────────────────────────────

    def _criar_clientes(self, n: int, usuario):
        from customers.infrastructure.models import Cliente

        self.stdout.write(f'\n  Criando {n} clientes...')
        clientes = []
        cpfs_usados = set()

        # Garante um de cada classificação inicial
        perfis = (
            ['verde'] * int(n * 0.55) +
            ['amarelo'] * int(n * 0.25) +
            ['vermelho'] * int(n * 0.20)
        )
        random.shuffle(perfis)
        if len(perfis) < n:
            perfis += ['verde'] * (n - len(perfis))

        for i in range(n):
            sexo = random.choice(['M', 'F'])
            nome_p = random.choice(NOMES_MASCULINOS if sexo == 'M' else NOMES_FEMININOS)
            sobrenome = f"{random.choice(SOBRENOMES)} {random.choice(SOBRENOMES)}"
            nome = f"{nome_p} {sobrenome}"

            while True:
                cpf = gerar_cpf()
                if cpf not in cpfs_usados:
                    cpfs_usados.add(cpf)
                    break

            cidade, estado = random.choice(CIDADES_PA + CIDADES_OUTRAS)
            logradouro = random.choice(BANCOS_LOGRADOUROS)
            numero = str(random.randint(10, 9999))

            data_nasc = date(
                random.randint(1960, 2000),
                random.randint(1, 12),
                random.randint(1, 28)
            )

            origem = random.choices(
                ['indicacao', 'proprio', 'redes_sociais', 'boato', 'outro'],
                weights=[35, 30, 20, 10, 5]
            )[0]

            instagram = None
            facebook = None
            if random.random() < 0.6:
                instagram = f"@{nome_p.lower()}{random.randint(10,99)}"
            if random.random() < 0.4:
                facebook = f"facebook.com/{nome_p.lower()}.{sobrenome.split()[0].lower()}"

            cliente = Cliente.objects.create(
                nome=nome,
                cpf=cpf,
                data_nascimento=data_nasc,
                profissao=random.choice(PROFISSOES),
                estado_civil=random.choice(['solteiro', 'casado', 'divorciado', 'uniao_estavel']),
                tipo_residencia=random.choice(['propria', 'alugada', 'familiar', 'financiada']),
                telefone_principal=gerar_telefone(),
                telefone_secundario=gerar_telefone() if random.random() < 0.5 else None,
                email=f"{nome_p.lower()}.{sobrenome.split()[0].lower()}{random.randint(1,99)}@gmail.com" if random.random() < 0.6 else None,
                instagram=instagram,
                facebook=facebook,
                cep=f"{random.randint(66,68)}{random.randint(100,999)}-{random.randint(100,999)}",
                logradouro=logradouro,
                numero=numero,
                bairro=random.choice(["Centro", "Nova Marabá", "Cidade Nova", "Jardim América", "São Félix", "Palmares"]),
                cidade=cidade,
                estado=estado,
                origem=origem,
                perfil_psicologico=random.choice(PERFIS_PSICOLOGICOS) if random.random() < 0.7 else None,
                observacoes=random.choice(OBSERVACOES),
                classificacao=perfis[i],
            )

            clientes.append(cliente)

        # Vincula indicadores (30% dos clientes de indicação)
        clientes_indicacao = [c for c in clientes if c.origem == 'indicacao']
        outros = [c for c in clientes if c.origem != 'indicacao']
        for c in clientes_indicacao:
            if outros:
                c.indicador = random.choice(outros)
                c.save(update_fields=['indicador'])

        self.stdout.write(self.style.SUCCESS(f'     {n} clientes criados.'))
        return clientes

    # ── Empréstimos ─────────────────────────────────────────────────────────

    def _criar_emprestimos(self, clientes: list, usuario):
        from loans.application.services import EmprestimoService
        from loans.infrastructure.models import Emprestimo
        from collaterals.infrastructure.models import Garantia

        self.stdout.write('\n  Criando empréstimos e pagamentos...')

        total_emp = 0
        total_pag = 0
        total_gar = 0

        hoje = date.today()

        # Cada cliente recebe 1 a 3 empréstimos
        for cliente in clientes:
            n_emp = random.choices([1, 2, 3], weights=[50, 35, 15])[0]

            for _ in range(n_emp):
                tipo = random.choices(
                    ['comum', 'parcelado'],
                    weights=[45, 55]
                )[0]

                # Data de início: entre 18 meses atrás e 2 meses atrás
                dias_atras = random.randint(15, 540)
                data_inicio = hoje - timedelta(days=dias_atras)

                # Taxa entre 4% e 15% ao mês (crédito informal)
                taxa = Decimal(str(round(random.uniform(0.04, 0.15), 4)))

                # Capital entre R$ 200 e R$ 8.000
                capital = Decimal(str(round(random.uniform(200, 8000), 2)))
                # Arredonda para valores "redondos" (mais realista)
                capital = Decimal(str(round(float(capital) / 50) * 50))

                try:
                    if tipo == 'comum':
                        emp = EmprestimoService.criar_emprestimo_comum(
                            cliente_id=str(cliente.id),
                            capital=capital,
                            taxa_mensal=taxa,
                            data_inicio=data_inicio,
                            observacoes='',
                            usuario=usuario,
                        )
                        self._simular_pagamentos_comum(emp, usuario, hoje)

                    else:
                        n_parcelas = random.choice([3, 4, 6, 8, 10, 12])
                        subtipo = random.choice(['fixo', 'sac'])
                        data_primeira = data_inicio + relativedelta(months=1)

                        emp = EmprestimoService.criar_emprestimo_parcelado(
                            cliente_id=str(cliente.id),
                            capital=capital,
                            taxa_mensal=taxa,
                            n_parcelas=n_parcelas,
                            subtipo=subtipo,
                            data_inicio=data_inicio,
                            data_primeira_parcela=data_primeira,
                            observacoes='',
                            usuario=usuario,
                        )
                        self._simular_pagamentos_parcelado(emp, usuario, hoje)

                    # Adiciona garantia em 55% dos empréstimos
                    if random.random() < 0.55:
                        self._criar_garantia(emp)
                        total_gar += 1

                    total_emp += 1

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'     Erro ao criar empréstimo: {e}'))

        # Recalcula classificações de todos os clientes
        self.stdout.write('  → Recalculando classificações...')
        from customers.application.services import ClienteService
        for cliente in clientes:
            try:
                ClienteService.atualizar_classificacao(str(cliente.id))
            except Exception:
                pass

        self.stdout.write(self.style.SUCCESS(
            f'     {total_emp} empréstimos · {total_gar} garantias criados.'
        ))

    def _simular_pagamentos_comum(self, emp, usuario, hoje):
        """Simula histórico de pagamentos para empréstimo comum."""
        from loans.application.services import EmprestimoService

        if emp.status in ('quitado', 'cancelado'):
            return

        meses_decorridos = max(0, (hoje - emp.data_inicio).days // 30)
        if meses_decorridos == 0:
            return

        perfil_pagamento = random.choices(
            ['bom', 'regular', 'ruim', 'inadimplente'],
            weights=[40, 30, 20, 10]
        )[0]

        data_pag = emp.data_inicio + relativedelta(months=1)

        for mes in range(min(meses_decorridos, 18)):
            if data_pag >= hoje:
                break
            if emp.capital_atual <= Decimal('0'):
                break

            tipo_pag = random.choices(
                ['quitar', 'juros', 'parcial'],
                weights={
                    'bom':         [15, 50, 35],
                    'regular':     [8,  60, 32],
                    'ruim':        [3,  40, 20],
                    'inadimplente':[2,  20, 10],
                }[perfil_pagamento]
            )[0]

            # Perfil ruim/inadimplente pula alguns meses
            if perfil_pagamento in ('ruim', 'inadimplente') and random.random() < 0.35:
                data_pag += relativedelta(months=1)
                continue

            try:
                from loans.domain.calculators import CalculadoraEmprestimoComum
                juros = CalculadoraEmprestimoComum.calcular_juros_mes(
                    emp.capital_atual, emp.taxa_juros_mensal
                )
                total = emp.capital_atual + juros

                if tipo_pag == 'quitar' and total <= Decimal('3000'):
                    valor = total
                elif tipo_pag == 'juros':
                    valor = juros
                elif tipo_pag == 'parcial':
                    fator = Decimal(str(round(random.uniform(0.3, 0.8), 2)))
                    valor = (juros + emp.capital_atual * fator).quantize(Decimal('0.01'))
                else:
                    data_pag += relativedelta(months=1)
                    continue

                emp.refresh_from_db()
                EmprestimoService.registrar_pagamento_comum(
                    emprestimo_id=str(emp.id),
                    valor=valor,
                    data_pagamento=data_pag,
                    observacoes='',
                    usuario=usuario,
                )
                emp.refresh_from_db()

            except Exception:
                pass

            data_pag += relativedelta(months=1)

        # Marca inadimplentes se data de vencimento passou
        if emp.data_vencimento and emp.data_vencimento < hoje and emp.status == 'ativo':
            if random.random() < 0.4:
                emp.status = 'inadimplente'
                emp.save(update_fields=['status', 'updated_at'])

    def _simular_pagamentos_parcelado(self, emp, usuario, hoje):
        """Simula pagamentos de parcelas."""
        from loans.infrastructure.models import ParcelaEmprestimo
        from payments.infrastructure.models import Pagamento

        perfil = random.choices(
            ['bom', 'regular', 'ruim'],
            weights=[45, 35, 20]
        )[0]

        parcelas_vencidas = emp.parcelas.filter(
            data_vencimento__lt=hoje,
            status='pendente',
        ).order_by('numero')

        for parcela in parcelas_vencidas:
            # Probabilidade de pagar baseada no perfil
            prob = {'bom': 0.90, 'regular': 0.70, 'ruim': 0.45}[perfil]

            if random.random() > prob:
                parcela.status = 'atrasado'
                parcela.save(update_fields=['status', 'updated_at'])
                continue

            # Data de pagamento: entre o vencimento e alguns dias depois
            atraso = random.randint(-5, 10) if perfil != 'bom' else random.randint(-2, 2)
            data_pag = parcela.data_vencimento + timedelta(days=max(0, atraso))
            if data_pag >= hoje:
                data_pag = parcela.data_vencimento

            try:
                Pagamento.objects.create(
                    emprestimo=emp,
                    parcela=parcela,
                    valor=parcela.valor_parcela,
                    tipo='parcela',
                    data_pagamento=data_pag,
                    valor_juros_pagos=parcela.valor_juros,
                    valor_capital_pago=parcela.valor_principal,
                    capital_antes=parcela.saldo_devedor_antes,
                    capital_depois=parcela.saldo_devedor_depois,
                    registrado_por=usuario,
                )
                parcela.valor_pago = parcela.valor_parcela
                parcela.status = 'pago'
                parcela.data_pagamento = data_pag
                parcela.save(update_fields=['valor_pago', 'status', 'data_pagamento', 'updated_at'])

                # Atualiza capital do empréstimo
                emp.capital_atual = parcela.saldo_devedor_depois
                if parcela.saldo_devedor_depois <= Decimal('0'):
                    emp.status = 'quitado'
                    emp.data_quitacao = data_pag
                emp.save(update_fields=['capital_atual', 'status', 'data_quitacao', 'updated_at'])

            except Exception:
                pass

        emp.refresh_from_db()

        # Se tem parcelas em atraso → inadimplente
        tem_atrasada = emp.parcelas.filter(status='atrasado').exists()
        if tem_atrasada and emp.status == 'ativo' and random.random() < 0.6:
            emp.status = 'inadimplente'
            emp.save(update_fields=['status', 'updated_at'])

    def _criar_garantia(self, emp):
        """Adiciona uma garantia ao empréstimo."""
        from collaterals.infrastructure.models import Garantia

        # Peso por valor do empréstimo
        if emp.capital_inicial >= Decimal('2000'):
            tipo = random.choices(
                ['veiculo', 'imovel', 'eletronico', 'joia', 'outro'],
                weights=[50, 15, 20, 10, 5]
            )[0]
        else:
            tipo = random.choices(
                ['eletronico', 'joia', 'veiculo', 'outro'],
                weights=[40, 25, 25, 10]
            )[0]

        opcoes = DESCRICOES_GARANTIAS.get(tipo, DESCRICOES_GARANTIAS['outro'])
        opcao = random.choice(opcoes)

        # Valor da garantia: 80% a 200% do capital
        fator = Decimal(str(round(random.uniform(0.8, 2.0), 2)))
        valor = (emp.capital_inicial * fator).quantize(Decimal('0.01'))
        # Arredonda para valor "realista"
        valor = Decimal(str(round(float(valor) / 100) * 100))

        perc = Decimal(str(round(random.uniform(0.50, 0.85), 2)))

        Garantia.objects.create(
            emprestimo=emp,
            tipo=tipo,
            descricao=opcao['descricao'],
            valor_estimado=valor,
            percentual_recuperacao=perc,
            detalhes=opcao.get('detalhes', {}),
        )