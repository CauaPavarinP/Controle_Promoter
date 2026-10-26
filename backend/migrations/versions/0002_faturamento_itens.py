"""Faturamento item a item, histórico de importações (com desfazer).

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TEXTOS = [("cod_emp", 20), ("num_nf", 30), ("cod_segmento", 20), ("descricao_segmento", 120), ("cod_est", 20),
          ("tp_pes", 2), ("razao_social", 200), ("cidade", 120), ("uf", 2), ("cod_rep", 20),
          ("representante", 150), ("familia_2", 120), ("familia_4", 150), ("marca", 150), ("embalagem", 40),
          ("volume", 20), ("um", 10), ("cod_item", 30), ("descricao_item", 255), ("ump", 20), ("cod_tp_nf", 20),
          ("cfop", 10), ("receita", 10), ("cond_pgto", 60), ("grupo", 60)]
VALORES = ["qtde", "preco_unit", "vlr_mercadoria", "vlr_total", "qtde_caixa", "bonificacao", "total_venda"]


def upgrade():
    # As versões anteriores guardavam o faturamento já somado por mês e um histórico simples
    # de importações (tabelas sem id). Elas ficam guardadas com prefixo "legado_"; o faturamento
    # precisa ser importado de novo, agora item a item.
    tabelas = sa.inspect(op.get_bind())
    for antiga in ("faturamento", "importacoes"):
        if tabelas.has_table(antiga) and "id" not in {c["name"] for c in tabelas.get_columns(antiga)}:
            op.rename_table(antiga, f"legado_{antiga}")

    op.create_table(
        "importacoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("arquivo_nome", sa.String(255), nullable=False, server_default=""),
        sa.Column("usuario", sa.String(60), nullable=False, server_default=""),
        sa.Column("periodos", sa.Text, nullable=False, server_default=""),
        sa.Column("linhas_lidas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("linhas_importadas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("linhas_com_erro", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_venda", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("avisos", sa.Text, nullable=False, server_default=""),
        sa.Column("log_erros", sa.Text, nullable=False, server_default=""),
        sa.Column("situacao", sa.String(20), nullable=False, server_default="ativa"),
        sa.Column("criado_em", sa.DateTime, server_default=sa.func.now()))

    op.create_table(
        "faturamento_itens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("importacao_id", sa.Integer, sa.ForeignKey("importacoes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ano", sa.Integer, nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        sa.Column("data_emissao", sa.Date),
        sa.Column("cod_cli", sa.String(30), nullable=False, server_default=""),
        sa.Column("cnpj_cpf", sa.String(14), nullable=False),
        sa.Column("tipo_nf", sa.String(60), nullable=False, server_default=""),
        sa.Column("tipo_nf_chave", sa.String(60), nullable=False, server_default=""),
        *[sa.Column(nome, sa.String(tamanho)) for nome, tamanho in TEXTOS],
        *[sa.Column(nome, sa.Numeric(14, 2)) for nome in VALORES])
    op.create_index("ix_fat_ano_mes", "faturamento_itens", ["ano", "mes"])
    op.create_index("ix_fat_cnpj_ano_mes", "faturamento_itens", ["cnpj_cpf", "ano", "mes"])
    op.create_index("ix_fat_num_nf", "faturamento_itens", ["num_nf"])
    op.create_index("ix_fat_importacao", "faturamento_itens", ["importacao_id"])


def downgrade():
    op.drop_table("faturamento_itens")
    op.drop_table("importacoes")
