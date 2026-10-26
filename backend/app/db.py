"""Acesso ao banco.

- Cadastros (supervisores, promotores, PDVs, roteiros, usuários): SQLAlchemy ORM (app/modelos.py),
  com a estrutura criada pelas migrations (backend/migrations).
- Faturamento item a item e histórico de importações: também ORM (app/faturamento.py).
- Configurações e totais da planilha para a conferência: tabelas pequenas lidas e gravadas
  inteiras com o pandas.
"""
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessaoLocal = sessionmaker(bind=engine, expire_on_commit=False)


def sessao_db():
    """Dependência do FastAPI: uma sessão do banco por requisição."""
    sessao = SessaoLocal()
    try:
        yield sessao
    finally:
        sessao.close()


def aplicar_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    pasta = Path(__file__).resolve().parent.parent
    configuracao = Config(str(pasta / "alembic.ini"))
    configuracao.set_main_option("script_location", str(pasta / "migrations"))
    command.upgrade(configuracao, "head")


COLUNAS = {
    # Formato da planilha importado pelas versões antigas (convertido para os cadastros).
    "legado_promotores": ["codigo", "nome", "admissao", "municipio", "supervisor",
                          "salario", "ajuda_custo", "transporte", "custo_mensal"],
    "legado_roteiro": ["codigo_promotor", "colaborador", "cnpj", "loja", "cidade", "uf", "visitas_semana"],
    # Faturamento mês a mês de cada linha das abas por UF da planilha (para a conferência).
    "conferencia_planilha": ["aba", "cnpj", "loja", "mes", "valor"],
    "configuracoes": ["chave", "valor"],
}


def ler_tabela(nome: str) -> pd.DataFrame:
    if not inspect(engine).has_table(nome):
        return pd.DataFrame(columns=COLUNAS[nome])
    return pd.read_sql_table(nome, engine)


def ler_configuracao(chave: str, padrao=None):
    df = ler_tabela("configuracoes")
    linha = df[df["chave"] == chave]
    return padrao if linha.empty else json.loads(linha["valor"].iloc[0])


def gravar_configuracao(chave: str, valor) -> None:
    df = ler_tabela("configuracoes")
    df = df[df["chave"] != chave]
    df = pd.concat([df, pd.DataFrame([{"chave": chave, "valor": json.dumps(valor)}])], ignore_index=True)
    substituir_tabela("configuracoes", df)


def substituir_tabela(nome: str, df: pd.DataFrame) -> None:
    df[COLUNAS[nome]].to_sql(nome, engine, if_exists="replace", index=False)
