"""Tamanho máximo do que cada pedido pode enviar ao servidor, conferido ANTES de receber tudo.

Sem isso, qualquer usuário logado podia mandar centenas de MB para uma rota comum (ex.: 400 MB para /api/exportar
levaram o servidor a 1,37 GB de memória; o do Render tem 512 MB) e o limite dos uploads só era conferido depois de o
arquivo inteiro já estar no disco.

Middleware ASGI puro: recusa logo pelo cabeçalho Content-Length e, quando ele não vem (envio em partes), conta os
bytes recebidos e para no limite.
"""
import json

from .config import LIMITE_FATURAMENTO_MB

from starlette.exceptions import HTTPException

MB = 1024 * 1024
LIMITE_IMPORTACAO = 150 * MB   # planilhas (a real tem 64 MB)
# Faturamento do ERP em texto (o ".xls" do Focco é HTML, TXT, CSV): lido aos poucos, usa pouca memória qualquer que
# seja o tamanho; o arquivo é grande porque cada célula leva a formatação junto (10 meses = ~500 MB).
# Faturamento: sem limite (None), a não ser que LIMITE_FATURAMENTO_MB esteja definido. Lido em partes (memória constante).
LIMITE_FATURAMENTO_TEXTO = LIMITE_FATURAMENTO_MB * MB if LIMITE_FATURAMENTO_MB else None
FOLGA_ENVIO = 1 * MB           # o envio do arquivo (multipart) tem cabeçalhos além do próprio arquivo
LIMITE_EXPORTACAO = 20 * MB    # tabela que a tela manda para virar Excel (a maior real tem ~2 MB)
LIMITE_PADRAO = 1 * MB         # todo o resto (login, cadastros, regras…)


def limite_para(caminho: str) -> int:
    if caminho == "/api/importacoes/faturamento/previa":
        return None if LIMITE_FATURAMENTO_TEXTO is None else LIMITE_FATURAMENTO_TEXTO + FOLGA_ENVIO
    if caminho.startswith("/api/importacoes/"):
        return LIMITE_IMPORTACAO + FOLGA_ENVIO
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
        if limite is None:   # rota sem limite de tamanho (faturamento): o envio vai direto para o disco
            return await self.app(scope, receive, send)
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
