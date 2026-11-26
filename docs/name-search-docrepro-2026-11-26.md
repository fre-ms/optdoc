# Name search for "docrepro" (26 November 2026)

A collision check made before the name of the whole application was chosen: the application
that joins optdoc, ocrdoc and the tools to come (`docs/family-design.md`). It is not a
professional trademark search and no legal opinion. Names of private persons who hold or applied
for marks are left out. The note moves to docrepro's own repository once there is one.

## Why another name than reprodoc

The working name was **reprodoc**, meant as "reprography" (the print trade's "Repro") of a
document. In German medicine, though, "Repro" first suggests reproductive medicine and "doc" a
doctor: reprodoc.de is a fertility centre, and ReproDoc Ltd works in cattle reproduction. The
tools serve medical documents, so the reading mattered.

Candidates around "faithful copy", "facsimile" and "anew" were checked first (about 60; one
passed, **facsimdoc**). The user then proposed **facsim** and **docrepro**.

## Method

- **Domains**: DNS (NS and A) for `.org`, `.com`, `.de`, `.net`, `.eu`, `.app`, `.dev`, `.io`.
- **Package names and accounts**: PyPI, npm, GitHub user or organisation; GitHub repository
  search by name.
- **Web**: search for the name, in one word, with a hyphen and in two words.
- **DPMAregister** (German, EU and international marks designating DE or the EU), wildcard
  search, with the control query `?meddra?` returning its known 4 hits.
- **TMview** (all connected offices): fuzzy and "contains" searches; every answer checked to
  have come from the service (a new response), not left over from an earlier query.
- **USPTO** trademark search (wordmark), with the control query `docuware` returning its known
  live marks through the same search field.

## facsim: not taken

| Check | Result |
|---|---|
| Domains | `.org` registered (a WordPress placeholder since about June 2024; the Facsimile Simulation Library publishes as `org.facsim` on Maven Central), `.com` registered (SURFnet name servers); `.de`, `.net`, `.eu`, `.app`, `.dev`, `.io` unregistered |
| Packages | free on PyPI and npm; GitHub user `facsim` taken (empty since 2019) |
| Web | FaCSim, an ARM architecture simulator (Seoul National University, 2008); the Facsimile Simulation Library (discrete-event simulation, LGPL); in medicine "FACS" is flow cytometry, and "FACS simulators" are known teaching tools (facSimile, a virtual flow cytometer, ANU; the FACS Simulator of the University of Salzburg) |
| DPMAregister | no mark FACSIM; near and alive: EU figurative mark "fake f fac simile faksi" (018840763, classes 9, 42: authentication of images), "faksimilar" (DE, classes 16, 35, 41), BD FACSYMPHONY (IR, class 9: flow cytometers) |

"sim" reads as simulation, which the application does not do, and in medicine "FACS-Sim" reads
as a flow-cytometry simulator: the same kind of misreading that ruled out reprodoc.

## docrepro: chosen

| Check | Result |
|---|---|
| Domains | `.org`, `.com`, `.de`, `.net`, `.eu`, `.app`, `.dev`, `.io` all unregistered |
| Packages | `docrepro`, `doc-repro`, `dokrepro` free on PyPI and npm, and as GitHub accounts; one neighbour, `docrepo` (a tool that scaffolds repository files), on PyPI, npm and GitHub |
| GitHub | one empty repository "docreprocann" (2023) |
| Web | no product or project of the name, in one word, with a hyphen or in two words; the nearest names are several "DocPro" in healthcare (an AI platform for practices, a clinic app) |
| DPMAregister | `?docrepro?`, `?dokrepro?`, `doc?repro?`, `?docrepr?`: no mark; `docrep?`: DOC REPORT (EU, lapsed), DOCREPUTATION (EU, alive), "Doc Rep Bonn Medizin Repititorium" (DE, cancelled) |
| TMview | fuzzy `docrepro`: DOTREPRO (Greece, class 16, lapsed 1998) and DocuRepro (Fuji Xerox, Japan, class 9, lapsed 2008); "contains" `docrepro`: DOCREPROCANN (Argentina, class 45, alive; a service around Argentina's medical-cannabis register REPROCANN); fuzzy `dokrepro`, `docurepro`: only the two lapsed marks; fuzzy "doc repro": REPRO DOC (France, 1977) and REPRO.DOC (France, 2000), both lapsed, the rest marks of "DOC" or "REPRO" alone |
| USPTO | `docrepro`, `docurepro`: no mark |

With "doc" first, the name reads as the reproduction of a document; the medical reading of
"Repro" is weaker than in "reprodoc", which sounded like a specialist's title.

Sources: register.dpma.de, tmdn.org/tmview, tmsearch.uspto.gov, pypi.org, registry.npmjs.org,
api.github.com; web search.
