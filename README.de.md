<p align="center"><img src="src/troedel/web/static/logo.svg" width="96" alt=""></p>

# Trödel

[English](README.md) · **Deutsch**

**Foto rein, Anzeige raus.** Mach ein paar Fotos von dem, was du verkaufen
willst, schreib zwei Wörter dazu, und Trödel entwirft die Anzeige: Titel,
Beschreibung, Eckdaten, Zustand, Kategorie und einen Preisvorschlag mit
Begründung. Die Fotos bereitet es auf deinem eigenen Rechner auf, und jedes
Feld liegt fertig zum Kopieren bereit für Kleinanzeigen, Vinted, eBay oder
Facebook Marketplace.

Trödel läuft bei dir selbst, für eine Person oder einen Haushalt, auf dem
eigenen Computer oder einem Heimserver. Es stellt nie selbst etwas ein:
Veröffentlichen bleibt in deiner Hand.

![Die Liste der Sachen: Entwürfe, was wo online ist und was verkauft wurde](docs/img/overview.webp)

> **Stand: früh.** Oberfläche und Anzeigen gibt es bisher **nur auf Deutsch**,
> gebaut für die deutschen Plattformen. Code, technische Dokumentation und
> Issues sind auf Englisch. Diese Seite ist die Übersetzung der
> [englischen README](README.md); weicht etwas ab, gilt die englische.

## Was es kann

- **Schreibt die Anzeige** aus Fotos und ein paar Stichwörtern, mit dem
  KI-Anbieter deiner Wahl. Was es nicht sehen kann, erfindet es nicht,
  sondern nennt es dir zum Nachprüfen.
- **Passt auf Zuruf an**: „Titel kürzer“, „erwähne den fehlenden Deckel“,
  „Preis 45“. Es ändert sich nur, was du verlangst; deine eigenen Korrekturen
  bleiben.
- **Bearbeitet Fotos auf deinem Rechner**, je Artikel: *Studio* (freigestellt,
  heller Grund, weicher Schatten), *Weiß*, *Aufgeräumt* (das Originalfoto,
  Störendes im Hintergrund wegretuschiert) oder *Original*. Der Gegenstand
  selbst wird nie verändert: Freistellen nutzt nur die Pixel aus deinem Foto,
  und die Retusche bleibt auf den Hintergrund beschränkt. Metadaten der Fotos
  (Ort, Gerät, Zeit) werden beim Hochladen entfernt.
- **Bereitet jede Plattform vor**: Längen, Wortwahl beim Zustand und der
  Schlusstext unterscheiden sich je Plattform; jedes Feld hat einen
  Kopierknopf.
- **Behält den Überblick**: was wo online ist, was für wie viel verkauft
  wurde, dazu eine einfache Statistik.

## So läuft es ab

**1. Fotografieren.** Trödel auf dem Handy öffnen, bis zu zwölf Fotos machen
und in wenigen Wörtern sagen, was es ist („Schreibtischlampe, grün,
funktioniert“). Ein Produktname hilft, wenn du ihn kennst. Das nächste Teil
kannst du sofort aufnehmen; geschrieben wird im Hintergrund.

**2. Entwurf lesen.** Nach ein paar Sekunden bis zu einer Minute, je nach
Anbieter, hat der Artikel Titel, Beschreibung, Eckdaten, Zustand, Kategorie,
Versandgröße und einen Preis mit Spanne und Begründung. Unter *Bitte prüfen*
steht, was Trödel auf den Fotos nicht erkennen konnte (eine Größe auf dem
Etikett, ob das Ladegerät dabei ist), damit du nachsiehst, statt dass es rät.
Jedes Feld lässt sich direkt ändern.

**3. Anpassen.** *Anpassen* nimmt eine Anweisung in normalen Worten: „Titel
kürzer“, „erwähne den Kratzer am Fuß“, „Preis 20“. Nur das ändert sich, deine
Korrekturen bleiben, und ein Tipp nimmt die Änderung zurück. *Komplett neu
schreiben* fängt von vorn an.

