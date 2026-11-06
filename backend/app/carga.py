"""Carga das planilhas nos cadastros (idempotente: rodar de novo não duplica nada).

- Promotores (aba PROMOTORES BRASIL) → supervisores, promotores e custos por competência.
- Roteiro (abas SC, SP, PR…) → PDVs e roteiros. Colaborador que não bate com nenhum
  promotor vira pendência (roteiro_pendencias), sem vínculo inventado.
- Na inicialização: converte os dados das versões antigas e cria o primeiro administrador.
"""
import logging
import re
from datetime import date

import pandas as pd
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from . import db
from .config import APP_SENHA, APP_USUARIO
from .importacao import LIMITE_CUSTO_MENSAL, normalizar_texto
from .modelos import (ApelidoColaborador, CustoPromotor, Pdv, Promotor, Roteiro, RoteiroPendente, Supervisor,
                      Usuario)
from .seguranca import gerar_hash

log = logging.getLogger("uvicorn.error")


def separar_municipio(texto: str) -> tuple[str, str]:
    """'TIJUCAS - SC' -> ('TIJUCAS', 'SC')."""
    texto = (texto or "").strip()
    achado = re.match(r"^(.*?)\s*-\s*([A-Za-z]{2})$", texto)
    return (achado.group(1).strip(), achado.group(2).upper()) if achado else (texto, "")


def _data(valor) -> date | None:
    if valor is None or valor == "" or (isinstance(valor, float) and pd.isna(valor)):
        return None
    data = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(data) else data.date()


def _numero(valor) -> float:
    try:
        return 0.0 if valor is None or pd.isna(valor) else float(valor)
    except (TypeError, ValueError):
        return 0.0


def obter_supervisor(sessao: Session, nome: str) -> Supervisor | None:
    nome = (nome or "").strip()
    if not nome or nome.upper() in ("#N/D", "#N/A", "(VAZIO)"):
        return None
    supervisor = sessao.scalar(select(Supervisor).where(func.lower(Supervisor.nome) == nome.lower()))
    if supervisor is None:
        supervisor = Supervisor(nome=nome)
        sessao.add(supervisor)
        sessao.flush()
    return supervisor


def custo_vigente(promotor: Promotor, ano: int, mes: int) -> CustoPromotor | None:
    vigentes = [c for c in promotor.custos if (c.ano, c.mes) <= (ano, mes)]
    return vigentes[-1] if vigentes else None


def aplicar_promotores(sessao: Session, df: pd.DataFrame) -> dict:
    """Cria ou atualiza promotores a partir da planilha. Custo novo vira reajuste no mês atual."""
    hoje = date.today()
    criados = atualizados = reajustes = corrigidos = 0
    for linha in df.itertuples():
        promotor = sessao.scalar(select(Promotor).where(Promotor.codigo == linha.codigo))
        municipio, uf = separar_municipio(linha.municipio)
        uf = uf or str(getattr(linha, "uf", "") or "").strip().upper()[:2]
        dados = {"nome": linha.nome, "municipio": municipio, "uf": uf,
                 "data_admissao": _data(linha.admissao)}
        # A planilha só sabe dizer "é supervisor"; Promotor/Repositor escolhido na tela não é sobrescrito.
        supervisor_na_lista = getattr(linha, "funcao", "") == "Supervisor"
        supervisor = obter_supervisor(sessao, linha.supervisor)
        if promotor is None:
            promotor = Promotor(codigo=linha.codigo, **dados, supervisor=supervisor,
                                funcao="Supervisor" if supervisor_na_lista else "Promotor")
            sessao.add(promotor)
            criados += 1
        else:
            for campo, valor in dados.items():
                if valor not in (None, ""):
                    setattr(promotor, campo, valor)
            if supervisor is not None:
                promotor.supervisor = supervisor
            if supervisor_na_lista:
                promotor.funcao = "Supervisor"
            atualizados += 1

        salario, ajuda, vt = _numero(linha.salario), _numero(linha.ajuda_custo), _numero(linha.transporte)
        outros = max(0.0, round(_numero(linha.custo_mensal) - (salario + ajuda + vt), 2))
        atual = custo_vigente(promotor, hoje.year, hoje.month) if promotor.custos else None
        valores = (salario, ajuda, vt, outros)
        # Custo gravado errado por versão anterior (ex.: "600 + 120m" lido como 600120): corrige no lugar,
        # em vez de virar reajuste a partir de hoje (o valor errado ficaria nos meses anteriores).
        errados = [c for c in promotor.custos if _custo_absurdo(c)]
        # "600 + 120m" que a versão anterior gravou como 0: corrige no lugar também (valia desde o início).
        campos_em_texto = str(getattr(linha, "custo_em_texto", "") or "").split()
        if campos_em_texto:
            errados += [c for c in promotor.custos if c not in errados
                        and all(not getattr(c, _CAMPO_CUSTO[campo]) for campo in campos_em_texto)]
        if errados:
            for custo in errados:
                custo.salario, custo.ajuda_custo, custo.vale_transporte, custo.outros = valores
            corrigidos += len(errados)
            continue
        if atual is not None and (atual.salario, atual.ajuda_custo, atual.vale_transporte, atual.outros) == valores:
            continue
        if atual is None:
            # Primeiro custo: vale desde a admissão (sem histórico anterior na planilha).
            inicio = promotor.data_admissao or date(hoje.year, 1, 1)
            ano, mes = inicio.year, inicio.month
        else:
            ano, mes = hoje.year, hoje.month
            reajustes += 1
        existente = next((c for c in promotor.custos if (c.ano, c.mes) == (ano, mes)), None)
        if existente is None:
            existente = CustoPromotor(ano=ano, mes=mes)
            promotor.custos.append(existente)
        existente.salario, existente.ajuda_custo, existente.vale_transporte, existente.outros = valores
    sessao.commit()
    return {"criados": criados, "atualizados": atualizados, "reajustes": reajustes,
            "custos_corrigidos": corrigidos}


