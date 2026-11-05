import { useEffect, useState } from 'react'
import { http } from '../../api.js'
import { formatarData, formatarMoeda, NOMES_MESES_LONGOS, UFS } from '../../formato.js'
import { Campo, Modal, Situacao, SituacaoRoteiro, Tabela, useLista } from '../ui.jsx'
import { EditarRoteiroModal, EncerrarModal, TrocarModal, VincularModal } from './RoteiroModais.jsx'

const agora = new Date()
const CUSTO_VAZIO = { ano: agora.getFullYear(), mes: agora.getMonth() + 1, salario: '', ajuda_custo: '', vale_transporte: '', outros: '' }
const PROMOTOR_VAZIO = {
  codigo: '', nome: '', data_admissao: '', municipio: '', uf: '', supervisor_id: '', funcao: 'Promotor', observacao: '',
}

const numero = (v) => (v === '' || v == null ? 0 : Number(v))
const custoParaEnvio = (c) => ({
  ano: Number(c.ano), mes: Number(c.mes), salario: numero(c.salario), ajuda_custo: numero(c.ajuda_custo),
  vale_transporte: numero(c.vale_transporte), outros: numero(c.outros),
})
const promotorParaEnvio = (p) => ({ ...p, supervisor_id: Number(p.supervisor_id), data_admissao: p.data_admissao || null })

