/*
 * The sun-avoidance animation as MP4 files for slides, rendered from the
 * viewer itself frame by frame.
 *
 *   NODE_PATH=<global node_modules> \
 *     node scripts/render_slew_video.mjs http://127.0.0.1:8000 <out dir> [variant ...]
 *
 * The first argument is a server already serving the site root, as for
 * render_slew_figure.mjs. ffmpeg (with libx264) must be on PATH. With no
 * variant named, all four are rendered:
 *
 *   full-ja, full-en    the page as it looks in a browser tab -- title,
 *                       instruments, legend and strip chart -- without the
 *                       buttons, which mean nothing in a video
 *   clean-ja, clean-en  the scene alone, with the labels drawn in it, for a
 *                       slide that carries its own title and notes
 *
 * The viewer advances with the wall clock, so recording the screen would drop
 * or repeat frames whenever the software renderer falls behind. Instead the
 * page's clock is replaced before it loads: requestAnimationFrame only queues
 * the callback, and performance.now reads a counter. The script moves the
 * counter on by exactly one frame, runs the queued frame and screenshots the
 * page, so every frame is the viewer's own at an exact time however long it
 * takes to draw.
 *
 * Output is H.264 in MP4, the format PowerPoint plays most reliably on both
 * Windows and macOS: 1920x1080 at 30 fps, yuv420p with BT.709 colour, the
 * index at the front of the file, a keyframe every second so the timeline can
 * be scrubbed, and no audio track. The run plays at the page's default 25x
 * (5x for the first 12 s), held for a second at the start and three at the
 * end.
 */
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';

/* Playwright is not a dependency of this repository -- see
   render_slew_figure.mjs -- so it is resolved through NODE_PATH. */
const { chromium } = createRequire(import.meta.url)('playwright');

const ORIGIN = process.argv[2] || 'http://127.0.0.1:8000';
const OUTDIR = process.argv[3] || '.';
const W = 1280, H = 720, SCALE = 1.5;         // CSS pixels, drawn at 1920x1080
const FPS = 30, HOLD_START = 1, HOLD_END = 3;  // seconds

/* What each variant hides. Hidden panels drop out of the viewer's framing
   (it measures only what is laid out), so the scene re-centres on its own. */
const HIDE = {
  full:  '.transport{display:none !important}',
  clean: 'header, .mid, footer{display:none !important}',
};
const ALL = ['full-ja', 'full-en', 'clean-ja', 'clean-en'];
const wanted = process.argv.slice(4).length ? process.argv.slice(4) : ALL;
for (const v of wanted) {
  if (!ALL.includes(v)) throw new Error(`unknown variant ${v}; one of ${ALL.join(', ')}`);
}

/* Installed before any of the page's scripts run. */
function installClock() {
  let now = 0, queue = [];
  performance.now = () => now;
  window.requestAnimationFrame = (cb) => { queue.push(cb); return queue.length; };
  window.cancelAnimationFrame = () => {};
  window.__frame = (ms) => {
    now += ms;
    const due = queue; queue = [];
    for (const cb of due) cb(now);
  };
}

function encoder(file) {
  const ff = spawn('ffmpeg', [
    '-y', '-loglevel', 'error',
    '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
    '-profile:v', 'high', '-level:v', '4.1', '-g', String(FPS),
    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
    '-color_range', 'tv', '-movflags', '+faststart', '-an', file,
  ], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((ok, fail) => ff.on('close', (code) =>
    code === 0 ? ok() : fail(new Error(`ffmpeg exited with ${code} for ${file}`))));
  return { ff, done };
}

mkdirSync(OUTDIR, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium',
  args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader',
         '--no-sandbox', '--disable-dev-shm-usage'],
});

for (const variant of wanted) {
  const [ui, lang] = variant.split('-');
  const page = await browser.newPage({
    viewport: { width: W, height: H }, deviceScaleFactor: SCALE,
    reducedMotion: 'no-preference',
  });
  await page.addInitScript(installClock);
  await page.goto(`${ORIGIN}/assets/demos/sun-safe-slew/index.html?lang=${lang}`,
                  { waitUntil: 'load' });
  /* booted: the viewer removes its loading overlay on the first frame. Poll
     on a timer -- Playwright's default polls on requestAnimationFrame, which
     now only runs when this script says so. */
  await page.waitForFunction(() => !document.getElementById('boot'), null,
                             { polling: 250, timeout: 60000 });
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({ content: HIDE[ui] });
  await page.evaluate(() => window.dispatchEvent(new Event('resize')));

  const tend = await page.evaluate(async () =>
    (await (await fetch('data/trajectory.json')).json()).meta.Tend);
  const elapsed = () => page.evaluate(() =>
    parseFloat(document.getElementById('met').textContent));

  const file = `${OUTDIR}/sun-safe-slew-${variant}.mp4`;
  const { ff, done } = encoder(file);
  const frame = async () => {
    await page.evaluate((ms) => window.__frame(ms), 1000 / FPS);
    const png = await page.screenshot({ type: 'png' });
    if (!ff.stdin.write(png)) await new Promise((r) => ff.stdin.once('drain', r));
  };

  /* paused at t = 0 while the camera settles on its preset, then the run */
  await page.evaluate(() => document.getElementById('play').click());
  for (let i = 0; i < HOLD_START * FPS; i++) await frame();
  await page.evaluate(() => document.getElementById('play').click());
  let n = HOLD_START * FPS;
  while ((await elapsed()) < tend - 0.05) {
    await frame(); n++;
    if (n % (10 * FPS) === 0) console.error(`${variant}: ${n} frames`);
    if (n > 5000) throw new Error('the run never reached its end');
  }
  for (let i = 0; i < HOLD_END * FPS; i++) { await frame(); n++; }

  ff.stdin.end();
  await done;
  console.log(`${file}: ${n} frames, ${(n / FPS).toFixed(1)} s`);
  await page.close();
}
await browser.close();
