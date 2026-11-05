"""Faturamento item a item: pré-visualização, gravação (tudo ou nada), desfazer e consultas.

Fluxo da importação:
1. preparar_previa(): lê o arquivo e devolve um resumo (período, totais, erros, CNPJs sem roteiro,
   meses que já existem). Os itens ficam guardados em memória por 30 minutos.
2. confirmar(): grava os itens numa transação. Meses que já existiam só são substituídos se o
   usuário confirmar (apaga os itens daquele ano/mês e grava os novos).
3. desfazer(): apaga os itens de uma importação.
"""
import json
import logging
import os
import secrets
import threading
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


def preparar_previa(conteudo, nome: str, usuario: str, cnpjs_no_roteiro: set[str], ao_progredir=None) -> dict:
    """`conteudo`: bytes do arquivo ou caminho dele no disco."""
    _limpar_previas()
    itens, erros, avisos, aba = ler_faturamento(conteudo, nome, ao_progredir=ao_progredir)
    if itens.empty:
        raise ErroImportacao("O arquivo não tem nenhuma linha válida (com CNPJ, data e valor).")
    meses = sorted({(int(a), int(m)) for a, m in zip(itens["ano"], itens["mes"])})
    with db.engine.connect() as conexao:
        existentes = sorted(set(meses) & meses_com_itens(conexao))

    por_cnpj = (itens.groupby("cnpj_cpf")
                     .agg(valor=("total_venda", "sum"), razao_social=("razao_social", "first"),
                          cidade=("cidade", "first"), uf=("uf", "first"))
                     .reset_index())
    for coluna in ("cnpj_cpf", "razao_social", "cidade", "uf"):  # "category" vazio vira NaN: volta para texto
        por_cnpj[coluna] = por_cnpj[coluna].astype(object).where(por_cnpj[coluna].notna(), "")
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


# ---------------------------------------------------------------------------
# Leitura em segundo plano: o arquivo grande leva minutos no servidor gratuito (0,15 de processador). A tela
# pergunta o andamento a cada poucos segundos em vez de esperar uma resposta só (que o navegador abandonaria).
# ---------------------------------------------------------------------------

log = logging.getLogger("uvicorn.error")
_leituras: dict[str, dict] = {}


def iniciar_leitura(caminho: str, nome: str, usuario: str, cnpjs_no_roteiro: set[str]) -> str:
    """Começa a ler o arquivo (já salvo no disco) numa thread e devolve o código da leitura."""
    agora = time.time()
    for codigo in [c for c, l in _leituras.items() if agora - l["criado"] > 3600]:
        _leituras.pop(codigo, None)
    if any(l["situacao"] == "lendo" for l in _leituras.values()):
        os.remove(caminho)
        raise ErroImportacao("Já tem um arquivo sendo lido. Espere ele terminar para enviar outro.")
    codigo = secrets.token_urlsafe(12)
    estado = _leituras[codigo] = {"situacao": "lendo", "linhas": 0, "criado": agora}

    def trabalhar():
        try:
            estado["previa"] = preparar_previa(caminho, nome, usuario, cnpjs_no_roteiro,
                                               ao_progredir=lambda linhas: estado.update(linhas=linhas))
            estado["situacao"] = "pronto"
        except ErroImportacao as erro:
            estado.update(situacao="erro", erro=str(erro))
        except Exception:  # noqa: BLE001 - qualquer falha vira mensagem para a tela, com detalhe no log
            log.exception("Erro ao ler o arquivo de faturamento %s", nome)
            estado.update(situacao="erro", erro="Erro inesperado ao ler o arquivo. Confira se é a exportação do ERP.")
        finally:
            try:
                os.remove(caminho)
            except OSError:
                pass

    threading.Thread(target=trabalhar, name=f"leitura-{codigo}", daemon=True).start()
    return codigo


def andamento_da_leitura(codigo: str) -> dict:
    estado = _leituras.get(codigo)
    if estado is None:
        raise ErroImportacao("Leitura não encontrada (o servidor pode ter reiniciado). Envie o arquivo de novo.")
    if estado["situacao"] == "erro":
        _leituras.pop(codigo, None)
        raise ErroImportacao(estado["erro"])
    if estado["situacao"] == "pronto":
        _leituras.pop(codigo, None)
        return {**estado["previa"], "situacao": "pronto"}
    return {"situacao": "lendo", "leitura": codigo, "linhas": estado["linhas"]}


def _pedacos_para_gravar(itens: pd.DataFrame, importacao_id: int):
    """Itens em pedaços de 5 mil linhas, com vazio = None (converter tudo de uma vez estourava a memória)."""
    for inicio in range(0, len(itens), 5000):
        pedaco = itens.iloc[inicio:inicio + 5000].assign(importacao_id=importacao_id)
        if pd.api.types.is_datetime64_any_dtype(pedaco["data_emissao"]):
            pedaco["data_emissao"] = pedaco["data_emissao"].dt.date
        yield pedaco.astype(object).where(pedaco.notna(), None)


