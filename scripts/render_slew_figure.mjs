/*
 * The still used on the Research pages, rendered from the animation itself.
 *
 *   NODE_PATH=<global node_modules> \
 *     node scripts/render_slew_figure.mjs http://127.0.0.1:8000 images/research
 *
 * The first argument is a server already serving the site root; the viewer
 * reads its data over HTTP, so file:// will not do.
 *
 * The viewer's ?figure=1 mode gives geometry with no text: its own labels are
 * sprites that land wherever the projection puts them, which is not where a
 * figure wants them. The annotation below is placed by hand in the 1280x720
 * frame, and deliberately kept to four notes -- the caption on the page
 * carries the colours, the numbers and the rest. Positions are pixel
 * coordinates in that frame, so they hold as long as `view`, `t` and the
 * aspect stay as they are here.
 */
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';

/* Playwright is not a dependency of this repository -- it is far too heavy to
   carry for one figure -- so it is resolved through require(), which honours
   NODE_PATH and lets a globally installed copy be pointed at:
     NODE_PATH=/usr/lib/node_modules node scripts/render_slew_figure.mjs ... */
const { chromium } = createRequire(import.meta.url)('playwright');

const ORIGIN = process.argv[2] || 'http://127.0.0.1:8000';
const OUTDIR = process.argv[3] || 'images/research';
const W = 1280, H = 720;

/* palette, kept in step with the viewer's custom properties */
const C = { teal: '#45e0d0', red: '#ff4d6a', sun: '#ff8a4d', ink: '#dce5f2', dim: '#9fb0c8' };

/* Every label is placed by hand, and so is the end of its leader. The frame
   is the "from the Sun" view: the keep-out cone projects to a circle, so
   inside the ring is a violation with no depth to argue about, which is the
   whole point of the picture and lets the annotation stay at four notes. The
   caption on the page carries the colours, the numbers and the rest.

   Leaders to the shortest path come from the left and the one to the governed
   path from the right, because the first runs inside the ring and the second
   outside it: crossing the other track would be ambiguous. `to: null` means
   the label sits next to what it names and needs no leader. Coordinates are
   pixels in the 1280x720 frame and hold for this view, time and aspect.  */
const NOTES = {
  en: [
    { head: '25° from the Sun',  sub: 'never look inside this circle', col: C.sun,
      x: 470, y: 58,  align: 'right', from: [482, 76],  to: [548, 258] },
    { head: 'Space telescope',   sub: '',                              col: C.ink,
      x: 462, y: 306, align: 'right', from: null,       to: null },
    { head: 'Shortest path',     sub: 'straight through the zone',     col: C.red,
      x: 520, y: 588, align: 'right', from: [532, 606], to: [732, 478] },
    { head: 'Governed path',     sub: 'stays outside the zone',        col: C.teal,
      x: 940, y: 250, align: 'left',  from: [930, 268], to: [856, 312] },
  ],
  ja: [
    { head: '太陽から 25°',      sub: 'この円の中を見てはならない',      col: C.sun,
      x: 470, y: 58,  align: 'right', from: [482, 76],  to: [548, 258] },
    { head: '宇宙望遠鏡',        sub: '',                              col: C.ink,
      x: 462, y: 306, align: 'right', from: null,       to: null },
    { head: '最短経路',          sub: '禁止領域を貫く',                 col: C.red,
      x: 520, y: 588, align: 'right', from: [532, 606], to: [732, 478] },
    { head: 'ERG の指令',        sub: '禁止領域の外側を回り込む',        col: C.teal,
      x: 940, y: 250, align: 'left',  from: [930, 268], to: [856, 312] },
  ],
};

const overlay = (notes) => `
<style>
  #anno{position:fixed; inset:0; z-index:9; pointer-events:none;
        font-family:var(--font-body)}
  #anno svg{position:absolute; inset:0; width:100%; height:100%; overflow:visible}
  #anno .n{position:absolute; line-height:1.28; white-space:nowrap;
           text-shadow:0 1px 3px #070a12, 0 0 9px #070a12, 0 0 20px #070a12}
  #anno .h{font-size:27px; font-weight:600; letter-spacing:.01em}
  #anno .s{font-size:24px; font-weight:400; color:${C.dim}; margin-top:1px}
</style>
<div id="anno">
  <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    ${notes.filter(n => n.to).map(n => `
      <line x1="${n.from[0]}" y1="${n.from[1]}" x2="${n.to[0]}" y2="${n.to[1]}"
            stroke="${n.col}" stroke-width="1.6" stroke-opacity=".6"/>
      <circle cx="${n.to[0]}" cy="${n.to[1]}" r="3.4" fill="${n.col}" fill-opacity=".9"/>`).join('')}
  </svg>
  ${notes.map(n => `
    <div class="n" style="${n.align === 'right'
        ? `right:${W - n.x}px` : `left:${n.x}px`}; top:${n.y}px; color:${n.col};
        text-align:${n.align}">
      <div class="h">${n.head}</div>
      ${n.sub ? `<div class="s">${n.sub}</div>` : ''}
    </div>`).join('')}
</div>`;

const b = await chromium.launch({
  executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium',
  args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader',
         '--no-sandbox', '--disable-dev-shm-usage'],
});
for (const lang of ['en', 'ja']) {
  const p = await b.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  const url = `${ORIGIN}/assets/demos/sun-safe-slew/index.html`
            + `?figure=1&view=1&t=400&earth=0&lang=${lang}`;
  await p.goto(url, { waitUntil: 'load' });
  await p.waitForTimeout(6000);                      // WebGL + the first frames
  await p.evaluate(html => document.body.insertAdjacentHTML('beforeend', html),
                   overlay(NOTES[lang]));
  await p.waitForTimeout(1200);
  const png = await p.screenshot();                  // 2560x1440
  writeFileSync(`${OUTDIR}/sun-safe-slew${lang === 'ja' ? '-ja' : ''}.raw.png`, png);
  console.log(`${lang}: ${url}`);
  await p.close();
}
await b.close();