**4. Selbst veröffentlichen.** *Veröffentlichen* zeigt je Plattform die Felder
in der Reihenfolge ihres Formulars, schon auf ihre Längen gekürzt und in ihrer
Wortwahl, jedes mit Kopierknopf, dazu die Fotos zum Sichern. Du fügst sie in
der App oder auf der Seite der Plattform ein und stellst den Artikel in Trödel
auf „online“. Trödel meldet sich bei keiner Plattform an und schickt nichts ab.

![Auf dem Handy: neues Teil, der Entwurf, Anpassen, die Felder für eine Plattform](docs/img/phone.webp)

**5. Überblick behalten.** Die Liste zeigt, was Entwurf ist, was wo online
steht und was verkauft wurde; wer beim Verkauf den Betrag einträgt, füllt die
Statistik.

![Eine Anzeige auf einem großen Bildschirm, dunkles Design](docs/img/listing.webp)

### Foto-Looks

Jeder Artikel hat einen Look, jederzeit änderbar; die Originale bleiben immer
erhalten.

![Dasselbe Foto wie aufgenommen, als Studio und als Weiß](docs/img/looks.webp)

| Look | Was passiert |
|---|---|
| *Original* | Das Foto, wie es aufgenommen wurde. |
| *Studio* | Der Gegenstand wird freigestellt und auf einen hellen Grund mit weichem Schatten gesetzt. |
| *Weiß* | Der Gegenstand wird freigestellt und mittig auf Weiß gesetzt, quadratisch. |
| *Aufgeräumt* | Das Foto bleibt, wie es ist; Störendes im Hintergrund wird wegretuschiert. |

Freigestellt wird auf deinem Rechner, mit einem offenen Modell, das beim
ersten Gebrauch heruntergeladen wird. Die Pixel des Gegenstands sind die aus
deinem Foto: Nichts wird neu gezeichnet, geglättet oder umgefärbt, das Bild
bleibt also ein ehrliches von dem, was du verkaufst. Nur *Aufgeräumt* fragt
den KI-Anbieter, wo Störendes liegt, und retuschiert diese Stellen lokal.

Die Bilder hier zeigen eine Demo-Instanz mit gezeichneten Gegenständen;
`python tools/demo.py` startet dieselbe, ohne Anbieter und ohne Modell.

## Wege, es zu benutzen

