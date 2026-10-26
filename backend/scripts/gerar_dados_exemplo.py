"""Gera planilhas FICTÍCIAS no mesmo layout das planilhas reais, para testar o sistema.

Uso:  python scripts/gerar_dados_exemplo.py
Saída: backend/exemplos/
  - faturamento_exemplo.xlsx   exportação do ERP (aba FATURAMENTO, uma linha por item de nota)
  - promotores_exemplo.xlsx    aba PROMOTORES BRASIL
  - roteiro_exemplo.xlsx       abas SC e PR (promotor ↔ loja)
  - planilha_completa_exemplo.xlsx  tudo junto, como "ROTEIROS X FATURAMENTOS", com os meses
                                    JAN…DEZ calculados nas abas por UF (para a conferência)
"""
import random
from pathlib import Path

import pandas as pd

PASTA = Path(__file__).resolve().parent.parent / "exemplos"
random.seed(101)
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

PROMOTORES = [
    # código, nome, admissão, município, supervisor, salário, ajuda, transporte
    ("90001", "Ana Teste", "2025-03-10", "TIJUCAS - SC", "Supervisora Um", 2260, 600, 400),
    ("90002", "Bruno Teste", "2026-02-03", "ITAJAI - SC", "Supervisora Um", 2260, 600, 400),
    ("90003", "Carla Teste", "2024-08-01", "CURITIBA - PR", "Supervisor Dois", 2400, 500, 350),
    ("90004", "Diego Teste", "2025-11-20", "LONDRINA - PR", "Supervisor Dois", 2260, 700, 0),
]

# código promotor, loja, CNPJ, COD CLI no ERP, cidade, UF, visitas/semana, compra média mensal (0 = não compra)
LOJAS = [
    ("90001", "REDE ALFA - CENTRO", "00.000.001/0001-01", "1001", "TIJUCAS", "SC", 3, 9000),
    ("90001", "REDE ALFA - PRAIA", "00.000.001/0001-01", "1001", "TIJUCAS", "SC", 2, 0),  # rede compra pela matriz
    ("90001", "MERCADO BETA", "00.000.002/0001-02", "1002", "PORTO BELO", "SC", 3, 1200),
    ("90002", "SUPER GAMA", "00.000.003/0001-03", "1003", "ITAJAI", "SC", 5, 25000),
    ("90002", "MERCADO DELTA", "00.000.004/0001-04", "1004", "ITAJAI", "SC", 3, 0),  # nunca compra
    ("90003", "REDE OMEGA - BATEL", "00.000.005/0001-05", "1005", "CURITIBA", "PR", 4, 60000),
    ("90003", "REDE OMEGA - PORTAO", "00.000.005/0001-05", "1005", "CURITIBA", "PR", 4, 0),
    ("90003", "ATACADO SIGMA", "00.000.006/0001-06", "1006", "CURITIBA", "PR", 2, 40000),
    ("90004", "MERCADO KAPPA", "00.000.007/0001-07", "1007", "LONDRINA", "PR", 3, 3000),
    # Mesmo CNPJ, mas cada loja com o seu COD CLI no ERP: dá para separar o faturamento.
    ("90004", "LAMBDA - CENTRO", "00.000.008/0001-08", "2001", "LONDRINA", "PR", 2, 5000),
    ("90004", "LAMBDA - ZONA SUL", "00.000.008/0001-08", "2002", "LONDRINA", "PR", 2, 2000),
]

PRODUTOS = [("1603045", "COCKTAIL EXEMPLO (VIDRO) 900ML CX6UN", 75.0, "APERITIVO"),
            ("6652008", "ICE EXEMPLO (VIDRO) 275ML CX24UN", 99.0, "ICE"),
            ("5601555", "ENERGETICO EXEMPLO (PET) 1L CX6UN", 24.0, "ENERGETICO")]


