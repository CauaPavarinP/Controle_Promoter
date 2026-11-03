"""Cálculos do painel: custo dos promotores × faturamento das lojas que eles atendem.

O cálculo é feito mês a mês e depois somado no período escolhido:
- Faturamento: cada linha do roteiro recebe o faturamento dos meses em que estava vigente
  (vale o vínculo vigente no último dia do mês). Trocar o promotor de uma loja não muda o que
  foi atribuído ao promotor antigo nos meses anteriores.
- Custo: em cada mês vale o custo da competência (último reajuste até aquele mês), contado a
  partir do mês de admissão e até o mês de desligamento. Reajuste não muda meses anteriores.

As regras ajustáveis vêm de app/regras.py (aba "Regras do cálculo"): o que conta como
faturamento, a divisão do custo do promotor entre as lojas e o limite de % que destaca a loja.

Lojas com o mesmo CNPJ: se cada uma tem o seu COD CLI (e eles são diferentes), o faturamento é
separado pelo COD CLI; senão, o faturamento do CNPJ conta uma vez só nos totais e as lojas
aparecem como "faturamento compartilhado" (sem % de custo).
Se uma loja tem mais de um promotor ao mesmo tempo, o faturamento conta para cada um deles.

"""
from calendar import monthrange
from dataclasses import dataclass

import pandas as pd

from .importacao import normalizar_texto, vincular_roteiro
from .regras import REGRAS_PADRAO

# Para o faturamento por visita: visitas no mês = visitas por semana × semanas do mês (52 / 12).
SEMANAS_POR_MES = 52 / 12


@dataclass
class Filtros:
    inicio: str            # "AAAA-MM"
    fim: str               # "AAAA-MM"
    supervisor: str = ""
    promotor: str = ""     # código do promotor
    uf: str = ""
    cidade: str = ""
    pdv: str = ""          # nome do PDV


def indice_mes(ano_mes: str) -> int:
    ano, mes = ano_mes.split("-")[:2]
    return int(ano) * 12 + int(mes) - 1


def _indice_data(texto):
    """'2026-03-15' -> índice do mês (ano × 12 + mês − 1); vazio -> None."""
    if texto is None or texto == "" or (isinstance(texto, float) and pd.isna(texto)):
        return None
    data = pd.to_datetime(texto, errors="coerce")
    return None if pd.isna(data) else data.year * 12 + data.month - 1


def _ultimo_mes_vigente(texto):
    """Último mês em que o vínculo vale: só conta o mês se estava vigente no último dia dele."""
    if texto is None or texto == "" or (isinstance(texto, float) and pd.isna(texto)):
        return None
    data = pd.to_datetime(texto, errors="coerce")
    if pd.isna(data):
        return None
    indice = data.year * 12 + data.month - 1
    return indice if data.day == monthrange(data.year, data.month)[1] else indice - 1


def _arredondar(valor):
    return None if valor is None or pd.isna(valor) else round(float(valor), 2)


def _percentual(custo, faturamento):
    return round(custo / faturamento * 100, 1) if faturamento and faturamento > 0 else None


def meses_de_custo(admissao: str, inicio: int, fim: int) -> int:
    """Quantos meses do período o promotor já estava contratado (mês da admissão conta inteiro)."""
    comeco = max(inicio, _indice_data(admissao) if _indice_data(admissao) is not None else inicio)
    return max(0, fim - comeco + 1)


