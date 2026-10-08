# Sites étudiés mais non collectés

[← Retour au guide](README.md)

Vérifié le 8 octobre 2026. Pour les offres de ces sites, prépare un CSV à la main ou
depuis un export (Apify...) : voir [source_manuelles.md](source_manuelles.md).

| Site | Pourquoi |
|------|----------|
| LinkedIn | Son robots.txt interdit tout aux robots (« Disallow: / ») ; LinkedIn poursuit les collectes automatiques |
| Indeed | Pages d'offres et de recherche interdites aux robots, protection anti-robots forte |
| Welcome to the Jungle | Bloque activement les robots (erreur 403 dès le robots.txt) |
| Keljob | Redirige vers Figaro Emploi, protégé par Cloudflare (erreur 403) |
| Stage.fr | Le serveur refuse les requêtes automatiques (« Access denied! ») malgré son robots.txt |
| Alternance-professionnelle.fr | Aucune offre en ligne (liste et flux RSS vides) |
| Jobirl | Sa seule liste d'offres (/recherche-interne) est interdite aux robots ; pas de sitemap ; offres surtout pour lycéens |
| HelloWork | Recherche interdite aux robots ; pas encore étudié en détail |
| JobTeaser | Offres souvent réservées aux étudiants connectés via leur école ; pas encore étudié en détail |

## LinkedIn : par les alertes e-mail

LinkedIn est accessible par tes alertes emploi reçues dans Gmail : voir
[source_linkedin.md](source_linkedin.md). Les alertes d'Indeed, HelloWork ou Welcome to
the Jungle pourront être ajoutées de la même façon quand tu en recevras.
