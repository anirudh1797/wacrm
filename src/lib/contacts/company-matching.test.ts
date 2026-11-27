import { describe, expect, it } from 'vitest';
import { companyNameKey, matchingCompanyCandidates } from './company-matching';

const companies = [
  { id: 'one', name: 'Acme Trading Ltd', country: 'IN' },
  { id: 'two', name: 'ACME TRADING LTD', country: 'US' },
  { id: 'three', name: 'Different Co' },
];

describe('company match review aid', () => {
  it('normalizes case and separators without inventing fuzzy matches', () => {
    expect(companyNameKey(' Acme-Trading, Ltd. ')).toBe('acmetradingltd');
    expect(matchingCompanyCandidates('acme trading ltd', companies).map((c) => c.id)).toEqual(['one', 'two']);
    expect(matchingCompanyCandidates('Acme Trading Limited', companies)).toEqual([]);
  });

  it('treats empty or punctuation-only names as unmatched', () => {
    expect(matchingCompanyCandidates('  ', companies)).toEqual([]);
    expect(matchingCompanyCandidates('---', companies)).toEqual([]);
    expect(matchingCompanyCandidates(undefined, companies)).toEqual([]);
  });

  it('does not silently collapse duplicate company identities', () => {
    expect(matchingCompanyCandidates('different co', companies).map((c) => c.id)).toEqual(['three']);
    expect(matchingCompanyCandidates('Acme Trading Ltd', companies)).toHaveLength(2);
  });
});
