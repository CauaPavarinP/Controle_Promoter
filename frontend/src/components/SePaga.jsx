// "Vale a pena?": o custo do atendimento (o que a 101 paga à agência, ao MEI ou ao CLT) cabe em até 3% do faturamento
// bruto das lojas (o que elas compraram da 101 no ERP)? O limite é editável. Usado nas abas Promotores, Agências e Lojas.
import { useEffect, useState } from 'react'
import { http } from '../api.js'
import { formatarMes, formatarMoeda, formatarPercentual } from '../formato.js'
import { Tabela } from './ui.jsx'

// Situação calculada no servidor: ok | acima | sem_compras | sem_custo | sem_erp | custo_nao_informado
const CLASSES = { ok: 'ok', acima: 'prejuizo', sem_compras: 'sem-faturamento', sem_erp: 'sem-erp',
  custo_nao_informado: 'custo-nao-informado' }

/** 'ok' | 'prejuizo' | 'sem-faturamento' | 'sem-erp' | 'custo-nao-informado' | null (sem custo). */
export const situacao = (linha) => CLASSES[linha?.situacao] || null

function textos(limite) {
  const pct = limite != null ? formatarPercentual(limite) : 'do limite'
  return {
    ok: '🟢 Vale a pena', prejuizo: `🔴 Acima de ${pct}`, 'sem-faturamento': '🔴 Sem compras',
    'sem-erp': '⚪ Falta o faturamento do ERP', 'custo-nao-informado': '⚪ Custo não informado',
  }
}

// O limite em uso (vem do servidor junto com o painel); usado nos textos das etiquetas.
let limiteAtual = 3
export const definirLimite = (limite) => { if (limite != null) limiteAtual = limite }

export function EtiquetaSituacao({ linha, soBolinha = false }) {
  const s = situacao(linha)
  if (!s) return <span className="dica" title="Sem custo no período">—</span>
  const texto = textos(limiteAtual)[s]
  if (soBolinha) {
    // Nas tabelas: só a bolinha; o texto aparece ao passar o mouse (e vai no Excel exportado).
    const [bolinha, ...resto] = texto.split(' ')
    return <span className="se-paga-bolinha" title={resto.join(' ')} aria-label={resto.join(' ')} role="img">{bolinha}</span>
  }
  return <span className={`se-paga se-paga-${s}`}>{texto}</span>
}

export const textoSituacao = (linha) => textos(limiteAtual)[situacao(linha)] || ''

const dicaValeAPena = () => `Vale a pena quando o custo do atendimento é até ${formatarPercentual(limiteAtual)} do ` +
  'faturamento bruto das lojas (VLR TOTAL do ERP). Acima disso, ou com custo e nenhuma compra, não vale.'

// Custo ÷ faturamento bruto: é a conta que define a cor.
export const COLUNA_PERCENTUAL = {
  campo: 'percentual_custo', titulo: '% do faturamento', num: true,
  ordenar: (l) => (l.sem_erp ? null : l.percentual_custo) ?? 9999,
  mostrar: (l) => (l.sem_erp || l.percentual_custo == null ? '—'
    : <b className={situacao(l) === 'ok' ? 'texto-ok' : 'texto-critico'}>{formatarPercentual(l.percentual_custo)}</b>),
  get dica() {
    return `Custo do atendimento ÷ o que as lojas compraram da 101 (faturamento bruto). O máximo é ${formatarPercentual(limiteAtual)}.`
  },
}

// Legenda das bolinhas, embaixo das tabelas que têm a coluna "Vale a pena?".
export function LegendaBolinhas() {
  const limite = formatarPercentual(limiteAtual)
  return (
    <p className="legenda-bolinhas">
      <span>🟢 Vale a pena: custo até {limite} do faturamento</span>
      <span>🔴 Acima de {limite}, ou com custo e nenhuma compra</span>
      <span>⚪ Falta o faturamento do ERP no período, ou custo não informado (ex.: CLT sem valor no arquivo)</span>
      <span>— Sem custo</span>
    </p>
  )
}

