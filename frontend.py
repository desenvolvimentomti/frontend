import os
import requests
from dotenv import load_dotenv  # Importante para ler o .env
from fastapi import FastAPI, Request, Form, Response, status, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional

# 1. Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

app = FastAPI(title="Frontend Startup Radar")

# Configuração de Arquivos Estáticos e Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 2. Pega a URL do arquivo .env (Se não achar, usa o localhost como padrão de segurança)
BACKEND_URL = os.getenv("BACKEND_URL")

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_current_user(token: str):
    """Obtém informações do usuário atual do backend"""
    try:
        headers = {"Authorization": token}
        response = requests.get(f"{BACKEND_URL}/users/me", headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# ==========================================
# AUTENTICAÇÃO (LOGIN / REGISTRO / LOGOUT)
# ==========================================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login_action(request: Request, response: Response, email: str = Form(...), password: str = Form(...)):
    print(f"DEBUG: Tentando login: {email}")
    try:
        payload = {"username": email, "password": password}
        # Timeout 10s para garantir conexão
        api_res = requests.post(f"{BACKEND_URL}/token", data=payload, timeout=10)

        if api_res.status_code == 200:
            token_data = api_res.json()
            access_token = token_data["access_token"]
            
            # Redireciona para a Home
            redirect = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
            
            # Configuração Segura de Cookie para Localhost
            redirect.set_cookie(
                key="access_token", 
                value=f"Bearer {access_token}", 
                httponly=True, 
                samesite="lax",
                secure=False 
            )
            return redirect
        else:
            return templates.TemplateResponse("login.html", {"request": request, "error": "E-mail ou senha incorretos."})
            
    except requests.exceptions.ConnectionError:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Erro: Backend offline."})
    except Exception as e:
        return templates.TemplateResponse("login.html", {"request": request, "error": f"Erro: {e}"})

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})

@app.post("/register")
def register_action(request: Request, response: Response, email: str = Form(...), password: str = Form(...)):
    print(f"DEBUG: Registrando usuário: {email}")
    try:
        payload = {"email": email, "password": password}
        api_res = requests.post(f"{BACKEND_URL}/register", json=payload, timeout=10)

        if api_res.status_code == 200:
            token_data = api_res.json()
            access_token = token_data["access_token"]
            
            # Login automático após registro
            redirect = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
            redirect.set_cookie(
                key="access_token", 
                value=f"Bearer {access_token}", 
                httponly=True, 
                samesite="lax",
                secure=False 
            )
            return redirect
        
        elif api_res.status_code == 400:
            detail = api_res.json().get("detail", "Erro ao cadastrar.")
            return templates.TemplateResponse("register.html", {"request": request, "error": detail})
        else:
            return templates.TemplateResponse("register.html", {"request": request, "error": f"Erro: {api_res.status_code}"})
            
    except Exception as e:
        return templates.TemplateResponse("register.html", {"request": request, "error": f"Erro: {e}"})

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("access_token")
    return response


# ==========================================
# FUNCIONALIDADES PRINCIPAIS (DASHBOARD)
# ==========================================

