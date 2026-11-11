"""Login, sessão e permissões por perfil."""
import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import db
from .modelos import Usuario


ROTAS_COM_SENHA_PROVISORIA = {"/api/sessao", "/api/minha-senha"}


def usuario_logado(request: Request, sessao: Session = Depends(db.sessao_db)) -> Usuario:
    usuario_id = request.session.get("usuario_id")
    usuario = sessao.get(Usuario, usuario_id) if usuario_id else None
    # A chave da sessão muda ao sair, trocar a senha ou receber senha nova: cookie antigo (ou roubado) deixa de valer.
    chave_valida = usuario is not None and usuario.sessao_chave and \
        hmac.compare_digest(str(request.session.get("chave", "")), usuario.sessao_chave)
    if usuario is None or not usuario.ativo or not chave_valida:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre novamente.")
    # Com senha provisória, só dá para ver a própria sessão e trocar a senha (o administrador sabe a provisória).
    if usuario.trocar_senha and request.url.path not in ROTAS_COM_SENHA_PROVISORIA:
        raise HTTPException(status_code=403, detail="Troque a senha provisória antes de continuar.")
    return usuario


def exigir_admin(usuario: Usuario = Depends(usuario_logado)) -> Usuario:
    if usuario.perfil != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem fazer isso.")
    return usuario
