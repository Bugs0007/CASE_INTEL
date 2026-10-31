# Asset Descriptions

One line per file. Read this instead of opening every image individually.

To find a specific brand or icon, **grep this file for the brand name in the description text** (e.g. `grep -i 'autodesk' asset-descriptions.md`). The Gemini Vision captions identify what's actually in each file — that's the agent's selector.

The `logo-<hash>.svg` filename prefix is a cheap structural hint (DOM said this SVG was inside a `<header>`, home-link `<a>`, or had an aria-label matching the page brand). It is NOT a content claim — many `logo-*` files are nav icons or decorative shapes. Trust the captions, not the filename prefix.

- svgs/svg-20426c70.svg — svg 20426c70
- svgs/svg-4772bfca.svg — svg 4772bfca
- svgs/svg-ad7ce798-2.svg — svg ad7ce798 2
- svgs/svg-ad7ce798.svg — svg ad7ce798
- svgs/svg-f99cc00c.svg — svg f99cc00c