def aplicar_tipos_de_nota(faturamento: pd.DataFrame, regras: dict) -> pd.DataFrame:
    """Escolhe a coluna de valor e soma, desconta ou tira cada tipo de nota conforme as regras."""
    fat = faturamento.copy()
    if "valor" not in fat:
        coluna = regras["valor_faturamento"]
        fat["valor"] = fat[coluna] if coluna in fat else fat["total_venda"]
    if regras["somente_receita"] and "receita" in fat:
        fat = fat[fat["receita"].map(normalizar_texto).isin({"SIM", "S"})]
    acoes = fat["chave_tipo"].map(lambda c: regras["tipos_nf"].get(c, regras["tipos_nf_padrao"]))
    fat = fat[acoes != "ignora"].copy()
    acoes = acoes[acoes != "ignora"]
    fat["valor"] = fat["valor"].astype(float).where(acoes == "soma", -fat["valor"].astype(float).abs())
    fat["notas"] = fat["notas"].where(acoes == "soma", 0)
    if "cod_cliente" not in fat:
        fat["cod_cliente"] = ""
    return fat


def cnpjs_separados_por_cod_cli(roteiro: pd.DataFrame) -> set[str]:
    """CNPJs com mais de uma loja no roteiro em que cada loja tem um COD CLI próprio (e diferente).

    Nesses casos o faturamento é separado por COD CLI; nos demais, as lojas dividem o valor do CNPJ.
    """
    if "cod_cli" not in roteiro:
        return set()
    lojas = roteiro[roteiro["cnpj"].fillna("") != ""].drop_duplicates(["cnpj", "loja"])
    separados = set()
    for cnpj, codigos in lojas.groupby("cnpj")["cod_cli"]:
        codigos = [c or "" for c in codigos]
        if len(codigos) > 1 and all(codigos) and len(set(codigos)) == len(codigos):
            separados.add(cnpj)
    return separados


def custos_por_mes(promotores: pd.DataFrame, custos: pd.DataFrame | None, meses: range) -> tuple[dict, dict]:
    """Custo de cada promotor em cada mês (competência) e o custo mensal vigente no fim do período.

    Sem tabela de custos (formato antigo), usa o custo mensal atual em todos os meses.
    """
    vigencias = {}
    if custos is not None and not custos.empty:
        for c in custos.itertuples():
            vigencias.setdefault(c.codigo, []).append((int(c.ano) * 12 + int(c.mes) - 1, float(c.total)))
        for lista in vigencias.values():
            lista.sort()
    por_mes, mensal_atual = {}, {}
    for p in promotores.itertuples():
        lista = [(-1, float(p.custo_mensal or 0))] if custos is None else vigencias.get(p.codigo, [])

        def custo_em(mes):
            anteriores = [v for v in lista if v[0] <= mes]
            return anteriores[-1][1] if anteriores else 0.0

        admissao = _indice_data(p.admissao)
        desligamento = _indice_data(getattr(p, "desligamento", ""))
        por_mes[p.codigo] = {
            m: (0.0 if (admissao is not None and m < admissao) or (desligamento is not None and m > desligamento)
                else custo_em(m)) for m in meses}
        mensal_atual[p.codigo] = custo_em(meses[-1])
    return por_mes, mensal_atual


