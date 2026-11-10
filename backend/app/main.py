"""API do Controle de Promotores (FastAPI)."""
import asyncio
from dataclasses import astuple
import logging
import os
import shutil
import secrets
import tempfile
import threading
from contextlib import asynccontextmanager

from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.orm import Session
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .limites import LimiteDeTamanho
from . import cadastros, db, exportar, faturamento, pendencias, respostas_guardadas, usuarios
from .autenticacao import exigir_admin, usuario_logado
from .calculos import Filtros, calcular_painel, indice_mes, opcoes_de_filtro, resumo_faturamento, tipos_de_nota
from .carga import aplicar_promotores, aplicar_roteiro, preparar_banco
from .carga import trava_cadastros as _trava_cadastros
from .config import FRONTEND_DIST, PRODUCAO, SECRET_KEY, SESSAO_HORAS
from .dados import colaboradores_pendentes, tabelas_do_calculo
from .importacao import ErroImportacao, devolver_memoria, importar_promotores, importar_roteiro, ler_totais_abas_uf
from .modelos import Pdv, Roteiro, Usuario
from .regras import gravar_regras, ler_regras

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def ciclo_de_vida(_app):
    # Cria/atualiza as tabelas (migrations), o primeiro administrador e converte dados antigos.
    preparar_banco()
    faturamento.limpar_pasta_previas()
    if PRODUCAO:  # soma o faturamento já ao ligar (no servidor gratuito leva de segundos a minutos)
        threading.Thread(target=faturamento.aquecer_cache, daemon=True).start()
    yield


app = FastAPI(title="Controle de Promotores", lifespan=ciclo_de_vida,
              docs_url=None if PRODUCAO else "/docs", redoc_url=None,
              openapi_url=None if PRODUCAO else "/openapi.json")
# Tamanho máximo de cada envio, conferido antes de receber tudo (app/limites.py).
app.add_middleware(LimiteDeTamanho)
# Respostas JSON comprimidas: o Resumo (~800 KB) e o Faturamento (~1,5 MB) viajam ~10x menores.
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=SESSAO_HORAS * 3600,
                   same_site="lax", https_only=PRODUCAO)

# Cabeçalhos de segurança em todas as respostas: o site não abre dentro de outro (clickjacking), o navegador só
# roda scripts do próprio site e não "adivinha" o tipo dos arquivos.
CABECALHOS_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                                "base-uri 'self'; form-action 'self'; object-src 'none'"),
}
METODOS_QUE_ALTERAM = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def protecoes(request: Request, chamar_proximo):
    # Pedido que altera dados vindo de outro site (CSRF): o cookie já é SameSite=Lax; esta é a segunda barreira.
    if request.method in METODOS_QUE_ALTERAM and request.url.path.startswith("/api/"):
        origem = request.headers.get("origin")
        if origem and urlsplit(origem).hostname != (request.url.hostname or ""):
            return JSONResponse({"detail": "Pedido recusado: origem diferente do site."}, status_code=403)
    resposta = await chamar_proximo(request)
    if request.method in METODOS_QUE_ALTERAM:
        respostas_guardadas.dados_mudaram()  # qualquer alteração invalida o Resumo/Faturamento guardados
    for nome, valor in CABECALHOS_SEGURANCA.items():
        resposta.headers.setdefault(nome, valor)
    if PRODUCAO:
        resposta.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    return resposta


def _numero_curto(valor) -> str:
    return f"{valor:g}" if isinstance(valor, (int, float)) else str(valor)


@app.exception_handler(RequestValidationError)
async def dados_invalidos(_request: Request, erro: RequestValidationError):
    """Erro de validação em texto (a tela mostra `detail` como mensagem; a lista do FastAPI virava "[object Object]")."""
    partes = []
    for item in erro.errors():
        campo = str(item.get("loc", ["", "?"])[-1])
        limites = item.get("ctx") or {}
        if "le" in limites:
            partes.append(f"{campo}: no máximo {_numero_curto(limites['le'])}")
        elif "ge" in limites:
            partes.append(f"{campo}: no mínimo {_numero_curto(limites['ge'])}")
        else:
            partes.append(f"{campo}: valor inválido")
    return JSONResponse({"detail": "Dados inválidos — " + "; ".join(partes)}, status_code=422)


