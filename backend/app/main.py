"""API do Controle de Promotores (FastAPI)."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import cadastros, db, faturamento, pendencias, usuarios
from .autenticacao import exigir_admin, usuario_logado
from .calculos import Filtros, calcular_painel, opcoes_de_filtro, tipos_de_nota
from .carga import aplicar_promotores, aplicar_roteiro, preparar_banco
from .config import FRONTEND_DIST, PRODUCAO, SECRET_KEY, SESSAO_HORAS
from .dados import colaboradores_pendentes, tabelas_do_calculo
from .importacao import ErroImportacao, importar_promotores, importar_roteiro, ler_totais_abas_uf
from .modelos import Pdv, Roteiro, Usuario
from .regras import gravar_regras, ler_regras

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def ciclo_de_vida(_app):
    # Cria/atualiza as tabelas (migrations), o primeiro administrador e converte dados antigos.
    preparar_banco()
    yield


app = FastAPI(title="Controle de Promotores", lifespan=ciclo_de_vida,
              docs_url=None if PRODUCAO else "/docs", redoc_url=None,
              openapi_url=None if PRODUCAO else "/openapi.json")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=SESSAO_HORAS * 3600,
                   same_site="lax", https_only=PRODUCAO)
app.include_router(usuarios.rotas)
app.include_router(cadastros.rotas)
app.include_router(pendencias.rotas)


@app.get("/health")
def health():
    return {"status": "ok"}


def _erro(mensagem: str, status: int = 400):
    raise HTTPException(status_code=status, detail=mensagem)


# ---------------------------------------------------------------------------
# Importações
# ---------------------------------------------------------------------------

async def _ler_arquivo(arquivo: UploadFile) -> tuple[bytes, str]:
    nome = arquivo.filename or ""
    if not nome.lower().endswith((".xlsx", ".xlsm", ".csv")):
        _erro("Envie um arquivo .xlsx, .xlsm ou .csv.")
    return await arquivo.read(), nome


def _cnpjs_no_roteiro(sessao: Session) -> set[str]:
    return set(sessao.scalars(select(Pdv.cnpj_cpf).join(Roteiro, Roteiro.pdv_id == Pdv.id)).all())


def _importar_cadastro(sessao: Session, tipo: str, conteudo: bytes, nome: str, usuario: Usuario) -> dict:
    leitor, aplicar = {"promotores": (importar_promotores, aplicar_promotores),
                       "roteiro": (importar_roteiro, aplicar_roteiro)}[tipo]
    tabela, resumo = leitor(conteudo, nome)
    resumo["cadastros"] = aplicar(sessao, tabela)
    faturamento.registrar(sessao, tipo, nome, usuario.usuario, len(tabela), resumo["avisos"])
    pendentes = colaboradores_pendentes(sessao)
    if tipo == "roteiro" and pendentes:
        resumo["avisos"].append(
            f"{len(pendentes)} colaborador(es) do roteiro não encontrados nos promotores (viraram pendência): "
            + ", ".join(pendentes[:10]) + (" …" if len(pendentes) > 10 else ""))
    return resumo


@app.post("/api/importacoes/faturamento/previa")
async def previa_faturamento(arquivo: UploadFile = File(...), sessao: Session = Depends(db.sessao_db),
                             usuario: Usuario = Depends(exigir_admin)):
    """Lê o arquivo do ERP e mostra o resumo antes de gravar."""
    conteudo, nome = await _ler_arquivo(arquivo)
    try:
        return faturamento.preparar_previa(conteudo, nome, usuario.usuario, _cnpjs_no_roteiro(sessao))
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
        return _importar_cadastro(sessao, tipo, conteudo, nome, usuario)
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
def opcoes(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    promotores, _custos, roteiro = tabelas_do_calculo(sessao)
    dados = opcoes_de_filtro(faturamento.faturamento_mensal(), promotores, roteiro, colaboradores_pendentes(sessao))
    dados["importacoes"] = faturamento.ultimas_por_tipo(sessao)
    dados["pendencias"] = pendencias.contar_pendencias(pendencias.calcular_pendencias(sessao))
    dados["reimportar_faturamento"] = faturamento.tem_faturamento_antigo()
    return dados


@app.get("/api/painel")
def painel(inicio: str, fim: str, supervisor: str = "", promotor: str = "", uf: str = "", cidade: str = "",
           sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    try:
        filtros = Filtros(inicio=inicio, fim=fim, supervisor=supervisor, promotor=promotor, uf=uf, cidade=cidade)
        indice_inicio = int(inicio[:4]) * 12 + int(inicio[5:7])
        indice_fim = int(fim[:4]) * 12 + int(fim[5:7])
    except (ValueError, IndexError) as erro:
        raise HTTPException(status_code=400, detail="Período inválido. Use AAAA-MM.") from erro
    if abs(indice_fim - indice_inicio) > 60:
        _erro("Escolha um período de até 5 anos.")
    promotores, custos, roteiro = tabelas_do_calculo(sessao)
    return calcular_painel(faturamento.faturamento_mensal(), promotores, roteiro, filtros, ler_regras(), custos)


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
