from fastapi import FastAPI, Request, Depends, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from a2wsgi import ASGIMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
import os
import uuid
import random
from dotenv import load_dotenv

from database import (
    init_db, get_db, User, Account, Transaction, FixedCostRule, Category, 
    InstallmentPlan, FutureIncome, FinancialGoal, SessionLocal,
    Workspace, WorkspaceMember, get_user_workspace, ensure_user_workspace,
    RegistrationVerification
)
from auth import (
    get_password_hash, verify_password, create_access_token, 
    get_current_user, get_current_admin
)
from email_service import send_confirmation_code, ADMIN_NOTIFICATION_EMAIL
from ofx_parser import parse_and_import_ofx
from pdf_parser import parse_and_import_pdf

# Carrega variáveis de ambiente
load_dotenv()

# Inicializa o banco de dados SQLite (cria tabelas e migrações)
init_db()

def seed_users():
    """
    Inicializa os usuários e workspaces padrão da plataforma.
    Se nenhuma credencial estiver no banco, cria o administrador padrão.
    """
    db = SessionLocal()
    try:
        user1_email = os.getenv("USER1_EMAIL")
        user1_name = os.getenv("USER1_NAME")
        user1_pass = os.getenv("USER1_PASSWORD")

        user2_email = os.getenv("USER2_EMAIL")
        user2_name = os.getenv("USER2_NAME")
        user2_pass = os.getenv("USER2_PASSWORD")

        def create_or_update_user(email, name, password, is_admin=False):
            if not email: return None
            password_hash = get_password_hash(password)
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(email=email, full_name=name or email, hashed_password=password_hash, is_admin=is_admin)
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"Usuário {email} criado.")
            else:
                user.full_name = name or user.full_name
                user.hashed_password = password_hash
                if is_admin:
                    user.is_admin = True
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"Usuário {email} atualizado.")
            
            # Garante que o usuário possua seu próprio banco de dados / workspace
            ensure_user_workspace(user, db)
            return user

        # 1. Se variáveis de ambiente estiverem configuradas, semeia os usuários
        if user1_email and user1_pass:
            create_or_update_user(user1_email, user1_name, user1_pass, is_admin=True)
            if user2_email and user2_pass:
                create_or_update_user(user2_email, user2_name, user2_pass, is_admin=False)
        
        # 2. Se o banco de dados não possuir NENHUM usuário cadastrado, cria admin padrão
        if db.query(User).count() == 0:
            create_or_update_user("admin@thamifin.com", "Dennis Admin", "admin123", is_admin=True)
            print("Usuário administrador inicial criado: admin@thamifin.com / admin123")
            
        # 3. Garante que todos os usuários existentes tenham seus workspaces configurados
        all_users = db.query(User).all()
        for u in all_users:
            ensure_user_workspace(u, db)
            
    except Exception as e:
        db.rollback()
        print("Erro durante seeding de usuários:", e)
    finally:
        db.close()

# Executa seeding
seed_users()

# Inicializa o app FastAPI
app = FastAPI(title="ThamiFin Platform")

# Middleware para compatibilidade com PythonAnywhere (WSGI)
wsgi_app = ASGIMiddleware(app)

# Define o diretório base para caminhos absolutos
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Monta arquivos estáticos (CSS / JS) e templates HTML
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --- ROTAS DE REDIRECIONAMENTO ---

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Redireciona para o login ou dashboard baseado nos cookies de login."""
    token = request.cookies.get("access_token")
    if token:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


# --- ROTAS DE AUTENTICAÇÃO (HTML & API) ---

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Renderiza a página de login."""
    return templates.TemplateResponse(request=request, name="login.html", context={"initial_tab": "login"})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    """Renderiza a página de cadastro com envio de código de confirmação."""
    return templates.TemplateResponse(request=request, name="login.html", context={"initial_tab": "register"})


