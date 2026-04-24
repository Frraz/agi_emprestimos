from django import forms
from customers.infrastructure.models import Cliente
from core.utils import validar_cpf, formatar_cpf

_I = "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
_S = "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
_T = "w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            'nome', 'cpf', 'rg', 'cnh', 'data_nascimento', 'foto',
            'profissao', 'estado_civil', 'tipo_residencia',
            'telefone_principal', 'telefone_secundario', 'email',
            'instagram', 'facebook',
            'cep', 'logradouro', 'numero', 'complemento',
            'bairro', 'cidade', 'estado',
            'origem', 'perfil_psicologico', 'observacoes',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'class': _I, 'placeholder': 'Nome completo'}),
            'cpf': forms.TextInput(attrs={'class': _I, 'placeholder': '000.000.000-00'}),
            'rg': forms.TextInput(attrs={'class': _I, 'placeholder': 'Ex: 12.345.678-9'}),
            'cnh': forms.TextInput(attrs={'class': _I, 'placeholder': 'Número da CNH'}),
            'data_nascimento': forms.DateInput(attrs={'class': _I, 'type': 'date'}),
            'foto': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 '
                         'file:rounded-lg file:border-0 file:text-sm file:font-medium '
                         'file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100'
            }),
            'profissao': forms.TextInput(attrs={'class': _I, 'placeholder': 'Ex: Comerciante'}),
            'estado_civil': forms.Select(attrs={'class': _S}),
            'tipo_residencia': forms.Select(attrs={'class': _S}),
            'telefone_principal': forms.TextInput(attrs={'class': _I, 'placeholder': '(00) 00000-0000'}),
            'telefone_secundario': forms.TextInput(attrs={'class': _I, 'placeholder': '(00) 00000-0000'}),
            'email': forms.EmailInput(attrs={'class': _I, 'placeholder': 'email@exemplo.com'}),
            'instagram': forms.TextInput(attrs={'class': _I, 'placeholder': '@usuario'}),
            'facebook': forms.TextInput(attrs={'class': _I, 'placeholder': 'facebook.com/usuario'}),
            'cep': forms.TextInput(attrs={
                'class': _I, 'placeholder': '00000-000',
                'hx-get': '/api/cep/', 'hx-trigger': 'change delay:300ms',
                'hx-target': '#campos-endereco', 'hx-include': '[name="cep"]',
            }),
            'logradouro': forms.TextInput(attrs={'class': _I}),
            'numero': forms.TextInput(attrs={'class': _I}),
            'complemento': forms.TextInput(attrs={'class': _I}),
            'bairro': forms.TextInput(attrs={'class': _I}),
            'cidade': forms.TextInput(attrs={'class': _I}),
            'estado': forms.TextInput(attrs={'class': _I, 'maxlength': 2, 'placeholder': 'UF'}),
            'origem': forms.Select(attrs={'class': _S}),
            'perfil_psicologico': forms.Textarea(attrs={'class': _T, 'rows': 3}),
            'observacoes': forms.Textarea(attrs={'class': _T, 'rows': 3}),
        }

    def clean_cpf(self):
        cpf = formatar_cpf(self.cleaned_data.get('cpf', ''))
        if not validar_cpf(cpf):
            raise forms.ValidationError('CPF inválido.')
        qs = Cliente.objects.filter(cpf=cpf, deleted_at__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('CPF já cadastrado.')
        return cpf