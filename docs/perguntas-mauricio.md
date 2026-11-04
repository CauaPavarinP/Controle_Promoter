# Perguntas para o Maurício

Dúvidas que apareceram ao montar o sistema com a planilha "ROTEIROS X FATURAMENTOS".
Atualizado em 04/11/2026. Marque a resposta ao lado de cada item.

## Promotores e custos (aba PROMOTORES BRASIL)

1. **Ajuda de custo "600 + 120m"** — na equipe da supervisora Sara (linhas 71 a 90), a coluna Ajud. Custo
   tem o texto "600 + 120m" em vez de um número.
   - O valor certo é R$ 720 (600 + 120)? O que quer dizer o "m"?
   - Hoje o TOTAL dessas linhas na planilha não soma a ajuda de custo (ex.: 2.260 + 600 = 2.860), porque o
     Excel ignora texto. O total certo deveria incluir a ajuda?
   - Resposta:
2. **Códigos repetidos** — a coluna código tem duas numerações (30xxx e números pequenos). Os códigos
   11, 12, 13, 17, 19 e 21 aparecem em duas pessoas diferentes cada.
   - Os números pequenos são de outra empresa, equipe ou contrato? Existe um código único para cada pessoa
     (ex.: matrícula do RH)?
   - Resposta:
3. **Supervisores na lista de promotores** — há linhas com "Sup." ou "Supervisor" no nome ou no município
   (ex.: linhas 6, 7 e 8).
   - O custo do supervisor deve entrar no custo dos promotores, ficar separado ou ficar de fora?
   - Resposta:
4. **Município vazio** — vários promotores estão sem município. Precisa preencher? (Serve para o filtro de
   município.)
   - Resposta:

## Lojas e roteiro (abas SC, SP, PR, MG, RS)

5. **Nomes que não batem com a PROMOTORES BRASIL** — cerca de 400 lojas têm na coluna Colaborador um nome
   que não existe na aba de promotores. Alguns são o mesmo nome escrito diferente; outros não têm nenhum
   parecido. (A lista sai em Lojas por UF → Colaboradores não encontrados → Exportar Excel.)
   - Os nomes sem parecido são promotores novos, ex-funcionários ou terceirizados?
   - Dá para colocar uma coluna "Código" do promotor nas abas por UF? Assim a ligação fica exata.
   - Resposta:
6. **Visitas por semana** — a planilha não tem quantas vezes o promotor vai a cada loja. Existe essa
   informação em algum lugar (outra planilha, o próprio roteiro)?
   - Resposta:
7. **Lojas com o mesmo CNPJ** — várias lojas (principalmente em MG: 358 lojas com 4 CNPJs) usam o mesmo
   CNPJ. Cada loja de rede tem um código de cliente próprio no ERP (COD CLI), ou tudo é faturado na matriz?
   - Resposta:
8. **Lojas com faturamento zero** — algumas lojas não têm nenhuma nota no ERP de janeiro a setembro
   (ex.: GIASSI - AREIAS, CONDOR 42). O CNPJ está certo ou a loja realmente não comprou?
   - Resposta:
9. **Aba SC** — a coluna Supervisor está toda com #N/A e a aba tem um filtro ativo. É de propósito?
   - Resposta:
10. **Aba RS** — o total geral (célula O2) soma só fevereiro, não o ano. É erro?
    - Resposta:

## Faturamento (aba FATURAMENTO)

11. **Setembro incompleto** — setembro tem muito menos linhas que os outros meses. A exportação foi feita
    no meio do mês?
    - Resposta:
12. **Filtros por marca, família, representante ou segmento** — esses dados estão na aba FATURAMENTO. Ele
    usa esse tipo de análise? (Se sim, dá para acrescentar o filtro no sistema.)
    - Resposta:
13. **Integração com o ERP** — hoje o faturamento entra pelo arquivo exportado do ERP. Ele quer que o
    sistema busque direto do ERP? (Depende da TI liberar acesso.)
    - Resposta:

## Uso do sistema

14. **Quem vai usar** — além do Maurício, os supervisores vão acessar? Cada supervisor deve ver só a
    própria equipe? O supervisor pode ver o salário dos promotores?
    - Resposta:
15. **Macros** — o arquivo tem macros (VBA). O que elas fazem? (Se fizerem algo além das fórmulas, isso
    ainda não está no sistema.)
    - Resposta:
16. **O que ele mais usa no dia a dia** — algum filtro, conta ou relatório que ele faz sempre com a planilha e
    que não aparece nas abas?
    - Resposta:
