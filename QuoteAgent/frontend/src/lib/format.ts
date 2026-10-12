/**
 * Showing numbers and words.
 *
 * Money arrives from the server as an exact decimal string and is never
 * turned into a JavaScript number, because that is how cents go missing on a
 * large bill of materials. It is formatted by splitting the string.
 */

export function money(value: string | null | undefined, currency?: string): string {
  if (value === null || value === undefined || value === "") return "—";
  const negative = value.trim().startsWith("-");
  const [whole, decimals = ""] = value.replace("-", "").split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const padded = (decimals + "00").slice(0, 2);
  const text = `${negative ? "-" : ""}${grouped}.${padded}`;
  return currency ? `${text} ${currency}` : text;
}

export function quantity(value: string | null | undefined): string {
  if (!value) return "—";
  const [whole, decimals] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  if (!decimals || /^0+$/.test(decimals)) return grouped;
  return `${grouped}.${decimals.replace(/0+$/, "")}`;
}

export function percent(value: string | null | undefined): string {
  if (!value) return "—";
  const asNumber = Number(value);
  if (Number.isNaN(asNumber)) return value;
  return `${asNumber.toFixed(1)}%`;
}

export function count(value: number | undefined | null): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-GB");
}

export function dateOnly(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function dateAndTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function duration(milliseconds: number): string {
  if (!milliseconds) return "instant";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(2)} s`;
}

/** Plain words for codes that otherwise leak onto the screen. */
const WORDS: Record<string, string> = {
  // statuses
  received: "Received",
  parsed: "Read",
  matched: "Parts identified",
  awaiting_customer: "Waiting for the customer",
  awaiting_supplier: "Waiting for a supplier",
  priced: "Priced",
  awaiting_approval: "Waiting for approval",
  sent: "Quote sent",
  revised: "Revised request received",
  won: "Won",
  lost: "Lost",
  cancelled: "Cancelled",
  // line statuses
  needs_clarification: "Question outstanding",
  non_catalogue: "Not a catalogue part",
  withdrawn: "Withdrawn",
  // question kinds
  missing_attribute: "Something is missing",
  conflicting_specification: "The line contradicts itself",
  ambiguous_match: "More than one part fits",
  quantity_unit: "The quantity needs confirming",
  // actors
  agent: "QuoteAgent",
  person: "A person",
  system: "The system",
  customer: "The customer",
  supplier: "A supplier",
  // match methods
  catalogue_number: "Our own catalogue number",
  cross_reference: "Cross-reference table",
  attribute_match: "Attribute match",
  text_similarity: "Text similarity",
  none: "No match",
  // duty components
  most_favoured_nation: "Normal trade relations rate",
  section_232: "Section 232 metals duty",
  section_301: "Section 301 duty",
  section_122: "Section 122 temporary duty",
  reciprocal: "Reciprocal trade agreement rate",
};

export function words(code: string | null | undefined): string {
  if (!code) return "";
  return WORDS[code] ?? code.replace(/_/g, " ");
}

/** Attribute names, in words, for the attribute checks panel. */
const ATTRIBUTE_WORDS: Record<string, string> = {
  kind: "part type",
  thread: "thread size",
  pitch_mm: "thread pitch",
  length_mm: "length",
  property_class: "strength class",
  material: "material",
  finish: "surface finish",
  designation: "bearing number",
  seal: "sealing",
  clearance: "internal clearance",
  bore_mm: "bore",
  stroke_mm: "stroke",
  outside_diameter_mm: "outside diameter",
  width_mm: "width",
  port: "port thread",
  action: "action",
};

export function attributeWords(name: string): string {
  return ATTRIBUTE_WORDS[name] ?? name.replace(/_/g, " ");
}

const VALUE_WORDS: Record<string, string> = {
  socket_head_cap_screw: "socket head cap screw",
  hex_head_bolt: "hexagon head bolt, fully threaded",
  hex_head_bolt_partial: "hexagon head bolt, partially threaded",
  button_head_screw: "button head screw",
  countersunk_socket_screw: "countersunk socket screw",
  socket_set_screw: "socket set screw",
  threaded_stud: "threaded stud",
  hex_nut: "hexagon nut",
  prevailing_torque_nut: "nut with a nylon insert",
  flat_washer: "flat washer",
  spring_washer: "spring lock washer",
  iso_15552_cylinder: "pneumatic cylinder to ISO 15552",
  compact_cylinder: "compact pneumatic cylinder",
  solenoid_valve: "solenoid valve",
  push_in_fitting: "push-in fitting",
  plain: "plain (self colour)",
  black_oxide: "black oxide",
  zinc_blue: "zinc plated, blue passivated",
  zinc_yellow: "zinc plated, yellow passivated",
  hot_dip_galvanised: "hot dip galvanised",
  zinc_flake: "zinc flake coated",
  stainless_plain: "stainless, untreated",
  carbon_steel: "carbon steel",
  stainless_steel: "stainless steel",
  sealed_both: "sealed both sides",
  sealed_one: "sealed one side",
  shielded_both: "shielded both sides",
  shielded_one: "shielded one side",
  open: "open, no seal",
  double_acting: "double acting",
  single_acting: "single acting",
};

export function valueWords(value: string): string {
  return VALUE_WORDS[value] ?? value;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
