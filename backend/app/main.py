"""API do Controle de Promotores (FastAPI)."""
import hmac
import logging

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import db
from .calculos import Filtros, calcular_painel, opcoes_de_filtro, tipos_de_nota
from .config import (APP_SENHA, APP_USUARIO, ARQUIVO_ENV, FRONTEND_DIST, PRODUCAO,
                     SECRET_KEY, SESSAO_HORAS)
from .importacao import (ErroImportacao, importar_faturamento, importar_promotores,
                         importar_roteiro, vincular_roteiro)
from .regras import gravar_regras, ler_regras

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Controle de Promotores", docs_url=None if PRODUCAO else "/docs",
              redoc_url=None, openapi_url=None if PRODUCAO else "/openapi.json")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=SESSAO_HORAS * 3600,
                   same_site="lax", https_only=PRODUCAO)

# Ajuda a conferir o login sem mostrar a senha no terminal.
if not APP_USUARIO or not APP_SENHA:
    log.warning("APP_USUARIO/APP_SENHA não definidos (%s): ninguém conseguirá entrar.",
                f"arquivo {ARQUIVO_ENV}" if ARQUIVO_ENV.exists() else f"{ARQUIVO_ENV} não encontrado")
else:
    log.info("Login configurado para o usuário '%s' (senha com %d caracteres).", APP_USUARIO, len(APP_SENHA))


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def exigir_login(request: Request) -> str:
    usuario = request.session.get("usuario")
    if not usuario:
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre novamente.")
    return usuario


class Credenciais(BaseModel):
    usuario: str
    senha: str


@app.post("/api/login")
def login(dados: Credenciais, request: Request):
    usuario_ok = hmac.compare_digest(dados.usuario.strip().encode(), APP_USUARIO.encode())
    senha_ok = hmac.compare_digest(dados.senha.encode(), APP_SENHA.encode())
    if not (APP_USUARIO and APP_SENHA and usuario_ok and senha_ok):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")
    request.session.clear()
    request.session["usuario"] = APP_USUARIO
    return {"usuario": APP_USUARIO}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/sessao")
def sessao(usuario: str = Depends(exigir_login)):
    return {"usuario": usuario}


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
async def importar(tipo: str, arquivo: UploadFile = File(...), _: str = Depends(exigir_login)):
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
    else:
        db.substituir_tabela(tipo, tabela)

    # O histórico guarda só os avisos do próprio arquivo; os colaboradores sem vínculo
    # são recalculados na aba de avisos, porque mudam quando a outra planilha é importada.
    if tipo == "faturamento":
        regras = ler_regras()
        sem_regra = [t["tipo"] for t in resumo["tipos_nf"] if t["chave"] not in regras["tipos_nf"]]
        if sem_regra:
            resumo["avisos"].append(
                "Tipos de nota sem regra definida (ficam fora do faturamento até você escolher em "
                "Regras do cálculo): " + ", ".join(sem_regra))

    db.registrar_importacao(tipo, nome, len(tabela), "; ".join(resumo["avisos"]))

    # Roteiro e promotores dependem um do outro: avisa nomes que não bateram.
    roteiro, promotores = db.ler_tabela("roteiro"), db.ler_tabela("promotores")
    if tipo in ("roteiro", "promotores") and not roteiro.empty and not promotores.empty:
        _, sem_vinculo = vincular_roteiro(roteiro, promotores)
        if sem_vinculo:
            resumo["avisos"].append(
                f"{len(sem_vinculo)} colaborador(es) do roteiro não encontrados na lista de promotores: "
                + ", ".join(sem_vinculo[:10]) + (" …" if len(sem_vinculo) > 10 else ""))
    return resumo


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

@app.get("/api/opcoes")
def opcoes(_: str = Depends(exigir_login)):
    dados = opcoes_de_filtro(db.ler_tabela("faturamento"), db.ler_tabela("promotores"),
                             db.ler_tabela("roteiro"))
    dados["importacoes"] = db.ultimas_importacoes()
    return dados


@app.get("/api/painel")
def painel(inicio: str, fim: str, supervisor: str = "", promotor: str = "", uf: str = "",
           cidade: str = "", _: str = Depends(exigir_login)):
    try:
        filtros = Filtros(inicio=inicio, fim=fim, supervisor=supervisor, promotor=promotor,
                          uf=uf, cidade=cidade)
        return calcular_painel(db.ler_tabela("faturamento"), db.ler_tabela("promotores"),
                               db.ler_tabela("roteiro"), filtros, ler_regras())
    except ValueError as erro:
        raise HTTPException(status_code=400, detail="Período inválido. Use AAAA-MM.") from erro


# ---------------------------------------------------------------------------
# Regras do cálculo (ajustadas pelo usuário)
# ---------------------------------------------------------------------------

@app.get("/api/regras")
def obter_regras(_: str = Depends(exigir_login)):
    regras = ler_regras()
    return {"regras": regras, "tipos_nf": tipos_de_nota(db.ler_tabela("faturamento"), regras)}


@app.put("/api/regras")
def salvar_regras(dados: dict, _: str = Depends(exigir_login)):
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
