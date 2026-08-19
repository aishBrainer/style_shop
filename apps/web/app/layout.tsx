import type { Metadata, Viewport } from 'next'
import { Playfair_Display } from 'next/font/google'

import { Providers } from '@/components/providers'
import './globals.css'

// Display serif, matching the reference design. Only headline type uses it, so
// a single weight range keeps the payload small.
const display = Playfair_Display({
  subsets: ['latin'],
  weight: ['600', '700'],
  variable: '--font-display',
  display: 'swap',
})

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME || 'AI Fashion Studio'

export const metadata: Metadata = {
  title: {
    default: `${APP_NAME} — Turn One Product Photo Into a Complete AI Photoshoot`,
    template: `%s · ${APP_NAME}`,
  },
  description:
    'Upload your product. Choose a model. Generate professional ecommerce imagery in minutes.',
  // §102: customer uploads are commercially sensitive; keep the app out of
  // search indexes entirely.
  robots: { index: false, follow: false },
}

export const viewport: Viewport = {
  themeColor: '#ffffff',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={display.variable}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
