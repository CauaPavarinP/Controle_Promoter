"""Converte a "Sistemática de atendimento" (planilha da filial, ex.: PR) no modelo de atendimento do sistema.

Para a filial passar a usar o modelo padrão: gera o primeiro arquivo já preenchido com o que a Sistemática tem, e
marca em laranja o que falta preencher (CNPJ da loja e valor do mês dos CLT).

O que lê:
  - aba do roteiro (a que tem LOJA, CIDADE, UF, FREQ., dias Seg…Sáb, RCA, SUPERVISOR, DIRETO OU MEI, PROMOTOR);
  - aba dos MEIs (NOME, CNPJ, VALOR MÊS…): o valor do mês de cada MEI é dividido entre as lojas dele, pelas visitas.

O que gera (uma linha por loja, no mês informado):
  - Tipo: CLT / MEI / Freelancer (coluna "DIRETO OU MEI");
  - Agência: CLT = --agencia-clt (padrão "101 do Brasil"); MEI = "MEI - <nome>"; Freelancer = "Freelancer - <nome>";
  - CNPJ: o que estiver escrito junto do nome da loja (o nome fica sem ele); senão, em branco (laranja);
  - Dias de visita (Seg, Qua…) e visitas no mês (quantas vezes esses dias caem no mês);
  - Valor do mês: MEI = valor do MEI dividido pelas lojas dele, pelas visitas; CLT e Freelancer em branco (laranja),
    a não ser que venha o arquivo de custo dos CLT (--custo-clt, ver abaixo);
  - Supervisor; Observação com o RCA e o endereço (para achar o CNPJ).

Custo dos CLT (opcional): --custo-clt arquivo.xlsx com as colunas "Promotor" (como está na Sistemática, ou só o
nome) e "Custo" (valor do mês: salário + ajuda + vale). O custo é dividido entre as lojas do promotor, pelas visitas.

Uso (na pasta backend; os arquivos ficam no seu computador):
    python scripts/converter_sistematica.py "SISTEMATICA_DE_ATENDIMENTO_PR_OUT_2026.xlsx" --mes 2026-10
    (opções: --saida arquivo.xlsx | --agencia-clt "101 do Brasil" | --custo-clt custos.xlsx)

O arquivo gerado tem dados reais: não coloque no repositório.
"""
import argparse
import calendar
import difflib
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import load_workbook  # noqa: E402
from openpyxl.styles import PatternFill  # noqa: E402

from app.cnpj import cnpj_valido, formatar  # noqa: E402
from app.importacao import normalizar_texto  # noqa: E402

MODELO = Path(__file__).resolve().parent.parent / "exemplos" / "modelo_atendimento_agencias.xlsx"
LARANJA = PatternFill("solid", fgColor="FFC98B")   # célula que a filial precisa preencher
DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
NOMES_DIAS = {"SEG": "Seg", "TER": "Ter", "QUA": "Qua", "QUI": "Qui", "SEX": "Sex", "SAB": "Sáb", "DOM": "Dom"}
ERROS = {"", "N A", "NA", "REF", "VALUE", "0"}
CNPJ_NO_TEXTO = re.compile(r"\d{2}\.?\d{3}\.?\d{3}\s*/?\s*\d{4}\s*-?\s*\d{2}")


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = re.sub(r"\s+", " ", str(valor)).strip()
    return "" if normalizar_texto(texto) in ERROS else texto


def _numero(valor) -> float:
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    texto = _texto(valor).replace("R$", "").strip()
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?|-?\d+,\d+", texto):
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _marcado(valor) -> bool:
    """Dia de atendimento marcado na grade (1, X, SIM…)."""
    texto = normalizar_texto(valor)
    return bool(texto) and texto not in {"0", "N", "NAO"}


def separar_cnpj(nome: str) -> tuple[str, str]:
    """("10 ATACADISTA 11.222.333/0001-81", …) -> ("10 ATACADISTA", "11.222.333/0001-81"); CNPJ inválido -> ""."""
    achado = CNPJ_NO_TEXTO.search(nome)
    if not achado:
        return nome.strip(), ""
    digitos = re.sub(r"\D", "", achado.group(0))
    limpo = (nome[:achado.start()] + " " + nome[achado.end():])
    limpo = re.sub(r"\s*[-–|/:]*\s*(CNPJ)?\s*[-–|/:]*\s*$", "", re.sub(r"\s+", " ", limpo)).strip(" -–|/:")
    return (limpo or nome.strip()), (formatar(digitos) if cnpj_valido(digitos) else "")


