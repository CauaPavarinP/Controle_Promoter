"""Pendências / qualidade dos dados e conferência com a planilha (documento, seções 6.1 e 7.8)."""
from datetime import date
from difflib import SequenceMatcher

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import db
from .autenticacao import exigir_admin, usuario_logado
from .cadastros import documento_valido, vigente_em
from .calculos import aplicar_tipos_de_nota, indice_mes
from .carga import obter_pdv
from .faturamento import codigos_por_cnpj, faturamento_mensal
from .importacao import normalizar_texto
from .modelos import ApelidoColaborador, FaturamentoItem, Pdv, Promotor, Roteiro, RoteiroPendente
from .regras import ler_regras

rotas = APIRouter(prefix="/api")


def _periodo_padrao(fat: pd.DataFrame) -> tuple[str, str]:
    """Últimos 12 meses com faturamento."""
    if fat.empty:
        hoje = date.today()
        return f"{hoje.year - 1}-{hoje.month:02d}", f"{hoje.year}-{hoje.month:02d}"
    indices = sorted({int(a) * 12 + int(m) - 1 for a, m in zip(fat["ano"], fat["mes"])})
    fim = indices[-1]
    inicio = max(indices[0], fim - 11)
    return f"{inicio // 12}-{inicio % 12 + 1:02d}", f"{fim // 12}-{fim % 12 + 1:02d}"


def _sobrepoe(roteiro: Roteiro, inicio: int, fim: int) -> bool:
    comeco = roteiro.data_inicio.year * 12 + roteiro.data_inicio.month - 1
    termino = (roteiro.data_fim.year * 12 + roteiro.data_fim.month - 1) if roteiro.data_fim else fim
    return comeco <= fim and termino >= inicio


