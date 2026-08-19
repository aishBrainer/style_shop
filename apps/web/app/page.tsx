import Link from 'next/link'
import {
  ArrowRight,
  Camera,
  Check,
  Eraser,
  Image as ImageIcon,
  Layers,
  Maximize2,
  Play,
  Scissors,
  Shirt,
  Sparkles,
  Video,
  Wand2,
} from 'lucide-react'

import { Badge, Button } from '@/components/ui'
import { HeroTransformation } from '@/components/landing/hero-transformation'
import { LandingFaq } from '@/components/landing/faq'

/**
 * §5, §6 — the marketing page. Server-rendered; no session required.
 *
 * Visual language follows the CamClo3D reference: white canvas, deep-plum ink,
 * magenta primary, Playfair Display for editorial headings, and an alternating
 * white / faint-plum section rhythm.
 *
 * Two things are deliberately absent, for honesty rather than time:
 *   - No testimonials or customer counts. There are no real customers to quote
 *     yet, and invented ones are fabricated social proof.
 *   - No photographic before/after pairs. The repo ships zero image assets, and
 *     §104 forbids presenting placeholder art as real output.
 * Both are worth adding the moment there is genuine material.
 */

const FEATURES = [
  { icon: Shirt, title: 'Virtual Try-On', body: 'Put any garment on any model, on demand.' },
  {
    icon: ImageIcon,
    title: 'AI Product Photography',
    body: 'Studio-grade packshots from a phone photo.',
  },
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
  { n: '03', title: 'Generate', body: 'Watch it render live, with progress at every stage.' },
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

/** The five single-purpose tools, mirroring the reference site's toolkit row. */
const TOOLKIT = [
  {
    icon: Maximize2,
    title: 'Image Upscaler',
    body: 'Raise resolution and sharpen detail until a product image is print-ready.',
  },
  {
    icon: Scissors,
    title: 'Background Remover',
    body: 'Cut the product out cleanly, including awkward edges like hair and lace.',
  },
  {
    icon: Camera,
    title: 'Change Background',
    body: 'Drop the product into a studio, an outdoor scene, or anything you describe.',
  },
  {
    icon: Wand2,
    title: 'Generative Fill',
    body: 'Extend a tight crop or fill a gap with matching generated content.',
  },
  {
    icon: Eraser,
    title: 'Magic Eraser',
    body: 'Paint over an unwanted object and have the background reconstructed behind it.',
  },
]

/**
 * What a brand currently pays for separately. Figures are widely-quoted industry
 * ranges shown for orientation, not quotes for any specific vendor — and they
 * are labelled as such in the UI so they cannot read as our own pricing.
 */
const REPLACES = [
  {
    role: 'Photographer, models, studio',
    cost: '$500 – $5,000 per shoot',
    instead: 'On-model imagery from a flat product photo',
  },
  {
    role: 'Ad designer',
    cost: 'Retainer, or a fee per creative',
    instead: 'Image ads generated from your brand kit',
  },
  {
    role: 'Video editor',
    cost: 'Days of turnaround per cut',
    instead: 'Short product video from a single still',
  },
  {
    role: 'Retouching queue',
    cost: 'Per-image, plus revision rounds',
    instead: 'Upscale, erase and background tools in the editor',
  },
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
                     -translate-x-1/2 rounded-full bg-lilac/20 blur-[140px]"
        />
        <div className="relative mx-auto max-w-6xl text-center">
          <Badge tone="accent" className="mb-6">
            <Sparkles className="h-3 w-3" /> Self-hosted AI · no per-image API fees
          </Badge>

          <h1 className="display mx-auto max-w-4xl text-balance text-4xl leading-[1.08] sm:text-6xl">
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
              <Button size="lg" variant="outline">
                See How It Works
              </Button>
            </Link>
          </div>

          <p className="mt-4 text-sm text-ink-faint">No credit card required</p>

          <HeroTransformation />
        </div>
      </section>

      {/* Section 3 — Feature grid */}
      <Section
        id="features"
        band
        eyebrow="The studio"
        title="A photo studio that fits in a browser tab"
        lede="On-model imagery, product photography, edits, poses and video — all generated from the product photos you already have."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="panel group p-5 transition hover:border-accent/30 hover:shadow-lifted"
            >
              <div className="mb-4 inline-flex rounded-xl bg-accent-muted p-2.5 text-accent">
                <Icon className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-semibold">{title}</h3>
              <p className="mt-1.5 text-sm text-ink-muted">{body}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Section 4 — How it works */}
      <Section id="how-it-works" eyebrow="How it works" title="Four steps, start to finish">
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(({ n, title, body }) => (
            <li key={n} className="panel p-6">
              <span className="font-mono text-xs font-semibold text-accent">{n}</span>
              <h3 className="mt-3 text-base font-semibold">{title}</h3>
              <p className="mt-1.5 text-sm text-ink-muted">{body}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* What the pipeline replaces. */}
      <Section
        band
        eyebrow="What it replaces"
        title="One subscription instead of four line items"
        lede="What brands typically stop paying for separately once the whole pipeline lives in one place."
      >
        <div className="panel divide-y divide-edge overflow-hidden">
          {REPLACES.map(({ role, cost, instead }) => (
            <div
              key={role}
              className="grid gap-2 p-5 sm:grid-cols-[1.1fr_1fr_1.3fr] sm:items-center sm:gap-6"
            >
              <p className="font-semibold">{role}</p>
              <p className="text-sm text-ink-faint line-through decoration-danger/50">{cost}</p>
              <p className="flex items-start gap-2 text-sm text-ink-muted">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                {instead}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-4 text-center text-xs text-ink-faint">
          Cost ranges are common industry figures shown for orientation only, not quotes.
        </p>
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

      {/* Creative toolkit — the single-purpose tools. */}
      <Section
        band
        eyebrow="Creative toolkit"
        title="Smaller tools for the last ten percent"
        lede="Every one of these is a first-class tool in the editor, not a buried menu item."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {TOOLKIT.map(({ icon: Icon, title, body }) => (
            <div key={title} className="panel flex flex-col p-6 transition hover:shadow-lifted">
              <div className="mb-4 inline-flex w-fit rounded-xl bg-lilac/20 p-2.5 text-plum">
                <Icon className="h-5 w-5" />
              </div>
              <h3 className="text-base font-semibold">{title}</h3>
              <p className="mt-2 flex-1 text-sm text-ink-muted">{body}</p>
              <Link
                href="/register"
                className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-accent
                           transition hover:text-accent-hover"
              >
                Try it free <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
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
                plan.highlight ? 'panel relative border-accent/40 p-6 shadow-lifted' : 'panel p-6'
              }
            >
              {plan.highlight && (
                <Badge tone="accent" className="absolute -top-2.5 left-6">
                  Most popular
                </Badge>
              )}
              <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-muted">
                {plan.name}
              </h3>
              <div className="mt-3 flex items-baseline gap-1.5">
                <span className="display text-4xl">{plan.price}</span>
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
      <Section band id="faq" eyebrow="Questions" title="Things worth knowing up front">
        <LandingFaq />
      </Section>

      {/* Section 10 — Final CTA, on the deep-plum band. */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-4xl overflow-hidden rounded-2xl bg-plum px-6 py-14 text-center">
          <h2 className="display text-3xl text-white sm:text-4xl">
            Your next photoshoot starts now.
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-lilac-soft">
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
    <header className="sticky top-0 z-40 border-b border-edge bg-canvas/85 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2.5 font-semibold">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white">
            <Sparkles className="h-4 w-4" />
          </span>
          AI Fashion Studio
        </Link>

        <nav className="hidden items-center gap-7 text-sm text-ink-muted md:flex">
          <a href="#features" className="transition hover:text-accent">
            Features
          </a>
          <a href="#how-it-works" className="transition hover:text-accent">
            How it works
          </a>
          <a href="#pricing" className="transition hover:text-accent">
            Pricing
          </a>
          <a href="#faq" className="transition hover:text-accent">
            FAQ
          </a>
        </nav>

        <div className="flex items-center gap-2">
          <Link href="/login">
            <Button variant="ghost" size="sm">
              Sign in
            </Button>
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
  lede,
  band,
  children,
}: {
  id?: string
  eyebrow: string
  title: string
  lede?: string
  /** Faint plum wash, used to alternate against the white sections. */
  band?: boolean
  children: React.ReactNode
}) {
  return (
    <section id={id} className={band ? 'bg-canvas-sunken px-6 py-20' : 'px-6 py-20'}>
      <div className="mx-auto max-w-6xl">
        <div className="mb-10 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">{eyebrow}</p>
          <h2 className="display mx-auto mt-3 max-w-2xl text-3xl sm:text-4xl">{title}</h2>
          {lede && <p className="mx-auto mt-4 max-w-2xl text-ink-muted">{lede}</p>}
        </div>
        {children}
      </div>
    </section>
  )
}
