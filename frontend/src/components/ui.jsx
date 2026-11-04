// Peças reaproveitadas pelas telas de cadastro: janela (modal), campo de formulário,
// tabela com ordenação, paginação e exportação, e lista de escolha com busca.
import { useEffect, useMemo, useState } from 'react'

export function Modal({ titulo, aoFechar, children, rodape, largo = false }) {
  useEffect(() => {
    const aoTeclar = (e) => e.key === 'Escape' && aoFechar()
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [aoFechar])

  return (
    <div className="modal-fundo" onMouseDown={(e) => e.target === e.currentTarget && aoFechar()}>
      <div className={`modal ${largo ? 'modal-largo' : ''}`} role="dialog" aria-modal="true">
        <header className="modal-topo">
          <h2>{titulo}</h2>
          <button className="fechar" onClick={aoFechar} aria-label="Fechar">×</button>
        </header>
        <div className="modal-corpo">{children}</div>
        {rodape && <footer className="modal-rodape">{rodape}</footer>}
      </div>
    </div>
  )
}

export function Campo({ rotulo, children, dica, largura }) {
  return (
    <label className="campo" style={largura ? { flexBasis: largura } : undefined}>
      <span>{rotulo}</span>
      {children}
      {dica && <small className="dica">{dica}</small>}
    </label>
  )
}

const SITUACOES_ROTEIRO = {
  vigente: ['ativa', 'Vigente'],
  agendado: ['agendada', 'Agendado'],
  encerrado: ['inativa', 'Encerrado'],
}

export function SituacaoRoteiro({ situacao }) {
  const [classe, texto] = SITUACOES_ROTEIRO[situacao]
  return <span className={`situacao ${classe}`} title={situacao === 'agendado' ? 'Começa numa data futura' : undefined}>{texto}</span>
}

export function Situacao({ ativo, textoAtivo = 'Ativo', textoInativo = 'Inativo' }) {
  return <span className={`situacao ${ativo ? 'ativa' : 'inativa'}`}>{ativo ? textoAtivo : textoInativo}</span>
}

// Exportação para Excel (.xlsx) formatado, montado no back-end (app/exportar.py).
// O subtítulo (filtros em uso) é definido pela tela que está aberta.
let subtituloExportacao = ''
export function definirSubtituloExportacao(texto) {
  subtituloExportacao = texto || ''
}

const CAMPOS_EM_REAIS = /custo|faturamento|valor|total|salario|ajuda|vale|transporte|outros|comprou|preco|venda|considerado/

/** moeda, percentual, numero ou texto: pelo "formato" da coluna ou pelo nome do campo. */
function formatoDaColuna(coluna) {
  if (coluna.formato) return coluna.formato
  if (/percentual/.test(coluna.campo)) return 'percentual'
  if (/^\d{4}-\d{2}$/.test(coluna.campo) || CAMPOS_EM_REAIS.test(coluna.campo)) return 'moeda'
  return coluna.num ? 'numero' : 'texto'
}

const SIGLAS = /\b(pdv|uf|cnpj|erp|cod|cli)\b/gi
const tituloDoArquivo = (nome) => {
  const texto = nome.replace(/[-_]+/g, ' ').trim().replace(SIGLAS, (s) => s.toUpperCase())
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

/** Gera o .xlsx: linhas na ordem da tela, as linhas de total (rodapé) em negrito no fim e, se `destacar(linha)`
 * disser, linhas em destaque (ex.: as UFs do Resumo). */
export async function exportarExcel(nomeArquivo, colunas, linhas, totais = [], destacar = null) {
  const valores = (l) => colunas.map((c) => {
    const v = c.exportar ? c.exportar(l) : l[c.campo]
    return v === undefined ? null : v
  })
  try {
    const resposta = await fetch('/api/exportar', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        titulo: tituloDoArquivo(nomeArquivo),
        subtitulo: subtituloExportacao,
        colunas: colunas.map((c) => ({ titulo: c.titulo, formato: formatoDaColuna(c) })),
        linhas: linhas.map(valores),
        totais: totais.map(valores),
        destaques: destacar ? linhas.flatMap((l, i) => (destacar(l) ? [i] : [])) : [],
      }),
    })
    if (!resposta.ok) {
      const erro = await resposta.json().catch(() => ({}))
      throw new Error(typeof erro.detail === 'string' ? erro.detail : 'Não foi possível gerar o Excel.')
    }
    const link = document.createElement('a')
    link.href = URL.createObjectURL(await resposta.blob())
    link.download = `${nomeArquivo}.xlsx`
    link.click()
    setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  } catch (e) {
    window.alert(e.message)
  }
}

/**
 * colunas: [{ campo, titulo, num, mostrar(linha), ordenar(linha), exportar(linha) }]
 * Clicar no título ordena; a lista é paginada e pode ser exportada para Excel.
 */
