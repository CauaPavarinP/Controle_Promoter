// Peças da importação de arquivos, usadas nas abas Faturamento, Promotores e Lojas por UF.
import { useEffect, useState } from 'react'
import { http } from '../api.js'
import { formatarCnpj, formatarMoeda, formatarMes } from '../formato.js'
import { exportarExcel, Tabela, useLista } from './ui.jsx'

const NOMES_TIPO = { faturamento: 'Faturamento', promotores: 'Promotores', roteiro: 'Roteiro', planilha: 'Planilha completa' }

export function ResultadoCadastro({ titulo, resultado }) {
  if (!resultado) return null
  if (resultado.erro) return <p className="dica"><b>{titulo}:</b> não encontrado no arquivo ({resultado.erro})</p>
  const c = resultado.cadastros || {}
  return (
    <div className="sucesso">
      <b>{titulo}:</b> novos {c.criados ?? 0}
      {c.atualizados != null && <> · já cadastrados {c.atualizados}</>}
      {c.reajustes != null && <> · reajustes {c.reajustes}</>}
      {c.mantidos != null && <> · já existiam {c.mantidos}</>}
      {c.pendentes != null && <> · pendências {c.pendentes}</>}
      {resultado.avisos?.map((a) => <p key={a} className="aviso-texto">⚠ {a}</p>)}
    </div>
  )
}

