import { useEffect, useState } from 'react'
import { api, definirAoExpirarSessao } from './api.js'
import Login from './components/Login.jsx'
import Painel from './components/Painel.jsx'
import MeuPerfil from './components/cadastros/MeuPerfil.jsx'

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
  // Senha provisória (criada pelo administrador): troca obrigatória antes de usar o sistema.
  if (usuario.trocar_senha) {
    return (
      <main className="troca-obrigatoria">
        <h1>Crie a sua senha</h1>
        <p className="dica">
          Você entrou com uma senha provisória, criada pelo administrador. Para continuar, digite essa senha em
          "Senha atual" e escolha uma senha nova, que só você vai saber.
        </p>
        <MeuPerfil usuario={usuario} aoTrocarSenha={() => setUsuario({ ...usuario, trocar_senha: false })} />
        <button className="secundario" onClick={sair}>Sair</button>
      </main>
    )
  }
  return <Painel usuario={usuario} aoSair={sair} />
}
