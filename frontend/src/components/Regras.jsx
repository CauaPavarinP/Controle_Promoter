import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { formatarMoeda } from '../formato.js'

const ACOES = [
  { valor: 'soma', texto: 'Soma no faturamento' },
  { valor: 'subtrai', texto: 'Desconta do faturamento' },
  { valor: 'ignora', texto: 'Fica de fora' },
]

const MODOS_REDE = [
  {
    valor: 'cnpj',
    titulo: 'Só o CNPJ da própria loja',
    exemplo: 'A loja só mostra as compras feitas no CNPJ dela. Se a matriz comprou, a loja aparece com R$ 0,00.',
  },
  {
    valor: 'rede_total',
    titulo: 'Rede inteira em cada loja',
    exemplo:
      'Junta todos os CNPJs da mesma empresa (mesma raiz, os 8 primeiros números). Se a rede comprou R$ 100.000, ' +
      'cada loja mostra R$ 100.000, e o total conta esse valor uma vez só.',
  },
  {
    valor: 'rede_dividido',
    titulo: 'Rede dividida igualmente entre as lojas',
    exemplo:
      'Junta os CNPJs da mesma empresa e divide pelo número de lojas no roteiro. Rede com 4 lojas que comprou ' +
      'R$ 100.000: cada loja fica com R$ 25.000.',
  },
]

const MODOS_RATEIO = [
  {
    valor: 'igual',
    titulo: 'Igual entre as lojas',
    exemplo: 'Promotor de R$ 3.000 com 3 lojas: cada loja custa R$ 1.000.',
  },
  {
    valor: 'visitas',
    titulo: 'Proporcional às visitas por semana',
    exemplo:
      'Promotor de R$ 3.000 que vai 4x numa loja e 2x em outra: a primeira custa R$ 2.000 e a segunda R$ 1.000. ' +
      'Só funciona se o roteiro tiver as visitas de todas as lojas do promotor; se faltar, divide igual.',
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
        <h2>2. Lojas de rede que compram pela matriz</h2>
        <p className="dica">
          Em redes como Condor ou Giassi, muitas vezes a nota sai no CNPJ da matriz, e não no da loja. Escolha como o
          sistema deve ligar essas compras às lojas.
        </p>
        <Opcoes nome="modo_rede" opcoes={MODOS_REDE} valor={regras.modo_rede} aoMudar={(v) => alterar('modo_rede', v)} />
      </section>

      <section className="bloco">
        <h2>3. Custo do promotor</h2>
        <p className="dica">
          O custo mensal vem da planilha de promotores (salário + ajuda de custo + transporte). Aqui você pode somar o que
          não está nela. Exemplo: salário de R$ 2.000 com 70% de encargos acrescenta R$ 1.400 por mês.
        </p>
        <div className="campos-linha">
          <Numero
            rotulo="Encargos sobre o salário (INSS, FGTS, férias…)"
            valor={regras.encargos_percentual}
            sufixo="%"
            aoMudar={(v) => alterar('encargos_percentual', v)}
          />
          <Numero
            rotulo="Custo extra por promotor, por mês (celular, combustível…)"
            valor={regras.custo_extra_mensal}
            sufixo="R$"
            passo={10}
            aoMudar={(v) => alterar('custo_extra_mensal', v)}
          />
        </div>
      </section>

      <section className="bloco">
        <h2>4. Como dividir o custo do promotor entre as lojas dele</h2>
        <p className="dica">
          Serve para ver quanto cada loja custa e comparar com o que ela compra (aba Lojas).
        </p>
        <Opcoes
          nome="rateio_custo"
          opcoes={MODOS_RATEIO}
          valor={regras.rateio_custo}
          aoMudar={(v) => alterar('rateio_custo', v)}
        />
        <div className="campos-linha">
          <Numero
            rotulo="Semanas por mês (para o custo por visita)"
            valor={regras.semanas_por_mes}
            passo={0.01}
            aoMudar={(v) => alterar('semanas_por_mes', v)}
          />
        </div>
      </section>

      <section className="bloco">
        <h2>5. Quando o custo está alto</h2>
        <p className="dica">
          O sistema calcula quanto do faturamento vai para pagar o promotor. Exemplo: promotor de R$ 3.000 em lojas que
          compram R$ 30.000 = 10%. Defina a partir de quantos % o resultado fica amarelo (atenção) e vermelho (crítico).
        </p>
        <div className="campos-linha">
          <Numero
            rotulo="Amarelo a partir de"
            valor={regras.faixa_alerta}
            sufixo="%"
            aoMudar={(v) => alterar('faixa_alerta', v)}
          />
          <Numero
            rotulo="Vermelho a partir de"
            valor={regras.faixa_critico}
            sufixo="%"
            aoMudar={(v) => alterar('faixa_critico', v)}
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
