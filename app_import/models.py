from django.db import models

# Modelo para armazenar os dados importados do CSV
class ImportedData(models.Model):
    # Adicione os campos que correspondem às colunas do seu CSV
    # Exemplo genérico:
    coluna1 = models.CharField(max_length=255, blank=True, null=True)
    coluna2 = models.CharField(max_length=255, blank=True, null=True)
    coluna3 = models.IntegerField(blank=True, null=True)
    # Adicione mais campos conforme necessário

    # Campo para registrar quando o dado foi importado
    imported_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Dado importado em {self.imported_at}"

