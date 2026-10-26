import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
EXEMPLOS = BACKEND / "exemplos"


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'teste.db'}")
    monkeypatch.setenv("APP_USUARIO", "mauricio")
    monkeypatch.setenv("APP_SENHA", "senha-teste")
    monkeypatch.setenv("SECRET_KEY", "chave-teste")
    import app.config
    import app.db
    import app.main
    for modulo in (app.config, app.db, app.main):
        importlib.reload(modulo)
    if not (EXEMPLOS / "faturamento_exemplo.xlsx").exists():
        subprocess.run([sys.executable, str(BACKEND / "scripts" / "gerar_dados_exemplo.py")], check=True)
    return TestClient(app.main.app)


def _entrar(cliente):
    resposta = cliente.post("/api/login", json={"usuario": "mauricio", "senha": "senha-teste"})
    assert resposta.status_code == 200


def test_rotas_exigem_login(cliente):
    assert cliente.get("/health").status_code == 200
    assert cliente.get("/api/opcoes").status_code == 401
    assert cliente.get("/api/painel", params={"inicio": "2026-01", "fim": "2026-09"}).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "mauricio", "senha": "errada"}).status_code == 401


def test_importar_e_consultar_painel(cliente):
    _entrar(cliente)
    for tipo in ("promotores", "roteiro", "faturamento"):
        with open(EXEMPLOS / f"{tipo}_exemplo.xlsx", "rb") as arquivo:
            resposta = cliente.post(f"/api/importar/{tipo}", files={"arquivo": (f"{tipo}.xlsx", arquivo)})
        assert resposta.status_code == 200, resposta.text

    opcoes = cliente.get("/api/opcoes").json()
    assert opcoes["meses"][0] == "2026-01"
    assert opcoes["supervisores"] == ["Supervisor Dois", "Supervisora Um"]
    assert opcoes["roteiro_sem_vinculo"] == []

    painel = cliente.get("/api/painel", params={"inicio": "2026-01", "fim": "2026-09"}).json()
    assert painel["resumo"]["promotores"] == 4
    assert painel["resumo"]["lojas"] == 9
    assert painel["resumo"]["faturamento"] > 0

    cliente.post("/api/logout")
    assert cliente.get("/api/opcoes").status_code == 401


def test_importacao_com_arquivo_errado(cliente):
    _entrar(cliente)
    with open(EXEMPLOS / "promotores_exemplo.xlsx", "rb") as arquivo:
        resposta = cliente.post("/api/importar/faturamento", files={"arquivo": ("p.xlsx", arquivo)})
    assert resposta.status_code == 400
    assert "faturamento" in resposta.json()["detail"]


def test_regras_salvas_mudam_o_painel(cliente):
    _entrar(cliente)
    for tipo in ("promotores", "roteiro", "faturamento"):
        with open(EXEMPLOS / f"{tipo}_exemplo.xlsx", "rb") as arquivo:
            resposta = cliente.post(f"/api/importar/{tipo}", files={"arquivo": (f"{tipo}.xlsx", arquivo)})
    assert any("sem regra" in a for a in resposta.json()["avisos"])  # a devolução do exemplo

    dados = cliente.get("/api/regras").json()
    assert {t["tipo"]: t["acao"] for t in dados["tipos_nf"]} == {"1-Venda": "soma", "2-Devolucao": "ignora"}
    parametros = {"inicio": "2026-01", "fim": "2026-09"}
    antes = cliente.get("/api/painel", params=parametros).json()["resumo"]["faturamento"]

    regras = dados["regras"]
    regras["tipos_nf"]["2 DEVOLUCAO"] = "subtrai"
    assert cliente.put("/api/regras", json=regras).status_code == 200
    depois = cliente.get("/api/painel", params=parametros).json()["resumo"]["faturamento"]
    assert depois == antes - 500

    regras["faixa_alerta"] = 99
    assert cliente.put("/api/regras", json=regras).status_code == 400
