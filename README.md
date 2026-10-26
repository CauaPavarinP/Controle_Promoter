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
- **Cadastros** de supervisores, promotores (com custo por competência), PDVs e roteiros (com datas e visitas).
- **Usuários** com perfis (administrador, consulta, supervisor), senha criptografada e bloqueio após 5 tentativas erradas.

## Fases (documento de requisitos)

| Fase | Situação |
|---|---|
| 1 — Base: banco com migrations, login com usuários, cadastros | ✅ Entregue |
| 2 — Dados: faturamento item a item, desfazer importação, importação inicial com conferência, pendências | ✅ Entregue |
| 3 — Consulta: grade mês a mês, tela por UF, detalhe da NF, imprimir, exportar | Próxima |
| 4 — Extras: gráficos, auditoria, visão restrita do supervisor | Depois |

## Estrutura

```
backend/            API em Python (FastAPI + pandas)
  app/config.py       variáveis de ambiente
  app/modelos.py      tabelas dos cadastros (SQLAlchemy)
  app/cadastros.py    rotas de supervisores, promotores, custos, PDVs e roteiros
  app/usuarios.py     login, sessão, troca de senha e usuários
  app/carga.py        carga das planilhas nos cadastros (idempotente) e primeiro administrador
  app/dados.py        monta as tabelas do cálculo a partir dos cadastros
  app/faturamento.py  faturamento item a item: pré-visualização, gravação, desfazer, consultas
  app/pendencias.py   tela de pendências e conferência com a planilha
  app/regras.py       regras do cálculo (padrões e validação)
  app/importacao.py   leitura das planilhas (Excel/CSV)
  app/calculos.py     cálculos do painel
  app/db.py           banco (SQLite local / Postgres no Render)
  app/main.py         rotas da API, login e entrega do front
  migrations/         estrutura do banco (Alembic), aplicada sozinha ao iniciar
  scripts/            gerador de planilhas FICTÍCIAS para teste
  exemplos/           planilhas fictícias geradas
  tests/              testes automatizados (pytest)
frontend/           tela em React (Vite)
  src/components/     Login, Painel (menu), análise, Importar, Regras
  src/components/cadastros/  Promotores, Supervisores, PDVs, Roteiros, Usuários, Meu perfil
```

## Importações (tela "Atualizar dados", só administrador)

| Cartão | Arquivo | O que faz |
|---|---|---|
| **Importação inicial** | "ROTEIROS X FATURAMENTOS" inteiro | Cadastra promotores, supervisores, PDVs e roteiros; guarda os totais das abas por UF para a **Conferência**; mostra o faturamento para confirmar. Pode rodar de novo sem duplicar. |
| **Faturamento do ERP** | Exportação no layout da aba FATURAMENTO | Mostra a **pré-visualização** (período, linhas, TOTAL VENDA, notas, clientes, linhas com erro, CNPJs sem roteiro, tipos de nota) e só grava ao confirmar. |
| **Promotores** | Aba PROMOTORES BRASIL | Cria ou atualiza pelo código; custo diferente vira reajuste a partir do mês corrente. |
| **Roteiro** | Abas SC, SP, PR… | Cria PDVs (CNPJ + nome) e vínculos novos; colaborador sem promotor vira pendência. |

- Colunas reconhecidas **pelo nome do cabeçalho** (sem diferenciar acento ou maiúscula), em qualquer uma das
  30 primeiras linhas e em qualquer aba. Nomes aceitos: listas `APELIDOS_*` de `app/importacao.py`.
- **Faturamento item a item:** todas as colunas da aba FATURAMENTO são guardadas (tabela `faturamento_itens`).
- **Mês que já existe:** só é substituído se o usuário marcar a confirmação (apaga os itens daquele ano/mês e
  grava os novos). Reimportar o mesmo arquivo não duplica.
- **Linhas com erro** (CNPJ vazio, data inválida, TOTAL VENDA que não é número) ficam de fora e aparecem na
  pré-visualização e no histórico, com o número da linha no Excel (exportável).
- **Histórico** com **desfazer** (apaga os itens daquela importação). Meses que ela substituiu não voltam.
- Promotores e roteiro **não apagam nada** (rodar de novo não duplica). O primeiro custo de um promotor vale
  desde a admissão; o vínculo do roteiro começa em 01/01 do ano corrente.
- **Conferência:** compara, por aba e mês, a soma das linhas da planilha com a mesma conta feita pelo sistema
  (faturamento do CNPJ de cada linha) e mostra quanto a planilha soma em dobro por causa de CNPJ repetido.

