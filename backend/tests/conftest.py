import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
EXEMPLOS = BACKEND / "exemplos"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def recarregar_app():
    """Recarrega os módulos para usarem o banco e as variáveis do teste."""
    import app.autenticacao
    import app.cadastros
    import app.carga
    import app.config
    import app.dados
    import app.db
    import app.main
    import app.regras
    import app.usuarios
    for modulo in (app.config, app.db, app.regras, app.carga, app.dados, app.autenticacao, app.usuarios,
                   app.cadastros, app.main):
        importlib.reload(modulo)
    return app


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'teste.db'}")
    monkeypatch.setenv("APP_USUARIO", "mauricio")
    monkeypatch.setenv("APP_SENHA", "senha-teste")
    monkeypatch.setenv("SECRET_KEY", "chave-teste")
    return recarregar_app()


@pytest.fixture()
def cliente(banco):
    if not (EXEMPLOS / "faturamento_exemplo.xlsx").exists():
        subprocess.run([sys.executable, str(BACKEND / "scripts" / "gerar_dados_exemplo.py")], check=True)
    with TestClient(banco.main.app) as cliente_teste:
        yield cliente_teste


def entrar(cliente, usuario="mauricio", senha="senha-teste"):
    resposta = cliente.post("/api/login", json={"usuario": usuario, "senha": senha})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()
