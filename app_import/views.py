from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import csv
import io
from django.db import transaction
import traceback # Import traceback for better error logging
from django.http import HttpResponse # Needed for CSV download
from collections import defaultdict
from django.core.paginator import Paginator # Importação para paginação
import re

from .forms import EditalCSVUploadForm
from .models import ImportedData, Edital

# View para cadastro de usuário
class SignUpView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy("login")
    template_name = "registration/signup.html"

# View para a página inicial após o login (upload)
@login_required
def home(request):
    edital_existente = None
    form = EditalCSVUploadForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        tipo = form.cleaned_data["tipo"]
        numero_ano = form.cleaned_data["numero_ano"]
        csv_file = request.FILES["csv_file"]
        confirmar_substituicao = form.cleaned_data.get("confirmar_substituicao", False)

        # Verificar se já existe um edital com o mesmo tipo e número/ano
        try:
            edital_existente = Edital.objects.get(tipo=tipo, numero_ano=numero_ano)
        except Edital.DoesNotExist:
            edital_existente = None

        # Se o edital existe e não foi confirmada a substituição, pedir confirmação
        if edital_existente and not confirmar_substituicao:
            uploader_original = edital_existente.uploaded_by.username if edital_existente.uploaded_by else "desconhecido"
            messages.warning(request, 
                             f"Já existe um edital '{edital_existente.get_tipo_display()} - {edital_existente.numero_ano}' "
                             f"carregado por '{uploader_original}'. "
                             f"Marque a caixa abaixo e clique em 'Upload CSV' novamente para substituí-lo.")
            form = EditalCSVUploadForm(initial=request.POST)
            return render(request, "home.html", {"form": form, "pedir_confirmacao": True, "edital_existente": edital_existente})

        # Se é um novo edital ou a substituição foi confirmada
        try:
            # Verificar se é um arquivo CSV
            if not csv_file.name.endswith(".csv"):
                messages.error(request, "Este não é um arquivo CSV.")
                return redirect("home")

            # Ler o arquivo CSV em memória, tentando detectar a codificação
            try:
                data_set = csv_file.read().decode("utf-8")
            except UnicodeDecodeError:
                try:
                    csv_file.seek(0)
                    data_set = csv_file.read().decode("latin-1")
                    messages.info(request, "Arquivo lido com codificação latin-1.")
                except Exception as decode_error:
                    messages.error(request, f"Não foi possível decodificar o arquivo. Verifique a codificação (UTF-8 preferível). Erro: {decode_error}")
                    return redirect("home")
            
            io_string = io.StringIO(data_set)
            reader = csv.DictReader(io_string, delimiter=",", quotechar='"') 
            
            if not reader.fieldnames:
                 messages.error(request, "Não foi possível ler o cabeçalho do CSV. Verifique o formato do arquivo.")
                 return redirect("home")

            with transaction.atomic():
                if edital_existente and confirmar_substituicao:
                    edital = edital_existente
                    edital.last_modified_by = request.user
                    edital.save()
                    ImportedData.objects.filter(edital=edital).delete()
                    acao = "substituído"
                else:
                    edital, created = Edital.objects.get_or_create(
                        tipo=tipo, 
                        numero_ano=numero_ano,
                        defaults={'uploaded_by': request.user}
                    )
                    if not created and not confirmar_substituicao:
                         messages.error(request, "Erro de concorrência: Edital foi criado enquanto processava. Tente novamente.")
                         return redirect("home")
                    elif not created and confirmar_substituicao:
                        edital.last_modified_by = request.user
                        edital.save()
                        ImportedData.objects.filter(edital=edital).delete()
                        acao = "substituído"
                    else: 
                        acao = "importado"

                dados_para_criar = []
                linhas_processadas = 0
                for row_dict in reader:
                    cleaned_row_dict = {k: v for k, v in row_dict.items() if k is not None and k.strip() != ''}
                    if not cleaned_row_dict:
                        continue 
                        
                    dados_para_criar.append(
                        ImportedData(
                            edital=edital,
                            dados_linha=cleaned_row_dict
                        )
                    )
                    linhas_processadas += 1
                
                if dados_para_criar:
                    ImportedData.objects.bulk_create(dados_para_criar)
                
                messages.success(
                    request, 
                    f"Arquivo CSV {acao} com sucesso para o edital "
                    f"'{edital.get_tipo_display()} - {edital.numero_ano}'! "
                    f"{linhas_processadas} linhas importadas."
                )

        except Exception as e:
            messages.error(request, f"Erro ao processar o arquivo CSV: {e}")
            traceback.print_exc()
        
        return redirect("home")

    else:
        if request.method == "POST" and not form.is_valid():
             for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
        form = EditalCSVUploadForm()

    return render(request, "home.html", {"form": form})

