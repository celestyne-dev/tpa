import { ArrowRight } from "lucide-react";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import { ButtonLink } from "@/components/ui/button";
import { Container } from "@/components/ui/container";

function HeroArt() {
  return (
    <svg viewBox="0 0 520 560" aria-hidden className="h-auto w-full">
      <defs>
        <linearGradient id="hero-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f3e7c9" />
          <stop offset="1" stopColor="#faf6ee" />
        </linearGradient>
        <clipPath id="hero-arch">
          <path d="M40 560V260a220 220 0 0 1 440 0v300Z" />
        </clipPath>
      </defs>
      <path d="M40 560V260a220 220 0 0 1 440 0v300Z" fill="url(#hero-sky)" />
      <g clipPath="url(#hero-arch)">
        <circle cx="260" cy="300" r="92" fill="#dcc28a" />
        <circle
          cx="260"
          cy="300"
          r="128"
          fill="none"
          stroke="#c9a862"
          strokeOpacity=".35"
          strokeWidth="2"
        />
        <circle
          cx="260"
          cy="300"
          r="168"
          fill="none"
          stroke="#c9a862"
          strokeOpacity=".2"
          strokeWidth="2"
        />
        <path d="M0 380 C120 320 200 360 290 340 S440 300 520 330 V560 H0Z" fill="#a8bb9a" />
        <path d="M0 430 C110 390 230 430 330 405 S470 380 520 395 V560 H0Z" fill="#6f8761" />
        <path d="M0 490 C140 455 260 495 380 470 S490 455 520 462 V560 H0Z" fill="#45593c" />
      </g>
      <path
        d="M40 560V260a220 220 0 0 1 440 0v300"
        fill="none"
        stroke="#24221f"
        strokeOpacity=".12"
        strokeWidth="1.5"
      />
      <g fill="#57704b">
        <path d="M96 168c18-30 46-38 64-34-8 24-34 40-64 34Z" opacity=".75" />
        <path d="M452 196c-12-26-36-36-54-34 4 22 28 38 54 34Z" opacity=".6" />
      </g>
    </svg>
  );
}

export function Hero() {
  return (
    <section className="relative overflow-hidden bg-ivory">
      <div
        aria-hidden
        className="pointer-events-none absolute top-0 right-0 h-full w-1/2 bg-gradient-to-l from-cream to-transparent"
      />
      <Container
        size="wide"
        className="relative grid items-center gap-12 py-16 sm:py-20 lg:grid-cols-[1.1fr_1fr] lg:gap-16 lg:py-28"
      >
        <div>
          <p className="inline-flex items-center gap-3 text-sm font-semibold tracking-[0.16em] text-sage-700 uppercase">
            <span aria-hidden className="h-px w-10 bg-gold-400" />
            {siteConfig.name}
          </p>
          <h1 className="mt-6 text-[2.75rem] leading-[1.05] font-medium sm:text-6xl lg:text-7xl">
            A Better Mindset. <span className="block text-sage-700 italic">A Brighter Life.</span>
          </h1>
          <p className="mt-7 max-w-xl text-lg text-muted sm:text-xl">
            Practical encouragement, thoughtful resources, and tools to help you grow through every
            season of life.
          </p>
          <div className="mt-10 flex flex-col gap-3 sm:flex-row sm:items-center">
            <ButtonLink href={routes.freeResources} size="lg">
              Explore Our Resources
              <ArrowRight aria-hidden />
            </ButtonLink>
            <ButtonLink href={routes.articles} size="lg" variant="outline">
              Read Our Articles
            </ButtonLink>
          </div>
        </div>
        <div className="mx-auto w-full max-w-md lg:max-w-none">
          <HeroArt />
        </div>
      </Container>
    </section>
  );
}
