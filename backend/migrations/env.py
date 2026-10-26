"""Ambiente das migrations: usa o mesmo banco do sistema (app/config.py)."""
from alembic import context

from app.db import engine

with engine.connect() as conexao:
    context.configure(connection=conexao, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
    conexao.commit()
