"""Converte a planilha "ROTEIROS X FATURAMENTOS" do Maurício no arquivo de atendimento do sistema (promotores CLT da 101).

O que lê (só estas abas; a aba FATURAMENTO não é aberta):
  - PROMOTORES BRASIL: custo de cada promotor (TOTAL = salário + ajuda de custo + vale-transporte), código, admissão;
  - SC, SP, PR, MG, RS: roteiro (qual promotor atende qual loja: CNPJ, razão social, cidade, UF, supervisor).

O que gera: um Excel no modelo "Atendimento das agências", pronto para importar na aba Agências, com uma linha por
loja × mês: Agência = "101 do Brasil", Tipo = CLT, Código = código do promotor, Supervisor na coluna Supervisor.

Valor de cada loja no mês = custo mensal do promotor dividido igualmente entre as lojas do roteiro dele
(ex.: R$ 3.000 e 10 lojas = R$ 300 por loja). Os centavos que sobram da divisão vão para a última loja, para a soma
bater com o custo. Promotor admitido depois do mês não entra naquele mês.

Uso (na pasta backend; o arquivo fica no seu computador, nada é enviado):
    python scripts/converter_planilha_mauricio.py "C:\\caminho\\ROTEIROS X FATURAMENTOS.xlsm" --de 2026-01 --ate 2026-09

Opções: --saida arquivo.xlsx (padrão: ao lado da planilha) | --abas SC,SP,PR,MG,RS | --agencia "101 do Brasil"

A aba "Conferência" do arquivo gerado (e o resumo na tela) lista o que precisa de atenção: promotor do roteiro sem
cadastro de custo, cadastro sem nenhuma loja, nomes ligados por semelhança, CNPJ inválido, supervisor "#N/A".
"""
import argparse
import difflib
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openpyxl import load_workbook  # noqa: E402

from app.cnpj import cnpj_valido, formatar  # noqa: E402
from app.importacao import normalizar_texto  # noqa: E402

MODELO = Path(__file__).resolve().parent.parent / "exemplos" / "modelo_atendimento_agencias.xlsx"
ABAS_ROTEIRO = ["SC", "SP", "PR", "MG", "RS"]
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
VAZIOS = {"", "N A", "NA", "0", "NONE", "NULL", "REF"}   # "#N/A", "#REF!" e afins viram vazio

APELIDOS_PROMOTORES = {
    "colaborador": ["COLABORADOR", "PROMOTOR", "NOME"],
    "codigo": ["CODIGO", "COD", "MATRICULA"],
    "admissao": ["ADMISSAO", "DATA DE ADMISSAO"],
    "salario": ["SALARIO"],
    "ajuda": ["AJUD CUSTO", "AJUDA DE CUSTO", "AJUDA CUSTO"],
    "vt": ["V TRANSP", "VALE TRANSPORTE", "VT"],
    "total": ["TOTAL"],
    "uf": ["UF", "ESTADO"],
    "supervisor": ["SUPERVISOR"],
}
APELIDOS_ROTEIRO = {
    "supervisor": ["SUPERVISOR"],
    "colaborador": ["COLABORADOR", "PROMOTOR"],
    "cnpj": ["CPFCNPJ", "CPF CNPJ", "CNPJ", "CNPJ CPF"],
    "loja": ["RAZAO SOCIAL", "LOJA", "PDV", "CLIENTE"],
    "cidade": ["CIDADE", "COLUNA1", "MUNICIPIO"],
    "uf": ["UF", "ESTADO"],
}


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = re.sub(r"\s+", " ", str(valor)).strip()
    return "" if normalizar_texto(texto) in VAZIOS else texto


def _numero(valor) -> float:
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    texto = _texto(valor).replace("R$", "").strip()
    if not texto:
        return 0.0
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})*(,\d+)?|-?\d+(,\d+)?", texto):
        return float(texto.replace(".", "").replace(",", "."))
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    achado = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", _texto(valor))
    return date(int(achado.group(3)), int(achado.group(2)), int(achado.group(1))) if achado else None


def _cabecalho(linhas: list, apelidos: dict) -> tuple[int, dict] | None:
    """(índice da linha do cabeçalho, campo -> coluna) entre as primeiras linhas: a que tem "Colaborador"."""
    for indice, linha in enumerate(linhas):
        nomes = {}
        for posicao, celula in enumerate(linha):
            nomes.setdefault(normalizar_texto(celula), posicao)
        if "COLABORADOR" not in nomes:
            continue
        mapa = {}
        for campo, opcoes in apelidos.items():
            for opcao in opcoes:
                if opcao in nomes:
                    mapa[campo] = nomes[opcao]
                    break
        return indice, mapa
    return None


