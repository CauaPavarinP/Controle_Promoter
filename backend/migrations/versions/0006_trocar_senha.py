"""Senha provisória: o usuário precisa trocá-la no primeiro acesso.

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuarios") as tabela:
        tabela.add_column(sa.Column("trocar_senha", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table("usuarios") as tabela:
        tabela.drop_column("trocar_senha")
