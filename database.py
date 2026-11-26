import os
import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint, event, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Define o diretório base para caminhos absolutos (importante para PythonAnywhere)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'finance.db')}"

# Engine do SQLite. Nota: 'check_same_thread=False' é necessário para o FastAPI rodar assíncrono.
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Habilitar suporte a chaves estrangeiras no SQLite (desativado por padrão)
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# Sessão e Base Declarativa
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELOS DE DADOS MULTI-TENANT (PLATAFORMA) ---

class Workspace(Base):
    """
    Representa o Banco de Dados / Espaço Financeiro de um usuário ou grupo.
    Cada espaço contém suas próprias contas bancárias, transações, parcelamentos e metas.
    """
    __tablename__ = "workspaces"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)                                  # Ex: "Espaço Pessoal Dennis", "Finanças Família"
    db_identifier = Column(String, unique=True, index=True, nullable=False) # Ex: "db_workspace_1"
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relações
    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="workspace", cascade="all, delete-orphan")
    installment_plans = relationship("InstallmentPlan", back_populates="workspace", cascade="all, delete-orphan")
    future_incomes = relationship("FutureIncome", back_populates="workspace", cascade="all, delete-orphan")
    financial_goals = relationship("FinancialGoal", back_populates="workspace", cascade="all, delete-orphan")
    fixed_rules = relationship("FixedCostRule", back_populates="workspace", cascade="all, delete-orphan")
    planned_expenses = relationship("PlannedExpense", back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceMember(Base):
    """
    Tabela de associação que define quais contas (logins) têm acesso a qual Banco de Dados / Espaço.
    """
    __tablename__ = "workspace_members"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, default="member")  # 'owner', 'member', 'admin'
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="workspace_memberships")
    
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),)


