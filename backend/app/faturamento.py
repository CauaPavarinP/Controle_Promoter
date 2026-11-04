"""Faturamento item a item: pré-visualização, gravação (tudo ou nada), desfazer e consultas.

Fluxo da importação:
1. preparar_previa(): lê o arquivo e devolve um resumo (período, totais, erros, CNPJs sem roteiro,
   meses que já existem). Os itens ficam guardados em memória por 30 minutos.
2. confirmar(): grava os itens numa transação. Meses que já existiam só são substituídos se o
   usuário confirmar (apaga os itens daquele ano/mês e grava os novos).
3. desfazer(): apaga os itens de uma importação.
"""
import json
import secrets
import time

import pandas as pd
from sqlalchemy import and_, delete, func, inspect, literal_column, or_, select, text
from sqlalchemy.orm import Session

from . import db
from .importacao import ErroImportacao, ler_faturamento, normalizar_texto
from .modelos import FaturamentoItem, Importacao

VALIDADE_PREVIA = 30 * 60
_previas: dict[str, dict] = {}


def _limpar_previas():
    agora = time.time()
    for token in [t for t, p in _previas.items() if agora - p["criado"] > VALIDADE_PREVIA]:
        _previas.pop(token, None)


def _rotulo(ano: int, mes: int) -> str:
    return f"{ano}-{mes:02d}"


def meses_com_itens(conexao) -> set[tuple[int, int]]:
    linhas = conexao.execute(select(FaturamentoItem.ano, FaturamentoItem.mes).distinct())
    return {(int(a), int(m)) for a, m in linhas}


def _filtro_meses(meses):
    return or_(*[and_(FaturamentoItem.ano == a, FaturamentoItem.mes == m) for a, m in meses])


def preparar_previa(conteudo: bytes, nome: str, usuario: str, cnpjs_no_roteiro: set[str]) -> dict:
    _limpar_previas()
    itens, erros, avisos, aba = ler_faturamento(conteudo, nome)
    if itens.empty:
        raise ErroImportacao("O arquivo não tem nenhuma linha válida (com CNPJ, data e valor).")
    meses = sorted({(int(a), int(m)) for a, m in zip(itens["ano"], itens["mes"])})
    with db.engine.connect() as conexao:
        existentes = sorted(set(meses) & meses_com_itens(conexao))

    por_cnpj = (itens.groupby("cnpj_cpf")
                     .agg(valor=("total_venda", "sum"), razao_social=("razao_social", "first"),
                          cidade=("cidade", "first"), uf=("uf", "first"))
                     .reset_index())
    sem_roteiro = por_cnpj[~por_cnpj["cnpj_cpf"].isin(cnpjs_no_roteiro)].sort_values("valor", ascending=False)

    token = secrets.token_urlsafe(16)
    _previas[token] = {"criado": time.time(), "itens": itens, "erros": erros, "avisos": avisos,
                       "arquivo": nome, "usuario": usuario}
    return {
        "token": token, "arquivo": nome, "aba": aba,
        "linhas_lidas": len(itens) + len(erros), "linhas_validas": len(itens), "linhas_com_erro": len(erros),
        "erros": erros[:100], "avisos": avisos,
        "meses": [_rotulo(a, m) for a, m in meses],
        "meses_existentes": [_rotulo(a, m) for a, m in existentes],
        "total_venda": round(float(itens["total_venda"].sum()), 2),
        "notas": int(itens["num_nf"].nunique()),
        "clientes": int(itens["cnpj_cpf"].nunique()),
        "cnpjs_sem_roteiro": {
            "quantidade": int(len(sem_roteiro)), "valor": round(float(sem_roteiro["valor"].sum()), 2),
            "exemplos": [{"cnpj": r.cnpj_cpf, "razao_social": r.razao_social, "cidade": r.cidade, "uf": r.uf,
                          "valor": round(float(r.valor), 2)} for r in sem_roteiro.head(20).itertuples()],
        },
    }


