"""Rotas dos cadastros: supervisores, promotores (com custos por competência), PDVs e roteiros.

Consultar: qualquer usuário logado. Incluir, alterar, inativar: só administrador.
Exclusão = inativar (o histórico continua no banco).
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from . import db
from .autenticacao import exigir_admin, usuario_logado
from .carga import custo_vigente
from .faturamento import dados_do_cliente
from .importacao import LIMITE_CUSTO_MENSAL, normalizar_cnpj, normalizar_texto
from .modelos import CustoPromotor, Pdv, Promotor, Roteiro, Supervisor

rotas = APIRouter(prefix="/api")


def _erro(mensagem: str, status: int = 400):
    raise HTTPException(status_code=status, detail=mensagem)


def _buscar(sessao: Session, modelo, ident: int):
    objeto = sessao.get(modelo, ident)
    if objeto is None:
        _erro("Registro não encontrado.", 404)
    return objeto


def vigente_em(roteiro: Roteiro, dia: date) -> bool:
    return roteiro.data_inicio <= dia and (roteiro.data_fim is None or roteiro.data_fim >= dia)


def situacao_roteiro(roteiro: Roteiro, dia: date) -> str:
    if roteiro.data_inicio > dia:
        return "agendado"
    return "vigente" if vigente_em(roteiro, dia) else "encerrado"


# ---------------------------------------------------------------------------
# Validação de CNPJ/CPF (dígitos verificadores)
# ---------------------------------------------------------------------------

def _digito(numeros: str, pesos: list[int]) -> str:
    resto = sum(int(n) * p for n, p in zip(numeros, pesos)) % 11
    return "0" if resto < 2 else str(11 - resto)


def documento_valido(digitos: str) -> bool:
    if len(set(digitos)) == 1:
        return False
    if len(digitos) == 14:
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        primeiro = _digito(digitos[:12], pesos)
        return digitos[12:] == primeiro + _digito(digitos[:12] + primeiro, [6] + pesos)
    if len(digitos) == 11:
        primeiro = _digito(digitos[:9], list(range(10, 1, -1)))
        return digitos[9:] == primeiro + _digito(digitos[:9] + primeiro, list(range(11, 1, -1)))
    return False


# ---------------------------------------------------------------------------
# Supervisores
# ---------------------------------------------------------------------------

class SupervisorEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=120)


class Transferencia(BaseModel):
    para_id: int


def _supervisor_json(s: Supervisor, hoje: date) -> dict:
    ativos = [p for p in s.promotores if p.ativo]
    pdvs = {r.pdv_id for p in ativos for r in p.roteiros if vigente_em(r, hoje)}
    return {"id": s.id, "nome": s.nome, "ativo": s.ativo, "promotores_ativos": len(ativos), "pdvs": len(pdvs)}


@rotas.get("/supervisores")
def listar_supervisores(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    supervisores = sessao.scalars(select(Supervisor).options(
        selectinload(Supervisor.promotores).selectinload(Promotor.roteiros)).order_by(Supervisor.nome))
    return [_supervisor_json(s, date.today()) for s in supervisores]


def _nome_supervisor_livre(sessao: Session, nome: str, ignorar_id: int | None = None):
    existente = sessao.scalar(select(Supervisor).where(func.lower(Supervisor.nome) == nome.strip().lower()))
    if existente and existente.id != ignorar_id:
        _erro("Já existe um supervisor com esse nome.")


@rotas.post("/supervisores")
def criar_supervisor(dados: SupervisorEntrada, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    _nome_supervisor_livre(sessao, dados.nome)
    supervisor = Supervisor(nome=dados.nome.strip())
    sessao.add(supervisor)
    sessao.commit()
    return {"id": supervisor.id}


@rotas.put("/supervisores/{ident}")
def alterar_supervisor(ident: int, dados: SupervisorEntrada, sessao: Session = Depends(db.sessao_db),
                       _=Depends(exigir_admin)):
    supervisor = _buscar(sessao, Supervisor, ident)
    _nome_supervisor_livre(sessao, dados.nome, ident)
    supervisor.nome = dados.nome.strip()
    sessao.commit()
    return {"ok": True}


@rotas.post("/supervisores/{ident}/inativar")
def inativar_supervisor(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    supervisor = _buscar(sessao, Supervisor, ident)
    if any(p.ativo for p in supervisor.promotores):
        _erro("Este supervisor ainda tem promotores ativos. Transfira a equipe para outro supervisor antes.")
    supervisor.ativo = False
    sessao.commit()
    return {"ok": True}


@rotas.post("/supervisores/{ident}/reativar")
def reativar_supervisor(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    _buscar(sessao, Supervisor, ident).ativo = True
    sessao.commit()
    return {"ok": True}


@rotas.post("/supervisores/{ident}/transferir")
def transferir_equipe(ident: int, dados: Transferencia, sessao: Session = Depends(db.sessao_db),
                      _=Depends(exigir_admin)):
    origem = _buscar(sessao, Supervisor, ident)
    destino = _buscar(sessao, Supervisor, dados.para_id)
    if destino.id == origem.id or not destino.ativo:
        _erro("Escolha outro supervisor, ativo, para receber a equipe.")
    ativos = [p for p in origem.promotores if p.ativo]
    for promotor in ativos:
        promotor.supervisor = destino
    sessao.commit()
    return {"transferidos": len(ativos)}


# ---------------------------------------------------------------------------
# Promotores e custos por competência
# ---------------------------------------------------------------------------

class CustoEntrada(BaseModel):
    # Teto por item (LIMITE_CUSTO_MENSAL): evita gravar um valor digitado errado como 600120.
    ano: int = Field(ge=2000, le=2100)
    mes: int = Field(ge=1, le=12)
    salario: float = Field(ge=0, le=LIMITE_CUSTO_MENSAL)
    ajuda_custo: float = Field(ge=0, le=LIMITE_CUSTO_MENSAL, default=0)
    vale_transporte: float = Field(ge=0, le=LIMITE_CUSTO_MENSAL, default=0)
    outros: float = Field(ge=0, le=LIMITE_CUSTO_MENSAL, default=0)


class PromotorEntrada(BaseModel):
    codigo: str = Field(min_length=1, max_length=30)
    nome: str = Field(min_length=1, max_length=150)
    data_admissao: date | None = None
    municipio: str = ""
    uf: str = Field(default="", max_length=2)
    supervisor_id: int
    funcao: str = "Promotor"
    observacao: str = ""


class PromotorNovo(PromotorEntrada):
    custo: CustoEntrada


class Desligamento(BaseModel):
    data_desligamento: date


def _custo_json(c: CustoPromotor) -> dict:
    return {"id": c.id, "ano": c.ano, "mes": c.mes, "salario": c.salario, "ajuda_custo": c.ajuda_custo,
            "vale_transporte": c.vale_transporte, "outros": c.outros, "total": c.total}


def _promotor_json(p: Promotor, hoje: date) -> dict:
    atual = custo_vigente(p, hoje.year, hoje.month) or (p.custos[0] if p.custos else None)
    return {
        "id": p.id, "codigo": p.codigo, "nome": p.nome,
        "data_admissao": p.data_admissao, "data_desligamento": p.data_desligamento,
        "municipio": p.municipio, "uf": p.uf, "funcao": p.funcao, "observacao": p.observacao, "ativo": p.ativo,
        "supervisor_id": p.supervisor_id, "supervisor": p.supervisor.nome if p.supervisor else "",
        "custo_atual": atual.total if atual else None,
        "lojas_vigentes": sum(1 for r in p.roteiros if vigente_em(r, hoje)),
    }


def _validar_promotor(sessao: Session, dados: PromotorEntrada, ignorar_id: int | None = None):
    existente = sessao.scalar(select(Promotor).where(Promotor.codigo == dados.codigo.strip()))
    if existente and existente.id != ignorar_id:
        _erro(f"O código {dados.codigo} já é do promotor {existente.nome}.")
    supervisor = sessao.get(Supervisor, dados.supervisor_id)
    if supervisor is None or not supervisor.ativo:
        _erro("Escolha um supervisor ativo.")


def _preencher_promotor(promotor: Promotor, dados: PromotorEntrada):
    promotor.codigo = dados.codigo.strip()
    promotor.nome = dados.nome.strip()
    promotor.data_admissao = dados.data_admissao
    promotor.municipio = dados.municipio.strip()
    promotor.uf = dados.uf.strip().upper()
    promotor.supervisor_id = dados.supervisor_id
    promotor.funcao = dados.funcao.strip() or "Promotor"
    promotor.observacao = dados.observacao


@rotas.get("/promotores")
def listar_promotores(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    promotores = sessao.scalars(select(Promotor).options(
        selectinload(Promotor.custos), selectinload(Promotor.supervisor), selectinload(Promotor.roteiros))
        .order_by(Promotor.nome))
    hoje = date.today()
    return [_promotor_json(p, hoje) for p in promotores]


@rotas.get("/promotores/{ident}")
def detalhar_promotor(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    promotor = _buscar(sessao, Promotor, ident)
    hoje = date.today()
    dados = _promotor_json(promotor, hoje)
    dados["custos"] = [_custo_json(c) for c in reversed(promotor.custos)]
    dados["roteiros"] = [_roteiro_json(r, hoje) for r in sorted(
        promotor.roteiros, key=lambda r: (not vigente_em(r, hoje), r.pdv.nome_fantasia))]
    return dados


@rotas.post("/promotores")
def criar_promotor(dados: PromotorNovo, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    _validar_promotor(sessao, dados)
    promotor = Promotor()
    _preencher_promotor(promotor, dados)
    promotor.custos.append(CustoPromotor(**dados.custo.model_dump()))
    sessao.add(promotor)
    sessao.commit()
    return {"id": promotor.id}


@rotas.put("/promotores/{ident}")
def alterar_promotor(ident: int, dados: PromotorEntrada, sessao: Session = Depends(db.sessao_db),
                     _=Depends(exigir_admin)):
    promotor = _buscar(sessao, Promotor, ident)
    _validar_promotor(sessao, dados, ident)
    _preencher_promotor(promotor, dados)
    sessao.commit()
    return {"ok": True}


@rotas.post("/promotores/{ident}/inativar")
def inativar_promotor(ident: int, dados: Desligamento, sessao: Session = Depends(db.sessao_db),
                      _=Depends(exigir_admin)):
    """Desliga o promotor e encerra os roteiros vigentes na data do desligamento."""
    promotor = _buscar(sessao, Promotor, ident)
    encerrados = 0
    for roteiro in promotor.roteiros:
        if roteiro.data_fim is None or roteiro.data_fim > dados.data_desligamento:
            roteiro.data_fim = max(dados.data_desligamento, roteiro.data_inicio)
            encerrados += 1
    promotor.ativo = False
    promotor.data_desligamento = dados.data_desligamento
    sessao.commit()
    return {"roteiros_encerrados": encerrados}


@rotas.post("/promotores/{ident}/reativar")
def reativar_promotor(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    promotor = _buscar(sessao, Promotor, ident)
    promotor.ativo = True
    promotor.data_desligamento = None
    sessao.commit()
    return {"ok": True}


@rotas.post("/promotores/{ident}/custos")
def registrar_custo(ident: int, dados: CustoEntrada, sessao: Session = Depends(db.sessao_db),
                    _=Depends(exigir_admin)):
    """Reajuste: vale a partir do mês informado, sem mudar os meses anteriores."""
    promotor = _buscar(sessao, Promotor, ident)
    custo = next((c for c in promotor.custos if (c.ano, c.mes) == (dados.ano, dados.mes)), None)
    if custo is None:
        custo = CustoPromotor(ano=dados.ano, mes=dados.mes)
        promotor.custos.append(custo)
    for campo in ("salario", "ajuda_custo", "vale_transporte", "outros"):
        setattr(custo, campo, getattr(dados, campo))
    sessao.commit()
    return {"id": custo.id}


@rotas.delete("/promotores/{ident}/custos/{custo_id}")
def excluir_custo(ident: int, custo_id: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    custo = _buscar(sessao, CustoPromotor, custo_id)
    if custo.promotor_id != ident:
        _erro("Registro não encontrado.", 404)
    if len(custo.promotor.custos) == 1:
        _erro("O promotor precisa ter pelo menos um custo. Altere o valor em vez de excluir.")
    sessao.delete(custo)
    sessao.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# PDVs
# ---------------------------------------------------------------------------

class PdvEntrada(BaseModel):
    cnpj_cpf: str = ""
    nome_fantasia: str = Field(min_length=1, max_length=200)
    razao_social: str = ""
    cod_cli_erp: str = ""
    cidade: str = ""
    uf: str = Field(default="", max_length=2)


def _pdv_json(pdv: Pdv, hoje: date, mesmo_cnpj: int = 1) -> dict:
    vigentes = [r for r in pdv.roteiros if vigente_em(r, hoje)]
    return {
        "id": pdv.id, "cnpj_cpf": pdv.cnpj_cpf, "nome_fantasia": pdv.nome_fantasia,
        "razao_social": pdv.razao_social, "cod_cli_erp": pdv.cod_cli_erp, "cidade": pdv.cidade, "uf": pdv.uf,
        "ativo": pdv.ativo, "promotores": [r.promotor.nome for r in vigentes],
        "lojas_mesmo_cnpj": mesmo_cnpj,
    }


def _preencher_pdv(sessao: Session, pdv: Pdv, dados: PdvEntrada, ignorar_id: int | None = None):
    cnpj = normalizar_cnpj(dados.cnpj_cpf)
    # Valida só CNPJ digitado ou alterado: PDV importado com CNPJ inválido continua editável
    # (aparece em Pendências para corrigir).
    if cnpj and cnpj != pdv.cnpj_cpf and not documento_valido(cnpj):
        _erro("CNPJ/CPF inválido: confira os números (dígito verificador não confere).")
    chave = normalizar_texto(dados.nome_fantasia)
    existente = sessao.scalar(select(Pdv).where(Pdv.cnpj_cpf == cnpj, Pdv.nome_chave == chave))
    if existente and existente.id != ignorar_id:
        _erro("Já existe um PDV com esse CNPJ e esse nome.")
    pdv.cnpj_cpf, pdv.nome_chave = cnpj, chave
    pdv.nome_fantasia = dados.nome_fantasia.strip()
    pdv.razao_social = dados.razao_social.strip()
    pdv.cod_cli_erp = dados.cod_cli_erp.strip()
    pdv.cidade = dados.cidade.strip().upper()
    pdv.uf = dados.uf.strip().upper()


@rotas.get("/pdvs")
def listar_pdvs(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    pdvs = sessao.scalars(select(Pdv).options(
        selectinload(Pdv.roteiros).selectinload(Roteiro.promotor)).order_by(Pdv.nome_fantasia)).all()
    por_cnpj = {}
    for pdv in pdvs:
        if pdv.cnpj_cpf:
            por_cnpj[pdv.cnpj_cpf] = por_cnpj.get(pdv.cnpj_cpf, 0) + 1
    hoje = date.today()
    return [_pdv_json(p, hoje, por_cnpj.get(p.cnpj_cpf, 1)) for p in pdvs]


@rotas.get("/pdvs/sugestao")
def sugerir_pdv(cnpj: str, _=Depends(usuario_logado)):
    """Dados do cliente no faturamento importado, para preencher o cadastro do PDV."""
    return dados_do_cliente(normalizar_cnpj(cnpj))


@rotas.post("/pdvs")
def criar_pdv(dados: PdvEntrada, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    pdv = Pdv()
    _preencher_pdv(sessao, pdv, dados)
    sessao.add(pdv)
    sessao.commit()
    return {"id": pdv.id}


@rotas.put("/pdvs/{ident}")
def alterar_pdv(ident: int, dados: PdvEntrada, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    pdv = _buscar(sessao, Pdv, ident)
    _preencher_pdv(sessao, pdv, dados, ident)
    sessao.commit()
    return {"ok": True}


@rotas.post("/pdvs/{ident}/inativar")
def inativar_pdv(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    pdv = _buscar(sessao, Pdv, ident)
    if any(vigente_em(r, date.today()) or (r.data_fim is None) for r in pdv.roteiros):
        _erro("Este PDV ainda está no roteiro de um promotor. Encerre o vínculo em Roteiros antes.")
    pdv.ativo = False
    sessao.commit()
    return {"ok": True}


@rotas.post("/pdvs/{ident}/reativar")
def reativar_pdv(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    _buscar(sessao, Pdv, ident).ativo = True
    sessao.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Roteiros (vínculo promotor ↔ PDV com vigência)
# ---------------------------------------------------------------------------

class RoteiroNovo(BaseModel):
    promotor_id: int
    pdv_id: int
    data_inicio: date
    visitas_por_semana: int | None = Field(default=None, ge=1, le=7)
    dias_semana: str = ""
    observacao: str = ""


class RoteiroAlteracao(BaseModel):
    visitas_por_semana: int | None = Field(default=None, ge=1, le=7)
    dias_semana: str = ""
    observacao: str = ""


class Encerramento(BaseModel):
    data_fim: date


class Troca(BaseModel):
    promotor_id: int
    data: date


class TransferenciaLote(BaseModel):
    de_promotor_id: int
    para_promotor_id: int
    data: date


def _roteiro_json(r: Roteiro, hoje: date) -> dict:
    return {
        "id": r.id, "promotor_id": r.promotor_id, "promotor": r.promotor.nome, "promotor_codigo": r.promotor.codigo,
        "pdv_id": r.pdv_id, "pdv": r.pdv.nome_fantasia, "cnpj_cpf": r.pdv.cnpj_cpf,
        "cidade": r.pdv.cidade, "uf": r.pdv.uf,
        "data_inicio": r.data_inicio, "data_fim": r.data_fim, "vigente": vigente_em(r, hoje),
        "situacao": situacao_roteiro(r, hoje),
        "visitas_por_semana": r.visitas_por_semana, "dias_semana": r.dias_semana, "observacao": r.observacao,
    }


def _sobreposto(sessao: Session, promotor_id: int, pdv_id: int, inicio: date, ignorar_id: int | None = None) -> bool:
    """Já existe vínculo do mesmo promotor com o mesmo PDV cobrindo essa data em diante?"""
    consulta = select(Roteiro).where(Roteiro.promotor_id == promotor_id, Roteiro.pdv_id == pdv_id,
                                     or_(Roteiro.data_fim.is_(None), Roteiro.data_fim >= inicio))
    return any(r.id != ignorar_id for r in sessao.scalars(consulta))


def _promotor_ativo(sessao: Session, ident: int) -> Promotor:
    promotor = sessao.get(Promotor, ident)
    if promotor is None or not promotor.ativo:
        _erro("Escolha um promotor ativo.")
    return promotor


@rotas.get("/roteiros")
def listar_roteiros(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    roteiros = sessao.scalars(select(Roteiro).options(
        selectinload(Roteiro.promotor), selectinload(Roteiro.pdv))).all()
    hoje = date.today()
    vigentes_por_pdv = {}
    for r in roteiros:
        if vigente_em(r, hoje):
            vigentes_por_pdv[r.pdv_id] = vigentes_por_pdv.get(r.pdv_id, 0) + 1
    dados = []
    for r in sorted(roteiros, key=lambda r: (r.promotor.nome, r.pdv.nome_fantasia, r.data_inicio)):
        item = _roteiro_json(r, hoje)
        item["promotores_no_pdv"] = vigentes_por_pdv.get(r.pdv_id, 0)
        dados.append(item)
    return dados


@rotas.post("/roteiros")
def vincular(dados: RoteiroNovo, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    _promotor_ativo(sessao, dados.promotor_id)
    pdv = sessao.get(Pdv, dados.pdv_id)
    if pdv is None or not pdv.ativo:
        _erro("Escolha um PDV ativo.")
    if _sobreposto(sessao, dados.promotor_id, dados.pdv_id, dados.data_inicio):
        _erro("Este promotor já tem um vínculo com este PDV nessa data.")
    roteiro = Roteiro(**dados.model_dump())
    sessao.add(roteiro)
    sessao.commit()
    return {"id": roteiro.id}


class LojaNova(BaseModel):
    """Loja cadastrada direto na aba das UFs: o PDV e o vínculo com o promotor de uma vez."""
    pdv: PdvEntrada
    promotor_id: int
    data_inicio: date
    visitas_por_semana: int | None = Field(default=None, ge=1, le=7)


@rotas.post("/lojas")
def cadastrar_loja(dados: LojaNova, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    """Usa o PDV que já existe com esse CNPJ e nome; senão, cria. Depois vincula ao promotor."""
    _promotor_ativo(sessao, dados.promotor_id)
    cnpj, chave = normalizar_cnpj(dados.pdv.cnpj_cpf), normalizar_texto(dados.pdv.nome_fantasia)
    pdv = sessao.scalar(select(Pdv).where(Pdv.cnpj_cpf == cnpj, Pdv.nome_chave == chave))
    if pdv is None:
        pdv = Pdv()
        _preencher_pdv(sessao, pdv, dados.pdv)
        sessao.add(pdv)
        sessao.flush()
    elif not pdv.ativo:
        pdv.ativo = True
    if _sobreposto(sessao, dados.promotor_id, pdv.id, dados.data_inicio):
        _erro("Este promotor já atende essa loja nessa data.")
    roteiro = Roteiro(promotor_id=dados.promotor_id, pdv_id=pdv.id, data_inicio=dados.data_inicio,
                      visitas_por_semana=dados.visitas_por_semana)
    sessao.add(roteiro)
    sessao.commit()
    return {"pdv_id": pdv.id, "roteiro_id": roteiro.id}


@rotas.put("/roteiros/{ident}")
def alterar_roteiro(ident: int, dados: RoteiroAlteracao, sessao: Session = Depends(db.sessao_db),
                    _=Depends(exigir_admin)):
    roteiro = _buscar(sessao, Roteiro, ident)
    roteiro.visitas_por_semana = dados.visitas_por_semana
    roteiro.dias_semana = dados.dias_semana
    roteiro.observacao = dados.observacao
    sessao.commit()
    return {"ok": True}


@rotas.post("/roteiros/{ident}/encerrar")
def encerrar(ident: int, dados: Encerramento, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    roteiro = _buscar(sessao, Roteiro, ident)
    if dados.data_fim < roteiro.data_inicio:
        _erro("A data de encerramento não pode ser antes do início do vínculo.")
    roteiro.data_fim = dados.data_fim
    sessao.commit()
    return {"ok": True}


def _trocar(sessao: Session, roteiro: Roteiro, novo: Promotor, data: date) -> Roteiro:
    """Encerra o vínculo no dia anterior e abre outro para o novo promotor a partir da data."""
    if roteiro.data_fim is not None and roteiro.data_fim < data:
        _erro("Este vínculo já estava encerrado antes dessa data.")
    if data <= roteiro.data_inicio:
        _erro("A data da troca precisa ser depois do início do vínculo atual.")
    if novo.id == roteiro.promotor_id:
        _erro("Escolha um promotor diferente do atual.")
    if _sobreposto(sessao, novo.id, roteiro.pdv_id, data):
        _erro(f"{novo.nome} já tem vínculo com este PDV nessa data.")
    roteiro.data_fim = data - timedelta(days=1)
    novo_roteiro = Roteiro(promotor_id=novo.id, pdv_id=roteiro.pdv_id, data_inicio=data,
                           visitas_por_semana=roteiro.visitas_por_semana, dias_semana=roteiro.dias_semana,
                           observacao=roteiro.observacao)
    sessao.add(novo_roteiro)
    return novo_roteiro


@rotas.post("/roteiros/{ident}/trocar")
def trocar_promotor(ident: int, dados: Troca, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    roteiro = _buscar(sessao, Roteiro, ident)
    novo = _trocar(sessao, roteiro, _promotor_ativo(sessao, dados.promotor_id), dados.data)
    sessao.commit()
    return {"id": novo.id}


@rotas.post("/roteiros/transferir")
def transferir_lote(dados: TransferenciaLote, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    """Passa todos os PDVs vigentes de um promotor para outro (ex.: desligamento)."""
    origem = _buscar(sessao, Promotor, dados.de_promotor_id)
    destino = _promotor_ativo(sessao, dados.para_promotor_id)
    if origem.id == destino.id:
        _erro("Escolha promotores diferentes.")
    vigentes = [r for r in origem.roteiros
                if r.data_inicio < dados.data and (r.data_fim is None or r.data_fim >= dados.data)]
    if not vigentes:
        _erro(f"{origem.nome} não tem PDVs vigentes nessa data.")
    for roteiro in vigentes:
        _trocar(sessao, roteiro, destino, dados.data)
    sessao.commit()
    return {"transferidos": len(vigentes)}
