# README screenshots — 16 September 2026

The owner requested screenshots of the Hantek application in its GitHub README.
Added the scope workspace, front-panel controls and capture library from the
packaged Hantek Studio 0.3.0 app. The README explicitly labels Demo mode and
simulated signals, and uses relative image paths for GitHub and local checkouts.
Screenshot provenance and refresh instructions are in `docs/screenshots/README.md`.

The packaged redesign UI suite passed all 16 checks in an isolated demo profile.
A separate isolated demo session captured the three full-page documentation
images, with a named simulated capture and notes. Both sessions completed with
zero renderer errors and no USB access. No acquisition or settings changes were
sent to either physical scope, and the regular application profiles were unused.

All three published images were visually inspected, and source hashes, PNG
structure, README links and the documentation diff were checked. The change is
limited to README text, screenshots and supporting notes; app code and build
outputs are unchanged. Generated profiles and original evidence remain ignored
under `.local/`.
