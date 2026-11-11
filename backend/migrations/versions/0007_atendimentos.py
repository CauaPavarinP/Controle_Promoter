"""Atendimento das agências: uma linha por loja × mês × agência, vinda do arquivo (modelo) que a agência manda.

Daqui em diante o sistema é alimentado só pelo arquivo do ERP (faturamento) e por estes arquivos.

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "atendimentos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("importacao_id", sa.Integer, sa.ForeignKey("importacoes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ano", sa.Integer, nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        sa.Column("agencia", sa.String(150), nullable=False),
        sa.Column("agencia_chave", sa.String(150), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=False, server_default=""),
        sa.Column("loja", sa.String(200), nullable=False),
        sa.Column("loja_chave", sa.String(200), nullable=False),
        sa.Column("cidade", sa.String(120), nullable=False, server_default=""),
        sa.Column("uf", sa.String(2), nullable=False, server_default=""),
        sa.Column("promotor", sa.String(150), nullable=False, server_default=""),
        sa.Column("promotor_codigo", sa.String(40), nullable=False, server_default=""),
        sa.Column("promotor_chave", sa.String(200), nullable=False, server_default=""),
        sa.Column("dias", sa.String(80), nullable=False, server_default=""),
        sa.Column("visitas", sa.Integer),
        sa.Column("valor", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="Ativa"),
        sa.Column("observacao", sa.Text, nullable=False, server_default=""),
        sa.Column("linha", sa.Integer),
    )
    op.create_index("ix_atend_ano_mes", "atendimentos", ["ano", "mes"])
    op.create_index("ix_atend_agencia_mes", "atendimentos", ["agencia_chave", "ano", "mes"])
    op.create_index("ix_atend_importacao", "atendimentos", ["importacao_id"])
    op.create_index("ix_atend_cnpj", "atendimentos", ["cnpj"])


def downgrade():
    op.drop_table("atendimentos")
