---
name: Cyber Memoir
description: An evidence-first archive of Chinese internet memes, shown as a planetarium where every lit star is a dated piece of evidence.
colors:
  sky-0: "#030305"
  sky-1: "#050608"
  sky-2: "#0b0c10"
  sky-3: "#17191f"
  panel: "rgba(8, 9, 12, 0.8)"
  panel-solid: "#08090c"
  ink: "#e8edf7"
  ink-2: "#bcc0c9"
  ink-3: "#8d929d"
  line: "rgba(205, 210, 222, 0.12)"
  line-2: "rgba(205, 210, 222, 0.24)"
  signal: "#7fe3c0"
  signal-hi: "#b4f2dc"
  signal-dim: "rgba(127, 227, 192, 0.12)"
  signal-ink: "#03170f"
  absent: "rgba(200, 205, 216, 0.46)"
  stage-source: "#f5b556"
  stage-popular: "#ff7766"
  stage-derivative: "#71b7ff"
  stage-derived: "#c8a2ff"
typography:
  display:
    fontFamily: "Memoir Serif, Noto Serif SC, Source Han Serif SC, Songti SC, serif"
    fontSize: "clamp(34px, 4.2vw, 60px)"
    fontWeight: 500
    lineHeight: 1.22
    letterSpacing: "0.02em"
  headline:
    fontFamily: "Memoir Serif, Noto Serif SC, Source Han Serif SC, Songti SC, serif"
    fontSize: "clamp(34px, 3.6vw, 50px)"
    fontWeight: 500
    lineHeight: 1.25
    letterSpacing: "0.02em"
  title:
    fontFamily: "Memoir Serif, Noto Serif SC, Source Han Serif SC, Songti SC, serif"
    fontSize: "26px"
    fontWeight: 500
    lineHeight: 1.4
  title-sm:
    fontFamily: "Memoir Serif, Noto Serif SC, Source Han Serif SC, Songti SC, serif"
    fontSize: "21px"
    fontWeight: 500
    lineHeight: 1.3
  body:
    fontFamily: "Jost, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans SC, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.65
    fontFeature: "lnum, tnum"
  body-long:
    fontFamily: "Jost, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans SC, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.95
  label:
    fontFamily: "Jost, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans SC, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
  numeral:
    fontFamily: "Jost, Futura, Avenir Next, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    letterSpacing: "0.04em"
    fontFeature: "lnum, tnum"
  wordmark:
    fontFamily: "Jost, Futura, Avenir Next, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 500
    letterSpacing: "0.2em"
rounded:
  slot: "6px"
  control: "10px"
  panel: "12px"
  console: "14px"
  stage: "18px"
  pill: "999px"
spacing:
  gutter: "clamp(20px, 3.4vw, 56px)"
  measure: "1440px"
  page: "1240px"
  tight: "12px"
  row: "22px"
  panel: "26px"
  section: "36px"
  column: "48px"
components:
  button-primary:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.signal-ink}"
    rounded: "{rounded.control}"
    padding: "0 26px"
    height: "48px"
  button-primary-hover:
    backgroundColor: "{colors.signal-hi}"
    textColor: "{colors.signal-ink}"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.signal}"
    rounded: "{rounded.control}"
    padding: "10px 24px"
    height: "46px"
  button-outline-hover:
    backgroundColor: "{colors.signal-dim}"
    textColor: "{colors.signal-hi}"
  search-console:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.console}"
    height: "62px"
  field-input:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 14px"
    height: "48px"
  tab:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.pill}"
    padding: "7px 16px"
  tab-active:
    backgroundColor: "{colors.signal-dim}"
    textColor: "{colors.signal}"
    rounded: "{rounded.pill}"
    padding: "7px 16px"
  stage-chip-source:
    textColor: "{colors.stage-source}"
    rounded: "{rounded.pill}"
    padding: "3px 11px 3px 9px"
  stage-chip-popular:
    textColor: "{colors.stage-popular}"
    rounded: "{rounded.pill}"
    padding: "3px 11px 3px 9px"
  stage-chip-derivative:
    textColor: "{colors.stage-derivative}"
    rounded: "{rounded.pill}"
    padding: "3px 11px 3px 9px"
  stage-chip-derived:
    textColor: "{colors.stage-derived}"
    rounded: "{rounded.pill}"
    padding: "3px 11px 3px 9px"
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "26px"
  star-panel:
    backgroundColor: "{colors.panel-solid}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "22px 24px 40px"
    width: "440px"
  nav-link:
    textColor: "{colors.ink-2}"
    padding: "6px 0"
  nav-link-active:
    textColor: "{colors.ink}"