| | Für wen | Läuft |
|---|---|---|
| [1. Der Download](#1-der-download-windows-und-macos) | Du willst es ausprobieren oder auf dem eigenen Computer benutzen | solange sein Fenster offen ist |
| [2. Docker](#2-docker-auf-einem-nas-oder-heimserver) | Der Haushalt soll es jederzeit erreichen, von jedem Handy | immer, auf einem NAS oder Heimserver |
| [3. Python](#3-mit-python) | Du hast Python und willst keins von beiden | solange der Befehl läuft |

Alle drei sind dieselbe App mit denselben Funktionen. In jedem Fall brauchst
du zusätzlich einen [KI-Anbieter](#ki-anbieter): Von selbst schreibt Trödel
nichts.

### Voraussetzungen

- **Der Download:** Windows 10 oder 11 (64-Bit), oder macOS 11 und neuer auf
  einem Mac mit Apple-Chip (M1 und neuer; Intel-Macs werden nicht
  unterstützt). Etwa 700 MB Speicherplatz. Sonst muss nichts installiert
  sein, kein Python und kein Docker.
- **Docker:** jede Maschine, auf der Docker mit Compose läuft, 64-Bit
  Intel/AMD oder ARM: ein NAS von Synology oder QNAP, ein Raspberry Pi 4 oder
  5, ein PC.
- **Python:** Version 3.12 oder neuer, unter Linux, macOS oder Windows.
- **Für alle:** ein aktueller Browser und ein Konto oder Schlüssel bei einem
  der [KI-Anbieter](#ki-anbieter), oder ein lokales Modell mit Ollama. Die
  Fotobearbeitung lädt ihre Modelle beim ersten Gebrauch herunter (ein paar
  hundert MB, einmalig, braucht Internet); Anzeigen schreiben geht auch ohne.

### 1. Der Download (Windows und macOS)

Von der [Release-Seite](https://github.com/tk-void/troedel/releases):

- **Windows:** `troedel-<version>-windows-x64-setup.exe`. Ausführen; es
  installiert nur für dein Benutzerkonto und fragt nach keinem
  Administrator-Passwort. Danach *Trödel* im Startmenü öffnen.
- **macOS:** `troedel-<version>-macos-arm64.dmg`. Öffnen, *Troedel* in
  *Programme* ziehen und von dort starten.

Die Downloads sind nicht signiert, deshalb warnt das System einmal. Windows:
*Weitere Informationen* → *Trotzdem ausführen*. macOS: *Systemeinstellungen →
Datenschutz & Sicherheit → Dennoch öffnen*.

**Was beim Öffnen passiert:** Trödel startet einen kleinen Webserver auf
deinem Computer, erreichbar nur von diesem Computer, und öffnet ein Fenster,
das genau das sagt. Das Fenster zeigt die Adresse (`http://localhost:8099`)
und öffnet sie in deinem Browser; die eigentliche App ist diese Seite im
Browser. Beim allerersten Start zeigt das Fenster außerdem einen einmaligen
Einrichtungscode: im Browser eintippen und ein Passwort wählen. Im System
wird nichts verankert, kein Dienst läuft weiter: Fenster schließen beendet
Trödel.

**Vom Handy aus:** im Fenster *Im Heimnetz freigeben* ankreuzen. Es zeigt
dann die Adresse für andere Geräte im selben WLAN und einen QR-Code zum
Scannen. Nur in einem Netz einschalten, das dir gehört.

**Wo deine Daten liegen:** im Ordner `Troedel` in deinem Benutzerordner
(`C:\Users\<du>\Troedel`, `/Users/<du>/Troedel`), getrennt vom Programm. Das
Fenster nennt den Ordner und öffnet ihn. Eine neue Version wird über die alte
installiert und findet dort alles wieder; Deinstallieren lässt den Ordner in
Ruhe. Was darin liegt: [Deine Daten](#deine-daten).

Unter Windows lieber nichts installieren? `troedel-<version>-windows-x64.zip`
ist dasselbe Programm als Ordner: entpacken und `Troedel.bat` doppelklicken.

### 2. Docker (auf einem NAS oder Heimserver)

Für ein Trödel, das immer läuft und das zu Hause jeder vom Handy öffnet. Das
hier als `compose.yaml` in einem eigenen Ordner speichern:

```yaml
services:
  troedel:
    image: ghcr.io/tk-void/troedel:latest
    restart: unless-stopped
    ports:
      - "8099:8099"
    user: "1000:1000"        # Besitzer von ./data: siehe `id -u` und `id -g`
    volumes:
      - ./data:/data         # hier liegen Anzeigen, Fotos und Einstellungen
    read_only: true
    tmpfs:
      - /tmp
```

```bash
mkdir -p data
docker compose up -d
docker compose logs troedel     # zeigt den einmaligen Einrichtungscode
```

Dann von jedem Gerät im Netz `http://<Adresse dieser Maschine>:8099` öffnen,
den Einrichtungscode eingeben, ein Passwort wählen und in den Einstellungen
einen KI-Anbieter aussuchen. Auf einem Synology- oder QNAP-NAS kommt dieselbe
Datei als Projekt in den *Container Manager* bzw. die *Container Station*;
der Einrichtungscode steht dort im Protokoll des Containers.

Das ist unverschlüsseltes HTTP in deinem Netz. Den Port nicht ins Internet
weiterleiten; für Zugriff von außen hat [docs/security.md](docs/security.md)
ein Beispiel mit HTTPS davor.

Das Image lieber selbst bauen? Dieses Repository klonen und darin
`docker compose up -d --build` ausführen. Seine `compose.yaml` ist dieselbe
Datei mit mehr Kommentaren.

### 3. Mit Python

```bash
pipx install "troedel[cutout] @ git+https://github.com/tk-void/troedel.git"
troedel --open                   # http://127.0.0.1:8099, Daten in ./data
```

Ohne `[cutout]` wird die Installation viel kleiner, dann ohne
Fotobearbeitung. Um es vom Handy zu erreichen, mit `--host 0.0.0.0` starten
und vorher [docs/security.md](docs/security.md) lesen. `troedel window` (mit
dem Extra `desktop`) startet dasselbe Fenster wie die Downloads.

## KI-Anbieter

Gewählt wird in den Einstellungen; Einzelheiten und Abwägungen stehen in
[docs/providers.md](docs/providers.md).

| Anbieter | Braucht | Fotos gehen an |
|---|---|---|
| Claude (Anthropic API) | API-Schlüssel, Bezahlung nach Verbrauch | Anthropic |
| Gemini | API-Schlüssel; hat eine kostenlose Stufe, auf der Google deine Inhalte zur Verbesserung seiner Produkte nutzen darf | Google |
| OpenAI | API-Schlüssel, ein Modell mit Bildverständnis | OpenAI |
| Ollama | ein lokales Modell mit Bildverständnis | niemanden, sie bleiben auf deinem Rechner |
| Jeder OpenAI-kompatible Dienst | Adresse, Modell, eventuell ein Schlüssel | diesen Dienst |
| Claude Code CLI (experimentell) | das Programm `claude`, angemeldet auf derselben Maschine; im Docker-Image nicht verfügbar | Anthropic |

Je Artikel gehen bis zu vier Fotos hinaus, verkleinert und ohne Metadaten.
Die Fotobearbeitung nutzt nie einen Anbieter, außer bei *Aufgeräumt*: Dort
wird er gefragt, wo Störendes liegt; retuschiert wird lokal.

## Deine Daten

Alles liegt in einem Ordner: `./data` (`/data` im Container) oder, bei den
Downloads, im Ordner `Troedel` in deinem Benutzerordner.

```
data/
  troedel.db      Anzeigen, Einstellungen, Sitzungen (SQLite)
  photos/         Originale, bearbeitete Looks, Masken
  models/         beim ersten Gebrauch geladen: Modelle fürs Freistellen und Retuschieren
  secrets.json    der API-Schlüssel, falls du einen in den Einstellungen eingetragen hast
```

**Sichern:** den Ordner kopieren, oder über *Einstellungen → Export* ein ZIP
mit Datenbank und Originalfotos holen (ohne den API-Schlüssel). `models/`
kann wegbleiben; es wird neu geladen.

## Sicherheit in Kürze

- Ohne Anmeldung wird nichts ausgeliefert. Das erste Passwort lässt sich nur
  mit einem einmaligen Code setzen, den der Server beim Start anzeigt.
- Passwörter werden als Argon2id-Hash gespeichert, Sitzungen nur als Hash,
  Anmeldeversuche werden gebremst.
- Trödel spricht unverschlüsseltes HTTP. In einem Netz, dem du vertraust, ist
  das ein vertretbarer Kompromiss; überall sonst gehört HTTPS davor. Es ist
  **nicht dafür gebaut, offen im Internet zu stehen.**

Das ganze Bild, mit einem HTTPS-Beispiel: [docs/security.md](docs/security.md).
Eine Sicherheitslücke melden: [SECURITY.md](SECURITY.md).

## Die Ausfüllhilfe (optional, experimentell)

Ein Userscript, das im eigenen Browser das Anzeigenformular bei Kleinanzeigen
und Vinted ausfüllt. Es ist standardmäßig aus, schickt nie etwas ab und kann
gegen die Nutzungsbedingungen einer Plattform verstoßen. Vor dem Einschalten
[docs/fill-helper.md](docs/fill-helper.md) lesen.

## Konfiguration

Alles, was man im Alltag ändert, steht in der App. Über die Umgebung wird
gesetzt, was zur Installation gehört; siehe
[docs/configuration.md](docs/configuration.md).

## Mitmachen

Issues und Pull Requests sind willkommen, bitte auf Englisch; los geht es mit
[CONTRIBUTING.md](CONTRIBUTING.md). Das ist ein Freizeitprojekt: Bitte rechne
nicht mit schnellen Antworten, und rechne damit, dass die plattformspezifischen
Teile brechen, sobald eine Plattform etwas ändert.

## Lizenz

[MIT](LICENSE). Mitgelieferte und nachgeladene Teile Dritter:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Trödel steht in keiner Verbindung zu Kleinanzeigen, Vinted, eBay, Meta,
Anthropic, Google oder OpenAI und wird von ihnen weder unterstützt noch
empfohlen. Ihre Namen werden nur genannt, um zu sagen, womit die Software
zusammenarbeitet.
