const moeda = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const NOMES_MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

export const formatarMoeda = (valor) => (valor == null ? '—' : moeda.format(valor))

export const formatarPercentual = (valor) =>
  valor == null ? '—' : `${valor.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`

// "2026-04" -> "abr/2026"
export const formatarMes = (anoMes) => {
  const [ano, mes] = anoMes.split('-')
  return `${NOMES_MESES[Number(mes) - 1]}/${ano}`
}

export const formatarCnpj = (cnpj) =>
  cnpj && cnpj.length === 14
    ? cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5')
    : cnpj || 'sem CNPJ'

// Faixas de cor do "% custo sobre faturamento". PROVISÓRIO: definir com Maurício/Rayan.
export const FAIXAS_PERCENTUAL = { alerta: 15, critico: 30 }

export function classePercentual(valor) {
  if (valor == null) return 'pct-sem'
  if (valor >= FAIXAS_PERCENTUAL.critico) return 'pct-critico'
  if (valor >= FAIXAS_PERCENTUAL.alerta) return 'pct-alerta'
  return 'pct-ok'
}
