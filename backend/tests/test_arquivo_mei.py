"""Arquivo dos MEIs ("CONTROLE DE PROMOTORES MEI", aba "CONTROLE GERAL"): promotor e valor em células mescladas,
loja e CNPJ juntos, frequência por semana e sem mês (escolhido na importação). Dados fictícios."""
import io

import pandas as pd
from openpyxl import Workbook

from app.calculo_atendimento import FiltrosAtendimento, calcular, inicio_no_mes
from app.atendimento import separar_cliente
from conftest import entrar

CABECALHO = ["NOME DO PROMOTOR", "UF", "CIDADE", "CLIENTE / CNPJ", "FREQUÊNCIA / SEMANA", "OBSERVAÇÃO", "VALOR (R$)"]


def _arquivo_mei() -> bytes:
    livro = Workbook()
    aba = livro.active
    aba.title = "CONTROLE GERAL"
    aba.append(["CONTROLE DE PROMOTORES MEI"])
    aba.append(["Gestão de clientes, frequência semanal e valores"])
    aba.append([])
    aba.append(CABECALHO)
    # Bloco 1 (linhas 5 a 8): 3 lojas de mesmo nome em cidades diferentes, CNPJ com dígito errado; R$ 720 mesclado.
    aba.append(["JOAO", "RS", "CIDADE UM", "MERCADO ALFA / 112223330001-00", 2, None, 720])
    aba.append([None, "RS", "CIDADE DOIS", "MERCADO ALFA / 112223330002-00", 1, None, None])
    aba.append([None, "RS", "CIDADE TRES", "MERCADO ALFA / 112223330003-00", 1, None, None])
    aba.append([None, "RS", "CIDADE QUATRO", "LOJA BETA / 11.222.333/0001-81", 1, "Atendimento teve início dia 20/10", None])
    # Bloco 2 (linhas 9 e 10): R$ 100,01 ÷ 2 (o centavo que sobra vai para a última loja).
    aba.append(["MARIA", "RS", "CIDADE UM", "REDE GAMA - 11.444.777/0001-61", 3, None, 100.01])
    aba.append([None, "RS", "CIDADE DOIS", "REDE GAMA - 11.444.777/0002-42", 1, None, None])
    for faixa in ("A5:A8", "G5:G8", "A9:A10", "G9:G10"):
        aba.merge_cells(faixa)
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def _previa(cliente, mes=None):
    dados = {"mes": mes} if mes else {}
    return cliente.post("/api/importacoes/atendimento/previa", files={"arquivo": ("mei.xlsx", _arquivo_mei())},
                        data=dados)


def test_separar_cliente_e_cnpj():
    assert separar_cliente("MAX FORT - 14.814.080/0003-41") == ("MAX FORT", "14.814.080/0003-41")
    assert separar_cliente("NIEDERAUER / 881232160005-58") == ("NIEDERAUER", "881232160005-58")
    assert separar_cliente("ROTA /  (15.384.277/0003-02) - 15.384.277/0003-02") == ("ROTA", "15.384.277/0003-02")
    assert separar_cliente("L. C. BONATO & CIA LTDA - FILIAL 01 - 93.049.203/0002-34") == (
        "L. C. BONATO & CIA LTDA - FILIAL 01", "93.049.203/0002-34")
    assert separar_cliente("SUPER 300 / 911402370001-94") == ("SUPER 300", "911402370001-94")
    assert separar_cliente("LOJA SEM CNPJ") == ("LOJA SEM CNPJ", "")
    assert inicio_no_mes("Atendimento teve início dia 20/10") == "20/10"


def test_arquivo_mei_sem_mes_pede_o_mes(cliente):
    entrar(cliente)
    resposta = _previa(cliente)
    assert resposta.status_code == 400 and "Mês de referência" in resposta.json()["detail"]