@app.post("/api/auth/request-code")
def request_registration_code(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Gera um código de 6 dígitos e envia para drinaldim@gmail.com
    para liberação do cadastro do novo usuário.
    """
    full_name_clean = full_name.strip()
    email_clean = email.strip().lower()
    
    if len(full_name_clean) < 2:
        raise HTTPException(status_code=400, detail="Por favor, digite seu nome completo.")
    if "@" not in email_clean or "." not in email_clean:
        raise HTTPException(status_code=400, detail="Email inválido.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="A senha deve conter no mínimo 6 caracteres.")
        
    # Verifica se já existe conta ativa com este email
    if db.query(User).filter(User.email == email_clean).first():
        raise HTTPException(status_code=400, detail="Este email já está cadastrado na plataforma.")
        
    # Gera código numérico de 6 dígitos
    code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    
    # Salva ou atualiza a solicitação pendente
    pending = db.query(RegistrationVerification).filter(
        RegistrationVerification.email == email_clean,
        RegistrationVerification.verified == False
    ).first()
    
    password_hash = get_password_hash(password)
    
    if pending:
        pending.full_name = full_name_clean
        pending.hashed_password = password_hash
        pending.code = code
        pending.expires_at = expires_at
        pending.created_at = datetime.utcnow()
    else:
        pending = RegistrationVerification(
            full_name=full_name_clean,
            email=email_clean,
            hashed_password=password_hash,
            code=code,
            target_email=ADMIN_NOTIFICATION_EMAIL,
            expires_at=expires_at
        )
        db.add(pending)
        
    db.commit()
    
    # Dispara e-mail de confirmação para drinaldim@gmail.com
    send_confirmation_code(user_name=full_name_clean, user_email=email_clean, code=code)
    
    return {
        "status": "success",
        "message": f"Código de confirmação enviado para {ADMIN_NOTIFICATION_EMAIL}. Solicite o código ao administrador para prosseguir com seu cadastro.",
        "email": email_clean,
        "target_email": ADMIN_NOTIFICATION_EMAIL
    }


@app.post("/api/auth/verify-code")
def verify_registration_code(
    email: str = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Valida o código de confirmação recebido em drinaldim@gmail.com
    e conclui a criação da conta e do banco de dados pessoal do usuário.
    """
    email_clean = email.strip().lower()
    code_clean = code.strip()
    
    pending = db.query(RegistrationVerification).filter(
        RegistrationVerification.email == email_clean,
        RegistrationVerification.verified == False
    ).order_by(RegistrationVerification.id.desc()).first()
    
    if not pending:
        raise HTTPException(
            status_code=400,
            detail="Nenhuma solicitação pendente encontrada para este email. Inicie novamente."
        )
        
    if datetime.utcnow() > pending.expires_at:
        raise HTTPException(
            status_code=400,
            detail="O código de confirmação expirou (validade: 15 minutos). Por favor, solicite um novo código."
        )
        
    if pending.code.strip() != code_clean:
        raise HTTPException(
            status_code=400,
            detail="Código de confirmação incorreto. Verifique o código enviado para drinaldim@gmail.com."
        )
        
    if db.query(User).filter(User.email == email_clean).first():
        raise HTTPException(status_code=400, detail="Este email já foi cadastrado.")
        
    # Cria o novo usuário
    new_user = User(
        full_name=pending.full_name,
        email=pending.email,
        hashed_password=pending.hashed_password,
        is_admin=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Provisiona o Banco de Dados / Espaço próprio exclusivo com contas bancárias
    ensure_user_workspace(new_user, db)
    
    # Marca como verificado
    pending.verified = True
    db.commit()
    
    # Autentica o usuário imediatamente com Cookie JWT
    access_token = create_access_token(data={"sub": new_user.email})
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=86400,
        samesite="lax",
        secure=False
    )
    return response


@app.post("/auth/register")
def register(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirmation_code: str = Form(None),
    db: Session = Depends(get_db)
):
    """
    Processa o cadastro: se o código for enviado, valida e cria.
    Se não, solicita o código enviando para drinaldim@gmail.com.
    """
    if confirmation_code:
        return verify_registration_code(email=email, code=confirmation_code, db=db)
    else:
        request_registration_code(full_name=full_name, email=email, password=password, db=db)
        return RedirectResponse(url=f"/register?step=verify&email={email}", status_code=303)


@app.post("/auth/login")
def login(
    response: RedirectResponse,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...)
):
    """Efetua a validação do login e injeta o Cookie JWT HTTP-Only."""
    email_clean = email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user or not verify_password(password, user.hashed_password):
        return RedirectResponse(url="/login?error=true", status_code=303)
        
    # Garante que o usuário tem seu espaço configurado
    ensure_user_workspace(user, db)
    
    # Criação do token de sessão JWT válido por 24 horas
    access_token = create_access_token(data={"sub": user.email})
    
    redirect = RedirectResponse(url="/dashboard", status_code=303)
    redirect.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=86400,
        samesite="lax",
        secure=False
    )
    return redirect


@app.get("/auth/logout")
def logout():
    """Remove a sessão do usuário deletando o cookie do JWT."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response


# --- PÁGINAS PRINCIPAIS DO DASHBOARD (ISOLADAS POR BANCO DE DADOS) ---

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página principal do dashboard."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    workspace = get_user_workspace(current_user, db)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html", 
        context={"user": current_user, "workspace": workspace, "active_page": "dashboard"}
    )


@app.get("/receitas", response_class=HTMLResponse)
def receitas_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de receitas."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    workspace = get_user_workspace(current_user, db)
    return templates.TemplateResponse(
        request=request,
        name="receitas.html", 
        context={"user": current_user, "workspace": workspace, "active_page": "receitas"}
    )


@app.get("/custos", response_class=HTMLResponse)
def custos_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de custos fixos e variáveis."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    workspace = get_user_workspace(current_user, db)
    return templates.TemplateResponse(
        request=request,
        name="custos.html", 
        context={"user": current_user, "workspace": workspace, "active_page": "custos"}
    )


@app.get("/graficos", response_class=HTMLResponse)
def graficos_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de gráficos interativos."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    workspace = get_user_workspace(current_user, db)
    return templates.TemplateResponse(
        request=request,
        name="graficos.html", 
        context={"user": current_user, "workspace": workspace, "active_page": "graficos"}
    )


@app.get("/parcelamentos", response_class=HTMLResponse)
def parcelamentos_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de parcelamentos."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    workspace = get_user_workspace(current_user, db)
    return templates.TemplateResponse(
        request=request,
        name="parcelamentos.html", 
        context={"user": current_user, "workspace": workspace, "active_page": "parcelamentos"}
    )


@app.get("/metas", response_class=HTMLResponse)
def metas_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de metas e projeções."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    workspace = get_user_workspace(current_user, db)
    return templates.TemplateResponse(
        request=request,
        name="metas.html", 
        context={"user": current_user, "workspace": workspace, "active_page": "metas"}
    )


# --- PÁGINA DO PERFIL DO USUÁRIO & COMPARTILHAMENTO DE BANCO DE DADOS ---

@app.get("/perfil", response_class=HTMLResponse)
def perfil_page(request: Request, db: Session = Depends(get_db)):
    """
    Página do Perfil do Usuário:
    - Exibe dados do usuário logado.
    - Exibe o Banco de Dados / Espaço ativo com suas contas bancárias.
    - Permite adicionar outros logins como membros com acesso a este banco de dados.
    """
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    workspace = get_user_workspace(current_user, db)
    memberships = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == current_user.id).all()
    workspace_members = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace.id).all()
    workspace_accounts = db.query(Account).filter(Account.workspace_id == workspace.id).all()
    
    return templates.TemplateResponse(
        request=request,
        name="perfil.html",
        context={
            "user": current_user,
            "workspace": workspace,
            "active_page": "perfil",
            "all_user_workspaces": memberships,
            "workspace_members": workspace_members,
            "workspace_accounts": workspace_accounts
        }
    )


@app.post("/api/profile/add-access")
def add_profile_access(
    email: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Adiciona outra conta de usuário (login) para ter acesso completo
    ao Banco de Dados / Espaço e contas bancárias do usuário atual.
    """
    email_clean = email.strip().lower()
    if not email_clean:
        raise HTTPException(status_code=400, detail="O email não pode ser vazio.")
        
    workspace = get_user_workspace(current_user, db)
    
    # Busca se o usuário já existe no sistema
    target_user = db.query(User).filter(User.email == email_clean).first()
    new_created = False
    temp_pass = ""
    
    if not target_user:
        # Cria a conta do convidado com uma senha padrão para acesso imediato
        temp_pass = "123456"
        target_user = User(
            email=email_clean,
            full_name=email_clean.split("@")[0].capitalize(),
            hashed_password=get_password_hash(temp_pass),
            is_admin=False
        )
        db.add(target_user)
        db.commit()
        db.refresh(target_user)
        new_created = True
        
    # Verifica se já é membro deste espaço
    existing_membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace.id,
        WorkspaceMember.user_id == target_user.id
    ).first()
    
    if existing_membership:
        raise HTTPException(status_code=400, detail="Esta conta já possui acesso a este Banco de Dados.")
        
    membership = WorkspaceMember(workspace_id=workspace.id, user_id=target_user.id, role="member")
    db.add(membership)
    if not target_user.current_workspace_id:
        target_user.current_workspace_id = workspace.id
        db.add(target_user)
    db.commit()
    
    if new_created:
        return {
            "status": "success",
            "message": f"Conta criada para '{email_clean}' com senha inicial '{temp_pass}' e vinculada com sucesso ao seu Banco de Dados!"
        }
    return {
        "status": "success",
        "message": f"Acesso concedido com sucesso para a conta '{email_clean}'!"
    }


