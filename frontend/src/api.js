// Chamadas ao back-end. Se a sessão expirar (401), avisa o App para voltar ao login.
let aoExpirarSessao = () => {}

export function definirAoExpirarSessao(funcao) {
  aoExpirarSessao = funcao
}

async function requisitar(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, { credentials: 'same-origin', ...opcoes })
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
