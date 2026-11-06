import { OfflineError } from './types';

export type AnswerMode = 'training' | 'exam';
export type Rational = { numerator: bigint; denominator: bigint };
export type ParsedAnswer = { value: Rational; normalized_answer: string };
export type CheckResult = { correct: boolean; normalized_answer: string; expected_answer: string };
export const MAX_ANSWER_LENGTH = 64;

// CPython str.strip() uses Unicode White_Space plus U+001C–U+001F, not JS trim().
const PYTHON_EDGE_SPACE = new Set([9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
  8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288]);
const DECIMAL = /^-?[0-9]+(?:,[0-9]+)?$/u;
const FRACTION = /^-?[0-9]+\/[0-9]+$/u;

function formatError(message: string): never {
  throw new OfflineError('invalid_answer_format', message, 'answer');
}

function strip(raw: string): string {
  let start = 0;
  let end = raw.length;
  while (start < end && PYTHON_EDGE_SPACE.has(raw.charCodeAt(start))) start++;
  while (end > start && PYTHON_EDGE_SPACE.has(raw.charCodeAt(end - 1))) end--;
  return raw.slice(start, end);
}

function reduced(numerator: bigint, denominator: bigint): Rational {
  let a = numerator < 0n ? -numerator : numerator;
  let b = denominator;
  while (b !== 0n) [a, b] = [b, a % b];
  return { numerator: numerator / a, denominator: denominator / a };
}

/** Exact finite decimal or reduced nonterminating fraction, matching format_fraction. */
export function formatFraction(value: Rational): string {
  if (value.numerator === 0n) return '0';
  let denominator = value.denominator;
  let twos = 0;
  let fives = 0;
  while (denominator % 2n === 0n) { denominator /= 2n; twos += 1; }
  while (denominator % 5n === 0n) { denominator /= 5n; fives += 1; }
  if (denominator !== 1n) return `${value.numerator}/${value.denominator}`;
  const places = Math.max(twos, fives);
  const magnitude = value.numerator < 0n ? -value.numerator : value.numerator;
  const scaled = magnitude * 2n ** BigInt(places - twos) * 5n ** BigInt(places - fives);
  const sign = value.numerator < 0n ? '-' : '';
  if (places === 0) return `${sign}${scaled}`;
  const digits = scaled.toString().padStart(places + 1, '0');
  const fractional = digits.slice(-places).replace(/0+$/u, '');
  const whole = digits.slice(0, -places);
  return fractional ? `${sign}${whole},${fractional}` : `${sign}${whole}`;
}

export function parseAnswer(raw: unknown, mode: AnswerMode = 'training'): ParsedAnswer {
  if (mode !== 'training' && mode !== 'exam') {
    throw new OfflineError('invalid_mode', "mode must be 'training' or 'exam'");
  }
  if (typeof raw !== 'string') formatError('Ответ должен передаваться строкой.');
  // Python counts code points before stripping, including astral characters.
  if (Array.from(raw).length > MAX_ANSWER_LENGTH) {
    formatError('Ответ должен содержать не более 64 символов.');
  }
  const text = strip(raw).replace(/−/gu, '-').replace(/\./gu, ',');
  if (!text) formatError('Введите ответ. Пустое поле не равно нулю.');
  let value: Rational;
  if (DECIMAL.test(text)) {
    const negative = text.startsWith('-');
    const [whole, fractional = ''] = (negative ? text.slice(1) : text).split(',');
    const numerator = BigInt(whole + fractional);
    value = reduced(negative ? -numerator : numerator, 10n ** BigInt(fractional.length));
  } else if (mode === 'training' && FRACTION.test(text)) {
    const [numerator, denominatorText] = text.split('/');
    const denominator = BigInt(denominatorText);
    if (denominator === 0n) {
      formatError('Знаменатель дроби должен быть положительным и не равным нулю.');
    }
    value = reduced(BigInt(numerator), denominator);
  } else {
    const suffix = mode === 'training'
      ? ' В обучении также допустима дробь a/b с положительным знаменателем.' : '';
    formatError('Введите целое число или конечную десятичную дробь без пробелов, знака плюс, выражений и единиц измерения.' + suffix);
  }
  return { value, normalized_answer: formatFraction(value) };
}

export function checkAnswer(raw: string, expected: string, mode: AnswerMode = 'training'): CheckResult {
  const parsed = parseAnswer(raw, mode);
  const reference = parseAnswer(expected, 'exam');
  return {
    correct: parsed.value.numerator === reference.value.numerator
      && parsed.value.denominator === reference.value.denominator,
    normalized_answer: parsed.normalized_answer,
    expected_answer: reference.normalized_answer,
  };
}