@app.post("/api/profile/remove-access/{member_id}")
def remove_profile_access(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Revoga o acesso de um usuário ao banco de dados do espaço atual."""
    workspace = get_user_workspace(current_user, db)
    membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.id == member_id,
        WorkspaceMember.workspace_id == workspace.id
    ).first()
    
    if not membership:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado.")
        
    if membership.user_id == workspace.owner_id:
        raise HTTPException(status_code=400, detail="Não é permitido revogar o acesso do proprietário do Banco de Dados.")
        
    target_user = membership.user
    if target_user and target_user.current_workspace_id == workspace.id:
        other_m = db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == target_user.id,
            WorkspaceMember.workspace_id != workspace.id
        ).first()
        target_user.current_workspace_id = other_m.workspace_id if other_m else None
        db.add(target_user)
        
    db.delete(membership)
    db.commit()
    return {"status": "success", "message": "Acesso revogado com sucesso."}


@app.post("/api/profile/switch-workspace")
def switch_workspace(
    workspace_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Alterna o banco de dados ativo do usuário caso ele tenha acesso a mais de um."""
    membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Você não tem acesso a este Banco de Dados.")
        
    current_user.current_workspace_id = workspace_id
    db.add(current_user)
    db.commit()
    return {"status": "success", "message": "Banco de Dados ativo alternado com sucesso!"}


# --- PAINEL ADMINISTRATIVO (/admin) ---

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    """
    Painel em /admin da URL do site:
    Permite gerenciar e linkar contas de usuários a certos bancos de dados,
    criar novos bancos de dados e gerenciar contas bancárias associadas.
    """
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    if not current_user.is_admin:
        return RedirectResponse(url="/dashboard?error=admin_only", status_code=303)
        
    all_users = db.query(User).order_by(User.id.asc()).all()
    all_workspaces = db.query(Workspace).order_by(Workspace.id.asc()).all()
    total_accounts = db.query(Account).count()
    total_transactions = db.query(Transaction).count()
    
    stats = {
        "total_users": len(all_users),
        "total_workspaces": len(all_workspaces),
        "total_accounts": total_accounts,
        "total_transactions": total_transactions
    }
    
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "user": current_user,
            "db": db,
            "active_page": "admin",
            "all_users": all_users,
            "all_workspaces": all_workspaces,
            "stats": stats
        }
    )


