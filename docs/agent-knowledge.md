# Agent-kennis SOMA MCP

Opgebouwde projectkennis voor elke agent (Claude Code, Codex, lokale modellen). De herkomst is
de Claude-memory van de oude laptop, omgezet op 5 oktober 2026. Bij een conflict gaan de code,
`AGENTS.md`, `CLAUDE.md` en de ADR's (`docs/adr/`) voor. Deze repository is publiek: alleen
kennis die hier veilig te delen is staat in dit bestand.

## Werkafspraken en regels

- **Publieke grens.** Deze repo is de enige goedgekeurde publieke SOMA-repository. De memory van dit
  project ging bijna volledig over interne infrastructuur en tenantdata (productiehost,
  provisioning, eigenaarsregisters, een incident bij een klant). Die kennis hoort niet in een
  publieke repo en is hier bewust weggelaten; ze staat in de privé-repo's van het SOMA-project
  (zie de PR-beschrijving). Voeg hier nooit interne infra, tenantdata of klantgegevens toe
  (zie "Repository privacy" in `AGENTS.md`).
- **Sandbox-weigeringen niet omzeilen.** Als de classifier van de sandbox een destructief commando
  (bijvoorbeeld een `docker compose down -v` over ssh) of een tool-aanroep weigert, probeer dan niet
  hetzelfde commando via een andere tool. Leg uit wat je wilde doen en geef de gebruiker het exacte
  commando (26 augustus 2026).

## Valkuilen en lessen

- **Gedeelde JSON-statebestanden van een draaiende service.** Schrijf ze alleen met hetzelfde
  atomaire schrijfpatroon plus `flock` als de applicatie zelf; overschrijf ze niet direct, want de
  service kan er tegelijk naar schrijven.
- **Verwijderscripts en gedeelde identiteit.** Een verwijderscript dat externe identiteiten
  (Auth0-gebruikers) opruimt moet eerst controleren of die identiteit nog door een andere, levende
  tenant wordt gebruikt. Bij ontbreken van die controle: niet draaien op een handle waarvan het
  subject gedeeld kan zijn (gevonden 26 augustus 2026; de details staan in de privé-repo).
- **Anthropic-workspace spend-limits** zijn niet via een API te lezen of te zetten (gecontroleerd
  tegen de docs op 26 augustus 2026); een spend-cap is handmatige attestatie, geen automatische
  afdwinging.
- **Controle van aanwezigheid van variabelen in een env-bestand.** Een naieve
  `grep -o '^[A-Z_]*='` kan een vals negatief geven; controleer door het bestand echt te sourcen,
  zonder de waarden te tonen.