def confirmar(token: str, substituir: bool, avisos_extra: list[str] | None = None) -> dict:
    previa = _previas.get(token)
    if previa is None:
        raise ErroImportacao("A pré-visualização expirou ou já foi usada. Envie o arquivo de novo.")
    itens = previa["itens"]
    meses = sorted({(int(a), int(m)) for a, m in zip(itens["ano"], itens["mes"])})

    with db.engine.begin() as conexao:   # tudo ou nada
        existentes = sorted(set(meses) & meses_com_itens(conexao))
        if existentes and not substituir:
            raise ErroImportacao(
                "Já existe faturamento para " + ", ".join(_rotulo(a, m) for a, m in existentes)
                + ". Confirme a substituição desses meses para continuar.")
        if existentes:
            conexao.execute(delete(FaturamentoItem).where(_filtro_meses(existentes)))
        importacao_id = conexao.execute(
            Importacao.__table__.insert().values(
                tipo="faturamento", arquivo_nome=previa["arquivo"], usuario=previa["usuario"],
                periodos=",".join(_rotulo(a, m) for a, m in meses),
                linhas_lidas=len(itens) + len(previa["erros"]), linhas_importadas=len(itens),
                linhas_com_erro=len(previa["erros"]), total_venda=round(float(itens["total_venda"].sum()), 2),
                avisos=json.dumps(previa["avisos"] + (avisos_extra or []), ensure_ascii=False),
                log_erros=json.dumps(previa["erros"], ensure_ascii=False), situacao="ativa")
        ).inserted_primary_key[0]
        itens.assign(importacao_id=importacao_id).to_sql(
            "faturamento_itens", conexao, if_exists="append", index=False, chunksize=5000)
        # Importações antigas que ficaram sem nenhum item (todos os meses substituídos).
        conexao.execute(text(
            "UPDATE importacoes SET situacao = 'substituida' WHERE tipo = 'faturamento' AND situacao = 'ativa' "
            "AND id <> :atual AND NOT EXISTS (SELECT 1 FROM faturamento_itens f WHERE f.importacao_id = importacoes.id)"),
            {"atual": importacao_id})
    _previas.pop(token, None)
    return {"importacao_id": importacao_id, "linhas_importadas": len(itens),
            "meses": [_rotulo(a, m) for a, m in meses], "meses_substituidos": [_rotulo(a, m) for a, m in existentes]}


def desfazer(sessao: Session, importacao_id: int) -> dict:
    importacao = sessao.get(Importacao, importacao_id)
    if importacao is None or importacao.tipo != "faturamento":
        raise ErroImportacao("Importação de faturamento não encontrada.")
    if importacao.situacao != "ativa":
        raise ErroImportacao("Esta importação já foi desfeita ou substituída.")
    apagados = sessao.execute(delete(FaturamentoItem).where(FaturamentoItem.importacao_id == importacao_id)).rowcount
    importacao.situacao = "desfeita"
    sessao.commit()
    return {"itens_apagados": apagados}


def registrar(sessao: Session, tipo: str, arquivo: str, usuario: str, linhas: int, avisos: list[str]) -> None:
    """Histórico das importações que não são de faturamento (promotores, roteiro)."""
    sessao.add(Importacao(tipo=tipo, arquivo_nome=arquivo, usuario=usuario, linhas_lidas=linhas,
                          linhas_importadas=linhas, avisos=json.dumps(avisos, ensure_ascii=False), situacao="ativa"))
    sessao.commit()


def historico(sessao: Session) -> list[dict]:
    itens_por_importacao = dict(sessao.execute(
        select(FaturamentoItem.importacao_id, func.count()).group_by(FaturamentoItem.importacao_id)).all())
    return [{
        "id": i.id, "tipo": i.tipo, "arquivo": i.arquivo_nome, "usuario": i.usuario,
        "data_hora": i.criado_em.isoformat() if i.criado_em else None,
        "periodos": [p for p in i.periodos.split(",") if p], "linhas_lidas": i.linhas_lidas,
        "linhas_importadas": i.linhas_importadas, "linhas_com_erro": i.linhas_com_erro,
        "itens_atuais": itens_por_importacao.get(i.id, 0), "total_venda": i.total_venda,
        "situacao": i.situacao, "avisos": json.loads(i.avisos or "[]"),
    } for i in sessao.scalars(select(Importacao).order_by(Importacao.id.desc()))]


