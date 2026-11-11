"""Remove atendimentos escolhidos (agência, mês, promotor ou importação), com prévia, backup e confirmação.

Feito para a limpeza antes da entrega:
  - a importação duplicada da GRUBAL ("GRUBAL (Demonstrativo outubro)" em 10/2026);
  - a "Agência Teste 101 Ltda" e os promotores de teste.

Por padrão SÓ MOSTRA o que seria apagado. Para apagar de verdade: --executar, e digitar APAGAR quando pedir.
Antes de apagar, guarda um backup no banco (aparece em Agências > Backups e dá para importar de novo).

Uso (na pasta backend, com a variável DATABASE_URL apontando para o banco):
    python scripts/limpar_atendimentos.py --agencia "GRUBAL (Demonstrativo outubro)" --mes 2026-10
    python scripts/limpar_atendimentos.py --agencia "Agência Teste 101 Ltda"
    python scripts/limpar_atendimentos.py --promotor-termina "Teste"
    python scripts/limpar_atendimentos.py --importacao 12
    (acrescente --executar para apagar)

Depois de apagar, reinicie o serviço no Render (o servidor guarda os cálculos na memória e só os refaz quando os
dados mudam pelo próprio sistema).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select, text  # noqa: E402

from app import db  # noqa: E402
from app.importacao import normalizar_texto  # noqa: E402
from app.modelos import Atendimento  # noqa: E402


def _filtro(args):
    condicoes = []
    if args.agencia:
        condicoes.append(Atendimento.agencia_chave == normalizar_texto(args.agencia))
    if args.mes:
        ano, mes = (int(x) for x in args.mes.split("-"))
        condicoes += [Atendimento.ano == ano, Atendimento.mes == mes]
    if args.promotor_termina:
        termo = args.promotor_termina.strip().lower()
        condicoes.append(func.lower(Atendimento.promotor).like(f"% {termo}"))
    if args.importacao:
        condicoes.append(Atendimento.importacao_id == args.importacao)
    return condicoes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agencia", help="nome da agência, como aparece no sistema (sem diferença de acento/maiúscula)")
    parser.add_argument("--mes", help="AAAA-MM (ex.: 2026-10)")
    parser.add_argument("--promotor-termina", help='promotores cujo nome termina com a palavra (ex.: "Teste")')
    parser.add_argument("--importacao", type=int, help="número da importação (Histórico de importações)")
    parser.add_argument("--executar", action="store_true", help="apaga de verdade (pede confirmação)")
    args = parser.parse_args()

    condicoes = _filtro(args)
    if not condicoes:
        parser.error("informe pelo menos um filtro (--agencia, --mes, --promotor-termina ou --importacao)")

    with db.SessaoLocal() as sessao:
        grupos = sessao.execute(
            select(Atendimento.agencia, Atendimento.ano, Atendimento.mes, Atendimento.importacao_id,
                   func.count(), func.count(func.distinct(Atendimento.loja_chave)),
                   func.count(func.distinct(Atendimento.promotor)), func.sum(Atendimento.valor))
            .where(*condicoes)
            .group_by(Atendimento.agencia, Atendimento.ano, Atendimento.mes, Atendimento.importacao_id)
            .order_by(Atendimento.agencia, Atendimento.ano, Atendimento.mes)).all()
        if not grupos:
            print("Nada encontrado com esses filtros. Nada foi apagado.")
            return
        print(f"{'Agência':45} {'Mês':8} {'Import.':>7} {'Linhas':>6} {'Lojas':>5} {'Prom.':>5} {'Valor':>12}")
        total = 0
        for agencia, ano, mes, importacao, linhas, lojas, promotores, valor in grupos:
            total += linhas
            print(f"{agencia[:45]:45} {ano}-{mes:02d}  {importacao:>7} {linhas:>6} {lojas:>5} {promotores:>5} "
                  f"{float(valor or 0):>12,.2f}")
        if args.promotor_termina:
            nomes = sessao.scalars(select(Atendimento.promotor).where(*condicoes).distinct()).all()
            print("Promotores:", ", ".join(sorted(nomes)))
        print(f"\nTotal: {total} linha(s) de atendimento.")

        if not args.executar:
            print("\nNADA FOI APAGADO (só a prévia). Para apagar, rode de novo com --executar.")
            return
        if input('\nDigite APAGAR para apagar essas linhas: ').strip().upper() != "APAGAR":
            print("Cancelado. Nada foi apagado.")
            return

        from app.cadastros import guardar_backup
        backup = guardar_backup(sessao, "script", "Antes do script limpar_atendimentos")
        print(f"Backup guardado no banco: {backup.arquivo_nome if backup else '(nada)'}")
        apagados = sessao.execute(delete(Atendimento).where(*condicoes)).rowcount
        # Importações de atendimento que ficaram sem nenhuma linha.
        sessao.execute(text(
            "UPDATE importacoes SET situacao = 'apagada' WHERE tipo = 'atendimento' AND situacao = 'ativa' "
            "AND NOT EXISTS (SELECT 1 FROM atendimentos a WHERE a.importacao_id = importacoes.id)"))
        sessao.commit()
        print(f"Apagadas {apagados} linha(s). Reinicie o serviço no Render para a tela mostrar os dados novos.")


if __name__ == "__main__":
    main()
