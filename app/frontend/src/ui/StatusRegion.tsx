/**
 * The page's live region.
 *
 * Both containers are rendered for the whole lifetime of the page and only their text
 * changes. A live region inserted at the same moment as its content is frequently not
 * announced at all, so mounting them conditionally would defeat the purpose.
 *
 * The split is deliberate: success and informational notices are polite, so they wait
 * for the screen reader to finish; failures interrupt, because they change what the
 * shopper has to do next.
 */

export type FeedbackTone = "success" | "info" | "error";

export interface StatusRegionProps {
  readonly message: string | null;
  readonly tone: FeedbackTone;
}

export function StatusRegion({ message, tone }: StatusRegionProps) {
  const text = message ?? "";
  const isError = tone === "error";

  return (
    <>
      <div
        className={[
          "status",
          "status--polite",
          isError ? "" : `status--${tone}`,
          !isError && text !== "" ? "status--visible" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        role="status"
        aria-live="polite"
      >
        {isError ? "" : text}
      </div>
      <div
        className={["status", "status--assertive", isError && text !== "" ? "status--visible status--error" : ""]
          .filter(Boolean)
          .join(" ")}
        role="alert"
        aria-live="assertive"
      >
        {isError ? text : ""}
      </div>
    </>
  );
}
