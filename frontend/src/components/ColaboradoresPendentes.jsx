// Nomes da coluna "Colaborador" das abas SC, SP, PR, MG e RS que não bateram com nenhum promotor da aba
// PROMOTORES BRASIL. As lojas desses nomes ficam sem promotor (fora do Resumo) até serem ligadas aqui.
import { useState } from 'react'
import { http } from '../api.js'
import { Tabela, useLista } from './ui.jsx'

// Padrão: início do ano, para as lojas entrarem nos meses do faturamento importado.
const inicioDoAno = () => `${new Date().getFullYear()}-01-01`

function Ligar({ item, promotores, aoConcluir }) {
  const [promotor, setPromotor] = useState(item.sugestao ? String(item.sugestao.id) : '')
  const [enviando, setEnviando] = useState(false)

  async function executar(acao) {
    setEnviando(true)
    try {
      await acao()
      aoConcluir()
    } catch (e) {
      window.alert(e.message)
    } finally {
      setEnviando(false)
    }
  }

  const ligar = () => executar(() => http.post('/api/pendencias/colaborador', {
    colaborador: item.colaborador, promotor_id: Number(promotor), data_inicio: inicioDoAno(),
  }))
  const descartar = () => {
    if (!window.confirm(`Descartar as ${item.quantidade} loja(s) de "${item.colaborador}"? Elas só voltam se você importar a planilha de novo.`)) return
    executar(() => http.delete(`/api/colaboradores-pendentes?${new URLSearchParams({ colaborador: item.colaborador })}`))
  }

  return (
    <div className="acoes ligar-colaborador">
      <select value={promotor} onChange={(e) => setPromotor(e.target.value)} aria-label="Promotor">
        <option value="">Escolha o promotor…</option>
        {promotores.map((p) => (
          <option key={p.id} value={p.id}>{p.nome}{p.sem_loja ? ' (sem loja)' : ''}</option>
        ))}
      </select>
      <button disabled={!promotor || enviando} onClick={ligar}>Ligar</button>
      <button className="secundario perigo" disabled={enviando} onClick={descartar}>Descartar</button>
    </div>
  )
}

export default function ColaboradoresPendentes({ admin, aoAlterar }) {
  const [dados, recarregar] = useLista(() => http.get('/api/colaboradores-pendentes'))
  const [todosPromotores] = useLista(() => http.get('/api/promotores'))
  if (!dados || (!dados.colaboradores.length && !dados.lembrados.length)) return null
  if (!dados.colaboradores.length) return <Lembrados lembrados={dados.lembrados} admin={admin} aoAlterar={recarregar} />

  const semLoja = new Set(dados.promotores_sem_loja.map((p) => p.id))
  // Promotores sem loja primeiro: o nome certo costuma estar entre eles.
  const promotores = (todosPromotores || []).filter((p) => p.ativo)
    .map((p) => ({ ...p, sem_loja: semLoja.has(p.id) }))
    .sort((a, b) => (b.sem_loja - a.sem_loja) || a.nome.localeCompare(b.nome))
  const totalLojas = dados.colaboradores.reduce((s, c) => s + c.quantidade, 0)
  const concluir = () => { recarregar(); aoAlterar() }

  return (
    <details className="bloco colaboradores-pendentes" open>
      <summary>
        ⚠ Colaboradores não encontrados: {dados.colaboradores.length} nome(s), {totalLojas} loja(s) sem promotor
      </summary>
      <p className="dica">
        Estes nomes da coluna "Colaborador" das abas SC, SP, PR, MG e RS não batem com nenhum promotor da aba
        Promotores (nome escrito diferente, abreviado, sem acento…). As lojas deles <b>não entram no Resumo</b> até
        serem ligadas.{admin && ' Escolha o promotor certo e clique em Ligar: todas as lojas daquele nome passam para ele (a partir de 01/01 deste ano) e o sistema lembra a ligação para as próximas importações. Quando acha um nome parecido, ele já vem escolhido — confira antes de ligar.'}
      </p>
      {dados.promotores_sem_loja.length > 0 && (
        <p className="dica">
          <b>Promotores sem nenhuma loja ({dados.promotores_sem_loja.length}):</b>{' '}
          {dados.promotores_sem_loja.map((p) => p.nome).join(', ')}.
        </p>
      )}
      <Tabela
        chave="colaborador"
        linhas={dados.colaboradores}
        porPagina={20}
        arquivo="colaboradores-nao-encontrados"
        colunas={[
          { campo: 'colaborador', titulo: 'Nome na planilha', quebra: true,
            mostrar: (c) => <>{c.colaborador}{c.sugestao && <small className="dica sublinha">parecido com: {c.sugestao.nome}</small>}</>,
            exportar: (c) => c.colaborador },
          { campo: 'quantidade', titulo: 'Lojas', num: true, formato: 'inteiro' },
          { campo: 'ufs', titulo: 'UF', mostrar: (c) => c.ufs.join(', '), exportar: (c) => c.ufs.join(', ') },
          { campo: 'exemplos', titulo: 'Algumas lojas', quebra: true, semOrdem: true,
            mostrar: (c) => c.lojas.slice(0, 3).map((l) => l.loja).join(' · ') + (c.quantidade > 3 ? ' …' : ''),
            exportar: (c) => c.lojas.map((l) => l.loja).join(' · ') },
          ...(admin ? [{ campo: 'acoes', titulo: 'Ligar ao promotor', semOrdem: true, semExportar: true,
            mostrar: (c) => <Ligar key={c.colaborador} item={c} promotores={promotores} aoConcluir={concluir} /> }] : []),
        ]}
      />
      <Lembrados lembrados={dados.lembrados} admin={admin} aoAlterar={recarregar} dentro />
    </details>
  )
}

/** Nomes já ligados antes: as próximas importações usam essas ligações sozinhas. */
function Lembrados({ lembrados, admin, aoAlterar, dentro = false }) {
  if (!lembrados.length) return null
  async function esquecer(item) {
    if (!window.confirm(`Esquecer que "${item.nome}" é ${item.promotor}? As lojas já ligadas continuam com ele; ` +
      'só a próxima importação volta a perguntar.')) return
    try {
      await http.delete(`/api/colaboradores-pendentes/lembrados/${item.id}`)
      aoAlterar()
    } catch (e) {
      window.alert(e.message)
    }
  }
  return (
    <details className={dentro ? 'lembrados' : 'bloco lembrados'}>
      <summary>Ligações lembradas ({lembrados.length})</summary>
      <p className="dica">
        Nomes da planilha que você já ligou a um promotor. Nas próximas importações das abas por UF, as lojas desses
        nomes vão direto para o promotor, sem passar por aqui.
      </p>
      <Tabela
        linhas={lembrados}
        porPagina={20}
        arquivo="ligacoes-lembradas"
        colunas={[
          { campo: 'nome', titulo: 'Nome na planilha', quebra: true },
          { campo: 'promotor', titulo: 'Promotor cadastrado', quebra: true },
          { campo: 'codigo', titulo: 'Código' },
          ...(admin ? [{ campo: 'acoes', titulo: '', semOrdem: true, semExportar: true,
            mostrar: (l) => <button className="secundario perigo" onClick={() => esquecer(l)}>Esquecer</button> }] : []),
        ]}
      />
    </details>
  )
}
