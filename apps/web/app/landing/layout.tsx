import { Instrument_Serif, Manrope } from "next/font/google";

import "./tailwind.css";

const display = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
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
