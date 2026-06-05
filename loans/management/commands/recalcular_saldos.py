"""
Recalcula o saldo dos empréstimos COMUM sob a regra de juros simples
(SEM capitalização), curando saldos inflados por "juros sobre juros"
gravados antes da correção da lógica financeira.

Para cada empréstimo comum, reconstrói `capital_atual` e `juros_acumulados`
reproduzindo, em ordem cronológica:
  1. o lançamento do 1º ciclo de juros (na criação);
  2. o lançamento de um ciclo de juros a cada vencimento mensal decorrido;
  3. cada pagamento já registrado (quitando juros acumulados → capital).

O capital nunca cresce por juros — não há juros sobre juros. Pagamentos não
são apagados nem alterados.

Uso:
  python manage.py recalcular_saldos --dry-run
  python manage.py recalcular_saldos
  python manage.py recalcular_saldos --emprestimo <uuid>
  python manage.py recalcular_saldos --data 2026-06-04
"""
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Recalcula saldos de empréstimos comuns sem capitalização (juros simples).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Simula sem salvar nada no banco.')
        parser.add_argument('--data', type=str, default=None,
                            help='Data de referência YYYY-MM-DD (padrão: hoje).')
        parser.add_argument('--emprestimo', type=str, default=None,
                            help='Recalcula apenas o empréstimo com este UUID.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if options.get('data'):
            from datetime import datetime
            data_ref = datetime.strptime(options['data'], '%Y-%m-%d').date()
        else:
            data_ref = date.today()

        from loans.infrastructure.models import Emprestimo

        qs = Emprestimo.objects.filter(tipo='comum', deleted_at__isnull=True)
        if options.get('emprestimo'):
            qs = qs.filter(id=options['emprestimo'])

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n=== Recalculando saldos (comum) — ref {data_ref:%d/%m/%Y} '
            f'— {"DRY RUN" if dry_run else "PRODUÇÃO"} ===\n'
        ))

        alterados = 0
        with transaction.atomic():
            for emp in qs.iterator():
                novo_capital, novo_juros = self._reconstruir(emp, data_ref)
                mudou = (
                    novo_capital != emp.capital_atual
                    or novo_juros != emp.juros_acumulados
                )
                if mudou:
                    self.stdout.write(
                        f'  {emp.cliente.nome[:28]:28}  '
                        f'capital {emp.capital_atual} → {novo_capital}  |  '
                        f'juros {emp.juros_acumulados} → {novo_juros}'
                    )
                    if not dry_run:
                        emp.capital_atual = novo_capital
                        emp.juros_acumulados = novo_juros
                        if novo_capital <= Decimal('0') and emp.status in ('ativo', 'inadimplente'):
                            emp.status = 'quitado'
                        emp.save(update_fields=[
                            'capital_atual', 'juros_acumulados', 'status', 'updated_at'
                        ])
                    alterados += 1

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(self.style.SUCCESS(
            f'✅  {alterados} empréstimo(s) com saldo recalculado.\n'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('⚠  DRY RUN — nada foi salvo.\n'))

    @staticmethod
    def _reconstruir(emp, data_ref: date):
        """Delega à função compartilhada em loans.application.services."""
        from loans.application.services import reconstruir_saldo_comum
        return reconstruir_saldo_comum(emp, data_ref)
