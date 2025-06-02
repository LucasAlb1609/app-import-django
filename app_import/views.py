from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.views import generic
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import csv
import io

from .forms import CSVUploadForm
from .models import ImportedData

# View para cadastro de usuário
class SignUpView(generic.CreateView):
    form_class = UserCreationForm
    success_url = reverse_lazy("login") # Redireciona para a página de login após o cadastro
    template_name = "registration/signup.html"

# View para a página inicial após o login (com upload de CSV)
@login_required
def home(request):
    if request.method == "POST":
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES["csv_file"]
            
            # Verificar se é um arquivo CSV
            if not csv_file.name.endswith(".csv"):
                messages.error(request, "Este não é um arquivo CSV.")
                return redirect("home")

            try:
                # Ler o arquivo em memória
                data_set = csv_file.read().decode("UTF-8")
                io_string = io.StringIO(data_set)
                next(io_string) # Pular o cabeçalho
                
                # Processar cada linha do CSV
                # ATENÇÃO: Ajuste os índices [0], [1], [2] conforme as colunas do seu CSV!
                for column in csv.reader(io_string, delimiter=",", quotechar="|"):
                    # Verificar se a linha tem o número esperado de colunas (ex: 3)
                    if len(column) == 3:
                        _, created = ImportedData.objects.update_or_create(
                            # Adapte os campos do modelo aqui
                            coluna1=column[0],
                            coluna2=column[1],
                            coluna3=column[2]
                        )
                    else:
                        # Log ou mensagem de erro para linhas com formato inesperado
                        print(f"Linha ignorada por ter formato inesperado: {column}")
                        messages.warning(request, f"Algumas linhas podem não ter sido importadas devido ao formato. Linha exemplo: {column}")

                messages.success(request, "Arquivo CSV importado com sucesso!")
            except Exception as e:
                messages.error(request, f"Erro ao processar o arquivo CSV: {e}")
            
            return redirect("home")
        else:
            # Mensagens de erro do formulário, se houver
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return redirect("home") # Redireciona de volta se o formulário for inválido
    else:
        form = CSVUploadForm()
    
    return render(request, "home.html", {"form": form})