# 1. HOME (Busca Inteligente + Filtro de Fase)
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, q: Optional[str] = None, fase: Optional[str] = None):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login")

    empresas_exibidas = []
    error_msg = None

    # Lógica para combinar Texto + Fase para a IA do Backend
    termo_busca = q
    if fase and fase != "":
        if q:
            termo_busca = f"{q} {fase}"
        else:
            termo_busca = fase

    try:
        headers = {"Authorization": token}
        
        if termo_busca:
            # Busca Semântica no Backend (/semantic-search) com IA
            response = requests.get(
                f"{BACKEND_URL}/semantic-search",
                params={
                    "query": termo_busca,
                    "top_k": 10,
                    "similarity_threshold": 0.5,
                    "use_query_expansion": True
                },
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                empresas_exibidas = response.json()
            elif response.status_code == 404:
                empresas_exibidas = [] 
            elif response.status_code == 401:
                return RedirectResponse(url="/login")
            else:
                error_msg = f"Erro na Busca: {response.status_code}"
        else:
            # Lista Completa (Hero View) se não houver busca nem fase
            response = requests.get(
                f"{BACKEND_URL}/companies", 
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                empresas_exibidas = response.json()
            elif response.status_code == 401:
                return RedirectResponse(url="/login")
            else:
                error_msg = f"Erro ao carregar dados: {response.status_code}"

        # Filtro de Fase Local (para garantir exatidão)
        if fase and fase != "":
            empresas_exibidas = [
                emp for emp in empresas_exibidas 
                if emp.get('fase_da_startup') == fase
            ]

    except Exception as e:
        error_msg = f"Erro de conexão: {e}"

    # Calculate statistics for dashboard cards
    stats = {}
    if not termo_busca and empresas_exibidas:
        stats['total'] = len(empresas_exibidas)
        stats['ideacao'] = len([e for e in empresas_exibidas if e.get('fase_da_startup') == 'Ideação'])
        stats['operacao'] = len([e for e in empresas_exibidas if e.get('fase_da_startup') == 'Operação'])
        stats['tracao'] = len([e for e in empresas_exibidas if e.get('fase_da_startup') == 'Tração'])
        stats['escala'] = len([e for e in empresas_exibidas if e.get('fase_da_startup') == 'Escala'])
        stats['com_investimento'] = len([e for e in empresas_exibidas if e.get('recebeu_investimento') == 'Sim'])

        # Count unique sectors
        setores = set()
        for e in empresas_exibidas:
            if e.get('setor_principal'):
                setores.add(e.get('setor_principal'))
        stats['setores'] = len(setores)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "empresas": empresas_exibidas,
        "query": q,
        "fase": fase, # Passamos a fase para manter o select selecionado
        "error": error_msg,
        "stats": stats
    })