def calcular_pendencias(sessao: Session, inicio: str = "", fim: str = "") -> dict:
    regras = ler_regras()
    fat_bruto = faturamento_mensal()
    if not inicio or not fim:
        inicio, fim = _periodo_padrao(fat_bruto)
    i_inicio, i_fim = sorted((indice_mes(inicio), indice_mes(fim)))
    fat = aplicar_tipos_de_nota(fat_bruto, regras)
    indices = fat["ano"].astype(int) * 12 + fat["mes"].astype(int) - 1
    fat = fat.loc[(indices >= i_inicio) & (indices <= i_fim)]
    por_cnpj = fat.groupby("cnpj").agg(valor=("valor", "sum"), notas=("notas", "sum"))

    hoje = date.today()
    pdvs = sessao.scalars(select(Pdv).options(selectinload(Pdv.roteiros).selectinload(Roteiro.promotor))).all()
    promotores = sessao.scalars(select(Promotor).options(
        selectinload(Promotor.custos), selectinload(Promotor.roteiros), selectinload(Promotor.supervisor))).all()

    # 1. Colaboradores do roteiro importado sem promotor cadastrado.
    pendentes = {}
    for p in sessao.scalars(select(RoteiroPendente).order_by(RoteiroPendente.colaborador)):
        grupo = pendentes.setdefault(p.colaborador, {"colaborador": p.colaborador, "lojas": [], "origens": set()})
        grupo["lojas"].append(p.loja)
        grupo["origens"].add(p.origem)
    colaboradores = [{**g, "origens": sorted(g["origens"]), "quantidade": len(g["lojas"])} for g in pendentes.values()]

    # 2. Lojas diferentes com o mesmo CNPJ (confirmar com o Maurício se são lojas diferentes mesmo).
    por_documento = {}
    for pdv in pdvs:
        if pdv.cnpj_cpf and pdv.ativo:
            por_documento.setdefault(pdv.cnpj_cpf, []).append(pdv)
    repetidos = {c: lista for c, lista in por_documento.items() if len(lista) > 1}
    codigos_fat = codigos_por_cnpj(list(repetidos))
    mesmo_cnpj = []
    for cnpj, lista in sorted(repetidos.items(), key=lambda item: item[1][0].nome_fantasia):
        codigos = [p.cod_cli_erp for p in lista]
        separado = all(codigos) and len(set(codigos)) == len(codigos)
        mesmo_cnpj.append({
            "cnpj": cnpj, "separado_por_cod_cli": separado,
            "valor_periodo": round(float(por_cnpj["valor"].get(cnpj, 0)), 2),
            "cod_cli_no_faturamento": codigos_fat.get(cnpj, []),
            "lojas": [{"id": p.id, "nome": p.nome_fantasia, "cod_cli": p.cod_cli_erp, "cidade": p.cidade,
                       "promotores": [r.promotor.nome for r in p.roteiros if vigente_em(r, hoje)]} for p in lista],
        })

    # 3. CNPJs que compraram no período e não estão no roteiro de nenhum promotor.
    cnpjs_com_roteiro = {p.cnpj_cpf for p in pdvs if p.cnpj_cpf and any(_sobrepoe(r, i_inicio, i_fim) for r in p.roteiros)}
    sem_roteiro = []
    for cnpj, linha in por_cnpj[por_cnpj["valor"] > 0].sort_values("valor", ascending=False).iterrows():
        if cnpj in cnpjs_com_roteiro:
            continue
        sem_roteiro.append({"cnpj": cnpj, "valor": round(float(linha["valor"]), 2), "notas": int(linha["notas"]),
                            "pdv_cadastrado": cnpj in por_documento})
    if sem_roteiro:
        dados = _dados_dos_clientes([s["cnpj"] for s in sem_roteiro[:300]])
        for item in sem_roteiro:
            item.update(dados.get(item["cnpj"], {}))

    # 4. PDVs atendidos no período sem nenhum faturamento.
    sem_faturamento = []
    for pdv in pdvs:
        roteiros = [r for r in pdv.roteiros if _sobrepoe(r, i_inicio, i_fim)]
        if roteiros and por_cnpj["valor"].get(pdv.cnpj_cpf, 0) <= 0:
            sem_faturamento.append({
                "id": pdv.id, "pdv": pdv.nome_fantasia, "cnpj": pdv.cnpj_cpf, "cidade": pdv.cidade, "uf": pdv.uf,
                "promotores": sorted({r.promotor.nome for r in roteiros}),
                "visitas_semana": sum(r.visitas_por_semana or 0 for r in roteiros if vigente_em(r, hoje)) or None,
            })

    # 5. Promotores ativos com cadastro incompleto.
    promotores_incompletos = []
    for p in promotores:
        if not p.ativo:
            continue
        problemas = []
        if p.supervisor is None:
            problemas.append("sem supervisor")
        if not p.custos:
            problemas.append("sem custo cadastrado")
        if not any(vigente_em(r, hoje) for r in p.roteiros):
            problemas.append("sem PDV no roteiro")
        if problemas:
            promotores_incompletos.append({"id": p.id, "codigo": p.codigo, "nome": p.nome, "problemas": problemas})

    # 6. Vínculos vigentes sem visitas por semana; 7. CNPJ inválido ou vazio.
    sem_visitas = sum(1 for p in pdvs for r in p.roteiros if vigente_em(r, hoje) and not r.visitas_por_semana)
    documentos = [{"id": p.id, "pdv": p.nome_fantasia, "cnpj": p.cnpj_cpf, "cidade": p.cidade, "uf": p.uf,
                   "problema": "sem CNPJ" if not p.cnpj_cpf else "CNPJ/CPF inválido"}
                  for p in pdvs if p.ativo and (not p.cnpj_cpf or not documento_valido(p.cnpj_cpf))]

    return {
        "periodo": {"inicio": inicio, "fim": fim},
        "colaboradores_sem_promotor": colaboradores,
        "lojas_mesmo_cnpj": mesmo_cnpj,
        "cnpjs_sem_roteiro": sem_roteiro,
        "pdvs_sem_faturamento": sem_faturamento,
        "promotores_incompletos": promotores_incompletos,
        "roteiros_sem_visitas": sem_visitas,
        "documentos": documentos,
    }


def _dados_dos_clientes(cnpjs: list[str]) -> dict:
    with db.engine.connect() as conexao:
        linhas = conexao.execute(
            select(FaturamentoItem.cnpj_cpf, func.max(FaturamentoItem.razao_social), func.max(FaturamentoItem.cidade),
                   func.max(FaturamentoItem.uf)).where(FaturamentoItem.cnpj_cpf.in_(cnpjs))
            .group_by(FaturamentoItem.cnpj_cpf)).all()
    return {c: {"razao_social": r or "", "cidade": ci or "", "uf": u or ""} for c, r, ci, u in linhas}


def contar_pendencias(dados: dict) -> int:
    """Quantos tipos de pendência existem (número ao lado do menu)."""
    listas = ("colaboradores_sem_promotor", "lojas_mesmo_cnpj", "cnpjs_sem_roteiro", "pdvs_sem_faturamento",
              "promotores_incompletos", "documentos")
    return sum(1 for chave in listas if dados[chave]) + (1 if dados["roteiros_sem_visitas"] else 0)


@rotas.get("/pendencias")
def listar_pendencias(inicio: str = "", fim: str = "", sessao: Session = Depends(db.sessao_db),
                      _=Depends(usuario_logado)):
    try:
        dados = calcular_pendencias(sessao, inicio, fim)
    except (ValueError, IndexError) as erro:
        raise HTTPException(status_code=400, detail="Período inválido. Use AAAA-MM.") from erro
    dados["total"] = contar_pendencias(dados)
    return dados