function CamposCusto({ custo, alterar }) {
  const total = ['salario', 'ajuda_custo', 'vale_transporte', 'outros'].reduce((s, c) => s + numero(custo[c]), 0)
  return (
    <>
      <div className="campos-linha">
        <Campo rotulo="Vale a partir de (mês)">
          <select value={custo.mes} onChange={(e) => alterar('mes', e.target.value)}>
            {NOMES_MESES_LONGOS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </Campo>
        <Campo rotulo="Ano">
          <input type="number" value={custo.ano} onChange={(e) => alterar('ano', e.target.value)} />
        </Campo>
      </div>
      <div className="campos-linha">
        <Campo rotulo="Salário (R$)"><input type="number" min="0" step="0.01" value={custo.salario} onChange={(e) => alterar('salario', e.target.value)} /></Campo>
        <Campo rotulo="Ajuda de custo (R$)"><input type="number" min="0" step="0.01" value={custo.ajuda_custo} onChange={(e) => alterar('ajuda_custo', e.target.value)} /></Campo>
        <Campo rotulo="Vale-transporte (R$)"><input type="number" min="0" step="0.01" value={custo.vale_transporte} onChange={(e) => alterar('vale_transporte', e.target.value)} /></Campo>
        <Campo rotulo="Outros (R$)"><input type="number" min="0" step="0.01" value={custo.outros} onChange={(e) => alterar('outros', e.target.value)} /></Campo>
      </div>
      <p className="dica">Total por mês: <b>{formatarMoeda(total)}</b></p>
    </>
  )
}

function CamposPromotor({ dados, alterar, supervisores }) {
  return (
    <>
      <div className="campos-linha">
        <Campo rotulo="Código (folha)" largura="140px"><input value={dados.codigo} onChange={(e) => alterar('codigo', e.target.value)} /></Campo>
        <Campo rotulo="Nome"><input value={dados.nome} onChange={(e) => alterar('nome', e.target.value)} /></Campo>
      </div>
      <div className="campos-linha">
        <Campo rotulo="Supervisor">
          <select value={dados.supervisor_id} onChange={(e) => alterar('supervisor_id', e.target.value)}>
            <option value="">Escolha…</option>
            {supervisores.filter((s) => s.ativo || s.id === Number(dados.supervisor_id))
              .map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
          </select>
        </Campo>
        <Campo rotulo="Admissão"><input type="date" value={dados.data_admissao || ''} onChange={(e) => alterar('data_admissao', e.target.value)} /></Campo>
        <Campo rotulo="Função">
          <select value={dados.funcao} onChange={(e) => alterar('funcao', e.target.value)}>
            <option>Promotor</option>
            <option>Repositor</option>
            <option>Supervisor</option>
          </select>
        </Campo>
      </div>
      <div className="campos-linha">
        <Campo rotulo="Município"><input value={dados.municipio} onChange={(e) => alterar('municipio', e.target.value)} /></Campo>
        <Campo rotulo="UF" largura="100px">
          <select value={dados.uf} onChange={(e) => alterar('uf', e.target.value)}>
            <option value="">—</option>
            {UFS.map((u) => <option key={u}>{u}</option>)}
          </select>
        </Campo>
      </div>
      <Campo rotulo="Observação"><input value={dados.observacao} onChange={(e) => alterar('observacao', e.target.value)} /></Campo>
    </>
  )
}

function NovoPromotor({ supervisores, aoFechar, aoSalvar }) {
  const [dados, setDados] = useState(PROMOTOR_VAZIO)
  const [custo, setCusto] = useState(CUSTO_VAZIO)
  const [erro, setErro] = useState('')
  async function salvar() {
    setErro('')
    try {
      await http.post('/api/promotores', { ...promotorParaEnvio(dados), custo: custoParaEnvio(custo) })
      aoSalvar()
    } catch (e) {
      setErro(e.message)
    }
  }
  return (
    <Modal titulo="Novo promotor" aoFechar={aoFechar} largo
      rodape={<button onClick={salvar} disabled={!dados.codigo || !dados.nome || !dados.supervisor_id || custo.salario === ''}>Salvar</button>}>
      <CamposPromotor dados={dados} alterar={(c, v) => setDados({ ...dados, [c]: v })} supervisores={supervisores} />
      <h3>Custo atual</h3>
      <CamposCusto custo={custo} alterar={(c, v) => setCusto({ ...custo, [c]: v })} />
      {erro && <p className="erro">{erro}</p>}
    </Modal>
  )
}

function DetalhePromotor({ id, supervisores, promotores, pdvs, podeEditar, aoFechar, aoAlterar }) {
  const [promotor, setPromotor] = useState(null)
  const [edicao, setEdicao] = useState(null)
  const [reajuste, setReajuste] = useState(null)
  const [desligamento, setDesligamento] = useState(null)
  const [janela, setJanela] = useState(null)   // { tipo: 'vincular'|'editar'|'trocar'|'encerrar', roteiro }
  const [erro, setErro] = useState('')

  const carregar = () => http.get(`/api/promotores/${id}`).then(setPromotor).catch((e) => setErro(e.message))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { carregar() }, [id])

  async function executar(acao, depois) {
    setErro('')
    try {
      await acao()
      depois?.()
      await carregar()
      aoAlterar()
    } catch (e) {
      setErro(e.message)
    }
  }

  const fecharJanela = () => setJanela(null)
  const concluirJanela = () => { setJanela(null); carregar(); aoAlterar() }

  if (!promotor) return <Modal titulo="Promotor" aoFechar={aoFechar}>{erro || 'Carregando…'}</Modal>

  const vigentes = promotor.roteiros.filter((r) => r.vigente)
  return (
    <Modal titulo={`${promotor.nome} (${promotor.codigo})`} aoFechar={aoFechar} largo>
      {erro && <div className="erro-caixa">{erro}</div>}

      <section className="detalhe-secao">
        <div className="secao-titulo">
          <h3>Dados</h3>
          {podeEditar && !edicao && (
            <div className="acoes">
              <button className="secundario" onClick={() => setEdicao({
                codigo: promotor.codigo, nome: promotor.nome, data_admissao: promotor.data_admissao || '',
                municipio: promotor.municipio, uf: promotor.uf, supervisor_id: promotor.supervisor_id ?? '',
                funcao: promotor.funcao, observacao: promotor.observacao,
              })}>Editar</button>
              {promotor.ativo ? (
                <button className="secundario perigo" onClick={() => setDesligamento(new Date().toISOString().slice(0, 10))}>Desligar</button>
              ) : (
                <button className="secundario" onClick={() => executar(() => http.post(`/api/promotores/${id}/reativar`))}>Reativar</button>
              )}
            </div>
          )}
        </div>
        {edicao ? (
          <>
            <CamposPromotor dados={edicao} alterar={(c, v) => setEdicao({ ...edicao, [c]: v })} supervisores={supervisores} />
            <div className="acoes">
              <button onClick={() => executar(() => http.put(`/api/promotores/${id}`, promotorParaEnvio(edicao)), () => setEdicao(null))}
                disabled={!edicao.supervisor_id}>Salvar</button>
              <button className="secundario" onClick={() => setEdicao(null)}>Cancelar</button>
            </div>
          </>
        ) : (
          <dl className="dados">
            <dt>Situação</dt><dd><Situacao ativo={promotor.ativo} textoInativo={`Desligado em ${formatarData(promotor.data_desligamento)}`} /></dd>
            <dt>Supervisor</dt><dd>{promotor.supervisor || <span className="texto-critico">sem supervisor</span>}</dd>
            <dt>Função</dt><dd>{promotor.funcao}</dd>
            <dt>Admissão</dt><dd>{formatarData(promotor.data_admissao)}</dd>
            <dt>Município</dt><dd>{promotor.municipio}{promotor.uf && ` - ${promotor.uf}`}</dd>
            {promotor.observacao && (<><dt>Observação</dt><dd>{promotor.observacao}</dd></>)}
          </dl>
        )}
        {desligamento && (
          <div className="caixa-acao">
            <p>
              Desligar <b>{promotor.nome}</b>: os {vigentes.length} PDV(s) dele serão encerrados nessa data e ficarão sem
              promotor. Para passar os PDVs a outra pessoa, use antes <b>Transferir em lote</b> na tela de Roteiros.
            </p>
            <Campo rotulo="Data do desligamento">
              <input type="date" value={desligamento} onChange={(e) => setDesligamento(e.target.value)} />
            </Campo>
            <div className="acoes">
              <button className="perigo" onClick={() => executar(
                () => http.post(`/api/promotores/${id}/inativar`, { data_desligamento: desligamento }), () => setDesligamento(null))}>
                Confirmar desligamento
              </button>
              <button className="secundario" onClick={() => setDesligamento(null)}>Cancelar</button>
            </div>
          </div>
        )}
      </section>

      <section className="detalhe-secao">
        <div className="secao-titulo">
          <h3>Custo por competência</h3>
          {podeEditar && !reajuste && <button className="secundario" onClick={() => setReajuste(CUSTO_VAZIO)}>+ Novo reajuste</button>}
        </div>
        <p className="dica">Cada valor vale a partir do mês indicado até o próximo reajuste. Mudar o custo não altera os meses anteriores.</p>
        {reajuste && (
          <div className="caixa-acao">
            <CamposCusto custo={reajuste} alterar={(c, v) => setReajuste({ ...reajuste, [c]: v })} />
            <div className="acoes">
              <button disabled={reajuste.salario === ''} onClick={() => executar(
                () => http.post(`/api/promotores/${id}/custos`, custoParaEnvio(reajuste)), () => setReajuste(null))}>Salvar reajuste</button>
              <button className="secundario" onClick={() => setReajuste(null)}>Cancelar</button>
            </div>
          </div>
        )}
        <Tabela
          chave="id"
          linhas={promotor.custos}
          porPagina={12}
          colunas={[
            { campo: 'vigencia', titulo: 'A partir de', semOrdem: true, mostrar: (c) => `${NOMES_MESES_LONGOS[c.mes - 1]}/${c.ano}` },
            { campo: 'salario', titulo: 'Salário', num: true, semOrdem: true, mostrar: (c) => formatarMoeda(c.salario) },
            { campo: 'ajuda_custo', titulo: 'Ajuda de custo', num: true, semOrdem: true, mostrar: (c) => formatarMoeda(c.ajuda_custo) },
            { campo: 'vale_transporte', titulo: 'Vale-transp.', num: true, semOrdem: true, mostrar: (c) => formatarMoeda(c.vale_transporte) },
            { campo: 'outros', titulo: 'Outros', num: true, semOrdem: true, mostrar: (c) => formatarMoeda(c.outros) },
            { campo: 'total', titulo: 'Total', num: true, semOrdem: true, mostrar: (c) => <b>{formatarMoeda(c.total)}</b> },
            ...(podeEditar ? [{
              campo: 'acoes', titulo: '', semOrdem: true,
              mostrar: (c) => promotor.custos.length > 1 && (
                <button className="secundario perigo" onClick={() => window.confirm('Excluir este reajuste?') &&
                  executar(() => http.delete(`/api/promotores/${id}/custos/${c.id}`))}>Excluir</button>
              ),
            }] : []),
          ]}
        />
      </section>

      <section className="detalhe-secao">
        <div className="secao-titulo">
          <h3>Roteiro ({vigentes.length} PDV(s) atendidos hoje)</h3>
          {podeEditar && promotor.ativo && <button className="secundario" onClick={() => setJanela({ tipo: 'vincular' })}>+ Vincular PDV</button>}
        </div>
        <Tabela
          linhas={promotor.roteiros}
          porPagina={20}
          vazio="Nenhum PDV vinculado."
          colunas={[
            { campo: 'pdv', titulo: 'PDV', quebra: true },
            { campo: 'cidade', titulo: 'Cidade', mostrar: (r) => `${r.cidade}${r.uf ? ` - ${r.uf}` : ''}` },
            { campo: 'visitas_por_semana', titulo: 'Visitas/sem.', num: true, mostrar: (r) => r.visitas_por_semana ?? <span className="texto-alerta">—</span> },
            { campo: 'data_inicio', titulo: 'Início', mostrar: (r) => formatarData(r.data_inicio) },
            { campo: 'data_fim', titulo: 'Fim', mostrar: (r) => formatarData(r.data_fim) },
            { campo: 'vigente', titulo: 'Situação', mostrar: (r) => <SituacaoRoteiro situacao={r.situacao} /> },
            ...(podeEditar ? [{
              campo: 'acoes', titulo: '', semOrdem: true,
              mostrar: (r) => r.situacao !== 'encerrado' && (
                <div className="acoes">
                  <button className="secundario" onClick={() => setJanela({ tipo: 'editar', roteiro: r })}>Editar</button>
                  <button className="secundario" onClick={() => setJanela({ tipo: 'trocar', roteiro: r })}>Trocar</button>
                  <button className="secundario perigo" onClick={() => setJanela({ tipo: 'encerrar', roteiro: r })}>Encerrar</button>
                </div>
              ),
            }] : []),
          ]}
        />
      </section>

      {janela?.tipo === 'vincular' && (
        <VincularModal promotores={promotores} pdvs={pdvs} promotorFixo={promotor} aoFechar={fecharJanela} aoSalvar={concluirJanela} />
      )}
      {janela?.tipo === 'editar' && <EditarRoteiroModal roteiro={janela.roteiro} aoFechar={fecharJanela} aoSalvar={concluirJanela} />}
      {janela?.tipo === 'trocar' && (
        <TrocarModal roteiro={janela.roteiro} promotores={promotores} aoFechar={fecharJanela} aoSalvar={concluirJanela} />
      )}
      {janela?.tipo === 'encerrar' && <EncerrarModal roteiro={janela.roteiro} aoFechar={fecharJanela} aoSalvar={concluirJanela} />}
    </Modal>
  )
}

export default function Promotores({ podeEditar }) {
  const [promotores, recarregar, erroLista] = useLista(() => http.get('/api/promotores'))
  const [supervisores] = useLista(() => http.get('/api/supervisores'))
  const [pdvs] = useLista(() => http.get('/api/pdvs'))
  const [filtros, setFiltros] = useState({ busca: '', supervisor: '', situacao: 'ativos' })
  const [novo, setNovo] = useState(false)
  const [aberto, setAberto] = useState(null)

  if (!promotores || !supervisores) return erroLista ? <div className="erro-caixa">{erroLista}</div> : <p>Carregando…</p>
  const termo = filtros.busca.trim().toLowerCase()
  const visiveis = promotores.filter((p) =>
    (filtros.situacao === 'todos' || (filtros.situacao === 'ativos') === p.ativo) &&
    (!filtros.supervisor || String(p.supervisor_id) === filtros.supervisor || (filtros.supervisor === 'sem' && !p.supervisor_id)) &&
    (!termo || `${p.nome} ${p.codigo} ${p.municipio}`.toLowerCase().includes(termo)))

  return (
    <section className="bloco">
      <div className="bloco-cabecalho">
        <div className="bloco-ferramentas">
          <input placeholder="Buscar nome, código ou município" value={filtros.busca} onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })} />
          <select value={filtros.supervisor} onChange={(e) => setFiltros({ ...filtros, supervisor: e.target.value })}>
            <option value="">Todos os supervisores</option>
            <option value="sem">Sem supervisor</option>
            {supervisores.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
          </select>
          <select value={filtros.situacao} onChange={(e) => setFiltros({ ...filtros, situacao: e.target.value })}>
            <option value="ativos">Ativos</option>
            <option value="inativos">Desligados</option>
            <option value="todos">Todos</option>
          </select>
        </div>
        {podeEditar && <button onClick={() => setNovo(true)}>+ Novo promotor</button>}
      </div>
      <p className="dica">Clique num promotor para ver custos, roteiro e editar.</p>
      <Tabela
        linhas={visiveis}
        arquivo="promotores"
        aoClicar={(p) => setAberto(p.id)}
        colunas={[
          { campo: 'codigo', titulo: 'Código' },
          { campo: 'nome', titulo: 'Nome', quebra: true },
          { campo: 'supervisor', titulo: 'Supervisor', mostrar: (p) => p.supervisor || <span className="texto-critico">sem supervisor</span> },
          { campo: 'municipio', titulo: 'Município', mostrar: (p) => `${p.municipio}${p.uf ? ` - ${p.uf}` : ''}` },
          { campo: 'custo_atual', titulo: 'Custo atual', num: true, mostrar: (p) => formatarMoeda(p.custo_atual) },
          { campo: 'lojas_vigentes', titulo: 'PDVs', num: true },
          { campo: 'ativo', titulo: 'Situação', mostrar: (p) => <Situacao ativo={p.ativo} textoInativo="Desligado" />, exportar: (p) => (p.ativo ? 'Ativo' : 'Desligado') },
        ]}
      />
      {novo && <NovoPromotor supervisores={supervisores} aoFechar={() => setNovo(false)} aoSalvar={() => { setNovo(false); recarregar() }} />}
      {aberto && (
        <DetalhePromotor id={aberto} supervisores={supervisores} promotores={promotores} pdvs={pdvs || []}
          podeEditar={podeEditar} aoFechar={() => setAberto(null)} aoAlterar={recarregar} />
      )}
    </section>
  )
}