@app.post("/api/admin/users")
def admin_create_user(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    workspace_choice: str = Form("NEW"),
    is_admin: bool = Form(False),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Cria um novo usuário e vincula ao banco de dados escolhido ou cria um exclusivo."""
    email_clean = email.strip().lower()
    if db.query(User).filter(User.email == email_clean).first():
        raise HTTPException(status_code=400, detail="Este email já está cadastrado.")
        
    new_user = User(
        full_name=full_name.strip(),
        email=email_clean,
        hashed_password=get_password_hash(password),
        is_admin=is_admin
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    if workspace_choice == "NEW":
        ensure_user_workspace(new_user, db)
    else:
        try:
            ws_id = int(workspace_choice)
            ws = db.query(Workspace).filter(Workspace.id == ws_id).first()
            if ws:
                member = WorkspaceMember(workspace_id=ws.id, user_id=new_user.id, role="member")
                db.add(member)
                new_user.current_workspace_id = ws.id
                db.add(new_user)
                db.commit()
            else:
                ensure_user_workspace(new_user, db)
        except ValueError:
            ensure_user_workspace(new_user, db)
            
    return {"status": "success", "message": f"Usuário '{full_name}' cadastrado com sucesso!"}


@app.post("/api/admin/workspaces")
def admin_create_workspace(
    name: str = Form(...),
    owner_id: int = Form(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Cria um novo Banco de Dados / Espaço Financeiro e vincula ao proprietário selecionado."""
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="O nome não pode ser vazio.")
        
    owner = db.query(User).filter(User.id == owner_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Usuário proprietário não encontrado.")
        
    ident = f"db_{owner_id}_{uuid.uuid4().hex[:6]}"
    ws = Workspace(name=name_clean, db_identifier=ident, owner_id=owner_id)
    db.add(ws)
    db.commit()
    db.refresh(ws)
    
    # Vincula o proprietário
    m = WorkspaceMember(workspace_id=ws.id, user_id=owner_id, role="owner")
    db.add(m)
    
    # Cria contas bancárias padrão
    default_accounts = [
        Account(workspace_id=ws.id, user_id=owner_id, bank_name="Nubank", balance=0.0),
        Account(workspace_id=ws.id, user_id=owner_id, bank_name="Banco Inter", balance=0.0),
        Account(workspace_id=ws.id, user_id=owner_id, bank_name="Caixa", balance=0.0),
    ]
    db.add_all(default_accounts)
    db.commit()
    
    return {"status": "success", "message": f"Banco de Dados '{name_clean}' criado com sucesso!"}


@app.post("/api/admin/link-user-workspace")
def admin_link_user_workspace(
    user_id: int = Form(...),
    workspace_id: int = Form(...),
    set_as_active: bool = Form(True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Linka uma conta de usuário a certo Banco de Dados pelo painel /admin."""
    user = db.query(User).filter(User.id == user_id).first()
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not user or not ws:
        raise HTTPException(status_code=404, detail="Usuário ou Banco de Dados não encontrado.")
        
    existing = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == user_id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    
    if not existing:
        m = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="member")
        db.add(m)
        
    if set_as_active:
        user.current_workspace_id = workspace_id
        db.add(user)
        
    db.commit()
    return {"status": "success", "message": f"Conta '{user.full_name}' vinculada com sucesso ao Banco de Dados '{ws.name}'!"}


@app.post("/api/admin/unlink-user-workspace")
def admin_unlink_user_workspace(
    user_id: int = Form(...),
    workspace_id: int = Form(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Remove o vínculo de uma conta com certo Banco de Dados pelo painel /admin."""
    membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.user_id == user_id,
        WorkspaceMember.workspace_id == workspace_id
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado.")
        
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.current_workspace_id == workspace_id:
        other = db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id != workspace_id
        ).first()
        user.current_workspace_id = other.workspace_id if other else None
        db.add(user)
        
    db.delete(membership)
    db.commit()
    return {"status": "success", "message": "Vínculo removido com sucesso."}


@app.post("/api/admin/users/{user_id}/toggle-admin")
def admin_toggle_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Alterna os privilégios de administrador de uma conta."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if user.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Você não pode revogar seus próprios privilégios de administrador.")
    user.is_admin = not user.is_admin
    db.add(user)
    db.commit()
    status_text = "Administrador" if user.is_admin else "Usuário Padrão"
    return {"status": "success", "message": f"Usuário {user.full_name} agora é {status_text}."}


@app.post("/api/admin/workspaces/{workspace_id}/accounts")
def admin_add_account_to_workspace(
    workspace_id: int,
    bank_name: str = Form(...),
    initial_balance: float = Form(0.0),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    """Adiciona uma conta bancária diretamente a um Banco de Dados pelo painel /admin."""
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Banco de Dados não encontrado.")
        
    acc = Account(
        workspace_id=workspace_id,
        bank_name=bank_name.strip(),
        initial_balance=initial_balance,
        balance=initial_balance,
        user_id=ws.owner_id
    )
    db.add(acc)
    db.commit()
    return {"status": "success", "message": f"Conta '{bank_name}' adicionada ao Banco de Dados '{ws.name}'!"}


# --- APIS DE DADOS FINANCEIROS (ISOLAMENTO POR BANCO DE DADOS) ---

def get_default_bank_color(bank_name: str) -> str:
    name_lower = (bank_name or "").lower()
    if "nubank" in name_lower:
        return "#820ad1"
    elif "inter" in name_lower:
        return "#ff7a00"
    elif "caixa" in name_lower:
        return "#0066ae"
    elif "itau" in name_lower or "itaú" in name_lower:
        return "#ec7000"
    elif "bradesco" in name_lower:
        return "#cc092f"
    elif "santander" in name_lower:
        return "#ea1d25"
    elif "mercado" in name_lower or "pago" in name_lower:
        return "#009ee3"
    elif "c6" in name_lower:
        return "#242424"
    elif "bb" in name_lower or "brasil" in name_lower:
        return "#fcee00"
    return "#48b9c7"


@app.get("/api/data")
def get_dashboard_data(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Retorna contas e transações associadas ao Banco de Dados / Espaço ativo do usuário.
    Garante isolamento absoluto de dados entre logins.
    """
    workspace = get_user_workspace(current_user, db)
    user_accounts = db.query(Account).filter(Account.workspace_id == workspace.id).all()
    
    data = []
    total_balance = 0.0
    
    for account in user_accounts:
        txs = db.query(Transaction).filter(
            Transaction.account_id == account.id
        ).order_by(Transaction.date.desc()).all()
        
        recalculated_balance = (account.initial_balance or 0.0) + sum(t.amount for t in txs)
        account.balance = recalculated_balance
        db.add(account)
        
        total_balance += recalculated_balance
        
        data.append({
            "id": account.id,
            "bank_name": account.bank_name,
            "balance": recalculated_balance,
            "initial_balance": account.initial_balance or 0.0,
            "color": account.color or get_default_bank_color(account.bank_name),
            "transactions": [
                {
                    "id": t.id,
                    "date": t.date.strftime("%d/%m/%Y"),
                    "description": t.description,
                    "amount": t.amount,
                    "type": t.transaction_type,
                    "category": t.category,
                    "cost_type": t.cost_type or "variavel",
                    "installment_plan_id": t.installment_plan_id,
                    "installment_number": t.installment_number,
                    "installment_plan_name": t.installment_plan.name if t.installment_plan else None,
                    "installment_plan_total_parts": t.installment_plan.total_parts if t.installment_plan else None
                } for t in txs
            ]
        })
        
    db.commit()
    
    return {
        "accounts": data,
        "total_balance": total_balance,
        "user_name": current_user.full_name,
        "workspace_name": workspace.name,
        "db_identifier": workspace.db_identifier
    }


@app.post("/api/accounts")
def create_bank_account(
    bank_name: str = Form(...),
    initial_balance: float = Form(0.0),
    color: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Permite ao usuário cadastrar uma nova conta bancária no seu Banco de Dados ativo."""
    name_clean = bank_name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="O nome do banco não pode ser vazio.")
        
    workspace = get_user_workspace(current_user, db)
    default_brand = get_default_bank_color(name_clean)
    if color and color.strip() and color.strip().lower() != "#48b9c7":
        chosen_color = color.strip()
    else:
        chosen_color = default_brand
    if not chosen_color.startswith("#"):
        chosen_color = f"#{chosen_color}"
    
    account = Account(
        workspace_id=workspace.id,
        user_id=current_user.id,
        bank_name=name_clean,
        initial_balance=initial_balance,
        balance=initial_balance,
        color=chosen_color
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return {
        "status": "success",
        "message": f"Conta bancária '{name_clean}' adicionada com sucesso!",
        "account": {
            "id": account.id,
            "bank_name": account.bank_name,
            "balance": account.balance,
            "color": account.color
        }
    }


@app.post("/api/accounts/{account_id}/color")
def update_account_color(
    account_id: int,
    color: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Atualiza a cor de destaque (accent color) de uma conta bancária."""
    workspace = get_user_workspace(current_user, db)
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.workspace_id == workspace.id
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada no seu Banco de Dados.")
        
    clean_color = color.strip()
    if not clean_color.startswith("#"):
        clean_color = f"#{clean_color}"
    account.color = clean_color
    db.add(account)
    db.commit()
    return {
        "status": "success",
        "message": f"Cor do banco '{account.bank_name}' atualizada com sucesso!",
        "color": account.color
    }


@app.delete("/api/accounts/{account_id}")
def delete_bank_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Permite ao usuário excluir uma conta bancária do seu Banco de Dados ativo."""
    workspace = get_user_workspace(current_user, db)
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.workspace_id == workspace.id
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada no seu Banco de Dados.")
        
    db.delete(account)
    db.commit()
    return {"status": "success", "message": f"Conta '{account.bank_name}' excluída com sucesso."}


@app.post("/api/upload/{account_id}")
async def upload_statement_file(
    account_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Importa extrato OFX ou PDF para uma conta bancária do Banco de Dados ativo do usuário."""
    workspace = get_user_workspace(current_user, db)
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.workspace_id == workspace.id
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Conta bancária não encontrada no seu Banco de Dados.")
        
    file_bytes = await file.read()
    filename_lower = (file.filename or "").lower()
    is_pdf = filename_lower.endswith(".pdf") or file_bytes.startswith(b"%PDF")
    
    try:
        if is_pdf:
            transactions, ledger_balance = parse_and_import_pdf(file_content=file_bytes, account_id=account.id)
        else:
            transactions, ledger_balance = parse_and_import_ofx(file_content=file_bytes, account_id=account.id)
        
        added_count = 0
        duplicate_count = 0
        
        # Regras de custo fixo específicas deste Banco de Dados
        fixed_rules = {r.description.strip().upper() for r in db.query(FixedCostRule).filter(FixedCostRule.workspace_id == workspace.id).all()}
        
        for tx in transactions:
            if tx.amount < 0:
                desc_upper = tx.description.strip().upper()
                if desc_upper in fixed_rules:
                    tx.cost_type = "fixo"
                else:
                    tx.cost_type = "variavel"
            else:
                tx.cost_type = "variavel"
                
            try:
                db.add(tx)
                db.commit()
                added_count += 1
            except IntegrityError:
                db.rollback()
                duplicate_count += 1
                
        txs = db.query(Transaction).filter(Transaction.account_id == account.id).all()
        current_sum = sum(t.amount for t in txs)

        if ledger_balance is not None:
            account.initial_balance = ledger_balance - current_sum
            account.balance = ledger_balance
        else:
            account.balance = (account.initial_balance or 0.0) + current_sum

        db.add(account)
        db.commit()
        
        return {
            "status": "success",
            "message": f"Upload concluído. Adicionadas: {added_count}. Duplicadas ignoradas: {duplicate_count}.",
            "added": added_count,
            "duplicates": duplicate_count
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Erro ao processar arquivo: {str(e)}")


@app.post("/api/transaction/{transaction_id}/category")
def update_transaction_category(
    transaction_id: int,
    category: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Atualiza a categoria de uma transação no Banco de Dados ativo."""
    workspace = get_user_workspace(current_user, db)
    tx = db.query(Transaction).join(Account).filter(
        Transaction.id == transaction_id,
        Account.workspace_id == workspace.id
    ).first()
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
        
    tx.category = category
    db.add(tx)
    db.commit()
    return {"status": "success", "message": "Categoria atualizada com sucesso"}


@app.post("/api/transfers/detect-and-match")
def detect_and_match_transfers(
    apply: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cruza saídas e entradas entre contas diferentes do mesmo espaço ativo
    que possuem o mesmo valor e datas próximas (até 2 dias de diferença),
    categorizando-as automaticamente como 'Transferência entre Contas'.
    """
    workspace = get_user_workspace(current_user, db)
    accounts = db.query(Account).filter(Account.workspace_id == workspace.id).all()
    account_ids = [a.id for a in accounts]
    account_map = {a.id: a.bank_name for a in accounts}

    if len(account_ids) < 2:
        return {
            "status": "success",
            "matched_count": 0,
            "newly_matched": 0,
            "message": "É necessário ter pelo menos duas contas bancárias para cruzar transferências.",
            "matches": []
        }

    txs = db.query(Transaction).filter(
        Transaction.account_id.in_(account_ids)
    ).order_by(Transaction.date.asc()).all()

    outflows = [t for t in txs if t.amount < 0]
    inflows = [t for t in txs if t.amount > 0]

    matches = []
    matched_inflow_ids = set()
    matched_outflow_ids = set()
    TRANSFER_CAT = "Transferência entre Contas"

    for out_tx in outflows:
        if out_tx.id in matched_outflow_ids:
            continue
        
        target_amount = round(abs(out_tx.amount), 2)
        best_match = None
        best_diff_days = 999

        for in_tx in inflows:
            if in_tx.id in matched_inflow_ids:
                continue
            if out_tx.account_id == in_tx.account_id:
                continue
            
            in_amount = round(in_tx.amount, 2)
            if target_amount == in_amount:
                diff_days = abs((out_tx.date.date() - in_tx.date.date()).days)
                if diff_days <= 2 and diff_days < best_diff_days:
                    best_match = in_tx
                    best_diff_days = diff_days
                    if diff_days == 0:
                        break

        if best_match:
            matched_inflow_ids.add(best_match.id)
            matched_outflow_ids.add(out_tx.id)

            was_already_matched = (
                out_tx.category == TRANSFER_CAT and best_match.category == TRANSFER_CAT
            )

            if apply and not was_already_matched:
                out_tx.category = TRANSFER_CAT
                best_match.category = TRANSFER_CAT
                db.add(out_tx)
                db.add(best_match)

            matches.append({
                "amount": target_amount,
                "outflow_id": out_tx.id,
                "outflow_bank": account_map.get(out_tx.account_id, "Banco"),
                "outflow_desc": out_tx.description,
                "outflow_date": out_tx.date.strftime("%d/%m/%Y"),
                "inflow_id": best_match.id,
                "inflow_bank": account_map.get(best_match.account_id, "Banco"),
                "inflow_desc": best_match.description,
                "inflow_date": best_match.date.strftime("%d/%m/%Y"),
                "diff_days": best_diff_days,
                "already_matched": was_already_matched
            })

    if apply and matches:
        db.commit()

    newly_matched = sum(1 for m in matches if not m["already_matched"])

    return {
        "status": "success",
        "matched_count": len(matches),
        "newly_matched": newly_matched,
        "message": f"{newly_matched} nova(s) transferência(s) identificada(s) e categorizada(s) automaticamente." if newly_matched > 0 else (
            f"Todas as {len(matches)} transferências identificadas já estavam categorizadas." if len(matches) > 0 else "Nenhuma transferência cruzada entre contas encontrada no período."
        ),
        "matches": matches
    }


@app.post("/api/transaction/{transaction_id}/cost_type")
def update_transaction_cost_type(
    transaction_id: int,
    cost_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Atualiza o tipo de custo (fixo/variável) e memoriza a regra para o Banco de Dados ativo."""
    if cost_type not in ["fixo", "variavel"]:
        raise HTTPException(status_code=400, detail="Tipo de custo inválido")

    workspace = get_user_workspace(current_user, db)
    tx = db.query(Transaction).join(Account).filter(
        Transaction.id == transaction_id,
        Account.workspace_id == workspace.id
    ).first()
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    desc_normalized = tx.description.strip()
    desc_upper = desc_normalized.upper()

    account_ids = [a.id for a in workspace.accounts]

    if cost_type == "fixo":
        existing_rule = db.query(FixedCostRule).filter(
            FixedCostRule.description == desc_upper,
            FixedCostRule.workspace_id == workspace.id
        ).first()
        if not existing_rule:
            new_rule = FixedCostRule(description=desc_upper, workspace_id=workspace.id)
            db.add(new_rule)
        
        db.query(Transaction).filter(
            Transaction.account_id.in_(account_ids),
            Transaction.description == tx.description,
            Transaction.amount < 0
        ).update({Transaction.cost_type: "fixo"}, synchronize_session=False)
    
    else:
        db.query(FixedCostRule).filter(
            FixedCostRule.description == desc_upper,
            FixedCostRule.workspace_id == workspace.id
        ).delete(synchronize_session=False)
        
        db.query(Transaction).filter(
            Transaction.account_id.in_(account_ids),
            Transaction.description == tx.description,
            Transaction.amount < 0
        ).update({Transaction.cost_type: "variavel"}, synchronize_session=False)

    db.commit()
    return {"status": "success", "message": f"Tipo de custo atualizado para {cost_type} retrospectivamente."}


@app.get("/api/categories")
def get_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna todas as categorias cadastradas."""
    categories = db.query(Category).order_by(Category.name.asc()).all()
    return [c.name for c in categories]


@app.post("/api/category")
def add_category(
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cadastra uma nova categoria de transação."""
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="O nome da categoria não pode ser vazio")
        
    if len(name_clean) > 25:
        raise HTTPException(status_code=400, detail="Nome da categoria muito longo (máximo 25 caracteres)")

    existing = db.query(Category).filter(Category.name.like(name_clean)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Esta categoria já existe")
        
    new_cat = Category(name=name_clean)
    db.add(new_cat)
    db.commit()
    return {"status": "success", "message": f"Categoria '{name_clean}' cadastrada com sucesso!"}


# --- API DE PARCELAMENTOS (ISOLADA POR BANCO DE DADOS) ---

@app.get("/api/installments")
def get_installments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna todos os parcelamentos do Banco de Dados ativo."""
    workspace = get_user_workspace(current_user, db)
    plans = db.query(InstallmentPlan).filter(
        InstallmentPlan.workspace_id == workspace.id
    ).order_by(InstallmentPlan.id.desc()).all()
    
    result = []
    for plan in plans:
        txs = plan.transactions
        paid_parts = len(txs)
        paid_amount = sum(abs(t.amount) for t in txs)
        
        result.append({
            "id": plan.id,
            "name": plan.name,
            "total_amount": plan.total_amount,
            "installment_amount": plan.installment_amount,
            "total_parts": plan.total_parts,
            "category": plan.category,
            "active": plan.active,
            "paid_parts": paid_parts,
            "paid_amount": paid_amount,
            "remaining_parts": max(0, plan.total_parts - paid_parts),
            "remaining_amount": max(0.0, plan.total_amount - paid_amount)
        })
    return result


@app.post("/api/installments")
def create_installment(
    name: str = Form(...),
    total_amount: float = Form(...),
    installment_amount: float = Form(...),
    total_parts: int = Form(...),
    category: str = Form("Outros"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cadastra um novo plano de parcelamento no Banco de Dados ativo."""
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="O nome do parcelamento não pode ser vazio")
        
    workspace = get_user_workspace(current_user, db)
    new_plan = InstallmentPlan(
        workspace_id=workspace.id,
        name=name_clean,
        total_amount=total_amount,
        installment_amount=installment_amount,
        total_parts=total_parts,
        category=category,
        active=True
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    return {"status": "success", "message": f"Parcelamento '{name_clean}' criado com sucesso!", "id": new_plan.id}


@app.delete("/api/installments/{plan_id}")
def delete_installment(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Exclui um parcelamento do Banco de Dados ativo."""
    workspace = get_user_workspace(current_user, db)
    plan = db.query(InstallmentPlan).filter(
        InstallmentPlan.id == plan_id,
        InstallmentPlan.workspace_id == workspace.id
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Parcelamento não encontrado")
        
    db.query(Transaction).filter(Transaction.installment_plan_id == plan_id).update({
        Transaction.installment_plan_id: None,
        Transaction.installment_number: None
    }, synchronize_session=False)
    
    db.delete(plan)
    db.commit()
    return {"status": "success", "message": "Parcelamento excluído com sucesso"}


@app.post("/api/transaction/{transaction_id}/link")
def link_transaction_to_installment(
    transaction_id: int,
    installment_plan_id: int = Form(...),
    installment_number: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Vincula uma transação real a um parcelamento no Banco de Dados ativo."""
    workspace = get_user_workspace(current_user, db)
    tx = db.query(Transaction).join(Account).filter(
        Transaction.id == transaction_id,
        Account.workspace_id == workspace.id
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
        
    plan = db.query(InstallmentPlan).filter(
        InstallmentPlan.id == installment_plan_id,
        InstallmentPlan.workspace_id == workspace.id
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Parcelamento não encontrado")
        
    if installment_number < 1 or installment_number > plan.total_parts:
        raise HTTPException(
            status_code=400, 
            detail=f"Número da parcela inválido. Deve ser entre 1 e {plan.total_parts}."
        )
        
    existing_link = db.query(Transaction).filter(
        Transaction.installment_plan_id == installment_plan_id,
        Transaction.installment_number == installment_number,
        Transaction.id != transaction_id
    ).first()
    if existing_link:
        raise HTTPException(
            status_code=400, 
            detail=f"A parcela {installment_number} já está vinculada à transação '{existing_link.description}'."
        )
        
    tx.installment_plan_id = installment_plan_id
    tx.installment_number = installment_number
    if tx.category == "Outros" and plan.category != "Outros":
        tx.category = plan.category
        
    db.add(tx)
    db.commit()
    return {"status": "success", "message": f"Transação vinculada com sucesso à parcela {installment_number}/{plan.total_parts}."}


@app.post("/api/transaction/{transaction_id}/unlink")
def unlink_transaction_from_installment(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove o vínculo de uma transação de qualquer parcelamento."""
    workspace = get_user_workspace(current_user, db)
    tx = db.query(Transaction).join(Account).filter(
        Transaction.id == transaction_id,
        Account.workspace_id == workspace.id
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
        
    tx.installment_plan_id = None
    tx.installment_number = None
    db.add(tx)
    db.commit()
    return {"status": "success", "message": "Transação desvinculada com sucesso."}


# --- API DE RECEITAS FUTURAS (ISOLADA POR BANCO DE DADOS) ---

@app.get("/api/future-incomes")
def get_future_incomes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lista todas as receitas futuras do Banco de Dados ativo."""
    workspace = get_user_workspace(current_user, db)
    incomes = db.query(FutureIncome).filter(
        FutureIncome.workspace_id == workspace.id
    ).order_by(FutureIncome.id.desc()).all()
    
    return [
        {
            "id": inc.id,
            "description": inc.description,
            "amount": inc.amount,
            "is_recurrent": inc.is_recurrent,
            "receive_day": inc.receive_day,
            "start_date": inc.start_date.strftime("%Y-%m-%d")
        } for inc in incomes
    ]


@app.post("/api/future-incomes")
def create_future_income(
    description: str = Form(...),
    amount: float = Form(...),
    is_recurrent: bool = Form(...),
    receive_day: int = Form(5),
    start_date: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cadastra uma nova receita futura estimada no Banco de Dados ativo."""
    desc_clean = description.strip()
    if not desc_clean:
        raise HTTPException(status_code=400, detail="A descrição não pode ser vazia")
        
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use AAAA-MM-DD.")
        
    workspace = get_user_workspace(current_user, db)
    new_inc = FutureIncome(
        workspace_id=workspace.id,
        description=desc_clean,
        amount=amount,
        is_recurrent=is_recurrent,
        receive_day=receive_day,
        start_date=dt_start
    )
    db.add(new_inc)
    db.commit()
    return {"status": "success", "message": f"Receita futura '{desc_clean}' cadastrada com sucesso!"}


@app.delete("/api/future-incomes/{income_id}")
def delete_future_income(
    income_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Exclui uma receita futura do Banco de Dados ativo."""
    workspace = get_user_workspace(current_user, db)
    inc = db.query(FutureIncome).filter(
        FutureIncome.id == income_id,
        FutureIncome.workspace_id == workspace.id
    ).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Receita futura não encontrada")
    db.delete(inc)
    db.commit()
    return {"status": "success", "message": "Receita futura excluída com sucesso"}


# --- API DE METAS FINANCEIRAS (ISOLADA POR BANCO DE DADOS) ---

@app.get("/api/financial-goals")
def get_financial_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lista todas as metas do Banco de Dados ativo."""
    workspace = get_user_workspace(current_user, db)
    goals = db.query(FinancialGoal).filter(
        FinancialGoal.workspace_id == workspace.id
    ).order_by(FinancialGoal.target_date.asc()).all()
    
    return [
        {
            "id": goal.id,
            "name": goal.name,
            "target_amount": goal.target_amount,
            "target_date": goal.target_date.strftime("%Y-%m-%d"),
            "category": goal.category,
            "active": goal.active
        } for goal in goals
    ]


@app.post("/api/financial-goals")
def create_financial_goal(
    name: str = Form(...),
    target_amount: float = Form(...),
    target_date: str = Form(...),
    category: str = Form("Lazer"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cadastra um novo objetivo financeiro no Banco de Dados ativo."""
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="O nome do objetivo não pode ser vazio")
        
    try:
        dt_target = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use AAAA-MM-DD.")
        
    workspace = get_user_workspace(current_user, db)
    new_goal = FinancialGoal(
        workspace_id=workspace.id,
        name=name_clean,
        target_amount=target_amount,
        target_date=dt_target,
        category=category,
        active=True
    )
    db.add(new_goal)
    db.commit()
    return {"status": "success", "message": f"Objetivo '{name_clean}' cadastrado com sucesso!"}


@app.delete("/api/financial-goals/{goal_id}")
def delete_financial_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Exclui um objetivo financeiro do Banco de Dados ativo."""
    workspace = get_user_workspace(current_user, db)
    goal = db.query(FinancialGoal).filter(
        FinancialGoal.id == goal_id,
        FinancialGoal.workspace_id == workspace.id
    ).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo financeiro não encontrado")
    db.delete(goal)
    db.commit()
    return {"status": "success", "message": "Objetivo financeiro excluído com sucesso"}


# --- ENGINE DO SIMULADOR E PROJEÇÕES (ISOLADO POR BANCO DE DADOS) ---

@app.get("/api/simulation/projection")
def get_simulation_projection(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retorna projeção de saldo e gastos computada exclusivamente para o Banco de Dados ativo.
    """
    workspace = get_user_workspace(current_user, db)
    accounts = db.query(Account).filter(Account.workspace_id == workspace.id).all()
    account_ids = [acc.id for acc in accounts]
    
    # 1. Calcula saldo consolidado atual
    current_balance = 0.0
    for acc in accounts:
        txs = db.query(Transaction).filter(Transaction.account_id == acc.id).all()
        current_balance += (acc.initial_balance or 0.0) + sum(t.amount for t in txs)
        
    # 2. Calcula média real de gastos dos últimos 90 dias
    ninety_days_ago = datetime.utcnow() - timedelta(days=90)
    txs_past_90_days = db.query(Transaction).filter(
        Transaction.account_id.in_(account_ids),
        Transaction.amount < 0,
        Transaction.date >= ninety_days_ago,
        Transaction.category.notin_(["Pagamento de Fatura", "Transferência entre Contas"])
    ).all() if account_ids else []
    
    total_past_90_days = sum(abs(t.amount) for t in txs_past_90_days)
    avg_expenses = total_past_90_days / 3.0
    
    if avg_expenses == 0 and account_ids:
        all_expenses = db.query(Transaction).filter(
            Transaction.account_id.in_(account_ids),
            Transaction.amount < 0, 
            Transaction.category.notin_(["Pagamento de Fatura", "Transferência entre Contas"])
        ).all()
        if all_expenses:
            first_tx = db.query(Transaction).filter(Transaction.account_id.in_(account_ids)).order_by(Transaction.date.asc()).first()
            diff_days = (datetime.utcnow() - first_tx.date).days if first_tx else 30
            months = max(1.0, diff_days / 30.4)
            avg_expenses = sum(abs(t.amount) for t in all_expenses) / months
        else:
            avg_expenses = 2000.0
    elif not account_ids:
        avg_expenses = 2000.0
            
    # 3. Calcula projeção de parcelamentos para os próximos 24 meses
    projection_months = 24
    installments_projection = [0.0] * projection_months
    
    active_plans = db.query(InstallmentPlan).filter(
        InstallmentPlan.workspace_id == workspace.id,
        InstallmentPlan.active == True
    ).all()
    for plan in active_plans:
        paid_parts = len(plan.transactions)
        remaining_parts = plan.total_parts - paid_parts
        for m in range(min(projection_months, max(0, remaining_parts))):
            installments_projection[m] += plan.installment_amount
            
    return {
        "current_balance": current_balance,
        "average_expenses": round(avg_expenses, 2),
        "installments_projection": [round(val, 2) for val in installments_projection]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