def ultimas_por_tipo(sessao: Session) -> dict:
    """Última importação ativa de cada tipo, com os avisos (aba de pendências)."""
    ultimas = {}
    for item in historico(sessao):
        if item["situacao"] == "ativa" and item["tipo"] not in ultimas:
            ultimas[item["tipo"]] = {"arquivo": item["arquivo"], "data_hora": item["data_hora"],
                                     "linhas": item["linhas_importadas"], "avisos": item["avisos"]}
    return ultimas


def erros_da_importacao(sessao: Session, importacao_id: int) -> list[dict]:
    importacao = sessao.get(Importacao, importacao_id)
    return json.loads(importacao.log_erros or "[]") if importacao else []


# ---------------------------------------------------------------------------
# Consultas usadas pelo cálculo
# ---------------------------------------------------------------------------

# RECEITA vazia vira "". Sem parâmetro (literal) para o Postgres aceitar a mesma expressão no SELECT e no
# GROUP BY (com parâmetro, cada um vira $1/$2 e ele recusa).
_RECEITA = func.coalesce(FaturamentoItem.receita, literal_column("''"))

COLUNAS_MENSAL = ["ano", "mes", "cnpj", "cod_cliente", "chave_tipo", "tipo_nf", "receita",
                  "total_venda", "vlr_total", "notas"]


def faturamento_mensal() -> pd.DataFrame:
    """Faturamento somado por mês, CNPJ, código de cliente, tipo de nota e RECEITA."""
    consulta = (select(FaturamentoItem.ano, FaturamentoItem.mes, FaturamentoItem.cnpj_cpf,
                       FaturamentoItem.cod_cli, FaturamentoItem.tipo_nf_chave, func.min(FaturamentoItem.tipo_nf),
                       _RECEITA,
                       func.coalesce(func.sum(FaturamentoItem.total_venda), 0),
                       func.coalesce(func.sum(FaturamentoItem.vlr_total), 0),
                       func.count(FaturamentoItem.num_nf.distinct()))
                .group_by(FaturamentoItem.ano, FaturamentoItem.mes, FaturamentoItem.cnpj_cpf, FaturamentoItem.cod_cli,
                          FaturamentoItem.tipo_nf_chave, _RECEITA))
    with db.engine.connect() as conexao:
        linhas = conexao.execute(consulta).all()
    df = pd.DataFrame(linhas, columns=COLUNAS_MENSAL)
    for coluna in ("total_venda", "vlr_total"):
        df[coluna] = df[coluna].astype(float)
    return df


def mensal_por_cliente(inicio: tuple[int, int], fim: tuple[int, int]) -> pd.DataFrame:
    """Faturamento do período somado por mês, CNPJ e tipo de nota, com razão social, cidade e UF do cliente."""
    indice = FaturamentoItem.ano * 12 + FaturamentoItem.mes
    consulta = (select(FaturamentoItem.ano, FaturamentoItem.mes, FaturamentoItem.cnpj_cpf,
                       FaturamentoItem.tipo_nf_chave, _RECEITA,
                       func.coalesce(func.sum(FaturamentoItem.total_venda), 0),
                       func.coalesce(func.sum(FaturamentoItem.vlr_total), 0),
                       func.count(FaturamentoItem.num_nf.distinct()),
                       func.max(FaturamentoItem.razao_social), func.max(FaturamentoItem.cidade),
                       func.max(FaturamentoItem.uf))
                .where(indice >= inicio[0] * 12 + inicio[1], indice <= fim[0] * 12 + fim[1])
                .group_by(FaturamentoItem.ano, FaturamentoItem.mes, FaturamentoItem.cnpj_cpf,
                          FaturamentoItem.tipo_nf_chave, _RECEITA))
    with db.engine.connect() as conexao:
        linhas = conexao.execute(consulta).all()
    df = pd.DataFrame(linhas, columns=["ano", "mes", "cnpj", "chave_tipo", "receita", "total_venda", "vlr_total",
                                       "notas", "razao_social", "cidade", "uf"])
    for coluna in ("total_venda", "vlr_total"):
        df[coluna] = df[coluna].astype(float)
    for coluna in ("razao_social", "cidade", "uf"):
        df[coluna] = df[coluna].fillna("")
    return df