def calcular_painel(faturamento: pd.DataFrame, promotores: pd.DataFrame, roteiro: pd.DataFrame,
                    filtros: Filtros, regras: dict | None = None, custos: pd.DataFrame | None = None) -> dict:
    regras = {**REGRAS_PADRAO, **(regras or {})}
    inicio, fim = indice_mes(filtros.inicio), indice_mes(filtros.fim)
    if inicio > fim:
        inicio, fim = fim, inicio
    meses = range(inicio, fim + 1)

    # --- Roteiro: uma linha por (vínculo, mês em que estava vigente no período) ---------------
    roteiro, _ = vincular_roteiro(roteiro, promotores)
    roteiro = roteiro.reset_index(drop=True).copy()
    roteiro["linha"] = roteiro.index
    roteiro["cnpj"] = roteiro["cnpj"].fillna("")
    separados = cnpjs_separados_por_cod_cli(roteiro)

    def chave_com_cod_cli(cnpj, cod_cli):
        # Lojas com o mesmo CNPJ e COD CLI diferentes: cada uma fica com o faturamento do seu código.
        return f"{cnpj}#{cod_cli}" if cnpj in separados else cnpj

    roteiro["chave"] = [chave_com_cod_cli(c, k) for c, k in
                        zip(roteiro["cnpj"], roteiro["cod_cli"] if "cod_cli" in roteiro else [""] * len(roteiro))]
    tem_datas = "data_inicio" in roteiro
    roteiro["meses"] = [
        list(range(max(inicio, _indice_data(r.data_inicio) if tem_datas and _indice_data(r.data_inicio) is not None
                       else inicio),
                   min(fim, _ultimo_mes_vigente(r.data_fim) if tem_datas and _ultimo_mes_vigente(r.data_fim) is not None
                       else fim) + 1))
        for r in roteiro.itertuples()]
    roteiro = roteiro[roteiro["meses"].map(len) > 0]
    ativos = (roteiro[["linha", "codigo_promotor", "chave", "loja", "visitas_semana", "meses"]]
              .explode("meses").rename(columns={"meses": "mes"}))
    ativos["mes"] = ativos["mes"].astype(int)

    # Quantas lojas dividem o mesmo CNPJ (no roteiro inteiro, não só no filtro).
    com_chave = ativos[ativos["chave"] != ""]
    lojas_por_chave = com_chave.drop_duplicates(["chave", "loja"]).groupby("chave").size()

    # --- Faturamento mensal por CNPJ (ou CNPJ + COD CLI) ------------------------------------
    fat = aplicar_tipos_de_nota(faturamento, regras)
    fat["mes"] = fat["ano"].astype(int) * 12 + fat["mes"].astype(int) - 1
    fat = fat[(fat["mes"] >= inicio) & (fat["mes"] <= fim)]
    fat["chave"] = [chave_com_cod_cli(c, k) for c, k in zip(fat["cnpj"], fat["cod_cliente"])]
    mensal = fat.groupby(["chave", "mes"]).agg(valor=("valor", "sum"), notas=("notas", "sum")).reset_index()

    ativos = ativos.merge(mensal, on=["chave", "mes"], how="left")
    ativos[["valor", "notas"]] = ativos[["valor", "notas"]].fillna(0)
    ativos.loc[ativos["chave"] == "", ["valor", "notas"]] = 0

    # --- Custo: por mês da competência, dividido entre as lojas do promotor naquele mês ------
    custo_mes, custo_atual = custos_por_mes(promotores, custos, meses)
    visitas = pd.to_numeric(ativos["visitas_semana"], errors="coerce")
    ativos["peso"] = 1.0
    if regras["rateio_custo"] == "visitas":
        grupo = ativos.assign(v=visitas).groupby(["codigo_promotor", "mes"])["v"]
        todas_com_visita = grupo.transform(lambda v: v.notna().all() and v.sum() > 0)
        ativos.loc[todas_com_visita, "peso"] = visitas[todas_com_visita].astype(float)
    soma_pesos = ativos.groupby(["codigo_promotor", "mes"])["peso"].transform("sum")
    custo_do_mes = [custo_mes.get(c, {}).get(m, 0.0) for c, m in zip(ativos["codigo_promotor"], ativos["mes"])]
    ativos["custo"] = pd.Series(custo_do_mes, index=ativos.index) * ativos["peso"] / soma_pesos

    # --- Filtros ---------------------------------------------------------------------------
    proms = promotores.copy()
    if filtros.supervisor:
        proms = proms[proms["supervisor"].map(normalizar_texto) == normalizar_texto(filtros.supervisor)]
    if filtros.promotor:
        proms = proms[proms["codigo"] == filtros.promotor]
    lojas = roteiro[roteiro["codigo_promotor"].isin(proms["codigo"])]
    if filtros.uf:
        lojas = lojas[lojas["uf"].str.upper() == filtros.uf.upper()]
    if filtros.cidade:
        lojas = lojas[lojas["cidade"].map(normalizar_texto) == normalizar_texto(filtros.cidade)]
    if filtros.pdv:
        lojas = lojas[lojas["loja"].map(normalizar_texto) == normalizar_texto(filtros.pdv)]
    if filtros.uf or filtros.cidade or filtros.pdv:
        # Filtrando por local, só interessam os promotores que atendem ali.
        proms = proms[proms["codigo"].isin(lojas["codigo_promotor"])]
    ativos = ativos[ativos["linha"].isin(lojas["linha"])]

    def somar_faturamento(linhas):
        validas = linhas[linhas["chave"] != ""]
        return validas.drop_duplicates(["chave", "mes"])["valor"].sum()

    # --- Por linha do roteiro (loja × promotor) ------------------------------------------------
    por_linha = ativos.groupby("linha").agg(
        faturamento=("valor", "sum"), custo_periodo=("custo", "sum"), meses_ativos=("mes", "nunique"))
    lojas = lojas.join(por_linha, on="linha")
    lojas[["faturamento", "custo_periodo", "meses_ativos"]] = (
        lojas[["faturamento", "custo_periodo", "meses_ativos"]].fillna(0))
    lojas["lojas_mesma_chave"] = lojas["chave"].map(lojas_por_chave).fillna(1).astype(int)
    lojas.loc[lojas["chave"] == "", "lojas_mesma_chave"] = 1
    lojas["compartilhado"] = lojas["lojas_mesma_chave"] > 1

    nomes = dict(zip(proms["codigo"], proms["nome"]))
    supervisores = dict(zip(proms["codigo"], proms["supervisor"]))

    # --- Tabela por promotor -------------------------------------------------------------------
    linhas_promotores = []
    for p in proms.itertuples():
        lojas_p = lojas[lojas["codigo_promotor"] == p.codigo]
        fat_p = somar_faturamento(ativos[ativos["codigo_promotor"] == p.codigo])
        custo_p = sum(custo_mes[p.codigo].values())
        visitas_p = pd.to_numeric(lojas_p["visitas_semana"], errors="coerce").dropna()
        linhas_promotores.append({
            "codigo": p.codigo, "nome": p.nome, "supervisor": p.supervisor, "municipio": p.municipio,
            "uf": (getattr(p, "uf", "") or "").upper() or "—",
            "custo_mensal": _arredondar(custo_atual[p.codigo]), "custo_periodo": _arredondar(custo_p),
            "lojas": int(lojas_p.drop_duplicates(["chave", "loja"]).shape[0]),
            "visitas_semana": _arredondar(visitas_p.sum()) if not visitas_p.empty else None,
            "faturamento": _arredondar(fat_p),
            "percentual_custo": _percentual(custo_p, fat_p),
        })
    linhas_promotores.sort(key=lambda l: (l["percentual_custo"] is None, -(l["percentual_custo"] or 0)))

    # --- Tabela por loja -------------------------------------------------------------------------
    linhas_lojas = []
    for l in lojas.itertuples():
        visitas_l = pd.to_numeric(l.visitas_semana, errors="coerce")
        visitas_periodo = 0 if pd.isna(visitas_l) else visitas_l * SEMANAS_POR_MES * l.meses_ativos
        linhas_lojas.append({
            "loja": l.loja, "cnpj": l.cnpj, "cidade": l.cidade, "uf": l.uf,
            "codigo_promotor": l.codigo_promotor, "promotor": nomes.get(l.codigo_promotor, ""),
            "supervisor": supervisores.get(l.codigo_promotor, ""),
            "visitas_semana": _arredondar(visitas_l),
            "faturamento": _arredondar(l.faturamento),
            "lojas_mesmo_cnpj": int(l.lojas_mesma_chave),
            "compartilhado": bool(l.compartilhado),
            "separado_por_cod_cli": l.cnpj in separados,
            "custo_periodo": _arredondar(l.custo_periodo),
            "percentual_custo": None if l.compartilhado else _percentual(l.custo_periodo, l.faturamento),
            # Quanto a loja comprou para cada visita do promotor no período.
            "faturamento_por_visita": (_arredondar(l.faturamento / visitas_periodo)
                                       if visitas_periodo > 0 and not l.compartilhado else None),
        })
    linhas_lojas.sort(key=lambda l: l["faturamento"])

    # --- Resumo ------------------------------------------------------------------------------------
    custo_total = sum(l["custo_periodo"] for l in linhas_promotores)
    fat_total = somar_faturamento(ativos)
    unicas = lojas.drop_duplicates(["chave", "loja"])
    visitas_total = pd.to_numeric(lojas["visitas_semana"], errors="coerce").sum()
    resumo = {
        "meses": len(meses),
        "promotores": len(linhas_promotores),
        "lojas": int(len(unicas)),
        "visitas_semana": _arredondar(visitas_total) if visitas_total else None,
        "custo": _arredondar(custo_total),
        "faturamento": _arredondar(fat_total),
        "percentual_custo": _percentual(custo_total, fat_total),
        "cnpjs_compartilhados": int(unicas[unicas["compartilhado"]]["chave"].nunique()),
        # Lojas do roteiro (com CNPJ) que não compraram nada no período. A planilha não tem as visitas
        # por semana, então toda loja do roteiro conta como visitada.
        "lojas_sem_compra": int(((unicas["faturamento"] <= 0) & (unicas["chave"] != "")).sum()),
    }
    regras_usadas = {c: regras[c] for c in ("rateio_custo", "limite_percentual")}
    bloco_custos = _bloco_custos(proms, custos, fim)
    return {"resumo": resumo, "promotores": linhas_promotores, "lojas": linhas_lojas, "regras": regras_usadas,
            "grade": _grade_mes_a_mes(lojas, ativos, meses, nomes, supervisores, separados),
            "custos": bloco_custos,
            "por_uf": _resumo_por_uf(proms, lojas, ativos, custo_mes, bloco_custos, somar_faturamento)}


