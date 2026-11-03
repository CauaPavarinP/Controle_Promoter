# Controle de Promotores

Sistema web para comparar o **custo dos promotores (repositores)** com o **faturamento das lojas** que
eles atendem. Substitui a planilha "ROTEIROS X FATURAMENTOS".

Pedido do Maurício (Comercial • 101 do Brasil), a validar com o Rayan.

## O que o sistema faz

Versão simplificada (branch `versao-simplificada`), com 4 abas:

| Aba | O que mostra | Como atualiza |
|---|---|---|
| **Resumo** | 4 cartões (custo, faturamento, custo ÷ faturamento, promotores e lojas) e uma tabela que abre em níveis **UF da loja → supervisor → promotor** (promotores, lojas, visitas, custo, faturamento, %), no lugar da aba RESUMO da planilha. Promotor que atende mais de uma UF aparece em cada uma com a sua parte do custo. Clicar no promotor abre as lojas dele | Calculado a partir das outras abas |
| **Faturamento** | Tudo o que o ERP faturou no período, por UF e por cliente, mês a mês (inclusive clientes fora do roteiro). Clicar num valor abre as notas | **Importar faturamento do ERP** (arquivo no layout da aba FATURAMENTO ou a própria planilha), com pré-visualização, confirmação e desfazer |
| **Promotores** | Promotores e repositores com custo por competência e as lojas de cada um; supervisores | Importar a aba PROMOTORES BRASIL ou cadastrar/editar na tela |
| **Lojas por UF** | Substitui as abas SC, SP, PR, MG e RS: supervisor, promotor, CNPJ, PDV, cidade, UF, JAN…DEZ e TOTAL. Botões por UF | Importar as abas da planilha ou **cadastrar loja na tela** (promotor, CNPJ, nome, cidade, UF, visitas/semana). Cada loja tem o menu **Alterar…** (editar dados, visitas, trocar promotor, encerrar). O quadro **Colaboradores não encontrados** lista os nomes da coluna Colaborador que não bateram com nenhum promotor, sugere o nome parecido e liga todas as lojas daquele nome ao promotor escolhido (ou descarta) |

- Com filtro de **UF, cidade ou PDV**, o custo é só a parte do promotor atribuída às lojas filtradas (o resto é de
  lojas de outros lugares).
- **Filtros** no Resumo e em Lojas por UF, numa barra que fica fixa ao rolar: período, supervisor e UF; promotor,
  cidade, PDV e atalhos de período em "Mais filtros". Os filtros escolhidos aparecem como etiquetas com ✕.
- O **faturamento das lojas vem do ERP**: o sistema soma as notas do CNPJ de cada loja, mês a mês (como o
  SOMASE da planilha), mas **CNPJ que aparece em mais de uma loja conta uma vez só** nos totais.
- Todas as tabelas ordenam por coluna e exportam para **Excel (.xlsx) formatado** (`app/exportar.py`): título, filtros
  em uso, cabeçalho colorido e fixo, filtro nas colunas, R$ e % já formatados (zero aparece como "-"), linhas
  alternadas e total em negrito. Botão **Imprimir** no Resumo e em Lojas por UF.
- **Visitas por semana:** a planilha não tem essa informação. Enquanto não for preenchida (Lojas por UF → Alterar…
  → Visitas por semana), o custo do promotor é dividido em partes iguais entre as lojas dele.
- **Usuários** com perfis (administrador, consulta, supervisor), senha criptografada e bloqueio após 5 tentativas.
- Só o administrador importa e cadastra; os outros perfis consultam.

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
  src/components/     Login, Painel (menu), Resumo, Faturamento, Promotores, Lojas por UF
  src/components/cadastros/  formulários de promotores, supervisores, PDVs, roteiros, usuários e perfil
```

## Importações (só administrador)

| Onde | Arquivo | O que faz |
|---|---|---|
| **Faturamento** | Exportação do ERP no layout da aba FATURAMENTO (ou a planilha inteira) | Mostra a **pré-visualização** (período, linhas, TOTAL VENDA, notas, clientes, linhas com erro, CNPJs sem roteiro) e só grava ao confirmar. |
| **Promotores** | Planilha com a aba PROMOTORES BRASIL | Cria ou atualiza pelo código; custo diferente vira reajuste a partir do mês corrente. |
| **Lojas por UF** | Planilha com as abas SC, SP, PR, MG, RS | Cria PDVs (CNPJ + nome) e vínculos novos; colaborador sem promotor fica pendente. Importe os promotores antes. |

- Aba sem coluna UF/Estado preenchida (caso da aba PR): a UF é o nome da aba. Na aba PR a cidade está na
  coluna "Coluna1", que também é reconhecida.
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

## Regras do cálculo

Valores padrão em `REGRAS_PADRAO` (`app/regras.py`): valor = TOTAL VENDA, todos os tipos de nota somam (como a
planilha), custo de cada loja proporcional às visitas por semana. Nesta versão não há tela para mudar as regras.

Regras fixas:
- **Custo por competência:** em cada mês vale o último reajuste até aquele mês. Conta a partir do mês de
  admissão e até o mês de desligamento (meses inteiros). Reajuste não muda os meses anteriores.
- **Roteiro com datas:** o faturamento de cada mês vai para o promotor cujo vínculo estava vigente no
  **último dia do mês**. Trocar o promotor não muda o que foi atribuído ao anterior.
- **PDVs com o mesmo CNPJ** (CNPJ + nome diferentes):
  1. se cada loja tem o seu **COD CLI** no cadastro e eles são diferentes, o faturamento é separado pelo COD CLI;
  2. se não, o faturamento do CNPJ conta **uma vez só** nos totais e as lojas aparecem com o aviso
     "faturamento compartilhado com outra loja";
- Loja com faturamento compartilhado: o % de custo da loja não é calculado.
- PDV com mais de um promotor ao mesmo tempo: o faturamento aparece cheio para cada um (opção "a" do
  documento, seção 5.5).

## Pendências com o Maurício / Rayan

- Cada loja de rede tem código de cliente próprio no ERP, ou tudo é faturado na matriz?
- Existe planilha de roteiro com a frequência de visitas por loja?
- A integração direta com o ERP (sem exportar arquivo) depende de acesso ao banco ou à API do ERP, a combinar com a TI.
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

Abra http://localhost:5173, entre com o usuário/senha do `.env` e importe, nesta ordem, os arquivos de
`backend/exemplos/`: `promotores_exemplo.xlsx` na aba **Promotores**, `roteiro_exemplo.xlsx` em **Lojas por UF** e
`faturamento_exemplo.xlsx` em **Faturamento**.

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
