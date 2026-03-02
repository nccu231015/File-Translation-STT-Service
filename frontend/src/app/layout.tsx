import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { UserProvider } from "@/context/user-context";
import { TranslationProvider } from "@/context/translation-context";
import { VoiceProvider } from "@/context/voice-context";
import { Toaster } from "@/components/ui/sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "全一電子 AI 助手",
  description: "地端部署企業 AI 平台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-TW">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {/* UserProvider must be outermost so child contexts can read username */}
        <UserProvider>
          <TranslationProvider>
            <VoiceProvider>
              {children}
            </VoiceProvider>
          </TranslationProvider>
        </UserProvider>
        <Toaster />
      </body>
    </html>
  );
}
