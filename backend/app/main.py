"""API do Controle de Promotores (FastAPI)."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import cadastros, db, usuarios
from .autenticacao import exigir_admin, usuario_logado
from .calculos import Filtros, calcular_painel, opcoes_de_filtro, tipos_de_nota
from .carga import aplicar_promotores, aplicar_roteiro, preparar_banco
from .config import FRONTEND_DIST, PRODUCAO, SECRET_KEY, SESSAO_HORAS
from .dados import colaboradores_pendentes, tabelas_do_calculo
from .importacao import ErroImportacao, importar_faturamento, importar_promotores, importar_roteiro
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


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Importação
# ---------------------------------------------------------------------------

IMPORTADORES = {
    "faturamento": importar_faturamento,
    "promotores": importar_promotores,
    "roteiro": importar_roteiro,
}


@app.post("/api/importar/{tipo}")
async def importar(tipo: str, arquivo: UploadFile = File(...), sessao: Session = Depends(db.sessao_db),
                   _=Depends(exigir_admin)):
    if tipo not in IMPORTADORES:
        raise HTTPException(status_code=404, detail="Tipo de importação inválido.")
    nome = arquivo.filename or ""
    if not nome.lower().endswith((".xlsx", ".xlsm", ".csv")):
        raise HTTPException(status_code=400, detail="Envie um arquivo .xlsx, .xlsm ou .csv.")
    conteudo = await arquivo.read()
    try:
        tabela, resumo = IMPORTADORES[tipo](conteudo, nome)
    except ErroImportacao as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro

    if tipo == "faturamento":
        db.gravar_faturamento(tabela)
        regras = ler_regras()
        sem_regra = [t["tipo"] for t in resumo["tipos_nf"] if t["chave"] not in regras["tipos_nf"]]
        if sem_regra:
            resumo["avisos"].append(
                "Tipos de nota sem regra definida (ficam fora do faturamento até você escolher em "
                "Regras do cálculo): " + ", ".join(sem_regra))
    elif tipo == "promotores":
        resumo["cadastros"] = aplicar_promotores(sessao, tabela)
    else:
        resumo["cadastros"] = aplicar_roteiro(sessao, tabela)

    # O histórico guarda só os avisos do próprio arquivo; os colaboradores sem promotor
    # ficam na tabela de pendências e aparecem na aba de avisos.
    db.registrar_importacao(tipo, nome, len(tabela), "; ".join(resumo["avisos"]))
    pendentes = colaboradores_pendentes(sessao)
    if tipo == "roteiro" and pendentes:
        resumo["avisos"].append(
            f"{len(pendentes)} colaborador(es) do roteiro não encontrados nos promotores (viraram pendência): "
            + ", ".join(pendentes[:10]) + (" …" if len(pendentes) > 10 else ""))
    return resumo


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

@app.get("/api/opcoes")
def opcoes(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    promotores, _custos, roteiro = tabelas_do_calculo(sessao)
    dados = opcoes_de_filtro(db.ler_tabela("faturamento"), promotores, roteiro, colaboradores_pendentes(sessao))
    dados["importacoes"] = db.ultimas_importacoes()
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
        raise HTTPException(status_code=400, detail="Escolha um período de até 5 anos.")
    promotores, custos, roteiro = tabelas_do_calculo(sessao)
    return calcular_painel(db.ler_tabela("faturamento"), promotores, roteiro, filtros, ler_regras(), custos)


# ---------------------------------------------------------------------------
# Regras do cálculo (ajustadas pelo administrador)
# ---------------------------------------------------------------------------

@app.get("/api/regras")
def obter_regras(_=Depends(usuario_logado)):
    regras = ler_regras()
    return {"regras": regras, "tipos_nf": tipos_de_nota(db.ler_tabela("faturamento"), regras)}


@app.put("/api/regras")
def salvar_regras(dados: dict, _=Depends(exigir_admin)):
    try:
        regras = gravar_regras(dados)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from erro
    return {"regras": regras, "tipos_nf": tipos_de_nota(db.ler_tabela("faturamento"), regras)}


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
