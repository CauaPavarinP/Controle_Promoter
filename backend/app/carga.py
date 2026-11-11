"""Preparação do banco ao ligar o servidor e a trava das importações de cadastro.

Desde a troca de fontes (só o arquivo do ERP e os arquivos das agências), os cadastros não vêm mais da planilha
"ROTEIROS X FATURAMENTOS": promotores, lojas e agências são montados a partir dos atendimentos (app/atendimento.py).
"""
import logging
import threading

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import db
from .config import APP_SENHA, APP_USUARIO
from .modelos import Usuario
from .seguranca import gerar_hash

log = logging.getLogger("uvicorn.error")

# Uma leitura pesada por vez (arquivo das agências ou limpeza dos dados): duas juntas misturariam os dados e
# somariam a memória. Também não roda junto com a leitura do faturamento (ver main.OCUPADO).
trava_cadastros = threading.Lock()


def criar_primeiro_admin(sessao: Session) -> None:
    """Sem nenhum usuário, cria o administrador com APP_USUARIO/APP_SENHA do .env."""
    if sessao.scalar(select(func.count(Usuario.id))):
        return
    if not APP_USUARIO or not APP_SENHA:
        log.warning("Nenhum usuário cadastrado e APP_USUARIO/APP_SENHA vazios: ninguém conseguirá entrar.")
        return
    sessao.add(Usuario(nome=APP_USUARIO, usuario=APP_USUARIO.lower(), senha_hash=gerar_hash(APP_SENHA),
                       perfil="admin"))
    sessao.commit()
    log.info("Administrador inicial '%s' criado a partir do .env.", APP_USUARIO)


def preparar_banco() -> None:
    db.aplicar_migrations()
    with db.SessaoLocal() as sessao:
        criar_primeiro_admin(sessao)
