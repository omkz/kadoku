import type {Metadata, Viewport} from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kadoku — Thoughtful gifts, made easy",
  description: "Your AI Gift Concierge. Find thoughtful gifts through conversation, not endless browsing.",
  applicationName: "Kadoku",
  manifest: "/manifest.webmanifest",
  icons: {icon: "/logo.svg"},
};
export const viewport: Viewport = {width:"device-width", initialScale:1, themeColor:"#F4E6CC"};

export default function RootLayout({children}: Readonly<{children:React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