def gerar_faturamento() -> pd.DataFrame:
    linhas, nota = [], 70000
    compradores = {}
    for _, loja, cnpj, cod_cli, cidade, uf, _, media in LOJAS:
        if media and (cnpj, cod_cli) not in compradores:
            compradores[(cnpj, cod_cli)] = (loja, cidade, uf, media)
    for (cnpj, cod_cli), (loja, cidade, uf, media) in compradores.items():
        for mes in range(1, 10):
            if random.random() < 0.35:  # meses sem compra (cliente estocado)
                continue
            nota += 1
            alvo = media * random.uniform(0.3, 2.5)
            while alvo > 0:
                cod, desc, preco, grupo = random.choice(PRODUTOS)
                qtd = random.randint(1, 25)
                valor = round(qtd * preco, 2)
                linhas.append({
                    "COD EMP": 10, "DT EMIS": f"{random.randint(1, 28):02d}/{mes:02d}/2026", "ANO": 2026, "MES": mes,
                    "NUM NF": nota, "COD SEGMENTO": 16, "DESCRICAO SEGMENTO": "VAREJO", "COD CLI": int(cod_cli),
                    "COD EST": 1, "TP PES": "J", "CNPJ CPF": cnpj, "1": loja.split(" - ")[0] + " LTDA",
                    "CIDADE": cidade, "UF": uf, "COD REP": 1006, "REPRESENTANTE": "REPRESENTANTE TESTE",
                    "COD ITEM": cod, "DESCRICAO ITEM": desc, "QTDE": qtd, "PRECO UNIT": preco,
                    "VLR MERCADORIA": valor, "VLR TOTAL": valor, "TIPO NF": "1-Venda", "CFOP": 5405,
                    "RECEITA": "SIM", "COND PGTO": "35/45 DIAS", "TOTAL VENDA": valor, "GRUPO": grupo,
                })
                alvo -= qtd * preco
    # Uma devolução (valor negativo) e uma bonificação (RECEITA = NAO), para testar as regras.
    linhas.append({**linhas[0], "NUM NF": 99998, "VLR TOTAL": -500.0, "TOTAL VENDA": -500.0, "TIPO NF": "2-Devolucao"})
    linhas.append({**linhas[1], "NUM NF": 99999, "VLR TOTAL": 300.0, "TOTAL VENDA": 300.0, "TIPO NF": "5-Bonificacao",
                   "RECEITA": "NAO"})
    return pd.DataFrame(linhas)


def tabela_promotores() -> pd.DataFrame:
    return pd.DataFrame([{
        "Admissão": pd.Timestamp(adm), "código": int(cod), "Colaborador": nome, "Salário": sal,
        "Ajud. Custo": ajuda, "V. transp.": transp, "Municipio": mun, "SUPERVISOR": sup,
        "TOTAL": sal + ajuda + transp,
    } for cod, nome, adm, mun, sup, sal, ajuda, transp in PROMOTORES])


def tabela_roteiro(uf: str, faturamento: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aba por UF. Com o faturamento, calcula JAN…DEZ como o SOMASE da planilha (por mês + CNPJ)."""
    nomes = {p[0]: p[1].upper() for p in PROMOTORES}
    supervisores = {p[0]: p[4] for p in PROMOTORES}
    linhas = []
    for cod, loja, cnpj, _, cidade, uf_loja, visitas, _ in LOJAS:
        if uf_loja != uf:
            continue
        linha = {"Supervisor": supervisores[cod], "Colaborador": nomes[cod], "CPF/CNPJ": cnpj,
                 "Razão Social": loja, "Cidade": cidade, "UF": uf_loja, "Visitas semana": visitas}
        if faturamento is not None:
            do_cnpj = faturamento[faturamento["CNPJ CPF"] == cnpj]
            for numero, nome_mes in enumerate(MESES, start=1):
                linha[nome_mes] = round(float(do_cnpj.loc[do_cnpj["MES"] == numero, "TOTAL VENDA"].sum()), 2)
            linha["TOTAL"] = round(sum(linha[m] for m in MESES), 2)
        linhas.append(linha)
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    PASTA.mkdir(exist_ok=True)
    faturamento = gerar_faturamento()
    promotores = tabela_promotores()

    faturamento.to_excel(PASTA / "faturamento_exemplo.xlsx", sheet_name="FATURAMENTO", index=False)
    # Igual à planilha real: título/totais acima e cabeçalho na linha 5.
    with pd.ExcelWriter(PASTA / "promotores_exemplo.xlsx") as escritor:
        promotores.to_excel(escritor, sheet_name="PROMOTORES BRASIL", index=False, startrow=4)
    with pd.ExcelWriter(PASTA / "roteiro_exemplo.xlsx") as escritor:
        for uf in ("SC", "PR"):
            tabela_roteiro(uf).to_excel(escritor, sheet_name=uf, index=False, startrow=3)
    with pd.ExcelWriter(PASTA / "planilha_completa_exemplo.xlsx") as escritor:
        faturamento.to_excel(escritor, sheet_name="FATURAMENTO", index=False)
        promotores.to_excel(escritor, sheet_name="PROMOTORES BRASIL", index=False, startrow=4)
        for uf in ("SC", "PR"):
            tabela_roteiro(uf, faturamento).to_excel(escritor, sheet_name=uf, index=False, startrow=3)
    print(f"Planilhas fictícias geradas em {PASTA} ({len(faturamento)} itens de nota).")