def _resumo_por_uf(proms, lojas, ativos, custo_mes, bloco_custos, somar_faturamento) -> list:
    """Os 3 blocos da aba RESUMO (monitoramento, custo e faturamento) por UF e supervisor do promotor.

    Uma linha por UF (subtotal) seguida das linhas dos supervisores daquela UF.
    """
    custo_mensal = {c["codigo"]: c for c in bloco_custos}
    proms = proms.assign(uf=proms["uf"].fillna("").str.upper() if "uf" in proms else "")

    def linha(nivel, uf, supervisor, grupo):
        codigos = set(grupo["codigo"])
        lojas_g = lojas[lojas["codigo_promotor"].isin(codigos)]
        visitas = pd.to_numeric(lojas_g["visitas_semana"], errors="coerce").dropna()
        custo = sum(sum(custo_mes[c].values()) for c in codigos)
        fat = somar_faturamento(ativos[ativos["codigo_promotor"].isin(codigos)])
        mensal = {campo: _arredondar(sum(custo_mensal[c][campo] for c in codigos if c in custo_mensal))
                  for campo in ("salario", "ajuda_custo", "vale_transporte", "outros", "total")}
        return {"nivel": nivel, "uf": uf or "—", "supervisor": supervisor or "(sem supervisor)",
                "promotores": len(codigos), "lojas": int(lojas_g.drop_duplicates(["chave", "loja"]).shape[0]),
                "visitas_semana": _arredondar(visitas.sum()) if not visitas.empty else None,
                "custo_mensal": mensal, "custo_periodo": _arredondar(custo), "faturamento": _arredondar(fat),
                "percentual_custo": _percentual(custo, fat)}

    linhas = []
    for uf, grupo_uf in sorted(proms.groupby("uf"), key=lambda g: (g[0] == "", g[0])):
        linhas.append(linha("uf", uf, "", grupo_uf))
        for supervisor, grupo in sorted(grupo_uf.groupby("supervisor"), key=lambda g: (g[0] == "", g[0])):
            linhas.append(linha("supervisor", uf, supervisor, grupo))
    return linhas


