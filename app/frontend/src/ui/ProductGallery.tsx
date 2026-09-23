/**
 * The product image.
 *
 * One `<img>` whose `src` is derived from the current selection -- there is no image
 * state to synchronise, so switching colour and size cannot leave a stale picture
 * behind. The `alt` prop is built from the selection by the page, not here.
 */

export interface ProductGalleryProps {
  readonly imageUrl: string;
  readonly alt: string;
}

export function ProductGallery({ imageUrl, alt }: ProductGalleryProps) {
  return (
    <figure className="gallery">
      <img className="gallery__image" src={imageUrl} alt={alt} width={480} height={576} />
    </figure>
  );
}
