/** Russian noun form for a count of distinct products. */
export function productWord(count: number): string {
  const mod = count % 100;
  if (mod >= 11 && mod <= 14) return 'товаров';
  if (count % 10 === 1) return 'товар';
  if (count % 10 >= 2 && count % 10 <= 4) return 'товара';
  return 'товаров';
}
