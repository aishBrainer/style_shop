import Link from 'next/link'
import {
  ArrowRight,
  Check,
  Image as ImageIcon,
  Layers,
  Maximize2,
  Play,
  Shirt,
  Sparkles,
  Video,
  Wand2,
} from 'lucide-react'

import { Badge, Button } from '@/components/ui'
import { HeroTransformation } from '@/components/landing/hero-transformation'
import { LandingFaq } from '@/components/landing/faq'

/** §5, §6 — the marketing page. Server-rendered; no session required. */

const FEATURES = [
  { icon: Shirt, title: 'Virtual Try-On', body: 'Put any garment on any model, on demand.' },
  { icon: ImageIcon, title: 'AI Product Photography', body: 'Studio-grade packshots from a phone photo.' },
  { icon: Layers, title: 'Model Swap', body: 'Keep the garment, change who is wearing it.' },
  { icon: Wand2, title: 'Pose Generator', body: 'Front, three-quarter, walking, editorial.' },
  { icon: Sparkles, title: 'Background Studio', body: 'Remove, replace or describe any backdrop.' },
  { icon: Maximize2, title: 'Image Enhancement', body: 'Upscale to 4x, clean up, expand the frame.' },
  { icon: Video, title: 'AI Video', body: 'Turn a still into a short product clip.' },
  { icon: Play, title: 'Ad Creative', body: 'Export every social format from one asset.' },
]

const STEPS = [
  { n: '01', title: 'Upload', body: 'Drop in a product photo. JPG, PNG or WebP.' },
  { n: '02', title: 'Choose', body: 'Pick a model from the library or upload your own.' },
  { n: '03', title: 'Generate', body: 'Watch it render live. Typically under two minutes.' },
  { n: '04', title: 'Download', body: 'HD, transparent PNG, or ecommerce-optimised.' },
]

const USE_CASES = [
  'Fashion brands',
  'Shopify stores',
  'Amazon sellers',
  'Instagram brands',
  'Agencies',
  'Jewellery',
  'Footwear',
  'Accessories',
]

const PLANS = [
  {
    name: 'Free',
    price: '$0',
    cadence: 'forever',
    features: [
      '25 credits per month',
      'Model library access',
      'Background removal',
      'Watermarked downloads',
      '1 GB storage',
    ],
    cta: 'Start free',
    highlight: false,
  },
  {
    name: 'Pro',
    price: '$39',
    cadence: 'per month',
    features: [
      '500 credits per month',
      'HD downloads, no watermark',
      'Custom model uploads',
      'Batch processing',
      'Brand kit',
      '20 GB storage',
    ],
    cta: 'Start free trial',
    highlight: true,
  },
  {
    name: 'Business',
    price: '$149',
    cadence: 'per month',
    features: [
      '2,000 credits per month',
      'Team workspaces',
      'Client projects',
      'Bulk generation',
      'Higher concurrency',
      '200 GB storage',
    ],
    cta: 'Talk to us',
    highlight: false,
  },
]

