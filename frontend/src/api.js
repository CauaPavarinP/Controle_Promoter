// Chamadas ao back-end. Se a sessão expirar (401), avisa o App para voltar ao login.
let aoExpirarSessao = () => {}

export function definirAoExpirarSessao(funcao) {
  aoExpirarSessao = funcao
}

// Igual ao limite do servidor (backend/app/limites.py). Acima disso o servidor corta a conexão no meio do envio e o
// navegador só diz "Failed to fetch"; por isso o tamanho é conferido aqui antes de enviar.
export const LIMITE_ARQUIVO_MB = 150
// Faturamento do ERP em texto (.xls do Focco, que é HTML, .txt, .csv): lido aos poucos no servidor, aceita mais.
export const LIMITE_FATURAMENTO_TEXTO_MB = 300

function limiteDoArquivo(caminho, arquivo) {
  const texto = /\.(xls|txt|csv)$/i.test(arquivo.name || '')
  return caminho.includes('/faturamento/') && texto ? LIMITE_FATURAMENTO_TEXTO_MB : LIMITE_ARQUIVO_MB
}

// Tempo máximo de espera. O servidor gratuito do Render "dorme" e leva ~50 s para acordar: 60 s cobre isso.
// Envio de arquivo e gravação de importação demoram mais (arquivo grande, servidor lento): 15 minutos.
export const TEMPO_LIMITE_MS = 60_000
const TEMPO_LIMITE_LONGO_MS = 15 * 60_000
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
  const limite = longo ? TEMPO_LIMITE_LONGO_MS : TEMPO_LIMITE_MS
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
  enviarArquivo: (caminho, arquivo) => {
    const mb = arquivo.size / 1024 / 1024
    const limite = limiteDoArquivo(caminho, arquivo)
    if (mb > limite) {
      return Promise.reject(new Error(
        `O arquivo tem ${Math.round(mb)} MB e o limite é ${limite} MB. Exporte do ERP um período menor ` +
        '(por exemplo, um ou dois meses por vez) e importe um arquivo de cada vez: o sistema junta os meses.'))
    }
    const corpo = new FormData()
    corpo.append('arquivo', arquivo)
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
