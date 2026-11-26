import io
import re
import csv
import hashlib
from datetime import datetime
from database import Transaction
from ofx_parser import auto_categorize, generate_transaction_hash

def parse_money(val_str: str) -> float:
    """
    Converte representação monetária (brasileira ou internacional) para float.
    Exemplos: '13,33' -> 13.33, '-14,96' -> -14.96, '1.234,56' -> 1234.56,
    'R$ -100,00' -> -100.0, '(50,00)' -> -50.0.
    """
    if not val_str:
        return 0.0
        
    s = str(val_str).strip()
    is_negative = False
    
    # Parênteses indicando valor negativo (formato contábil)
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        is_negative = True
        s = s[1:].strip()
    elif s.endswith("-"):
        is_negative = True
        s = s[:-1].strip()
        
    # Limpa moeda e espaços
    s = s.replace("R$", "").replace("$", "").replace("\xa0", " ").strip()
    
    # Tratamento de pontuação brasileira vs internacional
    if "," in s and "." in s:
        # Se vírgula vem depois do ponto: 1.234,56
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else: # 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        # Apenas vírgula: 13,33 ou 1234,56
        s = s.replace(",", ".")
        
    try:
        val = float(s)
        return -val if is_negative and val > 0 else (val if not is_negative else -abs(val))
    except ValueError:
        return 0.0

