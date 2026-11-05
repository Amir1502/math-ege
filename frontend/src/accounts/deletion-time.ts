// Deletion timestamps are validated before comparison and may carry six fractional digits.
export function deletionInstant(value: string): bigint {
  const fraction = value.match(/\.(\d{1,6})(?=Z|[+-]\d{2}:\d{2}$)/)?.[1] ?? '';
  const seconds = Date.parse(value.replace(/\.\d{1,6}(?=Z|[+-]\d{2}:\d{2}$)/, ''));
  return BigInt(seconds) * 1000n + BigInt(fraction.padEnd(6, '0'));
}
