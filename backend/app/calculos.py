"""Cálculos do painel: custo dos promotores × faturamento das lojas que eles atendem.

O cálculo é feito mês a mês e depois somado no período escolhido:
- Faturamento: cada linha do roteiro recebe o faturamento dos meses em que estava vigente
  (vale o vínculo vigente no último dia do mês). Trocar o promotor de uma loja não muda o que
  foi atribuído ao promotor antigo nos meses anteriores.
- Custo: em cada mês vale o custo da competência (último reajuste até aquele mês), contado a
  partir do mês de admissão e até o mês de desligamento. Reajuste não muda meses anteriores.

As regras ajustáveis vêm de app/regras.py (aba "Regras do cálculo"):
- tipos de nota: cada tipo soma, desconta ou fica de fora do faturamento;
- modo de rede: faturamento pelo CNPJ exato da loja, pela rede inteira (raiz do CNPJ,
  os 8 primeiros dígitos) ou pela rede dividida igualmente entre as lojas dela;
- custo: + encargos (% do salário) + custo extra fixo;
- divisão do custo do promotor entre as lojas dele: igual ou pelas visitas por semana;
- faixas de cor do % de custo sobre faturamento.

Regras fixas:
- Quando várias lojas mostram o mesmo valor (CNPJ ou rede compartilhados), os totais contam
  esse valor uma vez só, e o % de custo dessas lojas não é calculado.
- Se uma loja tem mais de um promotor ao mesmo tempo, o faturamento conta para cada um deles.
"""
from calendar import monthrange
from dataclasses import dataclass

import pandas as pd

from .importacao import normalizar_texto, vincular_roteiro
from .regras import REGRAS_PADRAO


@dataclass
class Filtros:
    inicio: str            # "AAAA-MM"
    fim: str               # "AAAA-MM"
    supervisor: str = ""
    promotor: str = ""     # código do promotor
    uf: str = ""
    cidade: str = ""


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


def raiz_cnpj(cnpj: str) -> str:
    """Os 8 primeiros dígitos identificam a empresa; todas as filiais têm a mesma raiz."""
    return cnpj[:8] if len(cnpj) == 14 else cnpj


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


