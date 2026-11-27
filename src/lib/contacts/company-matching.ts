export type CompanyCandidate = {
  id: string;
  name: string;
  domain?: string | null;
  country?: string | null;
  source?: string | null;
};

// A review aid only. Never use this name comparison as authorization or a
// contact-to-shipment join; only an explicit, reviewed company ID can do that.
export function companyNameKey(name: string): string {
  return name.toLocaleLowerCase('en').replace(/[^\p{L}\p{N}]/gu, '');
}

export function matchingCompanyCandidates(
  contactCompany: string | null | undefined,
  companies: CompanyCandidate[],
): CompanyCandidate[] {
  if (!contactCompany?.trim()) return [];
  const key = companyNameKey(contactCompany);
  if (!key) return [];
  return companies.filter((company) => companyNameKey(company.name) === key);
}
