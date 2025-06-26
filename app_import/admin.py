from django.contrib import admin
from .models import Edital, ImportedData

@admin.register(Edital)
class EditalAdmin(admin.ModelAdmin):
    """
    Configurações personalizadas para o modelo Edital no painel de administração do Django.
    """
    # Campos a serem exibidos na lista de editais
    list_display = (
        '__str__', 
        'uploaded_by', 
        'uploaded_at', 
        'last_modified_by', 
        'last_modified_at'
    )
    
    # Filtros que aparecerão na barra lateral direita
    list_filter = ('tipo', 'uploaded_at', 'last_modified_at', 'uploaded_by')
    
    # Campos pelos quais será possível buscar
    search_fields = ('numero_ano', 'uploaded_by__username')
    
    # Campos que serão somente leitura no formulário de edição
    # Estes campos são controlados automaticamente pela aplicação
    readonly_fields = (
        'uploaded_by', 
        'uploaded_at', 
        'last_modified_by', 
        'last_modified_at'
    )

    def get_queryset(self, request):
        # Otimiza a consulta ao banco de dados buscando os usuários relacionados
        return super().get_queryset(request).select_related('uploaded_by', 'last_modified_by')

@admin.register(ImportedData)
class ImportedDataAdmin(admin.ModelAdmin):
    """
    Configurações para o modelo ImportedData no painel de administração.
    Útil para inspecionar os dados brutos que foram importados.
    """
    list_display = ('id', 'edital', 'get_data_preview')
    list_filter = ('edital',)
    search_fields = ('edital__numero_ano',)
    
    # Torna os campos de dados somente leitura
    readonly_fields = ('edital', 'dados_linha')

    def get_data_preview(self, obj):
        """
        Retorna uma prévia dos dados JSON para facilitar a visualização na lista.
        """
        if isinstance(obj.dados_linha, dict):
            preview = str(list(obj.dados_linha.items())[:3])
            return (preview[:100] + '...') if len(preview) > 100 else preview
        return "Dados inválidos"
    get_data_preview.short_description = 'Prévia dos Dados da Linha'