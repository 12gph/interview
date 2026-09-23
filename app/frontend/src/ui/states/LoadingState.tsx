/**
 * First-load skeleton.
 *
 * A skeleton rather than a spinner because the page has a known shape: showing where
 * the image and the price will appear makes the wait feel shorter and stops the layout
 * from jumping when the data lands. `aria-busy` tells assistive technology the region
 * is still filling in.
 */

export function LoadingState() {
  return (
    <div className="state state--loading" aria-busy="true">
      <div className="state__skeleton" aria-hidden="true">
        <div className="skeleton skeleton--image" />
        <div className="skeleton__stack">
          <div className="skeleton skeleton--title" />
          <div className="skeleton skeleton--line" />
          <div className="skeleton skeleton--line skeleton--short" />
          <div className="skeleton skeleton--price" />
        </div>
      </div>
      <p className="state__text">Loading product…</p>
    </div>
  );
}