# 2. LISTA EM TABELA
@app.get("/lista", response_class=HTMLResponse)
def lista_tabela(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login")

    empresas_lista = []
    error_msg = None

    try:
        headers = {"Authorization": token}
        response = requests.get(f"{BACKEND_URL}/companies", headers=headers, timeout=30)
        
        if response.status_code == 200:
            empresas_lista = response.json()
            # Ordenação A-Z no Python
            empresas_lista.sort(key=lambda x: x['nome_da_empresa'].lower())
        elif response.status_code == 401:
            return RedirectResponse(url="/login")
        else:
            error_msg = f"Erro: {response.status_code}"

    except Exception as e:
        error_msg = f"Erro de conexão: {e}"

    return templates.TemplateResponse("tabela.html", {
        "request": request,
        "empresas": empresas_lista,
        "error": error_msg
    })

# 3. DETALHES DA EMPRESA
@app.get("/empresa/{empresa_id}", response_class=HTMLResponse)
def detalhes_empresa(request: Request, empresa_id: int):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login")

    empresa_selecionada = None
    error_msg = None

    try:
        headers = {"Authorization": token}
        # Busca lista e filtra (simulando get_by_id se a rota não existir)
        response = requests.get(f"{BACKEND_URL}/companies", headers=headers, timeout=30)
        
        if response.status_code == 200:
            todos_dados = response.json()
            for emp in todos_dados:
                if emp['id'] == empresa_id:
                    empresa_selecionada = emp
                    break
            
            if not empresa_selecionada:
                error_msg = "Empresa não encontrada."
        elif response.status_code == 401:
            return RedirectResponse(url="/login")
        else:
            error_msg = f"Erro no Backend: {response.status_code}"

    except Exception as e:
        error_msg = f"Erro de conexão: {e}"

    return templates.TemplateResponse("detalhes.html", {
        "request": request,
        "empresa": empresa_selecionada,
        "error": error_msg
    })

# ==========================================
# EDIÇÃO DE DADOS (MÍDIA E CONTATO)
# ==========================================

@app.get("/empresa/{empresa_id}/editar", response_class=HTMLResponse)
def editar_empresa_page(request: Request, empresa_id: int):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login")

    try:
        headers = {"Authorization": token}
        response = requests.get(f"{BACKEND_URL}/companies", headers=headers, timeout=30)
        
        empresa_alvo = None
        if response.status_code == 200:
            todos = response.json()
            for emp in todos:
                if emp['id'] == empresa_id:
                    empresa_alvo = emp
                    break
        
        if not empresa_alvo:
            return templates.TemplateResponse("nao_encontrado.html", {
                "request": request,
                "message": "A empresa que você está procurando não foi encontrada no sistema."
            }, status_code=404)

        return templates.TemplateResponse("editar.html", {
            "request": request,
            "empresa": empresa_alvo
        })

    except Exception as e:
        return templates.TemplateResponse("erro_generico.html", {
            "request": request,
            "message": f"Ocorreu um erro ao processar sua solicitação: {str(e)}",
            "code": "500"
        }, status_code=500)

# --- ACTIONS DE ATUALIZAÇÃO ---

@app.post("/empresa/{empresa_id}/upload_apresentacao")
async def upload_apresentacao_action(request: Request, empresa_id: int, arquivo: UploadFile = File(...)):
    token = request.cookies.get("access_token")
    headers = {"Authorization": token}
    
    if not arquivo.filename:
        return RedirectResponse(url=f"/empresa/{empresa_id}/editar", status_code=303)

    try:
        conteudo = await arquivo.read()
        tipo_conteudo = arquivo.content_type
        nome_arquivo = arquivo.filename

        files = {
            "file": (nome_arquivo, conteudo, tipo_conteudo)
        }

        requests.patch(
            f"{BACKEND_URL}/upload/apresentacao/{empresa_id}", 
            files=files, 
            headers=headers,
            timeout=30
        )

    except Exception as e:
        print(f"Erro upload: {e}")

    return RedirectResponse(url=f"/empresa/{empresa_id}/editar", status_code=303)

@app.get("/empresa/{empresa_id}/delete_apresentacao")
def delete_apresentacao_action(request: Request, empresa_id: int):
    token = request.cookies.get("access_token")
    headers = {"Authorization": token}
    
    requests.delete(f"{BACKEND_URL}/empresa/{empresa_id}/apresentacao", headers=headers, timeout=10)
    
    return RedirectResponse(url=f"/empresa/{empresa_id}/editar", status_code=303)

@app.post("/empresa/{empresa_id}/update_video")
def update_video(request: Request, empresa_id: int, link_video: Optional[str] = Form(None)):
    token = request.cookies.get("access_token")
    headers = {"Authorization": token}
    
    if not link_video or link_video.strip() == "":
        requests.delete(f"{BACKEND_URL}/empresa/{empresa_id}/video", headers=headers, timeout=10)
    else:
        payload = {"link_video": link_video.strip()}
        requests.patch(f"{BACKEND_URL}/empresa/{empresa_id}/video", json=payload, headers=headers, timeout=10)
    
    return RedirectResponse(url=f"/empresa/{empresa_id}/editar", status_code=303)

@app.post("/empresa/{empresa_id}/update_telefone")
def update_telefone(request: Request, empresa_id: int, telefone_contato: Optional[str] = Form(None)):
    token = request.cookies.get("access_token")
    headers = {"Authorization": token}

    if not telefone_contato or telefone_contato.strip() == "":
        requests.delete(f"{BACKEND_URL}/empresa/{empresa_id}/telefone", headers=headers, timeout=10)
    else:
        payload = {"telefone_contato": telefone_contato.strip()}
        requests.patch(f"{BACKEND_URL}/empresa/{empresa_id}/telefone", json=payload, headers=headers, timeout=10)

    return RedirectResponse(url=f"/empresa/{empresa_id}/editar", status_code=303)

# ==========================================
# ADMIN - GERENCIAR USUÁRIOS
# ==========================================

@app.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login")

    current_user = get_current_user(token)
    if not current_user or current_user.get("role") != "admin":
        return templates.TemplateResponse("acesso_negado.html", {
            "request": request,
            "message": "Apenas administradores podem acessar esta página.",
            "required_role": "Administrador",
            "user_role": current_user.get("role", "Usuário") if current_user else "Não autenticado"
        }, status_code=403)

    users = []
    error_msg = None

    try:
        headers = {"Authorization": token}
        # Note: Backend doesn't have /users endpoint, we'll need to add it or show only current user
        # For now, showing message that this needs backend support
        error_msg = "Funcionalidade em desenvolvimento - endpoint /users não disponível no backend"
    except Exception as e:
        error_msg = f"Erro: {e}"

    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "users": users,
        "current_user": current_user,
        "error": error_msg
    })

