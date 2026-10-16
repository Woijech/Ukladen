# Ukladen brand exports

Approved direction: A1, combining calendar day tiles, a note card and the U initial.

- `ukladen-avatar.png`: square symbol-only image on a light background, with padding for circular email avatars.
- `ukladen-logo.png`: the symbol above the Ukladen wordmark, on a light background.

These are raster PNG exports, not SVG masters. Keep these source exports for
downloads and future product branding. The frontend uses byte-identical copies in
`apps/web/src/shared/assets/`, inside its Docker build context. Update both copies
when replacing an approved export.

Use `Brand` from `apps/web/src/shared/brand.tsx` for compact product identity: the
approved symbol with an accessible text wordmark. It is used on the home,
sign-in/registration, email-verification, password-reset, group-selection and calendar
navigation surfaces. The full image appears in the desktop sign-in illustration.
Root metadata supplies the symbol as the browser and Apple touch icon.
Static image imports use Next.js image optimization; the existing standalone
static-asset copy includes the originals for both native and Docker builds.

Use the approved identity by default for future product branding. External account
avatars are not changed by the application; use `ukladen-avatar.png` for manual setup.
Generation used the built-in image_gen tool with the approved A1 image as the edit target.
The transparent experiment was rejected because of edge artifacts and is not included.

## Integration verification — 2026-10-16

- Frontend lint, typecheck, production build and all 56 existing browser tests passed.
- Base and home Compose configuration validation passed.
- Source/frontend PNG copies were checked for byte equality. The standalone server
  returned the exact symbol PNG for the metadata icon and a successful optimized
  image response for the compact logo.
- Desktop/mobile sign-in, desktop calendar and mobile group-selection placements
  were visually inspected. API fixtures were used for the calendar/group preview.
- No backend changes, external avatar updates, push or deployment were performed.

## Final generation prompts

### Avatar

Use case: logo-brand / precise-object-edit. Input image is the APPROVED Ukladen A1 logo and is the EDIT TARGET. Produce a finished export of this exact approved design, not a new creative variation. Preserve the seven rounded-square tiles forming a U, the exact muted lavender and dark-plum palette, the small calendar on the upper-left tile with two dark binding tabs and a white separator, and the tilted dark upper-right note card with two light text strokes and its light folded-corner detail. Preserve all proportions, corner radii, tilt angle and spacing within the symbol. Clean uniform flat colors, smooth crisp edges, no texture, gradient, shadows, mockup or embellishments. Remove the small "A1" option label completely. No badges, border, watermark or extra decoration.
Export: square email profile avatar. REMOVE the entire "Ukladen" wordmark so there is absolutely no text anywhere. Keep ONLY the approved U-shaped calendar-and-note symbol, centered optically on a perfectly solid warm-white background #FCFBFE. Scale the symbol to about 64% of canvas width and height, leaving balanced generous clear padding on all four sides so every shape fits safely within a centered circular avatar crop. Do not draw the circular crop or a surrounding tile. The symbol should be larger than in the reference after removing the wordmark, but remain fully contained in a centered circular safe area.

### Logo with wordmark

Use case: precise-object-edit / logo-brand. The reference image is the APPROVED Ukladen A1 logo and the edit target. Make the final clean logo export by REMOVING ONLY the little "A1" label at the top left. Keep the existing logo symbol AND exact "Ukladen" wordmark, their relative size, tile shapes, arrangement, spacing, rounded corners, symbol details, colors and typeface exactly the same. The symbol is seven lavender tiles in a U, with the upper-left tile a small calendar with two dark binding tabs and a white separator and the upper-right dark tilted tile a note with two white lines and white folded corner. Preserve this precise original design. Replace all the background with a perfectly uniform solid white #FFFFFF. Crisp clean edges, no gradients, no texture, no colored fringe, no glow, no shadow, no checkerboard, no mockup. Do not redesign, stretch or simplify any shapes or letters. Recenter the overall approved symbol-plus-wordmark group vertically after removing the corner label, leaving balanced clear margins. Only text: "Ukladen", spelled U-k-l-a-d-e-n.
