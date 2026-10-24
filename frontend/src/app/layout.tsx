import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "GnkAlgo Trader | Intelligence Behind Every Trade",
  icons: { icon: "/brand/gnkalgo.png", apple: "/brand/gnkalgo.png" },
  description: "A focused workspace for strategy research, risk management and paper trading. Intelligence behind every trade.",
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
