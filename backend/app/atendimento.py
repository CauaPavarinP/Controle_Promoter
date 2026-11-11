"""Atendimento das agências: leitura do arquivo (modelo único), prévia, gravação, desfazer e leitura para o cálculo.

Cada linha do arquivo é uma loja atendida num mês por uma agência (ou MEI, ou a própria 101 com promotor CLT):
mês, agência, CNPJ e nome da loja, cidade, UF, promotor, dias de visita, visitas no mês, valor do mês e status.
Lojas, promotores e agências do sistema são montados a partir destas linhas (tabela atendimentos).

Regras da leitura (cada uma vira aviso na prévia, para a agência corrigir no próximo arquivo):
- CNPJ com 14 dígitos fica como está (mesmo com dígito verificador errado: se bater com o ERP, liga); com um zero a
  mais na frente (15 dígitos, ex.: "009.477.652/0042-64") é corrigido quando, sem o zero, fica válido; com 12 ou 13
  dígitos (o Excel comeu o zero) ganha os zeros; o resto fica sem CNPJ (a loja entra, mas sem faturamento).
- Mês de referência: MM/AAAA, AAAA-MM, data do Excel ou "out/2026".
- Valor vazio = 0 (com aviso); valor que não é número = linha com erro (não entra).
- Linha de exemplo do modelo ("EXEMPLO - apague…") e linhas de total (sem loja) são ignoradas.
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
from .importacao import (ErroImportacao, _ler_abas, _mapear_colunas, devolver_memoria, ler_numero,
                         normalizar_texto)
from .modelos import Atendimento, Importacao

APELIDOS = {
    "mes": ["MES DE REFERENCIA", "MES REFERENCIA", "MES", "COMPETENCIA", "REFERENCIA"],
    "agencia": ["AGENCIA OU MEI", "AGENCIA", "EMPRESA", "AGENCIA MEI"],
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
}
OBRIGATORIAS = ("agencia", "cnpj", "loja", "valor")
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
NOMES_MESES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10,
               "NOV": 11, "DEZ": 12}
SEM_PROMOTOR = "Sem promotor informado"
VALIDADE_PREVIA = 30 * 60


# ---------------------------------------------------------------------------------------------------------------
# Campos
# ---------------------------------------------------------------------------------------------------------------

def cnpj_valido(digitos: str) -> bool:
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False

    def dv(base, pesos):
        resto = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return "0" if resto < 2 else str(11 - resto)
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return digitos[12] == dv(digitos[:12], pesos) and digitos[13] == dv(digitos[:13], [6] + pesos)


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
        return digitos, "" if cnpj_valido(digitos) else f"CNPJ {texto[:30]} não confere (dígito verificador)"
    if len(digitos) == 15 and digitos[0] == "0" and cnpj_valido(digitos[1:]):
        return digitos[1:], "corrigido"
    if len(digitos) in (12, 13) and cnpj_valido(digitos.zfill(14)):
        return digitos.zfill(14), "corrigido"
    return "", f"CNPJ {texto[:30] or '(vazio)'} inválido"


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


def _visitas(valor):
    numero = ler_numero(valor)
    if numero is None or numero <= 0:
        return None
    return int(round(numero))


def _status(valor) -> str:
    return "Encerrada" if normalizar_texto(valor).startswith("ENCERR") else "Ativa"


def chave_promotor(agencia_chave: str, codigo: str, nome: str) -> str:
    """Mesmo promotor em arquivos diferentes: pelo código, se a agência informar; senão pelo nome na agência."""
    if codigo:
        return f"{agencia_chave}|cod:{normalizar_texto(codigo)}"
    return f"{agencia_chave}|{normalizar_texto(nome)}"


# ---------------------------------------------------------------------------------------------------------------
# Leitura do arquivo
# ---------------------------------------------------------------------------------------------------------------

def _tabelas(conteudo: bytes, nome_arquivo: str):
    """(aba, linha do cabeçalho no Excel, DataFrame com as colunas renomeadas) das abas que têm o modelo."""
    for aba, ler in _ler_abas(conteudo, nome_arquivo):
        previa = ler(nrows=30)
        melhor = None
        for indice, linha in previa.iterrows():
            mapa = _mapear_colunas(linha.tolist(), APELIDOS)
            if all(c in mapa for c in OBRIGATORIAS) and (melhor is None or len(mapa) > len(melhor[1])):
                melhor = (indice, mapa)
        if melhor is None:
            continue
        cabecalho, mapa = melhor
        dados = ler(skiprows=cabecalho + 1)
        tabela = pd.DataFrame({campo: dados.iloc[:, posicao] if posicao < dados.shape[1]
                               else pd.Series([None] * len(dados), index=dados.index, dtype=object)
                               for campo, posicao in mapa.items()})
        yield aba, cabecalho + 2, tabela


def ler_atendimento(conteudo: bytes, nome_arquivo: str) -> dict:
    """Lê o arquivo da agência. Devolve {linhas: DataFrame, erros: [...], avisos: [...], abas: [...]}."""
    tabelas = list(_tabelas(conteudo, nome_arquivo))
    if not tabelas:
        raise ErroImportacao(
            "Não encontrei a tabela de atendimento. O arquivo precisa ter as colunas Agência ou MEI, CNPJ da loja, "
            "Loja e Valor do mês (use o modelo \"Atendimento das agências\").")
    linhas, erros = [], []
    corrigidos, sem_cnpj, cnpj_nao_confere, sem_valor, sem_promotor, sem_mes_coluna = [], [], [], [], [], False
    for aba, primeira, tabela in tabelas:
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
            agencia = _texto(registro.get("agencia"))
            if not agencia:
                erros.append({"linha": numero, "aba": aba, "motivo": "Agência ou MEI vazio"})
                continue
            mes = ler_mes(registro.get("mes"))
            if mes is None:
                erros.append({"linha": numero, "aba": aba, "motivo": "Mês de referência vazio ou inválido (use MM/AAAA)"})
                continue
            valor_bruto = registro.get("valor")
            if valor_bruto is None or (isinstance(valor_bruto, float) and pd.isna(valor_bruto)) or \
                    _texto(valor_bruto) == "":
                valor = 0.0
                sem_valor.append(loja)
            else:
                valor = ler_numero(valor_bruto)
                if valor is None or valor < 0:
                    erros.append({"linha": numero, "aba": aba, "motivo": f"Valor do mês não é número: {_texto(valor_bruto)[:30]}"})
                    continue
            cnpj, aviso_cnpj = ler_cnpj(registro.get("cnpj"))
            if aviso_cnpj == "corrigido":
                corrigidos.append(loja)
            elif not cnpj:
                sem_cnpj.append(f"{loja} ({aviso_cnpj})")
            elif aviso_cnpj:
                cnpj_nao_confere.append(loja)
            promotor = _texto(registro.get("promotor"))
            if not promotor:
                promotor = SEM_PROMOTOR
                sem_promotor.append(loja)
            codigo = _texto(registro.get("codigo"))
            uf = normalizar_texto(registro.get("uf"))[:2]
            agencia_chave = normalizar_texto(agencia)
            linhas.append({
                "linha": numero, "aba": aba, "ano": mes[0], "mes": mes[1], "agencia": agencia[:150],
                "agencia_chave": agencia_chave[:150], "cnpj": cnpj, "loja": loja[:200],
                "loja_chave": normalizar_texto(loja)[:200], "cidade": _texto(registro.get("cidade"))[:120].upper(),
                "uf": uf if uf in UFS else "", "promotor": promotor[:150], "promotor_codigo": codigo[:40],
                "promotor_chave": chave_promotor(agencia_chave, codigo, promotor)[:200],
                "dias": _texto(registro.get("dias"))[:80], "visitas": _visitas(registro.get("visitas")),
                "valor": round(float(valor), 2), "status": _status(registro.get("status")),
                "observacao": observacao[:2000],
            })
    if not linhas:
        raise ErroImportacao("O arquivo não tem nenhuma linha válida de atendimento."
                             + (f" Primeiro erro: {erros[0]['motivo']} ({erros[0]['aba']}, linha {erros[0]['linha']})."
                                if erros else ""))
    df = pd.DataFrame(linhas)

    # Cada loja aparece uma vez em cada aviso (o arquivo pode ter vários meses da mesma loja).
    corrigidos, sem_cnpj, cnpj_nao_confere, sem_valor, sem_promotor = (
        list(dict.fromkeys(lista)) for lista in (corrigidos, sem_cnpj, cnpj_nao_confere, sem_valor, sem_promotor))
    avisos = []
    if sem_mes_coluna:
        avisos.append("Uma aba não tem a coluna \"Mês de referência\": as linhas dela entraram como erro.")
    if corrigidos:
        avisos.append(f"{len(corrigidos)} CNPJ(s) com zero a mais na frente ou zero faltando foram corrigidos: "
                      + ", ".join(corrigidos[:8]) + (" …" if len(corrigidos) > 8 else ""))
    if sem_cnpj:
        avisos.append(f"{len(sem_cnpj)} loja(s) sem CNPJ válido entraram sem faturamento (corrija no próximo "
                      "arquivo): " + "; ".join(sem_cnpj[:8]) + (" …" if len(sem_cnpj) > 8 else ""))
    if cnpj_nao_confere:
        avisos.append(f"{len(cnpj_nao_confere)} CNPJ(s) com dígito verificador que não confere (confira com a "
                      "agência): " + "; ".join(cnpj_nao_confere[:8]) + (" …" if len(cnpj_nao_confere) > 8 else ""))
    if sem_valor:
        avisos.append(f"{len(sem_valor)} loja(s) sem valor entraram com R$ 0,00: " + "; ".join(sem_valor[:8])
                      + (" …" if len(sem_valor) > 8 else ""))
    if sem_promotor:
        avisos.append(f"{len(sem_promotor)} loja(s) sem promotor ficaram como \"{SEM_PROMOTOR}\": "
                      + "; ".join(sem_promotor[:8]) + (" …" if len(sem_promotor) > 8 else ""))
    repetidas = df[df.duplicated(["agencia_chave", "ano", "mes", "cnpj", "loja_chave", "promotor_chave"], keep=False)]
    if not repetidas.empty:
        avisos.append(f"{len(repetidas)} linha(s) repetidas (mesma agência, mês, loja e promotor): os valores foram "
                      "somados. Confira se não é a mesma loja duas vezes: " + ", ".join(repetidas["loja"].head(6)))
    avisos += _nomes_parecidos(df)
    return {"linhas": df, "erros": erros, "avisos": avisos, "abas": sorted({a for a, _, _ in tabelas})}


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


def preparar_previa(conteudo: bytes, nome_arquivo: str, usuario: str) -> dict:
    lido = ler_atendimento(conteudo, nome_arquivo)
    df = lido["linhas"]
    grupos = df.groupby(["agencia_chave", "ano", "mes"])
    with db.engine.connect() as conexao:
        existentes = _grupos_existentes(conexao, {(a, int(y), int(m)) for a, y, m in grupos.groups})
    resumo = []
    for (chave, ano, mes), grupo in grupos:
        resumo.append({"agencia": grupo["agencia"].iloc[0], "mes": _rotulo(int(ano), int(mes)),
                       "lojas": int(grupo["loja_chave"].nunique()), "promotores": int(grupo["promotor_chave"].nunique()),
                       "visitas": int(grupo["visitas"].fillna(0).sum()), "valor": round(float(grupo["valor"].sum()), 2),
                       "ja_existe": (chave, int(ano), int(mes)) in existentes})
    token = secrets.token_urlsafe(16)
    with _trava:
        agora = time.time()
        for velho in [t for t, p in _previas.items() if agora - p["criado"] > VALIDADE_PREVIA]:
            _previas.pop(velho, None)
        _previas[token] = {"criado": agora, "linhas": df, "erros": lido["erros"], "avisos": lido["avisos"],
                           "arquivo": nome_arquivo, "usuario": usuario}
    return {"token": token, "arquivo": nome_arquivo, "abas": lido["abas"], "grupos": resumo,
            "linhas_validas": len(df), "linhas_com_erro": len(lido["erros"]), "erros": lido["erros"][:100],
            "avisos": lido["avisos"], "valor_total": round(float(df["valor"].sum()), 2),
            "lojas": int(df[["cnpj", "loja_chave"]].drop_duplicates().shape[0]),
            "promotores": int(df["promotor_chave"].nunique()),
            "substituir": [f"{g['agencia']} {g['mes']}" for g in resumo if g["ja_existe"]]}


def confirmar(token: str, substituir: bool) -> dict:
    with _trava:
        previa = _previas.get(token)
    if previa is None:
        raise ErroImportacao("A pré-visualização expirou ou já foi usada. Envie o arquivo de novo.")
    df: pd.DataFrame = previa["linhas"]
    # Linhas repetidas (mesma agência, mês, loja e promotor) viram uma, com os valores somados.
    chaves = ["agencia_chave", "ano", "mes", "cnpj", "loja_chave", "promotor_chave"]
    df = (df.groupby(chaves, as_index=False, sort=False)
            .agg({**{c: "first" for c in df.columns if c not in chaves and c != "valor" and c != "visitas"},
                  "valor": "sum", "visitas": lambda v: int(v.sum()) if v.notna().any() else None}))
    grupos = {(a, int(y), int(m)) for a, y, m in df[["agencia_chave", "ano", "mes"]].itertuples(index=False)}
    meses = sorted({_rotulo(int(y), int(m)) for _, y, m in grupos})
    with db.engine.begin() as conexao:
        existentes = _grupos_existentes(conexao, grupos)
        if existentes and not substituir:
            raise ErroImportacao("Já existe atendimento importado para " + ", ".join(
                f"{df[df['agencia_chave'] == a]['agencia'].iloc[0]} {_rotulo(y, m)}" for a, y, m in sorted(existentes))
                + ". Confirme a substituição para continuar.")
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
                "ano", "mes", "agencia", "agencia_chave", "cnpj", "loja", "loja_chave", "cidade", "uf", "promotor",
                "promotor_codigo", "promotor_chave", "dias", "valor", "status", "observacao", "linha")}
                | {"importacao_id": importacao_id,
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
                             for a, y, m in sorted(existentes)]}


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

COLUNAS = ["ano", "mes", "agencia", "agencia_chave", "cnpj", "loja", "loja_chave", "cidade", "uf", "promotor",
           "promotor_codigo", "promotor_chave", "dias", "visitas", "valor", "status"]
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
    with _trava:
        if versao == _versao:
            _guardado.update(versao=versao, df=df)
    return df.copy()


def cnpjs_atendidos() -> set[str]:
    df = carregar()
    return set(df.loc[df["cnpj"] != "", "cnpj"])
