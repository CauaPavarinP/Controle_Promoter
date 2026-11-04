import importlib
import os
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
    import app.exportar
    import app.db
    import app.faturamento
    import app.main
    import app.pendencias
    import app.regras
    import app.usuarios
    for modulo in (app.config, app.db, app.regras, app.faturamento, app.carga, app.dados, app.autenticacao,
                   app.usuarios, app.cadastros, app.pendencias, app.exportar, app.main):
        importlib.reload(modulo)
    return app


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    # TEST_DATABASE_URL=postgresql://... roda os testes num Postgres (como no Render); o banco é zerado a cada teste.
    url_postgres = os.getenv("TEST_DATABASE_URL", "")
    if url_postgres:
        from sqlalchemy import create_engine, text
        motor = create_engine(url_postgres.replace("postgresql://", "postgresql+psycopg://", 1))
        with motor.begin() as conexao:
            conexao.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
        motor.dispose()
    monkeypatch.setenv("DATABASE_URL", url_postgres or f"sqlite:///{tmp_path / 'teste.db'}")
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


def importar_cadastros(cliente, *tipos):
    for tipo in tipos or ("promotores", "roteiro"):
        with open(EXEMPLOS / f"{tipo}_exemplo.xlsx", "rb") as arquivo:
            resposta = cliente.post(f"/api/importacoes/{tipo}", files={"arquivo": (f"{tipo}.xlsx", arquivo)})
        assert resposta.status_code == 200, resposta.text


def importar_faturamento(cliente, arquivo="faturamento_exemplo.xlsx", substituir=False):
    with open(EXEMPLOS / arquivo, "rb") as conteudo:
        previa = cliente.post("/api/importacoes/faturamento/previa", files={"arquivo": (arquivo, conteudo)})
    assert previa.status_code == 200, previa.text
    previa = previa.json()
    resposta = cliente.post(f"/api/importacoes/faturamento/{previa['token']}/confirmar",
                            json={"substituir": substituir})
    return previa, resposta


def gravar_itens(banco, linhas):
    """Grava itens de faturamento direto no banco: [(mes, cnpj, valor[, cod_cli, tipo, receita])]."""
    from app.importacao import normalizar_texto
    from app.modelos import FaturamentoItem, Importacao
    with banco.db.SessaoLocal() as sessao:
        importacao = Importacao(tipo="faturamento", arquivo_nome="teste", situacao="ativa")
        sessao.add(importacao)
        sessao.flush()
        for numero, linha in enumerate(linhas):
            mes, cnpj, valor, *resto = linha
            cod_cli, tipo, receita = list(resto) + ["", "1-Venda", "SIM"][len(resto):]
            sessao.add(FaturamentoItem(importacao_id=importacao.id, ano=2026, mes=mes, cnpj_cpf=cnpj, cod_cli=cod_cli,
                                       num_nf=str(numero), tipo_nf=tipo, tipo_nf_chave=normalizar_texto(tipo),
                                       receita=receita, total_venda=valor, vlr_total=valor))
        sessao.commit()