export const COLUNA_VALE_A_PENA = {
  legenda: () => <LegendaBolinhas />,
  campo: 'se_paga', titulo: 'Vale a pena?', ordenar: (l) => (l.sem_erp ? null : l.percentual_custo) ?? 9999,
  get dica() { return dicaValeAPena() },
  exportar: (l) => textoSituacao(l), mostrar: (l) => <EtiquetaSituacao linha={l} soBolinha />,
}

// Colunas de dinheiro e do veredito, iguais nas tabelas de promotores, agências e lojas.
export const COLUNAS_SE_PAGA = [
  { campo: 'custo_periodo', titulo: 'Custo', num: true, formato: 'moeda', mostrar: (l) => formatarCusto(l) },
  { campo: 'faturamento', titulo: 'Compraram', num: true, formato: 'moeda',
    mostrar: (l) => (l.sem_erp ? '—' : <>{formatarMoeda(l.faturamento)}{l.faturamento_sem_custo > 0 && (
      <span className="texto-alerta" title={`Mais ${formatarMoeda(l.faturamento_sem_custo)} de compras em ${l.meses_sem_custo} mês(es) sem custo de atendimento: ficam fora do % e do "Vale a pena?" (custo e compras do mesmo período).`}> ⚠</span>)}</>) },
  COLUNA_PERCENTUAL,
  COLUNA_VALE_A_PENA,
]

// Custo vazio no arquivo (ex.: CLT) ≠ R$ 0,00: mostra "não informado".
export const formatarCusto = (l, campo = 'custo_periodo') => (l?.custo_informado === false
  ? <span className="dica" title="O arquivo não traz o valor do mês destas lojas (ex.: CLT)">não informado</span>
  : formatarMoeda(l?.[campo]))

// Visitas: "≈13" quando estimadas pela frequência por semana (arquivo dos MEIs).
export const COLUNA_VISITAS = {
  campo: 'visitas', titulo: 'Visitas', num: true, formato: 'inteiro',
  mostrar: (l) => (l.visitas_estimadas
    ? <span className="dica" title="Estimativa: frequência por semana × dias do mês ÷ 7 (o arquivo não informa as visitas)">≈{l.visitas}</span>
    : l.visitas),
}

function periodoPadrao(meses) {
  if (!meses.length) return { inicio: '', fim: '' }
  const ultimo = meses[meses.length - 1]
  return { inicio: meses.find((m) => m.startsWith(ultimo.slice(0, 4))), fim: ultimo }
}

// "Ocultar agências sem custo": agências que informam as lojas com R$ 0 (ex.: promotores CLT, MEI ou freelancer
// pagos por fora) inflam as listas. A escolha fica guardada neste navegador.
const CHAVE_OCULTAR = 'ocultar-agencias-sem-custo'

function lerOcultar() {
  try {
    return window.localStorage.getItem(CHAVE_OCULTAR) !== 'nao'
  } catch {
    return true
  }
}

export function useOcultarSemCusto(agencias) {
  const [ocultar, setOcultarEstado] = useState(lerOcultar)
  const setOcultar = (valor) => {
    setOcultarEstado(valor)
    try {
      window.localStorage.setItem(CHAVE_OCULTAR, valor ? 'sim' : 'nao')
    } catch { /* navegador sem armazenamento: vale só nesta tela */ }
  }
  // Custo não informado (ex.: CLT) não é "sem custo": essas agências não são ocultadas.
  const semCusto = new Set((agencias || []).filter((a) => a.custo_informado !== false && !(a.custo_periodo > 0))
    .map((a) => a.chave))
  return { ocultar, setOcultar, semCusto, visivel: (chaves) => !ocultar || chaves.some((c) => !semCusto.has(c)) }
}

