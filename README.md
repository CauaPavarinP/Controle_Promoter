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
| **Lojas por UF** | Substitui as abas SC, SP, PR, MG e RS: supervisor, promotor, CNPJ, PDV, cidade, UF, JAN…DEZ e TOTAL. Botões por UF | Importar as abas da planilha ou **cadastrar loja na tela** (promotor, CNPJ, nome, cidade, UF, visitas/semana). Cada loja tem o menu **Alterar…** (editar dados, visitas, trocar promotor, encerrar). O quadro **Colaboradores não encontrados** lista os nomes da coluna Colaborador que não bateram com nenhum promotor, sugere o nome parecido e liga todas as lojas daquele nome ao promotor escolhido (ou descarta). A ligação fica **lembrada** (tabela `apelidos_colaborador`): nas próximas importações esse nome já vai direto para o promotor; dá para esquecer uma ligação feita por engano |

- Com filtro de **UF, cidade ou PDV**, o custo é só a parte do promotor atribuída às lojas filtradas (o resto é de
  lojas de outros lugares).
- **Filtros** no Resumo e em Lojas por UF, numa barra que fica fixa ao rolar: período, supervisor e UF; promotor,
  cidade, PDV e atalhos de período em "Mais filtros". Os filtros escolhidos aparecem como etiquetas com ✕.
- O **faturamento das lojas vem do ERP**: o sistema soma as notas do CNPJ de cada loja, mês a mês (como o
  SOMASE da planilha). **CNPJ que aparece em mais de uma loja é dividido** entre elas (e, dentro da loja, entre os
  promotores dela): a soma por promotor, supervisor ou UF sempre dá o total.
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
  scripts/            planilhas FICTÍCIAS para teste, modelo das agências, conversor da planilha, limpeza
  exemplos/           planilhas fictícias geradas
  tests/              testes automatizados (pytest)
frontend/           tela em React (Vite)
  src/components/     Login, Painel (menu), Resumo, Faturamento, Promotores, Lojas por UF
  src/components/cadastros/  formulários de promotores, supervisores, PDVs, roteiros, usuários e perfil
