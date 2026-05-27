import os
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

# --- MODELOS DE DADOS ---

class User(Base):
    """Representa o Usuário do sistema."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    
    # Relação com as contas bancárias do usuário
    accounts = relationship("Account", back_populates="owner", cascade="all, delete-orphan")


class Account(Base):
    """Representa uma Conta Bancária (Ex: Nubank, Inter, Caixa)."""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bank_name = Column(String, nullable=False)  # Nubank, Banco Inter, Caixa, etc.
    account_number = Column(String, nullable=True) # Número da conta, se disponível no OFX
    initial_balance = Column(Float, default=0.0) # Saldo inicial ou ajuste de saldo para alinhar com extratos
    balance = Column(Float, default=0.0) # Saldo atual consolidado
    
    # Relações
    owner = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")


class InstallmentPlan(Base):
    """
    Representa uma compra parcelada ativa (ex: Geladeira, iPhone, IPVA).
    """
    __tablename__ = "installment_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)               # Ex: "Geladeira Midea"
    total_amount = Column(Float, nullable=False)        # Ex: 1200.00
    installment_amount = Column(Float, nullable=False)  # Ex: 120.00
    total_parts = Column(Integer, nullable=False)       # Ex: 10
    category = Column(String, default="Outros")         # Categoria padrão
    active = Column(Boolean, default=True)              # Para arquivar quando finalizado
    
    # Relação com as parcelas já pagas (transações reais)
    transactions = relationship("Transaction", back_populates="installment_plan")


class Transaction(Base):
    """
    Representa uma transação financeira importada.
    Inclui um campo de hash único baseado nos dados da transação para evitar duplicidades.
    """
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)  # Positivo = Receita, Negativo = Despesa
    transaction_type = Column(String, nullable=False)  # CREDIT / DEBIT / PIX_ENVIADO / PIX_RECEBIDO
    category = Column(String, default="Outros")  # Categoria (ex: Alimentação, Lazer)
    cost_type = Column(String, default="variavel")  # 'variavel' ou 'fixo' para despesas
    
    # O FITID é o ID único da transação gerado pelo próprio banco no arquivo OFX
    fitid = Column(String, nullable=True)
    
    # Nosso hash de segurança que impede duplicidade física no banco
    hash = Column(String, unique=True, nullable=False, index=True)
    
    # Relacionamento com parcelamento
    installment_plan_id = Column(Integer, ForeignKey("installment_plans.id", ondelete="SET NULL"), nullable=True)
    installment_number = Column(Integer, nullable=True) # Ex: 3 (representa a parcela 3 de 10)
    
    # Relações
    account = relationship("Account", back_populates="transactions")
    installment_plan = relationship("InstallmentPlan", back_populates="transactions")


class FixedCostRule(Base):
    """
    Memoriza a descrição das transações que o usuário marcou como custo fixo
    para que novas importações com a mesma descrição sejam automatizadas.
    """
    __tablename__ = "fixed_cost_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, unique=True, nullable=False, index=True)


class Category(Base):
    """
    Representa uma categoria de transação no sistema.
    """
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)


class FutureIncome(Base):
    """
    Representa uma receita futura estimada (ex: Salários, Bônus, 13º).
    """
    __tablename__ = "future_incomes"
    
    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, nullable=False)               # Ex: "Salário Dennis"
    amount = Column(Float, nullable=False)                      # Ex: 5000.00
    is_recurrent = Column(Boolean, default=True)                # True = Mensal, False = Único
    receive_day = Column(Integer, default=5)                    # Dia de recebimento
    start_date = Column(DateTime, default=datetime.utcnow)      # Mês de início


class FinancialGoal(Base):
    """
    Representa um objetivo financeiro / sonho (ex: Viagem, Carro, Reserva).
    """
    __tablename__ = "financial_goals"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)                       # Ex: "Viagem Europeia"
    target_amount = Column(Float, nullable=False)                # Ex: 12000.00
    target_date = Column(DateTime, nullable=False)              # Data limite planejada
    category = Column(String, default="Lazer")                  # Categoria (Lazer, Moradia, etc.)
    active = Column(Boolean, default=True)                      # Meta ativa ou concluída


# Criar as tabelas no banco de dados se não existirem
def init_db():
    Base.metadata.create_all(bind=engine)
    # Migração automática simples para SQLite: adiciona colunas se não existirem
    with engine.connect() as conn:
        cursor = conn.exec_driver_sql("PRAGMA table_info(transactions)")
        columns = [row[1] for row in cursor.fetchall()]
        if "cost_type" not in columns:
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN cost_type VARCHAR DEFAULT 'variavel'")
        if "installment_plan_id" not in columns:
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN installment_plan_id INTEGER REFERENCES installment_plans(id) ON DELETE SET NULL")
        if "installment_number" not in columns:
            conn.exec_driver_sql("ALTER TABLE transactions ADD COLUMN installment_number INTEGER")

    # Popula categorias padrão se alguma estiver faltando no banco
    db = SessionLocal()
    try:
        # Remove a categoria antiga 'Alimentação' se ela existir
        db.query(Category).filter(Category.name == "Alimentação").delete()
        
        # Atualiza transações antigas de 'Alimentação' para 'Mercado'
        db.query(Transaction).filter(Transaction.category == "Alimentação").update(
            {Transaction.category: "Mercado"}, synchronize_session=False
        )
        
        defaults = ["Transporte", "Lazer", "Serviços & Assinaturas", "Saúde", "Receita", "Outros", "Loteria", "Mercado", "Restaurante & Delivery", "Pagamento de Fatura", "Moradia & Contas"]
        for name in defaults:
            existing = db.query(Category).filter(Category.name == name).first()
            if not existing:
                db.add(Category(name=name))
        db.commit()
    except Exception as e:
        db.rollback()
        print("Erro ao povoar categorias padrão:", e)
    finally:
        db.close()

# Dependência do FastAPI para obter a sessão ativa do banco
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