_CAMPO_CUSTO = {"salario": "salario", "ajuda_custo": "ajuda_custo", "transporte": "vale_transporte"}


def _custo_absurdo(custo: CustoPromotor) -> bool:
    return any(v is not None and (v < 0 or v > LIMITE_CUSTO_MENSAL)
               for v in (custo.salario, custo.ajuda_custo, custo.vale_transporte, custo.outros))


def _indice_promotores(sessao: Session) -> dict:
    """Nome normalizado (com e sem espaços) → lista de promotores com esse nome (pode haver homônimos)."""
    indice = {}
    for promotor in sessao.scalars(select(Promotor).order_by(Promotor.id)):
        nome = normalizar_texto(promotor.nome)
        for chave in {nome, nome.replace(" ", "")}:
            lista = indice.setdefault(chave, [])
            if promotor not in lista:
                lista.append(promotor)
    return indice


def escolher_promotor(codigo: str, colaborador: str, uf: str, por_codigo: dict, por_nome: dict,
                      apelidos: dict) -> tuple[Promotor | None, str]:
    """Promotor de uma linha do roteiro. Devolve (promotor, motivo); sem promotor, o motivo diz por quê.

    - Nome e código juntos precisam concordar: código de outra pessoa não liga a loja (antes o código
      ganhava do nome e a loja ia para quem tinha aquele número).
    - Nome repetido (homônimos): usa o da mesma UF da loja; se não der para decidir, fica pendente.
    """
    nome = normalizar_texto(colaborador)
    pelo_codigo = por_codigo.get(codigo) if codigo else None
    candidatos = (por_nome.get(nome) or por_nome.get(nome.replace(" ", ""))) if nome else None
    if not candidatos and nome in apelidos:
        candidatos = [apelidos[nome]]
    candidatos = candidatos or []
    if pelo_codigo is not None and (not nome or pelo_codigo in candidatos):
        return pelo_codigo, ""
    if pelo_codigo is not None and not candidatos:
        return None, f"código {codigo} é de {pelo_codigo.nome}, não de {colaborador}"
    if len(candidatos) == 1:
        return candidatos[0], ""
    if len(candidatos) > 1:
        mesma_uf = [p for p in candidatos if uf and (p.uf or "").upper() == uf.upper()]
        if len(mesma_uf) == 1:
            return mesma_uf[0], ""
        return None, "nome repetido em mais de um promotor"
    return None, "nome não encontrado"


def obter_pdv(sessao: Session, cnpj: str, nome: str, cidade: str = "", uf: str = "") -> Pdv:
    chave = normalizar_texto(nome)
    pdv = sessao.scalar(select(Pdv).where(Pdv.cnpj_cpf == cnpj, Pdv.nome_chave == chave))
    if pdv is None:
        pdv = Pdv(cnpj_cpf=cnpj, nome_fantasia=nome.strip(), nome_chave=chave, cidade=cidade, uf=uf)
        sessao.add(pdv)
        sessao.flush()
    else:
        pdv.cidade = pdv.cidade or cidade
        pdv.uf = pdv.uf or uf
    return pdv


