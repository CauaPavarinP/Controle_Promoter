import { useState } from 'react'
import { http } from '../../api.js'
import { Campo, Modal, Situacao, Tabela, useLista } from '../ui.jsx'

export default function Supervisores({ podeEditar }) {
  const [supervisores, recarregar, erroLista] = useLista(() => http.get('/api/supervisores'))
  const [edicao, setEdicao] = useState(null)        // { id?, nome }
  const [transferencia, setTransferencia] = useState(null)
  const [mostrarInativos, setMostrarInativos] = useState(false)
  const [erro, setErro] = useState('')

  async function executar(acao) {
    setErro('')
    try {
      await acao()
      recarregar()
      return true
    } catch (e) {
      setErro(e.message)
      return false
    }
  }

  async function salvar() {
    const ok = await executar(() =>
      edicao.id ? http.put(`/api/supervisores/${edicao.id}`, { nome: edicao.nome }) : http.post('/api/supervisores', { nome: edicao.nome }),
    )
    if (ok) setEdicao(null)
  }

  async function transferir() {
    const ok = await executar(() =>
      http.post(`/api/supervisores/${transferencia.origem.id}/transferir`, { para_id: Number(transferencia.para) }),
    )
    if (ok) setTransferencia(null)
  }

  if (!supervisores) return erroLista ? <div className="erro-caixa">{erroLista}</div> : <p>Carregando…</p>
  const visiveis = supervisores.filter((s) => mostrarInativos || s.ativo)

  const colunas = [
    { campo: 'nome', titulo: 'Supervisor' },
    { campo: 'promotores_ativos', titulo: 'Promotores ativos', num: true },
    { campo: 'pdvs', titulo: 'PDVs atendidos', num: true },
    { campo: 'ativo', titulo: 'Situação', mostrar: (s) => <Situacao ativo={s.ativo} />, exportar: (s) => (s.ativo ? 'Ativo' : 'Inativo') },
  ]
  if (podeEditar) {
    colunas.push({
      campo: 'acoes', titulo: '', semOrdem: true, semExportar: true,
      mostrar: (s) => (
        <div className="acoes">
          <button className="secundario" onClick={() => setEdicao({ id: s.id, nome: s.nome })}>Editar</button>
          {s.ativo && s.promotores_ativos > 0 && (
            <button className="secundario" onClick={() => setTransferencia({ origem: s, para: '' })}>Transferir equipe</button>
          )}
          {s.ativo ? (
            <button className="secundario perigo" onClick={() => executar(() => http.post(`/api/supervisores/${s.id}/inativar`))}>Inativar</button>
          ) : (
            <button className="secundario" onClick={() => executar(() => http.post(`/api/supervisores/${s.id}/reativar`))}>Reativar</button>
          )}
        </div>
      ),
    })
  }

  return (
    <section className="bloco">
      <div className="bloco-cabecalho">
        <label className="marcar">
          <input type="checkbox" checked={mostrarInativos} onChange={(e) => setMostrarInativos(e.target.checked)} />
          Mostrar inativos
        </label>
        {podeEditar && <button onClick={() => setEdicao({ nome: '' })}>+ Novo supervisor</button>}
      </div>
      {erro && <div className="erro-caixa">{erro}</div>}
      <Tabela colunas={colunas} linhas={visiveis} arquivo="supervisores" />

      {edicao && (
        <Modal
          titulo={edicao.id ? 'Editar supervisor' : 'Novo supervisor'}
          aoFechar={() => setEdicao(null)}
          rodape={<button onClick={salvar} disabled={!edicao.nome.trim()}>Salvar</button>}
        >
          <Campo rotulo="Nome">
            <input value={edicao.nome} onChange={(e) => setEdicao({ ...edicao, nome: e.target.value })} autoFocus />
          </Campo>
          {erro && <p className="erro">{erro}</p>}
        </Modal>
      )}

      {transferencia && (
        <Modal
          titulo={`Transferir equipe de ${transferencia.origem.nome}`}
          aoFechar={() => setTransferencia(null)}
          rodape={<button onClick={transferir} disabled={!transferencia.para}>Transferir</button>}
        >
          <p className="dica">
            Os {transferencia.origem.promotores_ativos} promotor(es) ativos passam para o supervisor escolhido. Depois disso
            dá para inativar {transferencia.origem.nome}.
          </p>
          <Campo rotulo="Novo supervisor">
            <select value={transferencia.para} onChange={(e) => setTransferencia({ ...transferencia, para: e.target.value })}>
              <option value="">Escolha…</option>
              {supervisores
                .filter((s) => s.ativo && s.id !== transferencia.origem.id)
                .map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
            </select>
          </Campo>
          {erro && <p className="erro">{erro}</p>}
        </Modal>
      )}
    </section>
  )
}