export function OpcaoOcultarSemCusto({ ocultar, setOcultar, semCusto }) {
  if (!semCusto.size) return null
  return (
    <label className="marcar" title="Agências que informaram todas as lojas com custo R$ 0 no período">
      <input type="checkbox" checked={ocultar} onChange={(e) => setOcultar(e.target.checked)} />
      Ocultar agências sem custo ({semCusto.size})
    </label>
  )
}

/** Busca o painel do período (e filtros extras, ex.: { promotor }) e devolve { dados, periodo, setPeriodo, recarregar }. */
export function useSePaga(meses, extras = {}, periodoInicial = null) {
  const [periodo, setPeriodo] = useState(() => periodoInicial || periodoPadrao(meses))
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [versao, setVersao] = useState(0)
  const chaveExtras = JSON.stringify(extras)
  useEffect(() => {
    if (!periodo.inicio && meses.length) setPeriodo(periodoPadrao(meses))
  }, [meses, periodo.inicio])
  useEffect(() => {
    if (!periodo.inicio) return
    let cancelado = false
    setErro('')
    http.get(`/api/painel?${new URLSearchParams({ ...periodo, ...JSON.parse(chaveExtras) })}`)
      .then((d) => !cancelado && setDados(d))
      .catch((e) => !cancelado && setErro(e.message))
    return () => { cancelado = true }
  }, [periodo, versao, chaveExtras])
  return { dados, erro, periodo, setPeriodo, recarregar: () => setVersao((v) => v + 1) }
}

