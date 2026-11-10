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
separado pelo COD CLI; senão, o faturamento do CNPJ é dividido em partes iguais entre as lojas e
elas aparecem como "faturamento compartilhado" (sem % de custo).
Se uma loja tem mais de um promotor ao mesmo tempo, o faturamento dela é dividido entre eles.
Assim a soma por promotor, supervisor ou UF sempre bate com o total.

Só contam os meses em que o promotor estava contratado (admissão → desligamento) e que já
aconteceram (meses futuros ficam fora).

"""
import re
from bisect import bisect_right
from calendar import monthrange
from datetime import date
from functools import lru_cache
from datetime import date
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
    """'2026-03' -> ano × 12 + mês − 1. Recusa (ValueError) mês 00, 13, texto fora do formato e ano absurdo."""
    achado = re.fullmatch(r"(\d{4})-(\d{2})", str(ano_mes).strip())
    if not achado:
        raise ValueError("Período inválido. Use AAAA-MM.")
    ano, mes = int(achado.group(1)), int(achado.group(2))
    if not 1 <= mes <= 12 or not 2000 <= ano <= 2100:
        raise ValueError("Período inválido. Use AAAA-MM com mês de 01 a 12.")
    return ano * 12 + mes - 1


@lru_cache(maxsize=4096)
def _ler_data(texto):
    """'2026-03-15' (ou date) -> date; vazio ou inválido -> None.

    As datas dos cadastros vêm sempre como AAAA-MM-DD: lidas direto, sem o pd.to_datetime (genérico, que tenta
    adivinhar o formato a cada chamada e respondia por mais da metade do tempo do Resumo).
    """
    if texto is None or texto == "" or (isinstance(texto, float) and pd.isna(texto)):
        return None
    if isinstance(texto, date):
        return texto
    try:
        return date.fromisoformat(str(texto).strip()[:10])
    except ValueError:
        data = pd.to_datetime(texto, errors="coerce")
        return None if pd.isna(data) else data.date()


def _indice_data(texto):
    """'2026-03-15' -> índice do mês (ano × 12 + mês − 1); vazio -> None."""
    data = _ler_data(texto)
    return None if data is None else data.year * 12 + data.month - 1


def _ultimo_mes_vigente(texto):
    """Último mês em que o vínculo vale: só conta o mês se estava vigente no último dia dele."""
    data = _ler_data(texto)
    if data is None:
        return None
    indice = data.year * 12 + data.month - 1
    return indice if data.day == monthrange(data.year, data.month)[1] else indice - 1


def _se_paga(linha: dict, margem) -> None:
    """Acrescenta à linha (promotor, loja ou resumo) o lucro estimado e o resultado.

    lucro estimado = faturamento × margem da 101; resultado = lucro estimado − custo do promotor no período.
    Resultado ≥ 0: o promotor se paga (o lucro das vendas às lojas dele cobre o que a 101 paga a ele).
    Sem margem informada, os dois ficam vazios.
    """
    custo = linha.get("custo_periodo", linha.get("custo"))
    if margem is None or custo is None:
        linha["lucro_estimado"] = linha["resultado"] = linha["percentual_do_lucro"] = None
        return
    lucro = (linha.get("faturamento") or 0.0) * margem / 100
    linha["lucro_estimado"] = round(lucro, 2)
    linha["resultado"] = round(lucro - custo, 2)
    # Quanto do lucro das lojas vai para pagar o promotor: abaixo de 100% ele se paga.
    linha["percentual_do_lucro"] = round(custo / lucro * 100, 1) if lucro > 0 else None


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


def _coluna(df: pd.DataFrame, nome: str, padrao=""):
    return df[nome] if nome in df else pd.Series([padrao] * len(df), index=df.index, dtype=object)


def mes_atual() -> int:
    hoje = date.today()
    return hoje.year * 12 + hoje.month - 1


def custos_por_mes(promotores: pd.DataFrame, custos: pd.DataFrame | None, meses: range) -> tuple[dict, dict]:
    """Custo de cada promotor em cada mês (competência) e o custo mensal vigente no fim do período.

    Sem tabela de custos (formato antigo), usa o custo mensal atual em todos os meses.
    Fora do contrato (antes da admissão ou depois do desligamento) o custo é zero.
    """
    vigencias = {}
    if custos is not None and not custos.empty:
        indices = custos["ano"].astype(int) * 12 + custos["mes"].astype(int) - 1
        for codigo, indice, total in sorted(zip(custos["codigo"], indices, custos["total"]), key=lambda v: v[1]):
            lista = vigencias.setdefault(codigo, ([], []))
            lista[0].append(int(indice))
            lista[1].append(float(total or 0))
    por_mes, mensal_atual = {}, {}
    for codigo, admissao, desligamento, mensal in zip(
            promotores["codigo"], promotores["admissao"], _coluna(promotores, "desligamento"),
            _coluna(promotores, "custo_mensal", 0.0)):
        indices, valores = ([-1], [float(mensal or 0)]) if custos is None else vigencias.get(codigo, ([], []))

        def custo_em(mes, indices=indices, valores=valores):
            posicao = bisect_right(indices, mes)
            return valores[posicao - 1] if posicao else 0.0

        comeco, termino = _indice_data(admissao), _indice_data(desligamento)
        por_mes[codigo] = {m: (0.0 if (comeco is not None and m < comeco) or (termino is not None and m > termino)
                               else custo_em(m)) for m in meses}
        mensal_atual[codigo] = custo_em(meses[-1]) if len(meses) else 0.0
    return por_mes, mensal_atual


def calcular_painel(faturamento: pd.DataFrame, promotores: pd.DataFrame, roteiro: pd.DataFrame,
                    filtros: Filtros, regras: dict | None = None, custos: pd.DataFrame | None = None,
                    ultimo_mes: int | None = None) -> dict:
    """Painel do período. `ultimo_mes` (índice ano × 12 + mês − 1) é o mês corrente: meses depois dele
    ainda não aconteceram e ficam fora (antes o custo era projetado para o futuro)."""
    regras = {**REGRAS_PADRAO, **(regras or {})}
    inicio, fim = sorted((indice_mes(filtros.inicio), indice_mes(filtros.fim)))
    ultimo_mes = mes_atual() if ultimo_mes is None else ultimo_mes
    avisos = []
    if fim > ultimo_mes:
        avisos.append(f"Os meses depois de {_rotulo_mes(ultimo_mes)} ainda não aconteceram e ficaram fora do "
                      "cálculo (custo, lojas e faturamento).")
        fim = ultimo_mes
    meses = range(inicio, fim + 1)  # vazio se o período inteiro é futuro

    # --- Promotores: supervisor cadastrado na lista de promotores fica de fora -----------------
    promotores = promotores.copy()
    funcao = _coluna(promotores, "funcao").fillna("")
    fora = promotores[funcao == "Supervisor"]
    if not fora.empty:
        avisos.append(f"{len(fora)} supervisor(es) cadastrado(s) como promotor ficaram fora do custo e da "
                      "contagem: " + ", ".join(fora["nome"].head(5)) + (" …" if len(fora) > 5 else ""))
        promotores = promotores[funcao != "Supervisor"]
    # Meses do período em que cada promotor estava contratado.
    janela = {}
    for codigo, admissao, desligamento in zip(promotores["codigo"], promotores["admissao"],
                                              _coluna(promotores, "desligamento")):
        comeco, termino = _indice_data(admissao), _indice_data(desligamento)
        janela[codigo] = (max(inicio, comeco) if comeco is not None else inicio,
                          min(fim, termino) if termino is not None else fim)

    # --- Roteiro: uma linha por (vínculo, mês em que estava vigente E o promotor contratado) ----
    roteiro, _ = vincular_roteiro(roteiro, promotores)
    roteiro = roteiro.reset_index(drop=True).copy()
    roteiro["linha"] = roteiro.index
    roteiro["cnpj"] = roteiro["cnpj"].fillna("")
    roteiro["loja"] = roteiro["loja"].fillna("")
    separados = cnpjs_separados_por_cod_cli(roteiro)

    def chave_com_cod_cli(cnpj, cod_cli):
        # Lojas com o mesmo CNPJ e COD CLI diferentes: cada uma fica com o faturamento do seu código.
        return f"{cnpj}#{cod_cli}" if cnpj in separados else cnpj

    roteiro["chave"] = [chave_com_cod_cli(c, k) for c, k in zip(roteiro["cnpj"], _coluna(roteiro, "cod_cli"))]
    primeiros, ultimos = [], []
    for codigo, data_inicio, data_fim in zip(roteiro["codigo_promotor"], _coluna(roteiro, "data_inicio"),
                                             _coluna(roteiro, "data_fim")):
        comeco_p, termino_p = janela[codigo]
        comeco, termino = _indice_data(data_inicio), _ultimo_mes_vigente(data_fim)
        primeiros.append(max(comeco_p, comeco) if comeco is not None else comeco_p)
        ultimos.append(min(termino_p, termino) if termino is not None else termino_p)
    roteiro["primeiro"], roteiro["ultimo"] = primeiros, ultimos
    roteiro = roteiro[roteiro["primeiro"] <= roteiro["ultimo"]]
    quantos = (roteiro["ultimo"] - roteiro["primeiro"] + 1).astype(int)
    ativos = roteiro.loc[roteiro.index.repeat(quantos),
                         ["linha", "codigo_promotor", "chave", "loja", "visitas_semana", "primeiro"]].copy()
    ativos["mes"] = (ativos["primeiro"] + ativos.groupby(level=0).cumcount()).astype(int)
    ativos = ativos.drop(columns="primeiro").reset_index(drop=True)

    # Quantas lojas dividem o mesmo CNPJ (no roteiro inteiro, não só no filtro).
    com_chave = ativos[ativos["chave"] != ""]
    lojas_por_chave = com_chave.drop_duplicates(["chave", "loja"]).groupby("chave").size()

    # --- Faturamento mensal por CNPJ (ou CNPJ + COD CLI) ------------------------------------
    fat = aplicar_tipos_de_nota(faturamento, regras)
    fat["mes"] = fat["ano"].astype(int) * 12 + fat["mes"].astype(int) - 1
    fat = fat[(fat["mes"] >= inicio) & (fat["mes"] <= fim)].copy()
    fat["chave"] = [chave_com_cod_cli(c, k) for c, k in zip(fat["cnpj"], fat["cod_cliente"])]
    mensal = fat.groupby(["chave", "mes"]).agg(valor=("valor", "sum"), notas=("notas", "sum")).reset_index()

    # Tabelas vazias (ex.: período todo no futuro) vêm sem tipo; o merge exige texto × texto e inteiro × inteiro.
    for tabela in (ativos, mensal):
        tabela["chave"] = tabela["chave"].astype(str)
        tabela["mes"] = tabela["mes"].astype(int)
    ativos = ativos.merge(mensal, on=["chave", "mes"], how="left")
    ativos[["valor", "notas"]] = ativos[["valor", "notas"]].fillna(0)
    ativos.loc[ativos["chave"] == "", ["valor", "notas"]] = 0
    # O faturamento de um CNPJ é DIVIDIDO entre as lojas que o compartilham naquele mês e, dentro da loja,
    # entre os promotores dela. Assim a soma por promotor (ou por loja, UF, supervisor) dá o total, sem contar
    # o mesmo CNPJ várias vezes.
    if not ativos.empty:
        lojas_no_mes = ativos.groupby(["chave", "mes"])["loja"].transform("nunique")
        promotores_na_loja = ativos.groupby(["chave", "loja", "mes"])["linha"].transform("size")
        ativos["valor"] = ativos["valor"] / lojas_no_mes / promotores_na_loja

    # --- Custo: por mês da competência, dividido entre as lojas do promotor naquele mês ------
    custo_mes, custo_atual = custos_por_mes(promotores, custos, meses)
    visitas = pd.to_numeric(ativos["visitas_semana"], errors="coerce")
    ativos["peso"] = 1.0
    if regras["rateio_custo"] == "visitas" and not ativos.empty:
        grupo = ativos.assign(v=visitas, tem=visitas.notna()).groupby(["codigo_promotor", "mes"])
        todas_com_visita = grupo["tem"].transform("all") & (grupo["v"].transform("sum") > 0)
        ativos.loc[todas_com_visita, "peso"] = visitas[todas_com_visita].astype(float)
    soma_pesos = ativos.groupby(["codigo_promotor", "mes"])["peso"].transform("sum")
    custo_do_mes = [custo_mes[c].get(m, 0.0) for c, m in zip(ativos["codigo_promotor"], ativos["mes"])]
    ativos["custo"] = pd.Series(custo_do_mes, index=ativos.index, dtype=float) * ativos["peso"] / soma_pesos

    # --- Filtros ---------------------------------------------------------------------------
    # Só entra quem estava contratado em algum mês do período (não admitido ainda / já desligado = fora).
    contratado = pd.Series([janela[c][0] <= janela[c][1] for c in promotores["codigo"]], index=promotores.index,
                           dtype=bool)
    proms = promotores[contratado]
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
    filtro_de_local = bool(filtros.uf or filtros.cidade or filtros.pdv)
    if filtro_de_local:
        # Filtrando por local, só interessam os promotores que atendem ali.
        proms = proms[proms["codigo"].isin(lojas["codigo_promotor"])]
    ativos = ativos[ativos["linha"].isin(lojas["linha"])]

    # --- Por linha do roteiro (loja × promotor) ------------------------------------------------
    por_linha = ativos.groupby("linha").agg(
        faturamento=("valor", "sum"), custo_periodo=("custo", "sum"), meses_ativos=("mes", "nunique"))
    lojas = lojas.join(por_linha, on="linha")
    lojas[["faturamento", "custo_periodo", "meses_ativos"]] = (
        lojas[["faturamento", "custo_periodo", "meses_ativos"]].fillna(0))
    lojas["lojas_mesma_chave"] = lojas["chave"].map(lojas_por_chave).fillna(1).astype(int)
    lojas.loc[lojas["chave"] == "", "lojas_mesma_chave"] = 1
    lojas["compartilhado"] = lojas["lojas_mesma_chave"] > 1
    lojas["visitas_num"] = pd.to_numeric(lojas["visitas_semana"], errors="coerce")

    nomes = dict(zip(proms["codigo"], proms["nome"]))
    supervisores = dict(zip(proms["codigo"], proms["supervisor"]))

    # Custo de cada promotor no período. Com filtro de UF, cidade ou PDV, só a parte atribuída às lojas
    # filtradas (o resto do custo é das lojas de outros lugares).
    atribuido = ativos.groupby("codigo_promotor")["custo"].sum()
    custo_do_promotor = {c: float(atribuido.get(c, 0.0)) if filtro_de_local else sum(custo_mes[c].values())
                         for c in proms["codigo"]}

    # --- Tabela por promotor -------------------------------------------------------------------
    fat_por_promotor = ativos.groupby("codigo_promotor")["valor"].sum()
    lojas_por_promotor = lojas.drop_duplicates(["codigo_promotor", "chave", "loja"]).groupby("codigo_promotor").size()
    visitas_por_promotor = lojas.dropna(subset=["visitas_num"]).groupby("codigo_promotor")["visitas_num"].sum()
    linhas_promotores = []
    for p in proms.itertuples():
        fat_p = float(fat_por_promotor.get(p.codigo, 0.0))
        custo_p = custo_do_promotor[p.codigo]
        visitas_p = visitas_por_promotor.get(p.codigo)
        linhas_promotores.append({
            "codigo": p.codigo, "nome": p.nome, "supervisor": p.supervisor, "municipio": p.municipio,
            "uf": (getattr(p, "uf", "") or "").upper() or "—",
            "custo_mensal": _arredondar(custo_atual[p.codigo]), "custo_periodo": _arredondar(custo_p),
            "lojas": int(lojas_por_promotor.get(p.codigo, 0)),
            "visitas_semana": _arredondar(visitas_p) if visitas_p is not None else None,
            "faturamento": _arredondar(fat_p),
            "percentual_custo": _percentual(custo_p, fat_p),
        })
    linhas_promotores.sort(key=lambda l: (l["percentual_custo"] is None, -(l["percentual_custo"] or 0)))

    # --- Tabela por loja -------------------------------------------------------------------------
    linhas_lojas = []
    for l in lojas.itertuples():
        visitas_l = l.visitas_num
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
    fat_total = float(ativos["valor"].sum())
    unicas = lojas.drop_duplicates(["chave", "loja"])
    visitas_total = lojas["visitas_num"].sum()
    sem_cnpj = int((unicas["cnpj"] == "").sum())
    if sem_cnpj:
        avisos.append(f"{sem_cnpj} loja(s) sem CNPJ no roteiro: aparecem sem faturamento.")
    if not lojas.empty and lojas["visitas_num"].isna().all():
        avisos.append("Nenhuma loja tem visitas por semana: o custo do promotor foi dividido em partes iguais "
                      "entre as lojas dele.")
    sem_supervisor = int((proms["supervisor"].fillna("") == "").sum())
    if sem_supervisor:
        avisos.append(f"{sem_supervisor} promotor(es) sem supervisor (aparecem em \"(sem supervisor)\").")
    resumo = {
        "meses": len(meses),
        "promotores": len(linhas_promotores),
        "lojas": int(len(unicas)),
        "visitas_semana": _arredondar(visitas_total) if visitas_total else None,
        "custo": _arredondar(custo_total),
        "faturamento": _arredondar(fat_total),
        "percentual_custo": _percentual(custo_total, fat_total),
        "cnpjs_compartilhados": int(unicas[unicas["compartilhado"]]["chave"].nunique()),
        "avisos": avisos,
    }
    regras_usadas = {c: regras[c] for c in ("rateio_custo", "limite_percentual", "margem_percentual")}
    for linha in [*linhas_promotores, *linhas_lojas, resumo]:
        _se_paga(linha, regras.get("margem_percentual"))
    return {"resumo": resumo, "promotores": linhas_promotores, "lojas": linhas_lojas, "regras": regras_usadas,
            "grade": _grade_mes_a_mes(lojas, ativos, meses, nomes, supervisores, separados),
            "custos": _bloco_custos(proms, custos, fim),
            "por_uf": _resumo_por_uf(proms, lojas, ativos, custo_do_promotor)}


def _resumo_por_uf(proms, lojas, ativos, custo_do_promotor) -> list:
    """Tabela do Resumo por UF da loja → supervisor → promotor (no lugar da aba RESUMO da planilha).

    O custo do promotor vai para a UF de cada loja, na mesma divisão usada nas lojas. Promotor que atende
    duas UFs aparece nas duas, cada uma com a sua parte. A parte do custo que não foi para nenhuma loja
    (mês sem loja no roteiro) fica na UF do cadastro do promotor.
    """
    uf_da_linha = lojas.set_index("linha")["uf"].fillna("").str.upper().replace("", "—")
    ativos = ativos.assign(uf=ativos["linha"].map(uf_da_linha).fillna("—"))
    nomes = dict(zip(proms["codigo"], proms["nome"]))
    supervisores = {c: s or "(sem supervisor)" for c, s in zip(proms["codigo"], proms["supervisor"].fillna(""))}
    uf_cadastro = {c: (u or "").upper() or "—" for c, u in zip(proms["codigo"], _coluna(proms, "uf"))}

    # Custo de cada (UF, promotor): o atribuído às lojas daquela UF + o que sobrou, na UF do cadastro.
    custo = ativos.groupby(["uf", "codigo_promotor"])["custo"].sum().to_dict()
    atribuido = ativos.groupby("codigo_promotor")["custo"].sum().to_dict()
    for codigo in proms["codigo"]:
        resto = custo_do_promotor[codigo] - atribuido.get(codigo, 0.0)
        if resto > 0.005 or codigo not in atribuido:
            chave = (uf_cadastro[codigo], codigo)
            custo[chave] = custo.get(chave, 0.0) + max(resto, 0.0)
    faturamento = ativos.groupby(["uf", "codigo_promotor"])["valor"].sum().to_dict()

    # Lojas (CNPJ + nome) e visitas de cada (UF, promotor).
    loja_da_linha = dict(zip(lojas["linha"], zip(lojas["chave"], lojas["loja"])))
    visitas_da_linha = dict(zip(lojas["linha"], lojas["visitas_num"]))
    lojas_do_par, visitas_do_par = {}, {}
    for uf, codigo, linha_ in ativos[["uf", "codigo_promotor", "linha"]].drop_duplicates().itertuples(index=False):
        lojas_do_par.setdefault((uf, codigo), set()).add(loja_da_linha[linha_])
        if not pd.isna(visitas_da_linha[linha_]):
            visitas_do_par.setdefault((uf, codigo), []).append(float(visitas_da_linha[linha_]))

    def linha(nivel, uf, nome, pares, codigo=""):
        lojas_g = set().union(*(lojas_do_par.get(p, set()) for p in pares))
        visitas = [v for p in pares for v in visitas_do_par.get(p, [])]
        custo_g = sum(custo[p] for p in pares)
        fat = sum(faturamento.get(p, 0.0) for p in pares)
        return {"nivel": nivel, "uf": uf, "nome": nome, "codigo": codigo,
                "supervisor": nome if nivel == "supervisor" else "",
                "promotores": len({c for _, c in pares}), "lojas": len(lojas_g),
                "visitas_semana": _arredondar(sum(visitas)) if visitas else None,
                "custo_periodo": _arredondar(custo_g), "faturamento": _arredondar(fat),
                "percentual_custo": _percentual(custo_g, fat)}

    linhas = []
    for uf in sorted({u for u, _ in custo}, key=lambda u: (u == "—", u)):
        da_uf = [p for p in custo if p[0] == uf]
        linhas.append(linha("uf", uf, uf, da_uf))
        for sup in sorted({supervisores[c] for _, c in da_uf}, key=lambda s: (s == "(sem supervisor)", s)):
            da_equipe = [p for p in da_uf if supervisores[p[1]] == sup]
            linhas.append(linha("supervisor", uf, sup, da_equipe))
            for par in sorted(da_equipe, key=lambda p: nomes[p[1]]):
                linhas.append(linha("promotor", uf, nomes[par[1]], [par], codigo=par[1]))
    return linhas


def _inteiro_ou_nada(valor):
    return None if valor is None or pd.isna(valor) else int(valor)


def _rotulo_mes(indice: int) -> str:
    return f"{indice // 12}-{indice % 12 + 1:02d}"


def _grade_mes_a_mes(lojas, ativos, meses, nomes, supervisores, separados) -> dict:
    """Faturamento de cada loja × promotor mês a mês, como as abas SC, SP, PR… da planilha.

    Loja que divide o CNPJ com outras (ou que tem mais de um promotor) mostra a sua parte; a linha de
    totais é a soma das linhas (cada CNPJ conta uma vez).
    """
    rotulos = [_rotulo_mes(m) for m in meses]
    valores = ativos.groupby(["linha", "mes"])["valor"].sum().to_dict()
    linhas = []
    for l in lojas.itertuples():
        por_mes = {rotulo: round(float(valores.get((l.linha, m), 0.0)), 2) for m, rotulo in zip(meses, rotulos)}
        linhas.append({
            "linha": int(l.linha), "roteiro_id": _inteiro_ou_nada(getattr(l, "roteiro_id", None)),
            "supervisor": supervisores.get(l.codigo_promotor, ""),
            "promotor": nomes.get(l.codigo_promotor, ""), "cnpj": l.cnpj, "loja": l.loja, "cidade": l.cidade,
            "uf": l.uf, "meses": por_mes, "total": round(sum(por_mes.values()), 2),
            "compartilhado": bool(l.compartilhado),
            # Para abrir as notas do valor: CNPJ e, se separado, o COD CLI.
            "detalhe": {"cnpj": l.cnpj, "cod_cli": (getattr(l, "cod_cli", "") or "") if l.cnpj in separados else ""},
        })
    por_mes_total = ativos.groupby("mes")["valor"].sum()
    totais = {rotulo: round(float(por_mes_total.get(m, 0.0)), 2) for m, rotulo in zip(meses, rotulos)}
    return {"meses": rotulos, "linhas": linhas, "totais": {**totais, "total": round(sum(totais.values()), 2)}}


def _bloco_custos(proms: pd.DataFrame, custos: pd.DataFrame | None, fim: int) -> list:
    """Custo de cada promotor vigente no último mês do período, como a aba PROMOTORES BRASIL."""
    campos = ("salario", "ajuda_custo", "vale_transporte", "outros")
    ultimos = {}
    if custos is not None and not custos.empty:
        indices = custos["ano"].astype(int) * 12 + custos["mes"].astype(int) - 1
        vigentes = custos[indices <= fim].assign(indice=indices[indices <= fim]).sort_values("indice")
        ultimos = {linha["codigo"]: linha for linha in vigentes.drop_duplicates("codigo", keep="last")
                   .to_dict("records")}
    linhas = []
    for p in proms.sort_values("nome").itertuples():
        if custos is None:
            valores = {"salario": float(p.salario or 0), "ajuda_custo": float(p.ajuda_custo or 0),
                       "vale_transporte": float(p.transporte or 0), "outros": 0.0}
        else:
            ultima = ultimos.get(p.codigo, {})
            valores = {c: float(ultima.get(c, 0) or 0) for c in campos}
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
    # Montado a partir de listas e dicionários: iterrows/.at do pandas nas ~6 mil linhas levavam ~1 s.
    info = dados[["razao_social", "cidade", "uf"]].to_dict("index")
    notas = notas.to_dict()
    por_cliente = tabela("cnpj")
    colunas = list(por_cliente.columns)
    clientes = [{"cnpj": cnpj, "razao_social": info[cnpj]["razao_social"], "cidade": info[cnpj]["cidade"],
                 "uf": info[cnpj]["uf"], "meses": {m: round(float(v), 2) for m, v in zip(colunas, linha)},
                 "total": round(float(linha.sum()), 2), "notas": int(notas[cnpj]), "no_roteiro": cnpj in cnpjs_no_roteiro}
                for cnpj, linha in zip(por_cliente.index, por_cliente.to_numpy())]
    clientes.sort(key=lambda c: -c["total"])
    return {"meses": meses, "por_uf": por_uf, "totais": {**totais, "total": total}, "clientes": clientes}