export default function LandingPage() {
  return (
    <div className="min-h-screen">
      <SiteHeader />

      {/* Section 1 — Hero (§6) */}
      <section className="relative overflow-hidden px-6 pb-24 pt-20 sm:pt-28">
        <div
          aria-hidden
          className="pointer-events-none absolute left-1/2 top-0 h-[520px] w-[900px]
                     -translate-x-1/2 rounded-full bg-accent/10 blur-[140px]"
        />
        <div className="relative mx-auto max-w-6xl text-center">
          <Badge tone="accent" className="mb-6">
            <Sparkles className="h-3 w-3" /> Self-hosted AI · no per-image API fees
          </Badge>

          <h1 className="mx-auto max-w-4xl text-balance text-4xl font-semibold leading-[1.1] tracking-tight sm:text-6xl">
            Turn One Product Photo Into a Complete AI Photoshoot.
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-ink-muted">
            Upload your product. Choose a model. Generate professional ecommerce imagery in minutes.
          </p>

          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link href="/register">
              <Button size="lg">
                Start Creating <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="#how-it-works">
              <Button size="lg" variant="secondary">
                See How It Works
              </Button>
            </Link>
          </div>

          <HeroTransformation />
        </div>
      </section>

      {/* Section 3 — Feature grid */}
      <Section id="features" eyebrow="Everything in one studio" title="One asset, every format">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="panel group p-5 transition hover:border-edge-strong hover:bg-canvas-overlay"
            >
              <div className="mb-4 inline-flex rounded-xl bg-accent-muted p-2.5 text-accent">
                <Icon className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-medium">{title}</h3>
              <p className="mt-1.5 text-sm text-ink-muted">{body}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Section 4 — How it works */}
      <Section id="how-it-works" eyebrow="How it works" title="Four steps, start to finish">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(({ n, title, body }) => (
            <div key={n} className="panel p-6">
              <span className="font-mono text-xs text-accent">{n}</span>
              <h3 className="mt-3 text-base font-medium">{title}</h3>
              <p className="mt-1.5 text-sm text-ink-muted">{body}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Section 5 — Use cases */}
      <Section eyebrow="Built for" title="Anyone who sells a physical product">
        <div className="flex flex-wrap justify-center gap-2.5">
          {USE_CASES.map((use) => (
            <span
              key={use}
              className="rounded-full border border-edge bg-canvas-raised px-4 py-2 text-sm text-ink-muted"
            >
              {use}
            </span>
          ))}
        </div>
      </Section>

      {/* Section 8 — Pricing */}
      <Section id="pricing" eyebrow="Pricing" title="Start free. Upgrade when it pays for itself.">
        <div className="grid gap-5 lg:grid-cols-3">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={
                plan.highlight
                  ? 'panel relative border-accent/40 p-6 shadow-glow'
                  : 'panel p-6'
              }
            >
              {plan.highlight && (
                <Badge tone="accent" className="absolute -top-2.5 left-6">
                  Most popular
                </Badge>
              )}
              <h3 className="text-sm font-medium uppercase tracking-wider text-ink-muted">
                {plan.name}
              </h3>
              <div className="mt-3 flex items-baseline gap-1.5">
                <span className="text-3xl font-semibold">{plan.price}</span>
                <span className="text-sm text-ink-faint">{plan.cadence}</span>
              </div>
              <ul className="mt-6 space-y-2.5">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2.5 text-sm text-ink-muted">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                    {feature}
                  </li>
                ))}
              </ul>
              <Link href="/register" className="mt-7 block">
                <Button variant={plan.highlight ? 'primary' : 'secondary'} className="w-full">
                  {plan.cta}
                </Button>
              </Link>
            </div>
          ))}
        </div>
      </Section>

      {/* Section 9 — FAQ */}
      <Section id="faq" eyebrow="Questions" title="Things worth knowing up front">
        <LandingFaq />
      </Section>

      {/* Section 10 — Final CTA */}
      <section className="px-6 py-24">
        <div className="panel mx-auto max-w-4xl overflow-hidden p-12 text-center">
          <h2 className="text-2xl font-semibold sm:text-3xl">Your next photoshoot starts now.</h2>
          <p className="mx-auto mt-3 max-w-lg text-ink-muted">
            No studio booking, no model call sheet, no retouching queue.
          </p>
          <Link href="/register" className="mt-8 inline-block">
            <Button size="lg">
              Start Creating <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </section>

      <SiteFooter />
    </div>
  )
}

function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-edge bg-canvas/80 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2.5 font-medium">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white">
            <Sparkles className="h-4 w-4" />
          </span>
          AI Fashion Studio
        </Link>

        <nav className="hidden items-center gap-7 text-sm text-ink-muted md:flex">
          <a href="#features" className="transition hover:text-ink">Features</a>
          <a href="#how-it-works" className="transition hover:text-ink">How it works</a>
          <a href="#pricing" className="transition hover:text-ink">Pricing</a>
          <a href="#faq" className="transition hover:text-ink">FAQ</a>
        </nav>

        <div className="flex items-center gap-2">
          <Link href="/login">
            <Button variant="ghost" size="sm">Sign in</Button>
          </Link>
          <Link href="/register">
            <Button size="sm">Start free</Button>
          </Link>
        </div>
      </div>
    </header>
  )
}

function SiteFooter() {
  return (
    <footer className="border-t border-edge px-6 py-10">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 text-sm text-ink-faint sm:flex-row">
        <p>© {new Date().getFullYear()} AI Fashion Studio</p>
        {/* §104 — no "100% realistic" claims anywhere in the marketing copy. */}
        <p>AI-generated product imagery. Results vary with input quality.</p>
      </div>
    </footer>
  )
}

function Section({
  id,
  eyebrow,
  title,
  children,
}: {
  id?: string
  eyebrow: string
  title: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className="px-6 py-20">
      <div className="mx-auto max-w-6xl">
        <div className="mb-10 text-center">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent">{eyebrow}</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
        </div>
        {children}
      </div>
    </section>
  )
}