def _inteiro_ou_nada(valor):
    return None if valor is None or pd.isna(valor) else int(valor)


def _rotulo_mes(indice: int) -> str:
    return f"{indice // 12}-{indice % 12 + 1:02d}"


def _grade_mes_a_mes(lojas, ativos, meses, nomes, supervisores, separados) -> dict:
    """Faturamento de cada loja × promotor mês a mês, como as abas SC, SP, PR… da planilha.

    A linha de totais conta cada CNPJ uma vez por mês.
    """
    rotulos = [_rotulo_mes(m) for m in meses]
    valores = ativos.groupby(["linha", "mes"])["valor"].sum()
    linhas = []
    for l in lojas.itertuples():
        por_mes = {_rotulo_mes(m): round(float(valores.get((l.linha, m), 0.0)), 2) for m in meses}
        linhas.append({
            "linha": int(l.linha), "roteiro_id": _inteiro_ou_nada(getattr(l, "roteiro_id", None)),
            "supervisor": supervisores.get(l.codigo_promotor, ""),
            "promotor": nomes.get(l.codigo_promotor, ""), "cnpj": l.cnpj, "loja": l.loja, "cidade": l.cidade,
            "uf": l.uf, "meses": por_mes, "total": round(sum(por_mes.values()), 2),
            "compartilhado": bool(l.compartilhado),
            # Para abrir as notas do valor: CNPJ e, se separado, o COD CLI.
            "detalhe": {"cnpj": l.cnpj, "cod_cli": (getattr(l, "cod_cli", "") or "") if l.cnpj in separados else ""},
        })
    validas = ativos[ativos["chave"] != ""]
    por_mes_total = validas.drop_duplicates(["chave", "mes"]).groupby("mes")["valor"].sum()
    totais = {_rotulo_mes(m): round(float(por_mes_total.get(m, 0.0)), 2) for m in meses}
    return {"meses": rotulos, "linhas": linhas, "totais": {**totais, "total": round(sum(totais.values()), 2)}}