## Regras do cálculo (ajustáveis na aba "Regras do cálculo")

O usuário escolhe cada regra na tela; elas ficam gravadas no banco (tabela `configuracoes`).
Os valores padrão estão em `REGRAS_PADRAO` (`app/regras.py`).

| Regra | Opções | Padrão |
|---|---|---|
| **Coluna de valor** | TOTAL VENDA (AL) · VLR TOTAL (AD) | TOTAL VENDA, como a planilha |
| **Tipos de nota** | cada tipo soma, desconta ou fica de fora; e o que fazer com tipos fora da lista | todos somam, como a planilha |
| **Só RECEITA = SIM** | sim · não | não, como a planilha |
| **Lojas de rede** | CNPJ exato da loja · rede inteira (raiz do CNPJ) em cada loja · rede dividida igualmente entre as lojas | CNPJ exato |
| **Custo do promotor** | + encargos (% do salário) + custo extra fixo por mês | 0% e R$ 0 |
| **Divisão do custo entre lojas** | igual · proporcional às visitas por semana | igual |
| **Semanas por mês** | usado no custo por visita | 4,33 |
| **Faixas de cor do % de custo** | amarelo a partir de X% · vermelho a partir de Y% | 15% e 30% |

Regras fixas:
- **Custo por competência:** em cada mês vale o último reajuste até aquele mês. Conta a partir do mês de
  admissão e até o mês de desligamento (meses inteiros). Reajuste não muda os meses anteriores.
- **Roteiro com datas:** o faturamento de cada mês vai para o promotor cujo vínculo estava vigente no
  **último dia do mês**. Trocar o promotor não muda o que foi atribuído ao anterior.
- **PDVs com o mesmo CNPJ** (CNPJ + nome diferentes):
  1. se cada loja tem o seu **COD CLI** no cadastro e eles são diferentes, o faturamento é separado pelo COD CLI;
  2. se não, o faturamento do CNPJ conta **uma vez só** nos totais e as lojas aparecem com o aviso
     "faturamento compartilhado com outra loja";
  3. essas lojas são listadas em **Pendências**, para confirmar se são lojas diferentes ou erro de digitação.
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

**Banco e usuários**
- As migrations rodam sozinhas quando o back-end inicia. Para rodar à mão: `cd backend && alembic upgrade head`.
- Na primeira vez, sem nenhum usuário no banco, o sistema cria um **administrador** com `APP_USUARIO` e
  `APP_SENHA` do `.env`. Depois disso os usuários são cadastrados na tela **Usuários** e o `.env` não é mais
  usado para login. Para trocar a senha, use **Meu perfil**.
- Dados importados por versões anteriores (tabelas `promotores` e `roteiro` antigas) são convertidos para os
  cadastros automaticamente, uma única vez. O **faturamento** antigo (só o total por mês) não é convertido:
  importe o arquivo de novo, agora item a item (o sistema avisa na Visão geral).

Testes: `cd backend && pytest`

## Publicar no Render (quando for a hora)

- **Build:** `pip install -r backend/requirements.txt && cd frontend && npm ci && npm run build`
- **Start:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Variáveis de ambiente:** `APP_USUARIO` e `APP_SENHA` (só para criar o primeiro administrador), `SECRET_KEY`,
  `DATABASE_URL` (Postgres do Render), `AMBIENTE=producao`
- O FastAPI entrega o React já compilado (`frontend/dist`): é **um serviço só**.
- Confirme se o ambiente Python do Render tem Node disponível para o `npm run build`. Se não tiver, a
  alternativa é fazer o build com Docker.

## Segurança

- O repositório deve ser **privado**.
- **Planilhas reais nunca vão para o GitHub.** O `.gitignore` bloqueia `.xlsx`/`.csv`, exceto os exemplos fictícios.
- Senhas e chaves só em variáveis de ambiente (`.env` local, Environment no Render).
- Todas as rotas `/api` exigem login, exceto `/api/login`. `/health` é público.
- Perfis: **administrador** altera tudo; **consulta** e **supervisor** só consultam. (A visão restrita do
  supervisor à própria equipe fica para a Fase 4.)
- Senhas guardadas com hash scrypt; 5 tentativas erradas bloqueiam o login por 15 minutos.
- Exportação para Excel (CSV) protegida contra fórmulas (`=`, `+`, `-`, `@`).
