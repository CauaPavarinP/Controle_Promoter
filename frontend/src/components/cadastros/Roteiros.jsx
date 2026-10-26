import { useState } from 'react'
import { http } from '../../api.js'
import { formatarData } from '../../formato.js'
import { SituacaoRoteiro, Tabela, useLista } from '../ui.jsx'
import { EditarRoteiroModal, EncerrarModal, TransferirLoteModal, TrocarModal, VincularModal } from './RoteiroModais.jsx'

export default function Roteiros({ podeEditar }) {
  const [roteiros, recarregar, erroLista] = useLista(() => http.get('/api/roteiros'))
  const [promotores, recarregarPromotores] = useLista(() => http.get('/api/promotores'))
  const [pdvs] = useLista(() => http.get('/api/pdvs'))
  const [filtros, setFiltros] = useState({ busca: '', promotor: '', situacao: 'vigentes', especial: '' })
  const [janela, setJanela] = useState(null)

  if (!roteiros || !promotores) return erroLista ? <div className="erro-caixa">{erroLista}</div> : <p>Carregando…</p>
  const termo = filtros.busca.trim().toLowerCase()
  const visiveis = roteiros.filter((r) =>
    (filtros.situacao === 'todos' || (filtros.situacao === 'vigentes') === (r.situacao !== 'encerrado')) &&
    (!filtros.promotor || String(r.promotor_id) === filtros.promotor) &&
    (filtros.especial !== 'sem_visitas' || !r.visitas_por_semana) &&
    (filtros.especial !== 'varios' || (r.vigente && r.promotores_no_pdv > 1)) &&
    (!termo || `${r.pdv} ${r.promotor} ${r.cidade}`.toLowerCase().includes(termo)))
  const semVisitas = roteiros.filter((r) => r.vigente && !r.visitas_por_semana).length

  const fechar = () => setJanela(null)
  const concluir = () => { setJanela(null); recarregar(); recarregarPromotores() }

  const colunas = [
    { campo: 'promotor', titulo: 'Promotor', quebra: true },
    {
      campo: 'pdv', titulo: 'PDV', quebra: true,
      mostrar: (r) => (
        <>
          {r.pdv}
          {r.vigente && r.promotores_no_pdv > 1 && (
            <span className="etiqueta" title="O faturamento deste PDV conta para cada promotor">
              {r.promotores_no_pdv} promotores
            </span>
          )}
        </>
      ),
    },
    { campo: 'cidade', titulo: 'Cidade', mostrar: (r) => `${r.cidade}${r.uf ? ` - ${r.uf}` : ''}` },
    { campo: 'visitas_por_semana', titulo: 'Visitas/sem.', num: true, mostrar: (r) => r.visitas_por_semana ?? <span className="texto-alerta">—</span> },
    { campo: 'dias_semana', titulo: 'Dias' },
    { campo: 'data_inicio', titulo: 'Início', mostrar: (r) => formatarData(r.data_inicio), exportar: (r) => formatarData(r.data_inicio) },
    { campo: 'data_fim', titulo: 'Fim', mostrar: (r) => formatarData(r.data_fim), exportar: (r) => formatarData(r.data_fim) },
    { campo: 'vigente', titulo: 'Situação', mostrar: (r) => <SituacaoRoteiro situacao={r.situacao} />, exportar: (r) => r.situacao },
  ]
  if (podeEditar) {
    colunas.push({
      campo: 'acoes', titulo: '', semOrdem: true, semExportar: true,
      mostrar: (r) => r.situacao !== 'encerrado' && (
        <div className="acoes">
          <button className="secundario" onClick={() => setJanela({ tipo: 'editar', roteiro: r })}>Editar</button>
          <button className="secundario" onClick={() => setJanela({ tipo: 'trocar', roteiro: r })}>Trocar</button>
          <button className="secundario perigo" onClick={() => setJanela({ tipo: 'encerrar', roteiro: r })}>Encerrar</button>
        </div>
      ),
    })
  }

  return (
    <section className="bloco">
      {semVisitas > 0 && (
        <div className="aviso">
          {semVisitas} vínculo(s) vigente(s) sem visitas por semana. Sem essa informação não dá para calcular o custo por
          visita. Use <b>Editar</b> para preencher, ou filtre por "Sem visitas por semana".
        </div>
      )}
      <div className="bloco-cabecalho">
        <div className="bloco-ferramentas">
          <input placeholder="Buscar PDV, promotor ou cidade" value={filtros.busca} onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })} />
          <select value={filtros.promotor} onChange={(e) => setFiltros({ ...filtros, promotor: e.target.value })}>
            <option value="">Todos os promotores</option>
            {promotores.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
          </select>
          <select value={filtros.situacao} onChange={(e) => setFiltros({ ...filtros, situacao: e.target.value })}>
            <option value="vigentes">Vigentes e agendados</option>
            <option value="encerrados">Encerrados</option>
            <option value="todos">Todos</option>
          </select>
          <select value={filtros.especial} onChange={(e) => setFiltros({ ...filtros, especial: e.target.value })}>
            <option value="">Todos os vínculos</option>
            <option value="sem_visitas">Sem visitas por semana</option>
            <option value="varios">PDV com mais de um promotor</option>
          </select>
        </div>
        {podeEditar && (
          <div className="acoes">
            <button className="secundario" onClick={() => setJanela({ tipo: 'lote' })}>Transferir em lote</button>
            <button onClick={() => setJanela({ tipo: 'vincular' })}>+ Vincular PDV</button>
          </div>
        )}
      </div>
      <Tabela linhas={visiveis} colunas={colunas} arquivo="roteiros" />

      {janela?.tipo === 'vincular' && <VincularModal promotores={promotores} pdvs={pdvs || []} aoFechar={fechar} aoSalvar={concluir} />}
      {janela?.tipo === 'lote' && <TransferirLoteModal promotores={promotores} aoFechar={fechar} aoSalvar={concluir} />}
      {janela?.tipo === 'editar' && <EditarRoteiroModal roteiro={janela.roteiro} aoFechar={fechar} aoSalvar={concluir} />}
      {janela?.tipo === 'trocar' && <TrocarModal roteiro={janela.roteiro} promotores={promotores} aoFechar={fechar} aoSalvar={concluir} />}
      {janela?.tipo === 'encerrar' && <EncerrarModal roteiro={janela.roteiro} aoFechar={fechar} aoSalvar={concluir} />}
    </section>
  )
}
