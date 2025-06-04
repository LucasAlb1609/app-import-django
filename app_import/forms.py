from django import forms
from .models import Edital # Importar o modelo Edital

class EditalCSVUploadForm(forms.Form):
    tipo = forms.ChoiceField(choices=Edital.TIPO_CHOICES, label="Tipo de Edital")
    numero_ano = forms.CharField(max_length=50, label="Número/Ano do Edital (Ex: 01/2025)")
    csv_file = forms.FileField(label="Selecione o arquivo CSV")
    # Campo de confirmação como BooleanField normal (renderiza como checkbox)
    confirmar_substituicao = forms.BooleanField(required=False, label="Confirmar Substituição")
