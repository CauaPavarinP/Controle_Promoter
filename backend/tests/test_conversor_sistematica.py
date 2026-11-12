"""Conversor da "Sistemática de atendimento" (planilha da filial) para o modelo das agências."""
import importlib.util
from pathlib import Path

from openpyxl import Workbook, load_workbook

from conftest import entrar

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "converter_sistematica.py"


def _conversor():
    spec = importlib.util.spec_from_file_location("converter_sistematica", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _sistematica(caminho: Path) -> Path:
    """Mesmo formato da real: títulos em cima, cabeçalho em 2 linhas (dias Seg…Sáb embaixo), aba dos MEIs."""
    livro = Workbook()
    aba = livro.active
    aba.title = "PR _ATENDIMENTO"
    aba.append(["SISTEMATICA DE ATENDIMENTO RED HORSE"])
    aba.append(["QUANT. DE LOJAS: 5", "QUANT. DE PROMOTORES: 2"])
    aba.append(["RECRUTANDO: PROMOTOR DIRETO"])
    aba.append([])
    aba.append(["LOJA", "ENDEREÇO", " BAIRRO", "CIDADE", "CEP ", "UF", "FREQ.", "Dias de Atendimento", None, None, None,
                None, None, "RCA RESPONSAVEL", "SUPERVISOR MERCHAN", "DIRETO OU MEI", "PROMOTOR RED HORSE"])
    aba.append([None] * 7 + ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab"])
    aba.append([])
    aba.append(["MERCADO UM 11.222.333/0001-81", "RUA A, 1", "CENTRO", "CURITIBA", "80000-000", "PR", "2",
                None, "1", None, "1", None, None, "RCA X", "JESUS", "CLT", "CARLOS - CURITIBA"])
    aba.append(["MERCADO DOIS", "RUA B, 2", "CENTRO", "CURITIBA", "80000-001", "PR", "3",
                "1", None, "1", None, "1", None, "RCA X", "JESUS", "CLT", "CARLOS - CURITIBA"])
    aba.append(["MERCADO TRES - CNPJ 77.752.293/0107-46", "RUA C", "", "PATO BRANCO", "", "PR", "1",
                None, "1", None, None, None, None, "RCA Y", "MARIA", "MEI", "ANA - PATO BRANCO"])
    aba.append(["MERCADO QUATRO", "RUA D", "", "PATO BRANCO", "", "PR", "1",
                None, None, None, "1", None, None, "RCA Y", "MARIA", "MEI", "ANA - PATO BRANCO"])
    aba.append(["MERCADO CINCO", "RUA E", "", "FRANCISCO BELTRAO", "", "PR", "1",
                "1", None, None, None, None, None, "RCA Y", "MARIA", "MEI", "LUCIANE MEI - FB"])
    aba.append(["MERCADO SEIS", "RUA F", "", "LONDRINA", "", "PR", "1",
                "1", None, None, None, None, None, "", "#N/A", "MEI", "AGENCIA IMPACTO"])
    meis = livro.create_sheet("MEI'S PR")
    meis.append(["FECHAMENTO DE VALORES MEI'S"])
    meis.append([])
    meis.append(["NOME", "CNPJ", "CIDADE", "DIA DE PAGAMENTO", "PAGAMENTO", "QUANT DE VISITAS", "CUSTO DIA", "VALOR MÊS"])
    meis.append(["ANA", "00.000.000/0001-91", "PATO BRANCO", "10", "30 DIAS", 9, 30, 270])
    meis.append(["LUCIANE", "00.000.000/0002-72", "TEL BORBA/TIBAGI", "10", "30 DIAS", 4, 25, 100])
    meis.append(["LUCIANE", "00.000.000/0003-53", "FRANCISCO BELTRÃO", "10", "30 DIAS", 4, 25, 125])
    meis.append([None, None, None, None, None, None, "TOTAL:", 495])
    livro.save(caminho)
    return caminho


def test_converte_sistematica_e_importa(cliente, tmp_path):
    conversor = _conversor()
    saida = tmp_path / "saida.xlsx"
    custos = tmp_path / "custos.xlsx"
    livro = Workbook()
    livro.active.append(["Promotor", "Custo"])
    livro.active.append(["Carlos - Curitiba", 2000])
    livro.save(custos)
    resultado = conversor.converter(_sistematica(tmp_path / "sist.xlsx"), "2026-10", saida, custo_clt=custos)
    lojas = {l["loja"]: l for l in resultado["lojas"]}
    # CNPJ junto do nome sai do nome; visitas = quantas vezes os dias caem em out/2026 (Ter+Qui = 9; Seg+Qua+Sex = 13).
    assert lojas["MERCADO UM"]["cnpj"] == "11.222.333/0001-81" and lojas["MERCADO TRES"]["cnpj"] == "77.752.293/0107-46"
    assert lojas["MERCADO UM"]["visitas"] == 9 and lojas["MERCADO DOIS"]["visitas"] == 13
    assert lojas["MERCADO UM"]["dias"] == ["TER", "QUI"]
    # CLT: R$ 2.000 divididos pelas visitas (9 e 13). MEI Ana: R$ 270 pelas visitas (Ter=4, Qui=5).
    assert lojas["MERCADO UM"]["valor"] + lojas["MERCADO DOIS"]["valor"] == 2000
    assert round(lojas["MERCADO UM"]["valor"]) == round(2000 * 9 / 22)
    assert lojas["MERCADO TRES"]["valor"] + lojas["MERCADO QUATRO"]["valor"] == 270
    # Duas LUCIANE: "FB" = Francisco Beltrão.
    assert lojas["MERCADO CINCO"]["valor"] == 125
    # "AGENCIA IMPACTO" na coluna do promotor vira agência, sem promotor e sem valor.
    assert lojas["MERCADO SEIS"]["tipo"] == "Agência" and lojas["MERCADO SEIS"]["promotor"] == ""
    assert lojas["MERCADO SEIS"]["valor"] is None
    avisos = dict(resultado["avisos"])
    assert any("AGENCIA IMPACTO" in i for k, v in avisos.items() if k.startswith("Agência escrita") for i in v)
    # Células a preencher em laranja.
    aba = load_workbook(saida)["Atendimentos"]
    titulos = {aba.cell(1, c).value: c for c in range(1, aba.max_column + 1)}
    laranja = [aba.cell(r, titulos["CNPJ da loja"]).fill.fgColor.rgb for r in range(2, 8)]
    assert laranja.count("00FFC98B") == 4    # 4 lojas sem CNPJ
    # Importa no sistema.
    entrar(cliente)
    previa = cliente.post("/api/importacoes/atendimento/previa", files={"arquivo": ("f.xlsx", saida.read_bytes())}).json()
    assert previa["linhas_com_erro"] == 0 and previa["linhas_validas"] == 6
    cliente.post(f"/api/importacoes/atendimento/{previa['token']}/confirmar", json={})
    painel = cliente.get("/api/painel", params={"inicio": "2026-10", "fim": "2026-10"}).json()
    assert painel["resumo"]["custo"] == 2000 + 270 + 125
    agencias = {a["nome"]: a["tipo"] for a in painel["agencias"]}
    assert agencias == {"101 do Brasil": "CLT", "MEI - Ana": "MEI", "MEI - Luciane": "MEI", "Agencia Impacto": "Agência"}
    assert {p["supervisor"] for p in painel["promotores"]} >= {"JESUS", "MARIA"}
