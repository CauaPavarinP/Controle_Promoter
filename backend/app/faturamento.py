"""Faturamento item a item: pré-visualização, gravação (tudo ou nada), desfazer e consultas.

Fluxo da importação:
1. preparar_previa(): lê o arquivo e devolve um resumo (período, totais, erros, CNPJs sem roteiro,
   meses que já existem). Os itens ficam guardados em memória por 30 minutos.
2. confirmar(): grava os itens numa transação. Meses que já existiam só são substituídos se o
   usuário confirmar (apaga os itens daquele ano/mês e grava os novos).
3. desfazer(): apaga os itens de uma importação.
"""
import json
import re
import logging
import multiprocessing
import os
import pickle
import secrets
import tempfile
import threading
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import and_, delete, func, inspect, literal_column, or_, select, text
from sqlalchemy.orm import Session

from . import db, respostas_guardadas
from .importacao import ErroImportacao, devolver_memoria, ler_faturamento_em_partes, normalizar_texto
from .modelos import FaturamentoItem, Importacao

VALIDADE_PREVIA = 30 * 60
_previas: dict[str, dict] = {}


def _rotulo(ano: int, mes: int) -> str:
    return f"{ano}-{mes:02d}"


# Substituição por EMPRESA (COD EMP) + mês: o relatório do Focco sai por empresa, então importar a empresa 10 não
# pode apagar o que já está gravado da empresa 11 no mesmo mês. "" = sem COD EMP (arquivo sem a coluna ou linha
# vazia): por segurança, conflita com todas as empresas do mês, para nunca contar a mesma venda duas vezes.
_EMPRESA = func.coalesce(FaturamentoItem.cod_emp, "")


def _empresa(valor) -> str:
    """Código da empresa sem variação de formato: 10, "10", "10,00", "10.0" e "010" são a mesma empresa."""
    texto = "" if valor is None or (isinstance(valor, float) and pd.isna(valor)) else str(valor).strip()
    numero = re.fullmatch(r"(\d+)(?:[.,]0+)?", texto)
    return str(int(numero.group(1))) if numero else texto


def periodos_do_arquivo(itens: pd.DataFrame) -> set[tuple[int, int, str]]:
    empresas = itens["cod_emp"].astype(object) if "cod_emp" in itens else pd.Series("", index=itens.index)
    return {(int(a), int(m), _empresa(e)) for a, m, e in zip(itens["ano"], itens["mes"], empresas)}


def periodos_em_conflito(conexao, do_arquivo: set[tuple[int, int, str]]) -> list[tuple[int, int, str, str]]:
    """Empresa + mês já gravados que o arquivo substitui: (ano, mês, empresa normalizada, valor gravado no banco).
    O valor gravado é o que se usa para apagar (pode ser "10,00" num arquivo antigo)."""
    if not do_arquivo:
        return []
    meses = {(a, m) for a, m, _ in do_arquivo}
    gravados = conexao.execute(select(FaturamentoItem.ano, FaturamentoItem.mes, _EMPRESA).distinct()
                               .where(or_(*[and_(FaturamentoItem.ano == a, FaturamentoItem.mes == m)
                                            for a, m in sorted(meses)]))).all()
    conflito = set()
    for a, m, gravado in gravados:
        a, m, e = int(a), int(m), _empresa(gravado)
        if (a, m, e) in do_arquivo or (a, m, "") in do_arquivo or (e == "" and (a, m) in meses):
            conflito.add((a, m, e, gravado))
    return sorted(conflito)


def _filtro_periodos(periodos):
    return or_(*[and_(FaturamentoItem.ano == a, FaturamentoItem.mes == m, _EMPRESA == gravado)
                 for a, m, _e, gravado in periodos])


def rotulo_periodo(ano: int, mes: int, empresa: str) -> str:
    return f"{_rotulo(ano, mes)}" + (f" (empresa {empresa})" if empresa else " (sem empresa)")


# ---------------------------------------------------------------------------
# Itens lidos ficam num arquivo temporário (não na memória) até a confirmação. Arquivo grande é lido e gravado
# num processo separado: ler 317 mil linhas cria milhões de textos pequenos e o Python não devolve toda essa
# memória ao sistema; com 512 MB no servidor gratuito, a 3ª importação seguida derrubava o servidor. O processo
# separado termina no fim e devolve tudo.
# ---------------------------------------------------------------------------

PASTA_PREVIAS = Path(tempfile.gettempdir()) / "controle-promotores-previas"
LIMITE_ARQUIVO_PROCESSO = 5 * 1024 * 1024   # bytes: acima disso a leitura vai para o processo separado
LIMITE_LINHAS_PROCESSO = 50_000             # itens: acima disso a gravação vai para o processo separado


