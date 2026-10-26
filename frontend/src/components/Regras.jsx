import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { formatarMoeda } from '../formato.js'

const ACOES = [
  { valor: 'soma', texto: 'Soma no faturamento' },
  { valor: 'subtrai', texto: 'Desconta do faturamento' },
  { valor: 'ignora', texto: 'Fica de fora' },
]

const MODOS_RATEIO = [
  {
    valor: 'visitas',
    titulo: 'Proporcional às visitas por semana',
    exemplo:
      'O promotor custa R$ 4.500 e faz 20 visitas por semana; uma loja com 5 visitas recebe 5/20 × 4.500 = R$ 1.125. ' +
      'Se faltar a frequência de alguma loja do promotor, divide em partes iguais.',
  },
  {
    valor: 'igual',
    titulo: 'Em partes iguais por loja',
    exemplo: 'Promotor de R$ 4.500 com 15 lojas: cada loja recebe R$ 300.',
  },
]

function Opcoes({ nome, opcoes, valor, aoMudar }) {
  return (
    <div className="opcoes">
      {opcoes.map((o) => (
        <label key={o.valor} className={`opcao ${valor === o.valor ? 'escolhida' : ''}`}>
          <input type="radio" name={nome} checked={valor === o.valor} onChange={() => aoMudar(o.valor)} />
          <div>
            <strong>{o.titulo}</strong>
            <p>{o.exemplo}</p>
          </div>
        </label>
      ))}
    </div>
  )
}

function Numero({ rotulo, valor, aoMudar, sufixo, passo = 1 }) {
  return (
    <label className="filtro">
      {rotulo}
      <div className="campo-numero">
        <input type="number" min="0" step={passo} value={valor} onChange={(e) => aoMudar(e.target.value)} />
        {sufixo && <span>{sufixo}</span>}
      </div>
    </label>
  )
}

export default function Regras({ aoSalvar, podeEditar = true }) {
  const [regras, setRegras] = useState(null)
  const [tipos, setTipos] = useState([])
  const [alterado, setAlterado] = useState(false)
  const [salvando, setSalvando] = useState(false)
  const [mensagem, setMensagem] = useState(null)

  useEffect(() => {
    api.regras()
      .then((dados) => {
        setRegras(dados.regras)
        setTipos(dados.tipos_nf)
      })
      .catch((e) => setMensagem({ erro: true, texto: e.message }))
  }, [])

  function alterar(campo, valor) {
    setRegras((atual) => ({ ...atual, [campo]: valor }))
    setAlterado(true)
    setMensagem(null)
  }

  function alterarTipo(chave, acao) {
    alterar('tipos_nf', { ...regras.tipos_nf, [chave]: acao })
  }

  async function salvar() {
    setSalvando(true)
    try {
      const dados = await api.salvarRegras(regras)
      setRegras(dados.regras)
      setTipos(dados.tipos_nf)
      setAlterado(false)
      setMensagem({ erro: false, texto: 'Regras salvas. O painel já usa os valores novos.' })
      aoSalvar()
    } catch (e) {
      setMensagem({ erro: true, texto: e.message })
    } finally {
      setSalvando(false)
    }
  }

  if (!regras) return mensagem ? <div className="erro-caixa">{mensagem.texto}</div> : <p>Carregando…</p>

  return (
    <div className="regras">
      <section className="bloco">
        <h2>1. O que conta como faturamento</h2>
        <p className="dica">
          O padrão é igual à planilha: soma a coluna <b>TOTAL VENDA</b> de todas as linhas, sem filtrar tipo de nota nem
          RECEITA. Assim os totais batem com as abas da planilha (veja em Conferência). Mude aqui se o Maurício decidir
          tirar devoluções, bonificações ou linhas que não geram receita.
        </p>
        <div className="campos-linha">
          <label className="filtro">
            Coluna de valor
            <select value={regras.valor_faturamento} onChange={(e) => alterar('valor_faturamento', e.target.value)}>
              <option value="total_venda">TOTAL VENDA (coluna AL, a que a planilha soma)</option>
              <option value="vlr_total">VLR TOTAL (coluna AD, valor da nota no ERP)</option>
            </select>
          </label>
          <label className="filtro">
            Tipos de nota que não estão na lista abaixo
            <select value={regras.tipos_nf_padrao} onChange={(e) => alterar('tipos_nf_padrao', e.target.value)}>
              {ACOES.map((a) => <option key={a.valor} value={a.valor}>{a.texto}</option>)}
            </select>
          </label>
        </div>
        <label className="marcar">
          <input type="checkbox" checked={regras.somente_receita} onChange={(e) => alterar('somente_receita', e.target.checked)} />
          Contar só as linhas com RECEITA = SIM
        </label>
        <p className="dica">
          Tipos de nota: <b>Venda</b> é faturamento. <b>Devolução</b> é dinheiro que volta (costuma ser descontada).
          <b> Bonificação</b> é produto dado sem cobrança. <b>Remessa</b> é envio por outro motivo.
        </p>
        {tipos.length ? (
          <div className="tabela-rolagem">
            <table>
              <thead>
                <tr>
                  <th>Tipo de nota</th>
                  <th className="num">Notas</th>
                  <th className="num">Valor total</th>
                  <th>O que fazer</th>
                </tr>
              </thead>
              <tbody>
                {tipos.map((t) => (
                  <tr key={t.chave}>
                    <td>{t.tipo}</td>
                    <td className="num">{t.notas}</td>
                    <td className="num">{formatarMoeda(t.valor)}</td>
                    <td>
                      <select
                        value={regras.tipos_nf[t.chave] || regras.tipos_nf_padrao}
                        onChange={(e) => alterarTipo(t.chave, e.target.value)}
                      >
                        {ACOES.map((a) => <option key={a.valor} value={a.valor}>{a.texto}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="dica">Importe o faturamento para ver os tipos de nota.</p>
        )}
      </section>

      <section className="bloco">
        <h2>2. Custo do promotor atribuído a cada loja</h2>
        <p className="dica">
          Serve para comparar o custo de cada loja com o que ela compra (aba Lojas).
        </p>
        <Opcoes
          nome="rateio_custo"
          opcoes={MODOS_RATEIO}
          valor={regras.rateio_custo}
          aoMudar={(v) => alterar('rateio_custo', v)}
        />
      </section>

      <section className="bloco">
        <h2>3. Limite de custo sobre faturamento</h2>
        <p className="dica">
          A loja fica destacada em vermelho quando o custo do promotor passa desse % do faturamento dela. Exemplo:
          promotor custando R$ 1.000 numa loja que compra R$ 4.000 = 25%. Deixe vazio enquanto o limite não for definido.
        </p>
        <div className="campos-linha">
          <Numero
            rotulo="Destacar a partir de"
            valor={regras.limite_percentual ?? ''}
            sufixo="%"
            aoMudar={(v) => alterar('limite_percentual', v === '' ? null : v)}
          />
        </div>
      </section>

      {podeEditar ? (
        <div className="barra-salvar">
          {mensagem && <span className={mensagem.erro ? 'erro' : 'texto-ok'}>{mensagem.texto}</span>}
          {alterado && !mensagem && <span className="dica">Há alterações não salvas.</span>}
          <button onClick={salvar} disabled={!alterado || salvando}>
            {salvando ? 'Salvando…' : 'Salvar regras'}
          </button>
        </div>
      ) : (
        <p className="dica">Só administradores podem alterar as regras.</p>
      )}
    </div>
  )
}
