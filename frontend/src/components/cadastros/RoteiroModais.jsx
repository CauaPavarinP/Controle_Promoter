// Janelas usadas na tela de Roteiros e no detalhe do promotor.
import { useState } from 'react'
import { http } from '../../api.js'
import { formatarCnpj } from '../../formato.js'
import { Campo, EscolhaComBusca, Modal } from '../ui.jsx'

const DIAS = ['seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom']
const hoje = () => new Date().toISOString().slice(0, 10)

function DiasDaSemana({ valor, aoMudar }) {
  const marcados = valor ? valor.split(',') : []
  function alternar(dia) {
    const novos = marcados.includes(dia) ? marcados.filter((d) => d !== dia) : [...marcados, dia]
    aoMudar(DIAS.filter((d) => novos.includes(d)).join(','))
  }
  return (
    <div className="dias">
      {DIAS.map((d) => (
        <label key={d} className={marcados.includes(d) ? 'marcado' : ''}>
          <input type="checkbox" checked={marcados.includes(d)} onChange={() => alternar(d)} />
          {d}
        </label>
      ))}
    </div>
  )
}

function Visitas({ valor, aoMudar }) {
  return (
    <select value={valor ?? ''} onChange={(e) => aoMudar(e.target.value ? Number(e.target.value) : null)}>
      <option value="">Não informado</option>
      {[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n}x por semana</option>)}
    </select>
  )
}

function useEnvio(aoConcluir) {
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)
  async function enviar(acao) {
    setErro('')
    setEnviando(true)
    try {
      await acao()
      aoConcluir()
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviando(false)
    }
  }
  return { erro, enviando, enviar }
}

export function VincularModal({ promotores, pdvs, promotorFixo, aoFechar, aoSalvar }) {
  const [dados, setDados] = useState({
    promotor_id: promotorFixo?.id ?? '', pdv_id: null, data_inicio: hoje(),
    visitas_por_semana: null, dias_semana: '', observacao: '',
  })
  const { erro, enviando, enviar } = useEnvio(aoSalvar)
  const opcoesPdv = pdvs
    .filter((p) => p.ativo)
    .map((p) => ({ valor: p.id, texto: `${p.nome_fantasia} — ${p.cidade}/${p.uf} — ${formatarCnpj(p.cnpj_cpf)}` }))
  const alterar = (campo, valor) => setDados((d) => ({ ...d, [campo]: valor }))

  return (
    <Modal
      titulo={promotorFixo ? `Vincular PDV a ${promotorFixo.nome}` : 'Vincular PDV a um promotor'}
      aoFechar={aoFechar}
      rodape={
        <button disabled={enviando || !dados.promotor_id || !dados.pdv_id || !dados.data_inicio}
          onClick={() => enviar(() => http.post('/api/roteiros', { ...dados, promotor_id: Number(dados.promotor_id) }))}>
          Vincular
        </button>
      }
    >
      {!promotorFixo && (
        <Campo rotulo="Promotor">
          <select value={dados.promotor_id} onChange={(e) => alterar('promotor_id', e.target.value)}>
            <option value="">Escolha…</option>
            {promotores.filter((p) => p.ativo).map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.codigo})</option>)}
          </select>
        </Campo>
      )}
      <Campo rotulo="PDV" dica="Busque pelo nome, cidade ou CNPJ. Se o PDV não existe, cadastre antes em PDVs.">
        <EscolhaComBusca opcoes={opcoesPdv} valor={dados.pdv_id} aoMudar={(v) => alterar('pdv_id', v)} />
      </Campo>
      <div className="campos-linha">
        <Campo rotulo="Início do atendimento">
          <input type="date" value={dados.data_inicio} onChange={(e) => alterar('data_inicio', e.target.value)} />
        </Campo>
        <Campo rotulo="Visitas por semana">
          <Visitas valor={dados.visitas_por_semana} aoMudar={(v) => alterar('visitas_por_semana', v)} />
        </Campo>
      </div>
      <Campo rotulo="Dias da semana (opcional)">
        <DiasDaSemana valor={dados.dias_semana} aoMudar={(v) => alterar('dias_semana', v)} />
      </Campo>
      <Campo rotulo="Observação">
        <input value={dados.observacao} onChange={(e) => alterar('observacao', e.target.value)} />
      </Campo>
      {erro && <p className="erro">{erro}</p>}
    </Modal>
  )
}