---

# Design System: Cyber Memoir

## Overview

**Creative North Star: "The Planetarium Show"**

The whole site is one night dome. A reader sits under a sky of colourless starlight, asks a question at a console on the horizon, and the dome turns to a meme's galaxy, where every lit star is a dated piece of evidence. The system refuses the encyclopedia page of cards and paragraphs: a meme is shown as a picture of time, not as an article.

Colour is scarce because colour carries meaning. The sky, its dust and every ornament are colourless; one mint projector light marks everything a reader can act on; the four role colours belong to evidence and to nothing else. A reader should tell ornament from evidence without a legend. Absence is drawn, never hidden: an empty stage is a dashed slot that says 无证据, an undated star is a dashed ring that says 无日期.

Density is low and instrument-like. Hairline rules, dotted rails and small tabular numerals do the structural work; a serif carries names and headings; motion is slow and sidereal and disappears entirely for readers who ask for less.

**Key Characteristics:**
- A near-black dome (sky-0) under every page, drawn once and turned by the compositor.
- One mint accent for controls; four role colours reserved for evidence.
- Noto Serif SC 500 for names and headings; Jost for numerals, dates and the wordmark.
- Hairline instruments: 1px rules at 12% and 24% white, dotted and dashed rails.
- Position comes from date only; decoration is seeded by meme id and never reshuffles.
- Absence drawn as dashed outlines, never tinted.

## Colors

A colourless night sky, one mint projector light, and four evidence colours that nothing else may borrow.

### Primary
- **Projector Mint** (signal): the one accent. Primary buttons, links, active tabs, the focus ring, the caret, the projector pointer and beam on the ecliptic, the time cursor and sweep, the active-star selection ring. If a reader can act on it or it is the projector pointing, it is mint.
- **Projector Mint, Bright** (signal-hi): hover state of every mint control and link.
- **Projector Mint, Veil** (signal-dim): fill behind active tabs, outline-button hover, the load-more hover. Always a wash, never a surface colour.
- **Console Ink** (signal-ink): text on a solid mint button. Nowhere else.

### Tertiary (evidence only)
- **Source Amber** (stage-source): stars whose role is 素材来源, drawn as diamonds.
- **Popular Coral** (stage-popular): stars whose role is 走红作品, drawn as squares.
- **Derivative Blue** (stage-derivative): derivative videos (衍生视频), drawn as small dots; also the dated event dots on the meme page's timeline, which are derivative videos.
- **Derived Violet** (stage-derived): derived memes (衍生梗), drawn as rings; also the dashed link between two galaxies when one meme derives from another.

### Neutral
- **Dome Black** (sky-0): the page, the html background, the theme colour. The whole site sits on it.
- **Night 1-3** (sky-1, sky-2, sky-3): quiet steps above the dome; sky-3 is the scrollbar thumb.
- **Instrument Glass** (panel) and **Instrument Glass, Solid** (panel-solid): panel surfaces over the sky, with a 6px backdrop blur on the translucent one.
- **Starlight Ink** (ink): primary text and star labels. Pure #fff is kept for the white-hot core of each evidence star and the lit second line of the dome headline.
- **Dim Ink** (ink-2): secondary text, nav links, definitions.
- **Faint Ink** (ink-3): metadata, dates on the map, placeholders, captions.
- **Hairline** (line) and **Hairline, Strong** (line-2): every rule, panel border and divider.
- **Absence Grey** (absent): the dashed outline of anything missing: empty stage slots, undated star rings, the abstained answer, the abstained console.

### Named Rules
**The Evidence Owns Colour Rule.** The four stage colours appear only on evidence: stars, stage chips, milestone slots, the legend that explains them, and relations between memes. Decoration stays colourless (warm or cool white, never above about 15% saturation), and chrome never borrows a stage hue.

**The One Projector Rule.** Mint marks controls and the projector's own output (its pointer, beam, cursor and the heading of the console's answer), and nothing else. Mint is never used for evidence, for decoration or for a page or section heading.

**The Drawn Absence Rule.** Missing things are outlined in dashed Absence Grey and left empty inside. Never fill, tint or colour an absence, and never draw a present, dated thing in Absence Grey dashes.

