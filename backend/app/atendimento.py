"""Atendimento das agências: leitura do arquivo (modelo único), prévia, gravação, desfazer e leitura para o cálculo.

Cada linha do arquivo é uma loja atendida num mês por uma agência (ou MEI, ou a própria 101 com promotor CLT):
mês, agência, CNPJ e nome da loja, cidade, UF, promotor, dias de visita, visitas no mês, valor do mês e status.
Lojas, promotores e agências do sistema são montados a partir destas linhas (tabela atendimentos).

Regras da leitura (cada uma vira aviso na prévia, para a agência corrigir no próximo arquivo):
- CNPJ: vale só com os 2 dígitos verificadores certos (app/cnpj.py). Com um zero a mais na frente (15 dígitos,
  ex.: "009.477.652/0042-64") é corrigido quando, sem o zero, fica válido; com 12 ou 13 dígitos (o Excel comeu o
  zero) ganha os zeros. O resto (inclusive 14 dígitos com verificador errado) fica sem CNPJ: a loja entra, mas sem
  faturamento, e a prévia mostra a linha do arquivo para a agência corrigir.
- Mês de referência: MM/AAAA, AAAA-MM, data do Excel ou "out/2026".
- Valor vazio = 0 (com aviso); valor que não é número = linha com erro (não entra).
- Linha de exemplo do modelo ("EXEMPLO - apague…") e linhas de total (sem loja) são ignoradas.
- Cabeçalho repetido no meio do arquivo (ex.: cada bloco de agência com o seu título e cabeçalho) e linha que parece
  título (sem CNPJ, sem valor e sem visitas) são descartados e listados na prévia.
- Promotor: identificado pelo "Código do promotor" quando vier; sem código, pelo nome dentro da agência.
"""
import difflib
import json
import re
import secrets
import threading
import time
from datetime import date, datetime

import pandas as pd
from sqlalchemy import delete, select, text

from . import db, respostas_guardadas
from .cnpj import cnpj_valido as _cnpj_valido
from .cnpj import formatar as formatar_cnpj
from .importacao import (ErroImportacao, _ler_abas, _mapear_colunas, devolver_memoria, ler_numero,
                         normalizar_texto)
from .modelos import Atendimento, Importacao

APELIDOS = {
    "mes": ["MES DE REFERENCIA", "MES REFERENCIA", "MES", "COMPETENCIA", "REFERENCIA"],
    "agencia": ["AGENCIA OU MEI", "AGENCIA", "EMPRESA", "AGENCIA MEI"],
    "tipo": ["TIPO", "TIPO DE CONTRATACAO", "TIPO DO PROMOTOR", "TIPO PROMOTOR", "VINCULO", "CONTRATACAO"],
    "cnpj": ["CNPJ DA LOJA", "CNPJ", "ESTAB CNPJ", "CNPJ LOJA", "CPF CNPJ"],
    "loja": ["LOJA", "ESTABELECIMENTO", "MERCADO", "LOJAS", "PDV"],
    "cidade": ["CIDADE", "MUNICIPIO"],
    "uf": ["UF", "ESTADO"],
    "promotor": ["PROMOTOR", "NOME DO PROMOTOR", "COLABORADOR"],
    "codigo": ["CODIGO DO PROMOTOR", "COD PROMOTOR", "CODIGO PROMOTOR", "MATRICULA"],
    "dias": ["DIAS DE VISITA", "DIAS DE ATENDIMENTO", "DIA DE ATEND", "DIAS"],
    "visitas": ["VISITAS NO MES", "VIS MES", "VISITAS MES", "QUANTIDADE DE ATENDIMENTOS", "VISITAS"],
    "valor": ["VALOR DO MES R", "VALOR DO MES", "VLR MES", "VALOR MES", "VALOR TOTAL", "VALOR"],
    "status": ["STATUS", "STATUS ATENDIMENTO", "SITUACAO"],
    "observacao": ["OBSERVACAO", "OBSERVACOES", "OBS"],
    "supervisor": ["SUPERVISOR", "SUPERVISORA", "SUPERVISOR MERCHAN", "SUPERVISOR A"],
    "frequencia": ["FREQUENCIA SEMANA", "FREQUENCIA SEMANAL", "FREQUENCIA", "VEZES POR SEMANA", "FREQ SEMANA"],
}
# Arquivo dos MEIs ("CONTROLE DE PROMOTORES MEI", aba "CONTROLE GERAL"): sem Mês, Agência e Loja; loja e CNPJ juntos
# em "CLIENTE / CNPJ"; promotor e valor em células mescladas por bloco de lojas do mesmo promotor.
APELIDOS_MEI = {
    "promotor": ["NOME DO PROMOTOR", "PROMOTOR"],
    "uf": ["UF", "ESTADO"],
    "cidade": ["CIDADE", "MUNICIPIO"],
    "cliente": ["CLIENTE CNPJ", "CLIENTE"],
    "frequencia": APELIDOS["frequencia"],
    "observacao": ["OBSERVACAO", "OBSERVACOES", "OBS"],
    "valor": ["VALOR R", "VALOR"],
}
OBRIGATORIAS_MEI = ("promotor", "cliente", "valor")
OBRIGATORIAS = ("agencia", "cnpj", "loja", "valor")
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
NOMES_MESES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10,
               "NOV": 11, "DEZ": 12}
SEM_PROMOTOR = "Sem promotor informado"
TIPOS = ("Agência", "CLT", "MEI", "Freelancer")
VALIDADE_PREVIA = 30 * 60


# ---------------------------------------------------------------------------------------------------------------
# Campos
# ---------------------------------------------------------------------------------------------------------------

def cnpj_valido(digitos: str) -> bool:
    return _cnpj_valido(digitos)


