/**
 * The wire format: exactly what the API sends.
 *
 * snake_case, and confined to this module plus `client.ts`. Everything downstream uses
 * the camelCase domain models from `domain/types.ts`, so a rename on either side of the
 * boundary stays a one-file change.
 */

export interface WireOptionValue {
  value: string;
  label: string;
  swatch: string | null;
}

export interface WireOptionDimension {
  key: string;
  label: string;
  values: WireOptionValue[];
}

export interface WireSku {
  id: string;
  options: Record<string, string>;
  price_minor: number;
  currency: string;
  available_quantity: number;
  in_stock: boolean;
  image_url: string;
}

export interface WireProduct {
  id: string;
  name: string;
  description: string;
  currency: string;
  hero_image_url: string;
  option_dimensions: WireOptionDimension[];
  skus: WireSku[];
}

export interface WireCartLine {
  sku_id: string;
  quantity: number;
  unit_price_minor: number;
  line_total_minor: number;
  name: string;
  image_url: string;
  options: Record<string, string>;
}

export interface WireCart {
  id: string;
  currency: string;
  items: WireCartLine[];
  total_item_count: number;
  subtotal_minor: number;
}

export interface WireSkuAvailability {
  sku_id: string;
  available_quantity: number;
}

export interface WireAddToCartResponse {
  cart: WireCart;
  sku_availability: WireSkuAvailability;
}

export interface WireErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id?: string;
}

export interface WireErrorResponse {
  error: WireErrorBody;
}
