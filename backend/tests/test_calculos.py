import pandas as pd
import pytest

from app.calculos import Filtros, calcular_painel, meses_de_custo
from app.importacao import converter_numero, normalizar_cnpj
from app.regras import REGRAS_PADRAO, validar_regras



def _venda(ano, mes, cnpj, valor, notas=1, tipo="1-Venda"):
    from app.importacao import normalizar_texto
    return {"ano": ano, "mes": mes, "cnpj": cnpj, "chave_tipo": normalizar_texto(tipo), "tipo_nf": tipo,
            "cod_cliente": "", "razao_social": "", "cidade": "", "uf": "", "valor": valor, "notas": notas}


def _dados():
    promotores = pd.DataFrame([
        {"codigo": "1", "nome": "Ana", "admissao": "2025-01-10", "municipio": "TIJUCAS - SC",
         "supervisor": "Vanessa", "salario": 800.0, "ajuda_custo": 0, "transporte": 0, "custo_mensal": 1000.0},
        {"codigo": "2", "nome": "Bruno", "admissao": "2026-03-15", "municipio": "CURITIBA - PR",
         "supervisor": "Lionis", "salario": 0, "ajuda_custo": 0, "transporte": 0, "custo_mensal": 2000.0},
    ])
    roteiro = pd.DataFrame([
        {"codigo_promotor": "", "colaborador": "ANA", "cnpj": "111", "loja": "REDE - A",
         "cidade": "TIJUCAS", "uf": "SC", "visitas_semana": 3},
        {"codigo_promotor": "", "colaborador": "ANA", "cnpj": "111", "loja": "REDE - B",
         "cidade": "TIJUCAS", "uf": "SC", "visitas_semana": 1},
        {"codigo_promotor": "1", "colaborador": "", "cnpj": "222", "loja": "SEM COMPRA",
         "cidade": "PORTO BELO", "uf": "SC", "visitas_semana": None},
        {"codigo_promotor": "2", "colaborador": "", "cnpj": "333", "loja": "OUTRA",
         "cidade": "CURITIBA", "uf": "PR", "visitas_semana": 1},
    ])
    faturamento = pd.DataFrame([
        _venda(2026, 1, "111", 10000.0, 2),
        _venda(2026, 4, "111", 5000.0),
        _venda(2026, 2, "333", 8000.0),
        _venda(2025, 1, "111", 99999.0, 9),
        _venda(2026, 4, "111", 2000.0, tipo="Devolucao"),
    ])
    return faturamento, promotores, roteiro


SO_VENDA = {"tipos_nf": {"1 VENDA": "soma"}, "tipos_nf_padrao": "ignora"}


def test_acumulado_conta_cnpj_compartilhado_uma_vez():
    fat, prom, rot = _dados()
    painel = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-06", supervisor="Vanessa"), SO_VENDA)
    ana = painel["promotores"][0]
    assert ana["faturamento"] == 15000.0          # rede com 2 lojas no mesmo CNPJ conta uma vez
    assert ana["custo_periodo"] == 6000.0         # 6 meses × 1000
    assert ana["lojas"] == 3
    assert ana["percentual_custo"] == 40.0
    assert painel["resumo"]["faturamento"] == 15000.0
    assert painel["resumo"]["cnpjs_compartilhados"] == 1
    lojas_rede = [l for l in painel["lojas"] if l["cnpj"] == "111"]
    # Cada loja da rede fica com a sua parte do CNPJ; somadas, dão o valor do CNPJ (não 2 × 15.000).
    assert all(l["faturamento"] == 7500.0 and l["compartilhado"] for l in lojas_rede)
    assert all(l["percentual_custo"] is None for l in lojas_rede)  # % não faz sentido com valor da rede


def test_devolucao_descontada_quando_configurado():
    fat, prom, rot = _dados()
    regras = {"tipos_nf": {"1 VENDA": "soma", "DEVOLUCAO": "subtrai"}}
    painel = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-06", supervisor="Vanessa"), regras)
    assert painel["resumo"]["faturamento"] == 13000.0


def test_padrao_soma_todos_os_tipos_como_a_planilha():
    fat, prom, rot = _dados()
    painel = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-06", supervisor="Vanessa"))
    assert painel["resumo"]["faturamento"] == 17000.0   # 10.000 + 5.000 + 2.000 da linha "Devolucao"


def test_coluna_de_valor_e_somente_receita():
    prom, rot = _dados()[1:]
    fat = pd.DataFrame([
        {"ano": 2026, "mes": 1, "cnpj": "111", "cod_cliente": "", "chave_tipo": "1 VENDA", "tipo_nf": "1-Venda",
         "receita": "SIM", "total_venda": 1000.0, "vlr_total": 900.0, "notas": 1},
        {"ano": 2026, "mes": 1, "cnpj": "111", "cod_cliente": "", "chave_tipo": "BONIF", "tipo_nf": "Bonif",
         "receita": "NAO", "total_venda": 100.0, "vlr_total": 100.0, "notas": 1},
    ])
    filtros = Filtros("2026-01", "2026-01", promotor="1")
    assert calcular_painel(fat, prom, rot, filtros)["resumo"]["faturamento"] == 1100.0
    assert calcular_painel(fat, prom, rot, filtros, {"valor_faturamento": "vlr_total"})["resumo"]["faturamento"] == 1000.0
    assert calcular_painel(fat, prom, rot, filtros, {"somente_receita": True})["resumo"]["faturamento"] == 1000.0