/** Filtros de local e de quem atende (UF → município → mercado, agência, tipo). Recalculam os números do topo. */
export function FiltrosLocal({ opcoes, valor, aoMudar, campos = ['uf', 'cidade', 'loja', 'agencia', 'tipo', 'supervisor'] }) {
  if (!opcoes) return null
  const mudar = (campo, v) => {
    const novo = { ...valor, [campo]: v }
    if (campo === 'uf') { novo.cidade = ''; novo.loja = '' }
    if (campo === 'cidade') novo.loja = ''
    aoMudar(novo)
  }
  const cidades = opcoes.cidades.filter((c) => !valor.uf || c.uf === valor.uf)
  const lojas = opcoes.lojas.filter((l) => (!valor.uf || l.uf === valor.uf) && (!valor.cidade || l.cidade === valor.cidade))
  return (
    <div className="filtros-local">
      {campos.includes('uf') && (
        <label className="filtro">UF
          <select value={valor.uf || ''} onChange={(e) => mudar('uf', e.target.value)}>
            <option value="">Todas</option>
            {opcoes.ufs.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </label>
      )}
      {campos.includes('cidade') && (
        <label className="filtro">Município
          <select value={valor.cidade || ''} onChange={(e) => mudar('cidade', e.target.value)}>
            <option value="">Todos</option>
            {cidades.map((c) => <option key={`${c.uf}-${c.cidade}`} value={c.cidade}>{c.cidade}{!valor.uf && ` - ${c.uf}`}</option>)}
          </select>
        </label>
      )}
      {campos.includes('loja') && (
        <label className="filtro">Mercado
          <input list="lista-mercados" value={valor.loja || ''} placeholder={`Todos (${lojas.length})`}
            onChange={(e) => mudar('loja', lojas.some((l) => l.nome === e.target.value) || !e.target.value ? e.target.value : valor.loja)}
            onInput={(e) => { if (!e.target.value) mudar('loja', '') }} />
          <datalist id="lista-mercados">
            {lojas.slice(0, 500).map((l) => <option key={`${l.nome}-${l.cidade}`} value={l.nome}>{l.cidade} - {l.uf}</option>)}
          </datalist>
        </label>
      )}
      {campos.includes('agencia') && (
        <label className="filtro">Agência
          <select value={valor.agencia || ''} onChange={(e) => mudar('agencia', e.target.value)}>
            <option value="">Todas</option>
            {opcoes.agencias.map((a) => <option key={a.chave} value={a.chave}>{a.nome}</option>)}
          </select>
        </label>
      )}
      {campos.includes('tipo') && (opcoes.tipos || []).length > 0 && (
        <label className="filtro">Tipo
          <select value={valor.tipo || ''} onChange={(e) => mudar('tipo', e.target.value)}>
            <option value="">Todos</option>
            {opcoes.tipos.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
      )}
      {campos.includes('supervisor') && (opcoes.supervisores || []).length > 0 && (
        <label className="filtro">Supervisor
          <select value={valor.supervisor || ''} onChange={(e) => mudar('supervisor', e.target.value)}>
            <option value="">Todos</option>
            {opcoes.supervisores.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      )}
      {Object.values(valor).some(Boolean) && (
        <button className="secundario" onClick={() => aoMudar({})}>Limpar filtros</button>
      )}
    </div>
  )
}

/** Quadro do topo: período, limite (máximo de % do faturamento) e o resultado geral. */
export function QuadroSePaga({ titulo, meses, periodo, setPeriodo, dados, podeEditar, aoMudarLimite, contar = 'promotores',
  linhas, children }) {
  const limite = dados?.regras?.limite_percentual
  const [editando, setEditando] = useState(null)
  const [erro, setErro] = useState('')
  const resumo = dados?.resumo
  definirLimite(limite)
  const contagem = { ok: 0, prejuizo: 0, 'sem-faturamento': 0, 'sem-erp': 0, 'custo-nao-informado': 0 }
  for (const p of linhas || dados?.[contar] || []) {
    const s = situacao(p)
    if (s) contagem[s] += 1
  }

  async function salvarLimite() {
    setErro('')
    try {
      const { regras } = await http.get('/api/regras')
      await http.put('/api/regras', { ...regras, limite_percentual: editando === '' ? null : editando })
      setEditando(null)
      aoMudarLimite()
    } catch (e) {
      setErro(e.message)
    }
  }

  return (
    <section className="bloco se-paga-quadro">
      <div className="bloco-cabecalho">
        <h2>{titulo}</h2>
        <div className="bloco-ferramentas">
          <label className="filtro">De
            <select value={periodo.inicio} onChange={(e) => setPeriodo({ ...periodo, inicio: e.target.value })}>
              {meses.map((m) => <option key={m} value={m}>{formatarMes(m)}</option>)}
            </select>
          </label>
          <label className="filtro">Até
            <select value={periodo.fim} onChange={(e) => setPeriodo({ ...periodo, fim: e.target.value })}>
              {meses.map((m) => <option key={m} value={m}>{formatarMes(m)}</option>)}
            </select>
          </label>
        </div>
      </div>
      {children}

      <div className="se-paga-margem">
        <b>Custo máximo do atendimento:</b>{' '}
        {editando !== null ? (
          <>
            <input className="margem-campo" inputMode="decimal" value={editando} autoFocus aria-label="Custo máximo (% do faturamento)"
              onChange={(e) => setEditando(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && salvarLimite()} /> % do faturamento
            <button onClick={salvarLimite}>Salvar</button>
            <button className="secundario" onClick={() => setEditando(null)}>Cancelar</button>
          </>
        ) : (
          <>
            <b className="margem-valor">{limite != null ? formatarPercentual(limite) : '…'}</b> do faturamento bruto das lojas
            {podeEditar && <button className="secundario" onClick={() => setEditando(limite != null ? String(limite).replace('.', ',') : '')}>Alterar</button>}
          </>
        )}
        {erro && <p className="erro">{erro}</p>}
        <p className="dica">
          % do faturamento = o que a 101 paga pelo atendimento (arquivos das agências) ÷ o que as lojas compraram da 101
          (VLR TOTAL do ERP, bruto). Exemplo: as lojas compraram R$ 10.000 e o promotor custa R$ 250 = 2,5%, vale a pena.
        </p>
      </div>

      {resumo && (
        <div className="cards cards-3">
          <div className="card"><span>Lojas compraram</span><strong>{resumo.sem_erp ? '—' : formatarMoeda(resumo.faturamento)}</strong>
            <small>faturamento bruto do ERP</small></div>
          <div className="card"><span>Custo do atendimento</span><strong>{formatarCusto(resumo, 'custo')}</strong>
            <small>pago às agências, MEIs e CLT</small></div>
          <div className={`card ${situacao(resumo) === 'ok' ? 'pct-ok' : situacao(resumo) ? 'pct-critico' : ''}`}>
            <span>% do faturamento</span>
            <strong>{resumo.sem_erp || resumo.percentual_custo == null ? '—' : formatarPercentual(resumo.percentual_custo)}</strong>
            <small><EtiquetaSituacao linha={resumo} /></small>
          </div>
        </div>
      )}
      {(resumo?.avisos || []).map((aviso) => <p key={aviso} className="nota">⚠ {aviso}</p>)}
      {resumo && (
        <p className="se-paga-legenda">
          <span className="se-paga se-paga-ok">🟢 Vale a pena: {contagem.ok}</span>{' '}
          <span className="se-paga se-paga-prejuizo">🔴 Não vale a pena: {contagem.prejuizo + contagem['sem-faturamento']}</span>
          {contagem['sem-erp'] > 0 && <span className="se-paga se-paga-sem-erp">⚪ Falta o faturamento: {contagem['sem-erp']}</span>}
          {contagem['custo-nao-informado'] > 0 && (
            <span className="se-paga se-paga-custo-nao-informado">⚪ Custo não informado: {contagem['custo-nao-informado']}</span>)}
        </p>
      )}
    </section>
  )
}

/** Cartões do resultado de um promotor (ou agência) e a tabela das lojas dele. */
export function FichaSePaga({ linha, lojas, periodo, carregado, temFaturamento }) {
  if (!temFaturamento) {
    return (
      <div className="aviso">
        Ainda não há faturamento importado. Importe o arquivo do ERP em <b>Importações › Faturamento do ERP</b> para ver quanto as lojas
        compraram e se vale a pena.
      </div>
    )
  }
  if (!carregado) return <p className="dica">Calculando…</p>
  if (!linha) {
    return (
      <div className="aviso">
        Sem atendimento de {formatarMes(periodo.inicio)} a {formatarMes(periodo.fim)} nos arquivos das agências.
      </div>
    )
  }
  return (
    <>
      <p className="dica">Período: {formatarMes(periodo.inicio)} a {formatarMes(periodo.fim)}</p>
      <div className="cards cards-3">
        <div className="card"><span>Lojas compraram</span><strong>{linha.sem_erp ? '—' : formatarMoeda(linha.faturamento)}</strong></div>
        <div className="card"><span>Custo no período</span><strong>{formatarCusto(linha)}</strong></div>
        <div className={`card ${situacao(linha) === 'ok' ? 'pct-ok' : situacao(linha) ? 'pct-critico' : ''}`}>
          <span>% do faturamento</span>
          <strong>{linha.sem_erp || linha.percentual_custo == null ? '—' : formatarPercentual(linha.percentual_custo)}</strong>
          <small><EtiquetaSituacao linha={linha} /></small>
        </div>
      </div>
      <Tabela
        chave="chave"
        linhas={lojas}
        porPagina={10}
        arquivo={`lojas-${linha.nome || linha.chave}`}
        vazio="Nenhuma loja no período."
        colunas={[
          { campo: 'loja', titulo: 'Loja', quebra: true,
            mostrar: (l) => <>{l.loja}{l.compartilhado && <span className="etiqueta" title="O CNPJ é de mais de uma loja: o faturamento foi dividido entre elas">CNPJ compartilhado</span>}</> },
          { campo: 'cidade', titulo: 'Cidade', mostrar: (l) => `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}` },
          { campo: 'dias', titulo: 'Dias', quebra: true },
          COLUNA_VISITAS,
          ...COLUNAS_SE_PAGA,
        ]}
      />
    </>
  )
}
