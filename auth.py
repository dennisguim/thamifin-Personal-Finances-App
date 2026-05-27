from datetime import datetime, timedelta
from typing import Optional
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import APIKeyCookie
import os
from dotenv import load_dotenv
import bcrypt
import jwt
from sqlalchemy.orm import Session
from database import get_db, User

# Carrega variáveis de ambiente
load_dotenv()

# Configurações de Segurança do JWT
SECRET_KEY = os.getenv("SECRET_KEY", "fallback_secret_for_dev_only")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # Duração da sessão: 1 dia (24 horas)

# Procura pelo token JWT em um cookie chamado "access_token"
cookie_sec = APIKeyCookie(name="access_token", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara uma senha em texto claro com o hash criptografado."""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    try:
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Gera um hash criptográfico seguro a partir da senha."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Gera um token JWT contendo os dados do usuário e data de expiração."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Dependência do FastAPI para verificar o cookie de sessão.
    Retorna o usuário logado ou redireciona/lança erro de credenciais.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autorizado. Por favor, faça login.",
        )
        
    try:
        # Decodifica o JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada")
        
    # Busca o usuário correspondente no banco de dados
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
        
    return user