def _bloco_custos(proms: pd.DataFrame, custos: pd.DataFrame | None, fim: int) -> list:
    """Custo de cada promotor vigente no último mês do período, como a aba PROMOTORES BRASIL."""
    linhas = []
    for p in proms.sort_values("nome").itertuples():
        valores = {"salario": float(p.salario or 0), "ajuda_custo": float(p.ajuda_custo or 0),
                   "vale_transporte": float(p.transporte or 0), "outros": 0.0}
        if custos is not None:
            vigencias = custos[(custos["codigo"] == p.codigo)
                               & (custos["ano"].astype(int) * 12 + custos["mes"].astype(int) - 1 <= fim)]
            if vigencias.empty:
                valores = dict.fromkeys(valores, 0.0)
            else:
                ultima = vigencias.sort_values(["ano", "mes"]).iloc[-1]
                valores = {c: float(ultima.get(c, 0) or 0) for c in valores}
        linhas.append({"codigo": p.codigo, "nome": p.nome, "supervisor": p.supervisor, "municipio": p.municipio,
                       **{c: round(v, 2) for c, v in valores.items()}, "total": round(sum(valores.values()), 2)})
    return linhas


def tipos_de_nota(faturamento: pd.DataFrame, regras: dict) -> list:
    """Tipos de nota existentes no faturamento importado, com a ação de cada um."""
    if faturamento.empty:
        return []
    coluna = regras["valor_faturamento"]
    tipos = (faturamento.groupby("chave_tipo")
                        .agg(tipo=("tipo_nf", "first"), notas=("notas", "sum"), valor=(coluna, "sum"))
                        .reset_index().sort_values("valor", ascending=False))
    return [{"chave": t.chave_tipo, "tipo": t.tipo, "notas": int(t.notas), "valor": _arredondar(t.valor),
             "acao": regras["tipos_nf"].get(t.chave_tipo, regras["tipos_nf_padrao"]),
             "na_lista": t.chave_tipo in regras["tipos_nf"]} for t in tipos.itertuples()]


