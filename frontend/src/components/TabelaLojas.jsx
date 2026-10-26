import { useState } from 'react'
import { classePercentual, formatarCnpj, formatarMoeda, formatarPercentual } from '../formato.js'

const TEXTO_MODO_REDE = {
  cnpj: 'Faturamento pelo CNPJ da própria loja.',
  rede_total: 'Lojas de rede mostram o faturamento da rede inteira (mesma raiz de CNPJ).',
  rede_dividido: 'O faturamento da rede está dividido igualmente entre as lojas dela.',
}

export default function TabelaLojas({ lojas, regras }) {
  const [busca, setBusca] = useState('')
  const [soSemCompra, setSoSemCompra] = useState(false)

  const termo = busca.trim().toLowerCase()
  const visiveis = lojas.filter(
    (l) =>
      (!soSemCompra || l.faturamento <= 0) &&
      (!termo || `${l.loja} ${l.cidade} ${l.promotor}`.toLowerCase().includes(termo)),
  )

  return (
    <section className="bloco">
      <div className="bloco-cabecalho">
        <h2>Lojas ({visiveis.length})</h2>
        <div className="bloco-ferramentas">
          <input placeholder="Buscar loja, cidade ou promotor" value={busca} onChange={(e) => setBusca(e.target.value)} />
          <label className="marcar">
            <input type="checkbox" checked={soSemCompra} onChange={(e) => setSoSemCompra(e.target.checked)} />
            Só lojas sem compra
          </label>
        </div>
      </div>
      <div className="legenda">
        <span><i className="cor-sem-compra" /> Sem compra no período</span>
        <span><i className="cor-ok" /> Custo abaixo de {regras.faixa_alerta}%</span>
        <span><i className="cor-alerta" /> De {regras.faixa_alerta}% a {regras.faixa_critico}%</span>
        <span><i className="cor-critico" /> Acima de {regras.faixa_critico}%</span>
      </div>
      <p className="dica">
        {TEXTO_MODO_REDE[regras.modo_rede]} Custo da loja = parte do custo do promotor
        ({regras.rateio_custo === 'visitas' ? 'proporcional às visitas' : 'dividido igual entre as lojas dele'}).
        Ordenado do menor faturamento para o maior. As regras ficam em "Regras do cálculo".
      </p>
      <div className="tabela-rolagem">
        <table>
          <thead>
            <tr>
              <th>Loja</th>
              <th>CNPJ</th>
              <th>Cidade</th>
              <th>Promotor</th>
              <th className="num">Visitas/<br />semana</th>
              <th className="num">Meses c/<br />compra</th>
              <th className="num">Faturamento</th>
              <th className="num">Custo da loja</th>
              <th className="num">% custo</th>
              <th className="num">Custo/visita</th>
            </tr>
          </thead>
          <tbody>
            {visiveis.map((l) => (
              <tr key={`${l.codigo_promotor}-${l.cnpj}-${l.loja}`} className={l.faturamento <= 0 ? 'linha-sem-compra' : ''}>
                <td className="quebra">
                  {l.loja}
                  {l.compartilhado && (
                    <span className="etiqueta" title="Valor do CNPJ/rede inteiro, compartilhado com outras lojas">
                      valor da rede ({l.lojas_mesmo_cnpj} lojas)
                    </span>
                  )}
                </td>
                <td>{formatarCnpj(l.cnpj)}</td>
                <td className="quebra">{l.cidade}{l.uf && ` - ${l.uf}`}</td>
                <td className="quebra">{l.promotor}</td>
                <td className="num">{l.visitas_semana ?? '—'}</td>
                <td className="num">{l.meses_com_compra}</td>
                <td className="num">{formatarMoeda(l.faturamento)}</td>
                <td className="num">{formatarMoeda(l.custo_periodo)}</td>
                <td
                  className={`num ${classePercentual(l.percentual_custo, regras)}`}
                  title={l.compartilhado ? 'Não calculado: o faturamento mostrado é da rede inteira' : undefined}
                >
                  {formatarPercentual(l.percentual_custo)}
                </td>
                <td className="num">{formatarMoeda(l.custo_por_visita)}</td>
              </tr>
            ))}
            {!visiveis.length && (
              <tr><td colSpan={10} className="vazio">Nenhuma loja com esses filtros.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
