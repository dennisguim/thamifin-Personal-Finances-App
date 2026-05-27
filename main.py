from fastapi import FastAPI, Request, Depends, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from a2wsgi import ASGIMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from typing import Optional
import os
from dotenv import load_dotenv

# Importações dos nossos módulos
from database import init_db, get_db, User, Account, Transaction, FixedCostRule, Category, InstallmentPlan, FutureIncome, FinancialGoal, SessionLocal
from auth import get_password_hash, verify_password, create_access_token, get_current_user
from ofx_parser import parse_and_import_ofx

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Inicializa o banco de dados SQLite (cria tabelas)
init_db()

def seed_users():
    db = SessionLocal()
    try:
        # Busca credenciais das variáveis de ambiente
        user1_email = os.getenv("USER1_EMAIL")
        user1_name = os.getenv("USER1_NAME")
        user1_pass = os.getenv("USER1_PASSWORD")

        user2_email = os.getenv("USER2_EMAIL")
        user2_name = os.getenv("USER2_NAME")
        user2_pass = os.getenv("USER2_PASSWORD")

        if not user1_email or not user1_pass:
            print("Pulei seeding de usuários: Variáveis de ambiente (USER1_EMAIL/PASS) não configuradas.")
            return

        def create_or_update_user(email, name, password):
            if not email: return None
            password_hash = get_password_hash(password)
            user = db.query(User).filter(User.email == email).first()
            if not user:
                user = User(email=email, full_name=name or email, hashed_password=password_hash)
                db.add(user)
                print(f"Usuário {email} criado.")
            else:
                user.full_name = name or user.full_name
                user.hashed_password = password_hash
                print(f"Usuário {email} atualizado.")
            return user

        u1 = create_or_update_user(user1_email, user1_name, user1_pass)
        u2 = create_or_update_user(user2_email, user2_name, user2_pass)
        
        db.commit()
        
        # 3. Excluir outros usuários que não estão no .env (limpeza de segurança)
        allowed_emails = [e for e in [user1_email, user2_email] if e]
        other_users = db.query(User).filter(~User.email.in_(allowed_emails)).all()
        for u in other_users:
            print(f"Removendo usuário não autorizado: {u.email}")
            db.delete(u)
        db.commit()
        
        # 4. Criar contas padrão se o banco estiver vazio
        if db.query(Account).count() == 0 and u1:
            accounts = [
                Account(user_id=u1.id, bank_name="Nubank", balance=0.0),
                Account(user_id=u1.id, bank_name="Banco Inter", balance=0.0),
                Account(user_id=u1.id, bank_name="Caixa", balance=0.0)
            ]
            db.add_all(accounts)
            db.commit()
            print("Contas bancárias padrão semeadas.")
            
    except Exception as e:
        db.rollback()
        print("Erro durante seeding de usuários:", e)
    finally:
        db.close()

# Executa seeding de usuários e contas
seed_users()

# Inicializa o app FastAPI
app = FastAPI(title="ThamiFin")

# Middleware para compatibilidade com PythonAnywhere (WSGI)
wsgi_app = ASGIMiddleware(app)

# Define o diretório base para caminhos absolutos (importante para PythonAnywhere)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Monta arquivos estáticos (CSS / JS) e templates HTML usando caminhos absolutos
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
    return templates.TemplateResponse(request=request, name="login.html")


@app.post("/auth/register")
def register(
    db: Session = Depends(get_db),
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    """Cadastra um novo usuário no banco SQLite."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="O cadastro público está desativado por segurança."
    )


@app.post("/auth/login")
def login(
    response: RedirectResponse,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...)
):
    """Efetua a validação do login e injeta o Cookie JWT HTTP-Only."""
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        # Para telas HTML tradicionais, retorna erro por redirecionamento simples
        return RedirectResponse(url="/login?error=true", status_code=303)
        
    # Criação do token de sessão JWT válido por 24 horas
    access_token = create_access_token(data={"sub": user.email})
    
    # Configura o cookie seguro HTTP-Only contendo o JWT
    redirect = RedirectResponse(url="/dashboard", status_code=303)
    redirect.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=86400,  # 24 horas em segundos
        samesite="lax",
        secure=False  # Mude para True se utilizar HTTPS em produção!
    )
    return redirect


@app.get("/auth/logout")
def logout():
    """Remove a sessão do usuário deletando o cookie do JWT."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response


# --- DASHBOARD & ENDPOINTS INTERNOS ---

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página principal do dashboard se estiver autenticado ou redireciona para login."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html", 
        context={"user": current_user, "active_page": "dashboard"}
    )