def visitas_no_mes(dias: list[str], ano: int, mes: int) -> int:
    """Quantas vezes os dias da semana marcados caem no mês (ex.: Ter e Qui em out/2026 = 9)."""
    total = 0
    for dia in range(1, calendar.monthrange(ano, mes)[1] + 1):
        if DIAS[calendar.weekday(ano, mes, dia)] in dias:
            total += 1
    return total


def _achar_cabecalho(linhas, obrigatorios: set[str], limite=15):
    for indice, linha in enumerate(linhas[:limite]):
        nomes = [normalizar_texto(c) for c in linha]
        if obrigatorios <= set(nomes):
            return indice, nomes
    return None, None


def ler_roteiro(livro) -> tuple[list[dict], str]:
    for aba in livro.worksheets:
        linhas = []
        for linha in aba.iter_rows(values_only=True):
            linhas.append(tuple(linha))
            if len(linhas) >= 15:
                break
        indice, nomes = _achar_cabecalho(linhas, {"LOJA", "CIDADE"})
        if indice is None or not any(n.startswith("PROMOTOR") for n in nomes):
            continue
        pos = lambda *alvos: next((i for i, n in enumerate(nomes) if any(n.startswith(a) for a in alvos)), None)  # noqa: E731
        col = {"loja": pos("LOJA"), "endereco": pos("ENDERECO"), "bairro": pos("BAIRRO"), "cidade": pos("CIDADE"),
               "cep": pos("CEP"), "uf": pos("UF"), "freq": pos("FREQ"), "rca": pos("RCA"),
               "supervisor": pos("SUPERVISOR"), "tipo": pos("DIRETO OU MEI", "TIPO"), "promotor": pos("PROMOTOR")}
        # Os dias (Seg…Sáb) ficam na linha logo abaixo do cabeçalho, embaixo de "Dias de Atendimento".
        dias_col = {}
        for linha in linhas[indice:indice + 3]:
            for posicao, celula in enumerate(linha):
                chave = normalizar_texto(celula)[:3]
                if chave in DIAS:
                    dias_col[chave] = posicao
        lojas, vazias = [], 0
        for numero, linha in enumerate(aba.iter_rows(min_row=indice + 2, values_only=True), start=indice + 2):
            valor = lambda campo: linha[col[campo]] if col.get(campo) is not None and col[campo] < len(linha) else None  # noqa: E731,B023
            loja = _texto(valor("loja"))
            if not loja or normalizar_texto(loja) in {"LOJA"} or normalizar_texto(loja)[:3] in DIAS:
                vazias += 1
                if vazias > 200:   # a aba vai formatada até a linha 1.048.576: para depois de 200 vazias seguidas
                    break
                continue
            vazias = 0
            nome, cnpj = separar_cnpj(loja)
            dias = [d for d, p in dias_col.items() if p < len(linha) and _marcado(linha[p])]
            lojas.append({
                "linha": numero, "loja_original": loja, "loja": nome, "cnpj": cnpj,
                "endereco": ", ".join(t for t in (_texto(valor("endereco")), _texto(valor("bairro")),
                                                  _texto(valor("cep"))) if t),
                "cidade": _texto(valor("cidade")).upper(), "uf": normalizar_texto(valor("uf"))[:2],
                "freq": _texto(valor("freq")), "dias": [d for d in DIAS if d in dias],
                "rca": _texto(valor("rca")), "supervisor": _texto(valor("supervisor")),
                "tipo_bruto": normalizar_texto(valor("tipo")), "promotor": _texto(valor("promotor")),
            })
        return lojas, aba.title
    raise SystemExit("Não achei a aba do roteiro (cabeçalho com LOJA, CIDADE e PROMOTOR).")


def ler_meis(livro) -> list[dict]:
    for aba in livro.worksheets:
        linhas = [tuple(l) for l in aba.iter_rows(values_only=True)]
        indice, nomes = _achar_cabecalho(linhas, {"NOME"})
        if indice is None or not any("VALOR" in n for n in nomes):
            continue
        p_nome = nomes.index("NOME")
        p_valor = next(i for i, n in enumerate(nomes) if n.startswith("VALOR"))
        p_cidade = next((i for i, n in enumerate(nomes) if n.startswith("CIDADE")), None)
        meis = []
        for linha in linhas[indice + 1:]:
            nome = _texto(linha[p_nome]) if p_nome < len(linha) else ""
            if not nome or normalizar_texto(nome).startswith("TOTAL"):
                continue
            meis.append({"nome": nome, "valor": round(_numero(linha[p_valor]), 2),
                         "cidade": _texto(linha[p_cidade]) if p_cidade is not None else ""})
        return meis
    return []


