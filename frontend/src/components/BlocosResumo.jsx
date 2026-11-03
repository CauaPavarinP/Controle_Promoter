// Os 3 blocos da aba RESUMO da planilha: monitoramento, custo e faturamento dos PDVs,
// por UF (linha em negrito) e pelos supervisores de cada UF.
import { classePercentual, formatarMoeda, formatarPercentual } from '../formato.js'
import { Tabela } from './ui.jsx'

const negrito = (l, texto) => (l.nivel === 'uf' ? <b>{texto}</b> : texto)

function colunasBase() {
  return [
    { campo: 'uf', titulo: 'UF', semOrdem: true, mostrar: (l) => negrito(l, l.nivel === 'uf' ? l.uf : ''), exportar: (l) => l.uf },
    { campo: 'supervisor', titulo: 'Supervisor', semOrdem: true,
      mostrar: (l) => (l.nivel === 'uf' ? <b>Total {l.uf}</b> : l.supervisor),
      exportar: (l) => (l.nivel === 'uf' ? `Total ${l.uf}` : l.supervisor) },
  ]
}

export default function BlocosResumo({ linhas, resumo, regras, mesFinal }) {
  const somarMensal = (campo) => linhas.filter((l) => l.nivel === 'uf').reduce((s, l) => s + l.custo_mensal[campo], 0)
  const chave = (l) => `${l.uf}-${l.nivel}-${l.supervisor}`
  const comChave = linhas.map((l) => ({ ...l, chave: chave(l) }))
  const classeLinha = (l) => (l.nivel === 'uf' ? 'linha-subtotal' : '')
  const rodapeTitulo = { uf: '', supervisor: 'Total geral' }

  return (
    <>
      <section className="bloco">
        <h2>Monitoramento — promotores / repositores</h2>
        <Tabela
          chave="chave" linhas={comChave} porPagina={200} arquivo="resumo-monitoramento" classeLinha={classeLinha}
          vazio="Nenhum promotor com esses filtros."
          rodape={[{ ...rodapeTitulo, promotores: resumo.promotores, lojas: resumo.lojas, visitas_semana: resumo.visitas_semana }]}
          colunas={[
            ...colunasBase(),
            { campo: 'promotores', titulo: 'Promotores', num: true, semOrdem: true, mostrar: (l) => negrito(l, l.promotores) },
            { campo: 'lojas', titulo: 'Lojas atendidas', num: true, semOrdem: true, mostrar: (l) => negrito(l, l.lojas) },
            { campo: 'visitas_semana', titulo: 'Visitas por semana', num: true, semOrdem: true, mostrar: (l) => negrito(l, l.visitas_semana ?? '—') },
          ]}
        />
      </section>

      <section className="bloco">
        <h2>Custo — promotores / repositores</h2>
        <p className="dica">Custo mensal vigente em {mesFinal}; a última coluna é o custo somado no período escolhido.</p>
        <Tabela
          chave="chave" linhas={comChave} porPagina={200} arquivo="resumo-custo" classeLinha={classeLinha}
          vazio="Nenhum promotor com esses filtros."
          rodape={[{
            ...rodapeTitulo, salario: somarMensal('salario'), ajuda_custo: somarMensal('ajuda_custo'),
            vale_transporte: somarMensal('vale_transporte'), total_mensal: somarMensal('total'), custo_periodo: resumo.custo,
          }]}
          colunas={[
            ...colunasBase(),
            { campo: 'salario', titulo: 'Salário', num: true, semOrdem: true,
              mostrar: (l) => negrito(l, formatarMoeda(l.custo_mensal ? l.custo_mensal.salario : l.salario)),
              exportar: (l) => (l.custo_mensal ? l.custo_mensal.salario : l.salario) },
            { campo: 'ajuda_custo', titulo: 'Ajuda de custo', num: true, semOrdem: true,
              mostrar: (l) => negrito(l, formatarMoeda(l.custo_mensal ? l.custo_mensal.ajuda_custo : l.ajuda_custo)),
              exportar: (l) => (l.custo_mensal ? l.custo_mensal.ajuda_custo : l.ajuda_custo) },
            { campo: 'vale_transporte', titulo: 'Vale-transporte', num: true, semOrdem: true,
              mostrar: (l) => negrito(l, formatarMoeda(l.custo_mensal ? l.custo_mensal.vale_transporte : l.vale_transporte)),
              exportar: (l) => (l.custo_mensal ? l.custo_mensal.vale_transporte : l.vale_transporte) },
            { campo: 'total_mensal', titulo: 'Total por mês', num: true, semOrdem: true,
              mostrar: (l) => negrito(l, formatarMoeda(l.custo_mensal ? l.custo_mensal.total : l.total_mensal)),
              exportar: (l) => (l.custo_mensal ? l.custo_mensal.total : l.total_mensal) },
            { campo: 'custo_periodo', titulo: 'Custo no período', num: true, semOrdem: true,
              mostrar: (l) => negrito(l, formatarMoeda(l.custo_periodo)) },
          ]}
        />
      </section>

      <section className="bloco">
        <h2>Faturamento ponto de venda — PDV</h2>
        <p className="dica">
          Faturamento das lojas atendidas, vindo do ERP. Loja que divide o CNPJ com outra conta uma vez só em cada total.
        </p>
        <Tabela
          chave="chave" linhas={comChave} porPagina={200} arquivo="resumo-faturamento" classeLinha={classeLinha}
          vazio="Nenhum promotor com esses filtros."
          rodape={[{ ...rodapeTitulo, faturamento: resumo.faturamento, custo_periodo: resumo.custo, percentual_custo: resumo.percentual_custo }]}
          colunas={[
            ...colunasBase(),
            { campo: 'faturamento', titulo: 'Faturamento', num: true, semOrdem: true, mostrar: (l) => negrito(l, formatarMoeda(l.faturamento)) },
            { campo: 'custo_periodo', titulo: 'Custo dos promotores', num: true, semOrdem: true, mostrar: (l) => negrito(l, formatarMoeda(l.custo_periodo)) },
            { campo: 'percentual_custo', titulo: 'Custo ÷ faturamento', num: true, semOrdem: true,
              mostrar: (l) => <span className={classePercentual(l.percentual_custo, regras)}>{negrito(l, formatarPercentual(l.percentual_custo))}</span> },
          ]}
        />
      </section>
    </>
  )
}