## Typography

**Display Font:** Memoir Serif, a self-hosted Noto Serif SC at weight 500 split into two unicode-range slices (with Source Han Serif SC, Songti SC, serif)
**Body Font:** Jost for Latin with PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans SC for Chinese
**Label/Mono Font:** Jost (with Futura, Avenir Next, Segoe UI) for numerals, dates and the wordmark; ui-monospace only for raw ids on curator pages

**Character:** A calm book serif names every meme and heading, like the engraved labels on a star atlas; a geometric Futura revival sets the numbers, so dates read as instrument readouts. All numerals are lining and tabular.

### Hierarchy
- **Display** (500, clamp(34px, 4.2vw, 60px), 1.22): the dome headline on the home page, two lines, the first in Dim Ink and the second in white with a faint starlight glow.
- **Headline** (500, clamp(34px, 3.6vw, 50px), 1.25): page titles on inner pages.
- **Title** (500, 24-28px, 1.4): section titles, meme names in the index (28px), the star panel title (25px), the current galaxy name in the breadcrumb (24px).
- **Title, small** (500, 20-22px, 1.3): panel headings, the sky caption's meme name, the milestone rail heading.
- **Body** (400, 16px, 1.65): all running text. Definitions and answers cap at 68ch and open to 1.85-1.9 leading.
- **Body, long** (400, 18px, 1.95): the meme page's definition, capped at 66ch.
- **Label** (400, 12.5-13.5px): metadata, row meta, legend notes, field hints, in Faint Ink.
- **Numeral** (Jost 400, 12.5-13.5px, 0.04em): every date and count, on the map, the rail and the lists.
- **Wordmark** (Jost 500, 15px, 0.2em, uppercase): CYBER MEMOIR in the header, and only there.

### Named Rules
**The Serif Names Things Rule.** A meme's name, a page title, a section heading or a star label is set in the serif. Numbers, dates and controls are not.

**The Legible Map Rule.** Text drawn inside a scalable map is sized as calc(Npx * var(--label-scale)), where the explorer measures how far the SVG has shrunk and sets the scale to at least 1, so map text stays at about 11px or more on screen. The meme page's still thumbnail uses a fixed scale of 1.5 and hides its labels entirely, because the time rail below it names every star.

**The Single Weight Rule.** The display face ships at 500 only. Headings do not ask for bold; hierarchy comes from size and ink level.

## Layout

The home page is a dome: a full-viewport section (min(100svh - 72px, 1020px)) whose upper half is the ecliptic, every published meme as a small spiral galaxy on a dotted arc ordered by date, and whose lower half is the horizon, a faint curved rim below which the headline and a full-width search console sit. Below the dome, the index runs as a 2.2fr / 1fr grid (the result panel and a short principles column).

Content sits in a 1440px measure with a fluid gutter (clamp(20px, 3.4vw, 56px)); inner pages use a 1240px measure, and the star map widens to 1500px. The spacing rhythm is observed rather than scaled: 12px between sibling controls, 22px between rows and grid columns, 26px panel padding, 36px between sections, 48px between the two columns of a detail or form page.

Geometry of the maps is product truth. On the universe level a galaxy's x is its date on a horizontal axis; quiet gaps over 21 days are compressed into dashed bands that carry their true length. Inside a galaxy, radius is time (earlier nearer the core) and the spiral arm fixes only the angle, itself a function of t. Stage never decides where anything sits.

Two breakpoints: 1050px narrows the grids; 760px collapses every grid to one column, unsticks the header, turns the milestone rail into two columns, and lets the star map scroll sideways at a fixed minimum width (1100px universe, 740px galaxy) with a swipe hint, rather than shrinking it past legibility. The star panel docks to the bottom on phones.

### Named Rules
**The Date Is The Position Rule.** A star's or galaxy's place is computed only from its date. Colour, shape and size may say what it is; nothing about its role may move it.

**The Time Is Always Drawn Rule.** Every time picture carries its direction: 时间 → on the universe axis, 早 → 晚 radially in a galaxy, 晚 → on the meme page's rail.

## Elevation & Depth

