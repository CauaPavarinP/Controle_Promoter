import { useEffect, useState } from 'react'
import { api, definirAoExpirarSessao } from './api.js'
import Login from './components/Login.jsx'
import Painel from './components/Painel.jsx'

export default function App() {
  // undefined = verificando sessão; null = não logado; texto = usuário logado
  const [usuario, setUsuario] = useState(undefined)

  useEffect(() => {
    definirAoExpirarSessao(() => setUsuario(null))
    api.sessao()
      .then((dados) => setUsuario(dados.usuario))
      .catch(() => setUsuario(null))
  }, [])

  async function sair() {
    await api.logout().catch(() => {})
    setUsuario(null)
  }

  if (usuario === undefined) return <div className="carregando-tela">Carregando…</div>
  if (!usuario) return <Login aoEntrar={setUsuario} />
  return <Painel usuario={usuario} aoSair={sair} />
}
