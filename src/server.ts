import { config as configureDotenv } from "dotenv";
import express, { Request, Response } from "express";
import { scrape as scrapeNinja } from "./scrapers/ninja-scraper";
import { apiKeyAuthMiddleware, fetchAllApiKeys } from "./middleware";
import OpenAI from "openai";

const app = express();
const PORT = process.env.PORT || 3000;
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
// app.use(apiKeyAuthMiddleware);

configureDotenv();
// fetchAllApiKeys();

const openaiClient = new OpenAI({
  apiKey: process.env["OPENAI_API_KEY"],
});
export const openai = () => openaiClient;

app.get("", async (req: Request, res: Response) => {
  return res.status(200).json({ status: "UP" });
});

app.get("/scrape-ninja", async (req: Request, res: Response) => {
  const url = req.query.url as string;
  if (!url) {
    return res.status(400).json({ error: "URL is required" });
  }

  try {
    const recipe = await scrapeNinja(url);
    res.json(recipe);
  } catch (error) {
    console.error("500 /scrape-ninja", error);
    res
      .status(500)
      .json({ message: "An error occurred while scraping the recipe.", error });
  }
});

app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});
