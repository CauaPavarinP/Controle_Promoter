# Ideia futura: buscar o faturamento direto da API do FoccoERP

**Situação (13/11/2026): IDEIA SALVA, NÃO DECIDIDA.** Por enquanto o faturamento continua sendo exportado à mão
do Focco ("Relatorio Faturamento - Mauricio", Gera Excel/TXT) e importado em Importações › Faturamento do ERP.

## Por que

Exportar o ano inteiro do Focco demora e às vezes trava; o arquivo .xls (HTML) é enorme. Pela API, o sistema
buscaria sozinho, por empresa e mês, sem arquivo.

## O que já se sabe (pela documentação Swagger da API)

- Endereço da documentação: portal da API do FoccoERP da empresa (`/api/docs/index.html`), definição
  **"FOCCOERP - CONSULTAS DINÂMICAS V1"**, grupo **Exportacao**.
- Rotas: `GET` e `POST /FoccoIntegrador/api/v1/Exportacao/{mnemonico}`
  - `mnemonico` (obrigatório, no caminho): código da consulta cadastrada no Focco.
- Corpo do `POST` (`ExportacaoRequestDTO`):
  ```json
  {
    "chave": "texto (opcional) — finalidade a confirmar",
    "take": 5000,
    "skip": 0,
    "sorting":    [{ "byColumn": "DT_EMIS", "sort": "asc" }],
    "parameters": [{ "column": "COD_EMP", "value": "11" }]
  }
  ```
  - `take`/`skip`: paginação (dá para buscar o ano inteiro aos poucos).
  - `parameters`: filtros coluna = valor (valor de tipo livre; **não há operador** "entre"/"maior que").
  - As descrições falam em "LOV" (lista de valores): o tipo de consulta do Focco por trás da exportação.
- Resposta `200`: lista de linhas, cada linha com os campos pelo **nome da coluna** da consulta — o mesmo formato
  do relatório que o sistema já lê. `401`/`403`: sem permissão; `404`: mnemônico não existe.
- Exige autenticação (botão "Authorize" no Swagger).
- Outras definições vistas: COMERCIAL V1 (Cliente, NotasFiscais, PedidoVenda), COMPRAS, ESTOQUE, ETIQUETAS,
  FOCCOHUB, INSIGHT, PRODUÇÃO, PRODUTOS E ENGENHARIA. NotasFiscais é a alternativa se a Exportação não servir.

## Como entraria no sistema (plano, sem mudar os cálculos)

1. Em Importações › Faturamento do ERP, botão **"Buscar do Focco"**: escolhe empresa(s) e mês(es).
2. O sistema chama a API página por página e grava as linhas num arquivo temporário (CSV) — e daí segue o mesmo
   caminho da importação por arquivo: leitura em partes, prévia, substituição por empresa + mês, Gravar.
3. Depois, se quiserem: busca automática diária (mês atual e anterior).
4. Endereço da API, usuário/token e mnemônico em **variáveis de ambiente** do servidor — nunca no código nem no
   repositório.
5. A importação por arquivo continua como plano B.

## O que falta (perguntas para a TI / suporte do Focco)

1. Qual o **mnemônico** do "Relatorio Faturamento - Mauricio"? Ele pode ser chamado por essa API? Se não, dá para
   cadastrar uma consulta com as mesmas colunas?
2. Como funciona a **autenticação**? Dá para criar um **usuário de API só de leitura**?
3. Como passar o **período** (data inicial/final) e a **empresa** nos `parameters`? Para que serve `chave`?
4. Máximo de linhas por chamada (`take`) e limite de chamadas?
5. A API aceita chamadas de um **servidor na internet** ou só de IPs liberados?
6. Teste: com autorização da TI, um "Try it out" com o mnemônico e `take: 5` (print da resposta com dados
   borrados) para ver os nomes das colunas e o formato de data e valor.

## Cuidados

- Precisa de aprovação do Carlos/TI. Se a troca de ERP (Prosyst, em avaliação) acontecer, a integração teria de
  ser refeita para o ERP novo.
- Nunca colocar token/senha no código, no chat ou no GitHub.
