// Aba Agências: importa o arquivo que cada agência (ou MEI, ou a própria 101 com promotores CLT) manda no modelo
// único, e mostra o resultado de cada agência: lojas, promotores, quanto custou e quanto as lojas compraram.
import { useState } from 'react'
import { http } from '../api.js'
import { formatarMes, formatarMoeda } from '../formato.js'
import { Envio, Historico } from './Importar.jsx'
import { COLUNAS_SE_PAGA, QuadroSePaga, useSePaga } from './SePaga.jsx'
import { Tabela } from './ui.jsx'

function PreviaAtendimento({ previa, aoConcluir, aoCancelar }) {
  const [substituir, setSubstituir] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState('')
  const existentes = previa.substituir.length > 0

  async function confirmar() {
    setEnviando(true)
    setErro('')
    try {
      aoConcluir(await http.post(`/api/importacoes/atendimento/${previa.token}/confirmar`, { substituir }))
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
        <div><span>Linhas</span><b>{previa.linhas_validas} válidas{previa.linhas_com_erro > 0 && <span className="texto-critico"> · {previa.linhas_com_erro} com erro</span>}</b></div>
        <div><span>Lojas</span><b>{previa.lojas}</b></div>
        <div><span>Promotores</span><b>{previa.promotores}</b></div>
        <div><span>Valor total</span><b>{formatarMoeda(previa.valor_total)}</b></div>
      </div>
      <Tabela
        chave="chave"
        linhas={previa.grupos.map((g) => ({ ...g, chave: `${g.agencia}-${g.mes}` }))}
        porPagina={24}
        colunas={[
          { campo: 'agencia', titulo: 'Agência', quebra: true },
          { campo: 'mes', titulo: 'Mês', mostrar: (g) => formatarMes(g.mes) },
          { campo: 'lojas', titulo: 'Lojas', num: true },
          { campo: 'promotores', titulo: 'Promotores', num: true },
          { campo: 'visitas', titulo: 'Visitas', num: true },
          { campo: 'valor', titulo: 'Valor', num: true, mostrar: (g) => formatarMoeda(g.valor) },
          { campo: 'ja_existe', titulo: '', semOrdem: true,
            mostrar: (g) => (g.ja_existe ? <span className="etiqueta">já importado: será substituído</span> : '') },
        ]}
      />
      {previa.avisos.map((a) => <p key={a} className="aviso-texto">⚠ {a}</p>)}
      {previa.linhas_com_erro > 0 && (
        <details>
          <summary>Ver linhas com erro (ficam de fora)</summary>
          <Tabela chave="linha" linhas={previa.erros} porPagina={20} arquivo="linhas-com-erro"
            colunas={[{ campo: 'aba', titulo: 'Aba' }, { campo: 'linha', titulo: 'Linha no Excel', num: true },
              { campo: 'motivo', titulo: 'Motivo' }]} />
        </details>
      )}
      {existentes && (
        <label className="marcar caixa-alerta">
          <input type="checkbox" checked={substituir} onChange={(e) => setSubstituir(e.target.checked)} />
          Já existe atendimento importado de {previa.substituir.join(', ')}. Substituir (apaga o que está no sistema
          dessas agências nesses meses e grava o arquivo novo).
        </label>
      )}
      {erro && <p className="erro">{erro}</p>}
      <div className="acoes">
        <button onClick={confirmar} disabled={enviando || (existentes && !substituir)}>
          {enviando ? 'Gravando…' : 'Gravar atendimento'}
        </button>
        <button className="secundario" onClick={aoCancelar} disabled={enviando}>Cancelar</button>
      </div>
    </div>
  )
}

function Importacao({ aoImportar }) {
  const [previa, setPrevia] = useState(null)
  const [concluido, setConcluido] = useState(null)
  const [versao, setVersao] = useState(0)
  return (
    <>
      <section className="importar">
        <div className="importar-cartao destaque">
          <Envio
            titulo="Importar o arquivo de uma agência"
            descricao={'Arquivo no modelo "Atendimento das agências" (uma linha por loja: mês, agência, CNPJ, loja, ' +
              'promotor, dias, visitas e valor do mês). Pode ter uma ou várias agências e meses. Você confere o resumo ' +
              'antes de gravar; agência e mês que já existem só são substituídos se você confirmar.'}
            rotulo="Ler arquivo"
            aoEnviar={async (arquivo) => {
              setConcluido(null)
              setPrevia(await http.enviarArquivo('/api/importacoes/atendimento/previa', arquivo))
            }}
          />
          <p className="dica">
            <a href="/api/modelo-atendimento">Baixar o modelo em Excel</a> para mandar às agências (com instruções e
            conferência do CNPJ).
          </p>
        </div>
      </section>
      {previa && (
        <section className="bloco">
          <PreviaAtendimento previa={previa} aoCancelar={() => setPrevia(null)}
            aoConcluir={(r) => { setPrevia(null); setConcluido(r); setVersao((v) => v + 1); aoImportar() }} />
        </section>
      )}
      {concluido && (
        <div className="sucesso">
          Atendimento gravado: {concluido.linhas_importadas} linha(s) de {concluido.meses.map(formatarMes).join(', ')}.
          {concluido.substituidos.length > 0 && <> Substituídos: {concluido.substituidos.join(', ')}.</>}
        </div>
      )}
      <details className="bloco">
        <summary>Histórico de importações das agências</summary>
        <Historico versao={versao} aoDesfazer={() => { setVersao((v) => v + 1); aoImportar() }} tipos={['atendimento', 'limpeza']} />
      </details>
    </>
  )
}

function ApagarDados({ aoApagar }) {
  const [texto, setTexto] = useState('')
  const [mensagem, setMensagem] = useState(null)
  async function apagar() {
    try {
      const r = await http.post('/api/cadastros/apagar', { confirmacao: texto })
      setTexto('')
      setMensagem({ erro: false, texto: `Apagados ${r.atendimentos} atendimento(s). Importe os arquivos das agências de novo.` })
      aoApagar()
    } catch (e) {
      setMensagem({ erro: true, texto: e.message })
    }
  }
  return (
    <details className="bloco nao-imprimir">
      <summary>Apagar os dados das agências e começar do zero</summary>
      <p className="dica">
        Apaga todos os atendimentos importados das agências (e o que sobrou dos cadastros da planilha antiga).
        <b> Não tem volta.</b> O faturamento do ERP, os usuários, as regras e o histórico de importações ficam.
      </p>
      <div className="acoes">
        <input value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Digite APAGAR" aria-label="Confirmação" />
        <button className="secundario perigo" disabled={texto.trim().toUpperCase() !== 'APAGAR'} onClick={apagar}>Apagar dados</button>
      </div>
      {mensagem && <p className={mensagem.erro ? 'erro' : 'texto-ok'}>{mensagem.texto}</p>}
    </details>
  )
}

export default function Agencias({ admin, meses, aoImportar }) {
  const sePaga = useSePaga(meses)
  const recarregar = () => { sePaga.recarregar(); aoImportar() }
  return (
    <>
      {admin && <Importacao aoImportar={recarregar} />}
      {meses.length > 0 && (
        <>
          <QuadroSePaga titulo="As agências valem o que custam?" meses={meses} periodo={sePaga.periodo} contar="agencias"
            setPeriodo={sePaga.setPeriodo} dados={sePaga.dados} podeEditar={admin} aoMudarMargem={sePaga.recarregar} />
          {sePaga.erro && <div className="erro-caixa">{sePaga.erro}</div>}
          <section className="bloco">
            <h2>Agências ({sePaga.dados?.agencias.length ?? '…'})</h2>
            {!sePaga.dados ? <p className="carregando">Calculando…</p> : (
              <Tabela
                chave="chave"
                linhas={sePaga.dados.agencias}
                arquivo="agencias"
                vazio="Nenhuma agência neste período. Importe os arquivos das agências."
                colunas={[
                  { campo: 'nome', titulo: 'Agência ou MEI', quebra: true },
                  { campo: 'ufs', titulo: 'UF' },
                  { campo: 'lojas', titulo: 'Lojas', num: true, formato: 'inteiro' },
                  { campo: 'promotores', titulo: 'Promotores', num: true, formato: 'inteiro' },
                  { campo: 'visitas', titulo: 'Visitas', num: true, formato: 'inteiro' },
                  { campo: 'meses', titulo: 'Meses com arquivo', semOrdem: true,
                    mostrar: (a) => (a.meses.length > 1
                      ? `${formatarMes(a.meses[0])} a ${formatarMes(a.meses[a.meses.length - 1])} (${a.meses.length})`
                      : formatarMes(a.meses[0])),
                    exportar: (a) => a.meses.join(', ') },
                  ...COLUNAS_SE_PAGA,
                ]}
              />
            )}
          </section>
        </>
      )}
      {admin && <ApagarDados aoApagar={recarregar} />}
    </>
  )
}