def parse_date(date_str: str) -> datetime | None:
    """Converte strings de datas variadas para datetime."""
    if not date_str:
        return None
    s = date_str.strip().split()[0] # Pega só a parte da data se houver hora
    s = s.replace(".", "/").replace("-", "/")
    
    formats = [
        "%d/%m/%Y",
        "%d/%m/%y",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def detect_encoding(file_content: bytes) -> str:
    """Detecta a codificação de texto do arquivo CSV."""
    for enc in ["utf-8", "utf-8-sig", "latin1", "cp1252"]:
        try:
            file_content.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"

def detect_delimiter(header_line: str) -> str:
    """Detecta o delimitador do CSV (; , \t |)."""
    counts = {
        ";": header_line.count(";"),
        ",": header_line.count(","),
        "\t": header_line.count("\t"),
        "|": header_line.count("|")
    }
    sorted_delims = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return sorted_delims[0][0] if sorted_delims[0][1] > 0 else ";"

def parse_and_import_csv(file_content: bytes, account_id: int) -> tuple[list[Transaction], float | None]:
    """
    Lê o conteúdo de um arquivo CSV de extrato bancário (ex: Banco Inter, Nubank, Itaú, etc.),
    extrai transações e saldo final se disponível.
    """
    encoding = detect_encoding(file_content)
    text = file_content.decode(encoding)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    
    if not lines:
        return [], None

    ledger_balance: float | None = None
    header_idx = -1
    delimiter = ";"

    # 1. Procura por saldo nos metadados do cabeçalho (ex: Banco Inter 'Saldo ;11,77')
    for i, line in enumerate(lines[:15]):
        # Se encontrar menção a Saldo antes do cabeçalho da tabela
        bal_match = re.search(r"^\s*Saldo\s*[;:=]\s*R?\$?\s*([+-]?[\d\.,]+)", line, re.IGNORECASE)
        if bal_match:
            try:
                ledger_balance = parse_money(bal_match.group(1))
            except Exception:
                pass

        # Identifica a linha de cabeçalho da tabela de transações
        line_clean = line.lower()
        has_date = any(k in line_clean for k in ["data", "dt", "date"])
        has_desc = any(k in line_clean for k in ["hist", "descri", "memo", "lançamento", "lancamento", "detalhe", "título", "titulo"])
        has_value = any(k in line_clean for k in ["valor", "amount", "quantia", "saldo", "crédito", "credito", "débito", "debito"])
        
        if (has_date and has_value) or (has_date and has_desc):
            header_idx = i
            delimiter = detect_delimiter(line)
            break

    # Se não achou cabeçalho clássico, tenta usar a linha 0
    if header_idx == -1:
        header_idx = 0
        delimiter = detect_delimiter(lines[0])

    header_line = lines[header_idx]
    # Faz parse do cabeçalho com o leitor CSV
    header_cols = [c.strip().lower() for c in next(csv.reader([header_line], delimiter=delimiter))]

    # Mapeamento de índices das colunas
    col_date = -1
    col_hist = -1
    col_desc = -1
    col_amount = -1
    col_credit = -1
    col_debit = -1
    col_balance = -1
    col_type = -1

    for idx, col in enumerate(header_cols):
        c = col.replace(" ", "").replace("_", "")
        if col_date == -1 and ("data" in c or "date" in c or c == "dt"):
            col_date = idx
        elif col_hist == -1 and "hist" in c:
            col_hist = idx
        elif col_desc == -1 and ("desc" in c or "memo" in c or "detalhe" in c or "titulo" in c or "título" in c or "estabelecimento" in c):
            col_desc = idx
        elif col_amount == -1 and ("valor" in c or "amount" in c or "quantia" in c):
            col_amount = idx
        elif col_credit == -1 and ("credit" in c or "crédito" in c or "entrada" in c):
            col_credit = idx
        elif col_debit == -1 and ("debit" in c or "débito" in c or "saida" in c or "saída" in c):
            col_debit = idx
        elif col_balance == -1 and ("saldo" in c or "balance" in c):
            col_balance = idx
        elif col_type == -1 and ("tipo" in c or "natureza" in c or c == "d/c"):
            col_type = idx

    # Se col_desc não foi achado mas col_hist foi, ou vice-versa
    if col_desc == -1 and col_hist != -1:
        col_desc = col_hist
        col_hist = -1

    # Validação mínima de colunas
    if col_date == -1 or (col_amount == -1 and col_credit == -1 and col_debit == -1):
        # Tenta fallback por posição se o cabeçalho não tiver nomes reconhecidos
        if len(header_cols) >= 3:
            col_date = 0
            col_desc = 1
            col_amount = 2

    transactions: list[Transaction] = []
    first_row_balance: float | None = None

    # Processa as linhas de dados
    data_reader = csv.reader(lines[header_idx + 1:], delimiter=delimiter)
    for row in data_reader:
        if not row or len(row) <= max(col_date, col_amount if col_amount != -1 else 0):
            continue

        # Data
        date_raw = row[col_date].strip() if col_date < len(row) else ""
        tx_date = parse_date(date_raw)
        if not tx_date:
            continue

        # Descrição e Histórico
        desc_val = row[col_desc].strip() if col_desc != -1 and col_desc < len(row) else ""
        hist_val = row[col_hist].strip() if col_hist != -1 and col_hist < len(row) else ""

        if desc_val and hist_val and desc_val.lower() != hist_val.lower():
            # Ex: "Bytedance Brasil Tecnologia Ltda. (Pix recebido)"
            full_desc = f"{desc_val} ({hist_val})"
        elif desc_val:
            full_desc = desc_val
        elif hist_val:
            full_desc = hist_val
        else:
            full_desc = "Transação CSV"

        # Limpa espaços duplicados
        full_desc = " ".join(full_desc.split())

        # Valor
        amount = 0.0
        if col_amount != -1 and col_amount < len(row):
            amount = parse_money(row[col_amount])
        elif col_credit != -1 or col_debit != -1:
            cred = parse_money(row[col_credit]) if col_credit != -1 and col_credit < len(row) else 0.0
            deb = parse_money(row[col_debit]) if col_debit != -1 and col_debit < len(row) else 0.0
            if cred > 0:
                amount = cred
            elif deb != 0:
                amount = -abs(deb)

        # Se houver indicação de Débito em coluna de Tipo
        if col_type != -1 and col_type < len(row):
            type_val = row[col_type].strip().upper()
            if any(k in type_val for k in ["D", "DEB", "DÉBITO", "DEBITO", "SAIDA", "SAÍDA"]) and amount > 0:
                amount = -amount

        # Se for 0.0, ignora linhas informativas
        if amount == 0.0:
            continue

        # Captura o saldo da primeira linha se ainda não capturado
        if col_balance != -1 and col_balance < len(row):
            row_bal_str = row[col_balance].strip()
            if row_bal_str:
                row_bal = parse_money(row_bal_str)
                if first_row_balance is None:
                    first_row_balance = row_bal

        # Tipo da transação e categoria
        desc_upper = full_desc.upper()
        hist_upper = hist_val.upper()
        if "PIX" in desc_upper or "PIX" in hist_upper:
            tx_type = "PIX_RECEBIDO" if amount > 0 else "PIX_ENVIADO"
        else:
            tx_type = "CREDIT" if amount > 0 else "DEBIT"

        category = auto_categorize(full_desc, amount)
        tx_hash = generate_transaction_hash(account_id, tx_date, amount, full_desc, "")

        db_tx = Transaction(
            account_id=account_id,
            date=tx_date,
            description=full_desc,
            amount=amount,
            transaction_type=tx_type,
            category=category,
            fitid=None,
            hash=tx_hash
        )
        transactions.append(db_tx)

    # Se não tínhamos saldo final do cabeçalho, usa o da primeira linha da tabela
    if ledger_balance is None and first_row_balance is not None:
        ledger_balance = first_row_balance

    return transactions, ledger_balance
