import { useState } from 'react'
import { http } from '../../api.js'
import { Campo } from '../ui.jsx'

const NOMES_PERFIL = { admin: 'Administrador', consulta: 'Consulta', supervisor: 'Supervisor' }

export default function MeuPerfil({ usuario, aoTrocarSenha }) {
  const [dados, setDados] = useState({ senha_atual: '', nova_senha: '', repetir: '' })
  const [mensagem, setMensagem] = useState(null)

  async function trocar(evento) {
    evento.preventDefault()
    if (dados.nova_senha !== dados.repetir) {
      setMensagem({ erro: true, texto: 'A nova senha e a repetição estão diferentes.' })
      return
    }
    try {
      await http.put('/api/minha-senha', { senha_atual: dados.senha_atual, nova_senha: dados.nova_senha })
      setDados({ senha_atual: '', nova_senha: '', repetir: '' })
      setMensagem({ erro: false, texto: 'Senha trocada.' })
      aoTrocarSenha?.()
    } catch (e) {
      setMensagem({ erro: true, texto: e.message })
    }
  }

  return (
    <>
      <section className="bloco">
        <dl className="dados">
          <dt>Nome</dt><dd>{usuario.nome}</dd>
          <dt>Login</dt><dd>{usuario.usuario}</dd>
          <dt>Perfil</dt><dd>{NOMES_PERFIL[usuario.perfil]}</dd>
        </dl>
      </section>
      <form className="bloco formulario-estreito" onSubmit={trocar}>
        <h2>Trocar senha</h2>
        <Campo rotulo="Senha atual">
          <input type="password" value={dados.senha_atual} onChange={(e) => setDados({ ...dados, senha_atual: e.target.value })} />
        </Campo>
        <Campo rotulo="Nova senha" dica="Pelo menos 8 caracteres.">
          <input type="password" value={dados.nova_senha} onChange={(e) => setDados({ ...dados, nova_senha: e.target.value })} />
        </Campo>
        <Campo rotulo="Repita a nova senha">
          <input type="password" value={dados.repetir} onChange={(e) => setDados({ ...dados, repetir: e.target.value })} />
        </Campo>
        {mensagem && <p className={mensagem.erro ? 'erro' : 'texto-ok'}>{mensagem.texto}</p>}
        <button type="submit" disabled={!dados.senha_atual || !dados.nova_senha}>Trocar senha</button>
      </form>
    </>
  )
}
