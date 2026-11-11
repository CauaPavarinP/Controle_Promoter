// Aba Lojas por UF: as lojas dos arquivos das agências, com quem atende, quanto custa, quanto compraram e o
// faturamento mês a mês (clicável para ver as notas).
import { formatarCnpj } from '../formato.js'
import GradeMensal from './GradeMensal.jsx'
import { COLUNAS_SE_PAGA } from './SePaga.jsx'
import { Tabela } from './ui.jsx'

export default function LojasUf({ uf, aoMudarUf, ufs, lojas, grade }) {
  return (
    <>
      <nav className="abas-uf nao-imprimir">
        <button className={!uf ? 'ativo' : ''} onClick={() => aoMudarUf('')}>Todas</button>
        {ufs.map((u) => (
          <button key={u} className={uf === u ? 'ativo' : ''} onClick={() => aoMudarUf(u)}>{u}</button>
        ))}
      </nav>
      {lojas && (
        <section className="bloco">
          <h2>Lojas atendidas ({lojas.length})</h2>
          <p className="dica">Das lojas que as agências informaram no período, com o custo do atendimento e quanto compraram da 101.</p>
          <Tabela
            chave="chave"
            linhas={lojas}
            porPagina={50}
            arquivo="lojas"
            vazio="Nenhuma loja com esses filtros."
            colunas={[
              { campo: 'loja', titulo: 'Loja', quebra: true,
                mostrar: (l) => <>{l.loja}{l.compartilhado && <span className="etiqueta" title="O CNPJ é de mais de uma loja: o faturamento foi dividido entre elas">CNPJ compartilhado</span>}</> },
              { campo: 'cnpj', titulo: 'CNPJ', mostrar: (l) => (l.cnpj ? formatarCnpj(l.cnpj) : <span className="texto-alerta">sem CNPJ</span>),
                exportar: (l) => (l.cnpj ? formatarCnpj(l.cnpj) : '') },
              { campo: 'cidade', titulo: 'Cidade', quebra: true, mostrar: (l) => `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}`,
                exportar: (l) => `${l.cidade}${l.uf ? ` - ${l.uf}` : ''}` },
              { campo: 'agencia', titulo: 'Agência', quebra: true },
              { campo: 'promotor', titulo: 'Promotor', quebra: true },
              { campo: 'dias', titulo: 'Dias', quebra: true },
              { campo: 'visitas', titulo: 'Visitas', num: true, formato: 'inteiro' },
              ...COLUNAS_SE_PAGA,
            ]}
          />
        </section>
      )}
      {grade && <GradeMensal grade={grade} />}
    </>
  )
}
