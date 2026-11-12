"""Supervisor do promotor em cada atendimento (coluna opcional "Supervisor" do modelo das agências).

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("atendimentos") as tabela:
        tabela.add_column(sa.Column("supervisor", sa.String(100), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("atendimentos") as tabela:
        tabela.drop_column("supervisor")