export function Tabela({
  colunas, linhas, chave = 'id', aoClicar, vazio = 'Nada encontrado.', arquivo, porPagina = 50, rodape = [],
  classeLinha,
}) {
  const [ordem, setOrdem] = useState(null)
  const [pagina, setPagina] = useState(0)
  const imprimindo = useImprimindo()

  useEffect(() => setPagina(0), [linhas])

  const ordenadas = useMemo(() => {
    if (!ordem) return linhas
    const coluna = colunas.find((c) => c.campo === ordem.campo)
    const valor = (l) => (coluna.ordenar ? coluna.ordenar(l) : l[coluna.campo])
    return [...linhas].sort((a, b) => {
      const x = valor(a)
      const y = valor(b)
      const comparacao =
        typeof x === 'number' && typeof y === 'number'
          ? x - y
          : String(x ?? '').localeCompare(String(y ?? ''), 'pt-BR', { numeric: true })
      return ordem.crescente ? comparacao : -comparacao
    })
  }, [linhas, ordem, colunas])

  // Na impressão saem todas as linhas, não só a página atual.
  const tamanho = imprimindo ? Infinity : porPagina
  const paginas = Math.max(1, Math.ceil(ordenadas.length / porPagina))
  const visiveis = imprimindo ? ordenadas : ordenadas.slice(pagina * tamanho, (pagina + 1) * tamanho)

  function ordenarPor(campo) {
    setOrdem((atual) => (atual?.campo === campo ? { campo, crescente: !atual.crescente } : { campo, crescente: true }))
  }

  return (
    <>
      <div className="tabela-rolagem">
        <table>
          <thead>
            <tr>
              {colunas.map((c) => (
                <th
                  key={c.campo}
                  className={`${c.num ? 'num' : ''} ${c.semOrdem ? '' : 'ordenavel'}`}
                  onClick={c.semOrdem ? undefined : () => ordenarPor(c.campo)}
                >
                  {c.titulo}
                  {ordem?.campo === c.campo && (ordem.crescente ? ' ▲' : ' ▼')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visiveis.map((l) => (
              <tr key={l[chave]} className={`${aoClicar ? 'clicavel' : ''} ${classeLinha ? classeLinha(l) : ''}`}
                onClick={aoClicar ? () => aoClicar(l) : undefined}>
                {colunas.map((c) => (
                  <td key={c.campo} className={`${c.num ? 'num' : ''} ${c.quebra ? 'quebra' : ''}`}>
                    {c.mostrar ? c.mostrar(l) : l[c.campo]}
                  </td>
                ))}
              </tr>
            ))}
            {!visiveis.length && (
              <tr><td colSpan={colunas.length} className="vazio">{vazio}</td></tr>
            )}
          </tbody>
          {rodape.length > 0 && linhas.length > 0 && (
            <tfoot>
              {rodape.map((l, i) => (
                <tr key={i}>
                  {colunas.map((c) => (
                    <td key={c.campo} className={`${c.num ? 'num' : ''}`}>{c.mostrar && l[c.campo] !== undefined ? c.mostrar(l) : l[c.campo]}</td>
                  ))}
                </tr>
              ))}
            </tfoot>
          )}
        </table>
      </div>
      <div className="tabela-rodape nao-imprimir">
        <span className="dica">{linhas.length} registro(s)</span>
        {paginas > 1 && (
          <div className="paginacao">
            <button className="secundario" disabled={pagina === 0} onClick={() => setPagina(pagina - 1)}>‹ Anterior</button>
            <span>Página {pagina + 1} de {paginas}</span>
            <button className="secundario" disabled={pagina >= paginas - 1} onClick={() => setPagina(pagina + 1)}>Próxima ›</button>
          </div>
        )}
        {arquivo && (
          <button className="secundario" onClick={() => exportarExcel(arquivo, colunas.filter((c) => !c.semExportar), ordenadas, rodape)}>
            Exportar Excel
          </button>
        )}
      </div>
    </>
  )
}

/** true enquanto o navegador está imprimindo (para mostrar todas as linhas das tabelas). */
export function useImprimindo() {
  const [imprimindo, setImprimindo] = useState(false)
  useEffect(() => {
    const antes = () => setImprimindo(true)
    const depois = () => setImprimindo(false)
    window.addEventListener('beforeprint', antes)
    window.addEventListener('afterprint', depois)
    return () => {
      window.removeEventListener('beforeprint', antes)
      window.removeEventListener('afterprint', depois)
    }
  }, [])
  return imprimindo
}

/** Lista de escolha com busca (para listas longas, como os PDVs). */
export function EscolhaComBusca({ opcoes, valor, aoMudar, placeholder = 'Digite para buscar…' }) {
  const [busca, setBusca] = useState('')
  const escolhida = opcoes.find((o) => o.valor === valor)
  const termo = busca.trim().toLowerCase()
  const filtradas = termo ? opcoes.filter((o) => o.texto.toLowerCase().includes(termo)).slice(0, 50) : []

  if (escolhida) {
    return (
      <div className="escolha-feita">
        <span>{escolhida.texto}</span>
        <button type="button" className="secundario" onClick={() => aoMudar(null)}>Trocar</button>
      </div>
    )
  }
  return (
    <div className="escolha-busca">
      <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder={placeholder} autoFocus />
      {filtradas.length > 0 && (
        <ul>
          {filtradas.map((o) => (
            <li key={o.valor}>
              <button type="button" onClick={() => { aoMudar(o.valor); setBusca('') }}>{o.texto}</button>
            </li>
          ))}
        </ul>
      )}
      {termo && !filtradas.length && <small className="dica">Nada encontrado.</small>}
    </div>
  )
}

/** Carrega uma lista da API e devolve [dados, recarregar, erro]. */
export function useLista(carregar) {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [versao, setVersao] = useState(0)
  useEffect(() => {
    let cancelado = false
    carregar()
      .then((d) => !cancelado && setDados(d))
      .catch((e) => !cancelado && setErro(e.message))
    return () => {
      cancelado = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versao])
  return [dados, () => setVersao((v) => v + 1), erro]
}