def test_mesmo_cnpj_separado_pelo_cod_cli():
    prom = _dados()[1]
    rot = pd.DataFrame([
        {"codigo_promotor": "1", "colaborador": "", "cnpj": "999", "loja": "LOJA A", "cidade": "X", "uf": "SC",
         "visitas_semana": None, "cod_cli": "A1"},
        {"codigo_promotor": "1", "colaborador": "", "cnpj": "999", "loja": "LOJA B", "cidade": "X", "uf": "SC",
         "visitas_semana": None, "cod_cli": "B2"},
    ])
    fat = pd.DataFrame([_venda(2026, 1, "999", 700.0) | {"cod_cliente": "A1"},
                        _venda(2026, 1, "999", 300.0) | {"cod_cliente": "B2"}])
    painel = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-01"))
    assert {l["loja"]: l["faturamento"] for l in painel["lojas"]} == {"LOJA A": 700.0, "LOJA B": 300.0}
    assert all(l["separado_por_cod_cli"] and not l["compartilhado"] for l in painel["lojas"])
    assert painel["resumo"]["faturamento"] == 1000.0

    # Sem COD CLI numa das lojas: não dá para separar, o CNPJ é compartilhado e conta uma vez.
    rot.loc[1, "cod_cli"] = ""
    painel = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-01"))
    assert [l["faturamento"] for l in painel["lojas"]] == [500.0, 500.0]
    assert painel["resumo"]["faturamento"] == 1000.0
    assert all(l["compartilhado"] for l in painel["lojas"])
    assert painel["resumo"]["faturamento"] == 1000.0


def test_mes_unico_e_outro_ano_nao_entram():
    fat, prom, rot = _dados()
    painel = calcular_painel(fat, prom, rot, Filtros("2026-02", "2026-02", supervisor="Vanessa"))
    assert painel["resumo"]["faturamento"] == 0
    assert painel["resumo"]["custo"] == 1000.0


def test_custo_comeca_na_admissao():
    assert meses_de_custo("2026-03-15", 2026 * 12, 2026 * 12 + 8) == 7   # mar a set
    assert meses_de_custo("2027-01-01", 2026 * 12, 2026 * 12 + 8) == 0
    assert meses_de_custo("", 2026 * 12, 2026 * 12 + 8) == 9


def test_rateio_do_custo_por_loja():
    fat, prom, rot = _dados()
    filtros = Filtros("2026-01", "2026-01", promotor="1")
    igual = calcular_painel(fat, prom, rot, filtros, {"rateio_custo": "igual"})
    assert sorted(l["custo_periodo"] for l in igual["lojas"]) == [333.33, 333.33, 333.33]
    # Por visitas só vale quando todas as lojas do promotor têm visitas; aqui falta uma → igual.
    sem_visita = calcular_painel(fat, prom, rot, filtros, {"rateio_custo": "visitas"})
    assert sorted(l["custo_periodo"] for l in sem_visita["lojas"]) == [333.33, 333.33, 333.33]
    rot.loc[rot["loja"] == "SEM COMPRA", "visitas_semana"] = 1
    por_visita = calcular_painel(fat, prom, rot, filtros, {"rateio_custo": "visitas"})
    loja_a = next(l for l in por_visita["lojas"] if l["loja"] == "REDE - A")
    assert loja_a["custo_periodo"] == 600.0                 # 3 das 5 visitas (exemplo do documento, seção 8.7)


def test_faturamento_por_visita():
    fat, prom, rot = _dados()
    prom.loc[prom["codigo"] == "2", "admissao"] = "2026-01-05"  # contratado em fevereiro
    rot.loc[rot["loja"] == "SEM COMPRA", "visitas_semana"] = 1
    painel = calcular_painel(fat, prom, rot, Filtros("2026-02", "2026-02", promotor="2"))
    outra = next(l for l in painel["lojas"] if l["loja"] == "OUTRA")
    assert outra["faturamento_por_visita"] == round(8000 / (1 * 52 / 12), 2)


def test_filtro_por_uf_mostra_so_promotores_do_local():
    fat, prom, rot = _dados()
    painel = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-09", uf="PR"))
    assert [p["nome"] for p in painel["promotores"]] == ["Bruno"]
    assert painel["promotores"][0]["custo_periodo"] == 14000.0  # mar a set = 7 meses


def test_validacao_das_regras():
    assert validar_regras({}) == REGRAS_PADRAO
    assert REGRAS_PADRAO["limite_percentual"] is None   # o documento pede o limite sem valor fixo
    assert validar_regras({"limite_percentual": "25"})["limite_percentual"] == 25.0
    with pytest.raises(ValueError):
        validar_regras({"limite_percentual": "abc"})
    with pytest.raises(ValueError):
        validar_regras({"rateio_custo": "outro"})
    with pytest.raises(ValueError):
        validar_regras({"tipos_nf": {"1 VENDA": "dobra"}})


def test_conversoes():
    assert normalizar_cnpj("06.124.533/0001-61") == "06124533000161"
    assert normalizar_cnpj(6124533000161) == "06124533000161"
    assert converter_numero("R$ 1.234,56") == 1234.56
    assert converter_numero(" - ") == 0.0
    assert converter_numero(99.5) == 99.5
