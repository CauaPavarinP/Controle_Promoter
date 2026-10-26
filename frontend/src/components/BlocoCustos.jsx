import { formatarMoeda } from '../formato.js'
import { Tabela } from './ui.jsx'

// Custo dos promotores filtrados, como a aba PROMOTORES BRASIL (valores vigentes no último mês do período).
export default function BlocoCustos({ custos, fim }) {
  const somar = (campo) => custos.reduce((s, c) => s + (c[campo] || 0), 0)
  const dinheiro = (campo) => (c) => formatarMoeda(c[campo])
  return (
    <section className="bloco">
      <h2>Custo dos promotores (mensal)</h2>
      <p className="dica">Valores vigentes em {fim}, sem encargos e custo extra das Regras do cálculo. Igual à aba PROMOTORES BRASIL com filtro.</p>
      <Tabela
        chave="codigo"
        linhas={custos}
        arquivo="custo-promotores"
        vazio="Nenhum promotor com esses filtros."
        rodape={[{ nome: `Total (${custos.length})`, salario: somar('salario'), ajuda_custo: somar('ajuda_custo'),
          vale_transporte: somar('vale_transporte'), outros: somar('outros'), total: somar('total') }]}
        colunas={[
          { campo: 'codigo', titulo: 'Código' },
          { campo: 'nome', titulo: 'Promotor', quebra: true },
          { campo: 'supervisor', titulo: 'Supervisor' },
          { campo: 'municipio', titulo: 'Município' },
          { campo: 'salario', titulo: 'Salário', num: true, mostrar: dinheiro('salario') },
          { campo: 'ajuda_custo', titulo: 'Ajuda de custo', num: true, mostrar: dinheiro('ajuda_custo') },
          { campo: 'vale_transporte', titulo: 'Vale-transp.', num: true, mostrar: dinheiro('vale_transporte') },
          { campo: 'outros', titulo: 'Outros', num: true, mostrar: dinheiro('outros') },
          { campo: 'total', titulo: 'Total', num: true, mostrar: (c) => <b>{formatarMoeda(c.total)}</b> },
        ]}
      />
    </section>
  )
}
