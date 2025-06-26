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
import unicodedata # Para normalização de acentos

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

        try:
            edital_existente = Edital.objects.get(tipo=tipo, numero_ano=numero_ano)
        except Edital.DoesNotExist:
            edital_existente = None

        if edital_existente and not confirmar_substituicao:
            uploader_original = edital_existente.uploaded_by.username if edital_existente.uploaded_by else "desconhecido"
            messages.warning(request, 
                             f"Já existe um edital '{edital_existente.get_tipo_display()} - {edital_existente.numero_ano}' "
                             f"carregado por '{uploader_original}'. "
                             f"Marque a caixa abaixo e clique em 'Upload CSV' novamente para substituí-lo.")
            form = EditalCSVUploadForm(initial=request.POST)
            return render(request, "home.html", {"form": form, "pedir_confirmacao": True, "edital_existente": edital_existente})

        try:
            if not csv_file.name.endswith(".csv"):
                messages.error(request, "Este não é um arquivo CSV.")
                return redirect("home")

            try:
                data_set = csv_file.read().decode("utf-8")
            except UnicodeDecodeError:
                try:
                    csv_file.seek(0)
                    data_set = csv_file.read().decode("latin-1")
                    messages.info(request, "Arquivo lido com codificação latin-1.")
                except Exception as decode_error:
                    messages.error(request, f"Não foi possível decodificar o arquivo. Verifique a codificação. Erro: {decode_error}")
                    return redirect("home")
            
            io_string = io.StringIO(data_set)
            
            delimiter_to_use = None
            try:
                dialect = csv.Sniffer().sniff(io_string.readline(), delimiters=';,')
                delimiter_to_use = dialect.delimiter
            except csv.Error:
                messages.warning(request, "Não foi possível detectar o delimitador. O sistema tentará usar ';' e ',' como padrão.")
            
            io_string.seek(0)

            delimiters_to_try = [delimiter_to_use] if delimiter_to_use else [';', ',']
            
            reader = None
            for delim in delimiters_to_try:
                try:
                    reader = csv.DictReader(io_string, delimiter=delim, quotechar='"')
                    if reader.fieldnames and len(reader.fieldnames) > 1:
                        if not delimiter_to_use:
                            messages.info(request, f"Arquivo lido com sucesso usando o delimitador '{delim}'.")
                        else:
                            messages.info(request, f"Delimitador '{delim}' detectado e usado com sucesso.")
                        break 
                    else:
                        io_string.seek(0)
                        reader = None
                except Exception:
                    io_string.seek(0)
                    reader = None

            if not reader or not reader.fieldnames:
                 messages.error(request, "Não foi possível ler o cabeçalho do CSV. Verifique o formato do arquivo e se o delimitador é ',' ou ';'.")
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
                    if not created:
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

@login_required
def listar_editais(request):
    editais = Edital.objects.all().order_by("-uploaded_at")
    return render(request, "listar_editais.html", {"editais": editais})

@login_required
def download_edital_csv(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    
    inscritos_filtrados = filtrar_inscritos(request, edital)
    
    if not inscritos_filtrados.exists():
        messages.error(request, "Não há dados para exportar com os filtros atuais.")
        return redirect('detalhe_edital', edital_id=edital_id)

    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=\"edital_{edital.tipo}_{edital.numero_ano.replace('/', '-')}_filtrado.csv\""},
    )
    response.write(u"\ufeff".encode("utf8"))
    
    writer = csv.writer(response, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)

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

CAMPOS_DADOS_PESSOAIS = [
    'nome', 'cpf', 'rg', 'identidade', 'documento', 'endereco', 'endereço', 
    'email', 'e-mail', 'telefone', 'celular', 'contato', 'nascimento', 
    'data de nascimento', 'filiação', 'mae', 'mãe', 'pai'
]

CAMPOS_DOCUMENTO = ['cpf', 'rg', 'identidade', 'documento']

CAMPOS_POLO = ['polo', 'pólo']

def remover_acentos(texto):
    if not texto or not isinstance(texto, str):
        return texto
    return ''.join(c for c in unicodedata.normalize('NFD', texto) 
                  if unicodedata.category(c) != 'Mn')

@login_required
def detalhe_edital(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    
    todos_inscritos = ImportedData.objects.filter(edital=edital)
    total_inscritos = todos_inscritos.count()
    
    if total_inscritos == 0:
        messages.warning(request, "Este edital não possui inscritos.")
        return redirect("listar_editais")
    
    campos_filtro, campos_texto, campos_dropdown, campos_polo, cidades_disponiveis, valores_polo_origem = identificar_campos_filtro(todos_inscritos)
    
    filtros_ativos = {}
    filtros_texto = {}
    cidade_polo_selecionada = request.GET.get('cidade_polo', '')
    polo_origem_selecionado = request.GET.get('polo_origem', '')
    
    for param, valor in request.GET.items():
        if param.startswith('filtro_') and valor:
            campo = param[7:]
            filtros_ativos[campo] = valor
        elif param.startswith('texto_') and valor:
            campo = param[6:]
            filtros_texto[campo] = valor
    
    inscritos = filtrar_inscritos(request, edital)
    
    colunas = set()
    dados_para_exibir = inscritos if inscritos.exists() else todos_inscritos
    for inscrito in dados_para_exibir[:100]:
        if isinstance(inscrito.dados_linha, dict):
            colunas.update(inscrito.dados_linha.keys())
    colunas = sorted(list(colunas))

    paginator = Paginator(inscritos, 50)
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
        'valores_polo_origem': valores_polo_origem,
        'polo_origem_selecionado': polo_origem_selecionado,
        'colunas': colunas,
        'page_obj': page_obj,
    }
    
    return render(request, "detalhe_edital.html", context)


