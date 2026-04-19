import express, { Request, Response } from "express";
import { processNinjaCheerio } from "./scrapers/ninja-scraper";
import { apiKeyAuthMiddleware, fetchAllApiKeys } from "./middleware";
import * as cheerio from "cheerio";

const app = express();
const PORT = process.env.PORT || 3000;
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(apiKeyAuthMiddleware);

fetchAllApiKeys();

app.get("", async (req: Request, res: Response) => {
  return res.status(200).json({ status: "UP" });
});

app.get("/scrape-ninja", async (req: Request, res: Response) => {
  const url = req.query.url as string;
  if (!url) {
    return res.status(400).json({ error: "URL is required" });
  }

  try {
    const response = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      },
    });

    if (!response.ok) {
      return res
        .status(500)
        .json({ error: `Failed to fetch URL: ${response.status}` });
    }

    const html = await response.text();
    const $ = cheerio.load(html);
    const recipe = await processNinjaCheerio($);
    res.json(recipe);
  } catch (error) {
    console.error("500 /scrape-ninja", error);
    res
      .status(500)
      .json({ message: "An error occurred while scraping the recipe.", error });
  }
});

const server = app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});

const shutdown = () => {
  server.close(() => process.exit(0));
};

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