# Nova view para listar os editais
@login_required
def listar_editais(request):
    editais = Edital.objects.all().order_by("-uploaded_at")
    return render(request, "listar_editais.html", {"editais": editais})

# Nova view para download do CSV de um edital específico
@login_required
def download_edital_csv(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    
    # Obter os dados filtrados se houver filtros ativos
    inscritos_filtrados = filtrar_inscritos(request, edital)
    
    if not inscritos_filtrados.exists():
        messages.error(request, "Não há dados importados para este edital.")
        return redirect("listar_editais")

    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=\"edital_{edital.tipo}_{edital.numero_ano.replace('/', '-')}.csv\""},
    )
    response.write(u"\ufeff".encode("utf8"))
    
    writer = csv.writer(response, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)

    # Determinar o cabeçalho (todas as chaves únicas de todos os JSONs)
    headers = set()
    all_rows_data = [item.dados_linha for item in inscritos_filtrados]
    for row_data in all_rows_data:
        if isinstance(row_data, dict):
             headers.update(row_data.keys())
    
    sorted_headers = sorted(list(headers))
    writer.writerow(sorted_headers)

    for row_data in all_rows_data:
        if isinstance(row_data, dict):
            writer.writerow([row_data.get(header, '') for header in sorted_headers])

    return response

# Lista de palavras-chave para identificar campos de dados pessoais
CAMPOS_DADOS_PESSOAIS = [
    'nome', 'cpf', 'rg', 'identidade', 'documento', 'endereco', 'endereço', 
    'email', 'e-mail', 'telefone', 'celular', 'contato', 'nascimento', 
    'data de nascimento', 'filiação', 'mae', 'mãe', 'pai'
]

# Lista de palavras-chave para identificar campos de polo
CAMPOS_POLO = [
    'polo', 'pólo'
]

# Nova view para detalhe do edital com filtros dinâmicos
@login_required
def detalhe_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    
    # Obter todos os inscritos deste edital
    todos_inscritos = ImportedData.objects.filter(edital=edital)
    total_inscritos = todos_inscritos.count()
    
    if total_inscritos == 0:
        messages.warning(request, "Este edital não possui inscritos.")
        return redirect("listar_editais")
    
    # Identificar todos os campos disponíveis e seus valores únicos
    campos_filtro, campos_texto, campos_dropdown, campos_polo, cidades_disponiveis = identificar_campos_filtro(todos_inscritos)
    
    # Obter filtros ativos da query string
    filtros_ativos = {}
    filtros_texto = {}
    cidade_polo_selecionada = request.GET.get('cidade_polo', '')
    
    for param, valor in request.GET.items():
        if param.startswith('filtro_') and valor:
            campo = param[7:]  # Remove 'filtro_' do início
            filtros_ativos[campo] = valor
        elif param.startswith('texto_') and valor:
            campo = param[6:]  # Remove 'texto_' do início
            filtros_texto[campo] = valor
    
    # Filtrar inscritos com base nos filtros ativos
    inscritos = filtrar_inscritos(request, edital)
    
    # Determinar todas as colunas para exibição na tabela
    colunas = set()
    for inscrito in inscritos:
        if isinstance(inscrito.dados_linha, dict):
            colunas.update(inscrito.dados_linha.keys())
    colunas = sorted(list(colunas))

    paginator = Paginator(inscritos, 50)  # 50 itens por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'edital': edital,
        'inscritos': page_obj.object_list,
        'total_inscritos': total_inscritos,
        'campos_filtro': campos_filtro,
        'campos_texto': campos_texto,
        'campos_dropdown': campos_dropdown,
        'campos_polo': campos_polo,
        'cidades_disponiveis': cidades_disponiveis,
        'filtros_ativos': filtros_ativos,
        'filtros_texto': filtros_texto,
        'cidade_polo_selecionada': cidade_polo_selecionada,
        'colunas': colunas,
        'page_obj': page_obj,
    }
    
    return render(request, "detalhe_edital.html", context)


