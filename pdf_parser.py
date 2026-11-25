import io
import re
import hashlib
from datetime import datetime
import pypdf
from database import Transaction
from ofx_parser import auto_categorize, generate_transaction_hash

def parse_money(val_str: str) -> float:
    """Converte representação monetária brasileira (ex: 'R$ -1.234,56' ou '-1234.56') para float."""
    if not val_str:
        return 0.0
    cleaned = (
        val_str.replace("R$", "")
        .replace("\xa0", " ")
        .replace(" ", "")
        .replace(".", "")
        .replace(",", ".")
    )
    return float(cleaned)

def parse_mercadopago_pdf(full_text: str, account_id: int) -> tuple[list[Transaction], float | None]:
    """Extrai transações e saldo final de um extrato PDF do Mercado Pago."""
    # Saldo final do extrato
    final_match = re.search(r"Saldo\s+final:\s*R\$\s*([\d\.,\-]+)", full_text, re.IGNORECASE)
    ledger_balance = parse_money(final_match.group(1)) if final_match else None

    lines = full_text.splitlines()
    in_movimentos = False
    blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in lines:
        if "DETALHE DOS MOVIMENTOS" in line:
            in_movimentos = True
            continue
        if not in_movimentos:
            continue
        if "Data de geração:" in line or "Você tem alguma dúvida?" in line:
            in_movimentos = False
            continue
        # Ignora rodapés de página como '1/5'
        if re.match(r"^\s*\d+/\d+\s*$", line):
            continue
        # Ignora cabeçalhos de coluna repetidos em quebras de página
        if "Data" in line and "Descrição" in line and "Valor" in line:
            continue

        if line.strip():
            current_block.append(line)
        else:
            if current_block:
                blocks.append(current_block)
                current_block = []

    if current_block:
        blocks.append(current_block)

    transactions: list[Transaction] = []

    for b in blocks:
        full_block_text = " \n ".join(b)

        # Procura data DD-MM-YYYY ou DD/MM/YYYY
        date_match = re.search(r"(\d{2}[-/]\d{2}[-/]\d{4})", full_block_text)
        if not date_match:
            continue

        date_str = date_match.group(1).replace("/", "-")
        try:
            tx_date = datetime.strptime(date_str, "%d-%m-%Y")
        except ValueError:
            continue

        # Procura valores monetários R$ ...
        val_matches = re.findall(r"R\$\s*([+-]?[\d\.,]+)", full_block_text)
        if not val_matches:
            continue

        amount = parse_money(val_matches[0])

        # Procura ID da operação (geralmente 10 a 16 dígitos)
        id_match = re.search(r"\b(\d{10,16})\b", full_block_text)
        fitid = id_match.group(1) if id_match else None

        # Monta a descrição limpa do bloco
        desc_parts = []
        for line in b:
            cleaned = re.sub(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b", "", line)
            if fitid:
                cleaned = cleaned.replace(fitid, "")
            cleaned = re.sub(r"R\$\s*[+-]?[\d\.,]+", "", cleaned)
            cleaned = cleaned.strip()
            if cleaned:
                desc_parts.append(cleaned)

        description = " ".join(desc_parts)
        description = " ".join(description.split())
        if not description:
            description = "Transação Mercado Pago"

        # Tipo da transação
        desc_upper = description.upper()
        if "PIX" in desc_upper:
            tx_type = "PIX_RECEBIDO" if amount > 0 else "PIX_ENVIADO"
        else:
            tx_type = "CREDIT" if amount > 0 else "DEBIT"

        category = auto_categorize(description, amount)

        # Hash determinístico anti-duplicidade
        tx_hash = generate_transaction_hash(
            account_id=account_id,
            date=tx_date,
            amount=amount,
            description=description,
            fitid=fitid or ""
        )

        db_tx = Transaction(
            account_id=account_id,
            date=tx_date,
            description=description,
            amount=amount,
            transaction_type=tx_type,
            category=category,
            fitid=fitid,
            hash=tx_hash
        )
        transactions.append(db_tx)

    return transactions, ledger_balance

def parse_and_import_pdf(file_content: bytes, account_id: int) -> tuple[list[Transaction], float | None]:
    """
    Lê o conteúdo binário de um extrato bancário em PDF e retorna
    (lista de transações, saldo final).
    """
    pdf_file = io.BytesIO(file_content)
    reader = pypdf.PdfReader(pdf_file)

    full_text = ""
    for page in reader.pages:
        # Extrai com layout preservado para garantir integridade das colunas
        text = page.extract_text(extraction_mode="layout") or page.extract_text() or ""
        full_text += text + "\n\n"

    # Se for Mercado Pago
    if "Mercado Pago" in full_text or "DETALHE DOS MOVIMENTOS" in full_text:
        return parse_mercadopago_pdf(full_text, account_id)

    # Heurística genérica para outros PDFs bancários tabulares
    lines = full_text.splitlines()
    transactions: list[Transaction] = []
    ledger_balance = None

    for line in lines:
        # Tenta capturar saldo final se presente
        if not ledger_balance:
            bal_match = re.search(r"saldo\s+(?:atual|final|dispon[ií]vel)[:\s]+R?\$?\s*([+-]?[\d\.,]+)", line, re.IGNORECASE)
            if bal_match:
                try:
                    ledger_balance = parse_money(bal_match.group(1))
                except Exception:
                    pass

        # Linha com data DD/MM/AAAA ou DD-MM-AAAA
        date_match = re.search(r"\b(\d{2}[-/]\d{2}[-/]\d{2,4})\b", line)
        val_match = re.findall(r"R?\$?\s*([+-]?\d{1,3}(?:\.\d{3})*,\d{2})", line)
        if date_match and val_match:
            date_str = date_match.group(1).replace("/", "-")
            try:
                parts = date_str.split("-")
                if len(parts[2]) == 2:
                    parts[2] = f"20{parts[2]}"
                tx_date = datetime.strptime(f"{parts[0]}-{parts[1]}-{parts[2]}", "%d-%m-%Y")
            except ValueError:
                continue

            amount = parse_money(val_match[-1])
            # Se a linha contiver indicação de D/C ou débito
            if re.search(r"\b(?:D|DÉBITO|DEBITO|-)\b", line, re.IGNORECASE) and amount > 0:
                amount = -amount

            # Descrição é a linha sem data e valor
            desc = re.sub(r"\b\d{2}[-/]\d{2}[-/]\d{2,4}\b", "", line)
            desc = re.sub(r"R?\$?\s*[+-]?\d{1,3}(?:\.\d{3})*,\d{2}", "", desc)
            desc = " ".join(desc.split()).strip()
            if not desc:
                desc = "Transação Importada"

            desc_upper = desc.upper()
            if "PIX" in desc_upper:
                tx_type = "PIX_RECEBIDO" if amount > 0 else "PIX_ENVIADO"
            else:
                tx_type = "CREDIT" if amount > 0 else "DEBIT"

            category = auto_categorize(desc, amount)
            tx_hash = generate_transaction_hash(account_id, tx_date, amount, desc, "")

            db_tx = Transaction(
                account_id=account_id,
                date=tx_date,
                description=desc,
                amount=amount,
                transaction_type=tx_type,
                category=category,
                fitid=None,
                hash=tx_hash
            )
            transactions.append(db_tx)

    return transactions, ledger_balance