def _ler_aba(aba, apelidos: dict):
    linhas = [tuple(l) for l in aba.iter_rows(values_only=True)]
    achado = _cabecalho(linhas[:20], apelidos)
    if achado is None:
        return None, []
    indice, mapa = achado
    registros = []
    for numero, linha in enumerate(linhas[indice + 1:], start=indice + 2):
        registro = {campo: (linha[pos] if pos < len(linha) else None) for campo, pos in mapa.items()}
        if any(_texto(v) for v in registro.values()):
            registros.append((numero, registro))
    return mapa, registros


# ---------------------------------------------------------------------------------------------------------------

def ler_promotores(livro, avisos: list) -> list[dict]:
    if "PROMOTORES BRASIL" not in livro.sheetnames:
        raise SystemExit('A planilha não tem a aba "PROMOTORES BRASIL".')
    mapa, registros = _ler_aba(livro["PROMOTORES BRASIL"], APELIDOS_PROMOTORES)
    if mapa is None or "colaborador" not in mapa:
        raise SystemExit('Não achei o cabeçalho (coluna "Colaborador") na aba PROMOTORES BRASIL.')
    promotores = []
    for numero, r in registros:
        nome = _texto(r.get("colaborador"))
        if not nome:
            continue
        total = r.get("total")
        custo = _numero(total) if isinstance(total, (int, float)) and not isinstance(total, bool) else \
            _numero(r.get("salario")) + _numero(r.get("ajuda")) + _numero(r.get("vt"))
        if not custo and not isinstance(total, (int, float)):
            # TOTAL é fórmula: sem o valor guardado (arquivo nunca aberto no Excel), soma as partes.
            custo = _numero(r.get("salario")) + _numero(r.get("ajuda")) + _numero(r.get("vt"))
        uf = normalizar_texto(r.get("uf"))[:2]
        promotores.append({"nome": nome, "chave": normalizar_texto(nome), "codigo": _texto(r.get("codigo")),
                           "custo": round(custo, 2), "admissao": _data(r.get("admissao")),
                           "uf": uf if uf in UFS else "", "supervisor": _texto(r.get("supervisor")),
                           "linha": numero})
    sem_custo = [p["nome"] for p in promotores if p["custo"] <= 0]
    if sem_custo:
        avisos.append(("Cadastro sem custo (TOTAL vazio ou zero): entram com R$ 0", sem_custo))
    return promotores


def ler_roteiros(livro, abas: list[str], avisos: list) -> list[dict]:
    lojas = []
    for nome_aba in abas:
        if nome_aba not in livro.sheetnames:
            avisos.append((f'Aba "{nome_aba}" não existe na planilha', []))
            continue
        mapa, registros = _ler_aba(livro[nome_aba], APELIDOS_ROTEIRO)
        if mapa is None or not {"colaborador", "loja"} <= set(mapa):
            avisos.append((f'Aba "{nome_aba}": não achei o cabeçalho (Colaborador, Razão Social)', []))
            continue
        supervisor_na = 0
        for numero, r in registros:
            colaborador, loja = _texto(r.get("colaborador")), _texto(r.get("loja"))
            if not colaborador or not loja:
                continue
            bruto_supervisor = r.get("supervisor")
            if bruto_supervisor is not None and not _texto(bruto_supervisor):
                supervisor_na += 1
            uf = normalizar_texto(r.get("uf"))[:2]
            lojas.append({"aba": nome_aba, "linha": numero, "colaborador": colaborador,
                          "chave": normalizar_texto(colaborador), "cnpj": _texto(r.get("cnpj")), "loja": loja,
                          "cidade": _texto(r.get("cidade")).upper(), "uf": uf if uf in UFS else nome_aba,
                          "supervisor": _texto(bruto_supervisor)})
        if supervisor_na:
            avisos.append((f'Aba "{nome_aba}": {supervisor_na} linha(s) com supervisor vazio ou "#N/A"', []))
    return lojas


def _cnpj_do_sistema(texto: str) -> str:
    """O CNPJ como o sistema vai entender (mesma correção da importação): "" se for inválido."""
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) == 15 and digitos[0] == "0":
        digitos = digitos[1:]
    elif len(digitos) in (12, 13):
        digitos = digitos.zfill(14)
    return digitos if cnpj_valido(digitos) else ""


