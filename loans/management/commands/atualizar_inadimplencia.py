"""
Comando de manutenção diária — deve rodar via cron todo dia às 00:01.

Crontab:
  1 0 * * * /caminho/venv/bin/python /caminho/manage.py atualizar_inadimplencia >> /var/log/agi_inadimplencia.log 2>&1

O que faz:
  1. Marca parcelas vencidas como "atrasado"
  2. Marca empréstimos comuns vencidos como "inadimplente"
  3. Reclassifica todos os clientes afetados
  4. Exibe relatório do que foi alterado
"""
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q


class Command(BaseCommand):
    help = 'Atualiza inadimplência: marca parcelas atrasadas e reclassifica clientes.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula sem salvar nada no banco.',
        )
        parser.add_argument(
            '--data',
            type=str,
            default=None,
            help='Data de referência no formato YYYY-MM-DD (padrão: hoje).',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        data_ref_str = options.get('data')

        if data_ref_str:
            from datetime import datetime
            data_ref = datetime.strptime(data_ref_str, '%Y-%m-%d').date()
        else:
            data_ref = date.today()

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f'\n=== Agi Empréstimos — Atualização de Inadimplência ==='
                f'\n    Data de referência: {data_ref.strftime("%d/%m/%Y")}'
                f'\n    Modo: {"DRY RUN (sem alterações)" if dry_run else "PRODUÇÃO"}\n'
            )
        )

        with transaction.atomic():
            parcelas_marcadas = self._marcar_parcelas_atrasadas(data_ref, dry_run)
            emprestimos_marcados = self._marcar_emprestimos_inadimplentes(data_ref, dry_run)
            clientes_atualizados = self._reclassificar_clientes(dry_run)

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(self.style.SUCCESS(
            f'✅  Parcelas marcadas como atrasadas: {parcelas_marcadas}\n'
            f'✅  Empréstimos marcados como inadimplentes: {emprestimos_marcados}\n'
            f'✅  Clientes reclassificados: {clientes_atualizados}\n'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('⚠  DRY RUN — nenhuma alteração foi salva.\n'))

    def _marcar_parcelas_atrasadas(self, data_ref: date, dry_run: bool) -> int:
        from loans.infrastructure.models import ParcelaEmprestimo

        qs = ParcelaEmprestimo.objects.filter(
            status__in=['pendente', 'parcialmente_pago'],
            data_vencimento__lt=data_ref,
            emprestimo__deleted_at__isnull=True,
            emprestimo__status__in=['ativo', 'inadimplente'],
        )
        count = qs.count()

        if count and not dry_run:
            qs.update(status='atrasado')

        if count:
            self.stdout.write(f'  → {count} parcela(s) vencida(s) marcada(s) como atrasada')
        else:
            self.stdout.write('  → Nenhuma parcela vencida encontrada')

        return count

    def _marcar_emprestimos_inadimplentes(self, data_ref: date, dry_run: bool) -> int:
        from loans.infrastructure.models import Emprestimo

        # Empréstimos COMUNS com data de vencimento ultrapassada
        qs_comuns = Emprestimo.objects.filter(
            tipo='comum',
            status='ativo',
            data_vencimento__lt=data_ref,
            deleted_at__isnull=True,
        )

        # Empréstimos PARCELADOS com pelo menos 1 parcela atrasada
        qs_parcelados = Emprestimo.objects.filter(
            tipo='parcelado',
            status='ativo',
            deleted_at__isnull=True,
            parcelas__status='atrasado',
        ).distinct()

        total = qs_comuns.count() + qs_parcelados.count()

        if not dry_run:
            ids_comuns = list(qs_comuns.values_list('id', flat=True))
            ids_parcelados = list(qs_parcelados.values_list('id', flat=True))

            if ids_comuns:
                Emprestimo.objects.filter(id__in=ids_comuns).update(status='inadimplente')
                self.stdout.write(
                    f'  → {len(ids_comuns)} empréstimo(s) comum(ns) → inadimplente'
                )
            if ids_parcelados:
                Emprestimo.objects.filter(id__in=ids_parcelados).update(status='inadimplente')
                self.stdout.write(
                    f'  → {len(ids_parcelados)} empréstimo(s) parcelado(s) → inadimplente'
                )
        else:
            self.stdout.write(
                f'  → {qs_comuns.count()} comum(ns) + '
                f'{qs_parcelados.count()} parcelado(s) seriam marcados inadimplentes'
            )

        return total

    def _reclassificar_clientes(self, dry_run: bool) -> int:
        from customers.infrastructure.models import Cliente
        from customers.application.services import ClienteService
        from django.db.models import Count

        # Pega apenas clientes com empréstimos ativos (os afetados)
        clientes = Cliente.objects.filter(
            deleted_at__isnull=True,
            emprestimos__deleted_at__isnull=True,
            emprestimos__status__in=['ativo', 'inadimplente'],
        ).distinct()

        count = 0
        for cliente in clientes:
            try:
                if not dry_run:
                    ClienteService.atualizar_classificacao(str(cliente.id))
                count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ Erro ao reclassificar {cliente.nome}: {e}')
                )

        self.stdout.write(f'  → {count} cliente(s) reclassificado(s)')
        return count