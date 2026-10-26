"""Acesso ao banco.

- Cadastros (supervisores, promotores, PDVs, roteiros, usuários): SQLAlchemy ORM (app/modelos.py),
  com a estrutura criada pelas migrations (backend/migrations).
- Faturamento agregado, histórico de importações e configurações: tabelas lidas e gravadas
  inteiras com o pandas (são pequenas).
"""
import json
from datetime import datetime
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
    "faturamento": ["ano", "mes", "cnpj", "chave_tipo", "tipo_nf", "cod_cliente", "razao_social",
                    "cidade", "uf", "valor", "notas"],
    # Formato da planilha importado pelas versões antigas (convertido para os cadastros).
    "legado_promotores": ["codigo", "nome", "admissao", "municipio", "supervisor",
                          "salario", "ajuda_custo", "transporte", "custo_mensal"],
    "legado_roteiro": ["codigo_promotor", "colaborador", "cnpj", "loja", "cidade", "uf", "visitas_semana"],
    "importacoes": ["tipo", "arquivo", "data_hora", "linhas", "detalhe"],
    "configuracoes": ["chave", "valor"],
}


def ler_tabela(nome: str) -> pd.DataFrame:
    if not inspect(engine).has_table(nome):
        return pd.DataFrame(columns=COLUNAS[nome])
    df = pd.read_sql_table(nome, engine)
    if nome == "faturamento" and "chave_tipo" not in df:
        # Faturamento importado antes das regras configuráveis só tinha "1-Venda".
        df["chave_tipo"], df["tipo_nf"] = "1 VENDA", "1-Venda"
    return df


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


def gravar_faturamento(novo: pd.DataFrame) -> None:
    """Substitui só os meses que vieram no arquivo novo e mantém os demais."""
    atual = ler_tabela("faturamento")
    meses_novos = set(zip(novo["ano"], novo["mes"]))
    if not atual.empty:
        manter = [(a, m) not in meses_novos for a, m in zip(atual["ano"], atual["mes"])]
        atual = atual[manter]
    substituir_tabela("faturamento", pd.concat([atual, novo], ignore_index=True))


def registrar_importacao(tipo: str, arquivo: str, linhas: int, detalhe: str = "") -> None:
    registro = pd.DataFrame([{
        "tipo": tipo, "arquivo": arquivo, "data_hora": datetime.now().isoformat(timespec="seconds"),
        "linhas": linhas, "detalhe": detalhe,
    }])
    registro.to_sql("importacoes", engine, if_exists="append", index=False)


def ultimas_importacoes() -> dict:
    df = ler_tabela("importacoes")
    if df.empty:
        return {}
    df = df.sort_values("data_hora").groupby("tipo").tail(1)
    return {r.tipo: {"arquivo": r.arquivo, "data_hora": r.data_hora, "linhas": int(r.linhas),
                     "avisos": [a for a in (r.detalhe or "").split("; ") if a]}
            for r in df.itertuples()}
