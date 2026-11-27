'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, Building2, Mail, Phone } from 'lucide-react';
import { createClient } from '@/lib/supabase/client';
import { useAuth } from '@/hooks/use-auth';
import type { Contact, ContactNote, Deal, Tag } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ContactDetailView } from '@/components/contacts/contact-detail-view';
import { matchingCompanyCandidates, type CompanyCandidate } from '@/lib/contacts/company-matching';

type ClientHome = {
  contact: Contact;
  tags: Tag[];
  notes: ContactNote[];
  deals: Deal[];
  companyCandidates: CompanyCandidate[];
  companyReviewNotice: string | null;
};

export default function ClientHomePage() {
  const { id } = useParams<{ id: string }>();
  const { accountId, profileLoading } = useAuth();
  const [home, setHome] = useState<ClientHome | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (profileLoading) return;
    if (!accountId) return;
    let active = true;
    const supabase = createClient();

    async function load() {
      try {
        const contactResult = await supabase.from('contacts').select('*')
          .eq('id', id).eq('account_id', accountId!).maybeSingle();
        if (contactResult.error) throw contactResult.error;
        if (!contactResult.data) {
          if (active) { setHome(null); setError('Contact not found in this account.'); setLoading(false); }
          return;
        }
        // Public CRM companies are account scoped. Trade identities and shipments
        // are intentionally not queried from the browser or inferred from this list.
        const companyResult = await supabase.from('companies')
          .select('id,name,domain,country,source')
          .eq('account_id', accountId!).order('name').limit(500);
        const [tagLinks, notesResult, dealsResult] = await Promise.all([
          supabase.from('contact_tags').select('tag_id').eq('contact_id', id),
          supabase.from('contact_notes').select('*').eq('contact_id', id).order('created_at', { ascending: false }).limit(20),
          supabase.from('deals').select('*, stage:pipeline_stages(*)').eq('contact_id', id).order('created_at', { ascending: false }).limit(20),
        ]);
        if (tagLinks.error || notesResult.error || dealsResult.error) {
          throw tagLinks.error ?? notesResult.error ?? dealsResult.error;
        }
        const tagIds = (tagLinks.data ?? []).map((link) => link.tag_id);
        const tagResult = tagIds.length
          ? await supabase.from('tags').select('*').in('id', tagIds).order('name')
          : null;
        if (tagResult?.error) throw tagResult.error;
        if (active) {
          setHome({
            contact: contactResult.data as Contact,
            tags: (tagResult?.data ?? []) as Tag[],
            notes: (notesResult.data ?? []) as ContactNote[],
            deals: (dealsResult.data ?? []) as Deal[],
            companyCandidates: companyResult.error ? [] : matchingCompanyCandidates(
              contactResult.data.company,
              (companyResult.data ?? []) as CompanyCandidate[],
            ),
            companyReviewNotice: companyResult.error
              ? 'Account company candidates could not be loaded; no match can be inferred.'
              : (companyResult.data?.length ?? 0) === 500
                ? 'Candidate search reached its 500-company review limit; the list may be incomplete.'
                : null,
          });
          setError(null);
        }
      } catch {
        if (active) { setHome(null); setError('Could not load this client dashboard. Please try again.'); }
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => { active = false; };
  }, [id, accountId, profileLoading, revision]);

  if (profileLoading || (accountId && loading)) return <p className="text-sm text-muted-foreground">Loading client dashboard…</p>;
  if (!accountId) return <p className="text-sm text-muted-foreground">Account access is required to view this client.</p>;
  if (error || !home) return <div className="space-y-4"><p role="alert">{error ?? 'Contact not found.'}</p><Button variant="outline" onClick={() => { setLoading(true); setRevision((n) => n + 1); }}>Retry</Button><Link className="block text-sm underline" href="/contacts">Back to contacts</Link></div>;

  const { contact, tags, notes, deals, companyCandidates, companyReviewNotice } = home;
  return (
    <div className="space-y-6">
      <Link href="/contacts" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Contacts</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="text-sm text-muted-foreground">Client dashboard · Contact</p><h1 className="text-2xl font-semibold text-foreground">{contact.name || contact.company || contact.phone || 'Unnamed contact'}</h1><p className="text-sm text-muted-foreground">{contact.company || 'No company recorded'}</p></div>
        <Button variant="outline" onClick={() => setDetailOpen(true)}>Edit contact, tags & notes</Button>
      </div>
      <section aria-labelledby="shipment-heading" className="space-y-4">
        <div><h2 id="shipment-heading" className="text-xl font-semibold">Shipments and lane mapping</h2><p className="text-sm text-muted-foreground">Recorded shipment parties and routes belong here only after this contact is linked to a verified company.</p></div>
        <Card><CardHeader><CardTitle>Recent shipments</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
          <p>No shipments can be safely attributed to this contact yet.</p>
          <p className="text-muted-foreground">The CRM holds a company name, not a verified company ID. Matching shipment records by name could show another company’s cargo.</p>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Shipment-party and route mapping</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground">No verified contact → company → recorded shipper/consignee mapping or dated origin → destination lanes are available to this account. No shipment map is shown.</CardContent></Card>
      </section>
      <section aria-labelledby="company-review-heading">
        <Card><CardHeader><CardTitle id="company-review-heading">Company identity review</CardTitle></CardHeader><CardContent className="space-y-3 text-sm">
          <p>Possible matches within this CRM account only. Names are not verified identity links; this preview neither saves a mapping nor grants shipment access.</p>
          {companyReviewNotice && <p role="status" className="text-muted-foreground">{companyReviewNotice}</p>}
          {!companyReviewNotice && (companyCandidates.length
            ? <ul className="space-y-2">{companyCandidates.map((candidate) => <li key={candidate.id} className="rounded border p-3"><p className="font-medium">{candidate.name}</p><p className="text-muted-foreground">{[candidate.country, candidate.domain, candidate.source].filter(Boolean).join(' · ') || 'No additional identity evidence recorded'}</p><p className="text-xs text-muted-foreground">Company ID: {candidate.id} · Unverified candidate</p></li>)}</ul>
            : <p className="text-muted-foreground">No matching account company record found. This does not rule out a trade-company candidate.</p>)}
          <p className="text-muted-foreground">A reviewer must verify the legal company and recorded shipment-party role before a durable contact→company link or shipment data is shown.</p>
        </CardContent></Card>
      </section>
      <section aria-labelledby="context-heading" className="space-y-4">
        <h2 id="context-heading" className="text-xl font-semibold">Company context and talking points</h2>
        <div className="grid gap-4 md:grid-cols-2">
        <Card><CardHeader><CardTitle>Public company talking points</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">
          <p>{contact.company ? `Company name on this contact: ${contact.company}` : 'No company name is recorded on this contact.'}</p>
          <p className="text-muted-foreground">No public facts have been verified and linked to this company identity. Add source URLs, dates and reviewed talking points after the company match is confirmed; a name match alone is not evidence.</p>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Internal CRM notes</CardTitle></CardHeader><CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">Private notes, not public-source findings or approved outreach.</p>
          {notes.length ? <ul className="space-y-3">{notes.map((note) => <li key={note.id} className="border-b pb-2 last:border-0"><p className="whitespace-pre-wrap">{note.note_text}</p><time className="text-xs text-muted-foreground" dateTime={note.created_at}>{new Date(note.created_at).toLocaleDateString()}</time></li>)}</ul> : <p className="text-muted-foreground">No notes recorded.</p>}
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Contact details</CardTitle></CardHeader><CardContent className="space-y-3">
          <p className="flex items-center gap-2"><Building2 className="size-4" />{contact.company || 'Company not recorded'}</p>
          <p className="flex items-center gap-2"><Phone className="size-4" />{contact.phone || 'Phone not recorded'}</p>
          <p className="flex items-center gap-2"><Mail className="size-4" />{contact.email || 'Email not recorded'}</p>
          <div className="flex flex-wrap gap-2" aria-label="Contact tags">{tags.length ? tags.map((tag) => <span key={tag.id} className="rounded-full border px-2 py-1 text-xs">{tag.name}</span>) : <span className="text-muted-foreground">No tags</span>}</div>
        </CardContent></Card>
        <Card><CardHeader><CardTitle>Relationship status</CardTitle></CardHeader><CardContent className="space-y-2">
          <p className="font-medium">Customer status: Not verified</p>
          <p className="text-muted-foreground">CRM deal outcomes do not prove that this contact has shipped with us. Confirm against a linked shipment or customer record before marking them as a customer.</p>
          <p>{deals.length ? `${deals.length} recent CRM deal${deals.length === 1 ? '' : 's'} listed below` : 'No CRM deals linked to this contact.'}</p>
        </CardContent></Card>
        </div>
      </section>
      <Card><CardHeader><CardTitle>CRM opportunities</CardTitle></CardHeader><CardContent>
        {deals.length ? <ul className="space-y-3">{deals.map((deal) => <li key={deal.id} className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 last:border-0"><span>{deal.title}</span><span className="text-sm text-muted-foreground">{deal.stage?.name || 'No stage'} · {deal.status || 'open'}</span></li>)}</ul> : <p className="text-muted-foreground">No linked opportunities.</p>}
      </CardContent></Card>
      <ContactDetailView open={detailOpen} onOpenChange={setDetailOpen} contactId={id} onUpdated={() => { setLoading(true); setRevision((n) => n + 1); }} />
    </div>
  );
}
