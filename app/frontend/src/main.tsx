/**
 * Browser entry point.
 *
 * The only place that constructs a real API client and a real DOM root; everything
 * below it receives its dependencies, which is what keeps the components testable
 * without a server.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { createApiClient } from "./api/client";
import { App } from "./ui/App";
import "./styles.css";

const PRODUCT_ID = "aurora-tee";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("Expected an element with id 'root' in index.html.");
}

createRoot(container).render(
  <StrictMode>
    <App client={createApiClient()} productId={PRODUCT_ID} />
  </StrictMode>,
);
