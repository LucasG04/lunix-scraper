import OpenAI from "openai";

let openaiClient: OpenAI | null = null;
export const openai = () => {
  if (!openaiClient) {
    openaiClient = new OpenAI({ apiKey: process.env["OPENAI_API_KEY"] });
  }
  return openaiClient;
};
