"""Backup dos atendimentos guardado no próprio banco antes de "Apagar os dados das agências".

O arquivo (Excel no modelo das agências, dá para importar de novo) fica numa tabela: o disco do servidor do Render
é apagado a cada reinício, o banco não.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "backups",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("criado_em", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("usuario", sa.String(80), nullable=False, server_default=""),
        sa.Column("motivo", sa.String(120), nullable=False, server_default=""),
        sa.Column("arquivo_nome", sa.String(255), nullable=False),
        sa.Column("linhas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conteudo", sa.LargeBinary, nullable=False),
    )


def downgrade():
    op.drop_table("backups")
