"""Conversor da planilha ROTEIROS X FATURAMENTOS (do Maurício) para o modelo de atendimento (CLT da 101)."""
import importlib.util
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

from conftest import EXEMPLOS, entrar

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "converter_planilha_mauricio.py"


def _conversor():
    spec = importlib.util.spec_from_file_location("converter_planilha_mauricio", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _planilha_com_pegadinhas(caminho: Path) -> Path:
    """Como a planilha real: cabeçalhos diferentes por aba, #N/A no supervisor, totais acima do cabeçalho."""
    livro = Workbook()
    livro.remove(livro.active)
    livro.create_sheet("FATURAMENTO").append(["MÊS&CNPJ", "COD EMP"])   # não é lida
    pb = livro.create_sheet("PROMOTORES BRASIL")
    for _ in range(3):
        pb.append([])
    pb.append([None, None, None, None, None, 9999, 999, 99, None, None, 99999])   # linha de SUBTOTAL
    pb.append(["UF&SUPERV&COD", "UF", "Admissão", "código", "Colaborador", "Salário", "Ajud. Custo", "V. transp.",
               "Municipio", "SUPERVISOR", "TOTAL"])
    pb.append(["SCAna03", "SC", datetime(2024, 1, 10), "03", "Ana Souza", 2000, 600, 400, "Tijucas", "Laysa", 3000])
    pb.append(["SCBruno", "SC", datetime(2026, 3, 15), "30380", "Bruno Lima", 2000, 500, None, "Itajaí", "Laysa", None])
    pb.append(["PRCarla", "PR", datetime(2023, 5, 2), "77", "Carla Dias", 1800, 0, 0, "Curitiba", "Ivan", 1800])
    pb.append(["MGSup", "MG", datetime(2020, 1, 1), "1", "Supervisor Sem Loja", 5000, 0, 0, "BH", "", 5000])
    sc = livro.create_sheet("SC")
    for _ in range(4):
        sc.append([])
    sc.append([None, None, None, None, None, None, 1, 2, 3, 4])
    sc.append(["Supervisor", "Colaborador", "CPFCNPJ", "Razão Social", "Cidade", "UF", "JAN", "FEV", "MAR", "TOTAL"])
    sc.append(["Laysa", "ANA SOUZA", "11.222.333/0001-81", "MERCADO UM", "TIJUCAS", "SC", 10, 0, 0, 10])
    sc.append(["#N/A", "ANA SOUZA", "77.752.293/0107-46", "MERCADO DOIS", "TIJUCAS", "SC", 0, 0, 0, 0])
    sc.append(["#N/A", "ANA SOUZA", "09.447.652/0020-59", "COMPER CD", "TIJUCAS", "SC", 0, 0, 0, 0])   # CNPJ errado
    sc.append(["Laysa", "BRUNO LIMAA", "09.477.652/0042-64", "MERCADO TRES", "ITAJAI", "SC", 0, 0, 0, 0])  # erro de digitação
    sc.append(["Laysa", "ZÉ SEM CADASTRO", "00.000.001/0001-36", "MERCADO QUATRO", "ITAJAI", "SC", 0, 0, 0, 0])
    pr = livro.create_sheet("PR")
    for _ in range(3):
        pr.append([])
    pr.append([None, None, None, None, None, " JAN ", " FEV "])
    pr.append(["Colaborador", "CPF/CNPJ", "RAZÃO SOCIAL", "Coluna1", "Estado", " JAN ", " TOTAL "])
    pr.append(["Carla Dias", "00.000.005/0001-14", "REDE OMEGA - BATEL", "CURITIBA", None, 1, 1])
    pr.append(["Carla Dias", "00.000.005/0001-14", "REDE OMEGA - PORTAO", "CURITIBA", None, 1, 1])
    pr.append(["Carla Dias", "00.000.006/0001-69", "ATACADO SIGMA", "CURITIBA", None, 1, 1])
    livro.create_sheet("RESUMO")
    livro.save(caminho)
    return caminho


def test_converte_com_as_pegadinhas_da_planilha_real(tmp_path):
    conversor = _conversor()
    resultado = conversor.converter(_planilha_com_pegadinhas(tmp_path / "roteiros.xlsx"), "2026-01", "2026-03",
                                    tmp_path / "saida.xlsx")
    linhas = resultado["linhas"]
    jan = [l for l in linhas if l["Mês de referência"] == "01/2026"]
    mar = [l for l in linhas if l["Mês de referência"] == "03/2026"]
    # Ana: R$ 3.000 em 3 lojas = R$ 1.000 cada. Bruno (admitido em 15/03) só entra em março, R$ 2.500 numa loja.
    ana = [l for l in jan if l["Promotor"] == "Ana Souza"]
    assert [l["Valor do mês (R$)"] for l in ana] == [1000, 1000, 1000]
    assert all(l["Código do promotor"] == "03" and l["Tipo"] == "CLT" and l["Agência ou MEI"] == "101 do Brasil"
               for l in ana)
    assert not any(l["Promotor"] == "Bruno Lima" for l in jan)
    assert [l["Valor do mês (R$)"] for l in mar if l["Promotor"] == "Bruno Lima"] == [2500]   # TOTAL vazio: soma
    # Carla: R$ 1.800 em 3 lojas; PR sem UF na coluna Estado usa o nome da aba; cidade vem de "Coluna1".
    carla = [l for l in jan if l["Promotor"] == "Carla Dias"]
    assert sum(l["Valor do mês (R$)"] for l in carla) == 1800 and {l["UF"] for l in carla} == {"PR"}
    assert {l["Cidade"] for l in carla} == {"CURITIBA"}
    # Supervisor na coluna Supervisor; "#N/A" usa o supervisor do cadastro.
    assert all(l["Supervisor"] == "Laysa" for l in ana)
    # Sem cadastro: entra com R$ 0, com o nome do roteiro.
    assert [l["Valor do mês (R$)"] for l in jan if l["Promotor"] == "ZÉ SEM CADASTRO"] == [0]
    avisos = dict(resultado["avisos"])
    assert any("BRUNO LIMAA → Bruno Lima" in i for i in avisos["Nome do roteiro ligado ao cadastro por semelhança (confira)"])
    assert any("ZÉ SEM CADASTRO" in i for k, v in avisos.items() if "sem cadastro" in k for i in v)
    assert any("Supervisor Sem Loja" in i for k, v in avisos.items() if "sem nenhuma loja" in k for i in v)
    assert any("COMPER CD" in i for k, v in avisos.items() if k.startswith("CNPJ inválido") for i in v)
    assert any('Aba "SC": 2 linha(s) com supervisor' in k for k in avisos)
    assert resultado["resumo"]["Valor total gerado (R$)"] == 3000 * 3 + 2500 + 1800 * 3


def test_arquivo_gerado_importa_no_sistema(cliente, tmp_path):
    """O arquivo gerado passa pela importação normal das agências, sem erro."""
    conversor = _conversor()
    resultado = conversor.converter(EXEMPLOS / "planilha_completa_exemplo.xlsx", "2026-01", "2026-09",
                                    tmp_path / "clt.xlsx")
    entrar(cliente)
    previa = cliente.post("/api/importacoes/atendimento/previa",
                          files={"arquivo": ("clt.xlsx", (tmp_path / "clt.xlsx").read_bytes())}).json()
    assert previa["linhas_com_erro"] == 0 and not previa["descartadas"] and not previa["cnpjs_invalidos"]
    assert previa["linhas_validas"] == len(resultado["linhas"])
    assert previa["valor_total"] == resultado["resumo"]["Valor total gerado (R$)"]
    cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={})
    painel = cliente.get("/api/painel", params={"inicio": "2026-01", "fim": "2026-09"}).json()
    assert {p["tipo"] for p in painel["promotores"]} == {"CLT"}
    assert {p["supervisor"] for p in painel["promotores"]} == {"Supervisora Um", "Supervisor Dois"}
    assert cliente.get("/api/opcoes").json()["supervisores"] == ["Supervisor Dois", "Supervisora Um"]
    so_um = cliente.get("/api/painel", params={"inicio": "2026-01", "fim": "2026-09", "supervisor": "Supervisora Um"}).json()
    assert {p["nome"] for p in so_um["promotores"]} == {"Ana Teste", "Bruno Teste"}
    assert painel["resumo"]["custo"] == resultado["resumo"]["Valor total gerado (R$)"]