Depth is light, not lift. The world is a dark room, so things come forward by glowing: evidence stars carry a radial glow in their role colour and a drop-shadow on their white core, the projector pointer and time cursor carry a mint drop-shadow, the nav's current-page dot glows. Surfaces over the sky are translucent instrument glass with a hairline border and a light backdrop blur; the few true shadows are long, soft and black, and only sit under things that float over the dome (the console, the sky caption, the star panel). There are no hard or offset shadows.

### Shadow Vocabulary
- **Floating instrument** (`box-shadow: 0 24px 60px -30px rgba(0, 0, 0, 0.9)`): the search console at rest.
- **Console focus** (`box-shadow: 0 0 0 4px rgba(127, 227, 192, 0.08), 0 24px 60px -30px rgba(0, 0, 0, 0.9)`): the console while the reader types.
- **Field focus** (`box-shadow: 0 0 0 4px rgba(127, 227, 192, 0.09)`): form fields on focus, with the border turning to 60% mint.
- **Caption** (`box-shadow: 0 18px 40px -18px rgba(0, 0, 0, 0.9)`): the sky caption under the projector beam.
- **Side panel** (`box-shadow: -24px 0 60px -20px rgba(0, 0, 0, 0.9)`): the star panel sliding in from the dome's edge.
- **Projector glow** (`filter: drop-shadow(0 0 6px rgba(127, 227, 192, 0.85))`): the pointer, the time sweep and the time cursor knob.

### Named Rules
**The Glow Means Light Rule.** A glow says something is lit: evidence, the projector, the current page. It is never used as decoration on a panel or a heading.

## Shapes

Soft instrument corners and hairlines. Controls round at 10px, panels at 12px, the search console at 14px, the star-map stage at 18px; tabs and stage chips are full pills; empty stage slots and list rows use 6px. Borders are always 1px hairlines.

The map has its own shape vocabulary and it is reserved. The four stages each own a shape as well as a colour, so the stage survives a colour-blind reader and a greyscale print: source is a diamond, popularized_by a square, a derivative video a small dot, a derived meme a ring. Milestones (the first star of each stage) carry diffraction spikes and a faint halo. Instruments use dotted and dashed hairlines: the ecliptic, the arm rails, the tick rings, the projector beam, the time cursor. Galaxies on the dome are canvas-painted two-armed spirals of colourless dust, their shape and tilt seeded by meme id.

### Named Rules
**The Reserved Glyph Rule.** Diamond, square, dot and ring in a stage colour mean evidence; diffraction spikes mean a milestone and appear nowhere else except the legend explaining them. Decoration never takes these shapes.

**The Seeded Sky Rule.** Every decorative element that belongs to a meme (its galaxy art, its dust, its motes) is generated from a seed hashed from the meme id, and the dome itself from a fixed seed, so the picture is identical on every load.

## Components

### Buttons
Mint, quiet and exact: the projector's own buttons.
- **Shape:** gently rounded (10px), minimum 46-48px tall.
- **Primary:** solid mint with Console Ink text, weight 600, 0.08em tracking. Used for the console's 搜索记忆 and the few form submits.
- **Hover / Focus:** hover lifts to bright mint; press scales to 0.97; focus is the global 2px mint outline at 3px offset.
- **Outline:** transparent with a 50% mint hairline and mint text; hover fills with the mint veil. Small variant 38px tall, 14.5px text. Used for 列表视图 and 重置视图 on the map.
- **Text button:** mint, underlined at 4px offset, for breadcrumbs and inline retries.
- **Danger and errors carry no hue.** Retract actions, the error box and the error console border use a 2px near-white outline (rgba(240,242,247,0.55–0.7)) with ink text. Every warm colour on this site is a role colour, so a red error beside a coral 走红作品 star would read as evidence; the heavier outline and the words carry the warning instead. (Fixed after the first DESIGN.md pass flagged the old coral as a violation of the Evidence Owns Colour Rule.)

### Chips
- **Stage chip:** a pill with a 1px border and text in the stage colour, led by a 6px glowing dot of the same colour. Only ever labels a role.
- **Tabs:** a pill track (hairline border, dark glass) of pill buttons; the active tab gets the mint veil, mint text and a 35% mint inset hairline.

### Cards / Containers
- **Corner Style:** 12px.
- **Background:** Instrument Glass with a 6px backdrop blur.
- **Shadow Strategy:** none at rest; see Elevation for the three floating exceptions.
- **Border:** 1px Hairline.
- **Internal Padding:** 26px, 18px on phones.
- On the meme page, evidence is a list read top to bottom: the glass box is dropped for a top hairline and 18px of vertical padding.

