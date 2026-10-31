---
colors:
  canvas: '#0B131B'
  surface: '#101B26'
  ink: '#F1F0EA'
  accent: '#E8C9A8'
  amber: '#E8B86A'
  success: '#7FD3AC'
typography:
  display: Newsreader
  body: Public Sans
  mono: IBM Plex Mono
---

# Night Board / launch film
The landing's real visual vocabulary: an advocate's evening, court papers, cause-list rows, order directions, citations, then dawn. Cinematic editorial typography, warm fine rules, opaque near-square panels, deep blue night, warm paper. No decorative fake analytics, generic AI network, bouncing cards, or tiny unreadable text. Each shot fills the frame.

Canvas 1920x1080, all compositions 6 seconds. Titles 94–132px, body 32–38px, mono metadata 26–30px. Primary text inside x192..1728/y108..972. Surfaces can bleed. All main text at least 28px. Warm accent is rationed. Never leave frame0 blank. Land all readable type still. Do not label chapter numbers.

Fonts shipped as assets/fonts/Newsreader.woff2 (normal 200–800), Newsreader-Italic.woff2 (italic 200–800), PublicSans.woff2 (normal 400–800), IBMPlexMono.woff2 (normal 400). Use @font-face in each HTML file with those root-relative paths, e.g. url('assets/fonts/Newsreader.woff2'). No external requests. Root id unique per scene, root width/height 100%. Template contains style, markup, script. Scope every selector to the scene id or unique prefix. Each composition builds exactly one paused gsap timeline registered only when complete. Stable ids, no JS-created markup, no clocks/randomness/timers. All timed layers class clip, start0,duration6. Animate children not .clip visibility. Root background must have separate full-bleed background child.

Use source sample names and data verbatim. All product illustrations carry 'Illustrative case data' at 26px in readable low-emphasis text. These are cinematic interpretations of the landing's existing demos, not invented app screens. No audio/media elements. Shared index imports local GSAP.

Motion: power3.out for entrances 0.5–0.8s; expo.inOut camera 0.9–1.4s; secondary 0.12s behind hero; no endless idle drift, no bounce. Exit through a source object, sweep or paper. Final state lands by 5.6s. Every seam resolves on full-color navy, paper, or dawn field. Use data-layout-allow-overlap and data-layout-allow-overflow only on intended illustration groups. Allow elements behind readable text only with solid enough ground for contrast.

