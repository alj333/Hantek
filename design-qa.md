# Hantek Studio 0.3 design QA

Final result: passed — 12 September 2026.

## Target and evidence

The user requested an ImageGen reimagination implemented in the existing standalone
React/Electron app. The selected [ImageGen concept](docs/design/2026-09-12/workspace-concept.png)
was generated from the previous demo workspace, using this [saved prompt](docs/design/2026-09-12/prompt.md).
The [implemented workspace](docs/design/2026-09-12/implemented-workspace.png) and
[implemented controls](docs/design/2026-09-12/implemented-controls.png) are actual
screenshots from packaged 0.3.0 running with isolated synthetic demo records.

The concept and final workspace screenshot were opened together in one comparison
input at exactly 1505 × 1045 pixels: demo connected, two saved records, an unsaved
preview, automatic refresh off, transient notice dismissed. The generated concept's
fictional instrument display is a visual reference only; it is never shipped as a
measurement or substituted for a captured screen.

## Findings and corrections

| Finding | Impact | Resolution |
| --- | --- | --- |
| Initial 210px sidebar and full-height preview drifted from the concept's proportions. | P2: recent activity fell entirely below the workspace view. | Matched the 264px sidebar at reference width, bounded preview height and moved activity into the left grid column beneath the screen. Reopened the final reference and implementation together. |
| Empty hardware catalog could show a green verified badge. | P2: unavailable controls could imply validation. | Neutral unavailable badge and information icon; added a mocked empty-catalog regression. |
| Existing banner assertion expected the previous copy. | Test maintenance, not a product defect. | Assertion now checks explicit DEMO MODE and simulated/no-USB wording; retains the source distinction. |
| New test initially assumed every control label was unique and ignored fractional Windows DPI. | Test maintenance, not a product defect. | Assert unique catalog IDs and accessible names separately. Exact reference capture uses CSS pixels; existing native suites retain 150% Windows scaling. |

No unresolved P0, P1 or P2 issue was found in the final visual and functional review.

## Comparison review

- **Layout and density:** the main screen, three right-side utility sections,
  sidebar connection block and recent activity follow the selected composition.
  Cards use 5–7px corners and restrained borders. Real status text adds some vertical
  height compared with the illustration; normal page scrolling remains available.
- **Typography:** bundled Inter variable font loads in the packaged sandbox with
  no network request. Heading, body, label and numeric hierarchy are consistent.
  Descriptive copy wraps; paths and capture titles truncate deliberately, with full
  records available in the library. The 264px sidebar shrinks on compact windows.
- **Color and icons:** graphite surfaces, amber primary actions and yellow/cyan
  channel cues match the concept. Existing Lucide outline icons were selected for
  the reference's thin line style. Secondary text contrast on panels exceeds 4.9:1;
  channel and source labels exceed 8:1. Focus uses a visible amber outline.
- **Image fidelity:** scope images remain original 800 × 480 PNGs using contain,
  preserving all four edges and aspect ratio. No generated waveform image, image
  filter, stretch, crop, fabricated measurement or custom decorative SVG was added.
  The old decorative empty-screen graticule and capture-tip illustration were removed.
- **Copy and behavior:** all four views work. Direct preview refresh produces an
  unsaved image and stops automatic refresh. Open controls navigates to the front
  panel. Recent capture opens the actual newest saved record. Existing acquisition,
  capture notes, search, filtering, settings, folder and export actions remain wired.
- **States:** disconnected, busy, fresh, stale, previous image, simulated source,
  request uncertainty, failure and empty-catalog states remain distinct. Errors
  never mark an old image current. Relative actions never claim an absolute setting.
- **Accessibility and viewport resilience:** native buttons and labelled inputs
  remain keyboard accessible, including all 39 catalog controls. Visible source
  labels accompany color. Reduced-motion preference is respected. At 980 × 680
  outer window size, all screen edges and F1–F5 remain visible; the control deck
  scrolls internally, and other views scroll vertically without horizontal overflow.

Desktop window sizes were 1440 × 1000 and the actual 980 × 680 minimum; the exact
reference comparison used 1505 × 1045 client pixels. This is a Windows desktop
application with an enforced minimum size, not a mobile website.

## Validation

- Python: 98 tests passed, including the AI settings/setup workflow.
- Desktop backend: 41 tests passed.
- TypeScript and Vite production build passed.
- Windows portable packaging and frozen Python bridge self-test passed.
- Packaged app UI: 16 redesign + 14 smoke + 10 controls + 7 preview/error checks
  passed (47 total, including the test-only mocked failure window).
- Inter font and license are included in the package. Renderer sandbox, context
  isolation, fixed IPC boundaries and blocked external network access are retained.
- Git diff and ignored build/capture/vendor artifact coverage checked.

Final local evidence: `.local/desktop-redesign-ui-tests/86440926-13f4-48a5-9dcc-4f3ac2c23327/`;
smoke `desktop-ui-tests/05270049-daea-4524-9c95-7ad7da8759ee`;
controls `desktop-controls-ui-tests/3d32d097-62fd-4447-903a-1e450fedb810`;
failure checks `desktop-preview-ui-tests/f2ebd1bb-4aef-40ce-88cb-9dc3353369eb`
(the latter three are also under `.local/`).

All validation in this increment was offline/demo. It makes no new claim about
hardware response, measurement accuracy or resolution of intermittent USB checksum
failures. The original user profile and two saved captures were retained when the
new portable application was opened, disconnected with automatic refresh off.
