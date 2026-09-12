# Redesign assets — 12 September 2026

## Typography

Inter's upright variable web font is bundled locally for the redesigned Hantek
Studio interface. The official stylesheet identifies its weight range as
100–900. The app must reference the bundled file; it must not load the remote
stylesheet or request a font from the network at runtime.

| Local asset | Purpose | Bytes | SHA-256 |
| --- | --- | --- | --- |
| `desktop/renderer/assets/fonts/InterVariable.woff2` | Upright Inter variable font | 352240 | `693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3` |
| `desktop/renderer/assets/fonts/Inter-LICENSE.txt` | Unmodified upstream license and copyright notice | 4380 | `262481e844521b326f5ecd053e59b98c8b2da78c8ee1bdbb6e8174305e54935a` |

Sources downloaded on 12 September 2026:

- [Official Inter project](https://rsms.me/inter/).
- [Official stylesheet](https://rsms.me/inter/inter.css), whose variable-font URL
  uses the `v=4.1` distribution parameter and declares normal style, weights 100–900.
- [Original WOFF2 asset](https://rsms.me/inter/font-files/InterVariable.woff2?v=4.1),
  copied without modification, conversion or subsetting.
- [Original license](https://raw.githubusercontent.com/rsms/inter/353b61b9f4430d5f420d56605a6e7993e0941470/LICENSE.txt),
  pinned to the official `rsms/inter` repository commit
  `353b61b9f4430d5f420d56605a6e7993e0941470`.

Inter is distributed under the **SIL Open Font License 1.1**. The complete
upstream license, including its copyright notice, accompanies the font. Preserve
that file in distributed app builds as well as in source. A local font URL in
CSS causes Vite to include the font; an unreferenced license text file requires
an explicit build/resource copy. The font is not installed into Windows.

The renderer integration should declare normal style, the 100–900 weight range,
and a local WOFF2 source. No italic file is included. Numeric instrument values
can use tabular figures where alignment is helpful.

Validation completed:

- The WOFF2 signature, declared file length, TrueType flavor, table count,
  compressed-size bounds and optional metadata/private-data bounds were checked.
  The file contains 19 tables and declares 882104 decompressed SFNT bytes.
- A headless Chromium font-loading check read only the local bytes, with page
  network requests blocked. `FontFace.load()` succeeded and the font was ready
  at weights 100, 400, 500, 600, 700 and 900 for interface text including
  `1.32 V`, `800 µs` and `Ω`.
- The license is valid UTF-8 and contains the upstream copyright notice and
  SIL Open Font License 1.1 text. The hashes above cover the exact saved files.

## Icons

The existing `lucide-react` dependency is retained intentionally. Its thin
outline icons suit the instrument interface and keep the redesigned controls
visually consistent. This asset task adds no icon package, substitutes no
emoji, and makes no package or renderer-code changes. Existing icon attribution
and dependency licensing remain applicable.
