"""Ligações lembradas entre o nome da coluna "Colaborador" das abas por UF e o promotor cadastrado.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "apelidos_colaborador",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome_chave", sa.String(150), nullable=False, unique=True),
        sa.Column("nome", sa.String(150), nullable=False, server_default=""),
        sa.Column("promotor_id", sa.Integer, sa.ForeignKey("promotores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("criado_em", sa.DateTime, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime, server_default=sa.func.now()))


def downgrade():
    op.drop_table("apelidos_colaborador")
