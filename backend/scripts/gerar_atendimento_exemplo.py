"""Gera o arquivo FICTÍCIO de atendimento das agências (no modelo único), para testar o sistema.

Uso:  python scripts/gerar_atendimento_exemplo.py
Saída: backend/exemplos/atendimento_exemplo.xlsx — janeiro a setembro de 2026, com as lojas e CNPJs de
faturamento_exemplo.xlsx: lojas de SC pela "Agência Alfa" (sem código de promotor) e as do PR pela própria
"101 do Brasil" (promotores CLT, com código).
"""
from pathlib import Path

from openpyxl import load_workbook

PASTA = Path(__file__).resolve().parent.parent / "exemplos"

# loja, CNPJ, cidade, UF, agência, promotor, código, dias, visitas no mês, valor do mês, primeiro mês
LOJAS = [
    ("REDE ALFA - CENTRO", "00.000.001/0001-01", "TIJUCAS", "SC", "Agência Alfa", "Ana Teste", "", "Seg, Qua, Sex", 12, 300, 1),
    ("REDE ALFA - PRAIA", "00.000.001/0001-01", "TIJUCAS", "SC", "Agência Alfa", "Ana Teste", "", "Ter, Qui", 8, 200, 1),
    ("MERCADO BETA", "00.000.002/0001-02", "PORTO BELO", "SC", "Agência Alfa", "Ana Teste", "", "Seg, Qua, Sex", 12, 300, 1),
    ("SUPER GAMA", "00.000.003/0001-03", "ITAJAI", "SC", "Agência Alfa", "Bruno Teste", "", "Seg a Sex", 20, 500, 2),
    ("MERCADO DELTA", "00.000.004/0001-04", "ITAJAI", "SC", "Agência Alfa", "Bruno Teste", "", "Seg, Qua, Sex", 12, 300, 2),
    ("REDE OMEGA - BATEL", "00.000.005/0001-05", "CURITIBA", "PR", "101 do Brasil", "Carla Teste", "90003", "Seg a Qui", 16, 800, 1),
    ("REDE OMEGA - PORTAO", "00.000.005/0001-05", "CURITIBA", "PR", "101 do Brasil", "Carla Teste", "90003", "Seg a Qui", 16, 800, 1),
    ("ATACADO SIGMA", "00.000.006/0001-06", "CURITIBA", "PR", "101 do Brasil", "Carla Teste", "90003", "Ter, Qui", 8, 400, 1),
    ("MERCADO KAPPA", "00.000.007/0001-07", "LONDRINA", "PR", "101 do Brasil", "Diego Teste", "90004", "Seg, Qua, Sex", 12, 600, 1),
    ("LAMBDA - CENTRO", "00.000.008/0001-08", "LONDRINA", "PR", "101 do Brasil", "Diego Teste", "90004", "Ter, Qui", 8, 400, 1),
    ("LAMBDA - ZONA SUL", "00.000.008/0001-08", "LONDRINA", "PR", "101 do Brasil", "Diego Teste", "90004", "Ter, Qui", 8, 400, 1),
]


def gerar(destino: Path = PASTA / "atendimento_exemplo.xlsx") -> Path:
    livro = load_workbook(PASTA / "modelo_atendimento_agencias.xlsx")
    aba = livro["Atendimentos"]
    linha = 2  # a linha de exemplo do modelo é substituída
    for mes in range(1, 10):
        for loja, cnpj, cidade, uf, agencia, promotor, codigo, dias, visitas, valor, primeiro in LOJAS:
            if mes < primeiro:
                continue
            valores = [f"{mes:02d}/2026", agencia, cnpj, loja, cidade, uf, promotor, codigo, dias, visitas, valor,
                       "Ativa", ""]
            for coluna, valor_celula in enumerate(valores, start=1):
                aba.cell(linha, coluna, valor_celula)
            linha += 1
    livro.save(destino)
    return destino


if __name__ == "__main__":
    print(gerar())