def ligar(promotores: list[dict], lojas: list[dict], avisos: list) -> None:
    """Liga cada loja do roteiro ao cadastro do promotor (pelo nome; na dúvida, pela UF; senão, por semelhança)."""
    por_nome = defaultdict(list)
    for p in promotores:
        por_nome[p["chave"]].append(p)
    nomes = list(por_nome)
    parecidos, sem_cadastro, homonimos = set(), set(), set()
    for loja in lojas:
        candidatos = por_nome.get(loja["chave"])
        if not candidatos:
            perto = difflib.get_close_matches(loja["chave"], nomes, n=1, cutoff=0.88)
            if perto:
                candidatos = por_nome[perto[0]]
                parecidos.add(f"{loja['colaborador']} → {candidatos[0]['nome']}")
        if not candidatos:
            loja["promotor"] = None
            sem_cadastro.add(f"{loja['colaborador']} ({loja['aba']})")
            continue
        if len(candidatos) > 1:
            da_uf = [p for p in candidatos if p["uf"] == loja["uf"]]
            if len(da_uf) == 1:
                candidatos = da_uf
            else:
                homonimos.add(loja["colaborador"])
        loja["promotor"] = candidatos[0]
    if parecidos:
        avisos.append(("Nome do roteiro ligado ao cadastro por semelhança (confira)", sorted(parecidos)))
    if sem_cadastro:
        avisos.append(("Promotor do roteiro sem cadastro na PROMOTORES BRASIL: lojas entram com R$ 0",
                       sorted(sem_cadastro)))
    if homonimos:
        avisos.append(("Nome repetido no cadastro (usei o primeiro): confira", sorted(homonimos)))
    usados = {id(l["promotor"]) for l in lojas if l.get("promotor")}
    sem_lojas = [p["nome"] for p in promotores if id(p) not in usados]
    if sem_lojas:
        avisos.append(("No cadastro, mas sem nenhuma loja no roteiro (supervisores, desligados…): custo não entra",
                       sem_lojas))
    invalidos = sorted({f"{l['loja']} ({l['cnpj'] or 'sem CNPJ'}) - {l['aba']} linha {l['linha']}"
                        for l in lojas if not _cnpj_do_sistema(l["cnpj"])})
    if invalidos:
        avisos.append(("CNPJ inválido: a loja entra sem faturamento até corrigir", invalidos))


