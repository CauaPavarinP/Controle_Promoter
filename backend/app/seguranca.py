"""Senhas (hash scrypt) e bloqueio após tentativas erradas."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

MAX_TENTATIVAS = 5
MINUTOS_BLOQUEIO = 15
_N, _R, _P = 2 ** 14, 8, 1


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    resumo = hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${sal.hex()}${resumo.hex()}"


def conferir_senha(senha: str, guardado: str) -> bool:
    try:
        _, sal, resumo = guardado.split("$")
        calculado = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=_N, r=_R, p=_P, dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado.hex(), resumo)


def gerar_senha() -> str:
    """Senha provisória, mostrada uma única vez para o administrador repassar."""
    return secrets.token_urlsafe(9)


def validar_nova_senha(senha: str) -> None:
    if len(senha) < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")


def esta_bloqueado(usuario) -> bool:
    return bool(usuario.bloqueado_ate and usuario.bloqueado_ate > datetime.now())


def registrar_falha(usuario) -> None:
    usuario.tentativas_falhas = (usuario.tentativas_falhas or 0) + 1
    if usuario.tentativas_falhas >= MAX_TENTATIVAS:
        usuario.bloqueado_ate = datetime.now() + timedelta(minutes=MINUTOS_BLOQUEIO)
        usuario.tentativas_falhas = 0


def registrar_sucesso(usuario) -> None:
    usuario.tentativas_falhas = 0
    usuario.bloqueado_ate = None


def nova_chave_de_sessao(usuario) -> str:
    """Troca a chave da sessão: quem estiver logado com a chave antiga cai (sair, troca de senha…)."""
    usuario.sessao_chave = secrets.token_hex(16)
    return usuario.sessao_chave


# Hash de uma senha qualquer, para o login de usuário inexistente levar o mesmo tempo que o de um que existe
# (sem isso dá para descobrir quais usuários existem medindo o tempo de resposta).
HASH_FALSO = gerar_hash(secrets.token_hex(8))
