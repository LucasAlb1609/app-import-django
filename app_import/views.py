# INÍCIO COMPLETO DO ARQUIVO views.py (SEM BARRAS INVERTIDAS INCORRETAS)
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

from .forms import EditalCSVUploadForm
from .models import ImportedData, Edital

# View para cadastro de usuário
class SignUpView(generic.CreateView ):
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
            # --- F-string CORRIGIDA (sem barras extras) --- 
            messages.warning(request, 
                             f"Já existe um edital '{edital_existente.get_tipo_display()} - {edital_existente.numero_ano}' "
                             f"carregado por '{uploader_original}'. "
                             f"Marque a caixa abaixo e clique em 'Upload CSV' novamente para substituí-lo.")
            # --- FIM DA CORREÇÃO --- 
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
            # Usar DictReader (sem barras extras no quotechar)
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
                    # Usar get_or_create (sem barras extras na chave 'uploaded_by')
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
                
                # --- F-string CORRIGIDA (sem barras extras) --- 
                messages.success(
                    request, 
                    f"Arquivo CSV {acao} com sucesso para o edital "
                    f"'{edital.get_tipo_display()} - {edital.numero_ano}'! "
                    f"{linhas_processadas} linhas importadas."
                )
                # --- FIM DA CORREÇÃO --- 

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

# --- FUNÇÕES DE LISTAGEM E DOWNLOAD --- 

# Nova view para listar os editais
@login_required
def listar_editais(request):
    editais = Edital.objects.all().order_by("-uploaded_at")
    return render(request, "listar_editais.html", {"editais": editais})

# Nova view para download do CSV de um edital específico
@login_required
def download_edital_csv(request, edital_id):
    edital = get_object_or_404(Edital, pk=edital_id)
    dados_importados = ImportedData.objects.filter(edital=edital)

    if not dados_importados.exists():
        messages.error(request, "Não há dados importados para este edital.")
        return redirect("listar_editais")

    response = HttpResponse(
        content_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=\"edital_{edital.tipo}_{edital.numero_ano.replace('/', '-')}.csv\""},
    )
    response.write(u"\ufeff".encode("utf8"))
    
    # Usar quotechar sem barras extras
    writer = csv.writer(response, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL)

    headers = set()
    all_rows_data = [item.dados_linha for item in dados_importados]
    for row_data in all_rows_data:
        if isinstance(row_data, dict):
             headers.update(row_data.keys())
    
    sorted_headers = sorted(list(headers))
    writer.writerow(sorted_headers)

    for row_data in all_rows_data:
        if isinstance(row_data, dict):
            # Usar get com string vazia sem barras extras
            writer.writerow([row_data.get(header, '') for header in sorted_headers])

    return response
# FIM COMPLETO DO ARQUIVO views.py
