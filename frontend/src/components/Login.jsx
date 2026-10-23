import { useState } from 'react'
import { api } from '../api.js'

export default function Login({ aoEntrar }) {
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function entrar(evento) {
    evento.preventDefault()
    setErro('')
    setEnviando(true)
    try {
      const dados = await api.login(usuario, senha)
      aoEntrar(dados.usuario)
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="login-fundo">
      <form className="login-caixa" onSubmit={entrar}>
        <h1>Controle de Promotores</h1>
        <p className="subtitulo">Comercial • 101 do Brasil</p>
        <label>
          Usuário
          <input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoFocus />
        </label>
        <label>
          Senha
          <input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} />
        </label>
        {erro && <p className="erro">{erro}</p>}
        <button type="submit" disabled={enviando || !usuario || !senha}>
          {enviando ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
