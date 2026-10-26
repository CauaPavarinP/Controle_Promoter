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
from .importacao import normalizar_texto
from .modelos import CustoPromotor, Pdv, Promotor, Roteiro, RoteiroPendente, Supervisor, Usuario
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
    criados = atualizados = reajustes = 0
    for linha in df.itertuples():
        promotor = sessao.scalar(select(Promotor).where(Promotor.codigo == linha.codigo))
        municipio, uf = separar_municipio(linha.municipio)
        dados = {"nome": linha.nome, "municipio": municipio, "uf": uf,
                 "data_admissao": _data(linha.admissao)}
        supervisor = obter_supervisor(sessao, linha.supervisor)
        if promotor is None:
            promotor = Promotor(codigo=linha.codigo, **dados, supervisor=supervisor)
            sessao.add(promotor)
            criados += 1
        else:
            for campo, valor in dados.items():
                if valor not in (None, ""):
                    setattr(promotor, campo, valor)
            if supervisor is not None:
                promotor.supervisor = supervisor
            atualizados += 1

        salario, ajuda, vt = _numero(linha.salario), _numero(linha.ajuda_custo), _numero(linha.transporte)
        outros = max(0.0, round(_numero(linha.custo_mensal) - (salario + ajuda + vt), 2))
        atual = custo_vigente(promotor, hoje.year, hoje.month) if promotor.custos else None
        valores = (salario, ajuda, vt, outros)
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
    return {"criados": criados, "atualizados": atualizados, "reajustes": reajustes}


def _indice_promotores(sessao: Session) -> dict:
    """Nome normalizado (com e sem espaços) → promotor, para ligar o roteiro pelo nome."""
    indice = {}
    for promotor in sessao.scalars(select(Promotor)):
        nome = normalizar_texto(promotor.nome)
        indice.setdefault(nome, promotor)
        indice.setdefault(nome.replace(" ", ""), promotor)
    return indice


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
    """Cria PDVs e roteiros vigentes a partir da planilha; o que não achar promotor vira pendência."""
    inicio = date(date.today().year, 1, 1)
    por_codigo = {p.codigo: p for p in sessao.scalars(select(Promotor))}
    por_nome = _indice_promotores(sessao)
    sessao.query(RoteiroPendente).delete()
    criados = mantidos = pendentes = 0
    for linha in df.itertuples():
        nome = normalizar_texto(linha.colaborador)
        promotor = (por_codigo.get(linha.codigo_promotor) or por_nome.get(nome)
                    or por_nome.get(nome.replace(" ", "")))
        visitas = None if pd.isna(linha.visitas_semana) else int(linha.visitas_semana)
        if promotor is None:
            sessao.add(RoteiroPendente(colaborador=linha.colaborador or linha.codigo_promotor, cnpj_cpf=linha.cnpj,
                                       loja=linha.loja, cidade=linha.cidade, uf=linha.uf,
                                       visitas_por_semana=visitas, origem=getattr(linha, "aba", origem)))
            pendentes += 1
            continue
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
    return {"criados": criados, "mantidos": mantidos, "pendentes": pendentes}


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
