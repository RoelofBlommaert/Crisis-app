---
name: Crisis Monitoring PoC
last_updated: 2026-09-14
---

# Crisis Monitoring PoC — Strategie

## Doelprobleem

NWW heeft tijdens crises wél inzicht, maar dat inzicht is versnipperd en emotie-gebonden per rol — beleidsmedewerker, voorlichter en post vormen elk hun eigen beeld, en de crisis mapping is altijd mensgestuurd. Daardoor is NWW altijd te laat en is de classificatie foutgevoelig.

## Onze aanpak

We winnen door incrementeel te automatiseren: losse, bestaande informatiestukjes eerst (zoals de huidige classificatie), gekoppeld en betrouwbaar gepresenteerd via bronnen als GDACS en GDELT, zodat er snel zichtbare, vertrouwde winst is in plaats van een groot ontwerp vooraf — nodig omdat mensen onder stress snel sceptisch worden en dan verkeerde keuzes maken. Voor bronnen waarvan toegang tot echte data nog niet bevestigd is (calls, RNI, CBS-vluchten), werkt de PoC voorlopig met gesynthetiseerde of fictieve data.

## Voor wie

**Primair:** Crisiscoördinator — gebruikt het om vroeg te zien wat er in een gebied speelt, automatisch gedetecteerd in plaats van mensgestuurd, eventueel gecombineerd met het volume aan binnenkomende communicatie, zodat die sneller kan inschatten of en hoe ernstig iets is.

## Sporen

### Near-real-time engineering

Infrastructuur die zorgt dat bronnen (GDACS, GDELT, OpenSky, e.d.) tijdig en actueel binnenkomen.

_Waarom het de aanpak dient:_ zonder actuele data is automatisering tijdens een crisis niet geloofwaardig.

### Data-integratie

Bronnen (GDACS, GDELT, CBS, Eurostat, OpenSky) aan elkaar koppelen tot één samenhangend beeld per gebied.

_Waarom het de aanpak dient:_ vervangt het versnipperde, per-rol beeld door een centraal beeld.

### Classificatie

De nu mensgestuurde crisis-classificatie stap voor stap automatiseren.

_Waarom het de aanpak dient:_ is letterlijk het eerste "losse informatiestukje" dat wordt geautomatiseerd.

### Flexibiliteit / hybride sturing

Automatische detectie én handmatige override naast elkaar laten werken.

_Waarom het de aanpak dient:_ behoudt vertrouwen — mensen worden onder stress sceptisch, controle houden helpt daartegen.

## Niet aan werken

- Nog geen voorspelling van crises — dat is een latere fase.
- Nog geen RNI-koppeling.
- Nog geen NWW-call-integratie.
- Classificatie hoeft in de PoC nog niet automatisch te werken — puur laten zien wat er aan data is en hoe het gecombineerd kan worden tot een risico-indicatie.

## Positionering

**One-liner:** Van reactief naar proactief: bestaande data inzetten om crises sneller en objectiever te classificeren, zodat NWW met vertrouwen kan handelen vóór de telefoon gaat.

**Kernboodschap:** We hebben de data al — GDACS, GDELT, CBS, Eurostat, OpenSky — maar die is versnipperd en het beeld is nu mensgestuurd. Deze PoC laat zien wat er beschikbaar is en hoe het gecombineerd kan worden tot één betrouwbaar risicobeeld per gebied, als eerste stap naar geautomatiseerde classificatie en op termijn crisisparaatheid.
