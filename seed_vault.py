"""
Seed the memory vault with a realistic agency knowledge base.

Run once: python3 seed_vault.py
Delete vault/ and re-run to reset. Everything it writes is plain markdown with
frontmatter and [[wikilinks]] — open the folder in Obsidian and it just works.
"""
import pathlib
import random

ROOT = pathlib.Path(__file__).resolve().parent
VAULT = ROOT / "vault"
random.seed(1922)   # deterministic vault, so the video looks the same every take

CLIENTS = [
    ("Filect", "SaaS billing platform", "Retainer", "8400"),
    ("Fairview Dental", "Six-clinic dental group", "Retainer", "3200"),
    ("Orchard Legal", "Boutique commercial firm", "Project", "11500"),
    ("Kestrel Logistics", "Regional freight broker", "Retainer", "5600"),
    ("Northbeam Automation", "Industrial controls", "Project", "18000"),
    ("Vantage Property", "Letting agency, 40 staff", "Retainer", "2900"),
    ("Halden Physio", "Physiotherapy chain", "Project", "6200"),
    ("Lumen Fitness", "Boutique gym franchise", "Retainer", "2400"),
    ("Harbour Accounting", "Accountancy practice", "Project", "9800"),
    ("Copper & Rye", "Independent distillery", "Project", "6000"),
]
PEOPLE = [
    ("Priya Raman", "Ops lead", "Filect"),
    ("Nadia Bell", "Practice manager", "Harbour Accounting"),
    ("Marcus Feld", "Managing partner", "Orchard Legal"),
    ("Yasmin Choudhury", "Clinic director", "Fairview Dental"),
    ("Sam Okafor", "Senior automation engineer", "internal"),
    ("Tom Rivers", "Founder", "Copper & Rye"),
    ("Ines Duarte", "Head of ops", "Kestrel Logistics"),
    ("Callum Reid", "Operations director", "Northbeam Automation"),
    ("Dee Whitlock", "Owner", "Lumen Fitness"),
    ("Farrah Nasser", "Delivery lead", "internal"),
]
CONCEPTS = [
    ("Reusable components", "The library of pre-built automation blocks we reuse across every build. The single biggest driver of margin — a build that reuses 70% of the library lands in nine days instead of twenty-five."),
    ("Margin model", "Fixed price against reusable components. We quote the outcome, not the hours, so every component we add to the library raises the margin on every future build."),
    ("Handover pack", "What the client receives at the end: loom walkthrough, written runbook, escalation path, and 30 days of bug cover. Cuts post-launch support tickets by roughly two thirds."),
    ("Lead qualification", "Three gates before a discovery call: budget above 2k, a named decision maker on the call, and at least one process they can describe end to end."),
    ("Discovery call", "45 minutes. Map the process, count the manual touchpoints, price the delay. We never quote on the call."),
    ("Component library", "Versioned collection of tested automation blocks. Every project must either use a component or contribute one."),
    ("Fixed price", "We never bill hourly. Hourly punishes us for getting faster, which is the entire competitive advantage."),
    ("Outbound campaign", "Cold email in tight niches. Twelve to eighteen touches, heavy personalisation on the first line only."),
    ("Retainer motion", "Post-build monthly for monitoring, changes and new automations. Target is 60% of revenue on retainer by year end."),
    ("Scope creep", "The main killer of fixed-price margin. Anything outside the signed brief becomes a change order, no exceptions."),
    ("Audit offer", "Free 30-minute process audit used as the entry offer on outbound. Converts around one in four into a paid build."),
    ("Growth package", "Our standard mid-tier: three automations, component library access, handover pack, 90 days support."),
    ("Capacity planning", "The binding constraint is senior engineer hours, not leads. Sam is the bottleneck."),
    ("Pricing floor", "We do not take builds under 2,000. Below that the handover pack alone eats the margin."),
    ("Positioning", "The gap nobody fills: fixed price against a reusable component library, in the under-30k band the consultancies abandoned."),
    ("Client onboarding", "Kickoff form, access checklist, shared drive, then the discovery call. Never start a build without all four."),
]
SOPS = [
    ("SOP — Automation build", "1. Confirm signed brief. 2. Check the component library first. 3. Build in staging. 4. Client walkthrough. 5. Handover pack. 6. 30-day bug cover."),
    ("SOP — Handover", "Record the loom before the final call. Written runbook in the shared drive. Escalation path named. Bug cover window stated in writing."),
    ("SOP — Discovery call", "Map process. Count touchpoints. Price the delay. Confirm decision maker. Book the follow-up before hanging up. Never quote live."),
    ("SOP — Outbound", "Pull the list, verify every address, write the sequence, load into the sender, warm the domain for 14 days first."),
    ("SOP — Invoicing", "50% on signature, 50% on handover. Seven-day terms. Chase at day 8, day 15, then pause work."),
    ("SOP — Change order", "Anything outside the brief gets priced in writing before a line of work happens. No verbal approvals."),
    ("SOP — Weekly review", "Friday. Pipeline, capacity, margin per active build, and one component added to the library."),
    ("SOP — Client offboarding", "Final invoice, access revoked, assets transferred, testimonial requested, 90-day check-in booked."),
]
PROJECTS = [
    ("Filect billing sync", "Filect", "Stripe to internal ledger reconciliation, nightly."),
    ("Fairview recall engine", "Fairview Dental", "Automated six-month patient recall across six clinics."),
    ("Orchard intake automation", "Orchard Legal", "Client intake form to matter creation, no rekeying."),
    ("Kestrel quote engine", "Kestrel Logistics", "Freight quote generation from a rate card."),
    ("Northbeam reporting stack", "Northbeam Automation", "Plant floor data into weekly ops reports."),
    ("Vantage viewing scheduler", "Vantage Property", "Viewing bookings straight into agent calendars."),
    ("Halden intake forms", "Halden Physio", "Patient intake and consent, paperless."),
    ("Lumen member winback", "Lumen Fitness", "Lapsed member reactivation sequence."),
    ("Harbour year-end pack", "Harbour Accounting", "Year-end document collection chase."),
    ("Copper & Rye stock alerts", "Copper & Rye", "Low-stock alerts into the ops channel."),
    ("Component library v3", "internal", "Third rewrite of the shared automation blocks."),
]

