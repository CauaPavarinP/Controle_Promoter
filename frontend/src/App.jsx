import { useEffect, useState } from 'react'
import { api, definirAoExpirarSessao } from './api.js'
import Login from './components/Login.jsx'
import Painel from './components/Painel.jsx'

export default function App() {
  // undefined = verificando sessão; null = não logado; objeto = usuário logado (nome, perfil…)
  const [usuario, setUsuario] = useState(undefined)

  useEffect(() => {
    definirAoExpirarSessao(() => setUsuario(null))
    api.sessao()
      .then((dados) => setUsuario(dados))
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
