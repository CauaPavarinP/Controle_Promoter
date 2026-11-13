// Aba Promotores: montada a partir dos arquivos das agências. Para cada promotor, quem é, onde atende, quanto custa,
// quanto as lojas dele compraram e se vale a pena mantê-lo.
import { useState } from 'react'
import { formatarMes, formatarMoeda } from '../formato.js'
import {
  COLUNA_PERCENTUAL, COLUNA_VALE_A_PENA, COLUNAS_SE_PAGA, FichaSePaga, FiltrosLocal, OpcaoOcultarSemCusto, QuadroSePaga,
  situacao, useOcultarSemCusto, useSePaga,
  formatarCusto,
} from './SePaga.jsx'
import { Modal, Tabela } from './ui.jsx'

function MesAMes({ linhas }) {
  const comAtendimento = linhas.filter((l) => l.com_atendimento)
  if (!comAtendimento.length) return <p className="dica">Sem atendimento no período.</p>
  return (
    <Tabela
      chave="mes"
      linhas={linhas}
      porPagina={24}
      arquivo="mes-a-mes"
      colunas={[
        { campo: 'mes', titulo: 'Mês', mostrar: (l) => formatarMes(l.mes) },
        { campo: 'lojas', titulo: 'Lojas', num: true, formato: 'inteiro', mostrar: (l) => (l.com_atendimento ? l.lojas : '—') },
        { campo: 'visitas', titulo: 'Visitas', num: true, formato: 'inteiro', mostrar: (l) => (l.com_atendimento ? l.visitas : '—') },
        ...COLUNAS_SE_PAGA.map((c) => ({ ...c, semOrdem: true,
          mostrar: (l) => (l.com_atendimento ? c.mostrar(l) : <span className="dica">sem atendimento</span>) })),
      ]}
    />
  )
}

function FichaPromotor({ promotor, meses, periodo, aoFechar }) {
  // O painel filtrado por este promotor traz as lojas dele e o mês a mês.
  const { dados, erro } = useSePaga(meses, { promotor: promotor.chave }, periodo)
  const linha = dados?.promotores.find((p) => p.chave === promotor.chave)
  return (
    <Modal titulo={promotor.nome} aoFechar={aoFechar} largo>
      {erro && <div className="erro-caixa">{erro}</div>}
      <section className="detalhe-secao">
        <h3>Dados</h3>
        <dl className="dados">
          <dt>Agência</dt><dd>{promotor.agencia}</dd>
          <dt>Tipo</dt><dd>{promotor.tipo || '—'}</dd>
          {promotor.supervisor && (<><dt>Supervisor</dt><dd>{promotor.supervisor}</dd></>)}
          {promotor.codigo && (<><dt>Código</dt><dd>{promotor.codigo}</dd></>)}
          <dt>Onde atende</dt><dd>{promotor.cidades || '—'}{promotor.ufs && ` (${promotor.ufs})`}</dd>
          <dt>Nos arquivos</dt><dd>de {formatarMes(promotor.primeiro_mes)} a {formatarMes(promotor.ultimo_mes)} ({promotor.meses_com_atendimento} mês(es) com atendimento no período)</dd>
          <dt>Lojas</dt><dd>{promotor.lojas_ultimo_mes} no último mês · {promotor.visitas} visita(s) no período</dd>
        </dl>
      </section>
      <section className="detalhe-secao">
        <h3>Vale a pena mantê-lo?</h3>
        <FichaSePaga linha={linha} lojas={dados?.lojas || []} periodo={periodo} carregado={Boolean(dados)} temFaturamento={meses.length > 0} />
      </section>
      <section className="detalhe-secao">
        <h3>Mês a mês</h3>
        {dados ? <MesAMes linhas={dados.mes_a_mes} /> : <p className="dica">Calculando…</p>}
      </section>
    </Modal>
  )
}

