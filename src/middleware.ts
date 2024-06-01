import { Request, Response, NextFunction } from "express";

let validApiKeys: string[] = [];

export const apiKeyAuthMiddleware = (
  req: Request,
  res: Response,
  next: NextFunction
) => {
  const apiKey = req.headers["x-api-key"];

  if (!apiKey || !validApiKeys.includes(apiKey as string)) {
    return res.status(401).json({ error: "Unauthorized: Invalid API key" });
  }

  next();
};

export const fetchAllApiKeys = () => {
  Object.keys(process.env).forEach((key) => {
    if (key.startsWith("API_KEY_")) {
      validApiKeys.push(process.env[key] as string);
    }
  });
};
