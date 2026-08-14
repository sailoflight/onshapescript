# Visual review

## Reference interpretation

The source is a low-resolution single-view product image. The model preserves its visual vocabulary while following the written constraints over ambiguous pixels:

- low black cylindrical pedestal;
- dense upward spray of black and amber/yellow cables;
- multiple brass/brown root and terminal collars;
- 17 small warm-white rectangular terminal blocks;
- blank white front plaque;
- no blue ring, backlight, rear plate, or second top disk.

## Required views

- `outputs/previews/reference_like.png` — primary 3/4 front/top review.
- `outputs/previews/iso.png` — alternate shape and depth review.
- `outputs/previews/front.png` — symmetry and terminal-height review.
- `outputs/previews/top.png` — S rows and perpendicular terminal fan review.
- `outputs/previews/right.png` — depth and plaque/root relationship.

## Review criteria

1. The lower cable field should form a dense intertwined cluster before opening into the fan.
2. Terminals should remain individually legible and vary in orientation.
3. Yellow and black strands should remain separately visible.
4. The base must remain a single standard cylinder with only its upper/lower circular edges rounded.
5. The plaque must be blank and visually embedded at the -Y front.
6. Root arrangement should read primarily along Y; terminal fan primarily along X.
7. No prohibited blue ring or second top disk may appear.

## Known visual differences

- The reference's blue circular ring is intentionally omitted.
- Exact cable weave and hidden geometry cannot be inferred from one image.
- Onshape shaded-view lighting differs from the source render.
- The parametric model favors robust smooth sweeps over pixel-matched cable kinks.
