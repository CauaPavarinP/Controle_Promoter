"""Arquivo dos MEIs: frequência por semana e o CNPJ como veio no arquivo; chave da loja sem CNPJ com a cidade.

- atendimentos.frequencia_semana (aceita vazio): vezes por semana, para estimar as visitas do período.
- atendimentos.cnpj_arquivo (padrão ""): o CNPJ como a agência mandou, quando o dígito verificador não confere
  (a tela mostra "CNPJ inválido no arquivo: <valor>"). Os dados antigos ficam com "" (o valor original não foi
  guardado; aparece ao importar de novo).
- loja_chave das lojas SEM CNPJ passa a ser nome + cidade + UF (antes só o nome). Só recalcula a chave: nenhuma
  linha é apagada nem somada. Linhas que já foram somadas na importação (ex.: 3 SUPER BENEDETTI viraram 1)
  continuam somadas até o arquivo ser importado de novo.

Revision ID: 0012
Revises: 0011
"""
import re
import unicodedata

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _normalizar(valor) -> str:
    # Igual a app.importacao.normalizar_texto (copiado: a migração não depende do código do app).
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", " ", texto.upper()).strip()


def _recalcular_chaves(com_cidade: bool):
    conexao = op.get_bind()
    linhas = conexao.execute(sa.text("SELECT id, loja, cidade, uf FROM atendimentos WHERE cnpj = ''")).all()
    for id_, loja, cidade, uf in linhas:
        chave = _normalizar(loja)
        if com_cidade:
            chave = f"{chave} | {_normalizar(cidade)} {_normalizar(uf)}".strip()
        conexao.execute(sa.text("UPDATE atendimentos SET loja_chave = :c WHERE id = :i"), {"c": chave[:200], "i": id_})


def upgrade():
    with op.batch_alter_table("atendimentos") as tabela:
        tabela.add_column(sa.Column("frequencia_semana", sa.Integer(), nullable=True))
        tabela.add_column(sa.Column("cnpj_arquivo", sa.String(40), nullable=False, server_default=""))
    _recalcular_chaves(com_cidade=True)


def downgrade():
    _recalcular_chaves(com_cidade=False)
    with op.batch_alter_table("atendimentos") as tabela:
        tabela.drop_column("cnpj_arquivo")
        tabela.drop_column("frequencia_semana")