def _gravar_itens(conexao, itens: pd.DataFrame, importacao_id: int) -> None:
    """Grava os itens. No Postgres usa COPY (carga em massa), várias vezes mais rápido que INSERT linha a linha."""
    if conexao.dialect.name != "postgresql":
        for pedaco in _pedacos_para_gravar(itens, importacao_id):
            pedaco.to_sql("faturamento_itens", conexao, if_exists="append", index=False)
        return
    colunas = ", ".join(list(itens.columns) + ["importacao_id"])
    cursor = conexao.connection.driver_connection.cursor()
    with cursor.copy(f"COPY faturamento_itens ({colunas}) FROM STDIN") as copia:
        for pedaco in _pedacos_para_gravar(itens, importacao_id):
            for linha in pedaco.itertuples(index=False, name=None):
                copia.write_row(linha)


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
        _gravar_itens(conexao, itens, importacao_id)
        # Importações antigas que ficaram sem nenhum item (todos os meses substituídos).
        conexao.execute(text(
            "UPDATE importacoes SET situacao = 'substituida' WHERE tipo = 'faturamento' AND situacao = 'ativa' "
            "AND id <> :atual AND NOT EXISTS (SELECT 1 FROM faturamento_itens f WHERE f.importacao_id = importacoes.id)"),
            {"atual": importacao_id})
    limpar_cache()
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
    limpar_cache()
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


# Somar as ~317 mil linhas do ano leva menos de 1 s num computador comum, mas de 30 s a minutos no Postgres
# gratuito do Render, e cada tela (Resumo, Faturamento, Lojas) pede essa soma. Por isso o resultado fica guardado
# na memória (~15 MB) e só é refeito quando o faturamento muda (importar, substituir meses ou desfazer).
# Pedidos que chegam enquanto a soma está sendo feita esperam por ela, em vez de cada um abrir outra no banco
# (era isso que esgotava as conexões e derrubava as outras telas com erro 500).
_cache: dict[str, dict] = {}
_trava_cache = threading.Lock()
_versao_cache = 0


def _do_cache(chave: str, calcular) -> pd.DataFrame:
    with _trava_cache:
        entrada = _cache.setdefault(chave, {"trava": threading.Lock(), "versao": None, "valor": None})
    with entrada["trava"]:
        if entrada["versao"] != _versao_cache:
            versao = _versao_cache  # se o faturamento mudar durante a soma, o próximo pedido refaz
            entrada["valor"] = calcular()
            entrada["versao"] = versao
        return entrada["valor"].copy()  # cópia: quem usa pode alterar à vontade


def limpar_cache() -> None:
    """Chamar sempre que faturamento_itens mudar (depois do commit)."""
    global _versao_cache
    with _trava_cache:
        _versao_cache += 1


def aquecer_cache() -> None:
    """Faz as somas com antecedência (ao ligar o servidor), para a primeira tela não esperar."""
    try:
        faturamento_mensal()
        _mensal_por_cliente_completo()
    except Exception:  # noqa: BLE001 - se falhar aqui, a primeira tela tenta de novo
        log.exception("Não foi possível pré-calcular o faturamento")


def faturamento_mensal() -> pd.DataFrame:
    """Faturamento somado por mês, CNPJ, código de cliente, tipo de nota e RECEITA."""
    return _do_cache("mensal", _somar_faturamento_mensal)


def _somar_faturamento_mensal() -> pd.DataFrame:
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
    df = _mensal_por_cliente_completo()
    indice = df["ano"] * 12 + df["mes"]
    dentro = (indice >= inicio[0] * 12 + inicio[1]) & (indice <= fim[0] * 12 + fim[1])
    return df[dentro].reset_index(drop=True)


def _mensal_por_cliente_completo() -> pd.DataFrame:
    """Todos os meses (o período é filtrado depois, na memória)."""
    return _do_cache("por_cliente", _somar_mensal_por_cliente)


def _somar_mensal_por_cliente() -> pd.DataFrame:
    consulta = (select(FaturamentoItem.ano, FaturamentoItem.mes, FaturamentoItem.cnpj_cpf,
                       FaturamentoItem.tipo_nf_chave, _RECEITA,
                       func.coalesce(func.sum(FaturamentoItem.total_venda), 0),
                       func.coalesce(func.sum(FaturamentoItem.vlr_total), 0),
                       func.count(FaturamentoItem.num_nf.distinct()),
                       func.max(FaturamentoItem.razao_social), func.max(FaturamentoItem.cidade),
                       func.max(FaturamentoItem.uf))
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