def limpar_pasta_previas() -> None:
    """Ao ligar o servidor: apaga itens de prévias que ficaram de antes (o servidor reiniciou no meio).

    Só os com mais de 1 hora: um arquivo novo pode ser de uma importação ainda em andamento.
    """
    limite = time.time() - 3600
    for arquivo in PASTA_PREVIAS.glob("*") if PASTA_PREVIAS.is_dir() else []:
        try:
            if arquivo.stat().st_mtime < limite:
                arquivo.unlink()
        except OSError:
            pass


def _apagar_arquivo(caminho) -> None:
    try:
        os.remove(caminho)
    except OSError:
        pass


def _descartar_previa(token: str) -> None:
    previa = _previas.pop(token, None)
    if previa is not None:
        _apagar_arquivo(previa["caminho_itens"])


def _descartar_previas() -> None:
    for token in list(_previas):
        _descartar_previa(token)


MAXIMO_ERROS_GUARDADOS = 5000   # linhas com erro guardadas para a tela/Excel (a contagem é sempre a total)


def _partes_gravadas(caminho: str):
    """Lê de volta, uma a uma, as partes que a leitura gravou no disco."""
    with open(caminho, "rb") as arquivo:
        while True:
            try:
                yield pickle.load(arquivo)
            except EOFError:
                return


def _ler_para_arquivo(fonte, nome: str, cnpjs_no_roteiro: set[str], ao_progredir=None) -> dict:
    """Lê o arquivo do ERP aos poucos, grava as partes num arquivo temporário e monta o resumo da prévia.

    Memória constante: cada parte (LINHAS_POR_PARTE linhas) vai para o disco assim que é lida, e da parte só ficam
    os números do resumo (total, meses, empresas, notas, clientes). Por isso não há limite de tamanho de arquivo.
    """
    aba, avisos, partes = ler_faturamento_em_partes(fonte, nome)
    PASTA_PREVIAS.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=PASTA_PREVIAS, suffix=".itens", delete=False) as arquivo:
        caminho_itens = arquivo.name
    linhas = lidas = total_erros = 0
    total, periodos, notas, clientes, erros = 0.0, set(), set(), {}, []
    try:
        with open(caminho_itens, "wb") as saida:
            for numero, (brutas, parte, erros_parte) in enumerate(partes, start=1):
                lidas += brutas
                total_erros += len(erros_parte)
                erros += erros_parte[:max(0, MAXIMO_ERROS_GUARDADOS - len(erros))]
                if not parte.empty:
                    pickle.dump(parte, saida, protocol=pickle.HIGHEST_PROTOCOL)
                    linhas += len(parte)
                    total += float(parte["total_venda"].sum())
                    periodos |= periodos_do_arquivo(parte)
                    notas.update(parte["num_nf"].dropna().unique().tolist())
                    resumo_parte = (parte.groupby("cnpj_cpf", observed=True)
                                    .agg(valor=("total_venda", "sum"), razao_social=("razao_social", "first"),
                                         cidade=("cidade", "first"), uf=("uf", "first")))
                    for cnpj, valor, razao, cidade, uf in resumo_parte.itertuples():
                        cliente = clientes.setdefault(cnpj, [0.0, razao, cidade, uf])
                        cliente[0] += float(valor)
                del parte
                if ao_progredir:
                    ao_progredir(lidas)
                if numero % 10 == 0:
                    devolver_memoria()
    except BaseException:
        _apagar_arquivo(caminho_itens)
        raise
    if not linhas:
        _apagar_arquivo(caminho_itens)
        raise ErroImportacao("O arquivo não tem nenhuma linha válida (com CNPJ, data e valor).")

    meses = sorted({(a, m) for a, m, _ in periodos})
    with db.engine.connect() as conexao:
        conflitos = periodos_em_conflito(conexao, periodos)
    existentes = sorted({(a, m) for a, m, *_ in conflitos})
    empresas = sorted({e for _, _, e in periodos} - {""})
    texto = lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)  # noqa: E731
    sem_roteiro = sorted(((c, d) for c, d in clientes.items() if c not in cnpjs_no_roteiro),
                         key=lambda item: -item[1][0])
    resumo = {
        "arquivo": nome, "aba": aba,
        "linhas_lidas": linhas + total_erros, "linhas_validas": linhas, "linhas_com_erro": total_erros,
        "erros": erros[:100], "avisos": avisos,
        "meses": [_rotulo(a, m) for a, m in meses],
        "meses_existentes": [_rotulo(a, m) for a, m in existentes],
        "empresas": empresas,
        "periodos_existentes": [{"mes": mes, "empresa": e} for mes, e in
                                sorted({(_rotulo(a, m), e) for a, m, e, _g in conflitos})],
        "total_venda": round(total, 2),
        "notas": len(notas),
        "clientes": len(clientes),
        "cnpjs_sem_roteiro": {
            "quantidade": len(sem_roteiro), "valor": round(sum(d[0] for _, d in sem_roteiro), 2),
            "exemplos": [{"cnpj": c, "razao_social": texto(d[1]), "cidade": texto(d[2]), "uf": texto(d[3]),
                          "valor": round(d[0], 2)} for c, d in sem_roteiro[:20]],
        },
    }
    if total_erros > len(erros):
        avisos.append(f"{total_erros} linhas com erro; o histórico guarda as primeiras {len(erros)}.")
    return {"resumo": resumo, "caminho_itens": caminho_itens, "erros": erros, "total_erros": total_erros,
            "avisos": avisos, "linhas": linhas, "periodos": sorted(periodos), "total_venda": round(total, 2)}


