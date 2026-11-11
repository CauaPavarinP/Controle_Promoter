// Tabela única do Resumo, que abre em níveis: UF da loja → agência → promotor.
import { useState } from 'react'
import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'
import { exportarExcel, useImprimindo } from './ui.jsx'

const COLUNAS = [
  { campo: 'nome', titulo: 'UF / Agência / Promotor' },
  { campo: 'promotores', titulo: 'Promotores', num: true },
  { campo: 'lojas', titulo: 'Lojas', num: true },
  { campo: 'visitas', titulo: 'Visitas', num: true },
  { campo: 'custo_periodo', titulo: 'Custo (agências)', num: true, moeda: true },
  { campo: 'faturamento', titulo: 'Lojas compraram', num: true, moeda: true },
  { campo: 'percentual_custo', titulo: 'Custo ÷ faturamento', num: true },
]

/** Monta a árvore com as linhas do painel, que já vêm na ordem UF → agência → promotor. */
function montarArvore(porUf) {
  const ufs = []
  for (const l of porUf) {
    if (l.nivel === 'uf') {
      ufs.push({ ...l, chave: `uf-${l.uf}`, filhos: [] })
    } else if (l.nivel === 'agencia') {
      ufs[ufs.length - 1].filhos.push({ ...l, chave: `a-${l.uf}-${l.agencia_chave}`, filhos: [] })
    } else {
      const equipe = ufs[ufs.length - 1].filhos
      equipe[equipe.length - 1].filhos.push({ ...l, chave_promotor: l.chave, chave: `p-${l.uf}-${l.chave}`, promotores: null })
    }
  }
  return ufs
}

function Celula({ coluna, linha, regras }) {
  const valor = linha[coluna.campo]
  if (coluna.campo === 'percentual_custo') {
    return <span className={classePercentual(valor, regras)}>{formatarPercentual(valor)}</span>
  }
  if (coluna.moeda) return formatarMoeda(valor)
  return valor ?? '—'
}

export default function ResumoArvore({ porUf, resumo, regras, aoAbrirPromotor }) {
  const [abertos, setAbertos] = useState(() => new Set())
  const imprimindo = useImprimindo()
  const arvore = montarArvore(porUf)
  const colunas = COLUNAS
  const total = { ...resumo, nome: 'Total geral', custo_periodo: resumo.custo }
  const aberto = (chave) => imprimindo || abertos.has(chave)

  function alternar(chave) {
    setAbertos((atual) => {
      const novo = new Set(atual)
      if (novo.has(chave)) novo.delete(chave)
      else novo.add(chave)
      return novo
    })
  }
  const abrirTudo = () => setAbertos(new Set(arvore.flatMap((u) => [u.chave, ...u.filhos.map((s) => s.chave)])))

  // Linhas visíveis, na ordem da tabela, com o nível de cada uma.
  const linhas = []
  for (const uf of arvore) {
    linhas.push({ ...uf, nivel: 0 })
    if (!aberto(uf.chave)) continue
    for (const sup of uf.filhos) {
      linhas.push({ ...sup, nivel: 1 })
      if (aberto(sup.chave)) sup.filhos.forEach((p) => linhas.push({ ...p, nivel: 2 }))
    }
  }

  function exportar() {
    // No Excel o nível aparece pelo recuo do nome.
    const todas = arvore.flatMap((u) => [
      { ...u, tipo: 'UF' },
      ...u.filhos.flatMap((s) => [
        { ...s, tipo: 'Supervisor', nome: `    ${s.nome}` },
        ...s.filhos.map((p) => ({ ...p, tipo: 'Promotor', nome: `        ${p.nome}` })),
      ]),
    ])
    exportarExcel('resumo-custo-x-faturamento', [{ campo: 'tipo', titulo: 'Nível' }, ...colunas], todas, [{ ...total, tipo: 'Total' }], (l) => l.tipo === 'UF')
  }

  return (
    <section className="bloco">
      <div className="bloco-cabecalho">
        <h2>Custo × compras por UF, agência e promotor</h2>
        <div className="bloco-ferramentas nao-imprimir">
          <button className="secundario" onClick={abrirTudo}>Abrir tudo</button>
          <button className="secundario" onClick={() => setAbertos(new Set())}>Fechar tudo</button>
        </div>
      </div>
      <p className="dica nao-imprimir">
        A UF é a da loja: promotor que atende mais de uma UF aparece em cada uma, com o custo e as compras daquelas lojas.
        Clique numa UF para ver as agências, numa agência para ver os promotores e num promotor para ver as lojas dele.
      </p>
      <div className="tabela-rolagem">
        <table className="arvore">
          <thead>
            <tr>{colunas.map((c) => <th key={c.campo} className={c.num ? 'num' : ''}>{c.titulo}</th>)}</tr>
          </thead>
          <tbody>
            {!linhas.length && <tr><td colSpan={colunas.length} className="vazio">Nenhum promotor com esses filtros.</td></tr>}
            {linhas.map((l) => {
              const temFilhos = l.nivel < 2 && l.filhos.length > 0
              const clicar = l.nivel === 2 ? () => aoAbrirPromotor(l.chave_promotor) : temFilhos ? () => alternar(l.chave) : undefined
              return (
                <tr key={l.chave} className={`nivel-${l.nivel} ${clicar ? 'clicavel' : ''}`} onClick={clicar}>
                  {colunas.map((c, i) => (
                    <td key={c.campo} className={c.num ? 'num' : ''}>
                      {i === 0 ? (
                        <span className="arvore-nome" style={{ paddingLeft: l.nivel * 22 }}>
                          {l.nivel < 2 && <span className="seta" aria-hidden="true">{temFilhos ? (aberto(l.chave) ? '▾' : '▸') : ''}</span>}
                          {l.nome}
                          {l.nivel === 2 && <span className="dica"> · ver lojas</span>}
                        </span>
                      ) : (
                        <Celula coluna={c} linha={l} regras={regras} />
                      )}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
          {linhas.length > 0 && (
            <tfoot>
              <tr>
                {colunas.map((c, i) => (
                  <td key={c.campo} className={c.num ? 'num' : ''}>
                    {i === 0 ? total.nome : <Celula coluna={c} linha={total} regras={regras} />}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
      <div className="tabela-rodape nao-imprimir">
        <span className="dica">{arvore.length} UF(s)</span>
        <button className="secundario" onClick={exportar}>Exportar Excel</button>
      </div>
    </section>
  )
}