def aplicar_roteiro(sessao: Session, df: pd.DataFrame, origem: str = "importação") -> dict:
    """Cria PDVs e roteiros vigentes a partir da planilha; o que não achar promotor vira pendência.

    A planilha não tem data: o vínculo começa em 01/01 do ano corrente ou na admissão do promotor, o que
    for depois (antes, começava em 01/01 mesmo para quem foi admitido depois).
    """
    comeco_do_ano = date(date.today().year, 1, 1)
    por_codigo = {p.codigo: p for p in sessao.scalars(select(Promotor))}
    por_nome = _indice_promotores(sessao)
    # Nomes já ligados antes no quadro "Colaboradores não encontrados".
    apelidos = {a.nome_chave: a.promotor for a in sessao.scalars(select(ApelidoColaborador))}
    sessao.query(RoteiroPendente).delete()
    criados = mantidos = pendentes = desligados = 0
    uf_diferente = []
    for linha in df.itertuples():
        promotor, motivo = escolher_promotor(linha.codigo_promotor, linha.colaborador, linha.uf, por_codigo,
                                             por_nome, apelidos)
        visitas = None if pd.isna(linha.visitas_semana) else int(linha.visitas_semana)
        if promotor is None:
            sessao.add(RoteiroPendente(colaborador=linha.colaborador or linha.codigo_promotor, cnpj_cpf=linha.cnpj,
                                       loja=linha.loja, cidade=linha.cidade, uf=linha.uf,
                                       visitas_por_semana=visitas, origem=getattr(linha, "aba", origem)))
            pendentes += 1
            continue
        inicio = max(comeco_do_ano, promotor.data_admissao or comeco_do_ano)
        if promotor.data_desligamento and promotor.data_desligamento < inicio:
            desligados += 1
            continue
        if promotor.uf and linha.uf and promotor.uf.upper() != linha.uf.upper():
            uf_diferente.append(f"{promotor.nome} ({promotor.uf}) → {linha.loja} ({linha.uf})")
        pdv = obter_pdv(sessao, linha.cnpj, linha.loja, linha.cidade, linha.uf)
        vigente = sessao.scalar(select(Roteiro).where(
            Roteiro.promotor_id == promotor.id, Roteiro.pdv_id == pdv.id, Roteiro.data_fim.is_(None)))
        if vigente is None:
            sessao.add(Roteiro(promotor_id=promotor.id, pdv_id=pdv.id, data_inicio=inicio,
                               visitas_por_semana=visitas))
            criados += 1
        else:
            if visitas is not None:
                vigente.visitas_por_semana = visitas
            mantidos += 1
        sessao.flush()
    sessao.commit()
    avisos = []
    if desligados:
        avisos.append(f"{desligados} loja(s) de promotor já desligado ficaram de fora.")
    if uf_diferente:
        avisos.append(f"{len(uf_diferente)} loja(s) numa UF diferente da UF do promotor (confira se o vínculo está "
                      "certo): " + "; ".join(uf_diferente[:5]) + (" …" if len(uf_diferente) > 5 else ""))
    return {"criados": criados, "mantidos": mantidos, "pendentes": pendentes, "uf_diferente": len(uf_diferente),
            "avisos": avisos}


def migrar_legado(sessao: Session) -> None:
    """Converte a planilha importada pelas versões antigas, uma única vez."""
    if db.ler_configuracao("legado_migrado", False):
        return
    tabelas = inspect(db.engine)
    if tabelas.has_table("legado_promotores") and sessao.scalar(select(func.count(Promotor.id))) == 0:
        resultado = aplicar_promotores(sessao, db.ler_tabela("legado_promotores").fillna(""))
        log.info("Promotores convertidos da versão anterior: %s", resultado)
    if tabelas.has_table("legado_roteiro") and sessao.scalar(select(func.count(Roteiro.id))) == 0:
        legado = db.ler_tabela("legado_roteiro")
        legado[["codigo_promotor", "colaborador", "cnpj", "loja", "cidade", "uf"]] = (
            legado[["codigo_promotor", "colaborador", "cnpj", "loja", "cidade", "uf"]].fillna(""))
        resultado = aplicar_roteiro(sessao, legado, "versão anterior")
        log.info("Roteiro convertido da versão anterior: %s", resultado)
    db.gravar_configuracao("legado_migrado", True)


def criar_primeiro_admin(sessao: Session) -> None:
    """Sem nenhum usuário, cria o administrador com APP_USUARIO/APP_SENHA do .env."""
    if sessao.scalar(select(func.count(Usuario.id))):
        return
    if not APP_USUARIO or not APP_SENHA:
        log.warning("Nenhum usuário cadastrado e APP_USUARIO/APP_SENHA vazios: ninguém conseguirá entrar.")
        return
    sessao.add(Usuario(nome=APP_USUARIO, usuario=APP_USUARIO.lower(), senha_hash=gerar_hash(APP_SENHA),
                       perfil="admin"))
    sessao.commit()
    log.info("Administrador inicial '%s' criado a partir do .env.", APP_USUARIO)


def preparar_banco() -> None:
    db.aplicar_migrations()
    with db.SessaoLocal() as sessao:
        criar_primeiro_admin(sessao)
        migrar_legado(sessao)