def _registrar_previa(lido: dict, nome: str, usuario: str) -> dict:
    """Guarda a prévia lida (só a mais recente) e devolve o resumo com o token para confirmar."""
    _descartar_previas()  # cada prévia segura um arquivo de itens; só a mais recente vale
    token = secrets.token_urlsafe(16)
    _previas[token] = {"criado": time.time(), "caminho_itens": lido["caminho_itens"], "linhas": lido["linhas"],
                       "erros": lido["erros"], "total_erros": lido["total_erros"], "avisos": lido["avisos"],
                       "periodos": lido["periodos"], "total_venda": lido["total_venda"],
                       "arquivo": nome, "usuario": usuario}
    # Prévia não confirmada em 30 minutos é descartada.
    relogio = threading.Timer(VALIDADE_PREVIA, _descartar_previa, args=[token])
    relogio.daemon = True
    relogio.start()
    return {"token": token, **lido["resumo"]}


def preparar_previa(conteudo, nome: str, usuario: str, cnpjs_no_roteiro: set[str], ao_progredir=None) -> dict:
    """Lê aqui mesmo (arquivo pequeno). `conteudo`: bytes do arquivo ou caminho dele no disco."""
    lido = _ler_para_arquivo(conteudo, nome, cnpjs_no_roteiro, ao_progredir)
    try:
        return _registrar_previa(lido, nome, usuario)
    finally:
        devolver_memoria()


# --- Processo separado ------------------------------------------------------

def _rodar_no_filho(funcao, argumentos, contador, caminho_resultado) -> None:
    """Corpo do processo separado: roda `funcao` e grava o resultado (ou o erro) num arquivo."""
    def ao_progredir(linhas):
        contador.value = linhas
    try:
        resultado = {"ok": funcao(*argumentos, ao_progredir=ao_progredir)}
    except ErroImportacao as erro:
        resultado = {"erro_importacao": str(erro)}
    except Exception as erro:  # noqa: BLE001 - o detalhe vai para o log do processo principal
        import traceback
        resultado = {"erro": f"{erro!r}\n{traceback.format_exc()}"}
    Path(caminho_resultado).parent.mkdir(parents=True, exist_ok=True)
    with open(caminho_resultado, "wb") as arquivo:
        pickle.dump(resultado, arquivo)


def _em_processo(funcao, argumentos: tuple, ao_progredir=None):
    """Roda `funcao(*argumentos, ao_progredir=...)` num processo novo e devolve o resultado."""
    soltar_cache()  # ~60 MB a mais de folga enquanto o processo separado trabalha
    contexto = multiprocessing.get_context("spawn")  # processo limpo (fork copiaria travas das outras threads)
    contador = contexto.Value("q", 0)
    PASTA_PREVIAS.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=PASTA_PREVIAS, suffix=".resultado", delete=False) as arquivo:
        caminho_resultado = arquivo.name
    try:
        processo = contexto.Process(target=_rodar_no_filho, args=(funcao, argumentos, contador, caminho_resultado),
                                    daemon=True)
        processo.start()
        while processo.is_alive():
            processo.join(1)
            if ao_progredir:
                ao_progredir(contador.value)
        try:
            with open(caminho_resultado, "rb") as arquivo:
                resultado = pickle.load(arquivo)
        except (OSError, EOFError, pickle.UnpicklingError):
            resultado = None
    finally:
        _apagar_arquivo(caminho_resultado)
    if resultado is None:
        log.error("Processo de importação terminou sem resultado (código %s)", processo.exitcode)
        raise ErroImportacao("A importação parou no meio (provavelmente faltou memória no servidor). "
                             "Tente de novo; se repetir, avise o suporte.")
    if "erro_importacao" in resultado:
        raise ErroImportacao(resultado["erro_importacao"])
    if "erro" in resultado:
        log.error("Erro no processo de importação: %s", resultado["erro"])
        raise RuntimeError("Erro no processo de importação")
    return resultado["ok"]


