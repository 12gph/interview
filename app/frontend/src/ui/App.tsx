/**
 * Application shell.
 *
 * Takes the client as a prop rather than importing a singleton, so tests can hand in a
 * stub and never touch the network.
 */

import type { ApiClient } from "../api/client";
import { ProductPage } from "./ProductPage";

export interface AppProps {
  readonly client: ApiClient;
  readonly productId: string;
}

export function App({ client, productId }: AppProps) {
  return (
    <div className="app">
      <header className="app__header">
        <span className="app__brand">Aurora</span>
      </header>
      <main className="app__main">
        <ProductPage client={client} productId={productId} />
      </main>
    </div>
  );
}
