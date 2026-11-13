// Chamadas ao back-end. Se a sessão expirar (401), avisa o App para voltar ao login.
let aoExpirarSessao = () => {}

export function definirAoExpirarSessao(funcao) {
  aoExpirarSessao = funcao
}

// Limites do servidor (GET /api/limites; o do faturamento em texto é configurável: LIMITE_FATURAMENTO_MB no .env).
// Acima deles o servidor corta a conexão no meio do envio e o navegador só diz "Failed to fetch"; por isso o tamanho
// é conferido aqui antes de enviar. Os valores abaixo valem se o servidor não responder.
const LIMITES_PADRAO = { faturamento_texto_mb: null, planilha_mb: 150 }   // null = sem limite
let limitesDoServidor = null

async function limiteDoArquivo(caminho, arquivo) {
  if (!limitesDoServidor) {
    limitesDoServidor = await requisitar('/api/limites').catch(() => null)
  }
  const limites = { ...LIMITES_PADRAO, ...(limitesDoServidor || {}) }
  // Faturamento: lido em partes no servidor, sem limite de tamanho (a não ser que LIMITE_FATURAMENTO_MB exista).
  return caminho.includes('/faturamento/') ? limites.faturamento_texto_mb : limites.planilha_mb
}

// Tempo máximo de espera. O servidor gratuito do Render "dorme" e leva ~50 s para acordar: 60 s cobre isso.
// Gravação de importação demora mais (arquivo grande, servidor lento): 1 hora. Envio de arquivo: 3 horas (o
// faturamento não tem limite de tamanho; um arquivo grande numa internet lenta leva muito tempo para subir).
export const TEMPO_LIMITE_MS = 60_000
const TEMPO_LIMITE_LONGO_MS = 60 * 60_000
const TEMPO_LIMITE_ENVIO_MS = 3 * 60 * 60_000
const AVISAR_DEMORA_MS = 3_000

// Pedidos que passaram de 3 s esperando: o App mostra "Conectando ao servidor…". Envio de arquivo não entra
// (a tela de importação já mostra o andamento).
let demorados = 0
let ouvintesDemora = []

export function aoMudarDemora(funcao) {
  ouvintesDemora.push(funcao)
  return () => { ouvintesDemora = ouvintesDemora.filter((f) => f !== funcao) }
}

function mudarDemora(diferenca) {
  demorados += diferenca
  ouvintesDemora.forEach((f) => f(demorados > 0))
}

function ehLongo(caminho, opcoes) {
  return opcoes.body instanceof FormData || (opcoes.method === 'POST' && caminho.startsWith('/api/importacoes/'))
}

async function requisitar(caminho, opcoes = {}) {
  const longo = ehLongo(caminho, opcoes)
  const limite = opcoes.body instanceof FormData ? TEMPO_LIMITE_ENVIO_MS : longo ? TEMPO_LIMITE_LONGO_MS : TEMPO_LIMITE_MS
  const controle = new AbortController()
  const tempo = setTimeout(() => controle.abort(), limite)
  let avisou = false
  const demora = longo ? null : setTimeout(() => { avisou = true; mudarDemora(1) }, AVISAR_DEMORA_MS)
  let resposta
  try {
    resposta = await fetch(caminho, { credentials: 'same-origin', ...opcoes, signal: controle.signal })
  } catch (e) {
    if (e.name === 'AbortError') {
      throw new Error(`O servidor não respondeu em ${Math.round(limite / 1000)} segundos. Se ele estava parado, pode ` +
        'levar até 1 minuto para acordar: espere um pouco e tente de novo.')
    }
    throw new Error(opcoes.body instanceof FormData
      ? 'A conexão com o servidor caiu durante o envio do arquivo. Confira a internet e tente de novo; se o arquivo ' +
        'for muito grande, exporte um período menor.'
      : 'Não consegui falar com o servidor. Confira a internet e tente de novo.')
  } finally {
    clearTimeout(tempo)
    if (demora) clearTimeout(demora)
    if (avisou) mudarDemora(-1)
  }
  if (resposta.status === 401 && caminho !== '/api/login') {
    aoExpirarSessao()
    throw new Error('Sessão expirada. Entre novamente.')
  }
  const dados = await resposta.json().catch(() => ({}))
  if (!resposta.ok) {
    throw new Error(dados.detail || 'Erro ao falar com o servidor.')
  }
  return dados
}

const json = (metodo, corpo) => ({
  method: metodo,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(corpo ?? {}),
})

// Atalhos para os cadastros: api.get('/api/promotores'), api.post('/api/pdvs', dados)…
export const http = {
  get: (caminho) => requisitar(caminho),
  post: (caminho, corpo) => requisitar(caminho, json('POST', corpo)),
  put: (caminho, corpo) => requisitar(caminho, json('PUT', corpo)),
  delete: (caminho) => requisitar(caminho, { method: 'DELETE' }),
  enviarArquivo: async (caminho, arquivo, campos = {}) => {
    const mb = arquivo.size / 1024 / 1024
    const limite = await limiteDoArquivo(caminho, arquivo)
    if (limite && mb > limite) {
      throw new Error(
        `O arquivo tem ${Math.round(mb)} MB e o limite é ${limite} MB. Exporte do ERP um período menor ` +
        '(por exemplo, um ou dois meses por vez) e importe um arquivo de cada vez: o sistema junta os meses.')
    }
    const corpo = new FormData()
    corpo.append('arquivo', arquivo)
    for (const [nome, valor] of Object.entries(campos)) if (valor) corpo.append(nome, valor)
    return requisitar(caminho, { method: 'POST', body: corpo })
  },
}

export const api = {
  sessao: () => requisitar('/api/sessao'),
  login: (usuario, senha) =>
    requisitar('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, senha }),
    }),
  logout: () => requisitar('/api/logout', { method: 'POST' }),
  opcoes: () => requisitar('/api/opcoes'),
  painel: (filtros) => requisitar('/api/painel?' + new URLSearchParams(filtros)),
  regras: () => requisitar('/api/regras'),
  salvarRegras: (regras) =>
    requisitar('/api/regras', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(regras),
    }),
  importar: (tipo, arquivo) => {
    const corpo = new FormData()
    corpo.append('arquivo', arquivo)
    return requisitar(`/api/importar/${tipo}`, { method: 'POST', body: corpo })
  },
}
