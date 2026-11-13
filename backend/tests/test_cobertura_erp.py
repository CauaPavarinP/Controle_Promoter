"""ERP importado só em parte (ex.: out/2026 só de MG): as lojas das outras UFs ficam "falta o faturamento" (⚪),
e não "não comprou" (🔴)."""
import pandas as pd

from app.calculo_atendimento import FiltrosAtendimento, calcular

REGRAS = {"valor_faturamento": "valor", "somente_receita": False, "tipos_nf": {}, "tipos_nf_padrao": "soma",
          "limite_percentual": 3.0}


def _atend(uf, cnpj, loja, valor=300.0, mes=10):
    return {"ano": 2026, "mes": mes, "cnpj": cnpj, "loja": loja, "loja_chave": loja.lower(), "cidade": "X", "uf": uf,
            "agencia": "Ag", "agencia_chave": "ag", "promotor": f"P {loja}", "promotor_chave": f"p-{loja}",
            "promotor_codigo": "", "tipo": "Agência", "supervisor": "", "visitas": 4, "valor": valor, "dias": "",
            "status": "Ativa"}


def _fat(uf, cnpj, valor, mes=10):
    return {"ano": 2026, "mes": mes, "cnpj": cnpj, "uf": uf, "valor": valor, "chave_tipo": "VENDA", "notas": 1}


def _rodar(atend, fat):
    return calcular(pd.DataFrame(fat), pd.DataFrame(atend), FiltrosAtendimento(inicio="2026-10", fim="2026-10"), REGRAS)


def test_mes_com_erp_so_de_outra_uf_fica_sem_erp():
    r = _rodar([_atend("PR", "11222333000181", "Loja PR")], [_fat("MG", "99888777000166", 50000)])
    promotor = r["promotores"][0]
    assert promotor["sem_erp"] is True and promotor["situacao"] == "sem_erp"
    assert r["resumo"]["sem_erp"] is True
    assert any("2026-10 (PR)" in aviso for aviso in r["resumo"]["avisos"])
    assert r["mes_a_mes"][0]["situacao"] == "sem_erp"


def test_uf_com_erp_e_sem_compra_continua_vermelho():
    r = _rodar([_atend("PR", "11222333000181", "Loja PR")], [_fat("PR", "99888777000166", 50000)])
    assert r["promotores"][0]["situacao"] == "sem_compras"
    assert not any("Sem faturamento do ERP" in aviso for aviso in r["resumo"]["avisos"])


def test_mistura_de_ufs_so_a_uf_sem_erp_fica_cinza():
    r = _rodar([_atend("PR", "11222333000181", "Loja PR"), _atend("MG", "99888777000166", "Loja MG")],
               [_fat("MG", "99888777000166", 50000)])
    por_nome = {p["nome"]: p for p in r["promotores"]}
    assert por_nome["P Loja PR"]["situacao"] == "sem_erp"
    assert por_nome["P Loja MG"]["situacao"] == "ok"          # 300 ÷ 50.000 = 0,6%
    assert r["resumo"]["sem_erp"] is False


def test_loja_sem_uf_usa_so_o_mes():
    r = _rodar([_atend("", "11222333000181", "Loja sem UF")], [_fat("MG", "99888777000166", 50000)])
    assert r["promotores"][0]["situacao"] == "sem_compras"
