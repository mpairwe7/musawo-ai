import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Providers from "@/components/Providers";
import ServiceWorkerRegistrar from "@/components/ServiceWorkerRegistrar";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_BASE_URL || "https://musawo.ai"),
  title: "Musawo AI — Community Health Navigator",
  description:
    "Offline-first health guidance for rural Uganda. VHT triage, maternal care, and community health support in Luganda, Runyankole, Swahili & English.",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Musawo AI",
  },
  openGraph: {
    title: "Musawo AI — Community Health Navigator",
    description:
      "Free, offline-first health guidance for rural Uganda. Supports VHT triage (iCCM), maternal care, and community health — in English, Luganda, Runyankole & Swahili.",
    siteName: "Musawo AI",
    locale: "en_UG",
    type: "website",
    url: "/",
    images: [
      { url: "/og-image.svg", width: 1200, height: 630, alt: "Musawo AI — Community Health Navigator for Rural Uganda", type: "image/svg+xml" },
      { url: "/icons/icon-512.png", width: 512, height: 512, alt: "Musawo AI logo" },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Musawo AI — Community Health Navigator",
    description:
      "Offline-first health guidance for rural Uganda. VHT triage, maternal care & community health in Luganda, Runyankole & Swahili.",
    images: ["/og-image.svg"],
  },
  icons: {
    icon: [
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: [{ url: "/icons/icon-192.png", sizes: "192x192" }],
  },
  other: {
    "mobile-web-app-capable": "yes",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  themeColor: "#2E7D32",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning className={`${geistSans.variable} ${geistMono.variable}`}>
      <head>
        <link rel="apple-touch-icon" href="/icons/icon-192.png" />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "WebApplication",
              name: "Musawo AI",
              description: "Community Health Navigator for rural Uganda — offline-first VHT triage, maternal care, and health guidance.",
              applicationCategory: "HealthApplication",
              operatingSystem: "Any",
              offers: { "@type": "Offer", price: "0", priceCurrency: "UGX" },
              author: { "@type": "Organization", name: "Musawo AI Project" },
              inLanguage: ["en", "lg", "nyn", "sw"],
              audience: { "@type": "Audience", audienceType: "Village Health Teams, Community Health Workers, Mothers, General Public" },
            }),
          }}
        />
      </head>
      <body>
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        <ServiceWorkerRegistrar />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