def ler_custo_clt(caminho: Path) -> dict[str, float]:
    livro = load_workbook(caminho, read_only=True, data_only=True)
    for aba in livro.worksheets:
        linhas = [tuple(l) for l in aba.iter_rows(values_only=True)]
        indice, nomes = _achar_cabecalho(linhas, {"PROMOTOR"}) if linhas else (None, None)
        if indice is None:
            indice, nomes = _achar_cabecalho(linhas, {"COLABORADOR"})
        if indice is None:
            continue
        p_nome = next(i for i, n in enumerate(nomes) if n in ("PROMOTOR", "COLABORADOR"))
        p_custo = next((i for i, n in enumerate(nomes) if n in ("CUSTO", "TOTAL", "VALOR", "VALOR MES", "CUSTO MES")),
                       None)
        if p_custo is None:
            raise SystemExit(f"{caminho.name}: falta a coluna Custo (ou TOTAL) com o valor do mês de cada CLT.")
        return {normalizar_texto(l[p_nome]): round(_numero(l[p_custo]), 2) for l in linhas[indice + 1:]
                if p_nome < len(l) and _texto(l[p_nome])}
    raise SystemExit(f"{caminho.name}: não achei as colunas Promotor e Custo.")


def _primeiro_nome(texto: str) -> str:
    return normalizar_texto(texto.split(" - ")[0]).split(" ")[0] if texto else ""


def _regiao_bate(regiao: str, cidade: str) -> bool:
    """"TEL BORBA" está em "TEL BORBA/TIBAGI/IMBAU"; "FB" são as iniciais de "FRANCISCO BELTRAO"."""
    regiao, cidade = normalizar_texto(regiao), normalizar_texto(cidade)
    if not regiao or not cidade:
        return False
    palavras = [p for p in regiao.split() if p not in {"MEI", "FREE", "FREELANCE", "FREELANCER", "Q", "DO", "DA", "DE"}]
    if not palavras:
        return False
    iniciais = "".join(p[0] for p in cidade.split() if p not in {"DO", "DA", "DE", "DOS", "DAS"})
    return " ".join(palavras) in cidade or any(len(p) >= 2 and p == iniciais for p in palavras) or \
        all(p in cidade.split() for p in palavras)


def achar_mei(promotor: str, meis_por_nome: dict) -> tuple[dict | None, str]:
    """(MEI da aba de valores, "" | "ambiguo" | "nao_achou"). Pelo primeiro nome (aceita erro de uma letra), e,
    quando há dois com o mesmo nome, pela região escrita depois do nome ("LUCIANE MEI - FB")."""
    nome = _primeiro_nome(promotor)
    candidatos = meis_por_nome.get(nome, [])
    if not candidatos:
        perto = difflib.get_close_matches(nome, list(meis_por_nome), n=1, cutoff=0.8)
        candidatos = meis_por_nome[perto[0]] if perto else []
    if len(candidatos) > 1:
        partes = re.split(r"\s+-\s*|\s*-\s+", promotor, maxsplit=1)
        resto = partes[1] if len(partes) > 1 else " ".join(normalizar_texto(promotor).split()[1:])
        candidatos = [m for m in candidatos if _regiao_bate(resto, m["cidade"])] or candidatos
    if len(candidatos) == 1:
        return candidatos[0], ""
    return None, "ambiguo" if candidatos else "nao_achou"


