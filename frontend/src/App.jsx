import { useEffect, useState } from 'react'
import { aoMudarDemora, api, definirAoExpirarSessao } from './api.js'
import Login from './components/Login.jsx'
import Painel from './components/Painel.jsx'
import MeuPerfil from './components/cadastros/MeuPerfil.jsx'

// Aparece quando alguma resposta do servidor passa de 3 s (o servidor gratuito "acorda" em até ~50 s).
function AvisoConectando() {
  const [demorando, setDemorando] = useState(false)
  useEffect(() => aoMudarDemora(setDemorando), [])
  if (!demorando) return null
  return (
    <div className="aviso-conectando nao-imprimir" role="status" aria-live="polite">
      Conectando ao servidor… Se ele estava parado, pode levar até 1 minuto para acordar.
    </div>
  )
}

export default function App() {
  return (
    <>
      <AvisoConectando />
      <Conteudo />
    </>
  )
}

function Conteudo() {
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
