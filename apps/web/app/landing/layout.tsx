import "./tailwind.css";

export default function LandingLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return <div className="landingTheme">{children}</div>;
}