def _ler_no_filho(caminho: str, nome: str, cnpjs_no_roteiro: set[str], ao_progredir=None) -> dict:
    return _ler_para_arquivo(caminho, nome, cnpjs_no_roteiro, ao_progredir)


# ---------------------------------------------------------------------------
# Leitura em segundo plano: o arquivo grande leva minutos no servidor gratuito (0,15 de processador). A tela
# pergunta o andamento a cada poucos segundos em vez de esperar uma resposta só (que o navegador abandonaria).
# ---------------------------------------------------------------------------

log = logging.getLogger("uvicorn.error")
_leituras: dict[str, dict] = {}


def iniciar_leitura(caminho: str, nome: str, usuario: str, cnpjs_no_roteiro: set[str]) -> str:
    """Começa a ler o arquivo (já salvo no disco) em segundo plano e devolve o código da leitura."""
    agora = time.time()
    for codigo in [c for c, l in _leituras.items() if agora - l["criado"] > 3600]:
        _leituras.pop(codigo, None)
    if any(l["situacao"] == "lendo" for l in _leituras.values()):
        os.remove(caminho)
        raise ErroImportacao("Já tem um arquivo sendo lido. Espere ele terminar para enviar outro.")
    codigo = secrets.token_urlsafe(12)
    estado = _leituras[codigo] = {"situacao": "lendo", "linhas": 0, "criado": agora}

    def progredir(linhas):
        estado["linhas"] = linhas

    def trabalhar():
        try:
            if os.path.getsize(caminho) > LIMITE_ARQUIVO_PROCESSO:
                _descartar_previas()  # libera o disco/memória da prévia anterior antes de ler a nova
                lido = _em_processo(_ler_no_filho, (caminho, nome, cnpjs_no_roteiro), progredir)
                estado["previa"] = _registrar_previa(lido, nome, usuario)
            else:
                estado["previa"] = preparar_previa(caminho, nome, usuario, cnpjs_no_roteiro, ao_progredir=progredir)
            estado["situacao"] = "pronto"
        except ErroImportacao as erro:
            estado.update(situacao="erro", erro=str(erro))
        except Exception:  # noqa: BLE001 - qualquer falha vira mensagem para a tela, com detalhe no log
            log.exception("Erro ao ler o arquivo de faturamento %s", nome)
            estado.update(situacao="erro", erro="Erro inesperado ao ler o arquivo. Confira se é a exportação do ERP.")
        finally:
            _apagar_arquivo(caminho)

    threading.Thread(target=trabalhar, name=f"leitura-{codigo}", daemon=True).start()
    return codigo


def lendo_agora() -> bool:
    return any(l["situacao"] == "lendo" for l in _leituras.values())


def andamento_da_leitura(codigo: str) -> dict:
    estado = _leituras.get(codigo)
    if estado is None:
        raise ErroImportacao("Leitura não encontrada: o servidor reiniciou ou ela foi feita há mais de 1 hora. "
                             "Envie o arquivo de novo.")
    # Leitura terminada continua disponível (até 1 hora): perguntar de novo devolve a mesma resposta.
    if estado["situacao"] == "erro":
        raise ErroImportacao(estado["erro"])
    if estado["situacao"] == "pronto":
        return {**estado["previa"], "situacao": "pronto", "leitura": codigo}
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


