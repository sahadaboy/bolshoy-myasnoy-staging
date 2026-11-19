export function formatPhoneInput(input: string): string {
  let digits = input.replace(/\D/g, '').slice(0, 15);
  if (!digits) return '';
  if (digits[0] === '8' && !input.startsWith('+')) digits = '7' + digits.slice(1);
  if (digits[0] !== '7') return '+' + digits;
  const local = digits.slice(1, 11);
  return (
    '+7' +
    (local ? ' (' + local.slice(0, 3) : '') +
    (local.length >= 3 ? ') ' : '') +
    local.slice(3, 6) +
    (local.length > 6 ? '-' + local.slice(6, 8) : '') +
    (local.length > 8 ? '-' + local.slice(8, 10) : '')
  );
}
