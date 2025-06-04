from django.db import models
from django.contrib.auth.models import User

# Modelo para armazenar informações sobre o Edital
class Edital(models.Model):
    TIPO_CHOICES = [
        ("Alunos", "Alunos"),
        ("Bolsistas", "Bolsistas"),
    ]
    
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    numero_ano = models.CharField(max_length=50) # Ex: "01/2025"
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="editais_uploaded")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    last_modified_at = models.DateTimeField(auto_now=True)
    last_modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="editais_modified")

    class Meta:
        # Garante que a combinação de tipo e numero_ano seja única
        unique_together = [["tipo", "numero_ano"]]
        verbose_name = "Edital"
        verbose_name_plural = "Editais"

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.numero_ano}"

# Modelo para armazenar os dados importados do CSV, agora usando JSONField
class ImportedData(models.Model):
    edital = models.ForeignKey(Edital, on_delete=models.CASCADE, related_name="dados_importados", null=True, blank=True) 
    # Campo JSON para armazenar os dados da linha do CSV (chave=cabeçalho, valor=dado da linha)
    dados_linha = models.JSONField()

    def __str__(self):
        # Tenta obter um nome ou identificador dos dados JSON para melhor representação
        nome = self.dados_linha.get("Nome") or self.dados_linha.get("nome") or list(self.dados_linha.values())[0] or "N/A"
        return f"Dado para {self.edital} - {nome}"

