import { useEffect, useState } from 'react'
import { formatarMes } from '../formato.js'

function Seletor({ rotulo, valor, aoMudar, opcoes, todos = 'Todos' }) {
  return (
    <label className="filtro">
      {rotulo}
      <select value={valor} onChange={(e) => aoMudar(e.target.value)}>
        {todos !== null && <option value="">{todos}</option>}
        {opcoes.map((o) => (
          <option key={o.valor} value={o.valor}>{o.texto}</option>
        ))}
      </select>
    </label>
  )
}

/** Campo de loja com sugestões: só filtra quando o nome bate com uma loja da lista (ou fica vazio). */
function FiltroLoja({ lojas, valor, aoMudar }) {
  const [texto, setTexto] = useState(valor)
  useEffect(() => setTexto(valor), [valor])
  function mudar(novo) {
    setTexto(novo)
    if (!novo || lojas.some((p) => p.nome === novo)) aoMudar(novo)
  }
  return (
    <label className="filtro filtro-pdv">
      Loja
      <input list="lista-lojas" value={texto} placeholder="Todas" onChange={(e) => mudar(e.target.value)} />
      <datalist id="lista-lojas">
        {lojas.map((p) => <option key={p.nome} value={p.nome}>{`${p.cidade}${p.uf ? ` - ${p.uf}` : ''}`}</option>)}
      </datalist>
    </label>
  )
}

const indice = (anoMes) => Number(anoMes.slice(0, 4)) * 12 + Number(anoMes.slice(5, 7)) - 1
const rotulo = (i) => `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`

