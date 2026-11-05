"""Login, sessão, troca de senha e cadastro de usuários (só administrador)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import db
from .autenticacao import exigir_admin, usuario_logado
from .modelos import PERFIS, Supervisor, Usuario
from .seguranca import (HASH_FALSO, MINUTOS_BLOQUEIO, conferir_senha, esta_bloqueado, gerar_hash, gerar_senha,
                        nova_chave_de_sessao, registrar_falha, registrar_sucesso, validar_nova_senha)

rotas = APIRouter(prefix="/api")


def _erro(mensagem: str, status: int = 400):
    raise HTTPException(status_code=status, detail=mensagem)


def _usuario_json(u: Usuario) -> dict:
    return {"id": u.id, "nome": u.nome, "usuario": u.usuario, "perfil": u.perfil,
            "supervisor_id": u.supervisor_id, "ativo": u.ativo, "bloqueado": esta_bloqueado(u)}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class Credenciais(BaseModel):
    usuario: str = Field(max_length=60)
    senha: str = Field(max_length=200)


@rotas.post("/login")
def login(dados: Credenciais, request: Request, sessao: Session = Depends(db.sessao_db)):
    usuario = sessao.scalar(select(Usuario).where(Usuario.usuario == dados.usuario.strip().lower()))
    if usuario is not None and esta_bloqueado(usuario):
        _erro(f"Usuário bloqueado por excesso de tentativas. Tente de novo em até {MINUTOS_BLOQUEIO} minutos.", 401)
    # Sempre confere um hash (o falso quando o usuário não existe): o tempo de resposta não entrega quem existe.
    senha_certa = conferir_senha(dados.senha, usuario.senha_hash if usuario is not None else HASH_FALSO)
    if usuario is None or not usuario.ativo or not senha_certa:
        if usuario is not None:
            registrar_falha(usuario)
            sessao.commit()
        _erro("Usuário ou senha inválidos.", 401)
    registrar_sucesso(usuario)
    if not usuario.sessao_chave:
        nova_chave_de_sessao(usuario)
    sessao.commit()
    request.session.clear()
    request.session["usuario_id"] = usuario.id
    request.session["chave"] = usuario.sessao_chave
    return _usuario_json(usuario)


@rotas.post("/logout")
def logout(request: Request, sessao: Session = Depends(db.sessao_db)):
    """Sai e derruba as outras sessões abertas desse usuário (o cookie antigo deixa de valer)."""
    usuario_id = request.session.get("usuario_id")
    usuario = sessao.get(Usuario, usuario_id) if usuario_id else None
    if usuario is not None and usuario.sessao_chave and request.session.get("chave") == usuario.sessao_chave:
        nova_chave_de_sessao(usuario)
        sessao.commit()
    request.session.clear()
    return {"ok": True}


@rotas.get("/sessao")
def sessao_atual(usuario: Usuario = Depends(usuario_logado)):
    return _usuario_json(usuario)


class TrocaSenha(BaseModel):
    senha_atual: str = Field(max_length=200)
    nova_senha: str = Field(max_length=200)


@rotas.put("/minha-senha")
def trocar_minha_senha(dados: TrocaSenha, request: Request, usuario: Usuario = Depends(usuario_logado),
                       sessao: Session = Depends(db.sessao_db)):
    usuario = sessao.get(Usuario, usuario.id)
    if not conferir_senha(dados.senha_atual, usuario.senha_hash):
        _erro("A senha atual está errada.")
    try:
        validar_nova_senha(dados.nova_senha)
    except ValueError as erro:
        _erro(str(erro))
    usuario.senha_hash = gerar_hash(dados.nova_senha)
    # Derruba as outras sessões (ex.: alguém que pegou a senha antiga); esta continua aberta.
    request.session["chave"] = nova_chave_de_sessao(usuario)
    sessao.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Usuários (administrador)
# ---------------------------------------------------------------------------

class UsuarioEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=150)
    perfil: str
    supervisor_id: int | None = None


class UsuarioNovo(UsuarioEntrada):
    usuario: str = Field(min_length=3, max_length=60, pattern=r"^[A-Za-z0-9._-]+$")


def _validar(sessao: Session, dados: UsuarioEntrada):
    if dados.perfil not in PERFIS:
        _erro("Perfil inválido.")
    if dados.perfil == "supervisor":
        if dados.supervisor_id is None or sessao.get(Supervisor, dados.supervisor_id) is None:
            _erro("Usuário com perfil supervisor precisa estar ligado a um supervisor.")


def _admins_ativos(sessao: Session) -> int:
    return sessao.scalar(select(func.count(Usuario.id)).where(Usuario.perfil == "admin", Usuario.ativo.is_(True)))


@rotas.get("/usuarios")
def listar_usuarios(sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    return [_usuario_json(u) for u in sessao.scalars(select(Usuario).order_by(Usuario.nome))]


@rotas.post("/usuarios")
def criar_usuario(dados: UsuarioNovo, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    _validar(sessao, dados)
    login_novo = dados.usuario.strip().lower()
    if sessao.scalar(select(Usuario).where(Usuario.usuario == login_novo)):
        _erro("Já existe um usuário com esse login.")
    senha = gerar_senha()
    usuario = Usuario(nome=dados.nome.strip(), usuario=login_novo, senha_hash=gerar_hash(senha),
                      perfil=dados.perfil, supervisor_id=dados.supervisor_id if dados.perfil == "supervisor" else None)
    sessao.add(usuario)
    sessao.commit()
    # A senha provisória só aparece agora; no banco fica apenas o hash.
    return {"id": usuario.id, "senha_provisoria": senha}


@rotas.put("/usuarios/{ident}")
def alterar_usuario(ident: int, dados: UsuarioEntrada, sessao: Session = Depends(db.sessao_db),
                    eu: Usuario = Depends(exigir_admin)):
    usuario = sessao.get(Usuario, ident) or _erro("Usuário não encontrado.", 404)
    _validar(sessao, dados)
    if usuario.perfil == "admin" and usuario.ativo and dados.perfil != "admin" and _admins_ativos(sessao) <= 1:
        _erro("O sistema precisa de pelo menos um administrador ativo.")
    usuario.nome = dados.nome.strip()
    usuario.perfil = dados.perfil
    usuario.supervisor_id = dados.supervisor_id if dados.perfil == "supervisor" else None
    sessao.commit()
    return {"ok": True}


@rotas.post("/usuarios/{ident}/nova-senha")
def nova_senha(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    usuario = sessao.get(Usuario, ident) or _erro("Usuário não encontrado.", 404)
    senha = gerar_senha()
    usuario.senha_hash = gerar_hash(senha)
    nova_chave_de_sessao(usuario)  # quem estava logado com a senha antiga cai
    registrar_sucesso(usuario)  # também desbloqueia
    sessao.commit()
    return {"senha_provisoria": senha}


@rotas.post("/usuarios/{ident}/inativar")
def inativar_usuario(ident: int, sessao: Session = Depends(db.sessao_db), eu: Usuario = Depends(exigir_admin)):
    usuario = sessao.get(Usuario, ident) or _erro("Usuário não encontrado.", 404)
    if usuario.id == eu.id:
        _erro("Você não pode inativar o seu próprio usuário.")
    if usuario.perfil == "admin" and _admins_ativos(sessao) <= 1:
        _erro("O sistema precisa de pelo menos um administrador ativo.")
    usuario.ativo = False
    sessao.commit()
    return {"ok": True}


@rotas.post("/usuarios/{ident}/reativar")
def reativar_usuario(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    usuario = sessao.get(Usuario, ident) or _erro("Usuário não encontrado.", 404)
    usuario.ativo = True
    sessao.commit()
    return {"ok": True}