export function EditarRoteiroModal({ roteiro, aoFechar, aoSalvar }) {
  const [dados, setDados] = useState({
    visitas_por_semana: roteiro.visitas_por_semana, dias_semana: roteiro.dias_semana, observacao: roteiro.observacao,
  })
  const { erro, enviando, enviar } = useEnvio(aoSalvar)
  return (
    <Modal
      titulo={`${roteiro.pdv} — ${roteiro.promotor}`}
      aoFechar={aoFechar}
      rodape={<button disabled={enviando} onClick={() => enviar(() => http.put(`/api/roteiros/${roteiro.id}`, dados))}>Salvar</button>}
    >
      <Campo rotulo="Visitas por semana">
        <Visitas valor={dados.visitas_por_semana} aoMudar={(v) => setDados({ ...dados, visitas_por_semana: v })} />
      </Campo>
      <Campo rotulo="Dias da semana">
        <DiasDaSemana valor={dados.dias_semana} aoMudar={(v) => setDados({ ...dados, dias_semana: v })} />
      </Campo>
      <Campo rotulo="Observação">
        <input value={dados.observacao} onChange={(e) => setDados({ ...dados, observacao: e.target.value })} />
      </Campo>
      {erro && <p className="erro">{erro}</p>}
    </Modal>
  )
}

export function TrocarModal({ roteiro, promotores, aoFechar, aoSalvar }) {
  const [dados, setDados] = useState({ promotor_id: '', data: hoje() })
  const { erro, enviando, enviar } = useEnvio(aoSalvar)
  return (
    <Modal
      titulo={`Trocar o promotor de ${roteiro.pdv}`}
      aoFechar={aoFechar}
      rodape={
        <button disabled={enviando || !dados.promotor_id}
          onClick={() => enviar(() => http.post(`/api/roteiros/${roteiro.id}/trocar`, { ...dados, promotor_id: Number(dados.promotor_id) }))}>
          Trocar
        </button>
      }
    >
      <p className="dica">
        O vínculo de <b>{roteiro.promotor}</b> termina no dia anterior à data da troca. O faturamento dos meses anteriores
        continua com ele.
      </p>
      <Campo rotulo="Novo promotor">
        <select value={dados.promotor_id} onChange={(e) => setDados({ ...dados, promotor_id: e.target.value })}>
          <option value="">Escolha…</option>
          {promotores.filter((p) => p.ativo && p.id !== roteiro.promotor_id)
            .map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.codigo})</option>)}
        </select>
      </Campo>
      <Campo rotulo="A partir de">
        <input type="date" value={dados.data} onChange={(e) => setDados({ ...dados, data: e.target.value })} />
      </Campo>
      {erro && <p className="erro">{erro}</p>}
    </Modal>
  )
}

export function EncerrarModal({ roteiro, aoFechar, aoSalvar }) {
  const [data, setData] = useState(hoje())
  const { erro, enviando, enviar } = useEnvio(aoSalvar)
  return (
    <Modal
      titulo={`Encerrar ${roteiro.pdv} — ${roteiro.promotor}`}
      aoFechar={aoFechar}
      rodape={
        <button className="perigo" disabled={enviando}
          onClick={() => enviar(() => http.post(`/api/roteiros/${roteiro.id}/encerrar`, { data_fim: data }))}>
          Encerrar vínculo
        </button>
      }
    >
      <p className="dica">O PDV deixa de ser atendido por este promotor a partir do dia seguinte. O histórico continua salvo.</p>
      <Campo rotulo="Último dia de atendimento">
        <input type="date" value={data} onChange={(e) => setData(e.target.value)} />
      </Campo>
      {erro && <p className="erro">{erro}</p>}
    </Modal>
  )
}

export function TransferirLoteModal({ promotores, aoFechar, aoSalvar }) {
  const [dados, setDados] = useState({ de_promotor_id: '', para_promotor_id: '', data: hoje() })
  const { erro, enviando, enviar } = useEnvio(aoSalvar)
  return (
    <Modal
      titulo="Transferir todos os PDVs de um promotor"
      aoFechar={aoFechar}
      rodape={
        <button disabled={enviando || !dados.de_promotor_id || !dados.para_promotor_id}
          onClick={() => enviar(() => http.post('/api/roteiros/transferir', {
            ...dados, de_promotor_id: Number(dados.de_promotor_id), para_promotor_id: Number(dados.para_promotor_id),
          }))}>
          Transferir
        </button>
      }
    >
      <p className="dica">Útil em desligamento ou troca de região. Os vínculos antigos são encerrados no dia anterior.</p>
      <Campo rotulo="De">
        <select value={dados.de_promotor_id} onChange={(e) => setDados({ ...dados, de_promotor_id: e.target.value })}>
          <option value="">Escolha…</option>
          {promotores.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.lojas_vigentes} PDVs)</option>)}
        </select>
      </Campo>
      <Campo rotulo="Para">
        <select value={dados.para_promotor_id} onChange={(e) => setDados({ ...dados, para_promotor_id: e.target.value })}>
          <option value="">Escolha…</option>
          {promotores.filter((p) => p.ativo && String(p.id) !== dados.de_promotor_id)
            .map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
        </select>
      </Campo>
      <Campo rotulo="A partir de">
        <input type="date" value={dados.data} onChange={(e) => setDados({ ...dados, data: e.target.value })} />
      </Campo>
      {erro && <p className="erro">{erro}</p>}
    </Modal>
  )
}
