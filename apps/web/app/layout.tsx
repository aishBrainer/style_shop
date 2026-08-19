import type { Metadata, Viewport } from 'next'

import { Providers } from '@/components/providers'
import './globals.css'

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
  themeColor: '#0a0b0f',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