def _meses(de: str, ate: str) -> list[tuple[int, int]]:
    a1, m1 = (int(x) for x in de.split("-"))
    a2, m2 = (int(x) for x in ate.split("-"))
    inicio, fim = a1 * 12 + m1 - 1, a2 * 12 + m2 - 1
    if fim < inicio:
        raise SystemExit("--ate precisa ser depois de --de.")
    return [(i // 12, i % 12 + 1) for i in range(inicio, fim + 1)]


def montar_linhas(lojas: list[dict], meses: list[tuple[int, int]], agencia: str) -> list[dict]:
    """Uma linha por loja × mês. Custo do promotor dividido igualmente entre as lojas dele (sem repetir a loja)."""
    por_promotor = defaultdict(list)
    for loja in lojas:
        chave_loja = (_cnpj_do_sistema(loja["cnpj"]) or loja["cnpj"], normalizar_texto(loja["loja"]))
        dono = id(loja["promotor"]) if loja.get("promotor") else ("sem", loja["chave"])
        if all(chave_loja != (c, n) for c, n, _ in por_promotor[dono]):
            por_promotor[dono].append((*chave_loja, loja))
    linhas = []
    for (ano, mes) in meses:
        fim_do_mes = date(ano + (mes == 12), mes % 12 + 1, 1)
        for itens in por_promotor.values():
            promotor = itens[0][2].get("promotor")
            if promotor and promotor["admissao"] and promotor["admissao"] >= fim_do_mes:
                continue   # ainda não tinha sido admitido
            custo = promotor["custo"] if promotor else 0.0
            centavos = int(round(custo * 100))
            parte, resto = divmod(centavos, len(itens))
            for posicao, (_, _, loja) in enumerate(itens):
                valor = (parte + (resto if posicao == len(itens) - 1 else 0)) / 100
                supervisor = loja["supervisor"] or (promotor["supervisor"] if promotor else "")
                observacao = f"Gerado da planilha ROTEIROS X FATURAMENTOS ({loja['aba']}, linha {loja['linha']})"
                linhas.append({
                    "Mês de referência": f"{mes:02d}/{ano}", "Agência ou MEI": agencia, "Tipo": "CLT",
                    "CNPJ da loja": formatar(_cnpj_do_sistema(loja["cnpj"])) or loja["cnpj"], "Loja": loja["loja"],
                    "Cidade": loja["cidade"], "UF": loja["uf"],
                    "Promotor": promotor["nome"] if promotor else loja["colaborador"],
                    "Código do promotor": promotor["codigo"] if promotor else "",
                    "Valor do mês (R$)": valor, "Status": "Ativa", "Observação": observacao, "Supervisor": supervisor,
                })
    return linhas


def gravar(linhas: list[dict], avisos: list, saida: Path, resumo: dict) -> None:
    livro = load_workbook(MODELO)
    aba = livro["Atendimentos"]
    posicoes = {aba.cell(1, c).value: c for c in range(1, aba.max_column + 1) if aba.cell(1, c).value}
    for coluna in range(1, posicoes["Conferência do CNPJ"]):
        aba.cell(2, coluna).value = None   # tira a linha de exemplo
    for numero, linha in enumerate(linhas, start=2):
        for titulo, valor in linha.items():
            aba.cell(numero, posicoes[titulo], valor if valor != "" else None)
    conferencia = livro.create_sheet("Conferência")
    conferencia["A1"] = "Conferência da conversão (esta aba não é importada)"
    linha = 3
    for rotulo, valor in resumo.items():
        conferencia.cell(linha, 1, rotulo)
        conferencia.cell(linha, 2, valor)
        linha += 1
    linha += 1
    for titulo, itens in avisos:
        conferencia.cell(linha, 1, f"⚠ {titulo}" + (f" ({len(itens)})" if itens else ""))
        linha += 1
        for item in itens:
            conferencia.cell(linha, 2, item)
            linha += 1
    conferencia.column_dimensions["A"].width = 70
    conferencia.column_dimensions["B"].width = 70
    livro.save(saida)


def converter(planilha: Path, de: str, ate: str, saida: Path | None = None, abas=None,
              agencia: str = "101 do Brasil") -> dict:
    avisos: list = []
    livro = load_workbook(planilha, read_only=True, data_only=True)
    try:
        promotores = ler_promotores(livro, avisos)
        lojas = ler_roteiros(livro, abas or ABAS_ROTEIRO, avisos)
    finally:
        livro.close()
    if not lojas:
        raise SystemExit("Nenhuma loja encontrada nas abas de roteiro.")
    ligar(promotores, lojas, avisos)
    meses = _meses(de, ate)
    linhas = montar_linhas(lojas, meses, agencia)
    saida = saida or planilha.with_name(f"Atendimento_CLT_101_{de}_a_{ate}.xlsx")
    resumo = {
        "Planilha": planilha.name, "Meses": f"{de} a {ate} ({len(meses)})",
        "Promotores no cadastro": len(promotores),
        "Promotores com lojas no roteiro": len({id(l["promotor"]) for l in lojas if l.get("promotor")}),
        "Lojas no roteiro": len(lojas), "Linhas geradas (loja × mês)": len(linhas),
        "Valor total gerado (R$)": round(sum(l["Valor do mês (R$)"] for l in linhas), 2),
    }
    gravar(linhas, avisos, saida, resumo)
    return {"saida": saida, "resumo": resumo, "avisos": avisos, "linhas": linhas}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("planilha", type=Path, help='a "ROTEIROS X FATURAMENTOS.xlsm"')
    parser.add_argument("--de", required=True, help="primeiro mês, AAAA-MM (ex.: 2026-01)")
    parser.add_argument("--ate", required=True, help="último mês, AAAA-MM (ex.: 2026-09)")
    parser.add_argument("--saida", type=Path, help="arquivo a gerar (.xlsx)")
    parser.add_argument("--abas", default=",".join(ABAS_ROTEIRO), help="abas de roteiro (padrão: SC,SP,PR,MG,RS)")
    parser.add_argument("--agencia", default="101 do Brasil", help='nome da "agência" (padrão: 101 do Brasil)')
    args = parser.parse_args()
    for valor in (args.de, args.ate):
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", valor):
            parser.error(f"mês inválido: {valor} (use AAAA-MM)")
    if not args.planilha.exists():
        parser.error(f"arquivo não encontrado: {args.planilha}")
    print("Lendo a planilha (as abas de promotores e roteiros; pode levar alguns segundos)…")
    resultado = converter(args.planilha, args.de, args.ate, args.saida,
                          [a.strip() for a in args.abas.split(",") if a.strip()], args.agencia)
    print()
    for rotulo, valor in resultado["resumo"].items():
        print(f"  {rotulo}: {valor}")
    for titulo, itens in resultado["avisos"]:
        print(f"\n⚠ {titulo}" + (f" ({len(itens)})" if itens else ""))
        for item in itens[:10]:
            print(f"    - {item}")
        if len(itens) > 10:
            print(f"    … mais {len(itens) - 10} (lista completa na aba Conferência do arquivo gerado)")
    print(f"\nArquivo gerado: {resultado['saida']}")
    print("Próximo passo: no sistema, aba Agências > Importar o arquivo de uma agência > confira a prévia > Gravar.")


if __name__ == "__main__":
    main()
