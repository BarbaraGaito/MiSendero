export const utf8Bytes = (value: string) => Array.from(value).reduce((total, character) => {
  const point = character.codePointAt(0)!;
  return total + (point <= 0x7f ? 1 : point <= 0x7ff ? 2 : point <= 0xffff ? 3 : 4);
}, 0);
