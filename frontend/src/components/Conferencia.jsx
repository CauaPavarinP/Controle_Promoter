// Conferência dos totais do sistema com as abas por UF da planilha (documento, seção 6.1, item 5).
import { http } from '../api.js'
import { formatarCnpj, formatarMoeda, NOMES_MESES_LONGOS } from '../formato.js'
import { Tabela, useLista } from './ui.jsx'

const NOMES_VALOR = { total_venda: 'TOTAL VENDA', vlr_total: 'VLR TOTAL' }

function classeDiferenca(valor) {
  return Math.abs(valor) < 0.01 ? 'pct-ok' : 'pct-critico'
}

export default function Conferencia() {
  const [dados, , erro] = useLista(() => http.get('/api/conferencia'))
  if (!dados) return erro ? <div className="erro-caixa">{erro}</div> : <p>Carregando…</p>
  if (!dados.disponivel) {
    return (
      <div className="aviso">
        A conferência aparece depois da <b>importação inicial da planilha completa</b> (em Atualizar dados), com o
        faturamento gravado.
      </div>
    )
  }

  return (
    <>
      <section className="bloco">
        <p className="dica">
          Compara, para {dados.ano}, o total de cada aba da planilha (a soma das linhas, como a linha de totais) com a mesma
          conta feita pelo sistema: o faturamento ({NOMES_VALOR[dados.regras.valor_faturamento]}
          {dados.regras.somente_receita ? ', só RECEITA = SIM' : ''}, conforme Regras do cálculo) do CNPJ de cada linha, mês a
          mês. <b>Diferença zero</b> = o sistema reproduz a planilha.
        </p>
        <p className="dica">
          A última coluna conta cada CNPJ <b>uma vez só</b>, que é como o painel soma. A diferença entre "Planilha" e essa
          coluna é o valor que a planilha soma em dobro quando lojas diferentes têm o mesmo CNPJ.
        </p>
      </section>

      {dados.abas.map((aba) => (
        <section className="bloco" key={aba.aba}>
          <h2>Aba {aba.aba}</h2>
          <Tabela
            chave="mes"
            linhas={[...aba.meses, { mes: 'total', ...aba.total }]}
            porPagina={13}
            arquivo={`conferencia-${aba.aba}`}
            colunas={[
              { campo: 'mes', titulo: 'Mês', semOrdem: true,
                mostrar: (l) => (l.mes === 'total' ? <b>Total</b> : NOMES_MESES_LONGOS[l.mes - 1]),
                exportar: (l) => (l.mes === 'total' ? 'Total' : NOMES_MESES_LONGOS[l.mes - 1]) },
              { campo: 'planilha', titulo: 'Planilha', num: true, semOrdem: true, mostrar: (l) => formatarMoeda(l.planilha) },
              { campo: 'sistema', titulo: 'Sistema (mesma conta)', num: true, semOrdem: true, mostrar: (l) => formatarMoeda(l.sistema) },
              { campo: 'diferenca', titulo: 'Diferença', num: true, semOrdem: true,
                mostrar: (l) => <span className={classeDiferenca(l.diferenca)}>{formatarMoeda(l.diferenca)}</span> },
              { campo: 'sem_repetir_cnpj', titulo: 'Sistema sem repetir CNPJ', num: true, semOrdem: true,
                mostrar: (l) => formatarMoeda(l.sem_repetir_cnpj) },
            ]}
          />
        </section>
      ))}

      <section className="bloco">
        <h2>Linhas com as maiores diferenças</h2>
        <p className="dica">
          Ajuda a achar o motivo: tipo de nota que a planilha soma e o sistema não (ou o contrário), coluna de valor
          diferente, faturamento importado de outro período…
        </p>
        <Tabela
          chave="chave"
          linhas={dados.maiores_diferencas.map((d, i) => ({ ...d, chave: i }))}
          porPagina={30}
          arquivo="conferencia-diferencas"
          vazio="Nenhuma diferença."
          colunas={[
            { campo: 'aba', titulo: 'Aba' },
            { campo: 'loja', titulo: 'Loja', quebra: true },
            { campo: 'cnpj', titulo: 'CNPJ', mostrar: (d) => formatarCnpj(d.cnpj), exportar: (d) => formatarCnpj(d.cnpj) },
            { campo: 'mes', titulo: 'Mês', mostrar: (d) => NOMES_MESES_LONGOS[d.mes - 1] },
            { campo: 'planilha', titulo: 'Planilha', num: true, mostrar: (d) => formatarMoeda(d.planilha) },
            { campo: 'sistema', titulo: 'Sistema', num: true, mostrar: (d) => formatarMoeda(d.sistema) },
            { campo: 'diferenca', titulo: 'Diferença', num: true, mostrar: (d) => <span className="pct-critico">{formatarMoeda(d.diferenca)}</span> },
          ]}
        />
      </section>
    </>
  )
}