@app.exception_handler(Exception)
async def erro_inesperado(request: Request, erro: Exception):
    """Qualquer falha não prevista vira uma mensagem em `detail` (a tela mostrava só "Erro ao falar com o servidor").

    O detalhe técnico fica no log do servidor com o mesmo número de referência, para achar depois.
    """
    referencia = secrets.token_hex(3).upper()
    log.error("Erro inesperado (ref. %s) em %s %s: %r", referencia, request.method, request.url.path, erro)
    if isinstance(erro, DBAPIError) and "too long" in str(erro.orig):
        mensagem = ("Algum valor é maior do que o sistema aceita (por exemplo, um CNPJ com mais de 14 dígitos ou "
                    "um texto muito longo). Confira o arquivo e tente de novo.")
    elif isinstance(erro, SATimeoutError):
        mensagem = "O servidor está ocupado com outros pedidos. Espere um minuto e tente de novo."
    else:
        mensagem = "Erro inesperado no servidor."
    return JSONResponse({"detail": f"{mensagem} (ref. {referencia})"}, status_code=500)


app.include_router(usuarios.rotas)
app.include_router(cadastros.rotas)
app.include_router(pendencias.rotas)
app.include_router(exportar.rotas)


@app.get("/health")
def health():
    return {"status": "ok"}


def _erro(mensagem: str, status: int = 400):
    raise HTTPException(status_code=status, detail=mensagem)


# ---------------------------------------------------------------------------
# Importações
# ---------------------------------------------------------------------------

# A planilha inteira tem ~63 MB; o limite evita que um arquivo enorme derrube o servidor.
TAMANHO_MAXIMO_MB = 150
OCUPADO = ("O servidor já está lendo outra planilha (faturamento ou cadastros). Espere ela terminar e envie de "
           "novo: duas leituras juntas passariam do limite de memória do servidor.")


async def _ler_arquivo(arquivo: UploadFile) -> tuple[bytes, str]:
    nome = arquivo.filename or ""
    if not nome.lower().endswith((".xlsx", ".xlsm", ".csv")):
        _erro("Envie um arquivo .xlsx, .xlsm ou .csv.")
    if arquivo.size is not None and arquivo.size > TAMANHO_MAXIMO_MB * 1024 * 1024:
        _erro(f"Arquivo grande demais (máximo {TAMANHO_MAXIMO_MB} MB).", 413)
    return await arquivo.read(), nome


def _cnpjs_no_roteiro(sessao: Session) -> set[str]:
    return set(sessao.scalars(select(Pdv.cnpj_cpf).join(Roteiro, Roteiro.pdv_id == Pdv.id)).all())


def _importar_cadastro_uma_vez(sessao: Session, tipo: str, conteudo: bytes, nome: str, usuario: Usuario) -> dict:
    if faturamento.lendo_agora() or not _trava_cadastros.acquire(blocking=False):
        raise ErroImportacao(OCUPADO)
    try:
        return _importar_cadastro(sessao, tipo, conteudo, nome, usuario)
    finally:
        _trava_cadastros.release()
        devolver_memoria()


def _importar_cadastro(sessao: Session, tipo: str, conteudo: bytes, nome: str, usuario: Usuario) -> dict:
    leitor, aplicar = {"promotores": (importar_promotores, aplicar_promotores),
                       "roteiro": (importar_roteiro, aplicar_roteiro)}[tipo]
    tabela, resumo = leitor(conteudo, nome)
    resumo["cadastros"] = aplicar(sessao, tabela)
    resumo["avisos"] += resumo["cadastros"].pop("avisos", [])
    faturamento.registrar(sessao, tipo, nome, usuario.usuario, len(tabela), resumo["avisos"])
    pendentes = colaboradores_pendentes(sessao)
    if tipo == "roteiro" and pendentes:
        resumo["avisos"].append(
            f"{len(pendentes)} colaborador(es) do roteiro não encontrados nos promotores (viraram pendência): "
            + ", ".join(pendentes[:10]) + (" …" if len(pendentes) > 10 else ""))
    return resumo


ESPERA_PREVIA_SEGUNDOS = 15


@app.post("/api/importacoes/faturamento/previa")
async def previa_faturamento(arquivo: UploadFile = File(...), sessao: Session = Depends(db.sessao_db),
                             usuario: Usuario = Depends(exigir_admin)):
    """Lê o arquivo do ERP e mostra o resumo antes de gravar.

    O arquivo é salvo no disco e lido em segundo plano. Se terminar em ~15 s, a resposta já é o resumo; senão
    vem {"situacao": "lendo", "leitura": código} e a tela pergunta o andamento em /leitura/{código}.
    """
    nome = arquivo.filename or ""
    if not nome.lower().endswith((".xlsx", ".xlsm", ".csv")):
        _erro("Envie um arquivo .xlsx, .xlsm ou .csv.")
    if arquivo.size is not None and arquivo.size > TAMANHO_MAXIMO_MB * 1024 * 1024:
        _erro(f"Arquivo grande demais (máximo {TAMANHO_MAXIMO_MB} MB).", 413)
    if _trava_cadastros.locked():
        _erro(OCUPADO)

    def salvar():
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(nome)[1].lower()) as arquivo_disco:
            shutil.copyfileobj(arquivo.file, arquivo_disco, length=1024 * 1024)
        return arquivo_disco
    destino = await run_in_threadpool(salvar)
    try:
        codigo = faturamento.iniciar_leitura(destino.name, nome, usuario.usuario, _cnpjs_no_roteiro(sessao))
        resposta = faturamento.andamento_da_leitura(codigo)
        for _ in range(int(ESPERA_PREVIA_SEGUNDOS * 2)):  # arquivo pequeno já volta com o resumo
            if resposta["situacao"] != "lendo":
                break
            await asyncio.sleep(0.5)
            resposta = faturamento.andamento_da_leitura(codigo)
        return resposta
    except ErroImportacao as erro:
        _erro(str(erro))


