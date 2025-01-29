import axios from "axios";
import cheerio from "cheerio";
import { Recipe } from "../types";
import { cleanText, extractNumber } from "../utils";
import { parseIngredient } from "../utils/parse-ingredients";
import Crawler from "crawler";

// export const scrape = async (url: string): Promise<Recipe> => {
//   // const response = await axios.get(url, {
//   //   headers: {
//   //     "User-Agent":
//   //       "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36",
//   //   },
//   // });
//   // const html = response.data;
//   // const $ = cheerio.load(html);

//   crawler.queue({
//     uri: url,
//     callback: async (error, res, done) => {
//       if (error) {
//         console.error(error);
//       } else {
//         const $ = cheerio.load(res.body);
//         const recipe = await parseRecipe($);
//         console.log(recipe);
//       }
//       done();
//     },
//   });
// };

export const processNinjaCheerio = async ($: any) => {
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
    (index: number, element: any) => {
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
  $(".single-cooking-mode-modal__step p").each(
    (index: number, element: any) => {
      const step = cleanText($(element).text());
      steps.push(step);
    }
  );

  // Scrape image
  let image = "";
  try {
    image =
      $(".single-hero")
        .css("background-image")
        ?.replace(/url\(["']?(.+?)["']?\)/, "$1") ?? "";
  } catch (error) {
    console.error("Error parsing image:", error);
  }

  return {
    title,
    totalTime,
    servings,
    ingredients,
    steps,
    image,
  };
};