# ==========================================
# ADMIN - CRIAR NOVA STARTUP
# ==========================================

@app.get("/admin/criar-startup", response_class=HTMLResponse)
def criar_startup_page(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login")

    current_user = get_current_user(token)
    if not current_user or current_user.get("role") not in ["admin", "maintainer"]:
        return templates.TemplateResponse("acesso_negado.html", {
            "request": request,
            "message": "Esta funcionalidade está disponível apenas para administradores e mantenedores.",
            "required_role": "Administrador ou Mantenedor",
            "user_role": current_user.get("role", "Usuário") if current_user else "Não autenticado"
        }, status_code=403)

    return templates.TemplateResponse("criar_startup.html", {
        "request": request,
        "current_user": current_user,
        "error": None
    })

@app.post("/admin/criar-startup")
async def criar_startup_action(request: Request):
    token = request.cookies.get("access_token")
    headers = {"Authorization": token}

    form_data = await request.form()

    payload = {
        "nome_da_empresa": form_data.get("nome_da_empresa"),
        "endereco": form_data.get("endereco"),
        "cnpj": form_data.get("cnpj"),
        "ano_de_fundacao": int(form_data.get("ano_de_fundacao")),
        "site": form_data.get("site", ""),
        "rede_social": form_data.get("rede_social", ""),
        "cadastrado_por": form_data.get("cadastrado_por", ""),
        "cargo": form_data.get("cargo", ""),
        "email": form_data.get("email", ""),
        "setor_principal": form_data.get("setor_principal"),
        "setor_secundario": form_data.get("setor_secundario", ""),
        "fase_da_startup": form_data.get("fase_da_startup"),
        "colaboradores": form_data.get("colaboradores"),
        "publico_alvo": form_data.get("publico_alvo"),
        "modelo_de_negocio": form_data.get("modelo_de_negocio"),
        "recebeu_investimento": form_data.get("recebeu_investimento"),
        "negocios_no_exterior": form_data.get("negocios_no_exterior"),
        "faturamento": form_data.get("faturamento"),
        "patente": form_data.get("patente"),
        "ja_pivotou": form_data.get("ja_pivotou"),
        "comunidades": form_data.get("comunidades", ""),
        "solucao": form_data.get("solucao"),
        "tag": form_data.get("tag", "")
    }

    try:
        response = requests.post(f"{BACKEND_URL}/empresa", json=payload, headers=headers, timeout=30)

        if response.status_code == 201:
            empresa = response.json()
            return RedirectResponse(url=f"/empresa/{empresa['id']}", status_code=303)
        else:
            current_user = get_current_user(token)
            error_detail = response.json().get("detail", f"Erro {response.status_code}")
            return templates.TemplateResponse("criar_startup.html", {
                "request": request,
                "current_user": current_user,
                "error": f"Erro ao criar startup: {error_detail}",
                "form_data": form_data
            })
    except Exception as e:
        current_user = get_current_user(token)
        return templates.TemplateResponse("criar_startup.html", {
            "request": request,
            "current_user": current_user,
            "error": f"Erro de conexão: {e}",
            "form_data": form_data
        })

# ==========================================
# ADMIN - EDITAR STARTUP COMPLETO
# ==========================================

@app.get("/admin/editar-startup/{empresa_id}", response_class=HTMLResponse)
def editar_startup_completo_page(request: Request, empresa_id: int):
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/login")

    current_user = get_current_user(token)
    if not current_user or current_user.get("role") not in ["admin", "maintainer"]:
        return templates.TemplateResponse("acesso_negado.html", {
            "request": request,
            "message": "Esta funcionalidade está disponível apenas para administradores e mantenedores.",
            "required_role": "Administrador ou Mantenedor",
            "user_role": current_user.get("role", "Usuário") if current_user else "Não autenticado"
        }, status_code=403)

    try:
        headers = {"Authorization": token}
        response = requests.get(f"{BACKEND_URL}/companies", headers=headers, timeout=30)

        empresa_alvo = None
        if response.status_code == 200:
            todos = response.json()
            for emp in todos:
                if emp['id'] == empresa_id:
                    empresa_alvo = emp
                    break

        if not empresa_alvo:
            return templates.TemplateResponse("nao_encontrado.html", {
                "request": request,
                "message": "A empresa que você está procurando não foi encontrada no sistema."
            }, status_code=404)

        return templates.TemplateResponse("editar_startup_completo.html", {
            "request": request,
            "empresa": empresa_alvo,
            "current_user": current_user,
            "error": None
        })
    except Exception as e:
        return templates.TemplateResponse("erro_generico.html", {
            "request": request,
            "message": f"Ocorreu um erro ao processar sua solicitação: {str(e)}",
            "code": "500"
        }, status_code=500)

@app.post("/admin/editar-startup/{empresa_id}")
async def editar_startup_completo_action(request: Request, empresa_id: int):
    token = request.cookies.get("access_token")
    headers = {"Authorization": token}

    form_data = await request.form()

    payload = {
        "nome_da_empresa": form_data.get("nome_da_empresa"),
        "endereco": form_data.get("endereco"),
        "cnpj": form_data.get("cnpj"),
        "ano_de_fundacao": int(form_data.get("ano_de_fundacao")),
        "site": form_data.get("site", ""),
        "rede_social": form_data.get("rede_social", ""),
        "cadastrado_por": form_data.get("cadastrado_por", ""),
        "cargo": form_data.get("cargo", ""),
        "email": form_data.get("email", ""),
        "setor_principal": form_data.get("setor_principal"),
        "setor_secundario": form_data.get("setor_secundario", ""),
        "fase_da_startup": form_data.get("fase_da_startup"),
        "colaboradores": form_data.get("colaboradores"),
        "publico_alvo": form_data.get("publico_alvo"),
        "modelo_de_negocio": form_data.get("modelo_de_negocio"),
        "recebeu_investimento": form_data.get("recebeu_investimento"),
        "negocios_no_exterior": form_data.get("negocios_no_exterior"),
        "faturamento": form_data.get("faturamento"),
        "patente": form_data.get("patente"),
        "ja_pivotou": form_data.get("ja_pivotou"),
        "comunidades": form_data.get("comunidades", ""),
        "solucao": form_data.get("solucao"),
        "tag": form_data.get("tag", "")
    }

    try:
        response = requests.put(f"{BACKEND_URL}/empresa/{empresa_id}", json=payload, headers=headers, timeout=30)

        if response.status_code == 200:
            return RedirectResponse(url=f"/empresa/{empresa_id}", status_code=303)
        else:
            current_user = get_current_user(token)
            error_detail = response.json().get("detail", f"Erro {response.status_code}")

            # Get empresa data again for form
            empresa_response = requests.get(f"{BACKEND_URL}/companies", headers=headers, timeout=30)
            empresa_alvo = None
            if empresa_response.status_code == 200:
                for emp in empresa_response.json():
                    if emp['id'] == empresa_id:
                        empresa_alvo = emp
                        break

            return templates.TemplateResponse("editar_startup_completo.html", {
                "request": request,
                "empresa": empresa_alvo,
                "current_user": current_user,
                "error": f"Erro ao atualizar: {error_detail}"
            })
    except Exception as e:
        current_user = get_current_user(token)
        return templates.TemplateResponse("editar_startup_completo.html", {
            "request": request,
            "empresa": {},
            "current_user": current_user,
            "error": f"Erro de conexão: {e}"
        })

# ==========================================
# ADMIN - DELETAR STARTUP
# ==========================================

@app.post("/admin/deletar-startup/{empresa_id}")
def deletar_startup_action(request: Request, empresa_id: int):
    token = request.cookies.get("access_token")
    headers = {"Authorization": token}

    try:
        response = requests.delete(f"{BACKEND_URL}/empresa/{empresa_id}", headers=headers, timeout=10)

        if response.status_code == 204:
            return RedirectResponse(url="/lista?deleted=true", status_code=303)
        else:
            return RedirectResponse(url=f"/empresa/{empresa_id}?error=delete_failed", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/empresa/{empresa_id}?error=connection", status_code=303)