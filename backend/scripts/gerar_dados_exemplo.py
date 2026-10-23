"""Gera planilhas FICTÍCIAS no mesmo layout das planilhas reais, para testar o sistema.

Uso:  python scripts/gerar_dados_exemplo.py
Saída: backend/exemplos/*.xlsx
"""
import random
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent / "exemplos"
random.seed(101)

PROMOTORES = [
    # código, nome, admissão, município, supervisor, salário, ajuda, transporte
    ("90001", "Ana Teste", "2025-03-10", "TIJUCAS - SC", "Supervisora Um", 2260, 600, 400),
    ("90002", "Bruno Teste", "2026-02-03", "ITAJAI - SC", "Supervisora Um", 2260, 600, 400),
    ("90003", "Carla Teste", "2024-08-01", "CURITIBA - PR", "Supervisor Dois", 2400, 500, 350),
    ("90004", "Diego Teste", "2025-11-20", "LONDRINA - PR", "Supervisor Dois", 2260, 700, 0),
]

# código promotor, loja, CNPJ, cidade, UF, visitas por semana, compra média mensal (0 = não compra)
LOJAS = [
    ("90001", "REDE ALFA - CENTRO", "00.000.001/0001-01", "TIJUCAS", "SC", 3, 9000),
    ("90001", "REDE ALFA - PRAIA", "00.000.001/0001-01", "TIJUCAS", "SC", 2, 0),  # mesma rede/CNPJ
    ("90001", "MERCADO BETA", "00.000.002/0001-02", "PORTO BELO", "SC", 3, 1200),
    ("90002", "SUPER GAMA", "00.000.003/0001-03", "ITAJAI", "SC", 5, 25000),
    ("90002", "MERCADO DELTA", "00.000.004/0001-04", "ITAJAI", "SC", 3, 0),  # nunca compra
    ("90003", "REDE OMEGA - BATEL", "00.000.005/0001-05", "CURITIBA", "PR", 4, 60000),
    ("90003", "REDE OMEGA - PORTAO", "00.000.005/0001-05", "CURITIBA", "PR", 4, 0),
    ("90003", "ATACADO SIGMA", "00.000.006/0001-06", "CURITIBA", "PR", 2, 40000),
    ("90004", "MERCADO KAPPA", "00.000.007/0001-07", "LONDRINA", "PR", 3, 3000),
]

PRODUTOS = [("1603045", "COCKTAIL EXEMPLO (VIDRO) 900ML CX6UN", 75.0),
            ("6652008", "ICE EXEMPLO (VIDRO) 275ML CX24UN", 99.0),
            ("5601555", "ENERGETICO EXEMPLO (PET) 1L CX6UN", 24.0)]


def gerar_faturamento():
    linhas, nota = [], 70000
    vistos = set()
    for _, loja, cnpj, cidade, uf, _, media in LOJAS:
        if media == 0 or cnpj in vistos:  # rede fatura pela matriz: uma vez por CNPJ
            continue
        vistos.add(cnpj)
        for mes in range(1, 10):
            if random.random() < 0.35:  # meses sem compra (cliente estocado)
                continue
            nota += 1
            alvo = media * random.uniform(0.3, 2.5)
            while alvo > 0:
                cod, desc, preco = random.choice(PRODUTOS)
                qtd = random.randint(1, 25)
                linhas.append({
                    "DT EMISSAO": f"{random.randint(1, 28):02d}/{mes:02d}/2026", "ANO": 2026, "MES": mes,
                    "NUM": nota, "DESCRICAO SEGMENTO": "VAREJO", "COD CLIENTE": 1000 + len(vistos),
                    "TP PES": "J", "CNPJ CPF": cnpj, "RAZAO SOCIAL": loja.split(" - ")[0] + " LTDA",
                    "CIDADE": cidade, "UF": uf, "REPRESENTANTE": "REPRESENTANTE TESTE",
                    "COD ITEM": cod, "DESCRICAO ITEM": desc, "QTD": qtd, "PRECO UN": preco,
                    "VLR TOT": round(qtd * preco, 2), "TIPO NF": "1-Venda",
                })
                alvo -= qtd * preco
    # Uma devolução, que não deve contar como faturamento.
    linhas.append({**linhas[0], "NUM": 99999, "VLR TOT": -500.0, "TIPO NF": "2-Devolucao"})
    pd.DataFrame(linhas).to_excel(PASTA / "faturamento_exemplo.xlsx", sheet_name="FATURAMENTO", index=False)
    return len(linhas)


def gerar_promotores():
    df = pd.DataFrame([{
        "Admissão": pd.Timestamp(adm), "código": int(cod), "Colaborador": nome, "Salário": sal,
        "Ajud. Custo": ajuda, "V. transp.": transp, "Municipio": mun, "SUPERVISOR": sup,
        "TOTAL": sal + ajuda + transp,
    } for cod, nome, adm, mun, sup, sal, ajuda, transp in PROMOTORES])
    # Igual à planilha real: título/totais acima e cabeçalho na linha 5.
    with pd.ExcelWriter(PASTA / "promotores_exemplo.xlsx") as escritor:
        df.to_excel(escritor, sheet_name="PROMOTORES BRASIL", index=False, startrow=4)


def gerar_roteiro():
    nomes = {p[0]: p[1].upper() for p in PROMOTORES}
    supervisores = {p[0]: p[4] for p in PROMOTORES}
    with pd.ExcelWriter(PASTA / "roteiro_exemplo.xlsx") as escritor:
        for uf in ("SC", "PR"):
            df = pd.DataFrame([{
                "Supervisor": supervisores[cod], "Colaborador": nomes[cod], "CPF/CNPJ": cnpj,
                "Razão Social": loja, "Cidade": cidade, "UF": uf_loja, "Visitas semana": visitas,
            } for cod, loja, cnpj, cidade, uf_loja, visitas, _ in LOJAS if uf_loja == uf])
            df.to_excel(escritor, sheet_name=uf, index=False, startrow=3)


if __name__ == "__main__":
    PASTA.mkdir(exist_ok=True)
    itens = gerar_faturamento()
    gerar_promotores()
    gerar_roteiro()
    print(f"Planilhas fictícias geradas em {PASTA} ({itens} itens de nota).")
