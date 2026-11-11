"""Chave da sessão do usuário: trocar a chave derruba as sessões abertas (sair, trocar senha, nova senha).

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuarios") as tabela:
        tabela.add_column(sa.Column("sessao_chave", sa.String(64), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("usuarios") as tabela:
        tabela.drop_column("sessao_chave")
