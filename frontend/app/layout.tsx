import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const spaceGrotesk = Space_Grotesk({ variable: "--font-space-grotesk", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Structura",
  description: "Watch data structures move, step by step.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // suppressHydrationWarning: browser extensions (e.g. ColorZilla) add attributes to <html>/<body>
    // before React loads. This only silences attribute mismatches on these two tags, not on children.
    <html lang="en" className={`${inter.variable} ${spaceGrotesk.variable} dark h-full`} data-scroll-behavior="smooth" suppressHydrationWarning>
      <body className="min-h-full" suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
