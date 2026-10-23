import { useState } from 'react'
import { formatarCnpj, formatarMoeda } from '../formato.js'

export default function TabelaLojas({ lojas }) {
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
      <p className="dica">Ordenado do menor faturamento para o maior.</p>
      <div className="tabela-rolagem">
        <table>
          <thead>
            <tr>
              <th>Loja</th>
              <th>CNPJ</th>
              <th>Cidade</th>
              <th>Promotor</th>
              <th className="num">Visitas/sem.</th>
              <th className="num">Meses c/ compra</th>
              <th className="num">Notas</th>
              <th className="num">Faturamento</th>
            </tr>
          </thead>
          <tbody>
            {visiveis.map((l) => (
              <tr key={`${l.codigo_promotor}-${l.cnpj}-${l.loja}`} className={l.faturamento <= 0 ? 'linha-sem-compra' : ''}>
                <td>
                  {l.loja}
                  {l.lojas_mesmo_cnpj > 1 && (
                    <span className="etiqueta" title="Valor do CNPJ inteiro, compartilhado com outras lojas da rede">
                      CNPJ da rede ({l.lojas_mesmo_cnpj} lojas)
                    </span>
                  )}
                </td>
                <td>{formatarCnpj(l.cnpj)}</td>
                <td>{l.cidade}{l.uf && ` - ${l.uf}`}</td>
                <td>{l.promotor}</td>
                <td className="num">{l.visitas_semana ?? '—'}</td>
                <td className="num">{l.meses_com_compra}</td>
                <td className="num">{l.notas}</td>
                <td className="num">{formatarMoeda(l.faturamento)}</td>
              </tr>
            ))}
            {!visiveis.length && (
              <tr><td colSpan={8} className="vazio">Nenhuma loja com esses filtros.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
