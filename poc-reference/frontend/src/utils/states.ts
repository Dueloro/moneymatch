// Residence states + the geo-fence list, shared by the Landing eligibility gate
// and the Solo Pools region check. Mirrors the backend RESTRICTED_STATES in
// api/_lib/solo_challenge.py (overview §9.2 / §10).

export const US_STATES = [
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
  'Connecticut', 'Delaware', 'District of Columbia', 'Florida', 'Georgia',
  'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky',
  'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
  'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire',
  'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota',
  'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island',
  'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah', 'Vermont',
  'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming',
];

// The 14 "Any Chance" states where real-money skill wagering is blocked.
export const EXCLUDED_STATES = new Set<string>([
  'Arizona', 'Arkansas', 'Connecticut', 'Delaware', 'Florida', 'Indiana',
  'Louisiana', 'Maryland', 'Minnesota', 'Montana', 'South Carolina',
  'South Dakota', 'Tennessee', 'Wyoming',
]);

export const ALLOWED_STATES = US_STATES.filter((s) => !EXCLUDED_STATES.has(s));

export function isStateAllowed(state: string | null): boolean {
  return state !== null && state !== '' && !EXCLUDED_STATES.has(state);
}
