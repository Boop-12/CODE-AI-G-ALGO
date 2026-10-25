import Image from "next/image";
import Link from "next/link";
import { PublicAppearance, ThemeControls } from "./PublicAppearance";

export default function PublicHome() {
  return (
    <PublicAppearance><main className="landing">
      <nav className="site-nav">
        <Link href="/" className="wordmark"><span className="brand-mark">g.</span> gnk<span>algo</span></Link>
        <div className="nav-links"><a href="#approach">Approach</a><a href="#platform">Platform</a></div>
        <ThemeControls />
        <div className="nav-actions"><Link href="/login" className="nav-signin">Sign in</Link><Link href="/register" className="button button-green">Get started <span>↗</span></Link></div>
      </nav>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow"><span className="eyebrow-dot" /> STRATEGY, BUILT FOR WHAT’S NEXT</p>
          <h1>Intelligence<br />behind <em>every trade.</em></h1>
          <p className="hero-lede">Predict, analyze, execute, manage risk, and automate with a clear view of what comes next.</p>
          <div className="hero-actions"><Link href="/register" className="button button-dark">Start your journey <span>↗</span></Link><a href="#approach" className="text-link">Explore the platform <span>↓</span></a></div>
        </div>
        <div className="hero-art">
          <Image src="/gnk-algo-brand.jpg" alt="GNK Algo: intelligence behind every trade" width={1672} height={943} priority className="hero-image" />
        </div>
      </section>
      <section className="ticker" id="approach"><span>SEE THE SIGNAL</span><i>✳</i><span>FIND YOUR EDGE</span><i>✳</i><span>MOVE WITH INTENT</span><i>✳</i><span>BUILD WHAT’S NEXT</span></section>
      <section className="approach" id="platform"><div><p className="eyebrow green">A LITTLE MORE FORWARD</p><h2>Good decisions start<br />with <em>better perspective.</em></h2></div><div className="approach-right"><p>Every next chapter starts with a question. We’re here to help you find the signal, see the bigger picture, and make your move count.</p><Link href="/register" className="text-link">Meet your next step <span>↗</span></Link></div></section>
      <footer className="site-footer"><Link href="/" className="wordmark"><span className="brand-mark">g.</span> gnk<span>algo</span></Link><span>THINK FORWARD. MAKE IT COUNT.</span><Link href="/login">Member sign in ↗</Link></footer>
    </main></PublicAppearance>
  );
}
