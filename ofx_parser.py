import hashlib
import io
from datetime import datetime
from ofxparse import OfxParser
from database import Transaction, Account

# Regras simples para classificar transações automaticamente com base na descrição (MEMO)
CATEGORY_RULES = {
    "Alimentação": ["MCDONALDS", "BURGER", "RESTAURANTE", "IFOOD", "SUPERMERCADO", "CARREFOUR", "PAO DE ACUCAR", "PADARIA", "CEASA", "CONVENIENCIA"],
    "Transporte": ["UBER", "99APP", "METRO", "ESTAPAR", "POSTO", "GASOLINA", "SHELL", "IPIRANGA", "PEDAGIO"],
    "Lazer": ["NETFLIX", "SPOTIFY", "CINEMA", "INGRESSO", "STEAM", "PLAYSTATION", "HOTEL", "CHOPP", "BAR"],
    "Serviços & Assinaturas": ["SABESP", "ENEL", "CLARO", "VIVO", "TIM", "INTERNET", "COELBA", "COPEL", "PREVIDENCIA", "SEGURO"],
    "Saúde": ["FARMACIA", "DROGASIL", "PAGUE MENOS", "MEDICO", "HOSPITAL", "DENTISTA", "EXAME"],
    "Transferências/Receitas": ["PIX RECEBIDO", "SALARIO", "TED RECEBIDA", "RENDIMENTO", "ESTORNO"],
}

def auto_categorize(description: str, amount: float) -> str:
    """Classifica automaticamente a transação de acordo com palavras-chave do extrato."""
    desc_upper = description.upper()
    
    # Se o valor for positivo, é uma receita (crédito)
    if amount > 0:
        return "Receita"
        
    # Busca correspondências nas regras de palavras-chave
    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in desc_upper:
                return category
                
    return "Outros"

def generate_transaction_hash(account_id: int, date: datetime, amount: float, description: str, fitid: str) -> str:
    """
    Gera um hash SHA-256 exclusivo e determinístico para cada movimentação financeira.
    Isso serve como uma 'impressão digital' imutável para evitar qualquer duplicata.
    """
    # Normaliza a descrição removendo espaços desnecessários e forçando maiúsculas
    normalized_desc = " ".join(description.strip().upper().split())
    # Formata a data de forma padronizada
    date_str = date.strftime("%Y-%m-%d %H:%M:%S")
    # Garante um valor decimal padronizado
    amount_str = f"{amount:.2f}"
    
    # Junta os elementos cruciais para gerar a string de hash
    raw_string = f"ACC_{account_id}|DT_{date_str}|VAL_{amount_str}|DESC_{normalized_desc}|FITID_{fitid or ''}"
    
    return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

def parse_and_import_ofx(file_content: bytes, account_id: int) -> tuple[list[Transaction], float | None]:
    """
    Lê o conteúdo binário de um arquivo OFX, mapeia cada transação para o modelo
    do banco de dados e retorna uma tupla (lista de transações, saldo final).
    """
    # Transforma o conteúdo de bytes em um arquivo simulado na memória para o parser ler
    ofx_file = io.BytesIO(file_content)

    # Faz o parsing do arquivo OFX usando a biblioteca ofxparse
    parsed_ofx = OfxParser.parse(ofx_file)

    transactions_to_import = []
    ledger_balance = None

    # Navega pelas transações encontradas na conta do arquivo OFX
    for parsed_account in parsed_ofx.accounts:
        # Tenta capturar o saldo do extrato se disponível
        if hasattr(parsed_account, "statement") and parsed_account.statement.balance is not None:
            ledger_balance = float(parsed_account.statement.balance)

        for tx in parsed_account.statement.transactions:
            # Converte valores
            amount = float(tx.amount)
            # Determina o tipo (PIX se contiver "PIX" na descrição, senão CREDIT/DEBIT)
            desc_upper = tx.memo.upper()
            if "PIX" in desc_upper:
                tx_type = "PIX_RECEBIDO" if amount > 0 else "PIX_ENVIADO"
            else:
                tx_type = "CREDIT" if amount > 0 else "DEBIT"
            # Categorização automática baseada na descrição
            category = auto_categorize(tx.memo, amount)

            # Gera o hash de segurança inteligente anti-duplicados
            tx_hash = generate_transaction_hash(
                account_id=account_id,
                date=tx.date,
                amount=amount,
                description=tx.memo,
                fitid=tx.id
            )

            # Cria a instância da transação (pronta para ser salva)
            db_transaction = Transaction(
                account_id=account_id,
                date=tx.date,
                description=tx.memo,
                amount=amount,
                transaction_type=tx_type,
                category=category,
                fitid=tx.id,
                hash=tx_hash
            )
            transactions_to_import.append(db_transaction)

    return transactions_to_import, ledger_balance
