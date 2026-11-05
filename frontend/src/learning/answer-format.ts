/** This checks syntax only. Exact mathematical comparison belongs to the server. */
export function answerFormatError(raw: string): string | null {
  if (raw.length > 64) return 'Ответ должен содержать не больше 64 символов.';
  const value = raw.trim().replaceAll('−', '-').replaceAll('.', ',');
  if (!value) return 'Введите ответ. Пустое поле не считается нулём.';
  if (/^-?[0-9]+(?:,[0-9]+)?$/.test(value)) return null;
  const fraction = /^-?[0-9]+\/([0-9]+)$/.exec(value);
  if (fraction) return /^0+$/.test(fraction[1]) ? 'Знаменатель дроби не может быть равен нулю.' : null;
  return 'Введите целое число, десятичную дробь или дробь a/b. Без единиц, выражений и пробелов внутри числа.';
}