def _gravar(previa: dict, substituir: bool, avisos_extra: list[str] | None, ao_progredir=None) -> dict:
    """Grava os itens da prévia numa transação (tudo ou nada). Roda aqui ou no processo separado.

    As partes são lidas do disco e gravadas uma por vez: a memória não cresce com o tamanho do arquivo."""
    periodos = {tuple(p) for p in previa["periodos"]}
    meses = sorted({(a, m) for a, m, _ in periodos})

    with db.engine.begin() as conexao:   # tudo ou nada
        conflitos = periodos_em_conflito(conexao, periodos)
        existentes = sorted({(a, m) for a, m, *_ in conflitos})
        if conflitos and not substituir:
            raise ErroImportacao(
                "Já existe faturamento para " + ", ".join(sorted({rotulo_periodo(a, m, e) for a, m, e, _g in conflitos}))
                + ". Confirme a substituição para continuar.")
        for inicio in range(0, len(conflitos), 200):
            conexao.execute(delete(FaturamentoItem).where(_filtro_periodos(conflitos[inicio:inicio + 200])))
        importacao_id = conexao.execute(
            Importacao.__table__.insert().values(
                tipo="faturamento", arquivo_nome=previa["arquivo"], usuario=previa["usuario"],
                periodos=",".join(_rotulo(a, m) for a, m in meses),
                linhas_lidas=previa["linhas"] + previa["total_erros"], linhas_importadas=previa["linhas"],
                linhas_com_erro=previa["total_erros"], total_venda=previa["total_venda"],
                avisos=json.dumps(previa["avisos"] + (avisos_extra or []), ensure_ascii=False),
                log_erros=json.dumps(previa["erros"], ensure_ascii=False), situacao="ativa")
        ).inserted_primary_key[0]
        gravadas = 0
        for parte in _partes_gravadas(previa["caminho_itens"]):
            _gravar_itens(conexao, parte, importacao_id)
            gravadas += len(parte)
            del parte
            if ao_progredir:
                ao_progredir(gravadas)
        # Importações antigas que ficaram sem nenhum item (todos os meses substituídos).
        conexao.execute(text(
            "UPDATE importacoes SET situacao = 'substituida' WHERE tipo = 'faturamento' AND situacao = 'ativa' "
            "AND id <> :atual AND NOT EXISTS (SELECT 1 FROM faturamento_itens f WHERE f.importacao_id = importacoes.id)"),
            {"atual": importacao_id})
    return {"importacao_id": importacao_id, "linhas_importadas": previa["linhas"],
            "meses": [_rotulo(a, m) for a, m in meses], "meses_substituidos": [_rotulo(a, m) for a, m in existentes],
            "periodos_substituidos": [{"mes": mes, "empresa": e} for mes, e in
                                      sorted({(_rotulo(a, m), e) for a, m, e, _g in conflitos})]}


def confirmar(token: str, substituir: bool, avisos_extra: list[str] | None = None) -> dict:
    previa = _previas.get(token)
    if previa is None:
        raise ErroImportacao("A pré-visualização expirou, já foi usada ou foi trocada por um arquivo lido depois. "
                             "Envie o arquivo de novo.")
    if previa["linhas"] > LIMITE_LINHAS_PROCESSO:
        resultado = _em_processo(_gravar, (previa, substituir, avisos_extra))
    else:
        try:
            resultado = _gravar(previa, substituir, avisos_extra)
        finally:
            devolver_memoria()
    limpar_cache()
    _descartar_previa(token)
    return resultado


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
        # O banco grava em UTC (sem fuso); o "Z" faz o navegador mostrar no horário de Brasília.
        "data_hora": i.criado_em.isoformat() + ("Z" if i.criado_em.tzinfo is None else "") if i.criado_em else None,
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
                  "total_venda", "vlr_total", "notas", "uf"]


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
            entrada["valor"] = None  # solta a soma antiga antes de montar a nova
            entrada["valor"] = calcular()
            entrada["versao"] = versao
            devolver_memoria()
        return entrada["valor"].copy()  # cópia: quem usa pode alterar à vontade


def limpar_cache() -> None:
    """Chamar sempre que faturamento_itens mudar (depois do commit)."""
    global _versao_cache
    with _trava_cache:
        _versao_cache += 1
    respostas_guardadas.dados_mudaram()


def soltar_cache() -> None:
    """Descarta as somas guardadas (sem marcar o faturamento como mudado): libera memória para uma tarefa pesada.

    A próxima tela que precisar refaz a soma.
    """
    with _trava_cache:
        entradas = list(_cache.values())
    for entrada in entradas:
        with entrada["trava"]:
            entrada["valor"] = None
            entrada["versao"] = None
    devolver_memoria()


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
                       func.count(FaturamentoItem.num_nf.distinct()),
                       func.max(FaturamentoItem.uf))  # UF do cliente: diz quais UFs do mês já têm ERP importado
                .group_by(FaturamentoItem.ano, FaturamentoItem.mes, FaturamentoItem.cnpj_cpf, FaturamentoItem.cod_cli,
                          FaturamentoItem.tipo_nf_chave, _RECEITA))
    with db.engine.connect() as conexao:
        linhas = conexao.execute(consulta).all()
    df = pd.DataFrame(linhas, columns=COLUNAS_MENSAL)
    for coluna in ("total_venda", "vlr_total"):
        df[coluna] = df[coluna].astype(float)
    df["uf"] = df["uf"].fillna("")
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