export default function PromotoresAba({ admin, meses, opcoes }) {
  // Local (UF → município → mercado), agência e tipo vão para o servidor: os números do topo recalculam para o filtro.
  const [local, setLocal] = useState({})
  const extras = Object.fromEntries(Object.entries(local).filter(([, v]) => v))
  const sePaga = useSePaga(meses, extras)
  const [filtros, setFiltros] = useState({ busca: '', resultado: '' })
  const [aberto, setAberto] = useState(null)
  const ocultacao = useOcultarSemCusto(sePaga.dados?.agencias)

  if (!meses.length) {
    return <div className="aviso">Ainda não há dados. Importe o faturamento do ERP e os arquivos das agências.</div>
  }
  const promotores = sePaga.dados?.promotores || []
  const termo = filtros.busca.trim().toLowerCase()
  const visiveis = promotores.filter((p) => ocultacao.visivel([p.agencia_chave]) &&
    (!filtros.resultado || filtros.resultado.split(',').includes(situacao(p))) &&
    (!termo || `${p.nome} ${p.codigo} ${p.cidades} ${p.agencia} ${p.supervisor}`.toLowerCase().includes(termo)))

  return (
    <>
      <QuadroSePaga titulo="Os promotores valem o que custam?" meses={meses} periodo={sePaga.periodo}
        linhas={sePaga.dados ? promotores.filter((p) => ocultacao.visivel([p.agencia_chave])) : undefined}
        setPeriodo={sePaga.setPeriodo} dados={sePaga.dados} podeEditar={admin} aoMudarLimite={sePaga.recarregar}>
        <FiltrosLocal opcoes={opcoes} valor={local} aoMudar={setLocal} />
      </QuadroSePaga>
      {sePaga.erro && <div className="erro-caixa">{sePaga.erro}</div>}
      <section className="bloco">
        <div className="bloco-cabecalho">
          <div className="bloco-ferramentas">
            <input placeholder="Buscar nome, código, cidade ou agência" value={filtros.busca}
              onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })} />
            <select value={filtros.resultado} onChange={(e) => setFiltros({ ...filtros, resultado: e.target.value })} aria-label="Vale a pena?">
              <option value="">Vale a pena? Todos</option>
              <option value="prejuizo,sem-faturamento">🔴 Só quem não vale a pena</option>
              <option value="ok">🟢 Só quem vale a pena</option>
              <option value="sem-erp">⚪ Só sem faturamento importado</option>
            </select>
            <OpcaoOcultarSemCusto {...ocultacao} />
          </div>
        </div>
        <p className="dica">
          Promotores dos arquivos das agências no período. Clique num promotor para ver os dados dele, as lojas e o mês a mês.
        </p>
        {!sePaga.dados ? <p className="carregando">Calculando…</p> : (
          <Tabela
            chave="chave"
            linhas={visiveis}
            arquivo="promotores"
            aoClicar={(p) => setAberto(p)}
            vazio="Nenhum promotor nos arquivos das agências neste período."
            colunas={[
              { campo: 'nome', titulo: 'Promotor', quebra: true },
              { campo: 'tipo', titulo: 'Tipo' },
              { campo: 'agencia', titulo: 'Agência', quebra: true },
              { campo: 'supervisor', titulo: 'Supervisor', quebra: true },
              { campo: 'ufs', titulo: 'UF' },
              { campo: 'lojas_ultimo_mes', titulo: 'Lojas', num: true, formato: 'inteiro' },
              { campo: 'visitas', titulo: 'Visitas', num: true, formato: 'inteiro' },
              { campo: 'custo_periodo', titulo: 'Custo', num: true, formato: 'moeda', mostrar: (p) => formatarCusto(p) },
              { campo: 'faturamento', titulo: 'Compraram', num: true, formato: 'moeda',
                mostrar: (p) => (p.sem_erp ? '—' : formatarMoeda(p.faturamento)) },
              COLUNA_PERCENTUAL,
              COLUNA_VALE_A_PENA,
            ]}
          />
        )}
      </section>
      {aberto && <FichaPromotor promotor={aberto} meses={meses} periodo={sePaga.periodo} aoFechar={() => setAberto(null)} />}
    </>
  )
}