class User(Base):
    """Representa a Conta / Login do Usuário no sistema."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    current_workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relações
    workspace_memberships = relationship("WorkspaceMember", back_populates="user", cascade="all, delete-orphan")
    accounts = relationship("Account", back_populates="owner")
    
    def get_active_workspace(self, db):
        """Retorna o espaço financeiro atualmente ativo para o usuário."""
        if self.current_workspace_id:
            ws = db.query(Workspace).filter(Workspace.id == self.current_workspace_id).first()
            if ws:
                return ws
        membership = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == self.id).first()
        if membership:
            return membership.workspace
        return None


class Account(Base):
    """Representa uma Conta Bancária (Ex: Nubank, Inter, Caixa) vinculada a um Banco de Dados / Espaço."""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    bank_name = Column(String, nullable=False)  # Nubank, Banco Inter, Caixa, etc.
    account_number = Column(String, nullable=True)
    color = Column(String, default="#48b9c7", nullable=True)
    initial_balance = Column(Float, default=0.0)
    balance = Column(Float, default=0.0)
    
    # Relações
    workspace = relationship("Workspace", back_populates="accounts")
    owner = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")


class InstallmentPlan(Base):
    """Representa uma compra parcelada ativa vinculada a um Banco de Dados."""
    __tablename__ = "installment_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True)
    name = Column(String, nullable=False)
    total_amount = Column(Float, nullable=False)
    installment_amount = Column(Float, nullable=False)
    total_parts = Column(Integer, nullable=False)
    category = Column(String, default="Outros")
    active = Column(Boolean, default=True)
    
    workspace = relationship("Workspace", back_populates="installment_plans")
    transactions = relationship("Transaction", back_populates="installment_plan")


class Transaction(Base):
    """Representa uma transação financeira importada."""
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    transaction_type = Column(String, nullable=False)
    category = Column(String, default="Outros")
    cost_type = Column(String, default="variavel")
    
    fitid = Column(String, nullable=True)
    hash = Column(String, unique=True, nullable=False, index=True)
    
    installment_plan_id = Column(Integer, ForeignKey("installment_plans.id", ondelete="SET NULL"), nullable=True)
    installment_number = Column(Integer, nullable=True)
    
    account = relationship("Account", back_populates="transactions")
    installment_plan = relationship("InstallmentPlan", back_populates="transactions")


class FixedCostRule(Base):
    """Regra de custo fixo memorizada para o Banco de Dados."""
    __tablename__ = "fixed_cost_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True)
    description = Column(String, nullable=False, index=True)
    
    workspace = relationship("Workspace", back_populates="fixed_rules")


class Category(Base):
    """Representa uma categoria de transação no sistema."""
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


class FutureIncome(Base):
    """Receita futura estimada vinculada ao Banco de Dados."""
    __tablename__ = "future_incomes"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    is_recurrent = Column(Boolean, default=True)
    receive_day = Column(Integer, default=5)
    start_date = Column(DateTime, default=datetime.utcnow)
    
    workspace = relationship("Workspace", back_populates="future_incomes")


class PlannedExpense(Base):
    """
    Gasto ou despesa prevista para o planejamento orçamentário futuro.
    Pode ser fixo ou variável, recorrente (alastrando para os meses seguintes) ou eventual/pontual.
    """
    __tablename__ = "planned_expenses"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, default="Outros")
    cost_type = Column(String, default="fixo") # 'fixo' ou 'variavel'
    is_recurrent = Column(Boolean, default=True) # Se True, alastra para todos os meses futuros
    start_date = Column(DateTime, default=datetime.utcnow) # Mês/Ano de início (ou do evento pontual)
    end_date = Column(DateTime, nullable=True) # Opcional: até quando se repete
    due_day = Column(Integer, default=10) # Dia previsto do gasto
    created_at = Column(DateTime, default=datetime.utcnow)
    
    workspace = relationship("Workspace", back_populates="planned_expenses")


class FinancialGoal(Base):
    """Meta financeira vinculada ao Banco de Dados."""
    __tablename__ = "financial_goals"
    
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    target_date = Column(DateTime, nullable=False)
    category = Column(String, default="Lazer")
    active = Column(Boolean, default=True)
    
    workspace = relationship("Workspace", back_populates="financial_goals")


class RegistrationVerification(Base):
    """
    Armazena solicitações de criação de conta pendentes de confirmação
    por código enviado para drinaldim@gmail.com.
    """
    __tablename__ = "registration_verifications"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    code = Column(String, nullable=False)
    target_email = Column(String, default="drinaldim@gmail.com")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    verified = Column(Boolean, default=False)


# --- GERENCIAMENTO DO BANCO E MIGRAÇÕES ---

def ensure_user_workspace(user: User, db) -> Workspace:
    """
    Garante que o usuário tenha um Banco de Dados / Espaço próprio configurado.
    Se não tiver, cria um espaço com contas bancárias padrão (Nubank, Inter, Caixa).
    """
    # 1. Verifica se já possui algum vínculo
    membership = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user.id).first()
    if membership:
        ws = db.query(Workspace).filter(Workspace.id == membership.workspace_id).first()
        if ws:
            if not user.current_workspace_id:
                user.current_workspace_id = ws.id
                db.add(user)
                db.commit()
            return ws

    # 2. Cria um novo espaço financeiro exclusivo para este usuário
    ident = f"db_{user.id}_{uuid.uuid4().hex[:6]}"
    first_name = user.full_name.split()[0] if user.full_name else "Usuário"
    workspace_name = f"Espaço Financeiro ({first_name})"
    ws = Workspace(name=workspace_name, db_identifier=ident, owner_id=user.id)
    db.add(ws)
    db.commit()
    db.refresh(ws)

    # 3. Vincula o usuário como Proprietário (owner)
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner")
    db.add(member)
    user.current_workspace_id = ws.id
    db.add(user)

    # 4. Cria as contas bancárias padrão para o espaço do usuário
    default_accounts = [
        Account(workspace_id=ws.id, user_id=user.id, bank_name="Nubank", balance=0.0),
        Account(workspace_id=ws.id, user_id=user.id, bank_name="Banco Inter", balance=0.0),
        Account(workspace_id=ws.id, user_id=user.id, bank_name="Caixa", balance=0.0),
    ]
    db.add_all(default_accounts)
    db.commit()
    db.refresh(ws)
    return ws


def get_user_workspace(user: User, db) -> Workspace:
    """
    Retorna o workspace ativo do usuário logado.
    Garante que o workspace seja válido e o usuário tenha acesso.
    """
    if user.current_workspace_id:
        membership = db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.workspace_id == user.current_workspace_id
        ).first()
        if membership:
            ws = db.query(Workspace).filter(Workspace.id == user.current_workspace_id).first()
            if ws:
                return ws

    return ensure_user_workspace(user, db)


def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Migrações automáticas simples para colunas adicionadas
    with engine.connect() as conn:
        def table_has_col(table, col):
            cursor = conn.exec_driver_sql(f"PRAGMA table_info({table})")
            return col in [row[1] for row in cursor.fetchall()]

        if not table_has_col("users", "is_admin"):
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
        if not table_has_col("users", "current_workspace_id"):
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN current_workspace_id INTEGER REFERENCES workspaces(id) ON DELETE SET NULL")
        if not table_has_col("users", "created_at"):
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN created_at DATETIME")
            
        if not table_has_col("accounts", "workspace_id"):
            conn.exec_driver_sql("ALTER TABLE accounts ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE")
        if not table_has_col("accounts", "color"):
            conn.exec_driver_sql("ALTER TABLE accounts ADD COLUMN color VARCHAR DEFAULT '#48b9c7'")
            
        if not table_has_col("transactions", "cost_type"):
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN cost_type VARCHAR DEFAULT 'variavel'")
        if not table_has_col("transactions", "installment_plan_id"):
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN installment_plan_id INTEGER REFERENCES installment_plans(id) ON DELETE SET NULL")
        if not table_has_col("transactions", "installment_number"):
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN installment_number INTEGER")
            
        if not table_has_col("installment_plans", "workspace_id"):
            conn.exec_driver_sql("ALTER TABLE installment_plans ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE")
        if not table_has_col("future_incomes", "workspace_id"):
            conn.exec_driver_sql("ALTER TABLE future_incomes ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE")
        if not table_has_col("financial_goals", "workspace_id"):
            conn.exec_driver_sql("ALTER TABLE financial_goals ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE")
        if not table_has_col("fixed_cost_rules", "workspace_id"):
            conn.exec_driver_sql("ALTER TABLE fixed_cost_rules ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE")
        if not table_has_col("future_incomes", "category"):
            conn.exec_driver_sql("ALTER TABLE future_incomes ADD COLUMN category VARCHAR DEFAULT 'Receita'")

    # Inicialização de dados
    db = SessionLocal()
    try:
        # Migra dados legados sem workspace se existirem
        orphaned_accounts = db.query(Account).filter(Account.workspace_id == None).all()
        if orphaned_accounts:
            # Cria ou busca workspace principal
            main_ws = db.query(Workspace).filter(Workspace.db_identifier == "db_space_principal").first()
            if not main_ws:
                main_ws = Workspace(name="Espaço Principal", db_identifier="db_space_principal")
                db.add(main_ws)
                db.commit()
                db.refresh(main_ws)
                
            for acc in orphaned_accounts:
                acc.workspace_id = main_ws.id
            db.commit()

        # Popula categorias padrão se alguma estiver faltando no banco
        defaults = ["Transporte", "Lazer", "Serviços & Assinaturas", "Saúde", "Receita", "Transferência entre Contas", "Outros", "Loteria", "Mercado", "Restaurante & Delivery", "Pagamento de Fatura", "Moradia & Contas"]
        for name in defaults:
            existing = db.query(Category).filter(Category.name == name).first()
            if not existing:
                db.add(Category(name=name))
        db.commit()
    except Exception as e:
        db.rollback()
        print("Erro durante init_db:", e)
    finally:
        db.close()


# Dependência do FastAPI para obter a sessão ativa do banco
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
