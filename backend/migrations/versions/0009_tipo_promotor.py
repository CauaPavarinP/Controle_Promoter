"""Tipo de contratação do promotor em cada atendimento: Agência, CLT, MEI ou Freelancer.

Linhas antigas: "CLT" quando a agência é a própria 101 ou o nome da agência diz CLT; MEI/Freelancer pelo nome da
agência; o resto, "Agência".

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("atendimentos") as tabela:
        tabela.add_column(sa.Column("tipo", sa.String(20), nullable=False, server_default="Agência"))
    op.execute("UPDATE atendimentos SET tipo = 'Freelancer' WHERE agencia_chave LIKE '%FREELA%' OR agencia_chave LIKE '%FREE LANCER%'")
    op.execute("UPDATE atendimentos SET tipo = 'MEI' WHERE agencia_chave LIKE '% MEI' OR agencia_chave LIKE '% MEI %' "
               "OR agencia_chave LIKE 'MEI %' OR agencia_chave = 'MEI'")
    op.execute("UPDATE atendimentos SET tipo = 'CLT' WHERE agencia_chave LIKE '%CLT%' OR agencia_chave LIKE '101 DO BRASIL%'")


def downgrade():
    with op.batch_alter_table("atendimentos") as tabela:
        tabela.drop_column("tipo")
