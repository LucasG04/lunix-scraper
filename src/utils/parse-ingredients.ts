import { openai } from "../server";
import { Ingredient } from "../types";

export const parseIngredient = async (
  ingredient: string
): Promise<Ingredient> => {
  //   const byRegex = parseIngredientByRegex(ingredient);
  //   if (byRegex) {
  //     return byRegex;
  //   }

  const byChatGPT = await parseIngredientByChatGPT(ingredient);
  if (byChatGPT) {
    return byChatGPT;
  }

  return {
    amount: null,
    unit: null,
    name: ingredient.trim(),
  };
};

const parseIngredientByRegex = (ingredient: string): Ingredient | undefined => {
  const regex = /^(\d+[\d\s\/.,]*)?\s*([a-zA-ZäöüÄÖÜß]{1,3})?\s*(.*)$/;
  const match = ingredient.match(regex);

  if (match) {
    return {
      amount: +match[1]?.trim() || null,
      unit: match[2]?.trim() || null,
      name: match[3]?.trim() || "",
    };
  }
};

const parseIngredientByChatGPT = async (
  ingredient: string
): Promise<Ingredient | undefined> => {
  const prompt = `Parse the following ingredient into amount, unit, and name: "${ingredient}". Respond ONLY with plain JSON without formatting. Use the JSON keys 'amount' (number), 'unit', and 'name'. Use "null" as fallback.`;

  try {
    const response = await openai().chat.completions.create({
      // model: "gpt-3.5-turbo",
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
      temperature: 0.5,
      max_tokens: 100,
    });
    const json = response.choices[0].message.content?.trim();
    return json && json.length > 0 ? JSON.parse(json) : undefined;
  } catch (error) {
    console.error("Error parsing ingredient with ChatGPT:", error);
  }
};