def _dividir(total: float, pesos: list[int]) -> list[float]:
    """Divide o total pelos pesos (visitas), em centavos; a sobra vai para a última loja. Sem visitas: igual."""
    centavos = int(round(total * 100))
    if not pesos:
        return []
    if sum(pesos) <= 0:
        pesos = [1] * len(pesos)
    partes = [centavos * p // sum(pesos) for p in pesos]
    partes[-1] += centavos - sum(partes)
    return [p / 100 for p in partes]


def converter(sistematica: Path, mes: str, saida: Path, agencia_clt="101 do Brasil", custo_clt: Path | None = None):
    ano, numero_mes = (int(x) for x in mes.split("-"))
    livro = load_workbook(sistematica, read_only=True, data_only=True)
    try:
        lojas, aba_roteiro = ler_roteiro(livro)
        meis = ler_meis(livro)
    finally:
        livro.close()
    custos = ler_custo_clt(custo_clt) if custo_clt else {}
    avisos = []

    tipos = {"CLT": "CLT", "DIRETO": "CLT", "MEI": "MEI", "FREE": "Freelancer", "FREELANCER": "Freelancer"}
    agencia_no_promotor, sem_nome = set(), set()
    for loja in lojas:
        loja["tipo"] = tipos.get(loja["tipo_bruto"], "CLT" if not loja["tipo_bruto"] else "Agência")
        loja["agencia"] = None
        chave = normalizar_texto(loja["promotor"])
        if chave.startswith("AGENCIA "):   # ex.: "AGENCIA IMPACTO" escrito na coluna do promotor
            agencia_no_promotor.add(loja["promotor"])
            loja.update(tipo="Agência", agencia=loja["promotor"].title(), promotor="")
        elif chave in {"PROMOTOR MEI", "PROMOTOR", "PROMOTOR CLT", "SEM PROMOTOR", "RECRUTANDO"}:
            sem_nome.add(loja["promotor"])
            loja["promotor"] = ""
        loja["visitas"] = visitas_no_mes(loja["dias"], ano, numero_mes)
    if agencia_no_promotor:
        avisos.append(("Agência escrita na coluna do promotor: entrou como agência, sem promotor (valor em branco)",
                       sorted(agencia_no_promotor)))
    if sem_nome:
        avisos.append(("Promotor sem nome (vaga?): entrou como \"Sem promotor informado\"", sorted(sem_nome)))
    fora = sorted({l["tipo_bruto"] for l in lojas if l["tipo"] == "Agência" and not l["agencia"]})
    if fora:
        avisos.append(("Tipo desconhecido em \"DIRETO OU MEI\" (entrou como Agência)", fora))

    # Valor do mês por promotor: MEI pela aba dos MEIs (pelo primeiro nome), CLT pelo arquivo de custo (se vier).
    por_promotor = defaultdict(list)
    for loja in lojas:
        por_promotor[(loja["tipo"], loja["promotor"])].append(loja)
    meis_por_nome = defaultdict(list)
    for m in meis:
        meis_por_nome[_primeiro_nome(m["nome"])].append(m)
    sem_valor_mei, mei_ambiguo, meis_usados = [], [], set()
    for (tipo, promotor), itens in por_promotor.items():
        total = None
        if tipo in ("MEI", "Freelancer"):   # MEI e freelancer recebem pela aba dos MEIs (a marcação às vezes troca)
            mei, problema = achar_mei(promotor, meis_por_nome)
            if mei is not None and id(mei) in meis_usados:
                problema, mei = "ambiguo", None   # dois promotores do roteiro no mesmo MEI: não divide duas vezes
            if mei is not None:
                total = mei["valor"]
                meis_usados.add(id(mei))
            elif problema == "ambiguo":
                mei_ambiguo.append(promotor)
            else:
                sem_valor_mei.append(promotor or "(promotor sem nome)")
        elif tipo == "CLT" and custos:
            chave = normalizar_texto(promotor)
            if chave not in custos:
                perto = difflib.get_close_matches(chave, list(custos), n=1, cutoff=0.85) or \
                    [c for c in custos if c == _primeiro_nome(promotor)]
                chave = perto[0] if perto else None
            total = custos.get(chave) if chave else None
        valores = _dividir(total, [i["visitas"] for i in itens]) if total is not None else [None] * len(itens)
        for item, valor in zip(itens, valores):
            item["valor"] = valor
    if sem_valor_mei:
        avisos.append(("MEI do roteiro sem valor na aba dos MEIs (valor em branco)", sorted(sem_valor_mei)))
    if mei_ambiguo:
        avisos.append(("MEI com nome repetido na aba dos MEIs (valor em branco, confira)", sorted(mei_ambiguo)))
    nao_usados = [m["nome"] for m in meis if id(m) not in meis_usados]
    if nao_usados:
        avisos.append(("Na aba dos MEIs, mas sem loja no roteiro", nao_usados))

    def nome_agencia(l):
        if l["agencia"]:
            return l["agencia"]
        if l["tipo"] == "CLT":
            return agencia_clt
        nome = re.sub(r"\b(MEI|FREE|FREELANCE|FREELANCER)\b", "", l["promotor"].split(" - ")[0], flags=re.I)
        return f"{l['tipo']} - {nome.strip(' -').title() or 'Sem nome'}"
    lojas.sort(key=lambda l: (l["tipo"] != "CLT", nome_agencia(l), l["promotor"], l["cidade"], l["loja"]))

    modelo = load_workbook(MODELO)
    aba = modelo["Atendimentos"]
    pos = {aba.cell(1, c).value: c for c in range(1, aba.max_column + 1) if aba.cell(1, c).value}
    for coluna in range(1, pos["Conferência do CNPJ"]):
        aba.cell(2, coluna).value = None
    for numero, l in enumerate(lojas, start=2):
        observacao = " · ".join(t for t in (f"RCA: {l['rca']}" if l["rca"] else "",
                                            f"End.: {l['endereco']}" if l["endereco"] else "") if t)
        valores = {
            "Mês de referência": f"{numero_mes:02d}/{ano}", "Agência ou MEI": nome_agencia(l), "Tipo": l["tipo"],
            "CNPJ da loja": l["cnpj"] or None, "Loja": l["loja"], "Cidade": l["cidade"], "UF": l["uf"] or None,
            "Promotor": l["promotor"], "Dias de visita": ", ".join(NOMES_DIAS[d] for d in l["dias"]) or None,
            "Visitas no mês": l["visitas"] or None, "Valor do mês (R$)": l["valor"], "Status": "Ativa",
            "Observação": observacao or None, "Supervisor": l["supervisor"] or None,
        }
        for titulo, valor in valores.items():
            aba.cell(numero, pos[titulo], valor)
        if not l["cnpj"]:
            aba.cell(numero, pos["CNPJ da loja"]).fill = LARANJA
        if l["valor"] is None:
            aba.cell(numero, pos["Valor do mês (R$)"]).fill = LARANJA

    sem_cnpj = sum(1 for l in lojas if not l["cnpj"])
    sem_valor = sum(1 for l in lojas if l["valor"] is None)
    resumo = {
        "Arquivo lido": f"{sistematica.name} (aba {aba_roteiro})", "Mês": f"{numero_mes:02d}/{ano}",
        "Lojas": len(lojas), "CLT / MEI / Freelancer (lojas)": " / ".join(
            str(sum(1 for l in lojas if l["tipo"] == t)) for t in ("CLT", "MEI", "Freelancer")),
        "Promotores": len(por_promotor),
        "CNPJ já preenchido (estava junto do nome)": len(lojas) - sem_cnpj,
        "CNPJ a preencher (laranja)": sem_cnpj,
        "Valor do mês a preencher (laranja)": sem_valor,
        "Valor já calculado (R$)": round(sum(l["valor"] or 0 for l in lojas), 2),
        "Valor dos MEIs na Sistemática (R$)": round(sum(m["valor"] for m in meis), 2),
    }
    conferencia = modelo.create_sheet("Conferência")
    conferencia["A1"] = "Conferência da conversão (esta aba não é importada)"
    conferencia["A2"] = ("Preencha as células em LARANJA na aba Atendimentos: CNPJ da loja (14 dígitos) e Valor do mês "
                         "(CLT: custo do promotor dividido pelas lojas dele). Depois importe em Importações › Arquivos "
                         "das agências.")
    linha = 4
    for rotulo, valor in resumo.items():
        conferencia.cell(linha, 1, rotulo)
        conferencia.cell(linha, 2, valor)
        linha += 1
    for titulo, itens in avisos:
        linha += 1
        conferencia.cell(linha, 1, f"⚠ {titulo} ({len(itens)})")
        for item in itens:
            linha += 1
            conferencia.cell(linha, 2, item)
    conferencia.column_dimensions["A"].width = 55
    conferencia.column_dimensions["B"].width = 60
    modelo.save(saida)
    return {"resumo": resumo, "avisos": avisos, "lojas": lojas, "saida": saida}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sistematica", type=Path)
    parser.add_argument("--mes", required=True, help="mês de referência, AAAA-MM (ex.: 2026-10)")
    parser.add_argument("--saida", type=Path)
    parser.add_argument("--agencia-clt", default="101 do Brasil")
    parser.add_argument("--custo-clt", type=Path, help="Excel com Promotor e Custo (valor do mês) dos CLT")
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.mes):
        parser.error("mês inválido (use AAAA-MM)")
    saida = args.saida or args.sistematica.with_name(f"Atendimento_{args.mes}_da_sistematica.xlsx")
    resultado = converter(args.sistematica, args.mes, saida, args.agencia_clt, args.custo_clt)
    for rotulo, valor in resultado["resumo"].items():
        print(f"  {rotulo}: {valor}")
    for titulo, itens in resultado["avisos"]:
        print(f"\n⚠ {titulo} ({len(itens)})")
        for item in itens[:10]:
            print(f"    - {item}")
    print(f"\nArquivo gerado: {saida}")


if __name__ == "__main__":
    main()
