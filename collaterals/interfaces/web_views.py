from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages as flash
from collaterals.infrastructure.models import Garantia, DocumentoGarantia
from loans.infrastructure.models import Emprestimo


@login_required
def garantia_create(request, emprestimo_pk):
    emp = get_object_or_404(Emprestimo, pk=emprestimo_pk, deleted_at__isnull=True)

    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        descricao = request.POST.get('descricao', '').strip()
        valor_str = request.POST.get('valor_estimado', '0').replace(',', '.')
        perc_str = request.POST.get('percentual_recuperacao', '70').replace(',', '.')

        from decimal import Decimal
        try:
            valor = Decimal(valor_str)
            percentual = Decimal(perc_str) / 100
        except Exception:
            flash.error(request, 'Valores inválidos.')
            return redirect('web_loans:detail', pk=emp.id)

        # Captura detalhes específicos do tipo
        detalhes = {}
        if tipo == 'veiculo':
            detalhes = {
                'placa': request.POST.get('placa', ''),
                'modelo': request.POST.get('modelo', ''),
                'ano': request.POST.get('ano', ''),
                'chassi': request.POST.get('chassi', ''),
            }
        elif tipo == 'imovel':
            detalhes = {
                'matricula': request.POST.get('matricula', ''),
                'endereco': request.POST.get('endereco_imovel', ''),
            }

        garantia = Garantia.objects.create(
            emprestimo=emp,
            tipo=tipo,
            descricao=descricao,
            valor_estimado=valor,
            percentual_recuperacao=percentual,
            detalhes=detalhes,
        )

        # Upload de documentos
        for arquivo in request.FILES.getlist('documentos'):
            DocumentoGarantia.objects.create(
                garantia=garantia,
                arquivo=arquivo,
                descricao=arquivo.name,
            )

        flash.success(request, f'Garantia "{garantia.get_tipo_display()}" adicionada.')
        return redirect('web_loans:detail', pk=emp.id)

    return render(request, 'collaterals/form.html', {
        'emp': emp,
        'tipo_choices': Garantia.TIPO_CHOICES,
    })


@login_required
def garantia_delete(request, pk):
    garantia = get_object_or_404(Garantia, pk=pk, deleted_at__isnull=True)
    emp_id = garantia.emprestimo.id
    if request.method == 'POST':
        garantia.soft_delete()
        flash.success(request, 'Garantia removida.')
    return redirect('web_loans:detail', pk=emp_id)