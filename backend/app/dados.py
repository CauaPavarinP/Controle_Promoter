"""Monta, a partir dos cadastros, as tabelas que o cálculo do painel usa (app/calculos.py)."""
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .modelos import Pdv, Promotor, Roteiro, RoteiroPendente


def _texto_data(data):
    return data.isoformat() if data else ""


def tabelas_do_calculo(sessao: Session) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    promotores = sessao.scalars(
        select(Promotor).options(selectinload(Promotor.custos), selectinload(Promotor.supervisor))).all()
    linhas_promotores, linhas_custos = [], []
    for p in promotores:
        atual = p.custos[-1] if p.custos else None
        linhas_promotores.append({
            "codigo": p.codigo, "nome": p.nome, "admissao": _texto_data(p.data_admissao),
            "desligamento": _texto_data(p.data_desligamento),
            "municipio": f"{p.municipio} - {p.uf}" if p.uf else p.municipio,
            "supervisor": p.supervisor.nome if p.supervisor else "",
            "salario": atual.salario if atual else 0.0,
            "ajuda_custo": atual.ajuda_custo if atual else 0.0,
            "transporte": atual.vale_transporte if atual else 0.0,
            "custo_mensal": atual.total if atual else 0.0,
        })
        linhas_custos += [{"codigo": p.codigo, "ano": c.ano, "mes": c.mes, "total": c.total, "salario": c.salario,
                           "ajuda_custo": c.ajuda_custo, "vale_transporte": c.vale_transporte, "outros": c.outros}
                          for c in p.custos]

    roteiros = sessao.execute(
        select(Roteiro, Promotor.codigo, Pdv).join(Promotor, Roteiro.promotor_id == Promotor.id)
        .join(Pdv, Roteiro.pdv_id == Pdv.id)).all()
    linhas_roteiro = [{
        "codigo_promotor": codigo, "colaborador": "", "cnpj": pdv.cnpj_cpf, "loja": pdv.nome_fantasia,
        "cidade": pdv.cidade, "uf": pdv.uf, "cod_cli": pdv.cod_cli_erp,
        "visitas_semana": r.visitas_por_semana,
        "data_inicio": _texto_data(r.data_inicio), "data_fim": _texto_data(r.data_fim),
    } for r, codigo, pdv in roteiros]

    colunas_promotores = ["codigo", "nome", "admissao", "desligamento", "municipio", "supervisor",
                          "salario", "ajuda_custo", "transporte", "custo_mensal"]
    colunas_roteiro = ["codigo_promotor", "colaborador", "cnpj", "loja", "cidade", "uf", "cod_cli",
                       "visitas_semana", "data_inicio", "data_fim"]
    return (pd.DataFrame(linhas_promotores, columns=colunas_promotores),
            pd.DataFrame(linhas_custos, columns=["codigo", "ano", "mes", "total", "salario", "ajuda_custo",
                                                 "vale_transporte", "outros"]),
            pd.DataFrame(linhas_roteiro, columns=colunas_roteiro))


def colaboradores_pendentes(sessao: Session) -> list[str]:
    nomes = sessao.scalars(select(RoteiroPendente.colaborador).distinct()).all()
    return sorted(n for n in nomes if n)
