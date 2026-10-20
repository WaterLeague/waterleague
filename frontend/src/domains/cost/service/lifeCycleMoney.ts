export function lifeCycleMoney(value: string, currency: string) {
  const [whole, fraction] = value.split('.');
  const sign = whole.startsWith('-') ? '-' : '';
  const integer = BigInt(whole.replace('-', '')).toLocaleString('ko-KR');
  const decimals = fraction.replace(/0+$/, '');
  return `${sign}${integer}${decimals ? '.' + decimals : ''}${currency === 'KRW' ? '원' : ' USD'}`;
}