def opcoes_de_filtro(faturamento: pd.DataFrame, promotores: pd.DataFrame, roteiro: pd.DataFrame,
                     pendentes: list | None = None) -> dict:
    roteiro, sem_vinculo = vincular_roteiro(roteiro, promotores)
    meses = sorted({f"{int(a)}-{int(m):02d}" for a, m in zip(faturamento["ano"], faturamento["mes"])})
    locais = (roteiro[["uf", "cidade"]].replace("", pd.NA).dropna()
              .drop_duplicates().sort_values(["uf", "cidade"]))
    pdvs = (roteiro[["loja", "cidade", "uf"]].drop_duplicates("loja").sort_values("loja"))
    return {
        "meses": meses,
        "pdvs": [{"nome": p.loja, "cidade": p.cidade, "uf": p.uf} for p in pdvs.itertuples()],
        "supervisores": sorted(s for s in promotores["supervisor"].unique() if s),
        "promotores": [{"codigo": p.codigo, "nome": p.nome, "supervisor": p.supervisor}
                       for p in promotores.sort_values("nome").itertuples()],
        "ufs": sorted(locais["uf"].unique().tolist()),
        "cidades": [{"uf": l.uf, "cidade": l.cidade} for l in locais.itertuples()],
        "roteiro_sem_vinculo": sem_vinculo if pendentes is None else pendentes,
    }


def resumo_faturamento(faturamento: pd.DataFrame, regras: dict, cnpjs_no_roteiro: set[str]) -> dict:
    """Aba Faturamento: tudo o que veio do ERP no período, por UF e por cliente, mês a mês.

    Mostra todos os clientes, atendidos por promotor ou não (coluna "no_roteiro").
    """
    fat = aplicar_tipos_de_nota(faturamento, regras)
    if fat.empty:
        return {"meses": [], "por_uf": [], "totais": {"total": 0.0}, "clientes": []}
    fat["rotulo"] = [f"{int(a)}-{int(m):02d}" for a, m in zip(fat["ano"], fat["mes"])]
    meses = sorted(fat["rotulo"].unique())
    fat["uf"] = fat["uf"].str.upper().replace("", "—")

    def tabela(indice):
        return fat.pivot_table(index=indice, columns="rotulo", values="valor", aggfunc="sum", fill_value=0.0)

    contagem = fat.groupby("uf")["cnpj"].nunique()
    por_uf = [{"uf": uf, "meses": {m: _arredondar(v) for m, v in linha.items()}, "total": _arredondar(linha.sum()),
               "clientes": int(contagem[uf])}
              for uf, linha in tabela("uf").iterrows()]
    por_uf.sort(key=lambda l: (l["uf"] == "—", l["uf"]))
    por_mes = fat.groupby("rotulo")["valor"].sum()
    totais = {m: _arredondar(por_mes.get(m, 0.0)) for m in meses}
    total = _arredondar(por_mes.sum())

    # Razão social, cidade e UF do último mês em que o cliente comprou.
    dados = fat.sort_values(["ano", "mes"]).drop_duplicates("cnpj", keep="last").set_index("cnpj")
    notas = fat.groupby("cnpj")["notas"].sum()
    clientes = [{"cnpj": cnpj, "razao_social": dados.at[cnpj, "razao_social"], "cidade": dados.at[cnpj, "cidade"],
                 "uf": dados.at[cnpj, "uf"], "meses": {m: _arredondar(v) for m, v in linha.items()},
                 "total": _arredondar(linha.sum()), "notas": int(notas[cnpj]), "no_roteiro": cnpj in cnpjs_no_roteiro}
                for cnpj, linha in tabela("cnpj").iterrows()]
    clientes.sort(key=lambda c: -c["total"])
    return {"meses": meses, "por_uf": por_uf, "totais": {**totais, "total": total}, "clientes": clientes}
