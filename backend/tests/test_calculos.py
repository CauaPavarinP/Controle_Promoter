import pandas as pd

from app.calculos import Filtros, calcular_painel, meses_de_custo
from app.importacao import converter_numero, normalizar_cnpj


def _dados():
    promotores = pd.DataFrame([
        {"codigo": "1", "nome": "Ana", "admissao": "2025-01-10", "municipio": "TIJUCAS - SC",
         "supervisor": "Vanessa", "salario": 0, "ajuda_custo": 0, "transporte": 0, "custo_mensal": 1000.0},
        {"codigo": "2", "nome": "Bruno", "admissao": "2026-03-15", "municipio": "CURITIBA - PR",
         "supervisor": "Lionis", "salario": 0, "ajuda_custo": 0, "transporte": 0, "custo_mensal": 2000.0},
    ])
    roteiro = pd.DataFrame([
        {"codigo_promotor": "", "colaborador": "ANA", "cnpj": "111", "loja": "REDE - A",
         "cidade": "TIJUCAS", "uf": "SC", "visitas_semana": 3},
        {"codigo_promotor": "", "colaborador": "ANA", "cnpj": "111", "loja": "REDE - B",
         "cidade": "TIJUCAS", "uf": "SC", "visitas_semana": 2},
        {"codigo_promotor": "1", "colaborador": "", "cnpj": "222", "loja": "SEM COMPRA",
         "cidade": "PORTO BELO", "uf": "SC", "visitas_semana": None},
        {"codigo_promotor": "2", "colaborador": "", "cnpj": "333", "loja": "OUTRA",
         "cidade": "CURITIBA", "uf": "PR", "visitas_semana": 1},
    ])
    faturamento = pd.DataFrame([
        {"ano": 2026, "mes": 1, "cnpj": "111", "cod_cliente": "", "razao_social": "", "cidade": "", "uf": "",
         "valor": 10000.0, "notas": 2},
        {"ano": 2026, "mes": 4, "cnpj": "111", "cod_cliente": "", "razao_social": "", "cidade": "", "uf": "",
         "valor": 5000.0, "notas": 1},
        {"ano": 2026, "mes": 2, "cnpj": "333", "cod_cliente": "", "razao_social": "", "cidade": "", "uf": "",
         "valor": 8000.0, "notas": 1},
        {"ano": 2025, "mes": 1, "cnpj": "111", "cod_cliente": "", "razao_social": "", "cidade": "", "uf": "",
         "valor": 99999.0, "notas": 9},
    ])
    return faturamento, promotores, roteiro


def test_acumulado_conta_cnpj_compartilhado_uma_vez():
    fat, prom, rot = _dados()
    painel = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-06", supervisor="Vanessa"))
    ana = painel["promotores"][0]
    assert ana["faturamento"] == 15000.0          # rede com 2 lojas no mesmo CNPJ conta uma vez
    assert ana["custo_periodo"] == 6000.0         # 6 meses × 1000
    assert ana["lojas"] == 3
    assert ana["lojas_sem_compra"] == 1
    assert ana["percentual_custo"] == 40.0
    assert painel["resumo"]["faturamento"] == 15000.0
    assert painel["resumo"]["cnpjs_compartilhados"] == 1
    lojas_rede = [l for l in painel["lojas"] if l["cnpj"] == "111"]
    assert all(l["faturamento"] == 15000.0 and l["lojas_mesmo_cnpj"] == 2 for l in lojas_rede)


def test_mes_unico_e_outro_ano_nao_entram():
    fat, prom, rot = _dados()
    painel = calcular_painel(fat, prom, rot, Filtros("2026-02", "2026-02", supervisor="Vanessa"))
    assert painel["resumo"]["faturamento"] == 0
    assert painel["resumo"]["custo"] == 1000.0


def test_custo_comeca_na_admissao():
    assert meses_de_custo("2026-03-15", 2026 * 12, 2026 * 12 + 8) == 7   # mar a set
    assert meses_de_custo("2027-01-01", 2026 * 12, 2026 * 12 + 8) == 0
    assert meses_de_custo("", 2026 * 12, 2026 * 12 + 8) == 9


def test_filtro_por_uf_mostra_so_promotores_do_local():
    fat, prom, rot = _dados()
    painel = calcular_painel(fat, prom, rot, Filtros("2026-01", "2026-09", uf="PR"))
    assert [p["nome"] for p in painel["promotores"]] == ["Bruno"]
    assert painel["promotores"][0]["custo_periodo"] == 14000.0  # mar a set = 7 meses


def test_conversoes():
    assert normalizar_cnpj("06.124.533/0001-61") == "06124533000161"
    assert normalizar_cnpj(6124533000161) == "06124533000161"
    assert converter_numero("R$ 1.234,56") == 1234.56
    assert converter_numero(" - ") == 0.0
    assert converter_numero(99.5) == 99.5
