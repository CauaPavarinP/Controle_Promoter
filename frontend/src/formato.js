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

// Destaque do "% custo sobre faturamento": vermelho quando passa do limite das Regras do cálculo.
export function classePercentual(valor, regras) {
  const limite = regras?.limite_percentual
  return valor != null && limite != null && valor > limite ? 'pct-critico' : ''
}

// "2026-03-15" -> "15/03/2026"
export const formatarData = (iso) => {
  if (!iso) return '—'
  const [ano, mes, dia] = iso.slice(0, 10).split('-')
  return `${dia}/${mes}/${ano}`
}

export const NOMES_MESES_LONGOS = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
  'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
]

// Máscara de CNPJ (14 dígitos) ou CPF (11 dígitos) enquanto digita.
export function mascararDocumento(texto) {
  const d = texto.replace(/\D/g, '').slice(0, 14)
  if (d.length <= 11) {
    return d.replace(/^(\d{3})(\d)/, '$1.$2').replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3').replace(/\.(\d{3})(\d)/, '.$1-$2')
  }
  return d
    .replace(/^(\d{2})(\d)/, '$1.$2')
    .replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
    .replace(/\.(\d{3})(\d)/, '.$1/$2')
    .replace(/(\d{4})(\d)/, '$1-$2')
}

export const UFS = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE',
  'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO']

// "2026-11-11T14:31:00" -> "11/11/2026, 14:31"
export const formatarDataHora = (iso) => (iso ? new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : '—')
