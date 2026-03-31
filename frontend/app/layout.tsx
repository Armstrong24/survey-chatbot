import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Pune Plastic Bag Survey — Data Chatbot",
  description:
    "Interactive AI chatbot for the survey on Awareness and Readiness to use Sustainable alternatives to plastic bags in Pune.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} bg-gray-50 text-gray-900 antialiased dark:bg-gray-950 dark:text-gray-100`}>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var key='theme-preference';var theme=localStorage.getItem(key)||'system';var isDark=theme==='dark'||(theme==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);if(isDark){document.documentElement.classList.add('dark');}else{document.documentElement.classList.remove('dark');}document.documentElement.setAttribute('data-theme',theme);}catch(e){}})();`,
          }}
        />
        {children}
      </body>
    </html>
  );
}
