"""Valor do mês "não informado": atendimentos.valor passa a aceitar NULL (vazio ≠ R$ 0,00).

Ex.: promotor CLT, que não tem custo por loja no arquivo. Os dados já gravados não mudam (o que entrou vazio antes
desta versão já está como 0 e não dá para saber qual era vazio).

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("atendimentos") as tabela:
        tabela.alter_column("valor", existing_type=sa.Numeric(12, 2), nullable=True, server_default=None)


def downgrade():
    op.execute("UPDATE atendimentos SET valor = 0 WHERE valor IS NULL")
    with op.batch_alter_table("atendimentos") as tabela:
        tabela.alter_column("valor", existing_type=sa.Numeric(12, 2), nullable=False, server_default="0")
