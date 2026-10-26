# Controle de Promotores

Sistema web para comparar o **custo dos promotores (repositores)** com o **faturamento das lojas** que
eles atendem. Substitui a planilha "ROTEIROS X FATURAMENTOS".

Pedido do Maurício (Comercial • 101 do Brasil), a validar com o Rayan.

## O que o sistema faz

- **Filtros únicos** para custo e faturamento: período (acumulado ou um mês), supervisor, promotor, UF e cidade.
- **Resumo:** custo dos promotores no período, faturamento das lojas, % do custo sobre o faturamento e lojas sem compra.
- **Tabela de promotores:** lojas, visitas/semana, custo, faturamento e % de custo. Clicar num promotor filtra as lojas dele.
- **Tabela de lojas:** faturamento no período, meses com compra, custo da loja, % de custo e custo por visita.
- **Avisos dos dados:** problemas encontrados nas planilhas (nomes que não batem, CNPJ faltando…).
- **Atualização dos dados** por upload das planilhas, sem mexer no código.
- **Regras do cálculo** ajustadas pelo próprio usuário na tela, sem mexer no código.

## Estrutura

```
backend/            API em Python (FastAPI + pandas)
  app/config.py       variáveis de ambiente
  app/regras.py       regras do cálculo (padrões e validação)
  app/importacao.py   leitura das planilhas (Excel/CSV)
  app/calculos.py     cálculos do painel
  app/db.py           banco (SQLite local / Postgres no Render)
  app/main.py         rotas da API, login e entrega do front
  scripts/            gerador de planilhas FICTÍCIAS para teste
  exemplos/           planilhas fictícias geradas
  tests/              testes automatizados (pytest)
frontend/           tela em React (Vite)
  src/components/     Login, Painel, Filtros, Cards, Tabelas, Importar
```

## Planilhas que o sistema importa

| Tipo | De onde vem | Colunas usadas |
|---|---|---|
| **Faturamento** | Exportação do ERP (aba FATURAMENTO), uma linha por item de nota | DT EMISSÃO ou ANO/MÊS, NUM (nota), CNPJ CPF, VLR TOT, TIPO NF, COD CLIENTE, Razão Social, Cidade, UF |
| **Promotores** | Aba PROMOTORES BRASIL | código, Colaborador, Admissão, Município, SUPERVISOR, Salário, Ajud. Custo, V. transp., TOTAL |
| **Roteiro** | Abas SC, SP, PR… (todas as abas com Colaborador + Razão Social) | Colaborador ou código do promotor, CPF/CNPJ, Razão Social, Cidade, UF, Visitas semana (opcional) |

- O cabeçalho pode estar em qualquer uma das 30 primeiras linhas. As colunas são reconhecidas pelo nome,
  sem diferenciar acento ou maiúscula. Os nomes aceitos ficam nas listas `APELIDOS_*` de `app/importacao.py`.
- Dá para enviar o arquivo inteiro (com todas as abas): cada importação procura a aba certa.
- **Faturamento:** os meses do arquivo substituem os meses iguais já importados; os outros meses ficam.
  Promotores e roteiro substituem a lista inteira.
- O sistema guarda o faturamento **agregado por mês, CNPJ e tipo de nota**, não os itens de nota.

## Regras do cálculo (ajustáveis na aba "Regras do cálculo")

O usuário escolhe cada regra na tela; elas ficam gravadas no banco (tabela `configuracoes`).
Os valores padrão estão em `REGRAS_PADRAO` (`app/regras.py`).

| Regra | Opções | Padrão |
|---|---|---|
| **Tipos de nota** | cada tipo soma, desconta ou fica de fora do faturamento | só "1-Venda" soma |
| **Lojas de rede** | CNPJ exato da loja · rede inteira (raiz do CNPJ) em cada loja · rede dividida igualmente entre as lojas | CNPJ exato |
| **Custo do promotor** | + encargos (% do salário) + custo extra fixo por mês | 0% e R$ 0 |
| **Divisão do custo entre lojas** | igual · proporcional às visitas por semana | igual |
| **Semanas por mês** | usado no custo por visita | 4,33 |
| **Faixas de cor do % de custo** | amarelo a partir de X% · vermelho a partir de Y% | 15% e 30% |

Regras fixas:
- O custo conta a partir do mês de admissão e usa o custo atual (ainda não há histórico de salário).
- Quando várias lojas mostram o mesmo valor (CNPJ ou rede inteira), os totais contam esse valor uma vez só,
  e o % de custo da loja não é calculado.
- Loja com mais de um promotor: o faturamento conta inteiro para cada promotor.
- Tipos de nota novos ficam de fora até o usuário escolher o que fazer com eles.

## Pendências com o Maurício / Rayan

- Cada loja de rede tem código de cliente próprio no ERP, ou tudo é faturado na matriz?
- Existe planilha de roteiro com a frequência de visitas por loja?
- Quais valores usar nas Regras do cálculo (o próprio Maurício pode ajustar na tela).
- Quem vai usar o sistema? Cada supervisor vê só a própria equipe?

## Rodar no computador (desenvolvimento)

Back-end (pasta `backend`):

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements-dev.txt
copy .env.example .env          # Linux/Mac: cp .env.example .env  → preencha usuário, senha e SECRET_KEY
python scripts/gerar_dados_exemplo.py
uvicorn app.main:app --reload --port 8000
```

Front-end (outro terminal, pasta `frontend`):

```bash
npm install
npm run dev
```

Abra http://localhost:5173, entre com o usuário/senha do `.env` e, em **Atualizar dados**, importe as três
planilhas de `backend/exemplos/`.

Testes: `cd backend && pytest`

## Publicar no Render (quando for a hora)

- **Build:** `pip install -r backend/requirements.txt && cd frontend && npm ci && npm run build`
- **Start:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Variáveis de ambiente:** `APP_USUARIO`, `APP_SENHA`, `SECRET_KEY`, `DATABASE_URL` (Postgres do Render), `AMBIENTE=producao`
- O FastAPI entrega o React já compilado (`frontend/dist`): é **um serviço só**.
- Confirme se o ambiente Python do Render tem Node disponível para o `npm run build`. Se não tiver, a
  alternativa é fazer o build com Docker.

## Segurança

- O repositório deve ser **privado**.
- **Planilhas reais nunca vão para o GitHub.** O `.gitignore` bloqueia `.xlsx`/`.csv`, exceto os exemplos fictícios.
- Senhas e chaves só em variáveis de ambiente (`.env` local, Environment no Render).
- Todas as rotas `/api` exigem login, exceto `/api/login`. `/health` é público.
