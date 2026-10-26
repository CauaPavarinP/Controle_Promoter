"""Cadastros: supervisores, promotores, custos por competência, PDVs, roteiros e usuários.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _carimbo():
    return [sa.Column("criado_em", sa.DateTime, server_default=sa.func.now()),
            sa.Column("atualizado_em", sa.DateTime, server_default=sa.func.now())]


def _dinheiro(nome):
    return sa.Column(nome, sa.Numeric(12, 2), nullable=False, server_default="0")


def upgrade():
    # Versões anteriores gravavam a planilha importada em "promotores" e "roteiro" (sem id).
    # Elas são renomeadas e convertidas para os cadastros na inicialização (app/carga.py).
    tabelas = sa.inspect(op.get_bind())
    for antiga, nova in (("promotores", "legado_promotores"), ("roteiro", "legado_roteiro")):
        if tabelas.has_table(antiga) and "id" not in {c["name"] for c in tabelas.get_columns(antiga)}:
            op.rename_table(antiga, nova)

    op.create_table(
        "supervisores",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False, unique=True),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        *_carimbo())

    op.create_table(
        "promotores",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("codigo", sa.String(30), nullable=False, unique=True),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("data_admissao", sa.Date),
        sa.Column("data_desligamento", sa.Date),
        sa.Column("municipio", sa.String(120), nullable=False, server_default=""),
        sa.Column("uf", sa.String(2), nullable=False, server_default=""),
        sa.Column("supervisor_id", sa.Integer, sa.ForeignKey("supervisores.id")),
        sa.Column("funcao", sa.String(30), nullable=False, server_default="Promotor"),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("observacao", sa.Text, nullable=False, server_default=""),
        *_carimbo())

    op.create_table(
        "custos_promotor",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("promotor_id", sa.Integer, sa.ForeignKey("promotores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ano", sa.Integer, nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        _dinheiro("salario"), _dinheiro("ajuda_custo"), _dinheiro("vale_transporte"), _dinheiro("outros"),
        *_carimbo(),
        sa.UniqueConstraint("promotor_id", "ano", "mes"))

    op.create_table(
        "pdvs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cnpj_cpf", sa.String(14), nullable=False, server_default=""),
        sa.Column("nome_fantasia", sa.String(200), nullable=False),
        sa.Column("nome_chave", sa.String(200), nullable=False),
        sa.Column("cod_cli_erp", sa.String(30), nullable=False, server_default=""),
        sa.Column("razao_social", sa.String(200), nullable=False, server_default=""),
        sa.Column("cidade", sa.String(120), nullable=False, server_default=""),
        sa.Column("uf", sa.String(2), nullable=False, server_default=""),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        *_carimbo(),
        sa.UniqueConstraint("cnpj_cpf", "nome_chave"))
    op.create_index("ix_pdvs_cnpj", "pdvs", ["cnpj_cpf"])

    op.create_table(
        "roteiros",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("promotor_id", sa.Integer, sa.ForeignKey("promotores.id"), nullable=False),
        sa.Column("pdv_id", sa.Integer, sa.ForeignKey("pdvs.id"), nullable=False),
        sa.Column("data_inicio", sa.Date, nullable=False),
        sa.Column("data_fim", sa.Date),
        sa.Column("visitas_por_semana", sa.Integer),
        sa.Column("dias_semana", sa.String(40), nullable=False, server_default=""),
        sa.Column("observacao", sa.Text, nullable=False, server_default=""),
        *_carimbo())
    op.create_index("ix_roteiros_promotor", "roteiros", ["promotor_id"])
    op.create_index("ix_roteiros_pdv", "roteiros", ["pdv_id"])

    op.create_table(
        "roteiro_pendencias",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("colaborador", sa.String(150), nullable=False, server_default=""),
        sa.Column("cnpj_cpf", sa.String(14), nullable=False, server_default=""),
        sa.Column("loja", sa.String(200), nullable=False, server_default=""),
        sa.Column("cidade", sa.String(120), nullable=False, server_default=""),
        sa.Column("uf", sa.String(2), nullable=False, server_default=""),
        sa.Column("visitas_por_semana", sa.Integer),
        sa.Column("origem", sa.String(60), nullable=False, server_default=""),
        *_carimbo())

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("usuario", sa.String(60), nullable=False, unique=True),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("perfil", sa.String(20), nullable=False, server_default="consulta"),
        sa.Column("supervisor_id", sa.Integer, sa.ForeignKey("supervisores.id")),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("tentativas_falhas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("bloqueado_ate", sa.DateTime),
        *_carimbo())


def downgrade():
    for tabela in ("usuarios", "roteiro_pendencias", "roteiros", "pdvs", "custos_promotor",
                   "promotores", "supervisores"):
        op.drop_table(tabela)