def dados_do_cliente(cnpj: str) -> dict:
    """Razão social, cidade, UF e códigos de cliente de um CNPJ no faturamento."""
    with db.engine.connect() as conexao:
        ultimo = conexao.execute(
            select(FaturamentoItem.razao_social, FaturamentoItem.cidade, FaturamentoItem.uf)
            .where(FaturamentoItem.cnpj_cpf == cnpj)
            .order_by(FaturamentoItem.ano.desc(), FaturamentoItem.mes.desc()).limit(1)).first()
        if ultimo is None:
            return {"encontrado": False}
        codigos = conexao.execute(select(FaturamentoItem.cod_cli).where(
            FaturamentoItem.cnpj_cpf == cnpj, FaturamentoItem.cod_cli != "").distinct()).scalars().all()
    return {"encontrado": True, "razao_social": ultimo[0] or "", "cidade": ultimo[1] or "", "uf": ultimo[2] or "",
            "cod_cli_erp": sorted(codigos)}


def codigos_por_cnpj(cnpjs: list[str]) -> dict[str, list[str]]:
    if not cnpjs:
        return {}
    with db.engine.connect() as conexao:
        linhas = conexao.execute(select(FaturamentoItem.cnpj_cpf, FaturamentoItem.cod_cli).where(
            FaturamentoItem.cnpj_cpf.in_(cnpjs), FaturamentoItem.cod_cli != "").distinct()).all()
    resultado = {}
    for cnpj, codigo in linhas:
        resultado.setdefault(cnpj, []).append(codigo)
    return {c: sorted(v) for c, v in resultado.items()}


def tem_faturamento_antigo() -> bool:
    """Banco atualizado de uma versão anterior, com faturamento ainda no formato antigo."""
    if not inspect(db.engine).has_table("legado_faturamento"):
        return False
    with db.engine.connect() as conexao:
        return conexao.execute(select(func.count(FaturamentoItem.id))).scalar() == 0



def itens_do_cliente(cnpj: str, ano: int, mes: int, cod_cli: str, regras: dict) -> dict:
    """Itens de nota de um CNPJ num mês (detalhe da grade), com o que conta no faturamento."""
    filtro = FaturamentoItem.cnpj_cpf == cnpj
    consulta = (select(FaturamentoItem).where(filtro, FaturamentoItem.ano == ano, FaturamentoItem.mes == mes)
                .order_by(FaturamentoItem.data_emissao, FaturamentoItem.num_nf, FaturamentoItem.id).limit(5000))
    if cod_cli:
        consulta = consulta.where(FaturamentoItem.cod_cli == cod_cli)
    coluna = regras["valor_faturamento"]
    itens, total = [], 0.0
    with Session(db.engine) as sessao:
        for item in sessao.scalars(consulta):
            acao = regras["tipos_nf"].get(item.tipo_nf_chave, regras["tipos_nf_padrao"])
            if regras["somente_receita"] and normalizar_texto(item.receita) not in ("SIM", "S"):
                acao = "ignora"
            valor = float(getattr(item, coluna) or 0)
            conta = {"soma": valor, "subtrai": -abs(valor)}.get(acao, 0.0)
            total += conta
            itens.append({
                "data": item.data_emissao.isoformat() if item.data_emissao else None, "num_nf": item.num_nf,
                "cnpj": item.cnpj_cpf, "cod_cli": item.cod_cli, "razao_social": item.razao_social,
                "tipo_nf": item.tipo_nf, "receita": item.receita, "cod_item": item.cod_item,
                "descricao_item": item.descricao_item, "qtde": item.qtde, "total_venda": item.total_venda,
                "vlr_total": item.vlr_total, "representante": item.representante, "acao": acao,
                "valor_considerado": round(conta, 2),
            })
    return {"itens": itens, "total_considerado": round(total, 2), "limitado": len(itens) == 5000}