def identificar_campos_filtro(inscritos):
    campos_valores = defaultdict(set)
    campos_texto = set()
    campos_dropdown = set()
    campos_polo = set()
    todas_cidades = set()
    valores_polo_origem = set()

    for inscrito in inscritos:
        if not isinstance(inscrito.dados_linha, dict):
            continue
            
        for campo, valor in inscrito.dados_linha.items():
            if not valor or not isinstance(valor, str) or len(valor) > 100:
                continue
            
            if campo.strip().lower() == 'polo de origem':
                valores_polo_origem.add(valor)
                continue 

            campo_lower = campo.lower()
                
            if any(keyword in campo_lower for keyword in CAMPOS_DADOS_PESSOAIS):
                campos_texto.add(campo)
            else:
                if any(keyword in campo_lower for keyword in CAMPOS_POLO):
                    campos_polo.add(campo)
                    cidade = extrair_cidade_do_polo(valor)
                    if cidade:
                        todas_cidades.add(cidade.strip())
                
                campos_dropdown.add(campo)
                campos_valores[campo].add(valor)
    
    cidades_disponiveis = sorted(list(todas_cidades))
    
    return {campo: sorted(list(valores)) for campo, valores in campos_valores.items()}, \
           sorted(list(campos_texto)), \
           sorted(list(campos_dropdown)), \
           sorted(list(campos_polo)), \
           cidades_disponiveis, \
           sorted(list(valores_polo_origem))


def extrair_cidade_do_polo(valor_polo):
    padrao = r'[A-Z]+\s*-\s*(.+)'
    match = re.search(padrao, valor_polo)
    if match:
        return match.group(1).strip()
    return valor_polo


def filtrar_inscritos(request, edital):
    inscritos = ImportedData.objects.filter(edital=edital)
    
    if not any(param.startswith(('filtro_', 'texto_', 'cidade_polo', 'polo_origem')) for param, v in request.GET.items() if v):
        return inscritos
    
    ids_filtrados = []
    
    cidade_polo = request.GET.get('cidade_polo', '')
    polo_origem_selecionado = request.GET.get('polo_origem', '')
    
    if cidade_polo:
        cidade_polo_normalizada = remover_acentos(cidade_polo.lower())
    
    for inscrito in inscritos.iterator():
        if not isinstance(inscrito.dados_linha, dict):
            continue
            
        atende_todos_filtros = True
        
        # ===== CORREÇÃO APLICADA AQUI =====
        # Lógica para aplicar o filtro de Polo de Origem de forma flexível
        if polo_origem_selecionado:
            polo_origem_encontrado_no_inscrito = False
            for campo, valor in inscrito.dados_linha.items():
                if campo.strip().lower() == 'polo de origem' and valor == polo_origem_selecionado:
                    polo_origem_encontrado_no_inscrito = True
                    break
            if not polo_origem_encontrado_no_inscrito:
                atende_todos_filtros = False
        
        if not atende_todos_filtros:
            continue
        
        # Filtros dropdown
        for param, valor in request.GET.items():
            if param.startswith('filtro_') and valor:
                campo = param[7:]
                if campo not in inscrito.dados_linha or str(inscrito.dados_linha.get(campo)) != valor:
                    atende_todos_filtros = False
                    break
        if not atende_todos_filtros: continue
        
        # Filtros de texto
        for param, valor in request.GET.items():
            if param.startswith('texto_') and valor:
                campo = param[6:]
                valor_campo_db = inscrito.dados_linha.get(campo)
                if not valor_campo_db:
                    atende_todos_filtros = False
                    break
                
                valor_campo_normalizado = remover_acentos(str(valor_campo_db).lower())
                valor_busca_normalizado = remover_acentos(str(valor).lower())
                
                if any(keyword in campo.lower() for keyword in CAMPOS_DOCUMENTO):
                    valor_campo_normalizado = re.sub(r'[^a-zA-Z0-9]', '', valor_campo_normalizado)
                    valor_busca_normalizado = re.sub(r'[^a-zA-Z0-9]', '', valor_busca_normalizado)
                
                if valor_busca_normalizado not in valor_campo_normalizado:
                    atende_todos_filtros = False
                    break
        if not atende_todos_filtros: continue
        
        # Filtro de cidade do polo
        if cidade_polo:
            atende_filtro_cidade = False
            for campo, valor in inscrito.dados_linha.items():
                if any(keyword in campo.lower() for keyword in CAMPOS_POLO) and valor and campo.strip().lower() != 'polo de origem':
                    cidade_extraida = extrair_cidade_do_polo(str(valor))
                    cidade_extraida_normalizada = remover_acentos(cidade_extraida.lower()) if cidade_extraida else ''
                    if cidade_extraida_normalizada and cidade_polo_normalizada in cidade_extraida_normalizada:
                        atende_filtro_cidade = True
                        break
            if not atende_filtro_cidade:
                atende_todos_filtros = False
        
        if atende_todos_filtros:
            ids_filtrados.append(inscrito.id)
    
    return inscritos.filter(id__in=ids_filtrados)