```

## Importações (só administrador)

O sistema é alimentado por duas fontes:

| Onde | Arquivo | O que faz |
|---|---|---|
| **Faturamento** | Relatório de faturamento do Focco: o ".xls" do **Gera Excel** (é HTML), o **Gera TXT**, ou .xlsx/.csv | Prévia (período, linhas, total, notas, clientes, linhas com erro, CNPJs sem agência) e só grava ao confirmar. Até 300 MB em .xls/.txt/.csv (configurável: `LIMITE_FATURAMENTO_MB` no `.env`; no Render deixe 300); 150 MB em .xlsx. |
| **Agências** | Arquivo de cada agência, MEI ou da própria 101 (CLT) no modelo "Atendimento das agências" (baixar na aba Agências) | Uma linha por loja × mês: agência, tipo, CNPJ, loja, promotor, visitas e valor do mês. Prévia com avisos (CNPJ inválido, lojas repetidas em outra agência, nomes parecidos, linhas descartadas). |

- **Mês que já existe** (faturamento) ou **agência + mês que já existe** (agências): só substitui com confirmação.
- **Histórico** com **desfazer**. "Apagar os dados das agências" guarda um backup no banco antes (aba Agências).
- **Faturamento:** valor = VLR TOTAL (bruto). "Vale a pena?" = custo do atendimento até 3% do faturamento das lojas
  (limite editável na tela).

### Promotores CLT da 101 a partir da planilha do Maurício

A planilha "ROTEIROS X FATURAMENTOS" (abas PROMOTORES BRASIL e SC/SP/PR/MG/RS) pode ser convertida no modelo das
agências, para não redigitar os CLT. Roda no computador onde está a planilha (nada é enviado):

```
cd backend
python scripts/converter_planilha_mauricio.py "C:\caminho\ROTEIROS X FATURAMENTOS.xlsm" --de 2026-01 --ate 2026-09
```

- Valor de cada loja no mês = custo do promotor (TOTAL da PROMOTORES BRASIL) ÷ lojas do roteiro dele.
- Agência "101 do Brasil", Tipo CLT, código do promotor e supervisor; quem foi admitido depois do mês
  não entra naquele mês.
- O arquivo gerado tem a aba **Conferência** (e o mesmo resumo na tela): promotor do roteiro sem cadastro de custo,
  cadastro sem loja, nomes ligados por semelhança, CNPJ inválido, supervisor "#N/A".
- Depois, importe o arquivo gerado na aba **Agências**, como o de qualquer agência. O arquivo gerado tem dados reais:
  não coloque no repositório.

## Regras do cálculo

Valores padrão em `REGRAS_PADRAO` (`app/regras.py`): valor = TOTAL VENDA, todos os tipos de nota somam (como a
planilha), custo de cada loja proporcional às visitas por semana. Nesta versão não há tela para mudar as regras.

Regras fixas:
- **Período:** `AAAA-MM`, mês 01 a 12, até 5 anos. **Meses depois do mês atual ficam fora** (não há custo projetado).
- **Custo por competência:** em cada mês vale o último reajuste até aquele mês. Conta a partir do mês de
  admissão e até o mês de desligamento (meses inteiros). Reajuste não muda os meses anteriores.
- **Promotor só conta nos meses em que estava contratado:** antes da admissão (ou depois do desligamento) ele não
  entra na contagem, as lojas dele não contam e o faturamento delas não vai para ele.
- **Roteiro com datas:** o faturamento de cada mês vai para o promotor cujo vínculo estava vigente no
  **último dia do mês**. Trocar o promotor não muda o que foi atribuído ao anterior.
- **PDVs com o mesmo CNPJ** (CNPJ + nome diferentes):
  1. se cada loja tem o seu **COD CLI** no cadastro e eles são diferentes, o faturamento é separado pelo COD CLI;
  2. se não, o faturamento do CNPJ é **dividido em partes iguais** entre as lojas (no mês) e as lojas aparecem
     com o aviso "faturamento compartilhado com outra loja";
- Loja com faturamento compartilhado: o % de custo da loja não é calculado.
- PDV com mais de um promotor ao mesmo tempo: o faturamento da loja é dividido em partes iguais entre eles
  (antes aparecia cheio para cada um — opção "a" do documento, seção 5.5 —, e a soma por promotor passava do
  total; **confirmar com o Maurício**).

## Pendências com o Maurício / Rayan

As perguntas em aberto estão em [`docs/perguntas-mauricio.md`](docs/perguntas-mauricio.md).

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

## Publicar no Render

- O serviço é criado com **Docker** (`Dockerfile` na raiz): uma etapa com Node gera o `frontend/dist` e a imagem
  final só com Python roda o FastAPI, que entrega o React. É **um serviço só**.
- **Banco:** Postgres do Render, na variável `DATABASE_URL`. As migrations rodam sozinhas ao iniciar.
- **Variáveis de ambiente:** `DATABASE_URL`, `SECRET_KEY`, `AMBIENTE=producao` (já vem no Dockerfile) e
  `APP_USUARIO` / `APP_SENHA` (só para criar o primeiro administrador; depois pode apagar).
- Para rodar os testes num Postgres, como no Render: `TEST_DATABASE_URL=postgresql://... pytest`.

## Segurança

- **Login:** senha com hash scrypt; bloqueio de 15 min após 5 erros; o login leva o mesmo tempo para usuário que
  existe ou não (não dá para descobrir usuários medindo o tempo).
- **Sessão:** cookie assinado, `HttpOnly`, `Secure` em produção e `SameSite=Lax`, válido por 12 h. Cada usuário tem
  uma chave de sessão: **Sair**, **trocar a senha** ou receber **senha nova** troca a chave e derruba os cookies
  antigos (inclusive um cookie roubado).
- **Permissões:** toda rota de consulta exige login; toda rota que altera dados exige administrador.
- **Pedidos de outro site (CSRF):** além do `SameSite=Lax`, pedidos que alteram dados com `Origin` de outro site são
  recusados.
- **Cabeçalhos:** `Content-Security-Policy` (só scripts do próprio site), `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy` e `Strict-Transport-Security` em produção.
- **Uploads:** só `.xlsx`, `.xlsm` e `.csv`, até 150 MB. **Excel exportado:** texto que começa com `=`, `+`, `@` não
  vira fórmula.
- **Produção:** `/docs` desligado; exige `SECRET_KEY` e `DATABASE_URL`; o contêiner roda sem root.
- Testes: `backend/tests/test_seguranca.py`.
- **Em aberto (decisão do Maurício):** os perfis consulta e supervisor veem o custo (salário) dos promotores.