class ResolverColaborador(BaseModel):
    colaborador: str
    promotor_id: int
    data_inicio: date


@rotas.post("/pendencias/colaborador")
def resolver_colaborador(dados: ResolverColaborador, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    """Liga todas as lojas pendentes de um colaborador a um promotor cadastrado."""
    promotor = sessao.get(Promotor, dados.promotor_id)
    if promotor is None or not promotor.ativo:
        raise HTTPException(status_code=400, detail="Escolha um promotor ativo.")
    pendentes = sessao.scalars(select(RoteiroPendente).where(RoteiroPendente.colaborador == dados.colaborador)).all()
    if not pendentes:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")
    criados = 0
    for item in pendentes:
        pdv = obter_pdv(sessao, item.cnpj_cpf, item.loja, item.cidade, item.uf)
        existe = sessao.scalar(select(Roteiro).where(
            Roteiro.promotor_id == promotor.id, Roteiro.pdv_id == pdv.id, Roteiro.data_fim.is_(None)))
        if existe is None:
            sessao.add(Roteiro(promotor_id=promotor.id, pdv_id=pdv.id, data_inicio=dados.data_inicio,
                               visitas_por_semana=item.visitas_por_semana))
            criados += 1
        sessao.delete(item)
    # Guarda a ligação: nas próximas importações esse nome já vai direto para o promotor.
    chave = normalizar_texto(dados.colaborador)
    apelido = sessao.scalar(select(ApelidoColaborador).where(ApelidoColaborador.nome_chave == chave))
    if apelido is None:
        sessao.add(ApelidoColaborador(nome_chave=chave, nome=dados.colaborador.strip(), promotor_id=promotor.id))
    else:
        apelido.promotor_id = promotor.id
    sessao.commit()
    return {"vinculos_criados": criados}


_CONECTIVOS = {"DE", "DA", "DO", "DAS", "DOS", "E"}


def _sugerir_promotor(nome: str, promotores: list) -> dict | None:
    """Promotor com o nome mais parecido (erro de digitação, acento, nome do meio a mais ou a menos)."""
    alvo = normalizar_texto(nome)
    # "DE", "DA", "DOS"… não contam como sobrenome em comum ("Maria de Souza" x "Maria de Oliveira").
    palavras = set(alvo.split()) - _CONECTIVOS
    melhor, nota_melhor = None, 0.0
    for p in promotores:
        candidato = normalizar_texto(p.nome)
        nota = SequenceMatcher(None, alvo, candidato).ratio()
        # Mesmo primeiro nome e algum sobrenome em comum também conta ("Ana Silva" x "Ana Maria Silva").
        comuns = palavras & (set(candidato.split()) - _CONECTIVOS)
        if alvo.split()[:1] == candidato.split()[:1] and len(comuns) >= 2:
            nota = max(nota, 0.85)
        if nota > nota_melhor:
            melhor, nota_melhor = p, nota
    if melhor is None or nota_melhor < 0.75:
        return None
    return {"id": melhor.id, "nome": melhor.nome, "codigo": melhor.codigo}


@rotas.get("/colaboradores-pendentes")
def colaboradores_pendentes_da_importacao(sessao: Session = Depends(db.sessao_db), _=Depends(usuario_logado)):
    """Nomes da coluna "Colaborador" das abas por UF que não bateram com nenhum promotor, com as lojas de
    cada um, e os promotores ativos que ficaram sem nenhuma loja (o nome certo costuma estar entre eles)."""
    grupos = {}
    for item in sessao.scalars(select(RoteiroPendente).order_by(RoteiroPendente.colaborador, RoteiroPendente.loja)):
        grupo = grupos.setdefault(item.colaborador, {"colaborador": item.colaborador, "lojas": [], "ufs": set()})
        grupo["lojas"].append({"loja": item.loja, "cidade": item.cidade, "uf": item.uf})
        if item.uf:
            grupo["ufs"].add(item.uf)
    ativos = sessao.scalars(select(Promotor).where(Promotor.ativo.is_(True))
                            .options(selectinload(Promotor.roteiros))).all()
    hoje = date.today()
    sem_loja = [{"id": p.id, "nome": p.nome, "codigo": p.codigo, "uf": p.uf}
                for p in ativos if not any(vigente_em(r, hoje) or r.data_fim is None for r in p.roteiros)]
    colaboradores = [{**g, "ufs": sorted(g["ufs"]), "quantidade": len(g["lojas"]),
                      "sugestao": _sugerir_promotor(g["colaborador"], ativos)} for g in grupos.values()]
    colaboradores.sort(key=lambda g: -g["quantidade"])
    lembrados = [{"id": a.id, "nome": a.nome, "promotor": a.promotor.nome, "codigo": a.promotor.codigo}
                 for a in sessao.scalars(select(ApelidoColaborador).options(selectinload(ApelidoColaborador.promotor))
                                         .order_by(ApelidoColaborador.nome))]
    return {"colaboradores": colaboradores, "promotores_sem_loja": sorted(sem_loja, key=lambda p: p["nome"]),
            "lembrados": lembrados}


@rotas.delete("/colaboradores-pendentes/lembrados/{ident}")
def esquecer_ligacao(ident: int, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    """Esquece uma ligação feita por engano. As lojas já ligadas continuam com o promotor até serem trocadas
    ou encerradas em Lojas por UF; só a próxima importação deixa de usar essa ligação."""
    apelido = sessao.get(ApelidoColaborador, ident)
    if apelido is None:
        raise HTTPException(status_code=404, detail="Ligação não encontrada.")
    sessao.delete(apelido)
    sessao.commit()
    return {"ok": True}


@rotas.delete("/colaboradores-pendentes")
def descartar_colaborador(colaborador: str, sessao: Session = Depends(db.sessao_db), _=Depends(exigir_admin)):
    """Descarta as lojas de um nome que não é promotor (ex.: célula vazia, #N/A). Reimportar traz de volta."""
    pendentes = sessao.scalars(select(RoteiroPendente).where(RoteiroPendente.colaborador == colaborador)).all()
    if not pendentes:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")
    for item in pendentes:
        sessao.delete(item)
    sessao.commit()
    return {"descartadas": len(pendentes)}


# ---------------------------------------------------------------------------
# Conferência com a planilha (totais das abas SC, SP, PR, MG, RS)
# ---------------------------------------------------------------------------

def calcular_conferencia() -> dict:
    """Compara, por aba e mês, o total da planilha com o mesmo cálculo feito pelo sistema
    (documento, seção 6.1, item 5): o faturamento do CNPJ de cada linha da aba, como o SOMASE
    da planilha, lado a lado, apontando as diferenças.
    """
    planilha = db.ler_tabela("conferencia_planilha")
    ano = db.ler_configuracao("conferencia_ano")
    if planilha.empty or not ano:
        return {"disponivel": False}
    regras = ler_regras()
    fat = aplicar_tipos_de_nota(faturamento_mensal(), regras)
    fat = fat[fat["ano"].astype(int) == int(ano)]
    valor_por = fat.groupby(["cnpj", "mes"])["valor"].sum()

    def sistema(linhas):
        return float(sum(valor_por.get((c, m), 0.0) for c, m in zip(linhas["cnpj"], linhas["mes"])))

    abas = []
    for aba, linhas_aba in planilha.groupby("aba", sort=False):
        meses = []
        for mes, linhas in linhas_aba.groupby("mes"):
            valor_planilha = float(linhas["valor"].sum())
            mesma_conta = sistema(linhas)
            if valor_planilha == 0 and mesma_conta == 0:
                continue
            meses.append({"mes": int(mes), "planilha": round(valor_planilha, 2), "sistema": round(mesma_conta, 2),
                          "diferenca": round(valor_planilha - mesma_conta, 2)})
        total = {c: round(sum(m[c] for m in meses), 2) for c in ("planilha", "sistema", "diferenca")}
        abas.append({"aba": aba, "meses": meses, "total": total})

    # Linhas que mais explicam as diferenças.
    planilha = planilha.copy()
    planilha["sistema"] = [valor_por.get((c, m), 0.0) for c, m in zip(planilha["cnpj"], planilha["mes"])]
    planilha["diferenca"] = planilha["valor"] - planilha["sistema"]
    maiores = planilha[planilha["diferenca"].abs() >= 0.01].reindex(
        planilha["diferenca"].abs().sort_values(ascending=False).index).head(30)
    maiores = maiores[maiores["diferenca"].abs() >= 0.01]
    return {
        "disponivel": True, "ano": int(ano),
        "regras": {"valor_faturamento": regras["valor_faturamento"], "somente_receita": regras["somente_receita"]},
        "abas": abas,
        "maiores_diferencas": [{"aba": r.aba, "loja": r.loja, "cnpj": r.cnpj, "mes": int(r.mes),
                                "planilha": round(float(r.valor), 2), "sistema": round(float(r.sistema), 2),
                                "diferenca": round(float(r.diferenca), 2)} for r in maiores.itertuples()],
    }


@rotas.get("/conferencia")
def conferencia(_=Depends(usuario_logado)):
    return calcular_conferencia()


def guardar_totais_planilha(totais: pd.DataFrame, ano: int) -> None:
    db.substituir_tabela("conferencia_planilha", totais)
    db.gravar_configuracao("conferencia_ano", int(ano))