/** Resumo do arquivo de faturamento antes de gravar, com o botão de confirmar. */
export function PreviaFaturamento({ previa, aoConcluir, aoCancelar }) {
  const [substituir, setSubstituir] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')
  const existentes = previa.meses_existentes.length > 0

  async function confirmar() {
    setEnviando(true)
    setErro('')
    try {
      const resultado = await http.post(`/api/importacoes/faturamento/${previa.token}/confirmar`, { substituir })
      aoConcluir(resultado)
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="previa">
      <h3>Confira antes de gravar — {previa.arquivo}</h3>
      <div className="previa-numeros">
        <div><span>Período</span><b>{formatarMes(previa.meses[0])} a {formatarMes(previa.meses[previa.meses.length - 1])}</b></div>
        <div><span>Linhas</span><b>{previa.linhas_validas} válidas{previa.linhas_com_erro > 0 && <span className="texto-critico"> · {previa.linhas_com_erro} com erro</span>}</b></div>
        <div><span>Total TOTAL VENDA</span><b>{formatarMoeda(previa.total_venda)}</b></div>
        <div><span>Notas fiscais</span><b>{previa.notas}</b></div>
        <div><span>Clientes (CNPJ)</span><b>{previa.clientes}</b></div>
        <div><span>CNPJs sem roteiro</span><b>{previa.cnpjs_sem_roteiro.quantidade} · {formatarMoeda(previa.cnpjs_sem_roteiro.valor)}</b></div>
      </div>
      {previa.avisos.map((a) => <p key={a} className="aviso-texto">⚠ {a}</p>)}

      {previa.linhas_com_erro > 0 && (
        <details>
          <summary>Ver linhas com erro (ficam de fora)</summary>
          <Tabela chave="linha" linhas={previa.erros} porPagina={20} arquivo="linhas-com-erro"
            colunas={[{ campo: 'linha', titulo: 'Linha no Excel', num: true }, { campo: 'motivo', titulo: 'Motivo' }]} />
          {previa.linhas_com_erro > previa.erros.length && <p className="dica">Mostrando as primeiras {previa.erros.length}.</p>}
        </details>
      )}
      {previa.cnpjs_sem_roteiro.quantidade > 0 && (
        <details>
          <summary>CNPJs que compraram e não estão no roteiro de nenhum promotor</summary>
          <Tabela chave="cnpj" linhas={previa.cnpjs_sem_roteiro.exemplos} porPagina={20}
            colunas={[
              { campo: 'razao_social', titulo: 'Cliente', quebra: true },
              { campo: 'cnpj', titulo: 'CNPJ', mostrar: (c) => formatarCnpj(c.cnpj) },
              { campo: 'cidade', titulo: 'Cidade', mostrar: (c) => `${c.cidade || ''}${c.uf ? ` - ${c.uf}` : ''}` },
              { campo: 'valor', titulo: 'TOTAL VENDA', num: true, mostrar: (c) => formatarMoeda(c.valor) },
            ]} />
        </details>
      )}

      {existentes && (
        <label className="marcar caixa-alerta">
          <input type="checkbox" checked={substituir} onChange={(e) => setSubstituir(e.target.checked)} />
          Já existe faturamento de {previa.meses_existentes.map(formatarMes).join(', ')}. Substituir esses meses
          (apaga o que está no sistema nesses meses e grava o arquivo novo).
        </label>
      )}
      {erro && <p className="erro">{erro}</p>}
      <div className="acoes">
        <button onClick={confirmar} disabled={enviando || (existentes && !substituir)}>
          {enviando ? 'Gravando…' : 'Gravar faturamento'}
        </button>
        <button className="secundario" onClick={aoCancelar} disabled={enviando}>Cancelar</button>
      </div>
    </div>
  )
}

export function Envio({ titulo, descricao, rotulo = 'Enviar', aoEnviar }) {
  const [arquivo, setArquivo] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')

  async function enviar() {
    setEnviando(true)
    setErro('')
    try {
      await aoEnviar(arquivo)
      setArquivo(null)
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <>
      <h3>{titulo}</h3>
      <p className="dica">{descricao}</p>
      <input type="file" accept=".xlsx,.xlsm,.csv" onChange={(e) => setArquivo(e.target.files[0] || null)} />
      <button disabled={!arquivo || enviando} onClick={enviar}>
        {enviando ? 'Lendo o arquivo… (arquivos grandes demoram)' : rotulo}
      </button>
      {erro && <p className="erro">{erro}</p>}
    </>
  )
}

export function Historico({ versao, aoDesfazer, tipos }) {
  const [lista, recarregar] = useLista(() => http.get('/api/importacoes'))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (versao) recarregar() }, [versao])

  async function desfazer(item) {
    const meses = item.periodos.map(formatarMes).join(', ')
    if (!window.confirm(`Desfazer a importação de ${item.arquivo}? Os itens de ${meses} que vieram dela serão apagados. ` +
      'Meses que ela substituiu não voltam: para isso, importe de novo o arquivo anterior.')) return
    try {
      await http.post(`/api/importacoes/${item.id}/desfazer`)
      recarregar()
      aoDesfazer()
    } catch (e) {
      window.alert(e.message)
    }
  }

  async function baixarErros(item) {
    const erros = await http.get(`/api/importacoes/${item.id}/erros`)
    exportarExcel(`erros-${item.arquivo}`, [{ campo: 'linha', titulo: 'Linha no Excel' }, { campo: 'motivo', titulo: 'Motivo' }], erros)
  }

  if (!lista) return <p>Carregando…</p>
  return (
    <section className="bloco">
      <h2>Histórico de importações</h2>
      <Tabela
        linhas={tipos ? lista.filter((i) => tipos.includes(i.tipo)) : lista}
        porPagina={15}
        vazio="Nenhuma importação ainda."
        colunas={[
          { campo: 'data_hora', titulo: 'Data', mostrar: (i) => new Date(i.data_hora).toLocaleString('pt-BR') },
          { campo: 'tipo', titulo: 'Tipo', mostrar: (i) => NOMES_TIPO[i.tipo] || i.tipo },
          { campo: 'arquivo', titulo: 'Arquivo', quebra: true },
          { campo: 'usuario', titulo: 'Usuário' },
          { campo: 'periodos', titulo: 'Período', semOrdem: true,
            mostrar: (i) => (i.periodos.length ? `${formatarMes(i.periodos[0])} a ${formatarMes(i.periodos[i.periodos.length - 1])}` : '—') },
          { campo: 'linhas_importadas', titulo: 'Linhas', num: true,
            mostrar: (i) => <>{i.linhas_importadas}{i.linhas_com_erro > 0 && <span className="texto-critico"> (+{i.linhas_com_erro} com erro)</span>}</> },
          { campo: 'total_venda', titulo: 'Total', num: true, mostrar: (i) => (i.tipo === 'faturamento' ? formatarMoeda(i.total_venda) : '—') },
          { campo: 'situacao', titulo: 'Situação', mostrar: (i) => <span className={`situacao ${i.situacao === 'ativa' ? 'ativa' : 'inativa'}`}>{i.situacao}</span> },
          {
            campo: 'acoes', titulo: '', semOrdem: true,
            mostrar: (i) => (
              <div className="acoes">
                {i.linhas_com_erro > 0 && <button className="secundario" onClick={() => baixarErros(i)}>Erros (Excel)</button>}
                {i.tipo === 'faturamento' && i.situacao === 'ativa' && (
                  <button className="secundario perigo" onClick={() => desfazer(i)}>Desfazer</button>
                )}
              </div>
            ),
          },
        ]}
      />
    </section>
  )
}