def custos_por_mes(promotores: pd.DataFrame, custos: pd.DataFrame | None, regras: dict,
                   meses: range) -> tuple[dict, dict]:
    """Custo de cada promotor em cada mês e o custo mensal vigente no fim do período.

    Sem tabela de custos (formato antigo), usa o custo mensal atual em todos os meses.
    """
    encargos, extra = regras["encargos_percentual"] / 100, regras["custo_extra_mensal"]
    vigencias = {}
    if custos is not None and not custos.empty:
        for c in custos.itertuples():
            vigencias.setdefault(c.codigo, []).append((int(c.ano) * 12 + int(c.mes) - 1, float(c.total),
                                                       float(c.salario)))
        for lista in vigencias.values():
            lista.sort()
    por_mes, mensal_atual = {}, {}
    for p in promotores.itertuples():
        if custos is None:
            lista = [(-1, float(p.custo_mensal or 0), float(p.salario or 0))]
        else:
            lista = vigencias.get(p.codigo, [])

        def custo_em(mes):
            anteriores = [v for v in lista if v[0] <= mes]
            if not anteriores:
                return 0.0
            _, total, salario = anteriores[-1]
            return total + salario * encargos + extra

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
    por_rede = regras["modo_rede"] != "cnpj"
    dividido = regras["modo_rede"] == "rede_dividido"
    chave_de = raiz_cnpj if por_rede else (lambda c: c)

    # --- Roteiro: uma linha por (vínculo, mês em que estava vigente no período) ---------------
    roteiro, _ = vincular_roteiro(roteiro, promotores)
    roteiro = roteiro.reset_index(drop=True).copy()
    roteiro["linha"] = roteiro.index
    roteiro["cnpj"] = roteiro["cnpj"].fillna("")
    separados = set() if por_rede else cnpjs_separados_por_cod_cli(roteiro)

    def chave_com_cod_cli(cnpj, cod_cli):
        # Lojas com o mesmo CNPJ e COD CLI diferentes: cada uma fica com o faturamento do seu código.
        return f"{cnpj}#{cod_cli}" if cnpj in separados else chave_de(cnpj)

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

    # Quantas lojas dividem o mesmo CNPJ/rede (no roteiro inteiro, não só no filtro).
    com_chave = ativos[ativos["chave"] != ""]
    lojas_por_chave_mes = com_chave.drop_duplicates(["chave", "loja", "mes"]).groupby(["chave", "mes"]).size()
    lojas_por_chave = com_chave.drop_duplicates(["chave", "loja"]).groupby("chave").size()

    # --- Faturamento mensal por CNPJ ou rede ------------------------------------------------
    fat = aplicar_tipos_de_nota(faturamento, regras)
    fat["mes"] = fat["ano"].astype(int) * 12 + fat["mes"].astype(int) - 1
    fat = fat[(fat["mes"] >= inicio) & (fat["mes"] <= fim)]
    fat["chave"] = [chave_com_cod_cli(c, k) for c, k in zip(fat["cnpj"], fat["cod_cliente"])]
    mensal = fat.groupby(["chave", "mes"]).agg(valor=("valor", "sum"), notas=("notas", "sum")).reset_index()

    ativos = ativos.merge(mensal, on=["chave", "mes"], how="left")
    ativos[["valor", "notas"]] = ativos[["valor", "notas"]].fillna(0)
    ativos.loc[ativos["chave"] == "", ["valor", "notas"]] = 0
    if dividido:
        divisor = pd.Series(list(zip(ativos["chave"], ativos["mes"]))).map(lojas_por_chave_mes).fillna(1).values
        ativos["valor"] = ativos["valor"] / divisor

    # --- Custo: por mês da competência, dividido entre as lojas do promotor naquele mês ------
    custo_mes, custo_atual = custos_por_mes(promotores, custos, regras, meses)
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
    if filtros.uf or filtros.cidade:
        # Filtrando por local, só interessam os promotores que atendem ali.
        proms = proms[proms["codigo"].isin(lojas["codigo_promotor"])]
    ativos = ativos[ativos["linha"].isin(lojas["linha"])]

    def somar_faturamento(linhas):
        validas = linhas[linhas["chave"] != ""]
        return validas.drop_duplicates(["chave", "loja", "mes"] if dividido else ["chave", "mes"])["valor"].sum()

    # --- Por linha do roteiro (loja × promotor) ------------------------------------------------
    por_linha = ativos.groupby("linha").agg(
        faturamento=("valor", "sum"), notas=("notas", "sum"), custo_periodo=("custo", "sum"),
        meses_ativos=("mes", "nunique"),
        meses_com_compra=("valor", lambda v: int((v > 0).sum())))
    lojas = lojas.join(por_linha, on="linha")
    lojas[["faturamento", "notas", "custo_periodo", "meses_ativos", "meses_com_compra"]] = (
        lojas[["faturamento", "notas", "custo_periodo", "meses_ativos", "meses_com_compra"]].fillna(0))
    lojas["lojas_mesma_chave"] = lojas["chave"].map(lojas_por_chave).fillna(1).astype(int)
    lojas.loc[lojas["chave"] == "", "lojas_mesma_chave"] = 1
    lojas["compartilhado"] = (lojas["lojas_mesma_chave"] > 1) & (not dividido)

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
            "custo_mensal": _arredondar(custo_atual[p.codigo]), "custo_periodo": _arredondar(custo_p),
            "lojas": int(lojas_p.drop_duplicates(["chave", "loja"]).shape[0]),
            "lojas_sem_compra": int((lojas_p["faturamento"] <= 0).sum()),
            "visitas_semana": _arredondar(visitas_p.sum()) if not visitas_p.empty else None,
            "faturamento": _arredondar(fat_p),
            "percentual_custo": _percentual(custo_p, fat_p),
        })
    linhas_promotores.sort(key=lambda l: (l["percentual_custo"] is None, -(l["percentual_custo"] or 0)))

    # --- Tabela por loja -------------------------------------------------------------------------
    semanas = regras["semanas_por_mes"]
    linhas_lojas = []
    for l in lojas.itertuples():
        visitas_l = pd.to_numeric(l.visitas_semana, errors="coerce")
        visitas_mes = 0 if pd.isna(visitas_l) else visitas_l * semanas
        custo_mensal_loja = l.custo_periodo / l.meses_ativos if l.meses_ativos else 0
        linhas_lojas.append({
            "loja": l.loja, "cnpj": l.cnpj, "cidade": l.cidade, "uf": l.uf,
            "codigo_promotor": l.codigo_promotor, "promotor": nomes.get(l.codigo_promotor, ""),
            "supervisor": supervisores.get(l.codigo_promotor, ""),
            "visitas_semana": _arredondar(visitas_l),
            "faturamento": _arredondar(l.faturamento), "notas": int(l.notas),
            "meses_com_compra": int(l.meses_com_compra),
            "lojas_mesmo_cnpj": int(l.lojas_mesma_chave),
            "compartilhado": bool(l.compartilhado),
            "separado_por_cod_cli": l.cnpj in separados,
            "custo_periodo": _arredondar(l.custo_periodo),
            "percentual_custo": None if l.compartilhado else _percentual(l.custo_periodo, l.faturamento),
            "custo_por_visita": _arredondar(custo_mensal_loja / visitas_mes) if visitas_mes > 0 else None,
        })
    linhas_lojas.sort(key=lambda l: l["faturamento"])

    # --- Resumo ------------------------------------------------------------------------------------
    custo_total = sum(l["custo_periodo"] for l in linhas_promotores)
    fat_total = somar_faturamento(ativos)
    unicas = lojas.drop_duplicates(["chave", "loja"])
    fat_por_loja = (ativos.drop_duplicates(["chave", "loja", "mes"]).groupby(["chave", "loja"])["valor"].sum())
    sem_compra = sum(1 for chave, loja in zip(unicas["chave"], unicas["loja"])
                     if fat_por_loja.get((chave, loja), 0) <= 0)
    visitas_total = pd.to_numeric(lojas["visitas_semana"], errors="coerce").sum()
    resumo = {
        "meses": len(meses),
        "promotores": len(linhas_promotores),
        "lojas": int(len(unicas)),
        "lojas_sem_compra": int(sem_compra),
        "visitas_semana": _arredondar(visitas_total) if visitas_total else None,
        "custo": _arredondar(custo_total),
        "faturamento": _arredondar(fat_total),
        "percentual_custo": _percentual(custo_total, fat_total),
        "cnpjs_compartilhados": int(unicas[unicas["compartilhado"]]["chave"].nunique()),
    }
    regras_usadas = {c: regras[c] for c in ("modo_rede", "rateio_custo", "faixa_alerta", "faixa_critico")}
    return {"resumo": resumo, "promotores": linhas_promotores, "lojas": linhas_lojas, "regras": regras_usadas}


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
    return {
        "meses": meses,
        "supervisores": sorted(s for s in promotores["supervisor"].unique() if s),
        "promotores": [{"codigo": p.codigo, "nome": p.nome, "supervisor": p.supervisor}
                       for p in promotores.sort_values("nome").itertuples()],
        "ufs": sorted(locais["uf"].unique().tolist()),
        "cidades": [{"uf": l.uf, "cidade": l.cidade} for l in locais.itertuples()],
        "roteiro_sem_vinculo": sem_vinculo if pendentes is None else pendentes,
    }
