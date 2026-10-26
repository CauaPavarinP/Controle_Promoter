"""Login, sessão e permissões por perfil."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import db
from .modelos import Usuario


def usuario_logado(request: Request, sessao: Session = Depends(db.sessao_db)) -> Usuario:
    usuario_id = request.session.get("usuario_id")
    usuario = sessao.get(Usuario, usuario_id) if usuario_id else None
    if usuario is None or not usuario.ativo:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre novamente.")
    return usuario


def exigir_admin(usuario: Usuario = Depends(usuario_logado)) -> Usuario:
    if usuario.perfil != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem fazer isso.")
    return usuario