def test_arquivo_mei_separa_as_lojas_e_divide_o_valor(cliente, banco):
    entrar(cliente)
    previa = _previa(cliente, "2026-10").json()
    assert previa["linhas_validas"] == 6 and previa["linhas_com_erro"] == 0 and previa["descartadas"] == []
    assert previa["incompletas"] == []                     # frequência informada: visitas não "faltam"
    assert previa["lojas"] == 6 and previa["promotores"] == 2
    grupos = {g["agencia"]: g for g in previa["grupos"]}
    assert set(grupos) == {"MEI - Joao", "MEI - Maria"}
    assert grupos["MEI - Joao"]["lojas"] == 4 and grupos["MEI - Joao"]["valor"] == 720 and grupos["MEI - Joao"]["mes"] == "2026-10"
    assert any("R$ 720,00 ÷ 4 lojas = R$ 180,00" in a for a in previa["avisos"])
    assert [(c["linha"], c["cnpj"]) for c in previa["cnpjs_invalidos"]][:1] == [(5, "112223330001-00")]
    assert not any("repetidas" in a for a in previa["avisos"])
    cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={})

    painel = cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-10"}).json()
    lojas = {(l["loja"], l["cidade"]): l for l in painel["lojas"]}
    assert len(lojas) == 6
    alfa = [l for (nome, _), l in lojas.items() if nome == "MERCADO ALFA"]
    assert sorted(l["custo_periodo"] for l in alfa) == [180, 180, 180]
    um = lojas[("MERCADO ALFA", "CIDADE UM")]
    assert um["dias"] == "2x/semana" and um["visitas"] == 9 and um["visitas_estimadas"] is True   # 2 × 31 ÷ 7
    assert um["cnpj"] == "" and um["cnpj_arquivo"] == "112223330001-00"
    assert lojas[("LOJA BETA", "CIDADE QUATRO")]["inicio"] == "20/10"
    gama = sorted(l["custo_periodo"] for (nome, _), l in lojas.items() if nome == "REDE GAMA")
    assert gama == [50.0, 50.01]
    assert any("estimadas pela frequência" in a for a in painel["resumo"]["avisos"])


REGRAS = {"valor_faturamento": "valor", "somente_receita": False, "tipos_nf": {}, "tipos_nf_padrao": "soma",
          "limite_percentual": 3.0}


def _atend(mes, valor):
    return {"ano": 2026, "mes": mes, "cnpj": "91292987003136", "loja": "REDE VIVO", "loja_chave": "REDE VIVO",
            "cidade": "X", "uf": "RS", "agencia": "MEI - Thiago", "agencia_chave": "MEI THIAGO", "promotor": "Thiago",
            "promotor_chave": "t", "promotor_codigo": "", "tipo": "MEI", "supervisor": "", "visitas": None,
            "valor": valor, "dias": "", "status": "Ativa", "frequencia_semana": 1, "cnpj_arquivo": "", "observacao": ""}


def _fat(mes, valor):
    return {"ano": 2026, "mes": mes, "cnpj": "91292987003136", "uf": "RS", "valor": valor, "chave_tipo": "VENDA",
            "notas": 1}


def test_acumulado_usa_so_o_faturamento_dos_meses_com_custo():
    fat = pd.DataFrame([_fat(m, 1000.0) for m in range(1, 12)])            # comprou de jan a nov
    # (b) custo só em outubro: o atendimento não existe nos outros meses (já era assim).
    so_outubro = calcular(fat, pd.DataFrame([_atend(10, 173.33)]), FiltrosAtendimento("2026-01", "2026-11"), REGRAS)
    loja = so_outubro["lojas"][0]
    assert (loja["faturamento"], loja["percentual_custo"], loja["faturamento_sem_custo"]) == (1000, 17.3, 0)
    # (a) linhas em outros meses com valor vazio ou R$ 0: o faturamento delas fica fora do %, com aviso.
    atend = pd.DataFrame([_atend(10, 173.33)] + [_atend(m, None) for m in range(1, 10)] + [_atend(11, 0.0)])
    r = calcular(fat, atend, FiltrosAtendimento("2026-01", "2026-11"), REGRAS)
    loja = r["lojas"][0]
    assert (loja["faturamento"], loja["percentual_custo"], loja["situacao"]) == (1000, 17.3, "acima")
    assert (loja["faturamento_sem_custo"], loja["meses_sem_custo"]) == (10000, 10)
    assert r["resumo"]["faturamento"] == 1000 and r["resumo"]["percentual_custo"] == 17.3
    assert any("meses sem custo" in a for a in r["resumo"]["avisos"])
    assert r["promotores"][0]["percentual_custo"] == 17.3
