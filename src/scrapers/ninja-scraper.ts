import axios from "axios";
import cheerio from "cheerio";
import { Recipe } from "../types";
import { cleanText, extractNumber } from "../utils";
import { parseIngredient } from "../utils/parse-ingredients";

export const scrape = async (url: string): Promise<Recipe> => {
  const response = await axios.get(url);
  const html = response.data;
  const $ = cheerio.load(html);

  // Scrape title
  const title = cleanText($("div.single-hero__title h1").first().text());

  // Scrape total time
  const totalTime =
    extractNumber(cleanText($(".single-method-overview__total-time").text())) ??
    0;

  // Scrape servings
  const servings =
    extractNumber(
      cleanText(
        $(
          ".single-skill-serves__serves .single-skill-serves__item-wrap span:nth-child(2)"
        ).text()
      )
    ) ?? 0;

  // Scrape ingredients (metric)
  const ingredientsSet: Set<string> = new Set();
  $('.single-ingredients__group[data-unit="metric"] li').each(
    (index, element) => {
      const ingredient = cleanText($(element).text());
      ingredientsSet.add(ingredient);
    }
  );
  const ingredientsArray = Array.from(ingredientsSet);
  const ingredients = await Promise.all(
    ingredientsArray.map(
      async (ingredient) => await parseIngredient(ingredient)
    )
  );

  // Scrape steps
  const steps: string[] = [];
  $(".single-cooking-mode-modal__step p").each((index, element) => {
    const step = cleanText($(element).text());
    steps.push(step);
  });

  // Scrape image
  const image =
    $(".single-hero")
      .css("background-image")
      ?.replace(/url\(["']?(.+?)["']?\)/, "$1") ?? "";

  return {
    title,
    totalTime,
    servings,
    ingredients,
    steps,
    image,
  };
};
