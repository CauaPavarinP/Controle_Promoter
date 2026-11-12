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
_url = os.getenv("DATABASE_URL", "").strip()
if not _url and PRODUCAO:
    # No Render o disco é apagado a cada deploy: sem Postgres, tudo o que fosse importado se perderia.
    raise RuntimeError("Defina a variável de ambiente DATABASE_URL (Internal Database URL do Postgres do Render).")
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


def _inteiro(nome: str, padrao: int, minimo: int, maximo: int) -> int:
    try:
        valor = int(os.getenv(nome, "").strip() or padrao)
    except ValueError:
        return padrao
    return min(max(valor, minimo), maximo)


# Tamanho máximo do arquivo de faturamento, em MB. 0 (padrão) = sem limite: o arquivo é lido e gravado em partes, com
# memória constante, então o tamanho não derruba o servidor; o que limita é o espaço em disco (conferido no envio).
# Para impor um teto (ex.: tempo de envio), defina LIMITE_FATURAMENTO_MB no .env.
LIMITE_FATURAMENTO_MB = _inteiro("LIMITE_FATURAMENTO_MB", 0, 0, 1_000_000)

# Pasta do front (React) já compilado com "npm run build".
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

# As regras de negócio (tipos de nota, redes, rateio, faixas…) ficam em app/regras.py
# e são ajustadas pelo usuário na aba "Regras do cálculo".
