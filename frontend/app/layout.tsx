import type { Metadata, Viewport } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'NESFIC-I-07 | Tea Drone PoW Dashboard',
  description: 'AI-Driven Drone-Based Pest Detection & Targeted Spot-Spraying for Assam & Dooars Tea Plantations',
  keywords: ['NESFIC', 'tea', 'drone', 'pest detection', 'precision agriculture', 'ArduPilot', 'Gazebo'],
  authors: [{ name: 'Tea Research Association, Tocklai' }],
  openGraph: {
    title: 'NESFIC-I-07 Drone Dashboard',
    description: 'Dual-UAV Scout + Sprayer simulation with Smart Dock integration',
    type: 'website',
  },
};

export const viewport: Viewport = {
  themeColor: '#050507',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="font-['Space_Grotesk'] min-h-screen bg-nesfic-950 text-nesfic-50">
        {children}
      </body>
    </html>
  );
}