@app.get("/api/importacoes/faturamento/leitura/{codigo}")
def andamento_da_leitura(codigo: str, _=Depends(exigir_admin)):
    """Andamento da leitura do arquivo do ERP: {"situacao": "lendo", "linhas": n} ou o resumo pronto."""
    try:
        return faturamento.andamento_da_leitura(codigo)
    except ErroImportacao as erro:
        _erro(str(erro))


@app.post("/api/importacoes/planilha")
async def importar_planilha(arquivo: UploadFile = File(...), sessao: Session = Depends(db.sessao_db),
                            usuario: Usuario = Depends(exigir_admin)):
    """Importação inicial: a planilha "ROTEIROS X FATURAMENTOS" inteira.

    Grava promotores e roteiro nos cadastros, guarda os totais das abas por UF para a conferência
    e devolve a pré-visualização do faturamento (que o usuário ainda precisa confirmar).
    """
    conteudo, nome = await _ler_arquivo(arquivo)
    if faturamento.lendo_agora() or not _trava_cadastros.acquire(blocking=False):
        _erro(OCUPADO)
    try:
        return await run_in_threadpool(_importar_planilha_inteira, sessao, conteudo, nome, usuario)
    finally:
        _trava_cadastros.release()
        devolver_memoria()


def _importar_planilha_inteira(sessao: Session, conteudo: bytes, nome: str, usuario: Usuario) -> dict:
    resultado = {}
    for tipo in ("promotores", "roteiro"):
        try:
            resultado[tipo] = _importar_cadastro(sessao, tipo, conteudo, nome, usuario)
        except ErroImportacao as erro:
            resultado[tipo] = {"erro": str(erro)}
    try:
        resultado["faturamento"] = faturamento.preparar_previa(conteudo, nome, usuario.usuario, _cnpjs_no_roteiro(sessao))
    except ErroImportacao as erro:
        resultado["faturamento"] = {"erro": str(erro)}
    totais = ler_totais_abas_uf(conteudo, nome)
    if not totais.empty:
        meses = resultado["faturamento"].get("meses") or []
        ano = max(int(m[:4]) for m in meses) if meses else None
        if ano:
            pendencias.guardar_totais_planilha(totais, ano)
        resultado["conferencia"] = {"abas": sorted(totais["aba"].unique().tolist()), "ano": ano}
    return resultado


# Declarada depois de /planilha e /faturamento/previa para não "engolir" essas rotas.
@app.post("/api/importacoes/{tipo}")
async def importar_cadastro(tipo: str, arquivo: UploadFile = File(...), sessao: Session = Depends(db.sessao_db),
                            usuario: Usuario = Depends(exigir_admin)):
    """Promotores ou roteiro: grava direto nos cadastros (não apaga nada)."""
    if tipo not in ("promotores", "roteiro"):
        _erro("Tipo de importação inválido.", 404)
    conteudo, nome = await _ler_arquivo(arquivo)
    try:
        # Ler a planilha de 64 MB leva até 1 minuto no servidor gratuito: fora da linha principal, para as outras
        # telas continuarem respondendo enquanto isso.
        return await run_in_threadpool(_importar_cadastro_uma_vez, sessao, tipo, conteudo, nome, usuario)
    except ErroImportacao as erro:
        _erro(str(erro))


class Confirmacao(BaseModel):
    substituir: bool = False


@app.post("/api/importacoes/faturamento/{token}/confirmar")
def confirmar_faturamento(token: str, dados: Confirmacao, _=Depends(exigir_admin)):
    regras = ler_regras()
    try:
        resultado = faturamento.confirmar(token, dados.substituir)
    except ErroImportacao as erro:
        _erro(str(erro))
    sem_regra = [t["tipo"] for t in tipos_de_nota(faturamento.faturamento_mensal(), regras) if not t["na_lista"]]
    if sem_regra and regras["tipos_nf_padrao"] == "ignora":
        resultado["aviso"] = ("Tipos de nota sem regra (ficam fora do faturamento até você escolher em Regras do "
                              "cálculo): " + ", ".join(sem_regra))
    return resultado


