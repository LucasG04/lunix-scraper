export interface Recipe {
  title: string;
  totalTime: number;
  servings: number;
  ingredients: Ingredient[];
  steps: string[];
  image: string;
}

export interface Ingredient {
  amount: number | null;
  unit: string | null;
  name: string;
}
