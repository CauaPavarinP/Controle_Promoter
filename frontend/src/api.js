// Chamadas ao back-end. Se a sessão expirar (401), avisa o App para voltar ao login.
let aoExpirarSessao = () => {}

export function definirAoExpirarSessao(funcao) {
  aoExpirarSessao = funcao
}

// Igual ao limite do servidor (backend/app/limites.py). Acima disso o servidor corta a conexão no meio do envio e o
// navegador só diz "Failed to fetch"; por isso o tamanho é conferido aqui antes de enviar.
export const LIMITE_ARQUIVO_MB = 150

async function requisitar(caminho, opcoes = {}) {
  let resposta
  try {
    resposta = await fetch(caminho, { credentials: 'same-origin', ...opcoes })
  } catch {
    throw new Error(opcoes.body instanceof FormData
      ? 'A conexão com o servidor caiu durante o envio do arquivo. Confira a internet e tente de novo; se o arquivo ' +
        'for muito grande, exporte um período menor.'
      : 'Não consegui falar com o servidor. Confira a internet e tente de novo.')
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
    if (mb > LIMITE_ARQUIVO_MB) {
      return Promise.reject(new Error(
        `O arquivo tem ${Math.round(mb)} MB e o limite é ${LIMITE_ARQUIVO_MB} MB. Exporte do ERP um período menor ` +
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
