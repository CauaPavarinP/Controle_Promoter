"""Respostas prontas do Resumo, do Faturamento e dos filtros, guardadas até os dados mudarem.

Montar o Resumo leva ~0,4 s num computador comum e alguns segundos no servidor gratuito (0,15 de processador), e
a tela pede de novo a cada troca de aba ou de filtro. Com os mesmos filtros e nada alterado desde a última vez, a
resposta guardada sai na hora.

Qualquer pedido que altera dados (POST/PUT/PATCH/DELETE: importar, cadastrar, editar, apagar, mudar regras…)
chama dados_mudaram() e tudo o que estava guardado deixa de valer. A data de hoje também faz parte da chave
(o custo vigente depende dela).
"""
import gzip
import threading
from collections import OrderedDict
from datetime import date

from fastapi.encoders import jsonable_encoder
from fastapi import Request
from fastapi.responses import JSONResponse, Response

MAXIMO = 24  # respostas guardadas (as mais antigas saem primeiro); cada uma tem de ~50 KB a ~1,5 MB

_trava = threading.Lock()
_guardadas: OrderedDict = OrderedDict()
_versao = 0


def dados_mudaram() -> None:
    global _versao
    with _trava:
        _versao += 1
        _guardadas.clear()


def responder(pedido: Request, chave: tuple, calcular) -> Response:
    """Devolve a resposta guardada para `chave` ou calcula, guarda e devolve.

    Guarda também a versão comprimida (gzip): comprimir 1,5 MB a cada pedido levava ~0,7 s no servidor gratuito.
    """
    with _trava:
        versao = _versao
        completa = (versao, date.today(), *chave)
        guardada = _guardadas.get(completa)
        if guardada is not None:
            _guardadas.move_to_end(completa)
    if guardada is None:
        corpo = JSONResponse(jsonable_encoder(calcular())).body
        guardada = (corpo, gzip.compress(corpo, compresslevel=6))
        with _trava:
            if versao == _versao:  # os dados mudaram durante o cálculo: não guarda uma resposta velha
                _guardadas[completa] = guardada
                while len(_guardadas) > MAXIMO:
                    _guardadas.popitem(last=False)
    corpo, comprimido = guardada
    if "gzip" in pedido.headers.get("accept-encoding", "").lower():
        return Response(content=comprimido, media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(content=corpo, media_type="application/json")
