// Aba Promotores: montada a partir dos arquivos das agências. Para cada promotor, quem é, onde atende, quanto custa,
// quanto as lojas dele compraram e se vale a pena mantê-lo.
import { useState } from 'react'
import { formatarMes, formatarMoeda, formatarPercentual } from '../formato.js'
import { COLUNAS_SE_PAGA, EtiquetaSituacao, FichaSePaga, QuadroSePaga, situacao, textoSituacao, useSePaga } from './SePaga.jsx'
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

export default function PromotoresAba({ admin, meses }) {
  const sePaga = useSePaga(meses)
  const [filtros, setFiltros] = useState({ busca: '', agencia: '', resultado: '' })
  const [aberto, setAberto] = useState(null)

  if (!meses.length) {
    return <div className="aviso">Ainda não há dados. Importe o faturamento do ERP e os arquivos das agências.</div>
  }
  const promotores = sePaga.dados?.promotores || []
  const agencias = [...new Map(promotores.map((p) => [p.agencia_chave, p.agencia])).entries()].sort((a, b) => a[1].localeCompare(b[1]))
  const termo = filtros.busca.trim().toLowerCase()
  const visiveis = promotores.filter((p) =>
    (!filtros.agencia || p.agencia_chave === filtros.agencia) &&
    (!filtros.resultado || filtros.resultado.split(',').includes(situacao(p))) &&
    (!termo || `${p.nome} ${p.codigo} ${p.cidades} ${p.agencia}`.toLowerCase().includes(termo)))

  return (
    <>
      <QuadroSePaga titulo="Os promotores valem o que custam?" meses={meses} periodo={sePaga.periodo}
        setPeriodo={sePaga.setPeriodo} dados={sePaga.dados} podeEditar={admin} aoMudarMargem={sePaga.recarregar} />
      {sePaga.erro && <div className="erro-caixa">{sePaga.erro}</div>}
      <section className="bloco">
        <div className="bloco-cabecalho">
          <div className="bloco-ferramentas">
            <input placeholder="Buscar nome, código, cidade ou agência" value={filtros.busca}
              onChange={(e) => setFiltros({ ...filtros, busca: e.target.value })} />
            <select value={filtros.agencia} onChange={(e) => setFiltros({ ...filtros, agencia: e.target.value })} aria-label="Agência">
              <option value="">Todas as agências</option>
              {agencias.map(([chave, nome]) => <option key={chave} value={chave}>{nome}</option>)}
            </select>
            <select value={filtros.resultado} onChange={(e) => setFiltros({ ...filtros, resultado: e.target.value })} aria-label="Vale a pena?">
              <option value="">Vale a pena? Todos</option>
              <option value="prejuizo,sem-faturamento">🔴 Só quem não vale a pena</option>
              <option value="limite">🟡 Só no limite</option>
              <option value="ok">🟢 Só quem vale a pena</option>
            </select>
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
              { campo: 'agencia', titulo: 'Agência', quebra: true },
              { campo: 'ufs', titulo: 'UF' },
              { campo: 'lojas_ultimo_mes', titulo: 'Lojas', num: true, formato: 'inteiro' },
              { campo: 'visitas', titulo: 'Visitas', num: true, formato: 'inteiro' },
              { campo: 'custo_periodo', titulo: 'Custo', num: true, formato: 'moeda', mostrar: (p) => formatarMoeda(p.custo_periodo) },
              { campo: 'percentual_custo', titulo: '% das compras', num: true, mostrar: (p) => formatarPercentual(p.percentual_custo) },
              { campo: 'se_paga', titulo: 'Vale a pena?', ordenar: (p) => p.percentual_do_lucro ?? 9999,
                exportar: textoSituacao, mostrar: (p) => <EtiquetaSituacao linha={p} /> },
            ]}
          />
        )}
      </section>
      {aberto && <FichaPromotor promotor={aberto} meses={meses} periodo={sePaga.periodo} aoFechar={() => setAberto(null)} />}
    </>
  )
}
