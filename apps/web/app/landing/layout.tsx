import { Manrope, Playfair_Display } from "next/font/google";

import "./tailwind.css";

const display = Playfair_Display({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--landing-font-display",
});

const body = Manrope({
  subsets: ["latin"],
  variable: "--landing-font-body",
});

export default function LandingLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className={`landingTheme ${display.variable} ${body.variable}`}>
      {children}
    </div>
  );
}
