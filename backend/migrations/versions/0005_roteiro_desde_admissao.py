"""Corrige dados importados antes da auditoria de 11/2026.

- Roteiro que começa antes da admissão do promotor passa a começar na admissão (a importação punha
  01/01 do ano em todos). Vínculo que terminou antes da admissão fica como está.
- Promotor com "Sup." / "Supervisor" no nome ou no município passa a ter a função Supervisor.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE roteiros
           SET data_inicio = (SELECT p.data_admissao FROM promotores p WHERE p.id = roteiros.promotor_id)
         WHERE EXISTS (SELECT 1 FROM promotores p
                        WHERE p.id = roteiros.promotor_id
                          AND p.data_admissao IS NOT NULL
                          AND p.data_admissao > roteiros.data_inicio
                          AND (roteiros.data_fim IS NULL OR roteiros.data_fim >= p.data_admissao))
    """)
    op.execute("""
        UPDATE promotores SET funcao = 'Supervisor'
         WHERE UPPER(nome) LIKE 'SUP.%' OR UPPER(nome) LIKE 'SUP %' OR UPPER(nome) LIKE '%SUPERVISOR%'
            OR UPPER(municipio) LIKE 'SUP.%' OR UPPER(municipio) LIKE 'SUP %' OR UPPER(municipio) LIKE '%SUPERVISOR%'
    """)


def downgrade():
    # Correção de dados: não há como saber a data antiga de cada vínculo.
    pass
