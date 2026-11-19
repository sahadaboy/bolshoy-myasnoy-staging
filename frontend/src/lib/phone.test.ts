import { expect, it } from 'vitest';
import { formatPhoneInput } from './phone';
it('formats manually entered Russian numbers and preserves international numbers', () => {
  expect(formatPhoneInput('89786544777')).toBe('+7 (978) 654-47-77');
  expect(formatPhoneInput('+79786544777')).toBe('+7 (978) 654-47-77');
  expect(formatPhoneInput('+37499123456')).toBe('+37499123456');
  expect(formatPhoneInput('')).toBe('');
});
