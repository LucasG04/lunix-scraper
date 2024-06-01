export const cleanText = (text: string): string => {
  return text.trim().replace(/\s+/g, " ");
};

export const extractNumber = (text: string): number => {
  return +(text.match(/\d+/)?.[0] ?? "");
};