def w(path, ntype, body, links=(), updated="2026-08-18", tags=()):
    VAULT.mkdir(parents=True, exist_ok=True)
    safe = path.replace("/", "-")
    fm = [f"type: {ntype}", f"updated: {updated}"]
    if tags:
        fm.append("tags: " + ", ".join(tags))
    linkline = ("\n\n" + " ".join(f"[[{l}]]" for l in links)) if links else ""
    (VAULT / f"{safe}.md").write_text(
        "---\n" + "\n".join(fm) + "\n---\n\n" + f"# {path}\n\n" + body + linkline + "\n",
        encoding="utf-8")

# clients
for name, desc, model, mrr in CLIENTS:
    people = [p[0] for p in PEOPLE if p[2] == name]
    w(name, "client",
      f"{desc}. Engagement: {model}. Current value: EUR {mrr}. "
      f"Won through [[Outbound campaign]] and qualified with [[Lead qualification]].",
      links=people + ["Margin model", "Handover pack"])

# people
for name, role, org in PEOPLE:
    where = org if org != "internal" else "our own team"
    w(name, "person", f"{role} at {where}.",
      links=([org] if org != "internal" else ["Capacity planning"]))

for name, body in CONCEPTS:
    w(name, "concept", body, links=["Margin model"] if name != "Margin model" else ["Reusable components"])

for name, body in SOPS:
    w(name, "sop", body, links=["Reusable components", "Handover pack"])

for name, client, body in PROJECTS:
    w(name, "project", body,
      links=([client] if client != "internal" else []) + ["SOP — Automation build", "Reusable components"])

# calls, invoices, proposals, briefs
topics = ["kickoff", "discovery", "scoping", "check-in", "handover", "escalation",
          "renewal", "review", "pricing", "technical"]
for i in range(38):
    client = CLIENTS[i % len(CLIENTS)][0]
    topic = topics[i % len(topics)]
    person = next((p[0] for p in PEOPLE if p[2] == client), PEOPLE[i % len(PEOPLE)][0])
    w(f"Call — {client} {topic} {i+1:02d}", "call",
      f"{topic.title()} call with {client}. Touchpoints mapped, actions logged.",
      links=[client, person, "Discovery call" if topic == "discovery" else "SOP — Automation build"],
      updated=f"2026-0{(i % 8) + 1}-{(i % 27) + 1:02d}")

for i in range(9):
    client = CLIENTS[i % len(CLIENTS)][0]
    w(f"Invoice {2610 + i} — {client}", "invoice",
      f"50/50 split against the signed brief. Terms seven days.",
      links=[client, "SOP — Invoicing"])

for i in range(9):
    client = CLIENTS[i % len(CLIENTS)][0]
    w(f"Proposal — {client}", "proposal",
      f"Fixed price against the component library. Growth package unless scoped otherwise.",
      links=[client, "Growth package", "Fixed price"])

for i in range(19):
    w(f"Note {i+1:02d} — {['margin','capacity','pricing','positioning','delivery'][i % 5]}", "note",
      f"Working note on {['margin','capacity','pricing','positioning','delivery'][i % 5]}.",
      links=[CONCEPTS[i % len(CONCEPTS)][0]])

w("Brief — Growth package", "brief",
  "Three automations, component library access, handover pack, 90 days support.",
  links=["Growth package", "Handover pack"])
w("Brief — Audit offer", "brief",
  "Free 30-minute process audit. Entry offer on all outbound.",
  links=["Audit offer", "Outbound campaign"])
w("Campaign — August outbound", "campaign",
  "Cold sequence to independent practices. Two replies so far: [[Marcus Feld]] and "
  "[[Yasmin Choudhury]], both asking for the audit.",
  links=["Outbound campaign", "Audit offer", "SOP — Outbound"])

print(f"vault seeded: {len(list(VAULT.glob('*.md')))} notes -> {VAULT}")
