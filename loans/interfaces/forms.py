from datetime import date
from decimal import Decimal
from django import forms

_I = "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
_T = "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"


class EmprestimoComumForm(forms.Form):
    capital = forms.DecimalField(
        max_digits=12, decimal_places=2,
        label='Capital (R$)',
        widget=forms.NumberInput(attrs={'class': _I, 'placeholder': '1000.00', 'step': '0.01'}),
    )
    taxa_mensal = forms.DecimalField(
        max_digits=6, decimal_places=2,
        label='Taxa de Juros Mensal (%)',
        help_text='Ex: 5.00 para 5% ao mês',
        widget=forms.NumberInput(attrs={'class': _I, 'placeholder': '5.00', 'step': '0.01'}),
    )
    data_inicio = forms.DateField(
        label='Data de Início',
        initial=date.today,
        widget=forms.DateInput(attrs={'class': _I, 'type': 'date'}),
    )
    observacoes = forms.CharField(
        required=False, label='Observações',
        widget=forms.Textarea(attrs={'class': _T, 'rows': 2}),
    )

    def clean_taxa_mensal(self):
        taxa = self.cleaned_data['taxa_mensal']
        if taxa <= 0 or taxa >= 100:
            raise forms.ValidationError('Taxa deve estar entre 0% e 100%.')
        return taxa / Decimal('100')


class EmprestimoParceladoForm(forms.Form):
    capital = forms.DecimalField(
        max_digits=12, decimal_places=2,
        label='Capital (R$)',
        widget=forms.NumberInput(attrs={
            'class': _I, 'placeholder': '1000.00', 'step': '0.01',
            'hx-post': '', 'hx-trigger': 'change delay:300ms',
            'hx-target': '#simulacao', 'hx-include': 'closest form',
            'hx-vals': '{"simular": "1"}',
        }),
    )
    taxa_mensal = forms.DecimalField(
        max_digits=6, decimal_places=2,
        label='Taxa de Juros Mensal (%)',
        help_text='Ex: 5.00 para 5% ao mês',
        widget=forms.NumberInput(attrs={
            'class': _I, 'placeholder': '5.00', 'step': '0.01',
            'hx-post': '', 'hx-trigger': 'change delay:300ms',
            'hx-target': '#simulacao', 'hx-include': 'closest form',
            'hx-vals': '{"simular": "1"}',
        }),
    )
    n_parcelas = forms.IntegerField(
        min_value=1, max_value=360,
        label='Número de Parcelas',
        widget=forms.NumberInput(attrs={
            'class': _I,
            'hx-post': '', 'hx-trigger': 'change delay:300ms',
            'hx-target': '#simulacao', 'hx-include': 'closest form',
            'hx-vals': '{"simular": "1"}',
        }),
    )
    subtipo = forms.ChoiceField(
        choices=[
            ('fixo', 'Parcela Fixa (Juros sobre Capital Inicial)'),
            ('sac', 'SAC — Parcela Decrescente (Amortização Constante)'),
        ],
        label='Modalidade',
        widget=forms.Select(attrs={'class': _I}),
    )
    data_inicio = forms.DateField(
        label='Data de Início',
        initial=date.today,
        widget=forms.DateInput(attrs={'class': _I, 'type': 'date'}),
    )
    data_primeira_parcela = forms.DateField(
        label='Data da 1ª Parcela',
        widget=forms.DateInput(attrs={'class': _I, 'type': 'date'}),
    )
    observacoes = forms.CharField(
        required=False, label='Observações',
        widget=forms.Textarea(attrs={'class': _T, 'rows': 2}),
    )

    def clean_taxa_mensal(self):
        taxa = self.cleaned_data['taxa_mensal']
        if taxa <= 0 or taxa >= 100:
            raise forms.ValidationError('Taxa deve estar entre 0% e 100%.')
        return taxa / Decimal('100')


class PagamentoComumForm(forms.Form):
    valor = forms.DecimalField(
        max_digits=12, decimal_places=2, label='Valor do Pagamento (R$)',
        widget=forms.NumberInput(attrs={'class': _I, 'step': '0.01'}),
    )
    data_pagamento = forms.DateField(
        label='Data do Pagamento',
        initial=date.today,
        widget=forms.DateInput(attrs={'class': _I, 'type': 'date'}),
    )
    observacoes = forms.CharField(
        required=False, label='Observações',
        widget=forms.Textarea(attrs={'class': _T, 'rows': 2}),
    )