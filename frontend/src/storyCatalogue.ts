/**
 * Featured Characters and Parva names for the Story Picker
 * (story-mode Requirement 2). These are fixed content, not runtime
 * data, so they're mirrored here rather than fetched - kept in sync
 * with backend/build_catalogue.py's FEATURED_CHARACTERS and
 * backend/scope.py's PARVA_NAMES. The backend's catalogue.json is the
 * source of truth for which SECTIONS support each subject; this list is
 * only the picker's menu of subject names.
 */
export const FEATURED_CHARACTERS = [
  "Arjuna",
  "Karna",
  "Draupadi",
  "Bhishma",
  "Krishna",
  "Yudhishthira",
  "Vidura",
  "Shikhandi",
  "Ghatotkacha",
  "Sanjaya",
];

// Matches backend catalogue.json's `subject` spelling exactly (all
// caps, site's own spelling) - sent verbatim as `subject` in the
// request body.
export const PARVAS = [
  "ADI PARVA",
  "SABHA PARVA",
  "VANA PARVA",
  "VIRATA PARVA",
  "UDYOGA PARVA",
  "BHISHMA PARVA",
  "DRONA PARVA",
  "Karna-parva",
  "Shalya-parva",
  "Sauptika-parva",
  "Stri-parva",
  "SANTI PARVA",
  "ANUSASANA PARVA",
  "ASWAMEDHA PARVA",
  "ASRAMAVASIKA PARVA",
  "Mausala-parva",
  "Mahaprasthanika-parva",
  "Svargarohanika-parva",
];

export function displayParvaName(name: string): string {
  return name
    .split(/[\s-]+/)
    .map((w) => w[0].toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}
