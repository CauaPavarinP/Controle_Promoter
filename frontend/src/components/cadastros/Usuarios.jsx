import { useState } from 'react'
import { http } from '../../api.js'
import { Campo, Modal, Situacao, Tabela, useLista } from '../ui.jsx'

const PERFIS = {
  admin: 'Administrador — tudo: cadastros, importações, regras e usuários',
  consulta: 'Consulta — vê o painel e os cadastros, sem alterar',
  supervisor: 'Supervisor — por enquanto igual a Consulta (visão só da equipe virá depois)',
}

function SenhaGerada({ titulo, senha, aoFechar }) {
  return (
    <Modal titulo={titulo} aoFechar={aoFechar} rodape={<button onClick={aoFechar}>Já anotei</button>}>
      <p>Senha provisória (aparece só agora). No primeiro acesso, o sistema pede para a pessoa criar a própria senha:</p>
      <p className="senha-gerada">{senha}</p>
      <button className="secundario" onClick={() => navigator.clipboard?.writeText(senha)}>Copiar</button>
    </Modal>
  )
}

export default function Usuarios({ eu }) {
  const [usuarios, recarregar, erroLista] = useLista(() => http.get('/api/usuarios'))
  const [supervisores] = useLista(() => http.get('/api/supervisores'))
  const [edicao, setEdicao] = useState(null)
  const [senha, setSenha] = useState(null)
  const [erro, setErro] = useState('')

  async function executar(acao) {
    setErro('')
    try {
      const resposta = await acao()
      recarregar()
      return resposta || true
    } catch (e) {
      setErro(e.message)
      return null
    }
  }

  async function salvar() {
    const corpo = { nome: edicao.nome, perfil: edicao.perfil, supervisor_id: edicao.supervisor_id ? Number(edicao.supervisor_id) : null }
    const resposta = await executar(() =>
      edicao.id ? http.put(`/api/usuarios/${edicao.id}`, corpo) : http.post('/api/usuarios', { ...corpo, usuario: edicao.usuario }))
    if (!resposta) return
    setEdicao(null)
    if (resposta.senha_provisoria) setSenha({ titulo: `Usuário ${edicao.usuario} criado`, senha: resposta.senha_provisoria })
  }

  async function gerarSenha(u) {
    if (!window.confirm(`Gerar uma nova senha para ${u.nome}? A senha atual deixa de funcionar.`)) return
    const resposta = await executar(() => http.post(`/api/usuarios/${u.id}/nova-senha`))
    if (resposta) setSenha({ titulo: `Nova senha de ${u.nome}`, senha: resposta.senha_provisoria })
  }

  if (!usuarios) return erroLista ? <div className="erro-caixa">{erroLista}</div> : <p>Carregando…</p>

  return (
    <section className="bloco">
      <div className="bloco-cabecalho">
        <p className="dica">Cada pessoa tem o próprio login. As senhas ficam guardadas criptografadas.</p>
        <button onClick={() => setEdicao({ nome: '', usuario: '', perfil: 'consulta', supervisor_id: '' })}>+ Novo usuário</button>
      </div>
      {erro && <div className="erro-caixa">{erro}</div>}
      <Tabela
        linhas={usuarios}
        colunas={[
          { campo: 'nome', titulo: 'Nome' },
          { campo: 'usuario', titulo: 'Login' },
          { campo: 'perfil', titulo: 'Perfil', mostrar: (u) => PERFIS[u.perfil].split(' — ')[0] },
          {
            campo: 'ativo', titulo: 'Situação',
            mostrar: (u) => (u.bloqueado ? <span className="situacao inativa">Bloqueado (tentativas)</span> : <Situacao ativo={u.ativo} />),
          },
          {
            campo: 'acoes', titulo: '', semOrdem: true,
            mostrar: (u) => (
              <div className="acoes">
                <button className="secundario" onClick={() => setEdicao({ ...u, supervisor_id: u.supervisor_id ?? '' })}>Editar</button>
                <button className="secundario" onClick={() => gerarSenha(u)}>Nova senha</button>
                {u.id !== eu.id && (u.ativo ? (
                  <button className="secundario perigo" onClick={() => executar(() => http.post(`/api/usuarios/${u.id}/inativar`))}>Inativar</button>
                ) : (
                  <button className="secundario" onClick={() => executar(() => http.post(`/api/usuarios/${u.id}/reativar`))}>Reativar</button>
                ))}
              </div>
            ),
          },
        ]}
      />

      {edicao && (
        <Modal titulo={edicao.id ? `Editar ${edicao.usuario}` : 'Novo usuário'} aoFechar={() => setEdicao(null)}
          rodape={<button onClick={salvar} disabled={!edicao.nome || (!edicao.id && !edicao.usuario)}>Salvar</button>}>
          <Campo rotulo="Nome"><input value={edicao.nome} onChange={(e) => setEdicao({ ...edicao, nome: e.target.value })} /></Campo>
          {!edicao.id && (
            <Campo rotulo="Login" dica="Letras, números, ponto, hífen ou sublinhado. Ex.: rayan, cristian.silva">
              <input value={edicao.usuario} onChange={(e) => setEdicao({ ...edicao, usuario: e.target.value.toLowerCase() })} />
            </Campo>
          )}
          <Campo rotulo="Perfil">
            <select value={edicao.perfil} onChange={(e) => setEdicao({ ...edicao, perfil: e.target.value })}>
              {Object.entries(PERFIS).map(([valor, texto]) => <option key={valor} value={valor}>{texto}</option>)}
            </select>
          </Campo>
          {edicao.perfil === 'supervisor' && (
            <Campo rotulo="Supervisor ligado a este usuário">
              <select value={edicao.supervisor_id} onChange={(e) => setEdicao({ ...edicao, supervisor_id: e.target.value })}>
                <option value="">Escolha…</option>
                {(supervisores || []).map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
              </select>
            </Campo>
          )}
          {erro && <p className="erro">{erro}</p>}
        </Modal>
      )}
      {senha && <SenhaGerada {...senha} aoFechar={() => setSenha(null)} />}
    </section>
  )
}