@app.get("/receitas", response_class=HTMLResponse)
def receitas_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de receitas (realizadas e estimadas)."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    return templates.TemplateResponse(
        request=request,
        name="receitas.html", 
        context={"user": current_user, "active_page": "receitas"}
    )


@app.get("/custos", response_class=HTMLResponse)
def custos_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de custos fixos e variáveis."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    return templates.TemplateResponse(
        request=request,
        name="custos.html", 
        context={"user": current_user, "active_page": "custos"}
    )


@app.get("/graficos", response_class=HTMLResponse)
def graficos_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de gráficos interativos."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    return templates.TemplateResponse(
        request=request,
        name="graficos.html", 
        context={"user": current_user, "active_page": "graficos"}
    )


@app.get("/api/data")
def get_dashboard_data(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    """
    Retorna contas e transações associadas ao usuário atualizado em formato JSON.
    Recalcula os saldos com base no saldo real de receitas e despesas.
    """
    user_accounts = db.query(Account).all()
    
    data = []
    total_balance = 0.0
    
    for account in user_accounts:
        # Busca transações para esta conta ordenadas pelas mais recentes
        txs = db.query(Transaction).filter(
            Transaction.account_id == account.id
        ).order_by(Transaction.date.desc()).all()
        
        # Recalcula o saldo real somando o saldo inicial e as movimentações
        recalculated_balance = (account.initial_balance or 0.0) + sum(t.amount for t in txs)
        account.balance = recalculated_balance
        db.add(account)
        
        total_balance += recalculated_balance
        
        data.append({
            "id": account.id,
            "bank_name": account.bank_name,
            "balance": recalculated_balance,
            "initial_balance": account.initial_balance or 0.0,
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
        
    db.commit() # Salva saldos atualizados
    
    return {
        "accounts": data,
        "total_balance": total_balance,
        "user_name": current_user.full_name
    }


@app.post("/api/upload/{account_id}")
async def upload_ofx_file(
    account_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Recebe um arquivo OFX do banco correspondente, faz o parser inteligente, 
    adiciona transações e trata duplicidades de forma transparente e robusta.
    """
    # Verifica se a conta realmente existe
    account = db.query(Account).filter(
        Account.id == account_id
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
        
    # Lê os bytes enviados do arquivo OFX
    file_bytes = await file.read()
    
    try:
        # Faz o parse das transações com hashes gerados e captura o saldo atual do OFX
        transactions, ledger_balance = parse_and_import_ofx(file_content=file_bytes, account_id=account.id)
        
        added_count = 0
        duplicate_count = 0
        
        # Carrega regras de custo fixo memorizadas do usuário
        fixed_rules = {r.description.strip().upper() for r in db.query(FixedCostRule).all()}
        
        # Insere transações de forma individual, ignorando colisões de hash
        for tx in transactions:
            # Se for despesa, classifica baseando-se nas regras aprendidas
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
                db.commit()  # Tenta salvar no SQLite física
                added_count += 1
            except IntegrityError:
                db.rollback()  # Desfaz se houver colisão de hash (duplicata detectada!)
                duplicate_count += 1
                
        # Força o recálculo do saldo da conta
        txs = db.query(Transaction).filter(Transaction.account_id == account.id).all()
        current_sum = sum(t.amount for t in txs)

        # Se o OFX trouxe um saldo (ledger_balance), ajustamos o initial_balance 
        # para que: initial_balance + current_sum == ledger_balance
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
    """Permite alterar manualmente a categoria de uma despesa no dashboard."""
    tx = db.query(Transaction).filter(
        Transaction.id == transaction_id
    ).first()
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
        
    tx.category = category
    db.add(tx)
    db.commit()
    return {"status": "success", "message": "Categoria atualizada com sucesso"}


@app.post("/api/transaction/{transaction_id}/cost_type")
def update_transaction_cost_type(
    transaction_id: int,
    cost_type: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Atualiza o tipo de custo (fixo ou variavel) de uma transação e aprende/esquece a regra.
    Atualiza retrospectivamente todas as transações com a mesma descrição.
    """
    if cost_type not in ["fixo", "variavel"]:
        raise HTTPException(status_code=400, detail="Tipo de custo inválido")

    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    desc_normalized = tx.description.strip()
    desc_upper = desc_normalized.upper()

    # Se for custo fixo, registra regra e atualiza retrospectivamente
    if cost_type == "fixo":
        existing_rule = db.query(FixedCostRule).filter(FixedCostRule.description == desc_upper).first()
        if not existing_rule:
            new_rule = FixedCostRule(description=desc_upper)
            db.add(new_rule)
        
        # Atualiza todas as transações com a mesma descrição
        db.query(Transaction).filter(
            Transaction.description == tx.description,
            Transaction.amount < 0
        ).update({Transaction.cost_type: "fixo"}, synchronize_session=False)
    
    else:  # 'variavel'
        # Remove a regra se existir
        db.query(FixedCostRule).filter(FixedCostRule.description == desc_upper).delete(synchronize_session=False)
        
        # Atualiza todas as transações correspondentes de volta para variavel
        db.query(Transaction).filter(
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
    """Retorna todas as categorias cadastradas em ordem alfabética."""
    categories = db.query(Category).order_by(Category.name.asc()).all()
    return [c.name for c in categories]


@app.post("/api/category")
def add_category(
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cadastra manualmente uma nova categoria de transação no banco."""
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="O nome da categoria não pode ser vazio")
        
    # Limita caracteres especiais para evitar quebras visuais
    if len(name_clean) > 25:
        raise HTTPException(status_code=400, detail="Nome da categoria muito longo (máximo 25 caracteres)")

    # Verifica se já existe (case-insensitive para evitar duplicidade idêntica)
    existing = db.query(Category).filter(Category.name.like(name_clean)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Esta categoria já existe")
        
    new_cat = Category(name=name_clean)
    db.add(new_cat)
    db.commit()
    return {"status": "success", "message": f"Categoria '{name_clean}' cadastrada com sucesso!"}


@app.get("/parcelamentos", response_class=HTMLResponse)
def parcelamentos_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de parcelamentos."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    return templates.TemplateResponse(
        request=request,
        name="parcelamentos.html", 
        context={"user": current_user, "active_page": "parcelamentos"}
    )


@app.get("/api/installments")
def get_installments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna todos os parcelamentos com dados computados de pagamento."""
    plans = db.query(InstallmentPlan).order_by(InstallmentPlan.id.desc()).all()
    result = []
    for plan in plans:
        # Busca transações associadas a este plano
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
    """Cadastra um novo plano de parcelamento."""
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="O nome do parcelamento não pode ser vazio")
        
    new_plan = InstallmentPlan(
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
    """Exclui um parcelamento, desvinculando as transações associadas."""
    plan = db.query(InstallmentPlan).filter(InstallmentPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Parcelamento não encontrado")
        
    # Desvincula transações associadas
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
    """Vincula uma transação real a um parcelamento."""
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
        
    plan = db.query(InstallmentPlan).filter(InstallmentPlan.id == installment_plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Parcelamento não encontrado")
        
    if installment_number < 1 or installment_number > plan.total_parts:
        raise HTTPException(
            status_code=400, 
            detail=f"Número da parcela inválido. Deve ser entre 1 e {plan.total_parts}."
        )
        
    # Verifica se já existe outra transação vinculada com este mesmo número de parcela
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
    # Se a transação estiver na categoria padrão, atualiza para a categoria do plano
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
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transação não encontrada")
        
    tx.installment_plan_id = None
    tx.installment_number = None
    db.add(tx)
    db.commit()
    return {"status": "success", "message": "Transação desvinculada com sucesso."}


@app.get("/metas", response_class=HTMLResponse)
def metas_page(request: Request, db: Session = Depends(get_db)):
    """Renderiza a página de metas e projeções."""
    try:
        current_user = get_current_user(request, db)
    except HTTPException:
        return RedirectResponse(url="/login", status_code=303)
        
    return templates.TemplateResponse(
        request=request,
        name="metas.html", 
        context={"user": current_user, "active_page": "metas"}
    )


# --- API DE RECEITAS FUTURAS ---

@app.get("/api/future-incomes")
def get_future_incomes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lista todas as receitas futuras estimadas."""
    incomes = db.query(FutureIncome).order_by(FutureIncome.id.desc()).all()
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
    """Cadastra uma nova receita futura estimada."""
    desc_clean = description.strip()
    if not desc_clean:
        raise HTTPException(status_code=400, detail="A descrição não pode ser vazia")
        
    try:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use AAAA-MM-DD.")
        
    new_inc = FutureIncome(
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
    """Exclui uma receita futura cadastrada."""
    inc = db.query(FutureIncome).filter(FutureIncome.id == income_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Receita futura não encontrada")
    db.delete(inc)
    db.commit()
    return {"status": "success", "message": "Receita futura excluída com sucesso"}


# --- API DE METAS FINANCEIRAS ---

@app.get("/api/financial-goals")
def get_financial_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lista todas as metas cadastradas."""
    goals = db.query(FinancialGoal).order_by(FinancialGoal.target_date.asc()).all()
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
    """Cadastra um novo objetivo financeiro."""
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="O nome do objetivo não pode ser vazio")
        
    try:
        dt_target = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use AAAA-MM-DD.")
        
    new_goal = FinancialGoal(
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
    """Exclui um objetivo financeiro cadastrado."""
    goal = db.query(FinancialGoal).filter(FinancialGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Objetivo financeiro não encontrado")
    db.delete(goal)
    db.commit()
    return {"status": "success", "message": "Objetivo financeiro excluído com sucesso"}


# --- ENGINE DO SIMULADOR E PROJEÇÕES ---

@app.get("/api/simulation/projection")
def get_simulation_projection(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retorna dados unificados para rodar a projeção:
    - Saldo consolidado atual das contas.
    - Média mensal histórica de gastos reais (últimos 90 dias).
    - Despesas agendadas de parcelamentos ativos mês a mês pelos próximos 24 meses.
    """
    # 1. Calcula saldo consolidado atual
    accounts = db.query(Account).all()
    current_balance = 0.0
    for acc in accounts:
        txs = db.query(Transaction).filter(Transaction.account_id == acc.id).all()
        current_balance += (acc.initial_balance or 0.0) + sum(t.amount for t in txs)
        
    # 2. Calcula média real de gastos dos últimos 90 dias (ignora faturas)
    ninety_days_ago = datetime.utcnow() - timedelta(days=90)
    txs_past_90_days = db.query(Transaction).filter(
        Transaction.amount < 0,
        Transaction.date >= ninety_days_ago,
        Transaction.category != "Pagamento de Fatura"
    ).all()
    
    total_past_90_days = sum(abs(t.amount) for t in txs_past_90_days)
    avg_expenses = total_past_90_days / 3.0
    
    if avg_expenses == 0:
        # Fallback caso não existam gastos nos últimos 90 dias
        all_expenses = db.query(Transaction).filter(
            Transaction.amount < 0, 
            Transaction.category != "Pagamento de Fatura"
        ).all()
        if all_expenses:
            first_tx = db.query(Transaction).order_by(Transaction.date.asc()).first()
            diff_days = (datetime.utcnow() - first_tx.date).days
            months = max(1.0, diff_days / 30.4)
            avg_expenses = sum(abs(t.amount) for t in all_expenses) / months
        else:
            avg_expenses = 2000.0 # Padrão neutro
            
    # 3. Calcula projeção de parcelamentos para os próximos 24 meses
    projection_months = 24
    installments_projection = [0.0] * projection_months
    
    active_plans = db.query(InstallmentPlan).filter(InstallmentPlan.active == True).all()
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
    # Executa o servidor local na porta 8000
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