# Função auxiliar para identificar campos e valores únicos para filtros
def identificar_campos_filtro(inscritos):
    """
    Identifica todos os campos disponíveis nos dados dos inscritos
    e seus valores únicos para criar filtros dinâmicos.
    Separa campos de texto (dados pessoais) e campos dropdown.
    Identifica campos de polo e extrai cidades disponíveis.
    """
    campos_valores = defaultdict(set)
    campos_texto = set()
    campos_dropdown = set()
    campos_polo = set()
    cidades_por_polo = {}
    todas_cidades = set()
    
    # Primeiro passo: coletar todos os campos e valores
    for inscrito in inscritos:
        if not isinstance(inscrito.dados_linha, dict):
            continue
            
        for campo, valor in inscrito.dados_linha.items():
            campo_lower = campo.lower()
            
            # Ignorar campos vazios ou muito longos
            if not valor or not isinstance(valor, str) or len(valor) > 100:
                continue
                
            # Verificar se é um campo de dados pessoais
            if any(keyword in campo_lower for keyword in CAMPOS_DADOS_PESSOAIS):
                campos_texto.add(campo)
            else:
                # Verificar se é um campo de polo
                if any(keyword in campo_lower for keyword in CAMPOS_POLO):
                    campos_polo.add(campo)
                    
                    # Extrair cidade do valor do polo
                    cidade = extrair_cidade_do_polo(valor)
                    if cidade:
                        todas_cidades.add(cidade.strip())
                
                campos_dropdown.add(campo)
                campos_valores[campo].add(valor)
    
    # Ordenar as cidades alfabeticamente
    cidades_disponiveis = sorted(list(todas_cidades))
    
    # Converter sets para listas ordenadas
    return {campo: sorted(list(valores)) for campo, valores in campos_valores.items()}, campos_texto, campos_dropdown, campos_polo, cidades_disponiveis


def extrair_cidade_do_polo(valor_polo):
    """
    Extrai o nome da cidade de um valor de polo.
    Exemplos:
    - "LP - Recife" -> "Recife"
    - "LF - GARANHUNS" -> "GARANHUNS"
    - "BSI - Caruaru" -> "Caruaru"
    """
    # Padrão comum: Sigla - Cidade
    padrao = r'[A-Z]+\s*-\s*(.+)'
    match = re.search(padrao, valor_polo)
    
    if match:
        return match.group(1).strip()
    
    # Se não encontrou no padrão comum, retorna o valor original
    # (pode ser apenas o nome da cidade)
    return valor_polo


# Função auxiliar para filtrar inscritos com base nos parâmetros da query string
def filtrar_inscritos(request, edital):
    """
    Filtra os inscritos de um edital com base nos filtros da query string.
    Suporta:
    - Filtros de texto (busca parcial)
    - Filtros dropdown (valor exato)
    - Filtro unificado de cidade do polo (busca em todos os campos de polo)
    """
    inscritos = ImportedData.objects.filter(edital=edital)
    
    # Se não há filtros ativos, retorna todos os inscritos
    if not any(param.startswith(('filtro_', 'texto_', 'cidade_polo')) for param in request.GET):
        return inscritos
    
    # Lista para armazenar os IDs dos inscritos que atendem a todos os filtros
    ids_filtrados = []
    
    # Verificar se há filtro de cidade do polo
    cidade_polo = request.GET.get('cidade_polo', '')
    
    # Processa cada inscrito para verificar se atende a todos os filtros
    for inscrito in inscritos:
        if not isinstance(inscrito.dados_linha, dict):
            continue
            
        atende_todos_filtros = True
        
        # Verificar filtros dropdown (valor exato)
        for param, valor in request.GET.items():
            if param.startswith('filtro_') and valor:
                campo = param[7:]  # Remove 'filtro_' do início
                
                # Verificar se o inscrito tem o campo e se o valor corresponde ao filtro
                if campo not in inscrito.dados_linha or inscrito.dados_linha[campo] != valor:
                    atende_todos_filtros = False
                    break
        
        # Se já falhou em algum filtro dropdown, não precisa verificar os outros
        if not atende_todos_filtros:
            continue
        
        # Verificar filtros de texto (busca parcial)
        for param, valor in request.GET.items():
            if param.startswith('texto_') and valor:
                campo = param[6:]  # Remove 'texto_' do início
                
                # Verificar se o inscrito tem o campo e se o valor contém o texto buscado
                if (campo not in inscrito.dados_linha or 
                    valor.lower() not in inscrito.dados_linha[campo].lower()):
                    atende_todos_filtros = False
                    break
        
        # Se já falhou em algum filtro de texto, não precisa verificar o filtro de cidade
        if not atende_todos_filtros:
            continue
        
        # Verificar filtro unificado de cidade do polo
        if cidade_polo:
            atende_filtro_cidade = False
            
            # Verificar todos os campos do inscrito que podem ser campos de polo
            for campo, valor in inscrito.dados_linha.items():
                campo_lower = campo.lower()
                
                # Se é um campo de polo
                if any(keyword in campo_lower for keyword in CAMPOS_POLO) and valor:
                    # Extrair cidade do valor do polo
                    cidade_extraida = extrair_cidade_do_polo(valor)
                    
                    # Comparar com a cidade selecionada (ignorando maiúsculas/minúsculas)
                    if cidade_extraida and cidade_extraida.lower() == cidade_polo.lower():
                        atende_filtro_cidade = True
                        break
            
            if not atende_filtro_cidade:
                atende_todos_filtros = False
        
        if atende_todos_filtros:
            ids_filtrados.append(inscrito.id)
    
    # Retorna apenas os inscritos que atendem a todos os filtros
    return inscritos.filter(id__in=ids_filtrados)
