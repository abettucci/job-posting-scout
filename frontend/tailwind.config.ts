import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#0A66C2",
          dark: "#004182",
          light: "#378FE9",
        },
      },
    },
  },
  plugins: [],
};
export default config;