def ler_cnpj(valor) -> tuple[str, str]:
    """Devolve (cnpj com 14 dígitos ou "", aviso ou ""). Aceita o CNPJ junto com o nome na mesma célula."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "", "sem CNPJ"
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = str(valor).strip()
    achado = re.search(r"\d[\d.\-/\s]{10,22}\d", texto)
    digitos = re.sub(r"\D", "", achado.group(0) if achado else texto)
    if len(digitos) == 14:
        if cnpj_valido(digitos):
            return digitos, ""
        return "", "dígito verificador não confere"
    if len(digitos) == 15 and digitos[0] == "0" and cnpj_valido(digitos[1:]):
        return digitos[1:], "corrigido"
    if len(digitos) in (12, 13) and cnpj_valido(digitos.zfill(14)):
        return digitos.zfill(14), "corrigido"
    if not texto:
        return "", "sem CNPJ"
    return "", f"{len(digitos)} dígitos" if digitos else "não é um CNPJ"


def ler_mes(valor) -> tuple[int, int] | None:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (datetime, date, pd.Timestamp)):
        return valor.year, valor.month
    texto = normalizar_texto(valor)
    achado = re.fullmatch(r"(\d{1,2}) (\d{4})", texto) or re.fullmatch(r"(\d{4}) (\d{1,2})(?: \d{1,2})?", texto)
    if achado:
        a, b = int(achado.group(1)), int(achado.group(2))
        ano, mes = (b, a) if a <= 12 and b > 12 else (a, b)
        return (ano, mes) if 1 <= mes <= 12 and 2000 <= ano <= 2100 else None
    achado = re.fullmatch(r"([A-Z]{3})[A-Z]* (\d{2,4})", texto)
    if achado and achado.group(1) in NOMES_MESES:
        ano = int(achado.group(2))
        return (ano + 2000 if ano < 100 else ano), NOMES_MESES[achado.group(1)]
    return None


def _texto(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    return re.sub(r"\s+", " ", str(valor)).strip()


ERROS_DO_EXCEL = {"N A", "NA", "REF", "VALUE", "DIV 0", "NAME", "NULL", "NUM"}   # "#N/A", "#REF!"…


def _texto_sem_erro(valor) -> str:
    """Texto da célula, com os erros do Excel ("#N/A", "#REF!"…) virando vazio."""
    texto = _texto(valor)
    return "" if normalizar_texto(texto) in ERROS_DO_EXCEL else texto


def _visitas(valor):
    """Visitas no mês: vazio (ou texto) = None (não informado); 0 continua 0 (vazio ≠ zero)."""
    if _vazio(valor):
        return None
    numero = ler_numero(valor)
    if numero is None or numero < 0:
        return None
    return int(round(numero))


def _status(valor) -> str:
    return "Encerrada" if normalizar_texto(valor).startswith("ENCERR") else "Ativa"


def ler_tipo(valor, agencia: str) -> tuple[str, bool]:
    """(tipo, veio_do_arquivo). Sem a coluna Tipo (ou com valor fora da lista), deduz pelo nome da agência:
    a própria 101 ou "CLT" no nome = CLT; "MEI" = MEI; "Freelancer" = Freelancer; o resto = Agência."""
    texto = normalizar_texto(valor)
    for tipo, chaves in (("CLT", ("CLT",)), ("MEI", ("MEI",)), ("Freelancer", ("FREELANCER", "FREELA", "FREE LANCER")),
                         ("Agência", ("AGENCIA",))):
        if texto and any(texto == c or texto.startswith(c + " ") for c in chaves):
            return tipo, True
    nome = f" {normalizar_texto(agencia)} "
    if " CLT " in nome or nome.startswith(" 101 DO BRASIL"):
        return "CLT", False
    if " MEI " in nome:
        return "MEI", False
    if " FREELA" in nome or " FREE LANCER " in nome:
        return "Freelancer", False
    return "Agência", False


def chave_promotor(agencia_chave: str, codigo: str, nome: str) -> str:
    """Mesmo promotor em arquivos diferentes: pelo código, se a agência informar; senão pelo nome na agência."""
    if codigo:
        return f"{agencia_chave}|cod:{normalizar_texto(codigo)}"
    return f"{agencia_chave}|{normalizar_texto(nome)}"


# ---------------------------------------------------------------------------------------------------------------
# Leitura do arquivo
# ---------------------------------------------------------------------------------------------------------------

def _colunas(dados: pd.DataFrame, mapa: dict) -> pd.DataFrame:
    return pd.DataFrame({campo: dados.iloc[:, posicao] if posicao < dados.shape[1]
                         else pd.Series([None] * len(dados), index=dados.index, dtype=object)
                         for campo, posicao in mapa.items()})


def _tabelas(conteudo: bytes, nome_arquivo: str, mes_escolhido: str = ""):
    """(aba, linha do cabeçalho no Excel, DataFrame com as colunas renomeadas, info do MEI ou None) das abas que
    têm o modelo, ou o layout do arquivo dos MEIs (convertido para as colunas do modelo)."""
    for aba, ler in _ler_abas(conteudo, nome_arquivo):
        previa = ler(nrows=30)
        melhor, mei = None, None
        for indice, linha in previa.iterrows():
            mapa = _mapear_colunas(linha.tolist(), APELIDOS)
            if all(c in mapa for c in OBRIGATORIAS) and (melhor is None or len(mapa) > len(melhor[1])):
                melhor = (indice, mapa)
            mapa_mei = _mapear_colunas(linha.tolist(), APELIDOS_MEI)
            if mei is None and all(c in mapa_mei for c in OBRIGATORIAS_MEI) and "agencia" not in mapa:
                mei = (indice, mapa_mei)
        if melhor is not None:
            cabecalho, mapa = melhor
            yield aba, cabecalho + 2, _colunas(ler(skiprows=cabecalho + 1), mapa), None
        elif mei is not None:
            cabecalho, mapa = mei
            tabela, info = _tabela_mei(_colunas(ler(skiprows=cabecalho + 1), mapa), mes_escolhido)
            yield aba, cabecalho + 2, tabela, info


_CNPJ_NO_FIM = re.compile(r"\(?\s*(\d[\d./\-]{10,20}\d)\s*\)?\s*$")   # sem espaço dentro do CNPJ


def separar_cliente(texto: str) -> tuple[str, str]:
    """"MAX FORT - 14.814.080/0003-41" → ("MAX FORT", "14.814.080/0003-41"); "NIEDERAUER / 881232160005-58";
    "ROTA /  (15.384.277/0003-02) - 15.384.277/0003-02" → ("ROTA", ...). Sem número no fim: (texto, "")."""
    texto = _texto(texto)
    achado = _CNPJ_NO_FIM.search(texto)
    if not achado:
        return texto, ""
    loja = re.sub(r"\(\s*[\d./\-]{11,}\s*\)", " ", texto[:achado.start()])   # "(15.384.277/0003-02)" repetido
    loja = re.sub(r"\s+", " ", loja).strip(" -/–|(")
    return (loja or texto), achado.group(1).strip()


def ler_frequencia(valor) -> int | None:
    """Vezes por semana: 3, "3", "3x", "3 vezes" → 3. Vazio ou sem número → None."""
    if _vazio(valor):
        return None
    numero = ler_numero(valor)
    if numero is None:
        achado = re.search(r"\d+", _texto(valor))
        numero = float(achado.group()) if achado else None
    if numero is None or numero <= 0 or numero > 7:
        return None
    return int(round(numero))


def _tabela_mei(tabela: pd.DataFrame, mes_escolhido: str) -> tuple[pd.DataFrame, dict]:
    """Converte o layout dos MEIs nas colunas do modelo.

    - Promotor (coluna A mesclada): vale para as linhas de baixo até o próximo nome.
    - Valor (coluna G mesclada): o valor do bloco é dividido em partes iguais entre as lojas do promotor; os
      centavos que sobram do arredondamento vão para a última loja do bloco (a soma bate com o arquivo).
      Se cada loja tiver o próprio valor (sem mesclar), vale o de cada linha.
    - Agência: "MEI - <Promotor>" (cada MEI é um prestador, com nota e pagamento próprios). Tipo: MEI.
    - Mês: o arquivo não tem; vem do campo "Mês de referência" escolhido na importação."""
    if not mes_escolhido or ler_mes(mes_escolhido) is None:
        raise ErroImportacao("Este é o arquivo dos MEIs (\"CONTROLE GERAL\"), que não tem o mês: escolha o mês de "
                             "referência no campo \"Mês de referência\" e leia o arquivo de novo.")
    ano, mes = ler_mes(mes_escolhido)
    t = tabela.copy()
    t["cliente"] = t["cliente"].map(_texto)
    linhas_loja = t["cliente"] != ""
    novo_bloco = t["promotor"].map(lambda v: not _vazio(v))
    t["bloco"] = novo_bloco.cumsum()
    t["promotor"] = t["promotor"].where(novo_bloco).ffill()
    t = t[linhas_loja & (t["bloco"] > 0)].copy()
    divisoes, valores = [], []
    for _, g in t.groupby("bloco", sort=False):
        preenchidos = [v for v in g["valor"] if not _vazio(v)]
        if len(preenchidos) == 1 and len(g) > 1 and not _vazio(g["valor"].iloc[0]):
            total = ler_numero(g["valor"].iloc[0])
            if total is None:
                valores += [g["valor"].iloc[0]] + [None] * (len(g) - 1)
                continue
            parte = round(total / len(g), 2)
            partes = [parte] * len(g)
            partes[-1] = round(total - parte * (len(g) - 1), 2)
            valores += partes
            divisoes.append(f"{_texto(g['promotor'].iloc[0]).title()}: {_brl(total)} ÷ {len(g)} lojas = {_brl(parte)}"
                            + (f" (última loja {_brl(partes[-1])})" if partes[-1] != parte else ""))
        else:
            valores += list(g["valor"])
    t["valor"] = valores
    separados = t["cliente"].map(separar_cliente)
    nomes = t["promotor"].map(lambda v: _texto(v).title())
    convertida = pd.DataFrame({
        "mes": f"{mes:02d}/{ano}", "agencia": "MEI - " + nomes, "tipo": "MEI",
        "cnpj": [c for _, c in separados], "loja": [l for l, _ in separados],
        "cidade": t["cidade"] if "cidade" in t else "", "uf": t["uf"] if "uf" in t else "",
        "promotor": nomes, "frequencia": t["frequencia"] if "frequencia" in t else None,
        "observacao": t["observacao"] if "observacao" in t else "", "valor": t["valor"],
    }, index=t.index)
    # Mantém a numeração das linhas do Excel (as linhas vazias ficam de fora sem desalinhar).
    convertida = convertida.reindex(range(len(tabela)))
    return convertida, {"mes": f"{mes:02d}/{ano}", "divisoes": divisoes}


def _brl(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


_NOMES_CABECALHO = {campo: {normalizar_texto(n) for n in nomes} for campo, nomes in APELIDOS.items()}


def _cabecalho_repetido(registro: dict) -> bool:
    """A linha repete o cabeçalho: 2 ou mais células com o nome da própria coluna ("LOJA", "CNPJ"…)."""
    iguais = sum(1 for campo, valor in registro.items()
                 if campo in _NOMES_CABECALHO and normalizar_texto(valor) in _NOMES_CABECALHO[campo])
    return iguais >= 2


def _vazio(valor) -> bool:
    return valor is None or (isinstance(valor, float) and pd.isna(valor)) or _texto(valor) == ""


def _parece_titulo(registro: dict) -> bool:
    """Título ou separador de bloco (ex.: "ATENDIMENTOS FORT"), não uma loja.

    Linha com Mês (válido) e Agência preenchidos é SEMPRE uma loja, mesmo sem CNPJ, valor e visitas (ex.: promotor
    CLT, que não tem custo por loja). Só é título quando falta o Mês ou a Agência E também não tem CNPJ, valor nem
    visitas. Se faltar Mês/Agência mas tiver CNPJ ou valor, a linha vai para "linhas com erro" (não some calada)."""
    if ler_mes(registro.get("mes")) is not None and not _vazio(registro.get("agencia")):
        return False
    tem_digitos = bool(re.search(r"\d{6}", re.sub(r"\D", "", _texto(registro.get("cnpj")))))
    return not tem_digitos and _vazio(registro.get("valor")) and _vazio(registro.get("visitas"))


def chave_loja(loja: str, cnpj: str, cidade: str, uf: str) -> str:
    """Nome normalizado da loja; sem CNPJ válido, mais cidade e UF (duas lojas de mesmo nome em cidades diferentes,
    ex.: SUPER BENEDETTI de Três de Maio e de Crissiumal, continuam sendo duas lojas)."""
    if cnpj:
        return normalizar_texto(loja)[:200]
    return f"{normalizar_texto(loja)} | {normalizar_texto(cidade)} {normalizar_texto(uf)}".strip()[:200]


def ler_atendimento(conteudo: bytes, nome_arquivo: str, mes_escolhido: str = "") -> dict:
    """Lê o arquivo da agência. Devolve {linhas: DataFrame, erros: [...], avisos: [...], abas: [...]}.
    mes_escolhido ("MM/AAAA" ou "AAAA-MM"): só para o arquivo dos MEIs, que não tem a coluna Mês."""
    tabelas = list(_tabelas(conteudo, nome_arquivo, mes_escolhido))
    if not tabelas:
        raise ErroImportacao(
            "Não encontrei a tabela de atendimento. O arquivo precisa ter as colunas Agência ou MEI, CNPJ da loja, "
            "Loja e Valor do mês (use o modelo \"Atendimento das agências\").")
    linhas, erros, descartadas, cnpjs_invalidos, incompletas = [], [], [], [], []
    corrigidos, sem_promotor, promotor_agencia, sem_mes_coluna = [], [], [], False
    tipo_invalido = []
    meis = [info for _, _, _, info in tabelas if info]
    for aba, primeira, tabela, _info in tabelas:
        if "mes" not in tabela:
            sem_mes_coluna = True
        for posicao, registro in enumerate(tabela.to_dict("records")):
            numero = primeira + posicao
            loja = _texto(registro.get("loja"))
            observacao = _texto(registro.get("observacao"))
            if normalizar_texto(observacao).startswith("EXEMPLO"):
                continue  # linha de exemplo do modelo
            if not loja:
                continue  # linha vazia ou de total/título
            conteudo_linha = " | ".join(_texto(v) for v in registro.values() if not _vazio(v))[:160]
            if _cabecalho_repetido(registro):
                descartadas.append({"linha": numero, "aba": aba, "motivo": "Cabeçalho repetido",
                                    "conteudo": conteudo_linha})
                continue
            if _parece_titulo(registro):
                descartadas.append({"linha": numero, "aba": aba, "motivo": "Parece título (sem CNPJ, valor e visitas)",
                                    "conteudo": conteudo_linha})
                continue
            agencia = _texto(registro.get("agencia"))
            if not agencia:
                erros.append({"linha": numero, "aba": aba, "motivo": "Agência ou MEI vazio"})
                continue
            mes = ler_mes(registro.get("mes"))
            if mes is None:
                erros.append({"linha": numero, "aba": aba, "motivo": "Mês de referência vazio ou inválido (use MM/AAAA)"})
                continue
            valor_bruto = registro.get("valor")
            if _vazio(valor_bruto):
                valor = None   # não informado (vazio ≠ R$ 0,00): fica NULL no banco
            else:
                valor = ler_numero(valor_bruto)
                if valor is None or valor < 0:
                    erros.append({"linha": numero, "aba": aba, "motivo": f"Valor do mês não é número: {_texto(valor_bruto)[:30]}"})
                    continue
            visitas = _visitas(registro.get("visitas"))
            frequencia = ler_frequencia(registro.get("frequencia"))
            if frequencia is None:
                achado = re.match(r"\s*(\d)\s*x\s*/?\s*(por\s+)?semana", _texto(registro.get("dias")), re.I)
                frequencia = int(achado.group(1)) if achado else None
            falta = [nome for nome, vazio in (("valor do mês", valor is None),
                                              ("visitas no mês", visitas is None and frequencia is None)) if vazio]
            if falta:
                incompletas.append({"linha": numero, "aba": aba, "loja": loja[:200], "agencia": agencia[:150],
                                    "falta": " e ".join(falta)})
            cnpj, aviso_cnpj = ler_cnpj(registro.get("cnpj"))
            if aviso_cnpj == "corrigido":
                corrigidos.append(loja)
            elif not cnpj:
                cnpjs_invalidos.append({"linha": numero, "aba": aba, "loja": loja[:200],
                                        "cnpj": _texto(registro.get("cnpj"))[:40], "motivo": aviso_cnpj})
            promotor = _texto(registro.get("promotor"))
            if not promotor:
                promotor = SEM_PROMOTOR
                sem_promotor.append(loja)
            elif normalizar_texto(promotor) == normalizar_texto(agencia) or \
                    normalizar_texto(promotor).startswith("AGENCIA "):
                promotor_agencia.append(f"{promotor} (linha {numero})")
            tipo, do_arquivo = ler_tipo(registro.get("tipo"), agencia)
            if "tipo" in registro and not _vazio(registro.get("tipo")) and not do_arquivo:
                tipo_invalido.append(f"{_texto(registro.get('tipo'))[:20]} (linha {numero})")
            codigo = _texto(registro.get("codigo"))
            uf = normalizar_texto(registro.get("uf"))[:2]
            uf = uf if uf in UFS else ""
            cidade = _texto(registro.get("cidade"))[:120].upper()
            agencia_chave = normalizar_texto(agencia)
            dias = _texto(registro.get("dias"))[:80] or (f"{frequencia}x/semana" if frequencia else "")
            linhas.append({
                "linha": numero, "aba": aba, "ano": mes[0], "mes": mes[1], "agencia": agencia[:150],
                "agencia_chave": agencia_chave[:150], "tipo": tipo, "cnpj": cnpj, "loja": loja[:200],
                "loja_chave": chave_loja(loja, cnpj, cidade, uf), "cidade": cidade,
                "uf": uf, "promotor": promotor[:150], "promotor_codigo": codigo[:40],
                "promotor_chave": chave_promotor(agencia_chave, codigo, promotor)[:200],
                "dias": dias, "visitas": visitas, "frequencia_semana": frequencia,
                "cnpj_arquivo": "" if cnpj else _texto(registro.get("cnpj"))[:40],
                "valor": None if valor is None else round(float(valor), 2), "status": _status(registro.get("status")),
                "supervisor": _texto_sem_erro(registro.get("supervisor"))[:100],
                "observacao": observacao[:2000],
            })
    if not linhas:
        raise ErroImportacao("O arquivo não tem nenhuma linha válida de atendimento."
                             + (f" Primeiro erro: {erros[0]['motivo']} ({erros[0]['aba']}, linha {erros[0]['linha']})."
                                if erros else ""))
    df = pd.DataFrame(linhas)

    # Cada loja aparece uma vez em cada aviso (o arquivo pode ter vários meses da mesma loja).
    corrigidos, sem_promotor, promotor_agencia = (
        list(dict.fromkeys(lista)) for lista in (corrigidos, sem_promotor, promotor_agencia))
    # Vazio = não informado (NaN), nunca 0: as somas ignoram, e o cálculo mostra "custo não informado".
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["visitas"] = pd.to_numeric(df["visitas"], errors="coerce")
    df["frequencia_semana"] = pd.to_numeric(df["frequencia_semana"], errors="coerce")
    lojas_sem_cnpj = list(dict.fromkeys(c["loja"] for c in cnpjs_invalidos))
    avisos = []
    for info in meis:
        avisos.append(f"Arquivo dos MEIs: gravado em {info['mes']} (mês escolhido na importação); cada promotor é "
                      "uma agência \"MEI - <nome>\". Visitas estimadas pela frequência por semana.")
        if info["divisoes"]:
            avisos.append("Valor do promotor (célula mesclada) dividido igualmente entre as lojas dele: "
                          + "; ".join(info["divisoes"]) + ".")
    if sem_mes_coluna:
        avisos.append("Uma aba não tem a coluna \"Mês de referência\": as linhas dela entraram como erro.")
    if corrigidos:
        avisos.append(f"{len(corrigidos)} CNPJ(s) com zero a mais na frente ou zero faltando foram corrigidos: "
                      + ", ".join(corrigidos[:8]) + (" …" if len(corrigidos) > 8 else ""))
    if lojas_sem_cnpj:
        avisos.append(f"{len(lojas_sem_cnpj)} loja(s) sem CNPJ válido entram sem faturamento: veja a lista \"CNPJ "
                      "inválido\" abaixo, com a linha do arquivo, e peça a correção à agência.")
    if descartadas:
        avisos.append(f"{len(descartadas)} linha(s) descartadas por parecerem cabeçalho ou título: veja a lista "
                      "\"Linhas descartadas\" abaixo.")
    if tipo_invalido:
        avisos.append(f"{len(tipo_invalido)} linha(s) com Tipo fora da lista (Agência, CLT, MEI, Freelancer): o tipo "
                      "foi deduzido pelo nome da agência: " + "; ".join(tipo_invalido[:6])
                      + (" …" if len(tipo_invalido) > 6 else ""))
    if promotor_agencia:
        avisos.append(f"{len(promotor_agencia)} promotor(es) com nome de agência (confira se a coluna Promotor está "
                      "certa): " + "; ".join(promotor_agencia[:6]) + (" …" if len(promotor_agencia) > 6 else ""))
    sem_valor = sum(1 for i in incompletas if "valor" in i["falta"])
    sem_visitas = sum(1 for i in incompletas if "visitas" in i["falta"])
    if sem_valor:
        avisos.append(f"{sem_valor} loja(s) entraram sem valor do mês (custo não informado, não R$ 0,00): veja a lista "
                      "\"Lojas sem valor ou visitas\" abaixo, com a linha do arquivo.")
    if sem_visitas:
        avisos.append(f"{sem_visitas} loja(s) entraram sem visitas no mês (não informado): veja a lista \"Lojas sem "
                      "valor ou visitas\" abaixo, com a linha do arquivo.")
    if sem_promotor:
        avisos.append(f"{len(sem_promotor)} loja(s) sem promotor ficaram como \"{SEM_PROMOTOR}\": "
                      + "; ".join(sem_promotor[:8]) + (" …" if len(sem_promotor) > 8 else ""))
    repetidas = df[df.duplicated(["agencia_chave", "ano", "mes", "cnpj", "loja_chave", "promotor_chave"], keep=False)]
    if not repetidas.empty:
        avisos.append(f"{len(repetidas)} linha(s) repetidas (mesma agência, mês, loja e promotor): os valores foram "
                      "somados. Confira se não é a mesma loja duas vezes: " + ", ".join(repetidas["loja"].head(6)))
    avisos += _nomes_parecidos(df)
    return {"linhas": df, "erros": erros, "avisos": avisos, "abas": sorted({a for a, _, _, _ in tabelas}),
            "descartadas": descartadas, "cnpjs_invalidos": cnpjs_invalidos, "incompletas": incompletas}


def _nomes_parecidos(df: pd.DataFrame) -> list[str]:
    """Promotores sem código com nomes quase iguais na mesma agência (ex.: "Marceli" e "Marcely")."""
    avisos = []
    sem_codigo = df[(df["promotor_codigo"] == "") & (df["promotor"] != SEM_PROMOTOR)]
    for agencia, grupo in sem_codigo.groupby("agencia"):
        nomes = sorted(set(grupo["promotor"]))
        chaves = {n: normalizar_texto(n) for n in nomes}
        pares = [(a, b) for i, a in enumerate(nomes) for b in nomes[i + 1:]
                 if difflib.SequenceMatcher(None, chaves[a], chaves[b]).ratio() >= 0.85]
        if pares:
            avisos.append(f"{agencia}: nomes de promotor parecidos (se forem a mesma pessoa, use o mesmo nome ou "
                          "a coluna Código do promotor): " + "; ".join(f"{a} / {b}" for a, b in pares[:5]))
    return avisos


# ---------------------------------------------------------------------------------------------------------------
# Prévia e gravação
# ---------------------------------------------------------------------------------------------------------------

_previas: dict[str, dict] = {}
_trava = threading.Lock()


def _rotulo(ano: int, mes: int) -> str:
    return f"{ano}-{mes:02d}"


def _grupos_existentes(conexao, grupos: set[tuple[str, int, int]]) -> set[tuple[str, int, int]]:
    if not grupos:
        return set()
    linhas = conexao.execute(select(Atendimento.agencia_chave, Atendimento.ano, Atendimento.mes).distinct()).all()
    return {(a, int(y), int(m)) for a, y, m in linhas} & grupos


def _chave_loja(cnpj: str, loja_chave: str) -> str:
    """A mesma loja em arquivos diferentes: pelo CNPJ; sem CNPJ válido, pelo nome + cidade/UF (loja_chave)."""
    return f"cnpj:{cnpj}" if cnpj else f"nome:{loja_chave}"


def _repetidas_em_outra_agencia(conexao, df: pd.DataFrame) -> list[dict]:
    """Lojas do arquivo que, no MESMO mês, já estão no sistema por OUTRA agência (ex.: o mesmo arquivo da GRUBAL
    mandado de novo com outro nome de agência: o custo seria contado duas vezes)."""
    meses = {(int(a), int(m)) for a, m in df[["ano", "mes"]].drop_duplicates().itertuples(index=False)}
    if not meses:
        return []
    filtro = " OR ".join(f"(ano = {a} AND mes = {m})" for a, m in sorted(meses))
    existentes = conexao.execute(text(
        "SELECT ano, mes, agencia, agencia_chave, cnpj, loja, loja_chave, importacao_id FROM atendimentos "
        f"WHERE {filtro}")).all()
    no_sistema: dict = {}
    for ano, mes, agencia, agencia_chave, cnpj, loja, loja_chave, importacao_id in existentes:
        no_sistema.setdefault((int(ano), int(mes), _chave_loja(cnpj, loja_chave)), {})[agencia_chave] = (
            agencia, loja, importacao_id)
    repetidas, vistas = [], set()
    for linha in df.itertuples(index=False):
        chave = (int(linha.ano), int(linha.mes), _chave_loja(linha.cnpj, linha.loja_chave))
        for agencia_chave, (agencia, loja, importacao_id) in no_sistema.get(chave, {}).items():
            if agencia_chave == linha.agencia_chave or (chave, linha.agencia_chave, agencia_chave) in vistas:
                continue
            vistas.add((chave, linha.agencia_chave, agencia_chave))
            repetidas.append({"mes": _rotulo(chave[0], chave[1]), "loja": linha.loja, "cnpj": formatar_cnpj(linha.cnpj),
                              "agencia_nova": linha.agencia, "agencia_existente": agencia, "loja_existente": loja,
                              "importacao_existente": importacao_id,
                              # uso interno (gravação), não vão para a tela
                              "_ano": chave[0], "_mes": chave[1], "_chave": chave[2], "_agencia_chave": agencia_chave})
    return repetidas


def _repetidas_no_arquivo(df: pd.DataFrame) -> list[str]:
    """No próprio arquivo, a mesma loja no mesmo mês por duas agências diferentes."""
    chaves = df.assign(chave=[_chave_loja(c, l) for c, l in zip(df["cnpj"], df["loja_chave"])])
    por_loja = chaves.groupby(["ano", "mes", "chave"])["agencia"].agg(lambda v: sorted(set(v)))
    return [f"{linha_loja} em {_rotulo(int(a), int(m))}: {' e '.join(agencias)}"
            for (a, m, _), agencias, linha_loja in zip(
                por_loja.index, por_loja.values,
                chaves.groupby(["ano", "mes", "chave"])["loja"].first().values) if len(agencias) > 1]


def preparar_previa(conteudo: bytes, nome_arquivo: str, usuario: str, mes: str = "") -> dict:
    lido = ler_atendimento(conteudo, nome_arquivo, mes)
    df = lido["linhas"]
    grupos = df.groupby(["agencia_chave", "ano", "mes"])
    with db.engine.connect() as conexao:
        existentes = _grupos_existentes(conexao, {(a, int(y), int(m)) for a, y, m in grupos.groups})
        # A substituição da mesma agência e mês já trata o que for da própria agência; aqui só OUTRAS agências.
        repetidas = _repetidas_em_outra_agencia(conexao, df)
    no_arquivo = _repetidas_no_arquivo(df)
    if no_arquivo:
        lido["avisos"].append(f"{len(no_arquivo)} loja(s) aparecem no arquivo por duas agências no mesmo mês "
                              "(o custo conta duas vezes; confira): " + "; ".join(no_arquivo[:6])
                              + (" …" if len(no_arquivo) > 6 else ""))
    resumo = []
    for (chave, ano, mes), grupo in grupos:
        resumo.append({"agencia": grupo["agencia"].iloc[0], "mes": _rotulo(int(ano), int(mes)),
                       "lojas": int(grupo[["cnpj", "loja_chave"]].drop_duplicates().shape[0]), "promotores": int(grupo["promotor_chave"].nunique()),
                       "visitas": int(grupo["visitas"].fillna(0).sum()), "valor": round(float(grupo["valor"].sum()), 2),
                       "sem_valor": int(grupo["valor"].isna().sum()),
                       "ja_existe": (chave, int(ano), int(mes)) in existentes})
    token = secrets.token_urlsafe(16)
    with _trava:
        agora = time.time()
        for velho in [t for t, p in _previas.items() if agora - p["criado"] > VALIDADE_PREVIA]:
            _previas.pop(velho, None)
        _previas[token] = {"criado": agora, "linhas": df, "erros": lido["erros"], "avisos": lido["avisos"],
                           "arquivo": nome_arquivo, "usuario": usuario, "repetidas": repetidas}
    return {"token": token, "arquivo": nome_arquivo, "abas": lido["abas"], "grupos": resumo,
            "linhas_validas": len(df), "linhas_com_erro": len(lido["erros"]), "erros": lido["erros"][:100],
            "avisos": lido["avisos"], "valor_total": round(float(df["valor"].sum()), 2),
            "lojas": int(df[["cnpj", "loja_chave"]].drop_duplicates().shape[0]),
            "promotores": int(df["promotor_chave"].nunique()),
            "substituir": [f"{g['agencia']} {g['mes']}" for g in resumo if g["ja_existe"]],
            "repetidas_outra_agencia": [{k: v for k, v in r.items() if not k.startswith("_")} for r in repetidas],
            "descartadas": lido["descartadas"][:200],
            "cnpjs_invalidos": lido["cnpjs_invalidos"][:500], "incompletas": lido["incompletas"][:2000]}


ACOES_REPETIDAS = ("substituir", "ignorar")


def confirmar(token: str, substituir: bool, repetidas: str | None = None) -> dict:
    """substituir: troca o que a MESMA agência já tem nos mesmos meses.
    repetidas: o que fazer com as lojas que OUTRA agência já tem no mesmo mês — "substituir" (apaga as da outra
    agência e grava as do arquivo) ou "ignorar" (não grava as do arquivo). Obrigatório quando houver."""
    with _trava:
        previa = _previas.get(token)
    if previa is None:
        raise ErroImportacao("A pré-visualização expirou ou já foi usada. Envie o arquivo de novo.")
    df: pd.DataFrame = previa["linhas"]
    if repetidas is not None and repetidas not in ACOES_REPETIDAS:
        raise ErroImportacao("Escolha o que fazer com as lojas repetidas: substituir ou ignorar.")
    # Linhas repetidas (mesma agência, mês, loja e promotor) viram uma, com os valores somados.
    chaves = ["agencia_chave", "ano", "mes", "cnpj", "loja_chave", "promotor_chave"]
    df = (df.groupby(chaves, as_index=False, sort=False)
            .agg({**{c: "first" for c in df.columns if c not in chaves and c != "valor" and c != "visitas"},
                  # min_count=1: se nenhuma das linhas repetidas tem valor, o total continua "não informado" (NaN), não 0
                  "valor": lambda v: v.sum(min_count=1),
                  "visitas": lambda v: int(v.sum()) if v.notna().any() else None}))
    grupos = {(a, int(y), int(m)) for a, y, m in df[["agencia_chave", "ano", "mes"]].itertuples(index=False)}
    meses = sorted({_rotulo(int(y), int(m)) for _, y, m in grupos})
    ignoradas = substituidas_outras = 0
    with db.engine.begin() as conexao:
        existentes = _grupos_existentes(conexao, grupos)
        if existentes and not substituir:
            raise ErroImportacao("Já existe atendimento importado para " + ", ".join(
                f"{df[df['agencia_chave'] == a]['agencia'].iloc[0]} {_rotulo(y, m)}" for a, y, m in sorted(existentes))
                + ". Confirme a substituição para continuar.")
        # Conferido de novo na hora de gravar: outra importação pode ter entrado depois da prévia.
        outras = _repetidas_em_outra_agencia(conexao, df)
        if outras and repetidas is None:
            raise ErroImportacao(f"{len(outras)} loja(s) do arquivo já estão no sistema por outra agência no mesmo "
                                 "mês. Escolha substituir as repetidas ou ignorá-las.")
        if outras:
            chaves_outras = {(r["_ano"], r["_mes"], r["_chave"]) for r in outras}
            marcada = pd.Series([(int(a), int(m), _chave_loja(c, lc)) in chaves_outras for a, m, c, lc in
                                 df[["ano", "mes", "cnpj", "loja_chave"]].itertuples(index=False)], index=df.index)
            if repetidas == "ignorar":
                ignoradas = int(marcada.sum())
                df = df[~marcada]
                if df.empty:
                    raise ErroImportacao("Todas as lojas do arquivo já estão no sistema por outra agência: nada a "
                                         "gravar.")
                grupos = {(a, int(y), int(m)) for a, y, m in df[["agencia_chave", "ano", "mes"]].itertuples(index=False)}
                meses = sorted({_rotulo(int(y), int(m)) for _, y, m in grupos})
                existentes = {g for g in existentes if g in grupos}
            else:
                for r in outras:
                    tipo, valor = r["_chave"].split(":", 1)
                    condicao = (Atendimento.cnpj == valor) if tipo == "cnpj" else \
                        ((Atendimento.cnpj == "") & (Atendimento.loja_chave == valor))
                    substituidas_outras += conexao.execute(delete(Atendimento).where(
                        Atendimento.ano == r["_ano"], Atendimento.mes == r["_mes"],
                        Atendimento.agencia_chave == r["_agencia_chave"], condicao)).rowcount
        for agencia_chave, ano, mes in existentes:
            conexao.execute(delete(Atendimento).where(Atendimento.agencia_chave == agencia_chave,
                                                      Atendimento.ano == ano, Atendimento.mes == mes))
        importacao_id = conexao.execute(Importacao.__table__.insert().values(
            tipo="atendimento", arquivo_nome=previa["arquivo"][:255], usuario=previa["usuario"],
            periodos=",".join(meses), linhas_lidas=len(previa["linhas"]) + len(previa["erros"]),
            linhas_importadas=len(df), linhas_com_erro=len(previa["erros"]),
            total_venda=round(float(df["valor"].sum()), 2),
            avisos=json.dumps(previa["avisos"], ensure_ascii=False),
            log_erros=json.dumps(previa["erros"], ensure_ascii=False), situacao="ativa")).inserted_primary_key[0]
        registros = []
        for linha in df.to_dict("records"):
            registros.append({c: linha[c] for c in (
                "ano", "mes", "agencia", "agencia_chave", "tipo", "cnpj", "loja", "loja_chave", "cidade", "uf", "promotor",
                "promotor_codigo", "promotor_chave", "dias", "status", "observacao", "linha", "supervisor",
                "cnpj_arquivo")}
                | {"importacao_id": importacao_id,
                   "frequencia_semana": None if pd.isna(linha["frequencia_semana"]) else int(linha["frequencia_semana"]),
                   "valor": None if pd.isna(linha["valor"]) else round(float(linha["valor"]), 2),
                   "visitas": None if pd.isna(linha["visitas"]) else int(linha["visitas"])})
        conexao.execute(Atendimento.__table__.insert(), registros)
        # Importações de atendimento que ficaram sem linha nenhuma (todos os meses substituídos).
        conexao.execute(text(
            "UPDATE importacoes SET situacao = 'substituida' WHERE tipo = 'atendimento' AND situacao = 'ativa' "
            "AND id <> :atual AND NOT EXISTS (SELECT 1 FROM atendimentos a WHERE a.importacao_id = importacoes.id)"),
            {"atual": importacao_id})
    with _trava:
        _previas.pop(token, None)
    dados_mudaram()
    return {"importacao_id": importacao_id, "linhas_importadas": len(df), "meses": meses,
            "substituidos": [f"{df[df['agencia_chave'] == a]['agencia'].iloc[0]} {_rotulo(y, m)}"
                             for a, y, m in sorted(existentes) if (df["agencia_chave"] == a).any()],
            "repetidas_ignoradas": ignoradas, "repetidas_substituidas": substituidas_outras}


def exportar_xlsx(sessao) -> tuple[bytes, int]:
    """Todos os atendimentos num Excel no MESMO modelo que as agências preenchem (dá para importar de novo).

    Devolve (conteúdo do arquivo, número de linhas)."""
    import io

    from openpyxl import load_workbook

    from .main import MODELO_ATENDIMENTO   # import aqui: main importa este módulo
    livro = load_workbook(MODELO_ATENDIMENTO)
    aba = livro["Atendimentos"]
    for coluna in range(1, 16):            # tira a linha de exemplo (a coluna P, conferência do CNPJ, fica)
        aba.cell(2, coluna).value = None
    campos = ("ano", "mes", "agencia", "tipo", "cnpj", "loja", "cidade", "uf", "promotor", "promotor_codigo", "dias",
              "visitas", "valor", "status", "observacao", "supervisor", "cnpj_arquivo")
    consulta = select(*[getattr(Atendimento, c) for c in campos]).order_by(
        Atendimento.ano, Atendimento.mes, Atendimento.agencia, Atendimento.loja)
    total = 0
    for numero, linha in enumerate(sessao.execute(consulta), start=2):
        r = dict(zip(campos, linha))
        promotor = "" if r["promotor"] == SEM_PROMOTOR else r["promotor"]
        cnpj = formatar_cnpj(r["cnpj"]) if r["cnpj"] else (r["cnpj_arquivo"] or "")   # inválido: como veio
        valores = [f"{r['mes']:02d}/{r['ano']}", r["agencia"], r["tipo"], cnpj, r["loja"], r["cidade"],
                   r["uf"], promotor, r["promotor_codigo"], r["dias"], r["visitas"], r["valor"], r["status"],
                   r["observacao"], r["supervisor"]]
        for coluna, valor in enumerate(valores, start=1):
            aba.cell(numero, coluna, valor if valor != "" else None)
        total += 1
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue(), total


def desfazer(sessao, importacao: Importacao) -> dict:
    apagados = sessao.execute(delete(Atendimento).where(Atendimento.importacao_id == importacao.id)).rowcount
    importacao.situacao = "desfeita"
    sessao.commit()
    dados_mudaram()
    return {"itens_apagados": apagados}


def apagar_tudo(sessao) -> int:
    apagados = sessao.execute(delete(Atendimento)).rowcount
    sessao.execute(text("UPDATE importacoes SET situacao = 'apagada' WHERE tipo = 'atendimento' AND situacao = 'ativa'"))
    sessao.commit()
    dados_mudaram()
    return apagados


# ---------------------------------------------------------------------------------------------------------------
# Leitura para o cálculo (guardada na memória até mudar)
# ---------------------------------------------------------------------------------------------------------------

COLUNAS = ["ano", "mes", "agencia", "agencia_chave", "tipo", "cnpj", "loja", "loja_chave", "cidade", "uf", "promotor",
           "promotor_codigo", "promotor_chave", "dias", "visitas", "valor", "status", "supervisor", "observacao",
           "cnpj_arquivo", "frequencia_semana"]
_guardado: dict = {"versao": None, "df": None}
_versao = 0


def dados_mudaram() -> None:
    global _versao
    with _trava:
        _versao += 1
    respostas_guardadas.dados_mudaram()
    devolver_memoria()


def carregar() -> pd.DataFrame:
    """Todos os atendimentos (alguns milhares de linhas no máximo), como DataFrame."""
    with _trava:
        if _guardado["versao"] == _versao and _guardado["df"] is not None:
            return _guardado["df"].copy()
        versao = _versao
    consulta = select(*[getattr(Atendimento, c) for c in COLUNAS])
    with db.engine.connect() as conexao:
        df = pd.DataFrame(conexao.execute(consulta).all(), columns=COLUNAS)
    df["valor"] = df["valor"].astype(float)
    df["visitas"] = pd.to_numeric(df["visitas"], errors="coerce")
    df["frequencia_semana"] = pd.to_numeric(df["frequencia_semana"], errors="coerce")
    df[["observacao", "cnpj_arquivo"]] = df[["observacao", "cnpj_arquivo"]].fillna("")
    with _trava:
        if versao == _versao:
            _guardado.update(versao=versao, df=df)
    return df.copy()


def cnpjs_atendidos() -> set[str]:
    df = carregar()
    return set(df.loc[df["cnpj"] != "", "cnpj"])
