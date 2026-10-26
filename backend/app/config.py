"""Configurações lidas das variáveis de ambiente (arquivo .env em desenvolvimento)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ARQUIVO_ENV = BASE_DIR / ".env"
# utf-8-sig: aceita o .env salvo pelo Bloco de Notas com BOM.
# override: em desenvolvimento o .env manda, mesmo que exista variável igual no Windows.
load_dotenv(ARQUIVO_ENV, encoding="utf-8-sig", override=True)

PRODUCAO = os.getenv("AMBIENTE", "").lower() == "producao"

# Banco: SQLite local em desenvolvimento, Postgres (DATABASE_URL do Render) em produção.
_url = os.getenv("DATABASE_URL", "")
if not _url:
    (BASE_DIR / "dados").mkdir(exist_ok=True)
    _url = f"sqlite:///{BASE_DIR / 'dados' / 'app.db'}"
elif _url.startswith("postgres://"):
    _url = "postgresql+psycopg://" + _url[len("postgres://"):]
elif _url.startswith("postgresql://"):
    _url = "postgresql+psycopg://" + _url[len("postgresql://"):]
DATABASE_URL = _url

# Login
APP_USUARIO = os.getenv("APP_USUARIO", "").strip()
APP_SENHA = os.getenv("APP_SENHA", "").strip()

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if PRODUCAO:
        raise RuntimeError("Defina a variável de ambiente SECRET_KEY em produção.")
    # Em desenvolvimento gera uma chave temporária (as sessões caem ao reiniciar).
    SECRET_KEY = secrets.token_hex(32)

SESSAO_HORAS = int(os.getenv("SESSAO_HORAS", "12"))

# Pasta do front (React) já compilado com "npm run build".
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

# As regras de negócio (tipos de nota, redes, rateio, faixas…) ficam em app/regras.py
# e são ajustadas pelo usuário na aba "Regras do cálculo".
