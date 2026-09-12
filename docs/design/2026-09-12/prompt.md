# Hantek Studio redesign prompt

Generated with the built-in ImageGen tool. The existing demo workspace screenshot was supplied as a visual reference. Selected result: `workspace-concept.png`.

```text
Create a polished, implementable desktop UI redesign for Hantek Studio, a real Windows app controlling a Hantek DSO5102P oscilloscope over USB. Use the attached existing app screenshot to understand its actual features and content. Reimagine the interface completely; do not retain the cream/green visual theme.

Output ONE flat front-facing full app window UI mockup, approximately 1440 by 1000, landscape 3:2. No laptop, device frame, perspective, hands or surrounding scene.

Art direction: precision laboratory instrument, beautifully restrained dark graphite and deep charcoal surfaces, warm off-white typography, muted grey secondary text, warm amber primary action, signal yellow CH1 and cool cyan CH2. Hairline low-contrast borders, modest 6-10px corner radii. Inter or similarly crisp sans-serif UI typography, tabular numerals, strong hierarchy, generous deliberate spacing. Thin outline icons. No gradients, neon glow, glass effects, marketing hero, fictional AI chat or ornamental graphs.

Layout: 210px left sidebar with small amber waveform mark, Hantek Studio branding, tiny INSTRUMENT WORKSPACE descriptor; primary nav Workspace (active amber subtle fill), Controls, Captures, Settings. Bottom sidebar instrument connection card with DSO5102P, clearly marked DEMO source, Disconnect action and small local workspace footer. 60px top application bar: Your bench / Workspace at left and quiet Local storage + DEMO status at right.
Main content has heading Scope workspace, small subtitle Live screen capture and instrument control, and View captures button.
An unmistakable slim DEMO MODE banner says Simulated scope. No USB device commands are sent.
Main grid: dominant instrument panel, and a narrow right utility column. Instrument panel header DSO5102P with screen preview subtitle and DEMO pill. A clearly legible toolbar: amber Save capture, outlined Run and Stop, subtle Refresh preview icon and Auto-refresh toggle. Under this: a large black instrument screen showing a plausible captured oscilloscope display, fine graticule, one yellow CH1 sine wave and cyan CH2 sine wave. Label the actual screen DEMO. Keep this captured image visually distinct as an image, without invented data analytics around it. Under the screen: Preview only • Not saved, timestamp, and discreet export/folder actions. Preserve generous black space around the captured screen as required to display every edge without cropping.
Right column: Session overview with Connection Demo connected, Latest capture timestamp, Screen size 800 × 480, Saved captures 2, and storage location link. Under this an Instrument controls card with Channel / Timebase / Trigger labels and a real Open controls button leading to the existing front panel. Below, a compact recent-capture entry can be shown.
Below main grid: compact Recent activity list with two or three realistic demo actions and times. Quiet bottom app footer.
Important: retain real desktop workflow; controls are relative front-panel actions, never imply numeric settings readback in this UI. No fake telemetry, measurements, current numeric scope setup inputs, cloud status, or unimplemented features. Use clear labels, excellent readability and visually complete, uncropped content. The mockup is the visual source for immediate implementation in the existing React/Electron app.
```
