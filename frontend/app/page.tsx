import { Suspense } from "react";
import { Hero } from "@/components/landing/hero";
import { GuestActions, NavActions } from "@/components/landing/nav-actions";
import { PromptMarquee } from "@/components/landing/prompt-marquee";
import { ScrollProgress } from "@/components/landing/scroll-progress";
import { SiteFooter } from "@/components/landing/site-footer";
import { SiteNav } from "@/components/landing/site-nav";
import { StatStrip } from "@/components/landing/stat-strip";

// Below the fold: lazy-loaded from a Client Component so their JavaScript is split into separate chunks.
import { CtaBand, HowItWorks, TopicsBento } from "@/components/landing/lazy-sections";

export default function LandingPage() {
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-lg focus:bg-accent focus:px-3 focus:py-2 focus:text-on-accent">
        Skip to content
      </a>
      <ScrollProgress />
      <SiteNav
        actions={<Suspense fallback={<GuestActions />}><NavActions /></Suspense>}
        mobileActions={<Suspense fallback={<GuestActions variant="sheet" />}><NavActions variant="sheet" /></Suspense>}
      />
      <main id="main">
        <Hero />
        <StatStrip />
        <PromptMarquee />
        <HowItWorks />
        <TopicsBento />
        <CtaBand />
      </main>
      <SiteFooter />
    </>
  );
}