@app.get("/api/importacoes")
def historico(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    return faturamento.historico(sessao)


@app.get("/api/importacoes/{ident}/erros")
def erros_da_importacao(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    return faturamento.erros_da_importacao(sessao, ident)


@app.post("/api/importacoes/{ident}/desfazer")
def desfazer(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    try:
        return faturamento.desfazer(sessao, ident)
    except ErroImportacao as erro:
        _erro(str(erro))


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

@app.get("/api/opcoes")
def opcoes(pedido: Request, sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    def calcular():
        promotores, _custos, roteiro = tabelas_do_calculo(sessao)
        dados = opcoes_de_filtro(faturamento.faturamento_mensal(), promotores, roteiro, colaboradores_pendentes(sessao))
        dados["importacoes"] = faturamento.ultimas_por_tipo(sessao)
        dados["reimportar_faturamento"] = faturamento.tem_faturamento_antigo()
        return dados
    return respostas_guardadas.responder(pedido, ("opcoes",), calcular)


# Até 5 anos por consulta (60 meses).
MESES_MAXIMOS = 60


@app.get("/api/painel")
def painel(pedido: Request, inicio: str, fim: str, supervisor: str = "", promotor: str = "", uf: str = "", cidade: str = "",
           pdv: str = "", sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    try:
        indice_inicio, indice_fim = indice_mes(inicio), indice_mes(fim)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    if abs(indice_fim - indice_inicio) >= MESES_MAXIMOS:
        _erro("Escolha um período de até 5 anos.")
    filtros = Filtros(inicio=inicio, fim=fim, supervisor=supervisor, promotor=promotor, uf=uf, cidade=cidade, pdv=pdv)

    def calcular():
        promotores, custos, roteiro = tabelas_do_calculo(sessao)
        return calcular_painel(faturamento.faturamento_mensal(), promotores, roteiro, filtros, ler_regras(), custos)
    return respostas_guardadas.responder(pedido, ("painel", *astuple(filtros)), calcular)


def _ano_mes(texto: str) -> tuple[int, int]:
    try:
        indice = indice_mes(texto)
    except ValueError:
        _erro("Mês inválido. Use AAAA-MM.")
    return indice // 12, indice % 12 + 1


@app.get("/api/faturamento")
def faturamento_do_erp(pedido: Request, inicio: str, fim: str, sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    """Aba Faturamento: o que veio do ERP no período, por UF e por cliente."""
    inicio_, fim_ = sorted([_ano_mes(inicio), _ano_mes(fim)])  # "De" depois de "Até": inverte
    return respostas_guardadas.responder(
        pedido, ("faturamento", inicio_, fim_),
        lambda: resumo_faturamento(faturamento.mensal_por_cliente(inicio_, fim_), ler_regras(), _cnpjs_no_roteiro(sessao)))


@app.get("/api/faturamento/itens")
def itens_de_um_mes(cnpj: str, mes: str, cod_cli: str = "", _=Depends(usuario_logado)):
    """Notas (itens) de um PDV num mês: o detalhe de um valor da grade mês a mês."""
    ano, numero = _ano_mes(mes)
    if len(cnpj) < 8:
        _erro("CNPJ inválido.")
    return faturamento.itens_do_cliente(cnpj, ano, numero, cod_cli, ler_regras())


# ---------------------------------------------------------------------------
# Regras do cálculo (ajustadas pelo administrador)
# ---------------------------------------------------------------------------

@app.get("/api/regras")
def obter_regras(_=Depends(usuario_logado)):
    regras = ler_regras()
    return {"regras": regras, "tipos_nf": tipos_de_nota(faturamento.faturamento_mensal(), regras)}


@app.put("/api/regras")
def salvar_regras(dados: dict, _=Depends(exigir_admin)):
    try:
        regras = gravar_regras(dados)
    except ValueError as erro:
        _erro(str(erro))
    return {"regras": regras, "tipos_nf": tipos_de_nota(faturamento.faturamento_mensal(), regras)}


# ---------------------------------------------------------------------------
# Front (React compilado)
# ---------------------------------------------------------------------------

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    def front(caminho: str):
        if caminho.startswith("api/"):
            raise HTTPException(status_code=404)
        arquivo = (FRONTEND_DIST / caminho).resolve()
        if caminho and arquivo.is_file() and FRONTEND_DIST.resolve() in arquivo.parents:
            return FileResponse(arquivo)
        return FileResponse(FRONTEND_DIST / "index.html")
