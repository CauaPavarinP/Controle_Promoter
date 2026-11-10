"""Tamanho máximo do que cada pedido pode enviar ao servidor, conferido ANTES de receber tudo.

Sem isso, qualquer usuário logado podia mandar centenas de MB para uma rota comum (ex.: 400 MB para /api/exportar
levaram o servidor a 1,37 GB de memória; o do Render tem 512 MB) e o limite dos uploads só era conferido depois de o
arquivo inteiro já estar no disco.

Middleware ASGI puro: recusa logo pelo cabeçalho Content-Length e, quando ele não vem (envio em partes), conta os
bytes recebidos e para no limite.
"""
import json

from starlette.exceptions import HTTPException

MB = 1024 * 1024
LIMITE_IMPORTACAO = 150 * MB   # planilhas (a real tem 64 MB)
LIMITE_EXPORTACAO = 20 * MB    # tabela que a tela manda para virar Excel (a maior real tem ~2 MB)
LIMITE_PADRAO = 1 * MB         # todo o resto (login, cadastros, regras…)


def limite_para(caminho: str) -> int:
    if caminho.startswith("/api/importacoes/"):
        return LIMITE_IMPORTACAO
    if caminho == "/api/exportar":
        return LIMITE_EXPORTACAO
    return LIMITE_PADRAO


class GrandeDemais(HTTPException):
    """HTTPException para o FastAPI repassar como está (outros erros na leitura do corpo ele troca por 400)."""

    def __init__(self, limite: int):
        super().__init__(status_code=413, detail=f"Envio grande demais (máximo {limite // MB} MB).")


async def _responder_413(send, limite: int) -> None:
    corpo = json.dumps({"detail": f"Envio grande demais (máximo {limite // MB} MB)."}, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(corpo)).encode())]})
    await send({"type": "http.response.body", "body": corpo})


class LimiteDeTamanho:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limite = limite_para(scope.get("path", ""))
        cabecalhos = dict(scope.get("headers") or [])
        declarado = cabecalhos.get(b"content-length")
        if declarado is not None:
            try:
                if int(declarado) > limite:
                    return await _responder_413(send, limite)
            except ValueError:
                return await _responder_413(send, limite)

        recebido = 0
        respondeu = False

        async def receber():
            nonlocal recebido
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                recebido += len(mensagem.get("body", b""))
                if recebido > limite:
                    raise GrandeDemais(limite)
            return mensagem

        async def enviar(mensagem):
            nonlocal respondeu
            if mensagem["type"] == "http.response.start":
                respondeu = True
            await send(mensagem)

        try:
            await self.app(scope, receber, enviar)
        except GrandeDemais:
            if not respondeu:
                await _responder_413(send, limite)
