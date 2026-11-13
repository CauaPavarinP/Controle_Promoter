// Aba Lojas por UF: as lojas dos arquivos das agências, com quem atende, quanto custa, quanto compraram e o
// faturamento mês a mês (clicável para ver as notas).
import { formatarCnpj } from '../formato.js'
import GradeMensal from './GradeMensal.jsx'
import { COLUNA_VISITAS, COLUNAS_SE_PAGA, OpcaoOcultarSemCusto, useOcultarSemCusto } from './SePaga.jsx'
import { Tabela } from './ui.jsx'

export default function LojasUf({ uf, aoMudarUf, ufs, lojas: todas, grade, avisos = [], agencias }) {
  const ocultacao = useOcultarSemCusto(agencias)
  const lojas = todas && todas.filter((l) => ocultacao.visivel(l.agencia_chaves || []))
  return (
    <>
      <nav className="abas-uf nao-imprimir">
        <button className={!uf ? 'ativo' : ''} onClick={() => aoMudarUf('')} aria-pressed={!uf}>Todas</button>
        {ufs.map((u) => (
          <button key={u} className={uf === u ? 'ativo' : ''} onClick={() => aoMudarUf(u)} aria-pressed={uf === u}
            aria-label={`Lojas de ${u}`}>{u}</button>
        ))}
      </nav>
      {avisos.map((aviso) => <p key={aviso} className="nota">⚠ {aviso}</p>)}
      {lojas && (
        <section className="bloco">
          <div className="bloco-cabecalho">
            <h2>Lojas atendidas ({lojas.length})</h2>
            <div className="bloco-ferramentas"><OpcaoOcultarSemCusto {...ocultacao} /></div>
          </div>
          <p className="dica">Das lojas que as agências informaram no período, com o custo do atendimento e quanto compraram da 101.</p>
          <Tabela
            chave="chave"
            linhas={lojas}
            porPagina={50}
            arquivo="lojas"
            vazio="Nenhuma loja com esses filtros."
            colunas={[
              { campo: 'loja', titulo: 'Loja', quebra: true,
                mostrar: (l) => <>{l.loja}{l.compartilhado && <span className="etiqueta" title="O CNPJ é de mais de uma loja: o faturamento foi dividido entre elas">CNPJ compartilhado</span>}
                  {l.inicio && <span className="etiqueta" title="Observação do arquivo: o atendimento começou no meio do mês. O custo e o faturamento do mês não foram cortados.">início {l.inicio}</span>}</> },
              { campo: 'cnpj', titulo: 'CNPJ', mostrar: (l) => {
                if (l.cnpj) return formatarCnpj(l.cnpj)
                if (l.cnpj_arquivo) {
                  return <span className="texto-alerta" title="O dígito verificador não confere (erro no arquivo da agência): a loja fica sem faturamento até a agência corrigir.">CNPJ inválido no arquivo: {l.cnpj_arquivo}</span>
                }
                return <span className="texto-alerta">sem CNPJ</span>
              },
                exportar: (l) => (l.cnpj ? formatarCnpj(l.cnpj) : l.cnpj_arquivo ? `inválido: ${l.cnpj_arquivo}` : '') },
              { campo: 'cidade', titulo: 'Cidade', quebra: true, mostrar: (l) => `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}`,
                exportar: (l) => `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}` },
              { campo: 'agencia', titulo: 'Agência', quebra: true },
              { campo: 'promotor', titulo: 'Promotor', quebra: true },
              { campo: 'dias', titulo: 'Dias', quebra: true },
              COLUNA_VISITAS,
              ...COLUNAS_SE_PAGA,
            ]}
          />
        </section>
      )}
      {grade && <GradeMensal grade={grade} />}
    </>
  )
}