export default function Filtros({ opcoes, filtros, alterar, limpar }) {
  const meses = opcoes.meses.map((m) => ({ valor: m, texto: formatarMes(m) }))

  // Listas dependentes: promotores da agência escolhida, cidades da UF escolhida.
  const promotores = opcoes.promotores
    .filter((p) => !filtros.agencia || p.agencia_chave === filtros.agencia)
    .map((p) => ({ valor: p.chave, texto: filtros.agencia ? p.nome : `${p.nome} (${p.agencia})` }))
  const cidades = opcoes.cidades
    .filter((c) => !filtros.uf || c.uf === filtros.uf)
    .map((c) => ({ valor: c.cidade, texto: filtros.uf ? c.cidade : `${c.cidade} - ${c.uf}` }))

  function mudarAgencia(valor) {
    alterar('agencia', valor)
    const promotor = opcoes.promotores.find((p) => p.chave === filtros.promotor)
    if (valor && promotor && promotor.agencia_chave !== valor) alterar('promotor', '')
  }

  function mudarUf(valor) {
    alterar('uf', valor)
    alterar('cidade', '')
  }

  // Atalhos de período, contados a partir do último mês com faturamento.
  const ultimo = opcoes.meses[opcoes.meses.length - 1]
  function aplicarPeriodo(inicioDesejado) {
    const inicio = opcoes.meses.find((m) => indice(m) >= indice(inicioDesejado)) || opcoes.meses[0]
    alterar('modo', 'acumulado')
    alterar('inicio', inicio)
    alterar('fim', ultimo)
  }
  const atalhos = [
    { texto: 'Ano até hoje', inicio: `${ultimo.slice(0, 4)}-01` },
    { texto: 'Últimos 3 meses', inicio: rotulo(indice(ultimo) - 2) },
    { texto: 'Últimos 6 meses', inicio: rotulo(indice(ultimo) - 5) },
    { texto: 'Últimos 12 meses', inicio: rotulo(indice(ultimo) - 11) },
  ]

  // Filtros escolhidos, mostrados como etiquetas com "x" para tirar.
  const nomePromotor = opcoes.promotores.find((p) => p.chave === filtros.promotor)?.nome
  const nomeAgencia = opcoes.agencias.find((a) => a.chave === filtros.agencia)?.nome
  const ativos = [
    filtros.agencia && { campo: 'agencia', texto: `Agência: ${nomeAgencia || filtros.agencia}` },
    filtros.tipo && { campo: 'tipo', texto: `Tipo: ${filtros.tipo}` },
    filtros.promotor && { campo: 'promotor', texto: `Promotor: ${nomePromotor || filtros.promotor}` },
    filtros.uf && { campo: 'uf', texto: `UF: ${filtros.uf}` },
    filtros.cidade && { campo: 'cidade', texto: `Cidade: ${filtros.cidade}` },
    filtros.loja && { campo: 'loja', texto: `Loja: ${filtros.loja}` },
  ].filter(Boolean)
  const [maisFiltros, setMaisFiltros] = useState(false)
  const escondidosAtivos = ['promotor', 'cidade', 'loja'].filter((c) => filtros[c]).length

  return (
    <section className="filtros">
      <div className="filtros-linha">
        <div className="filtro">
          Período
          <div className="alternar">
            <button className={filtros.modo === 'acumulado' ? 'ativo' : ''} onClick={() => alterar('modo', 'acumulado')}>
              Acumulado
            </button>
            <button className={filtros.modo === 'mes' ? 'ativo' : ''} onClick={() => alterar('modo', 'mes')}>
              Um mês
            </button>
          </div>
        </div>
        <Seletor
          rotulo={filtros.modo === 'mes' ? 'Mês' : 'De'}
          valor={filtros.inicio}
          aoMudar={(v) => alterar('inicio', v)}
          opcoes={meses}
          todos={null}
        />
        {filtros.modo === 'acumulado' && (
          <Seletor rotulo="Até" valor={filtros.fim} aoMudar={(v) => alterar('fim', v)} opcoes={meses} todos={null} />
        )}
        <Seletor
          rotulo="Agência"
          valor={filtros.agencia}
          aoMudar={mudarAgencia}
          opcoes={opcoes.agencias.map((a) => ({ valor: a.chave, texto: a.nome }))}
          todos="Todas"
        />
        {(opcoes.tipos || []).length > 0 && (
          <Seletor rotulo="Tipo" valor={filtros.tipo} aoMudar={(v) => alterar('tipo', v)}
            opcoes={opcoes.tipos.map((t) => ({ valor: t, texto: t }))} todos="Todos" />
        )}
        <Seletor rotulo="UF" valor={filtros.uf} aoMudar={mudarUf} opcoes={opcoes.ufs.map((u) => ({ valor: u, texto: u }))} />
        <button className="secundario mais-filtros" onClick={() => setMaisFiltros((v) => !v)} aria-expanded={maisFiltros}>
          {maisFiltros ? 'Menos filtros ▴' : `Mais filtros${escondidosAtivos ? ` (${escondidosAtivos})` : ''} ▾`}
        </button>
      </div>

      {maisFiltros && (
        <div className="filtros-linha">
          <Seletor rotulo="Promotor" valor={filtros.promotor} aoMudar={(v) => alterar('promotor', v)} opcoes={promotores} />
          <Seletor rotulo="Cidade" valor={filtros.cidade} aoMudar={(v) => alterar('cidade', v)} opcoes={cidades} todos="Todas" />
          <FiltroLoja lojas={opcoes.lojas || []} valor={filtros.loja} aoMudar={(v) => alterar('loja', v)} />
          <div className="atalhos">
            <span className="dica">Período rápido:</span>
            {atalhos.map((a) => (
              <button key={a.texto} className="secundario" onClick={() => aplicarPeriodo(a.inicio)}>{a.texto}</button>
            ))}
          </div>
        </div>
      )}

      {ativos.length > 0 && (
        <div className="filtros-ativos">
          {ativos.map((a) => (
            <button key={a.campo} className="chip" onClick={() => (a.campo === 'uf' ? mudarUf('') : alterar(a.campo, ''))}
              title="Tirar este filtro" aria-label={`Tirar o filtro ${a.texto}`}>
              {a.texto} <span aria-hidden="true">✕</span>
            </button>
          ))}
          <button className="link" onClick={limpar}>Limpar tudo</button>
        </div>
      )}
    </section>
  )
}
