/** The brand illustration used by the split hero when no image is chosen. */
export function HeroArt() {
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