### Inputs / Fields
- **Style:** 1px Hairline, Strong border, 10px radius, glass fill, 48px tall, 16px text, Faint Ink placeholders.
- **Focus:** border turns to 60% mint with a 4px mint halo; the native outline is suppressed.
- **Search console states:** searching draws a mint scan line travelling along the console's bottom edge; abstained turns the border to dashed Absence Grey; error turns it to a 2px near-white outline.

### Navigation
- **Style:** Dim Ink links at 15px with 3vw gaps in a 72px sticky header of dark glass (backdrop blur 10px) over a Hairline bottom rule.
- **Active / hover:** the current page turns to Starlight Ink and a 4px glowing mint dot rises beneath it; hover shows the same dot.
- **Mobile:** below 760px the header unsticks and the links wrap to their own row, scrolling sideways if needed.

### Evidence Star (signature)
A white-hot core inside a glow in the role's colour, circled by the role's thin catalogue mark (diamond, square, dot or ring), always present. Milestones grow by 1.35x and add diffraction spikes and a halo, and their glow pulses slowly. Undated stars draw their mark dashed. Hover and focus brighten the glow and thicken the mark; keyboard focus turns the mark mint; the selected star wears a slowly turning dashed mint ring. Stars are SVG groups with role="button", a tab stop and an aria-label naming role, title and date; they ignite in the order they happened.

### Milestone Rail (signature)
Four slots in model order (source, popularized_by, derivative, derived meme), each led by a glowing dot in its stage colour, with the first star's title and date. A stage with no evidence keeps its slot: the dot becomes a dashed Absence Grey circle and the slot holds a dashed 无证据 box. The rail's heading notes it is ordered by stage, not by time.

### Sky Band and Caption (signature)
The home page's ecliptic: canvas-painted galaxies on a dotted arc, dated at both ends, with a mint projector pointer bobbing above the focused one and a dotted mint beam down to a glass caption card (name in the serif, meta, a two-line definition, a mint 进入星系 → link). Galaxies ignite one after another on load.

### Star Panel
A 440px glass drawer that slides in from the right edge of the dome (from the bottom on phones) holding the star's title, meta, stage chip, and its evidence as quoted OCR in hairline-ruled blockquotes.

## Do's and Don'ts

### Do:
- **Do** put the dome (sky-0 under the fixed night sky) behind every page; the site is one world.
- **Do** compute every star's and galaxy's position from its date alone: x by date on the universe axis, radius by date in a galaxy, the arm angle as a function of t.
- **Do** reserve the four stage colours, the four stage shapes and diffraction spikes for evidence; milestones alone carry spikes.
- **Do** mark every control, and only controls and the projector, with mint (#7fe3c0); hover goes to bright mint (#b4f2dc).
- **Do** draw a missing stage as a dashed 无证据 slot and an undated star as a dashed ring, in Absence Grey, empty inside.
- **Do** draw the direction of time on every time picture (时间 →, 早 → 晚).
- **Do** size map text as calc(Npx * var(--label-scale)) so it stays about 11px or more however far the SVG shrinks.
- **Do** seed decoration from the meme id (and the dome from its fixed seed) so nothing reshuffles between loads.
- **Do** remove every decorative loop (sidereal rotation, twinkles, meteors, dust drift, time sweep, pulses, the flight transition) under prefers-reduced-motion, keeping state readable through colour, opacity and the dashed/solid vocabulary.
- **Do** set names and headings in the serif at 500 and every date and count in Jost with tabular numerals.

### Don't:
- **Don't** let a stage decide where a star sits, or sort a galaxy's stars by stage.
- **Don't** give decoration a hue: dust, motes, twinkles, meteors and the Milky Way stay warm or cool white, small and not interactive.
- **Don't** tint, fill or colour an absence, and don't hide an empty stage to tidy a galaxy.
- **Don't** use mint on evidence, ornament or page and section headings, or a stage colour on chrome.
- **Don't** shrink map labels below legibility to fit a phone; let the map scroll sideways at its minimum width instead.
- **Don't** add hard or offset shadows, or glows on panels and headings; depth in this world is light.
- **Don't** add eyebrow or kicker labels above headings, or letter-spaced uppercase Latin outside the wordmark.
- **Don't** display a UTC instant; dates are shown in Beijing time as the API sends them.
