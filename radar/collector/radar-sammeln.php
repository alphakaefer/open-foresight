<?php
/**
 * Zukunftsradar: freie Quellen abrufen, mit dem letzten Stand zusammenfuehren,
 * Abgelaufenes entfernen, Trends bilden - und radar/wissensstand.json
 * schreiben, die die App liest (Format: src/lib/radar/typen.ts).
 *
 * PHP statt Node, weil es auf dem Webspace laufen soll und der Webspace nur
 * PHP kennt. Ein Cronjob im KAS ruft einmal am Tag die URL auf:
 *
 *   https://zukunftsgut.org/api/radar-sammeln.php
 *
 * und stuendlich nur die Nachrichten (Nachrichtenlauf, siehe unten):
 *
 *   https://zukunftsgut.org/api/radar-sammeln.php?nachrichten
 *
 * Ohne Schluessel, dafuer mit Mindestabstand: ueber das Netz sammelt die Seite
 * hoechstens alle 6 Stunden, jeder weitere Aufruf bekommt nur den Stand
 * gemeldet. So kann niemand die Quellen im Sekundentakt abfragen lassen, und
 * die Cron-URL ist kein Geheimnis, das irgendwo gehuetet werden muesste.
 * Auf dem eigenen Rechner oder per SSH (ohne Mindestabstand):
 *
 *   php radar-sammeln.php [--ziel ../public/radar/wissensstand.json]
 *
 * Der Destatis-Token steht in studio-config.php oberhalb des Web-Roots (wie die
 * Datenbank beim Teilen): 'radar' => ['destatis_token' => '...'] - eintragen mit
 * scripts/radar-einrichten.sh. Ohne Token fehlen nur die amtlichen Zahlen.
 *
 * Jeder Lauf baut auf dem vorigen auf: Meldungen bleiben, bis sie abgelaufen
 * sind; Zeitreihen ersetzen sich, der neue Wert gilt. Faellt eine Quelle aus,
 * bleibt stehen, was sie beim letzten Mal lieferte.
 *
 * Von Nachrichten wird nur Titel, Anriss und Link genommen, nie der Artikel.
 */

declare(strict_types=1);

/** Halbwertszeit je Art in Tagen - dieselben Werte wie src/lib/radar/frische.ts. */
const HALBWERTSZEIT_TAGE = ['nachricht' => 10, 'umfrage' => 30, 'messung' => 30, 'forschung' => 120, 'statistik' => 365, 'parlament' => 45];
/** Unter einem Achtel (drei Halbwertszeiten) ist ein Fund abgelaufen. */
const ABGELAUFEN = 0.125;
/** So weit reicht der Nachrichtenstrom zurueck - genug fuer "mehr als in der Woche davor". */
const TAGE_ZURUECK = 14;
/** Mit Kontaktseite - Wikimedia verlangt das und drosselt sonst. */
define('ABSENDER', getenv('RADAR_USER_AGENT') ?: 'open-foresight-radar/1.0 (+https://github.com/alphakaefer/open-foresight)');
const TAG = 86400;
/**
 * Ueber das Netz nie oefter als alle 6 Stunden. Frueher 20 - dann blockierte ein
 * Lauf von Hand am Abend den Cron am naechsten Morgen (28.09.2026: 05:30 fiel aus,
 * weil am Vorabend um 20:21 gesammelt worden war).
 */
const MINDESTABSTAND = 6 * 3600;
/**
 * Der Nachrichtenlauf (?nachrichten) holt nur die Nachrichtenquellen - fuer den
 * stuendlichen Cron und den Abruf von Hand auf der Seite (Karl, 08.10.2026:
 * "der Abruf von Nachrichten sollte regelmaessiger geschehen"). Er ist in
 * Sekunden durch und schont die Kontingente von OpenAlex, Destatis und Co.
 */
const MINDESTABSTAND_NACHRICHTEN = 20 * 60;

// ---- WETTER-KONSTANTEN-ANFANG ----
// Hier oben, nicht beim Wetter: ein const wird erst ausgefuehrt, wenn der Ablauf es erreicht, und der Lauf braucht sie schon vorher.

/** Nur Ort oder Institution oder Meldungsart - Kulisse, kein Thema (Trends im Nachrichtenstrom und Wetter). */
const KULISSE = ['deutschland', 'berlin', 'usa', 'eu', 'europa', 'europäische union', 'bundesregierung', 'bundestag', 'bundesrat',
    'reform', 'politik', 'wirtschaft', 'welt', 'international', 'nachrichten', 'liveblog', 'interview', 'kommentar', 'marktbericht'];

// Wetter (radar/wetter.json): Schwellen sind eine Darstellungsregel, kein Urteil.
/** Deutschsprachige Nachrichtenquellen: Boeen und Fronten sprechen ueber deutsche Woerter. BBC und Al Jazeera brachten "after", "says", "government" hinein. Neue deutsche Quelle hier eintragen. */
const WETTER_QUELLEN = ['tagesschau', 'dlf', 'handelsblatt', 'heise', 'golem', 'pv-magazine', 'klimareporter', 'personalwirtschaft',
    'dlf-forschung', 'wissenschaft-de', 'mpg', 'smc', 'idw', 'spektrum', 'scinexx', 'spiegel-wissenschaft', 'helmholtz'];
/**
 * Die Redaktion, deren Schlagworte Begriffe sind und deren Anriss zum Thema passt (bei den anderen zaehlt nur der Titel).
 */
const WETTER_SCHLAGWORTE = 'tagesschau';
/** Die sechs Regionen: STEEP-Ebene -> Alltagsname, Wissenschaft seit 17.10.2026 am Ende. */
const WETTER_REGIONEN = ['gesellschaft' => 'Gesellschaft', 'technologie' => 'Technik', 'wirtschaft' => 'Wirtschaft', 'umwelt' => 'Umwelt', 'politik' => 'Politik', 'wissenschaft' => 'Wissenschaft'];
/** Eine Boee: Woche geteilt durch das Mittel der vier Vorwochen mindestens so gross, mit mindestens so vielen Meldungen, hoechstens so viele je Region. */
const WETTER_BOE_FAKTOR = 5;
const WETTER_BOE_MELDUNGEN = 10;
const WETTER_BOEN_MAX = 6;
/** Die Quellen mit Vorgeschichte muessen zusammen mindestens so oft darueber berichten - sonst traegt eine einzelne Meldung den Faktor. */
const WETTER_BEZUG_MIN = 4;
const WETTER_VORWOCHEN = 4;
/** Eine Vorwoche ist brauchbar, wenn die Quelle darin mindestens halb so viel meldete wie in dieser Woche; eine Quelle zaehlt ab zwei brauchbaren Vorwochen. */
const WETTER_VORWOCHE_ANTEIL = 0.5;
const WETTER_VORWOCHEN_MIN = 2;
/**
 * Titel, die keine Entwicklung sind, sondern Kaufberatung, Test, Bildergalerie oder Rubrik (heise, Golem): sie bleiben schon beim
 * Sammeln draussen und zaehlen im Wetter nicht mit - sonst ruecken Produktzyklen als Boeen nach vorn.
 */
const WETTER_RAUSCHEN = '/fotonews|bilder der woche|#tgiqf|\\bquiz\\b|so funktioniert es|pc-spiele|neue spiele|im kino\\b|ratgeber|häppchen|vorbestellung|ausverkauft'
    . '|liefertermin|hands-?on|erster eindruck|unboxing|kurz notiert|wochenrückblick|schnäppchen|black friday|prime day|vergleichstest|\\bdeals?\\b'
    . '|^wetter\\s+-|^interview der woche/iu';
/** Hauptwoerter, die in jeder Meldung stehen koennen und nichts benennen - als Begriff fuer eine Boee nicht gemeint. */
const WETTER_FLOSKELN = ['studie', 'studien', 'forschung', 'forscher', 'forschende', 'forscherinnen', 'wissenschaft', 'wissenschaftler', 'wissenschaftlerinnen',
    'universität', 'hochschule', 'institut', 'milliarden', 'millionen', 'dollar', 'prozent', 'euro', 'kritik', 'bericht', 'warnung', 'update', 'neues',
    'jetzt', 'analyse', 'ergebnis', 'ergebnisse', 'untersuchung', 'entwicklung', 'menschen', 'unternehmen', 'wissenschaftsmeldungen',
    'künstliche', 'intelligenz', 'branche', 'technologie', 'mitarbeiter', 'modelle', 'deutsche'];
/**
 * Boeen je Region: Quellen ohne Vorwochen (heise, Golem und die jungen Wissenschaftsquellen) koennen keinen Faktor liefern. Hat eine Region
 * weniger Boeen, kommen ihre staerksten Begriffe der Woche dazu, bis sie so viele hat. Ein Begriff braucht mindestens so viele Meldungen,
 * dazu knapp ein Drittel der Wurzel aus dem Volumen der Region (Wissenschaft 50 Meldungen: 4, Umwelt 170: 4, Technik 550: 8, Politik 1500: 12),
 * aus mindestens so vielen Quellen, davon mindestens dieser Anteil in den letzten Tagen. Ohne Faktor (null). Kandidaten sind auch die
 * Wortanfaenge aus dem Themenkatalog ("Solar" trifft Solarpaket und Solar-Aufschlag): in duennen Regionen steht kaum ein ganzes Wort oft genug.
 */
const WETTER_REGION_MIN = 3;
const WETTER_REGION_MELDUNGEN = 4;
const WETTER_REGION_WURZEL = 0.3;
const WETTER_REGION_QUELLEN = 2;
const WETTER_REGION_JUNG_TAGE = 3;
const WETTER_REGION_JUNG_ANTEIL = 0.5;
/** Ein Begriff gehoert einer Region, wenn mindestens dieser Anteil seiner Meldungen dort steht ("Hersteller" und "Fehler" stehen ueberall). */
const WETTER_REGION_KONZENTRATION = 0.6;
/**
 * Trends (art "trend", Karl 17.10.2026: jede Region soll etwas Bewegtes zeigen): hat eine Region weniger als WETTER_REGION_MIN Boeen, kommen bis dahin
 * hoechstens WETTER_TREND_MAX Begriffe dazu, die ueber zwei Wochen stetig zunehmen statt zu springen. Gezaehlt wird nur in Quellen mit brauchbarer
 * Vorwoche (sonst ist jeder Begriff "gestiegen"), mit der Mindestmenge der Region; die Vorwoche braucht mindestens WETTER_TREND_VORWOCHE_MIN
 * Meldungen, die Woche muss um die Luftdruck-Schwelle steigen (wetterRichtung), an mindestens WETTER_TREND_TAGE Tagen vorkommen, und kein
 * Tag darf mehr als WETTER_TREND_SPITZE der Wochenmeldungen tragen (das waere ein Sprung, kein Trend).
 */
const WETTER_TREND_MAX = 2;
const WETTER_TREND_VORWOCHE_MIN = 2;
const WETTER_TREND_TAGE = 4;
const WETTER_TREND_SPITZE = 0.4;
/** Zeitangaben sind keine Begriffe ("im September", "am Mittwoch"). */
const WETTER_ZEIT = ['januar', 'februar', 'märz', 'april', 'mai', 'juni', 'juli', 'august', 'september', 'oktober', 'november', 'dezember',
    'montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag', 'samstag', 'sonntag', 'wochenende', 'jahresende', 'woche'];
/** Titelwoerter sind Begriffe, wenn sie gross geschrieben und mindestens so lang sind; ein Kandidat muss in so vielen Meldungen der Woche stehen. */
const WETTER_WORT_LAENGE = 5;
const WETTER_KANDIDAT_MIN = 3;
/** Tage im Verlauf und Rueckblick fuer Beginn und Dauer. */
const WETTER_VERLAUF_TAGE = 14;
const WETTER_RUECKBLICK_TAGE = 42;
/** Zwei Begriffe, deren Wochenmeldungen sich zu diesem Anteil decken, sind eine Boee. */
const WETTER_UEBERLAPP = 0.6;
/** Beginn und Halbwertszeit: ein Tag zaehlt zur Boee ab diesem Anteil ihres Gipfels; die Zahl halbiert sich bei diesem Anteil. */
const WETTER_TAGESANTEIL = 0.25;
const WETTER_HALB = 0.5;
/** Luftdruck: Aenderung zur Vorwoche mindestens so gross (absolut, relativ) - sonst "gleich". */
const WETTER_GLEICH_MIN = 3;
const WETTER_GLEICH_ANTEIL = 0.25;
/** Fronten: mindestens so viele gemeinsame Meldungen in der Woche, mindestens so viel mehr als bei Zufall, hoechstens so viele. */
const WETTER_FRONT_MIN = 5;
const WETTER_FRONT_UEBER_ZUFALL = 1.5;
const WETTER_FRONTEN_MAX = 8;
/** Begriffe einer Front (Karl, 18.10.2026: sie sollen sagen, worum es geht): hoechstens so viele, jeder in mindestens so vielen gemeinsamen Meldungen der Woche. */
const WETTER_FRONT_BEGRIFFE_MAX = 4;
const WETTER_FRONT_BEGRIFF_MIN = 2;
/**
 * Saison (Karl, 17.10.2026: mehr Zeitskalen, zwischen Wetterlage und Klima): die Groessen, die sich ueber vier bis zwoelf Wochen am staerksten
 * bewegen - Messreihen, Wikipedia-Aufmerksamkeit (Wochenwerte) und Themen in den Meldungen (vier Wochen). Bewegung = Veraenderung im Fenster
 * (WETTER_SAISON_WOCHEN; mindestens WETTER_SAISON_MIN_TAGE zwischen erstem und letztem Punkt, bei Wochenwerten also vier Wochen Daten) geteilt durch den Spielraum der Reihe (Spanne der letzten WETTER_SAISON_SPIELRAUM
 * Punkte); ab WETTER_SAISON_MIN gilt sie als Richtung, darunter als stabil. Je Region hoechstens WETTER_SAISON_JE_REGION Groessen, aus einer Quelle
 * hoechstens WETTER_SAISON_JE_QUELLE (sieben Umfragewerte sind eine Quelle); hat eine Region weniger als WETTER_SAISON_MINDEST, kommen die
 * naechstbesten als "stabil" dazu. Eine Reihe, deren letzter Punkt aelter ist als WETTER_SAISON_ALTER_TAGE (Quartalsreihen +90), ist keine Saison mehr.
 * Themen in den Meldungen: mindestens WETTER_SAISON_MELDUNGEN in den vier Wochen, keine Woche mit mehr als WETTER_SAISON_SPITZE davon (das ist eine
 * Boee, keine Saison). Harte Zahlen zuerst: die WETTER_SAISON_REIHEN staerksten Messreihen einer Region stehen vor Aufmerksamkeit und Meldungen.
 * WETTER_SAISON_PUNKTE: wie viele Punkte der Verlauf zeigt.
 */
const WETTER_SAISON_WOCHEN = 12;
const WETTER_SAISON_MIN_TAGE = 21;
const WETTER_SAISON_MIN = 0.35;
const WETTER_SAISON_JE_REGION = 4;
const WETTER_SAISON_MINDEST = 2;
const WETTER_SAISON_JE_QUELLE = 2;
const WETTER_SAISON_SPIELRAUM = 24;
const WETTER_SAISON_ALTER_TAGE = 150;
const WETTER_SAISON_MELDUNGEN = 12;
const WETTER_SAISON_SPITZE = 0.6;
const WETTER_SAISON_REIHEN = 2;
const WETTER_SAISON_PUNKTE = ['woche' => 16, 'monat' => 7, 'quartal' => 5];
/**
 * Wortanfaenge, die als Verb etwas anderes heissen: "Erde steuert auf 2,8 Grad" stand unter Haushalt und Steuern
 * (Persona-Durchlauf 22.10.2026). Je Wort ein Blick nach vorn, der diese Endungen ausschliesst; "Steuern" bleibt.
 */
const THEMA_SPERREN = ['steuer' => '(?!(?:te?n?|nde?n?)(?!\p{L})|ung)'];
/** Beispiele und Titel fuer ein Thema: Meldungen mit so vielen verschiedenen Woertern des Themas kommen zuerst (ein Wort trifft oft nebenbei). */
const WETTER_THEMA_WOERTER = 2;
// ---- WETTER-KONSTANTEN-ENDE ----

/**
 * Themenfelder: wo Nachrichten, Kennzahlen und Forschung zusammenkommen.
 *
 * Karl, 27.09.2026: Publikationszahlen allein sagen wenig - durch KI waechst
 * die Publikationsrate ueberall. Relevanz geben die Nachrichten und die
 * wirtschaftlichen und gesellschaftlichen Entwicklungen vor; Forschung ist die
 * Tiefe dazu. Also: je Feld zaehlen die tagesschau-Meldungen (Gewicht), dazu
 * die passenden Kennzahlen und neue Studien.
 *
 * 'de': Wortanfaenge fuer die Nachrichten (bis drei Buchstaben nur als ganzes
 * Wort). 'en': Suche in OpenAlex; ihre Woerter ab fuenf Buchstaben verbinden
 * auch arXiv-Papers mit dem Feld (mindestens zwei muessen treffen).
 * 'reihen': ids aus dem Wissensstand, mit * am Ende als Praefix.
 */
const THEMENFELDER = [
    ['ki-arbeit', 'KI und Arbeitswelt', 'wirtschaft', ['KI', 'Künstliche Intelligenz', 'Automatisierung', 'Stellenabbau', 'Arbeitsmarkt', 'Jobverlust'],
        'artificial intelligence employment labor market', ['destatis-ki-unternehmen', 'eurostat-arbeitslosigkeit']],
    ['ki-sicherheit', 'KI-Sicherheit und Regulierung', 'technologie', ['OpenAI', 'KI-Agent', 'KI-Sicherheit', 'Chatbot', 'AI Act', 'KI-Regulierung', 'KI-Modell'],
        'AI safety governance regulation', []],
    ['energie', 'Energie und Strompreise', 'umwelt', ['Energiewende', 'Strompreis', 'Erneuerbar', 'Windkraft', 'Windenergie', 'Solar', 'Wärmepumpe', 'Gaspreis', 'Netzentgelt'],
        'energy transition renewable electricity prices', ['energy-charts-erneuerbare']],
    ['klima', 'Klimawandel und Extremwetter', 'umwelt', ['Klima', 'Hitze', 'Dürre', 'Hochwasser', 'Unwetter', 'Waldbrand', 'Starkregen', 'Erderwärmung'],
        'climate change extreme weather adaptation', []],
    ['preise', 'Preise und Kaufkraft', 'wirtschaft', ['Inflation', 'Teuerung', 'Spritpreis', 'Lebensmittelpreis', 'Kaufkraft', 'Zinsen', 'EZB', 'Verbraucherpreis'],
        'inflation cost of living households', ['destatis-inflation']],
    ['industrie', 'Industrie und Standort', 'wirtschaft', ['Industrie', 'Autoindustrie', 'Autobauer', 'Insolvenz', 'Stellenabbau', 'Standort', 'Chemie', 'Werksschließung'],
        'manufacturing industry competitiveness Germany', ['destatis-produktion', 'destatis-insolvenzen']],
    ['handel', 'Handel und Zölle', 'wirtschaft', ['Zoll', 'Zölle', 'Handelsstreit', 'Handelskonflikt', 'Export', 'Freihandel'],
        'international trade tariffs', []],
    ['demokratie', 'Demokratie und Parteien', 'politik', ['AfD', 'Rechtsextrem', 'Demokratie', 'Landtagswahl', 'Bundestagswahl', 'Koalition', 'Umfragewert', 'Polarisierung'],
        'democracy polarization populism', ['dawum-*']],
    ['sicherheit', 'Sicherheit und Verteidigung', 'politik', ['Bundeswehr', 'Wehrpflicht', 'Wehrdienst', 'NATO', 'Verteidigung', 'Aufrüstung', 'Drohne', 'Ukraine', 'Russland'],
        'European security defense policy', []],
    ['geopolitik', 'USA, China und die Weltordnung', 'politik', ['Trump', 'China', 'Xi Jinping', 'Weltordnung', 'UN-Generalversammlung', 'Sanktion'],
        'geopolitics United States China rivalry', []],
    ['migration', 'Migration und Integration', 'gesellschaft', ['Migration', 'Asyl', 'Flüchtling', 'Geflüchtete', 'Integration', 'Abschiebung', 'Einwanderung'],
        'migration integration refugees Europe', []],
    ['gesundheit', 'Gesundheit und Pflege', 'gesellschaft', ['Pflege', 'Krankenhaus', 'Gesundheit', 'Krankenkasse', 'Klinik', 'Ärzte'],
        'health care system nursing care reform', []],
    ['rente', 'Rente und Demografie', 'gesellschaft', ['Rente', 'Renten', 'Demografie', 'Fachkräftemangel', 'Fachkräfte', 'Altersvorsorge'],
        'pension reform population ageing labor shortage', []],
    ['bildung', 'Bildung und Schule', 'gesellschaft', ['Schule', 'Bildung', 'Kita', 'Lehrkräfte', 'Lehrer', 'Studium', 'Hochschule'],
        'education schools learning outcomes', []],
    ['wohnen', 'Wohnen und Mieten', 'gesellschaft', ['Miete', 'Mieten', 'Wohnung', 'Wohnungsbau', 'Wohnungsnot', 'Mietpreis'],
        'housing affordability rents', []],
    ['desinformation', 'Desinformation und Plattformen', 'gesellschaft', ['Desinformation', 'Fake', 'Deepfake', 'Social Media', 'TikTok', 'Plattform', 'Propaganda'],
        'misinformation social media platforms', []],
    ['cyber', 'Cybersicherheit', 'technologie', ['Cyber', 'Hacker', 'Hackerangriff', 'IT-Sicherheit', 'Datenleck', 'Ransomware'],
        'cybersecurity cyber attacks', []],
    // Technologie beleben und Wissenschaft als sechster Bereich (Karl, 17.10.2026). Die Woerter stehen so, dass sich keine zwei Felder
    // dieselben Meldungen teilen (OpenAI, Chatbot und KI-Modell gehoeren zu ki-sicherheit, Hochschule zu bildung) - sonst meldete
    // das Wetter jede Ueberschneidung als Front.
    ['ki-modelle', 'KI-Modelle und Anbieter', 'technologie', ['Anthropic', 'Gemini', 'ChatGPT', 'Sprachmodell', 'Open-Weight', 'Mistral', 'Copilot', 'DeepSeek', 'Llama', 'Grok', 'KI-Update'],
        'large language models foundation models', []],
    ['chips', 'Chips und Rechenzentren', 'technologie', ['Chip', 'Halbleiter', 'Nvidia', 'TSMC', 'ASML', 'Rechenzentr', 'GPU', 'Prozessor', 'Supercomputer', 'Mikrochip'],
        'semiconductor chips data centers computing', []],
    ['digitalpolitik', 'Digitalpolitik und Datenschutz', 'technologie', ['Datenschutz', 'DSGVO', 'Chatkontrolle', 'Vorratsdaten', 'Digitalgesetz', 'Digitalministerium', 'Digitalpolitik',
        'Digitalsteuer', 'Digital Services Act', 'Digital Markets Act', 'Gesichtserkennung', 'Überwachung'],
        'data protection digital regulation privacy', []],
    ['robotik', 'Robotik und autonomes Fahren', 'technologie', ['Roboter', 'Robotik', 'Humanoid', 'Robotaxi', 'Waymo', 'selbstfahrend', 'autonomes Fahren', 'autonome Fahr', 'Fahrassistent', 'Autopilot'],
        'robotics autonomous vehicles', []],
    ['raumfahrt', 'Raumfahrt und Satelliten', 'technologie', ['Raumfahrt', 'Raketenstart', 'Trägerrakete', 'Starlink', 'Satellit', 'SpaceX', 'Starship', 'Weltraum', 'Mondmission', 'Artemis', 'ESA', 'NASA', 'Raumsonde'],
        'space exploration satellites launch', []],
    ['netze', 'Netze und Mobilfunk', 'technologie', ['Glasfaser', 'Mobilfunk', '5G', '6G', 'Telekom', 'Breitband', 'Funkloch', 'Vodafone'],
        'telecommunications 5G network infrastructure', []],
    ['medizin', 'Medizin und Impfstoffe', 'wissenschaft', ['Impfstoff', 'Impfung', 'Krebs', 'Therapie', 'Wirkstoff', 'Antibiot', 'Alzheimer', 'Diabetes', 'Virus', 'Medikament'],
        'vaccine clinical trial therapy', []],
    ['astronomie', 'Astronomie und Physik', 'wissenschaft', ['Teleskop', 'Astronom', 'Exoplanet', 'Schwarzes Loch', 'Schwarze Löcher', 'Urknall', 'CERN', 'Teilchenphysik', 'Gravitationswelle', 'Galaxie',
        'Sonnensystem', 'Quanten', 'Supernova', 'Kosmos'],
        'astrophysics particle physics quantum', []],
    ['biotech', 'Biotechnologie und Gentechnik', 'wissenschaft', ['CRISPR', 'Gentechnik', 'Genom', 'genetisch', 'DNA', 'Biotech', 'Stammzell', 'Embryo', 'Genschere', 'Mikrobiom', 'Protein'],
        'gene editing biotechnology genomics', []],
    ['erdsystem', 'Erdsystem und Artenvielfalt', 'wissenschaft', ['Ozean', 'Meeresspiegel', 'Gletscher', 'Eisschild', 'Permafrost', 'Korallen', 'Antarktis', 'Arktis', 'Atmosphär', 'Vulkan', 'Erdbeben',
        'Artenvielfalt', 'Biodiversität', 'Artensterben'],
        'ocean ice sheet biodiversity earth system', []],
    ['forschungspolitik', 'Forschungspolitik und Hochschulen', 'wissenschaft', ['Forschungspolitik', 'Forschungsförderung', 'Forschungsministerium', 'Forschungsetat', 'Exzellenzstrategie',
        'Wissenschaftsfreiheit', 'Wissenschaftsrat', 'DFG', 'Hightech Agenda', 'Max-Planck', 'Fraunhofer', 'Helmholtz', 'Leibniz', 'Nobelpreis', 'Hochschulpolitik', 'Hochschulfinanz',
        'Wissenschaftsstandort', 'Forschungsstandort'],
        'research policy funding universities', []],
    ['urgeschichte', 'Urgeschichte und Evolution', 'wissenschaft', ['Neandertaler', 'Archäolog', 'Urmensch', 'Evolution', 'Fossilien', 'Dinosaur', 'Steinzeit', 'Paläo'],
        'human evolution archaeology paleontology', []],
    // Jede Region mindestens vier bis fuenf lebende Themen (Karl, 17.10.2026: Umwelt neben Politik sah traurig aus). Gewaehlt nach den
    // Meldungen der Woche; ohne englische Suche ('') fragt der Sammler OpenAlex nicht - das Feld lebt von den Nachrichten.
    ['landwirtschaft', 'Landwirtschaft und Naturschutz', 'umwelt', ['Landwirt', 'Bauern', 'Ackerbau', 'Pestizid', 'Glyphosat', 'Dünger', 'Tierhaltung', 'Naturschutz', 'Artenschutz', 'Agrar', 'Ernte', 'Forstwirtschaft'],
        'agriculture nature conservation pesticides', []],
    ['wasser', 'Wasser und Gewässer', 'umwelt', ['Trinkwasser', 'Wasserversorgung', 'Grundwasser', 'Gewässer', 'Wasserknappheit', 'Niedrigwasser', 'Abwasser', 'Meeresschutz', 'Fischerei', 'Nordsee', 'Ostsee'],
        'water supply groundwater aquatic ecosystems', []],
    ['verkehr', 'Verkehr und Mobilität', 'umwelt', ['Bahn', 'Deutschlandticket', 'Nahverkehr', 'ÖPNV', 'Verkehrswende', 'Elektroauto', 'E-Auto', 'Ladesäule', 'Verbrenner', 'Flughafen', 'Tempolimit', 'Autobahn', 'Schiene', 'Radweg'],
        'sustainable transport electric mobility', []],
    ['kreislauf', 'Kreislaufwirtschaft und Müll', 'umwelt', ['Recycling', 'Kreislaufwirtschaft', 'Müll', 'Abfall', 'Plastik', 'Verpackung', 'Pfand', 'Rohstoff', 'Mehrweg'],
        'circular economy waste recycling', []],
    ['europa', 'Europa und die EU', 'politik', ['EU', 'Brüssel', 'Europäische Union', 'Kommission', 'Ratspräsident', 'Eurozone', 'Von der Leyen'], '', []],
    ['bundesregierung', 'Bundesregierung und Reformen', 'politik', ['Bundesregierung', 'Kanzler', 'Kabinett', 'Bundesrat', 'Minister', 'Reform', 'Gesetzentwurf', 'Koalitionsausschuss'], '', []],
    ['nahost', 'Nahost', 'politik', ['Israel', 'Gaza', 'Iran', 'Nahost', 'Hamas', 'Libanon', 'Syrien'], '', []],
    ['haushalt', 'Haushalt, Steuern und Schulden', 'politik', ['Haushalt', 'Steuer', 'Schulden', 'Sondervermögen', 'Schuldenbremse', 'Subvention'], '', []],
    ['boerse', 'Börse und Anleger', 'wirtschaft', ['Börse', 'Aktie', 'DAX', 'Wall Street', 'Anleger', 'Rendite', 'Anleihe', 'Dow Jones', 'Nasdaq'], '', []],
    ['banken', 'Banken und Geldanlage', 'wirtschaft', ['Bank', 'Sparkasse', 'Commerzbank', 'Unicredit', 'Kredit', 'Geldanlage', 'Versicherung', 'Kontobetrug'], '', []],
    ['arbeit', 'Arbeit, Löhne und Tarife', 'wirtschaft', ['Tarif', 'Streik', 'Gewerkschaft', 'Mindestlohn', 'Arbeitszeit', 'Kündigung', 'Betriebsrat', 'Gehalt', 'Arbeitslos'],
        'wages collective bargaining working hours', []],
    ['unternehmen', 'Unternehmen und Übernahmen', 'wirtschaft', ['Übernahme', 'Fusion', 'Gewinnwarnung', 'Quartalszahlen', 'Start-up', 'Mittelstand', 'Konzern', 'Pleite'], '', []],
    ['kriminalitaet', 'Kriminalität und Justiz', 'gesellschaft', ['Polizei', 'Kriminalität', 'Messer', 'Tatverdächtig', 'Anklage', 'Urteil', 'Festnahme', 'Mord'], '', []],
    ['familie', 'Familie, Frauen und Kinder', 'gesellschaft', ['Familie', 'Kinder', 'Eltern', 'Frauen', 'Gleichstellung', 'Elterngeld', 'Jugend', 'Senioren'],
        'family policy gender equality child wellbeing', []],
    ['religion', 'Kirche und Religion', 'gesellschaft', ['Papst', 'Kirche', 'Bischof', 'Islam', 'Moschee', 'Synagoge', 'Antisemitismus', 'Muslim'], '', []],
];

$web = PHP_SAPI !== 'cli';
$konfig = konfiguration() ?? [];

$ziel = option('--ziel') ?? __DIR__ . '/../radar/wissensstand.json';
$nurNachrichten = $web ? isset($_GET['nachrichten']) : in_array('--nachrichten', $argv ?? [], true);
/** Wann zuletzt alle Quellen liefen - der Nachrichtenlauf darf den vollen Lauf nicht verdraengen. */
$vollMarke = $ziel . '.voll';

if ($web) {
    header('Content-Type: text/plain; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    $letzter = is_file($ziel) ? (int) filemtime($ziel) : 0;
    // ?pruefen: nur melden, nie sammeln - fuer die Kontrolle nach dem Ausrollen.
    if (isset($_GET['pruefen'])) {
        echo $letzter ? 'Stand ' . gmdate('Y-m-d H:i', $letzter) . " UTC\n" : "Noch kein Stand\n";
        exit;
    }
    // Ohne Marke ist noch nie ein voller Lauf fertig geworden - dann darf einer laufen. Mit dem Stand der Nachrichtenlaeufe als
    // Ersatz kam er nie: sie frischen die Datei stuendlich auf (08. bis 15.10.2026 ohne vollen Lauf, die Statistiken standen still).
    $seit = $nurNachrichten ? $letzter : (is_file($vollMarke) ? (int) filemtime($vollMarke) : 0);
    $abstand = $nurNachrichten ? MINDESTABSTAND_NACHRICHTEN : MINDESTABSTAND;
    if (time() - $seit < $abstand) {
        printf("Stand ist aktuell (%s UTC). Nächster Lauf frühestens %s UTC.\n", gmdate('d.m. H:i', $seit), gmdate('d.m. H:i', $seit + $abstand));
        exit;
    }
    // Der Cronjob wartet nicht unbedingt, bis alles durch ist - weiterlaufen.
    ignore_user_abort(true);
    set_time_limit(300);
}
$destatisToken = getenv('DESTATIS_TOKEN') ?: (string) ($konfig['radar']['destatis_token'] ?? '') ?: keepass('GENESIS API') ?: keepass('Destatis GENESIS');
/**
 * OpenAlex rechnet seit 2026 nach Budget ab: ohne Schluessel teilen sich alle
 * auf derselben IP-Adresse ein kleines Tagesbudget - auf einem geteilten
 * Webspace ist das schnell weg. Mit Karls Schluessel ("OpenAlex Key" in
 * KeePassXC, auf dem Server radar.openalex_key) laeuft es ueber sein Budget.
 * Ein Lauf kostet rund 30 Abfragen, etwa 3 Cent.
 */
define('OPENALEX_SCHLUESSEL', getenv('OPENALEX_KEY') ?: (string) ($konfig['radar']['openalex_key'] ?? '') ?: keepass('OpenAlex Key'));
/** Bundestag, DIP (30.09.2026): "DIP Bundestag API" in KeePassXC, auf dem Server radar.dip_key. */
define('DIP_SCHLUESSEL', getenv('DIP_KEY') ?: (string) ($konfig['radar']['dip_key'] ?? '') ?: keepass('DIP Bundestag API'));

if (!is_dir(dirname($ziel))) {
    mkdir(dirname($ziel), 0755, true);
}
// Nie zwei Laeufe gleichzeitig - der zweite wuerde den ersten ueberschreiben.
$sperre = fopen(sys_get_temp_dir() . '/radar-' . md5((string) realpath(dirname($ziel))) . '.lock', 'c');
if ($sperre === false || !flock($sperre, LOCK_EX | LOCK_NB)) {
    echo "Läuft schon.\n";
    exit;
}

$alt = is_file($ziel) ? json_decode((string) file_get_contents($ziel), true) : null;
$jetzt = time();

$quellen = [];
$neueSignale = [];
$reihen = [];
$trends = [];
/** Welche Trends zu welcher Quelle gehoeren - fuer den Fall, dass sie ausfaellt. */
$trendPraefix = ['wikipedia' => 'aufmerksamkeit-', 'openalex' => 'forschung-'];

$alleQuellen = [
    ['tagesschau', 'tagesschau.de', 'https://www.tagesschau.de', 'nachricht', 'quelleTagesschau'],
    ['dlf', 'Deutschlandfunk', 'https://www.deutschlandfunk.de/nachrichten-100.html', 'nachricht', 'quelleDeutschlandfunk'],
    ['arxiv', 'arXiv', 'https://arxiv.org', 'forschung', 'quelleArxiv'],
    ['huggingface', 'Hugging Face Daily Papers', 'https://huggingface.co/papers', 'forschung', 'quelleHuggingface'],
    ['openalex-themen', 'OpenAlex (neue Studien je Themenfeld)', 'https://openalex.org', 'forschung', 'quelleOpenalexThemen'],
    ['openalex', 'OpenAlex (Forschungsumfang)', 'https://openalex.org', 'forschung', 'quelleOpenalex'],
    ['wikipedia', 'Wikipedia-Seitenaufrufe', 'https://pageviews.wmcloud.org', 'messung', 'quelleWikipedia'],
    ['destatis', 'Statistisches Bundesamt (GENESIS)', 'https://www-genesis.destatis.de', 'statistik', 'quelleDestatis'],
    ['eurostat', 'Eurostat', 'https://ec.europa.eu/eurostat', 'statistik', 'quelleEurostat'],
    ['dawum', 'DAWUM (Wahlumfragen)', 'https://dawum.de', 'umfrage', 'quelleDawum'],
    ['energy-charts', 'Energy-Charts (Fraunhofer ISE)', 'https://energy-charts.info', 'messung', 'quelleEnergyCharts'],
    // Fuer die drei Blickwinkel (Karl, 28.09.2026) - die tagesschau allein ist
    // zu politisch, zu Durchbruechen und zum Markt fuer Beratung kam kaum etwas.
    ['idw', 'idw – Informationsdienst Wissenschaft', 'https://idw-online.de', 'forschung', 'quelleIdw'],
    ['pv-magazine', 'pv magazine', 'https://www.pv-magazine.de', 'nachricht', 'quellePvMagazine'],
    ['klimareporter', 'Klimareporter°', 'https://www.klimareporter.de', 'nachricht', 'quelleKlimareporter'],
    ['handelsblatt', 'Handelsblatt', 'https://www.handelsblatt.com', 'nachricht', 'quelleHandelsblatt'],
    ['ezb', 'Europäische Zentralbank', 'https://data.ecb.europa.eu', 'statistik', 'quelleEzb'],
    ['personalwirtschaft', 'Personalwirtschaft', 'https://www.personalwirtschaft.de', 'nachricht', 'quellePersonalwirtschaft'],
    ['iab', 'IAB-Forum', 'https://www.iab-forum.de', 'forschung', 'quelleIab'],
    ['arbeitsagentur', 'Jobbörse der Bundesagentur für Arbeit', 'https://www.arbeitsagentur.de/jobsuche/', 'messung', 'quelleArbeitsagentur'],
    // Fuer die Weltlage (28.09.2026): die Reihen, an denen das Foresight-Modell
    // seine Anzeichen prueft. Vorher sammelte sie der KI-CEO getrennt.
    ['fred', 'FRED (St. Louis Fed)', 'https://fred.stlouisfed.org', 'statistik', 'quelleFred'],
    ['sffed', 'Federal Reserve Bank of San Francisco (TFP)', 'https://www.frbsf.org/research-and-insights/data-and-indicators/total-factor-productivity-tfp/', 'statistik', 'quelleTfp'],
    ['eurostat-makro', 'Eurostat (Industrie, Kerninflation, BIP)', 'https://ec.europa.eu/eurostat', 'statistik', 'quelleEurostatMakro'],
    // Primaerquelle fuer Politik (Karl, 30.09.2026): Gesetzgebung und Kleine Anfragen.
    ['dip', 'Deutscher Bundestag/Bundesrat – DIP', 'https://dip.bundestag.de', 'parlament', 'quelleDip'],
    // Mehr Blick ueber Deutschland hinaus und auf Technik (Karl, 08.10.2026). dpa hat
    // keinen freien Feed - ihre Meldungen kommen ueber tagesschau und Handelsblatt.
    ['bbc', 'BBC News (World)', 'https://www.bbc.com/news/world', 'nachricht', 'quelleBbc'],
    ['aljazeera', 'Al Jazeera English', 'https://www.aljazeera.com', 'nachricht', 'quelleAljazeera'],
    ['heise', 'heise online', 'https://www.heise.de', 'nachricht', 'quelleHeise'],
    ['golem', 'Golem.de', 'https://www.golem.de', 'nachricht', 'quelleGolem'],
    // Wissenschaft als sechster Bereich (Karl, 17.10.2026).
    ['dlf-forschung', 'Deutschlandfunk – Forschung aktuell', 'https://www.deutschlandfunk.de/forschung-aktuell-100.html', 'nachricht', 'quelleDlfForschung'],
    ['wissenschaft-de', 'wissenschaft.de', 'https://www.wissenschaft.de', 'nachricht', 'quelleWissenschaftDe'],
    ['mpg', 'Max-Planck-Gesellschaft', 'https://www.mpg.de/forschung', 'forschung', 'quelleMpg'],
    ['smc', 'Science Media Center Germany', 'https://sciencemediacenter.de', 'nachricht', 'quelleSmc'],
    // Mehr Wissenschaft (Karl, 17.10.2026: auch dort Boeen und Trends).
    ['spektrum', 'Spektrum der Wissenschaft', 'https://www.spektrum.de', 'nachricht', 'quelleSpektrum'],
    ['scinexx', 'scinexx', 'https://www.scinexx.de', 'nachricht', 'quelleScinexx'],
    ['spiegel-wissenschaft', 'DER SPIEGEL – Wissenschaft', 'https://www.spiegel.de/wissenschaft/', 'nachricht', 'quelleSpiegelWissenschaft'],
    ['helmholtz', 'Helmholtz-Gemeinschaft', 'https://www.helmholtz.de', 'forschung', 'quelleHelmholtz'],
];
// Messreihen zu Demokratie, Sicherheit und Vermoegen (15.10.2026): je Reihe eine eigene Quelle, damit eine ausgefallene die anderen nicht aufhaelt.
foreach (sorgenReihen() as $d) {
    $alleQuellen[] = [$d['id'], $d['quelleName'], $d['url'], $d['art'] ?? 'statistik', fn() => ['reihen' => [sorgenReihe($d)]]];
}
if ($nurNachrichten) {
    $alleQuellen = array_values(array_filter($alleQuellen, fn($q) => $q[3] === 'nachricht'));
}
/**
 * Quellen mit vielen Meldungen am Tag bleiben kuerzer als ihre Halbwertszeit
 * hergaebe - fuer die Blickwinkel zaehlen ohnehin nur die letzten Tage, und
 * der Wissensstand soll klein genug zum Laden bleiben.
 */
const KURZLEBIG = ['handelsblatt' => 14, 'idw' => 21, 'heise' => 21, 'golem' => 21, 'mpg' => 30, 'bbc' => 10, 'aljazeera' => 10];
/** Zaehlungen ohne Verlauf in der Quelle: der Verlauf entsteht aus den taeglichen Laeufen. */
const FORTGESCHRIEBEN = ['ba-stellen-personalentwicklung'];

/** Bundestag, DIP - Quelle, Nutzungsbedingungen und Abruf: quelleDip() unten. */
const DIP_API = 'https://search.dip.bundestag.de/api/v1/';

/** Sachgebiete des DIP, die eindeutig zu einem Themenfeld gehoeren. Die uebrigen ordnen die Stichworte zu. */
const DIP_SACHGEBIET_FELD = [
    'Energie' => 'energie',
    'Umwelt' => 'klima',
    'Gesundheit' => 'gesundheit',
    'Verteidigung' => 'sicherheit',
    'Migration und Aufenthaltsrecht' => 'migration',
    'Bildung und Erziehung' => 'bildung',
    'Soziale Sicherung' => 'rente',
    'Raumordnung, Bau- und Wohnungswesen' => 'wohnen',
    'Politisches Leben, Parteien' => 'demokratie',
    'Außenwirtschaft' => 'handel',
    'Außenpolitik und internationale Beziehungen' => 'geopolitik',
    'Wirtschaft' => 'industrie',
];

const DIP_SACHGEBIET_STEEP = [
    'Energie' => 'umwelt', 'Umwelt' => 'umwelt', 'Landwirtschaft und Ernährung' => 'umwelt', 'Verkehr' => 'umwelt',
    'Wirtschaft' => 'wirtschaft', 'Außenwirtschaft' => 'wirtschaft', 'Öffentliche Finanzen, Steuern und Abgaben' => 'wirtschaft', 'Arbeit und Beschäftigung' => 'wirtschaft',
    'Gesundheit' => 'gesellschaft', 'Soziale Sicherung' => 'gesellschaft', 'Bildung und Erziehung' => 'gesellschaft', 'Migration und Aufenthaltsrecht' => 'gesellschaft',
    'Gesellschaftspolitik, soziale Gruppen' => 'gesellschaft', 'Raumordnung, Bau- und Wohnungswesen' => 'gesellschaft', 'Kultur' => 'gesellschaft', 'Sport, Freizeit und Tourismus' => 'gesellschaft',
    'Medien, Kommunikation und Informationstechnik' => 'technologie', 'Wissenschaft, Forschung und Technologie' => 'technologie',
];


$parlament = null;
foreach ($alleQuellen as [$id, $name, $url, $art, $funktion]) {
    $start = microtime(true);
    try {
        $e = $funktion($destatisToken);
        $parlament = $e['parlament'] ?? $parlament;
        array_push($neueSignale, ...($e['signale'] ?? []));
        array_push($reihen, ...($e['reihen'] ?? []));
        array_push($trends, ...($e['trends'] ?? []));
        $anzahl = count($e['signale'] ?? []) + count($e['reihen'] ?? []) + count($e['trends'] ?? []);
        $quellen[] = ['id' => $id, 'name' => $name, 'url' => $url, 'art' => $art, 'anzahl' => $anzahl, 'ok' => true];
        printf("  ✓ %-36s %4d  (%.1f s)\n", $name, $anzahl, microtime(true) - $start);
    } catch (Throwable $err) {
        $fehler = mb_substr(ohneSchluessel($err->getMessage()), 0, 200);
        $quellen[] = ['id' => $id, 'name' => $name, 'url' => $url, 'art' => $art, 'anzahl' => 0, 'ok' => false, 'fehler' => $fehler];
        printf("  ✗ %-36s %s\n", $name, $fehler);
        // Was die Quelle beim letzten Mal lieferte, bleibt stehen - mit altem Stand.
        $alteReihen = array_values(array_filter($alt['reihen'] ?? [], fn($r) => $r['quelle'] === $id));
        array_push($reihen, ...$alteReihen);
        $reihenIds = array_column($alteReihen, 'id');
        foreach ($alt['trends'] ?? [] as $t) {
            if ((isset($t['reihe']) && in_array($t['reihe'], $reihenIds, true))
                || (isset($trendPraefix[$id]) && str_starts_with($t['id'], $trendPraefix[$id]))) {
                $trends[] = $t;
            }
        }
        // Signale der Quelle bleiben ohnehin, bis sie ablaufen (unten).
    }
}

// Nachrichtenlauf: was die uebrigen Quellen beim letzten vollen Lauf lieferten, bleibt stehen.
if ($nurNachrichten && $alt) {
    $gelaufen = array_column($quellen, 'id');
    $quellen = [...array_values(array_filter($alt['quellen'] ?? [], fn($q) => !in_array($q['id'], $gelaufen, true))), ...$quellen];
    array_push($reihen, ...($alt['reihen'] ?? []));
    // Themen im Nachrichtenstrom werden unten neu gebildet, alles andere bleibt.
    array_push($trends, ...array_values(array_filter($alt['trends'] ?? [], fn($t) => ($t['art'] ?? '') !== 'thema')));
    $parlament = $alt['parlament'] ?? null;
}

// --- Signale zusammenfuehren: Altes behalten, Neues darueber, Abgelaufenes weg ---
// Ausnahmen vom Behalten: die Studien je Themenfeld sind eine Momentaufnahme
// (die passendsten der letzten drei Monate) und werden bei jedem gelungenen
// Lauf ersetzt; frueher ungefiltert Aufgenommenes (arXiv ohne Qualitaetszeichen,
// die alte Quelle openalex-neu) faellt heraus.
$gelungen = array_column(array_filter($quellen, fn($q) => $q['ok']), 'id');
$nachId = [];
foreach ($alt['signale'] ?? [] as $s) {
    $ersetzt = $s['quelle'] === 'openalex-themen' && in_array('openalex-themen', $gelungen, true);
    $ungeprueft = ($s['quelle'] === 'arxiv' && empty($s['pruefung'])) || $s['quelle'] === 'openalex-neu';
    if (!$ersetzt && !$ungeprueft) {
        $nachId[$s['id']] = $s;
    }
}
foreach ($neueSignale as $s) {
    $s['gesehen'] = $nachId[$s['id']]['gesehen'] ?? $s['gesehen'];
    $nachId[$s['id']] = $s;
}
$signale = array_values(array_filter($nachId, fn($s) => !abgelaufen($s, $jetzt)
    && ($jetzt - strtotime($s['datum'])) / TAG <= (KURZLEBIG[$s['quelle']] ?? INF)
    && !($s['quelle'] === 'handelsblatt' && handelsblattVerlockung($s['titel'] ?? '', $s['url'] ?? ''))));
usort($signale, fn($a, $b) => strcmp($b['datum'], $a['datum']));
$entfernt = count($nachId) - count($signale);

// Fortgeschriebene Reihen: der heutige Wert kommt zu den frueheren dazu.
foreach ($reihen as &$r) {
    if (!in_array($r['id'], FORTGESCHRIEBEN, true)) {
        continue;
    }
    $frueher = array_values(array_filter($alt['reihen'] ?? [], fn($a) => $a['id'] === $r['id']))[0]['punkte'] ?? [];
    $neu = array_column($r['punkte'], 't');
    $r['punkte'] = array_slice([...array_filter($frueher, fn($p) => !in_array($p['t'], $neu, true)), ...$r['punkte']], -400);
    // Richtung gegen den Stand vor gut vier Wochen, solange es den noch nicht gibt gegen den ersten.
    $letzt = end($r['punkte']);
    $vergleich = $r['punkte'][0];
    foreach ($r['punkte'] as $p) {
        if (strtotime($p['t']) <= strtotime($letzt['t']) - 28 * TAG) {
            $vergleich = $p;
        }
    }
    $r['richtung'] = richtungVon($letzt['wert'] / max(1, $vergleich['wert']), 1, 0.03);
}
unset($r);

// Faellt der Bundestag aus, bleibt die letzte Zaehlung stehen - mit ihrem Stand.
$parlament ??= $alt['parlament'] ?? null;

array_push($trends, ...themenImNachrichtenstrom($signale, $jetzt));
$themen = themenfelder($signale, $reihen, $jetzt);

$stand = [
    'stand' => iso($jetzt),
    'quellen' => $quellen,
    'signale' => $signale,
    'reihen' => array_values($reihen),
    'trends' => array_values($trends),
    'themen' => $themen,
    'parlament' => $parlament,
    'entfernt' => $entfernt,
];
$stand = array_filter($stand, fn($v) => $v !== null);
// Erst vollstaendig schreiben, dann umbenennen: die App liest nie eine halbe Datei.
$zwischen = $ziel . '.neu';
file_put_contents($zwischen, json_encode($stand, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
rename($zwischen, $ziel);
schreibeKern($stand, dirname($ziel) . '/wissensstand-kern.json');
if (!$nurNachrichten) {
    touch($vollMarke);
}
printf(
    "\n  %d Signale, %d Reihen, %d Trends%s -> %s\n",
    count($signale),
    count($reihen),
    count($trends),
    $entfernt ? ", $entfernt abgelaufen entfernt" : '',
    $web ? 'radar/wissensstand.json' : $ziel,
);
schreibeWetter($signale, $themen, $jetzt, dirname($ziel) . '/wetter.json', array_values($reihen), array_values($trends));
weltlage($ziel);
radarText(dirname($ziel), $konfig, $web);

/**
 * Die Weltlage: der Tagesstand des Foresight-Modells aus diesen Reihen. Gerechnet
 * wird im Modell selbst (projects/foresight-model, engine/tagesstand.py) - hier
 * nur aufgerufen, damit Radar und Modell denselben Takt haben. Auf dem Server
 * liegt es ausserhalb des Web-Roots (scripts/deploy-weltlage.sh); fehlt es,
 * bleibt der Radar, wie er ist.
 */
function weltlage(string $wissensstand): void
{
    // Das Modell rechnet in seinem eigenen Ordner - die Pfade muessen absolut sein.
    $wissensstand = realpath($wissensstand) ?: $wissensstand;
    $kandidaten = array_filter([getenv('WELTMODELL') ?: null, dirname(__DIR__, 2)]);
    foreach ($kandidaten as $ordner) {
        $modell = is_file("$ordner/model/world_model.de.json") ? "$ordner/model/world_model.de.json" : "$ordner/exports/weltmodell.json";
        if (is_file("$ordner/engine/tagesstand.py") && is_file($modell)) {
            $python = is_executable('/usr/bin/python3') ? '/usr/bin/python3' : 'python3';
            $befehl = 'cd ' . escapeshellarg($ordner) . " && $python -m engine.tagesstand --modell " . escapeshellarg($modell)
                . ' --wissensstand ' . escapeshellarg($wissensstand) . ' --ziel ' . escapeshellarg(dirname($wissensstand) . '/weltlage.json') . ' 2>&1';
            exec($befehl, $ausgabe, $rc);
            echo implode("\n", $ausgabe) . ($rc ? "\n  ✗ Weltlage nicht gerechnet (Rueckgabe $rc)" : '') . "\n";
            if (!$rc) verlaufFortschreiben(dirname($wissensstand));
            return;
        }
    }
    echo "  - Weltlage: Modell nicht gefunden, nur der Radar\n";
}

/**
 * Der Tagestext zur Weltlage (Pilot mit Mistral, server/radar-text.php; Karls Ja
 * fuer die Stage am 28.10.2026). Nach jeder Weltlage, aber nur, wenn sich das
 * Zahlenblatt geaendert hat: einmal am Tag und wenn sich etwas bewegt, hoechstens
 * sechs Anfragen am Tag. Ohne Schluessel (scripts/radar-einrichten.sh --mistral)
 * bleibt alles, wie es ist. Das Protokoll liegt oberhalb des Web-Roots, weil es
 * auch abgelehnte Texte enthaelt.
 */
/**
 * Der Tagestext steht seit 31.10.2026 nicht mehr auf der Radar-Seite (Karl, Feedback 0005: „Den ganzen absatz brauce ich
 * eigentlich nicht“), darum fragt der Sammler Mistral nicht mehr. radar-text.php bleibt; true schaltet ihn wieder ein.
 */
const RADAR_TEXT_AN = false;

function radarText(string $ordner, array $konfig, bool $web): void
{
    $schluessel = getenv('MISTRAL_API_KEY') ?: (string) ($konfig['radar']['mistral_key'] ?? '');
    if (!RADAR_TEXT_AN || $schluessel === '' || !is_file("$ordner/weltlage.json") || !is_file(__DIR__ . '/radar-text.php')) {
        return;
    }
    require_once __DIR__ . '/radar-text.php';
    if ($web) {
        set_time_limit(180);
    }
    [, $meldung] = schreibeText([
        'lage' => "$ordner/weltlage.json",
        'protokoll' => getenv('RADAR_TEXT_PROTOKOLL') ?: ($web ? dirname(__DIR__, 2) : $ordner) . '/radar-text-protokoll.jsonl',
        'schluessel' => $schluessel,
        'zeitlimit' => 60,
        'nurNeu' => true,
        'hoechstensHeute' => 6,
    ]);
    if ($meldung !== '') {
        echo "$meldung\n";
    }
}

/**
 * Der Verlauf der Weltlage (Karl, 04.10.2026: "kannst du nicht die Veraenderungen
 * der letzten 7 Tage rekonstruieren?"). Die Weltlage selbst ist nur der heutige
 * Stand; hier kommt je Tag ein Eintrag mit den Wahrscheinlichkeiten dazu - so
 * zeigt der Radar, was sich in einer Woche verschoben hat. Ein Eintrag je Tag,
 * hoechstens 400.
 */
function verlaufFortschreiben(string $ordner): void
{
    $lage = json_decode((string) @file_get_contents("$ordner/weltlage.json"), true);
    if (!is_array($lage) || empty($lage['szenarien'])) return;
    $datei = "$ordner/weltlage-verlauf.json";
    $verlauf = json_decode((string) @file_get_contents($datei), true) ?: [];
    $heute = date('Y-m-d');
    $verlauf = array_values(array_filter($verlauf, fn($e) => ($e['datum'] ?? '') !== $heute));
    $p = [];
    foreach ($lage['szenarien'] as $sz) $p[$sz['id']] = $sz['p_tag'];
    $verlauf[] = ['datum' => $heute, 'basis' => $lage['basis']['version'] ?? '', 'p' => $p];
    $verlauf = array_slice($verlauf, -400);
    file_put_contents("$datei.neu", json_encode($verlauf, JSON_UNESCAPED_UNICODE));
    rename("$datei.neu", $datei);
    echo "  ✓ Verlauf der Weltlage: " . count($verlauf) . " Tage\n";
}

// =============================================================================
// Quellen
// =============================================================================

function quelleTagesschau(): array
{
    // Tag fuer Tag, zwei Wochen zurueck. Die Startseite der Schnittstelle zeigt
    // nur die neuesten Meldungen - aeltere Tage waeren duenner besetzt, und
    // jedes Thema saehe aus, als nehme es zu.
    $ressorts = ['inland' => 'politik', 'ausland' => 'politik', 'wirtschaft' => 'wirtschaft', 'wissen' => 'technologie'];
    $anfragen = [];
    foreach ($ressorts as $ressort => $_) {
        for ($i = 0; $i < TAGE_ZURUECK; $i++) {
            $tag = date('ymd', time() - $i * TAG);
            $anfragen["$ressort|$tag"] = ['url' => "https://www.tagesschau.de/api2u/news?date=$tag&ressort=$ressort"];
        }
    }
    $signale = [];
    $fehler = 0;
    foreach (holeAlle($anfragen) as $schluessel => $antwort) {
        if ($antwort['status'] !== 200) {
            $fehler++;
            continue;
        }
        $vorgabe = $ressorts[explode('|', $schluessel)[0]];
        foreach (json_decode($antwort['text'], true)['news'] ?? [] as $m) {
            $url = $m['shareURL'] ?? $m['detailsweb'] ?? '';
            if (($m['type'] ?? '') !== 'story' || $url === '') {
                continue;
            }
            $text = kurz(implode(': ', array_filter([$m['topline'] ?? '', $m['firstSentence'] ?? ''])), 280);
            $stichworte = array_values(array_filter(array_map(fn($t) => $t['tag'] ?? '', $m['tags'] ?? [])));
            $signale[] = signal([
                'id' => "tagesschau:$url",
                'quelle' => 'tagesschau',
                'quelleName' => 'tagesschau.de',
                'art' => 'nachricht',
                'steep' => steepVon($m['title'] . ' ' . $text . ' ' . implode(' ', $stichworte), $vorgabe),
                'titel' => $m['title'],
                'text' => $text,
                'url' => $url,
                'datum' => iso(strtotime($m['date'])),
                'guete' => 4,
                'stichworte' => $stichworte,
            ]);
        }
    }
    if ($fehler > count($anfragen) / 2) {
        throw new RuntimeException("$fehler von " . count($anfragen) . ' Abrufen gescheitert');
    }
    return ['signale' => $signale];
}

function quelleDeutschlandfunk(): array
{
    $xml = xml(hole('https://www.deutschlandfunk.de/nachrichten-100.rss'));
    $signale = [];
    foreach ($xml->channel->item as $item) {
        $titel = trim((string) $item->title);
        $url = trim((string) $item->link);
        $datum = strtotime((string) $item->pubDate);
        if ($titel === '' || $url === '' || !$datum) {
            continue;
        }
        $text = kurz(html_entity_decode(strip_tags((string) $item->description), ENT_QUOTES | ENT_HTML5), 280);
        $signale[] = signal([
            'id' => "dlf:$url",
            'quelle' => 'dlf',
            'quelleName' => 'Deutschlandfunk',
            'art' => 'nachricht',
            'steep' => steepVon("$titel $text", 'politik'),
            'titel' => $titel,
            'text' => $text,
            'url' => $url,
            'datum' => iso($datum),
            'guete' => 4,
        ]);
    }
    return ['signale' => $signale];
}

/**
 * arXiv: Vorabdrucke, nicht begutachtet - und inzwischen Hunderte am Tag.
 * Genommen wird nur, was ein Zeichen von Qualitaet traegt (Karl, 27.09.2026):
 * - in einer Zeitschrift erschienen (journal_ref),
 * - bei einer Konferenz angenommen ("Accepted to EMNLP 2026" im Kommentar;
 *   Workshops zaehlen, aber schwaecher),
 * - oder auf Hugging Face von der Fachgemeinde hochgewaehlt.
 * Von 200 neuen Papers sind das etwa 30.
 */
function quelleArxiv(): array
{
    $abfrage = rawurlencode('cat:cs.AI OR cat:cs.CY OR cat:cs.CL OR cat:cs.LG OR cat:econ.GN OR cat:physics.soc-ph');
    $antworten = holeAlle([
        'arxiv' => ['url' => "https://export.arxiv.org/api/query?search_query=$abfrage&sortBy=submittedDate&sortOrder=descending&max_results=300"],
        'hf' => ['url' => 'https://huggingface.co/api/daily_papers?limit=100'],
    ], 2, 60);
    // arXiv weist unter Last voruebergehend ab (406, 503) - einmal nach einer Pause nachfassen.
    if ($antworten['arxiv']['status'] !== 200) {
        sleep(5);
        $antworten['arxiv'] = holeAlle(['arxiv' => ['url' => "https://export.arxiv.org/api/query?search_query=$abfrage&sortBy=submittedDate&sortOrder=descending&max_results=300"]], 1, 60)['arxiv'];
    }
    if ($antworten['arxiv']['status'] !== 200) {
        throw new RuntimeException('HTTP ' . $antworten['arxiv']['status']);
    }
    $stimmen = [];
    foreach ($antworten['hf']['status'] === 200 ? json($antworten['hf']['text']) : [] as $eintrag) {
        $stimmen[$eintrag['paper']['id']] = (int) ($eintrag['paper']['upvotes'] ?? 0);
    }
    $xml = xml($antworten['arxiv']['text']);
    $signale = [];
    foreach ($xml->entry as $e) {
        $url = preg_replace('/v\d+$/', '', trim((string) $e->id));
        $arxivId = basename($url);
        $a = $e->children('http://arxiv.org/schemas/atom');
        $kategorie = (string) ($a->primary_category?->attributes()['term'] ?? '');
        $zeitschrift = trim((string) $a->journal_ref);
        $kommentar = trim(preg_replace('/\s+/', ' ', (string) $a->comment));
        $angenommen = preg_match('/\b(accepted|to appear|published|camera[- ]ready)\b/i', $kommentar) === 1;
        $workshop = stripos($kommentar, 'workshop') !== false;
        [$pruefung, $guete] = match (true) {
            $zeitschrift !== '' => [str_starts_with($zeitschrift, 'http') ? 'in einer Zeitschrift erschienen' : 'erschienen: ' . kurz($zeitschrift, 60), 4],
            $angenommen && !$workshop => ['angenommen: ' . kurz(preg_replace('/^.*?\b(accepted|to appear|published)\b\s*(to|at|by|in|as)?\s*/i', '', $kommentar), 50), 4],
            ($stimmen[$arxivId] ?? 0) >= 5 => [$stimmen[$arxivId] . ' Stimmen auf Hugging Face', 3],
            $angenommen && $workshop => ['Workshop-Beitrag', 3],
            default => [null, 0],
        };
        if ($pruefung === null) {
            continue; // reiner Vorabdruck ohne Zeichen von Qualitaet
        }
        $titel = kurz((string) $e->title, 200);
        $text = kurz((string) $e->summary, 300);
        $vorgabe = $kategorie === 'cs.CY' || $kategorie === 'physics.soc-ph' ? 'gesellschaft' : (str_starts_with($kategorie, 'econ') ? 'wirtschaft' : 'technologie');
        $signale[] = signal([
            'id' => "arxiv:$url",
            'quelle' => 'arxiv',
            'quelleName' => "arXiv ($kategorie)",
            'art' => 'forschung',
            'steep' => steepVon("$titel $text", $vorgabe),
            'titel' => $titel,
            'text' => $text,
            'url' => $url,
            'datum' => iso(strtotime((string) $e->published)),
            'guete' => $guete,
            'pruefung' => $pruefung,
        ]);
    }
    return ['signale' => $signale];
}

function quelleHuggingface(): array
{
    $signale = [];
    foreach (json(hole('https://huggingface.co/api/daily_papers?limit=30')) as $eintrag) {
        $p = $eintrag['paper'];
        $titel = kurz($p['title'], 200);
        $text = kurz($p['summary'] ?? '', 300);
        $signale[] = signal([
            'id' => 'hf:' . $p['id'],
            'quelle' => 'huggingface',
            'quelleName' => 'Hugging Face Papers' . (!empty($p['upvotes']) ? " ({$p['upvotes']} Stimmen)" : ''),
            'art' => 'forschung',
            'steep' => steepVon("$titel $text", 'technologie'),
            'titel' => $titel,
            'text' => $text,
            'url' => 'https://huggingface.co/papers/' . $p['id'],
            'datum' => iso(strtotime($p['publishedAt'])),
            // Von der Gemeinschaft hochgewaehlt, aber nicht begutachtet.
            'guete' => 3,
            'pruefung' => 'von der Fachgemeinde ausgewählt',
        ]);
    }
    return ['signale' => $signale];
}

/**
 * Neue Studien je Themenfeld: Zeitschriftenartikel der letzten drei Monate mit
 * Zusammenfassung, nach Passung sortiert. Damit steht neben jedem Feld, das in
 * den Nachrichten zaehlt, was die Forschung gerade dazu herausfindet.
 *
 * Nur aus Kernzeitschriften (OpenAlex "is_core", nach dem Leiden-Ranking des
 * CWTS): ohne diese Grenze kamen Zeitschriften zweifelhafter Herkunft und
 * Sammelstellen wie PubMed mit - begutachtet heisst nicht gleich belastbar.
 */
/** Eine OpenAlex-Adresse, mit Schluessel, wenn es einen gibt. */
function openalex(string $url): string
{
    return OPENALEX_SCHLUESSEL === '' ? $url : $url . '&api_key=' . rawurlencode(OPENALEX_SCHLUESSEL);
}

/** Schluessel aus Adressen in Meldungen entfernen - die Meldungen stehen oeffentlich im Wissensstand. */
function ohneSchluessel(string $text): string
{
    return (string) preg_replace('/(api_key|apikey|token|key)=[^&\s]+/i', '$1=***', $text);
}

function quelleOpenalexThemen(): array
{
    $von = date('Y-m-d', time() - 90 * TAG);
    $bis = date('Y-m-d');
    $anfragen = [];
    foreach (THEMENFELDER as $i => [, , , , $en]) {
        if ($en === '') {
            continue;
        }
        $anfragen[$i] = ['url' => openalex('https://api.openalex.org/works?search=' . rawurlencode($en)
            . "&filter=from_publication_date:$von,to_publication_date:$bis,type:article,has_abstract:true,primary_location.source.is_core:true"
            . '&per-page=3&select=id,doi,display_name,publication_date,abstract_inverted_index,primary_location')];
    }
    $signale = [];
    foreach (holeAlle($anfragen) as $i => $antwort) {
        if ($antwort['status'] !== 200) {
            continue;
        }
        [$feld, , $steep] = THEMENFELDER[$i];
        foreach (json_decode($antwort['text'], true)['results'] ?? [] as $w) {
            $zeitschrift = html_entity_decode((string) ($w['primary_location']['source']['display_name'] ?? ''), ENT_QUOTES | ENT_HTML5);
            $signale[] = signal([
                'id' => 'openalex:' . $w['id'],
                'quelle' => 'openalex-themen',
                'quelleName' => $zeitschrift !== '' ? kurz($zeitschrift, 60) : 'OpenAlex',
                'art' => 'forschung',
                'steep' => $steep,
                'titel' => kurz(html_entity_decode(strip_tags((string) $w['display_name']), ENT_QUOTES | ENT_HTML5), 200),
                'text' => kurz(abstractAus($w['abstract_inverted_index'] ?? []), 300),
                'url' => $w['doi'] ?: $w['id'],
                'datum' => iso(strtotime($w['publication_date'])),
                'guete' => 4,
                'pruefung' => 'Kernzeitschrift',
                'themen' => [$feld],
            ]);
        }
    }
    if (!$signale) {
        throw new RuntimeException('keine Antwort' . (OPENALEX_SCHLUESSEL === '' ? ' (ohne Schlüssel - Tagesbudget der IP-Adresse aufgebraucht?)' : ''));
    }
    return ['signale' => $signale];
}

/** Forschungsthemen, deren Umfang ueber die Jahre gemessen wird. */
function quelleOpenalex(): array
{
    $themen = [
        ['large language model', 'Große Sprachmodelle', 'technologie'],
        ['AI agent', 'KI-Agenten', 'technologie'],
        ['artificial intelligence regulation', 'Regulierung von KI', 'politik'],
        ['quantum computing', 'Quantencomputing', 'technologie'],
        ['solid-state battery', 'Feststoffbatterien', 'umwelt'],
        ['green hydrogen', 'Grüner Wasserstoff', 'umwelt'],
        ['heat pump', 'Wärmepumpen', 'umwelt'],
        ['misinformation', 'Desinformation', 'gesellschaft'],
        ['loneliness', 'Einsamkeit', 'gesellschaft'],
        ['remote work', 'Remote-Arbeit', 'wirtschaft'],
        ['skills shortage', 'Fachkräftemangel', 'wirtschaft'],
    ];
    // Das laufende Jahr ist unvollstaendig und wird nachindexiert - verglichen
    // werden die beiden letzten vollen Jahre, der Verlauf reicht sieben zurueck.
    $bis = (int) date('Y') - 1;
    $anfragen = ['alle' => ['url' => openalex('https://api.openalex.org/works?filter=publication_year:' . ($bis - 6) . "-$bis&group_by=publication_year")]];
    foreach ($themen as $i => [$suche]) {
        $anfragen[$i] = ['url' => openalex('https://api.openalex.org/works?filter=title_and_abstract.search:' . rawurlencode("\"$suche\"")
            . ',publication_year:' . ($bis - 6) . "-$bis&group_by=publication_year")];
    }
    $antworten = holeAlle($anfragen);
    // Alle Veroeffentlichungen je Jahr: die Forschung waechst insgesamt, auch
    // durch KI. Gemessen wird deshalb der ANTEIL eines Themas, nicht seine Zahl.
    $gesamt = array_column(json_decode($antworten['alle']['text'] ?? '{}', true)['group_by'] ?? [], 'count', 'key');
    if (!$gesamt) {
        throw new RuntimeException('keine Gesamtzahlen');
    }
    unset($antworten['alle']);
    $trends = [];
    foreach ($antworten as $i => $antwort) {
        if ($antwort['status'] !== 200) {
            continue;
        }
        [$suche, $name, $steep] = $themen[$i];
        $proJahr = array_column(json_decode($antwort['text'], true)['group_by'] ?? [], 'count', 'key');
        // Anteil je Million Veroeffentlichungen
        $anteil = array_map(fn($j) => ($gesamt[(string) $j] ?? 0) ? ($proJahr[(string) $j] ?? 0) / $gesamt[(string) $j] * 1e6 : 0, range($bis - 6, $bis));
        [$vorher, $zuletzt] = array_slice($anteil, -2);
        if (!$vorher || !$zuletzt) {
            continue;
        }
        $momentum = $zuletzt / $vorher;
        $trends[] = [
            'id' => 'forschung-' . preg_replace('/\W+/', '-', $suche),
            'art' => 'forschung',
            'steep' => $steep,
            'titel' => "Forschung: $name",
            'beschreibung' => zahlDe((int) ($proJahr[(string) $bis] ?? 0)) . " Veröffentlichungen $bis. Ihr Anteil an allen Veröffentlichungen "
                . ($momentum >= 1 ? 'stieg' : 'sank') . ' um ' . abs(round(($momentum - 1) * 100)) . ' % gegenüber ' . ($bis - 1)
                . ' - bereinigt um das Wachstum der Forschung insgesamt (OpenAlex).',
            'momentum' => $momentum,
            'verlauf' => array_map(fn($x) => round($x, 1), $anteil),
            'belege' => [],
        ];
    }
    if (!$trends) {
        throw new RuntimeException('keine Antwort');
    }
    return ['trends' => $trends];
}

function quelleWikipedia(): array
{
    // Wikipedia-Artikel, deren Aufrufe zeigen, wofuer sich gerade viele interessieren.
    $artikel = [
        ['Künstliche_Intelligenz', 'Künstliche Intelligenz', 'technologie'], ['ChatGPT', 'ChatGPT', 'technologie'],
        ['Quantencomputer', 'Quantencomputer', 'technologie'], ['Deepfake', 'Deepfakes', 'technologie'],
        ['Cyberangriff', 'Cyberangriffe', 'technologie'], ['Inflation', 'Inflation', 'wirtschaft'],
        ['Rezession', 'Rezession', 'wirtschaft'], ['Fachkräftemangel', 'Fachkräftemangel', 'wirtschaft'],
        ['Insolvenz', 'Insolvenz', 'wirtschaft'], ['Hitzewelle', 'Hitzewellen', 'umwelt'],
        ['Wärmepumpe', 'Wärmepumpe', 'umwelt'], ['Energiewende', 'Energiewende', 'umwelt'],
        ['Hochwasser', 'Hochwasser', 'umwelt'], ['Einsamkeit', 'Einsamkeit', 'gesellschaft'],
        ['Wohnungsnot', 'Wohnungsnot', 'gesellschaft'], ['Bürgergeld', 'Bürgergeld', 'gesellschaft'],
        ['Vier-Tage-Woche', 'Vier-Tage-Woche', 'gesellschaft'], ['Wehrpflicht', 'Wehrpflicht', 'politik'],
        ['Rechtsextremismus', 'Rechtsextremismus', 'politik'], ['Schuldenbremse', 'Schuldenbremse', 'politik'],
        ['NATO', 'NATO', 'politik'],
        // Der Markt fuer Beratung und Weiterbildung - nur, was ueber 30 Aufrufe am Tag kommt.
        ['Coaching', 'Coaching', 'gesellschaft'], ['Mediation', 'Mediation', 'gesellschaft'],
        ['Supervision', 'Supervision', 'gesellschaft'], ['Design_Thinking', 'Design Thinking', 'wirtschaft'],
        ['Resilienz_(Psychologie)', 'Resilienz', 'gesellschaft'],
    ];
    $bis = date('Ymd', time() - TAG);
    $von = date('Ymd', time() - 112 * TAG);
    $anfragen = [];
    foreach ($artikel as $i => [$titel]) {
        $anfragen[$i] = ['url' => 'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/de.wikipedia/all-access/user/'
            . rawurlencode($titel) . "/daily/{$von}00/{$bis}00"];
    }
    // Zu zweit, und Gedrosseltes nach einer Pause noch einmal einzeln: der
    // Webspace teilt seine Adresse mit vielen Seiten, Wikimedia zaehlt sie zusammen.
    $antworten = holeAlle($anfragen, 2);
    foreach ($antworten as $i => $antwort) {
        if ($antwort['status'] === 429) {
            sleep(2);
            $antworten[$i] = holeAlle([$i => $anfragen[$i]])[$i];
        }
    }
    $trends = [];
    foreach ($antworten as $i => $antwort) {
        if ($antwort['status'] !== 200) {
            continue; // Artikel umbenannt oder weg - die anderen zaehlen trotzdem
        }
        [$titel, $name, $steep] = $artikel[$i];
        $tage = array_column(json_decode($antwort['text'], true)['items'] ?? [], 'views');
        if (count($tage) < 60) {
            continue;
        }
        // Wochensummen; verglichen werden die letzten vier Wochen mit den zwoelf davor.
        $wochen = array_map('array_sum', array_chunk(array_slice($tage, count($tage) % 7), 7));
        $jung = array_sum(array_slice($wochen, -4)) / 4;
        $davor = array_slice($wochen, -16, count($wochen) >= 16 ? 12 : count($wochen) - 4);
        $altWert = $davor ? array_sum($davor) / count($davor) : 0;
        // Unter 30 Aufrufen am Tag ist jede Bewegung Zufall (oder eine Weiterleitung).
        if (!$altWert || $jung / 7 < 30) {
            continue;
        }
        $momentum = $jung / $altWert;
        $trends[] = [
            'id' => "aufmerksamkeit-$titel",
            'art' => 'aufmerksamkeit',
            'steep' => $steep,
            'titel' => "Interesse: $name",
            'beschreibung' => zahlDe((int) round($jung / 7)) . ' Aufrufe pro Tag in den letzten vier Wochen, '
                . ($momentum >= 1 ? '+' : '') . round(($momentum - 1) * 100) . ' % gegenüber den zwölf Wochen davor (de.wikipedia).',
            'momentum' => $momentum,
            'verlauf' => $wochen,
            'belege' => [],
        ];
    }
    if (!$trends) {
        throw new RuntimeException('keine Antwort');
    }
    return ['trends' => $trends];
}

function quelleDestatis(string $token): array
{
    if ($token === '') {
        throw new RuntimeException('kein Token (studio-config.php: radar.destatis_token)');
    }
    $jahr = (int) date('Y');
    $tabellen = ['61111-0002' => $jahr - 3, '52411-0010' => $jahr - 3, '42153-0001' => $jahr - 2, '52911-0001' => $jahr - 6, '52911-0005' => $jahr - 6];
    $anfragen = [];
    foreach ($tabellen as $name => $seit) {
        $anfragen[$name] = [
            'url' => 'https://genesis.destatis.de/genesisWS/rest/2020/data/tablefile',
            'methode' => 'POST',
            'kopf' => ["username: $token", 'password;', 'Content-Type: application/x-www-form-urlencoded'], // "password;" = leer gesendet; "password:" liesse curl weg
            'rumpf' => http_build_query(['name' => $name, 'area' => 'all', 'compress' => 'false', 'transpose' => 'false',
                'startyear' => $seit, 'format' => 'ffcsv', 'language' => 'de']),
        ];
    }
    // Nacheinander: GENESIS nimmt je Zugang nur eine Anfrage zur Zeit an und
    // antwortet auf parallele mit 404.
    $antworten = holeAlle($anfragen, 1, 120);
    $zeilen = function (string $name) use ($antworten): array {
        $a = $antworten[$name] ?? null;
        if (!$a || $a['status'] !== 200) {
            throw new RuntimeException("$name: HTTP " . ($a['status'] ?? 0));
        }
        return genesisCsv(str_starts_with($a['text'], "PK\x03\x04") ? ersteDateiAusZip($a['text']) : $a['text'], $name);
    };
    $tabelle = fn($code) => "https://www-genesis.destatis.de/datenbank/online/table/$code";
    $reihen = [];
    $trends = [];

    // Inflationsrate: aus dem Index selbst gerechnet, Vorjahresmonat zu Monat.
    $index = [];
    foreach ($zeilen('61111-0002') as $z) {
        $w = zahl($z['value'] ?? '');
        if (($z['value_unit'] ?? '') === '2020=100' && is_finite($w)) {
            $index[genesisZeit($z)] = $w;
        }
    }
    ksort($index);
    $punkte = [];
    foreach ($index as $t => $w) {
        $vorjahr = $index[((int) substr($t, 0, 4) - 1) . substr($t, 4)] ?? null;
        if ($vorjahr) {
            $punkte[] = ['t' => $t, 'wert' => round(($w / $vorjahr - 1) * 100, 1)];
        }
    }
    $punkte = array_slice($punkte, -24);
    $letzt = end($punkte);
    $vorJahr = $punkte[count($punkte) - 13] ?? null;
    if ($letzt && $vorJahr) {
        $r = [
            'id' => 'destatis-inflation', 'quelle' => 'destatis', 'quelleName' => 'Destatis, Verbraucherpreisindex (61111-0002)',
            'steep' => 'wirtschaft', 'titel' => 'Inflationsrate', 'einheit' => '%', 'url' => $tabelle('61111-0002'), 'punkte' => $punkte,
            'aussage' => prozent($letzt['wert']) . ' im ' . monatName($letzt['t']) . ', vor einem Jahr ' . prozent($vorJahr['wert']) . '.',
            'richtung' => richtungVon($letzt['wert'], $vorJahr['wert'], 0.3), 'stand' => $letzt['t'] . '-01',
        ];
        $reihen[] = $r;
        if ($r['richtung'] !== 'stabil') {
            $trends[] = trendAusReihe($r, ($letzt['wert'] + 5) / ($vorJahr['wert'] + 5));
        }
    }

    // Unternehmensinsolvenzen: Summe der letzten drei Monate gegen dieselben Monate im Vorjahr.
    $punkte = [];
    foreach ($zeilen('52411-0010') as $z) {
        $w = zahl($z['value'] ?? '');
        if (($z['value_variable_label'] ?? '') === 'Insolvenzverfahren (Unternehmen)' && is_finite($w)) {
            $punkte[] = ['t' => genesisZeit($z), 'wert' => $w];
        }
    }
    usort($punkte, fn($a, $b) => strcmp($a['t'], $b['t']));
    $punkte = array_slice($punkte, -24);
    if (count($punkte) >= 15) {
        $summe = fn(array $xs) => array_sum(array_column($xs, 'wert'));
        $jung = $summe(array_slice($punkte, -3));
        $altW = $summe(array_slice($punkte, -15, 3));
        $letzt = end($punkte);
        $r = [
            'id' => 'destatis-insolvenzen', 'quelle' => 'destatis', 'quelleName' => 'Destatis, Insolvenzverfahren (52411-0010)',
            'steep' => 'wirtschaft', 'titel' => 'Unternehmensinsolvenzen', 'einheit' => 'Verfahren', 'url' => $tabelle('52411-0010'),
            'punkte' => $punkte,
            'aussage' => zahlDe((int) $letzt['wert']) . ' beantragte Verfahren im ' . monatName($letzt['t']) . '; in den drei Monaten bis dahin '
                . ($jung >= $altW ? '+' : '') . round(($jung / $altW - 1) * 100) . ' % gegenüber dem Vorjahreszeitraum.',
            'richtung' => richtungVon($jung / $altW, 1, 0.05), 'stand' => $letzt['t'] . '-01',
        ];
        $reihen[] = $r;
        if ($r['richtung'] !== 'stabil') {
            $trends[] = trendAusReihe($r, $jung / $altW);
        }
    }

    // Industrieproduktion, saisonbereinigt.
    $punkte = [];
    foreach ($zeilen('42153-0001') as $z) {
        $w = zahl($z['value'] ?? '');
        if (in_array('X13 JDemetra+  kalender- und saisonbereinigt', $z, true) && in_array('Verarbeitendes Gewerbe', $z, true) && is_finite($w)) {
            $punkte[] = ['t' => genesisZeit($z), 'wert' => $w];
        }
    }
    usort($punkte, fn($a, $b) => strcmp($a['t'], $b['t']));
    $punkte = array_slice($punkte, -24);
    if (count($punkte) >= 13) {
        $letzt = end($punkte);
        $vorJahr = $punkte[count($punkte) - 13];
        $aenderung = ($letzt['wert'] / $vorJahr['wert'] - 1) * 100;
        $r = [
            'id' => 'destatis-produktion', 'quelle' => 'destatis', 'quelleName' => 'Destatis, Produktionsindex (42153-0001)',
            'steep' => 'wirtschaft', 'titel' => 'Industrieproduktion', 'einheit' => 'Index 2021=100', 'url' => $tabelle('42153-0001'),
            'punkte' => $punkte,
            'aussage' => 'Index ' . zahlDe($letzt['wert']) . ' im ' . monatName($letzt['t']) . ' (saisonbereinigt), '
                . ($aenderung >= 0 ? '+' : '') . prozent($aenderung) . ' zum Vorjahresmonat.',
            'richtung' => richtungVon($letzt['wert'] / $vorJahr['wert'], 1, 0.02), 'stand' => $letzt['t'] . '-01',
        ];
        $reihen[] = $r;
        if ($r['richtung'] !== 'stabil') {
            $trends[] = trendAusReihe($r, $letzt['wert'] / $vorJahr['wert']);
        }
    }

    // KI in Unternehmen: jaehrlich, zwei Tabellen (bis 2024 und ab 2025).
    $ki = [];
    foreach (['52911-0001', '52911-0005'] as $code) {
        try {
            foreach ($zeilen($code) as $z) {
                $treffer = array_filter($z, fn($v) => str_starts_with((string) $v, 'Künstliche Intelligenz'));
                $w = zahl($z['value'] ?? '');
                if ($treffer && ($z['value_unit'] ?? '') === 'Prozent' && is_finite($w)) {
                    $ki[$z['time']] = $w;
                }
            }
        } catch (Throwable) {
            // eine der beiden Tabellen reicht fuer einen Stand
        }
    }
    ksort($ki);
    $punkte = array_map(fn($t, $w) => ['t' => "$t-12", 'wert' => $w], array_keys($ki), array_values($ki));
    if ($punkte) {
        $letzt = end($punkte);
        $vor = $punkte[count($punkte) - 2] ?? null;
        $r = [
            'id' => 'destatis-ki-unternehmen', 'quelle' => 'destatis', 'quelleName' => 'Destatis, IKT-Indikatoren (52911)',
            'steep' => 'technologie', 'titel' => 'Unternehmen, die KI nutzen', 'einheit' => '% der Unternehmen', 'url' => $tabelle('52911-0005'),
            'punkte' => $punkte,
            'aussage' => prozent($letzt['wert'], 0) . ' der Unternehmen (ab 10 Beschäftigten) nutzten ' . substr($letzt['t'], 0, 4) . ' KI'
                . ($vor ? ', ' . substr($vor['t'], 0, 4) . ' waren es ' . prozent($vor['wert'], 0) . '.' : '.'),
            'richtung' => $vor ? richtungVon($letzt['wert'], $vor['wert'], 1) : 'stabil', 'stand' => $letzt['t'] . '-31',
        ];
        $reihen[] = $r;
        if ($vor && $r['richtung'] !== 'stabil') {
            $trends[] = trendAusReihe($r, $letzt['wert'] / $vor['wert']);
        }
    }
    if (!$reihen) {
        throw new RuntimeException('keine Tabelle lesbar');
    }
    return ['reihen' => $reihen, 'trends' => $trends];
}

function quelleEurostat(): array
{
    // Arbeitslosenquote, saisonbereinigt: Deutschland und EU im Vergleich.
    $d = json(hole('https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?geo=DE&geo=EU27_2020&s_adj=SA&age=TOTAL&sex=T&unit=PC_ACT&lastTimePeriod=24'));
    $zeiten = $d['dimension']['time']['category']['index'];
    asort($zeiten);
    $zeiten = array_keys($zeiten);
    // Flacher Index ueber alle Dimensionen; nur geo und time haben mehr als einen Wert.
    $schritt = function (string $dim) use ($d): int {
        $pos = array_search($dim, $d['id'], true);
        $n = 1;
        for ($i = $pos + 1; $i < count($d['id']); $i++) {
            $n *= $d['size'][$i];
        }
        return $n;
    };
    $reihe = function (string $geo) use ($d, $zeiten, $schritt): array {
        $aus = [];
        foreach ($zeiten as $i => $t) {
            $k = (string) ($d['dimension']['geo']['category']['index'][$geo] * $schritt('geo') + $i * $schritt('time'));
            if (isset($d['value'][$k])) {
                $aus[] = ['t' => $t, 'wert' => $d['value'][$k]];
            }
        }
        return $aus;
    };
    $de = $reihe('DE');
    $eu = $reihe('EU27_2020');
    $letzt = end($de);
    $vorJahr = $de[count($de) - 13] ?? null;
    if (!$letzt || !$vorJahr) {
        return [];
    }
    $r = [
        'id' => 'eurostat-arbeitslosigkeit', 'quelle' => 'eurostat', 'quelleName' => 'Eurostat (une_rt_m)', 'steep' => 'wirtschaft',
        'titel' => 'Arbeitslosenquote', 'einheit' => '%', 'url' => 'https://ec.europa.eu/eurostat/databrowser/view/une_rt_m/default/table',
        'punkte' => $de,
        'aussage' => prozent($letzt['wert']) . ' in Deutschland im ' . monatName($letzt['t']) . ' (EU: ' . prozent(end($eu)['wert'] ?? NAN)
            . '), vor einem Jahr ' . prozent($vorJahr['wert']) . '.',
        'richtung' => richtungVon($letzt['wert'], $vorJahr['wert'], 0.2), 'stand' => $letzt['t'] . '-01',
    ];
    return ['reihen' => [$r], 'trends' => $r['richtung'] !== 'stabil' ? [trendAusReihe($r, $letzt['wert'] / $vorJahr['wert'])] : []];
}

function quelleDawum(): array
{
    $d = json(hole('https://api.dawum.de/'));
    $bundestag = array_filter($d['Surveys'], fn($s) => $s['Parliament_ID'] === '0');
    $jetzt = time();
    /** Mittel aller Umfragen im Fenster [von Tagen, bis Tagen) vor heute. */
    $mittel = function (string $partei, int $von, int $bis) use ($bundestag, $jetzt): ?float {
        $w = [];
        foreach ($bundestag as $s) {
            $alter = $jetzt - strtotime($s['Date']);
            if ($alter >= $bis * TAG && $alter < $von * TAG && isset($s['Results'][$partei])) {
                $w[] = $s['Results'][$partei];
            }
        }
        return $w ? array_sum($w) / count($w) : null;
    };
    $reihen = [];
    $trends = [];
    foreach ($d['Parties'] as $p => $partei) {
        $name = $partei['Shortcut'];
        $jetztW = $mittel((string) $p, 30, 0);
        if ($name === 'Sonstige' || $jetztW === null || $jetztW < 3) {
            continue;
        }
        $vorher = $mittel((string) $p, 120, 90);
        if ($vorher === null) {
            continue;
        }
        // Verlauf: 30-Tage-Mittel der letzten zwoelf Monate.
        $punkte = [];
        for ($i = 0; $i < 12; $i++) {
            $w = $mittel((string) $p, (12 - $i) * 30, (11 - $i) * 30);
            if ($w !== null) {
                $punkte[] = ['t' => date('Y-m', $jetzt - (11 - $i) * 30 * TAG), 'wert' => round($w, 1)];
            }
        }
        $r = [
            'id' => 'dawum-' . strtolower(preg_replace('/\W+/', '-', $name)), 'quelle' => 'dawum',
            'quelleName' => 'DAWUM, Mittel der Bundestags-Umfragen', 'steep' => 'politik', 'titel' => "Umfragewert $name", 'einheit' => '%',
            'url' => 'https://dawum.de/Bundestag/', 'punkte' => $punkte,
            'aussage' => prozent($jetztW) . ' im Mittel der Umfragen der letzten 30 Tage, vor drei Monaten ' . prozent($vorher) . '.',
            'wert' => round($jetztW, 1),
            'richtung' => richtungVon($jetztW, $vorher, 1), 'stand' => date('Y-m-d'),
        ];
        $reihen[] = $r;
        if (abs($jetztW - $vorher) >= 1.5) {
            $trends[] = trendAusReihe($r, $jetztW / $vorher);
        }
    }
    return ['reihen' => $reihen, 'trends' => $trends];
}

function quelleEnergyCharts(): array
{
    $d = json(hole('https://api.energy-charts.info/ren_share_daily_avg?country=de'));
    $tage = [];
    foreach ($d['days'] as $i => $t) {
        if (is_numeric($d['data'][$i] ?? null)) {
            $tage[] = ['t' => substr($t, 6) . '-' . substr($t, 3, 2) . '-' . substr($t, 0, 2), 'wert' => (float) $d['data'][$i]];
        }
    }
    if (count($tage) < 330) {
        return [];
    }
    $mittel = fn(array $xs) => array_sum(array_column($xs, 'wert')) / count($xs);
    $jung = $mittel(array_slice($tage, -30));
    $vorJahr = $mittel(array_slice($tage, 0, 30));
    // Monatsmittel fuer den Verlauf
    $monate = [];
    foreach ($tage as $p) {
        $monate[substr($p['t'], 0, 7)][] = $p['wert'];
    }
    $punkte = [];
    foreach ($monate as $t => $w) {
        $punkte[] = ['t' => $t, 'wert' => round(array_sum($w) / count($w), 1)];
    }
    $r = [
        'id' => 'energy-charts-erneuerbare', 'quelle' => 'energy-charts', 'quelleName' => 'Energy-Charts, Fraunhofer ISE', 'steep' => 'umwelt',
        'titel' => 'Anteil erneuerbarer Energien am Strom', 'einheit' => '%',
        'url' => 'https://energy-charts.info/charts/renewable_share/chart.htm?l=de&c=DE', 'punkte' => $punkte,
        'aussage' => prozent($jung) . ' der öffentlichen Nettostromerzeugung in den letzten 30 Tagen, im selben Zeitraum des Vorjahres '
            . prozent($vorJahr) . '.',
        'wert' => round($jung, 1),
        'richtung' => richtungVon($jung, $vorJahr, 2), 'stand' => end($tage)['t'],
    ];
    $reihen = [$r];
    $trends = $r['richtung'] !== 'stabil' ? [trendAusReihe($r, $jung / $vorJahr)] : [];

    // Was installiert ist: Photovoltaik und Batteriespeicher, Monat fuer Monat.
    try {
        $d = json(hole('https://api.energy-charts.info/installed_power?country=de&time_step=monthly&installation_decomission=false'));
        $zeiten = array_map(fn($t) => substr($t, 3) . '-' . substr($t, 0, 2), $d['time']);
        foreach ([['Solar DC', 'solar', 'Installierte Photovoltaik-Leistung', 'GW'], ['Battery storage (capacity)', 'speicher', 'Kapazität der Batteriespeicher', 'GWh']] as [$typ, $id, $titel, $einheit]) {
            $werte = array_values(array_filter($d['production_types'], fn($p) => $p['name'] === $typ))[0]['data'] ?? [];
            $punkte = [];
            foreach ($werte as $i => $w) {
                if (is_numeric($w)) {
                    $punkte[] = ['t' => $zeiten[$i], 'wert' => round((float) $w, 1)];
                }
            }
            $punkte = array_slice($punkte, -25);
            if (count($punkte) < 13) {
                continue;
            }
            $letzt = end($punkte);
            $vor = $punkte[count($punkte) - 13];
            $r = [
                'id' => "energy-charts-$id", 'quelle' => 'energy-charts', 'quelleName' => 'Energy-Charts, Fraunhofer ISE', 'steep' => 'umwelt',
                'titel' => $titel, 'einheit' => $einheit, 'url' => 'https://energy-charts.info/charts/installed_power/chart.htm?l=de&c=DE',
                'punkte' => $punkte,
                'aussage' => zahlDe($letzt['wert']) . " $einheit im " . monatName($letzt['t']) . ', vor einem Jahr ' . zahlDe($vor['wert'])
                    . " $einheit (" . ($letzt['wert'] >= $vor['wert'] ? '+' : '') . round(($letzt['wert'] / $vor['wert'] - 1) * 100) . ' %).',
                'richtung' => richtungVon($letzt['wert'] / $vor['wert'], 1, 0.02), 'stand' => $letzt['t'] . '-01',
            ];
            $reihen[] = $r;
            $trends[] = trendAusReihe($r, $letzt['wert'] / $vor['wert']);
        }
    } catch (Throwable) {
        // Der Anteil am Strom reicht fuer einen Stand.
    }
    return ['reihen' => $reihen, 'trends' => $trends];
}

// -----------------------------------------------------------------------------
// Fachquellen fuer die drei Blickwinkel
// -----------------------------------------------------------------------------

/**
 * Ein RSS-Feed als Signale: Titel, Anriss, Link - nie der Artikel. $nimm
 * entscheidet je Eintrag (Titel, Rubriken), ob er dazugehoert.
 *
 * @param array{0: string, 1: string, 2: string, 3: string, 4: int, 5?: string} $q id, Name, Adresse, Art, Guete, Pruefung
 * $fest: der Bereich gehoert der Quelle (Fachpresse der Wissenschaft), nicht den Woertern im Titel.
 */
/** HTML-Zeichen zu Text; ein Feed (Helmholtz) kodiert sie doppelt ("Ged&amp;#228;chtnis"), dann noch einmal. */
function entitaeten(string $text): string
{
    $text = html_entity_decode($text, ENT_QUOTES | ENT_HTML5);
    return preg_match('/&(#\d+|#x[0-9a-f]+|[a-z]+);/i', $text) === 1 ? html_entity_decode($text, ENT_QUOTES | ENT_HTML5) : $text;
}

function rss(array $q, string $vorgabe, ?callable $nimm = null, int $hoechstens = 60, bool $fest = false): array
{
    [$id, $name, $url, $art, $guete] = $q;
    $xml = xml(hole($url));
    $signale = [];
    // RSS (channel/item) oder Atom (feed/entry, etwa heise).
    $atom = isset($xml->entry);
    foreach ($atom ? $xml->entry : $xml->channel->item as $item) {
        $titel = kurz(entitaeten(strip_tags((string) $item->title)), 200);
        $link = $atom ? trim((string) ($item->link['href'] ?? '')) : trim((string) $item->link);
        $datum = strtotime((string) ($atom ? ($item->published ?: $item->updated) : $item->pubDate));
        $rubriken = $atom
            ? array_map(fn($c) => trim((string) $c['term']), iterator_to_array($item->category, false))
            : array_map(fn($c) => trim((string) $c), iterator_to_array($item->category, false));
        if ($titel === '' || $link === '' || !$datum || ($nimm && !$nimm($titel, $rubriken, $link))) {
            continue;
        }
        $roh = $atom ? ((string) $item->summary ?: (string) $item->content) : (string) $item->description;
        $text = kurz(entitaeten(strip_tags($roh)), 280);
        $signale[] = signal([
            'id' => "$id:$link",
            'quelle' => $id,
            'quelleName' => $name,
            'art' => $art,
            'steep' => $fest ? $vorgabe : steepVon("$titel $text", $vorgabe),
            'titel' => $titel,
            'text' => $text,
            'url' => $link,
            'datum' => iso($datum),
            'guete' => $guete,
            'pruefung' => $q[5] ?? null,
        ]);
        if (count($signale) >= $hoechstens) {
            break;
        }
    }
    return ['signale' => $signale];
}

/**
 * Pressemitteilungen aus Hochschulen und Instituten - rund 60 am Tag. Genommen
 * werden deutsche Meldungen ueber Ergebnisse, nicht Preise, Termine und
 * Personalien, und nur zu Feldern, die einer der Blickwinkel beobachtet.
 */
function quelleIdw(): array
{
    $felder = '/energie|strom|solar|photovolt|wind|wasserstoff|batterie|speicher|wärme|klima|co2|emission|kreislauf|recycl|nachhaltig'
        . '|umwelt|ressourc|landwirt|ernährung|wasser|mobilität|verkehr|arbeit|beschäftig|weiterbild|bildung|lernen|führung|organisation'
        . '|unternehm|wirtschaft|innovation|gründ|start-?up|\bki\b|künstlich|digital|roboter|quanten|therapie|impf|antibiot/iu';
    return rss(
        ['idw', 'idw – Informationsdienst Wissenschaft', 'https://idw-online.de/de/pressreleasesrss', 'forschung', 4, 'Pressemitteilung aus der Forschung'],
        'wissenschaft',
        fn($titel) => preg_match($felder, $titel) === 1 && !titelTermin($titel) && !titelEnglisch($titel),
        80,
    );
}

/** Preise, Termine und Personalien sind keine Ergebnisse. */
function titelTermin(string $titel): bool
{
    return preg_match('/pressekonferenz|preis\b|preisträger|auszeichnung|erhält|verliehen|tagung|kongress|symposium|einladung|veranstaltung'
        . '|vortrag|ringvorlesung|workshop|save the date|ernannt|neue[rn]? (präsident|direktor|professor|leitung)|jubiläum|stellenausschreibung/iu', $titel) === 1;
}

/** Deutsch: idw und Helmholtz fuehren viele Meldungen doppelt, auf Deutsch und Englisch. */
function titelEnglisch(string $titel): bool
{
    return preg_match_all('/\b(the|of|and|for|with|to|in|on|a|is)\b/i', $titel) >= 2 && !preg_match('/[äöüß]/u', $titel);
}

/**
 * Wissenschaft (Karl, 17.10.2026: ein sechster Bereich). Fachpresse und Institute, deutsch: Titel, Anriss und Link, nie der Artikel.
 * Der Bereich gehoert der Quelle (fest), nicht den Woertern im Titel. Weitere Wissenschaftsquellen weiter unten (quelleSpektrum).
 */
function quelleDlfForschung(): array
{
    // Die Sendung "Forschung aktuell" legt jeden Tag eine Zusammenfassung ("Wissenschaftsmeldungen ...", "A / B / C") neben die Einzelbeitraege.
    $doppelt = fn(string $titel) => preg_match('/^(?i:wissenschaftsmeldungen)|\s\/\s|\p{Ll}\/\p{Lu}/u', $titel) === 1;
    // Der Feed reicht gut drei Monate zurueck: damit hat die Quelle vom ersten Lauf an Vorwochen.
    return rss(['dlf-forschung', 'Deutschlandfunk – Forschung aktuell', 'https://www.deutschlandfunk.de/forschung-aktuell-100.rss', 'nachricht', 4], 'wissenschaft',
        fn($titel) => !$doppelt($titel), 100, true);
}

function quelleWissenschaftDe(): array
{
    // Die Adresse mit www und /feed/ leitet auf diese um; der Server meldete am 17.10.2026 einmal einen Verbindungsfehler auf www.
    return rss(['wissenschaft-de', 'wissenschaft.de', 'https://wissenschaft.de/feed.xml', 'nachricht', 3], 'wissenschaft',
        fn($titel) => preg_match('/nachrichtenquellen für|^folge \d+|podcast|gewinnspiel/iu', $titel) !== 1, 60, true);
}

/** Forschungsergebnisse der Max-Planck-Gesellschaft, von ihr selbst geschrieben. */
function quelleMpg(): array
{
    return rss(['mpg', 'Max-Planck-Gesellschaft', 'https://www.mpg.de/de/forschung.rss', 'forschung', 4, 'Pressemitteilung aus der Forschung'], 'wissenschaft', null, 40, true);
}

/** Einordnungen des Science Media Centers (gemeinnuetzig): was Fachleute zu einer Studie oder einem Ereignis sagen. */
function quelleSmc(): array
{
    return rss(['smc', 'Science Media Center Germany', 'https://sciencemediacenter.de/feed.rss', 'nachricht', 4], 'wissenschaft', null, 30, true);
}

/**
 * Mehr Wissenschaft (17.10.2026): Titel, Anriss und Link wie bei den anderen Feeds, nie der Artikel. Spektrum trug ich am Anfang nicht ein, weil sein
 * Feed "Alle Rechte vorbehalten" nennt; heise und die tagesschau nennen in ihren Feeds ein Copyright ebenso, darum zaehlt es hier wie dort.
 * Wer das anders will, nimmt die Zeile in $alleQuellen heraus. Der Bereich gehoert der Quelle.
 */
function quelleSpektrum(): array
{
    return rss(['spektrum', 'Spektrum der Wissenschaft', 'https://www.spektrum.de/alias/rss/spektrum-de-rss-feed/996406', 'nachricht', 4], 'wissenschaft',
        fn($titel) => preg_match('/podcast|gewinnspiel|leserbrief|^buchtipp|^rätsel|^sudoku/iu', $titel) !== 1, 40, true);
}

function quelleScinexx(): array
{
    return rss(['scinexx', 'scinexx', 'https://www.scinexx.de/feed/', 'nachricht', 3], 'wissenschaft', null, 40, true);
}

function quelleSpiegelWissenschaft(): array
{
    return rss(['spiegel-wissenschaft', 'DER SPIEGEL – Wissenschaft', 'https://www.spiegel.de/wissenschaft/index.rss', 'nachricht', 4], 'wissenschaft', null, 40, true);
}

/** Presseinformationen der Helmholtz-Zentren, von der Gemeinschaft selbst ausgewaehlt; deutsch, ohne Preise und Termine. */
function quelleHelmholtz(): array
{
    return rss(['helmholtz', 'Helmholtz-Gemeinschaft', 'https://www.helmholtz.de/ueber-uns/wer-wir-sind/presse-medien/mediathek/rss-feeds/presseinformationen/feed.xml', 'forschung', 4,
        'Pressemitteilung aus der Forschung'], 'wissenschaft', fn($titel) => !titelEnglisch($titel) && !titelTermin($titel), 20, true);
}

/** Weltnachrichten auf Englisch - der Blick von aussen auf Europa und Deutschland. */
function quelleBbc(): array
{
    return rss(['bbc', 'BBC News (World)', 'https://feeds.bbci.co.uk/news/world/rss.xml', 'nachricht', 4], 'politik');
}

/** Der Blick aus dem Nahen Osten und dem globalen Sueden; staatlich (Katar) finanziert, daher Guete 3. */
function quelleAljazeera(): array
{
    return rss(['aljazeera', 'Al Jazeera English', 'https://www.aljazeera.com/xml/rss/all.xml', 'nachricht', 3], 'politik',
        fn($titel) => preg_match('/\b(sport|football|cricket|tennis|olympic|quiz)\b/i', $titel) !== 1);
}

/** Technik und Netzpolitik - ohne Angebote, Deals und Produkttests. */
function quelleHeise(): array
{
    $ohne = '/anzeige|angebot|deal|rabatt|gutschein|im test|test:|bestenliste|kaufberatung|heise\+|c\'t \d|podcast|webinar|workshop|heise-academy/iu';
    return rss(['heise', 'heise online', 'https://www.heise.de/rss/heise-atom.xml', 'nachricht', 4], 'technologie',
        fn($titel) => preg_match($ohne, $titel) !== 1 && preg_match(WETTER_RAUSCHEN, $titel) !== 1, 80);
}

function quelleGolem(): array
{
    $ohne = '/\\(g\\+\\)|anzeige|angebot|deal|rabatt|gutschein|sonderangebot|im test|test:|golem plus|podcast|karrierewelt|jobs?:/iu';
    return rss(['golem', 'Golem.de', 'https://rss.golem.de/rss.php?feed=RSS2.0', 'nachricht', 3], 'technologie',
        fn($titel) => preg_match($ohne, $titel) !== 1 && preg_match(WETTER_RAUSCHEN, $titel) !== 1);
}

function quellePvMagazine(): array
{
    return rss(['pv-magazine', 'pv magazine', 'https://www.pv-magazine.de/feed/', 'nachricht', 3], 'umwelt');
}

function quelleKlimareporter(): array
{
    return rss(['klimareporter', 'Klimareporter°', 'https://www.klimareporter.de/?format=feed&type=rss', 'nachricht', 3], 'umwelt');
}

/** Wirtschaft, Finanzen, Unternehmen - ohne Rubriken, die die tagesschau besser abdeckt oder die nichts bewegen. */
function quelleHandelsblatt(): array
{
    $ohne = ['International', 'Politik', 'Dienstleister', 'Sport', 'Panorama', 'Kultur', 'Reise', 'Auto', 'Lifestyle'];
    return rss(
        ['handelsblatt', 'Handelsblatt', 'https://www.handelsblatt.com/contentexport/feed/schlagzeilen', 'nachricht', 4],
        'wirtschaft',
        fn($titel, $rubriken, $link) => !array_intersect($rubriken, $ohne) && !handelsblattVerlockung($titel, $link),
    );
}

/**
 * Anlage-Verlockungen (Karl, 18.10.2026: "übermäßig viel Aktien-Verlockungen, gefühlt Werbung, um eine gierige
 * Zielgruppe anzulocken - bitte filtern"): die Rubrik Anlagestrategie (Geldanlage, Fonds + ETF, Kolumnen, Rankings)
 * und Ratgeber-Titel, die das Depot der Leser ansprechen. Marktberichte und Geldpolitik bleiben. Gilt auch fuer
 * den Bestand, damit die Fronten sofort sauber sind.
 */
function handelsblattVerlockung(string $titel, string $url): bool
{
    $pfad = (string) parse_url($url, PHP_URL_PATH);
    return strpos($pfad, '/finanzen/anlagestrategie/') === 0
        || preg_match('/^(Geldanlage|Depot|Vermögen|Geld\. Leben\. Looman\.|Aktie im Blick|Märkte Insight|Ranking \d{4}'
            . '|Aktien-?Tipps?|Dividenden?|Sparplan|ETFs?):/u', $titel) === 1;
}

/** Fachpresse fuer Personalarbeit - ohne bezahlte Beitraege. */
function quellePersonalwirtschaft(): array
{
    return rss(
        ['personalwirtschaft', 'Personalwirtschaft', 'https://www.personalwirtschaft.de/feed/', 'nachricht', 3],
        'wirtschaft',
        fn($titel, $rubriken) => !in_array('Sponsored', $rubriken, true),
    );
}

/** Forschung des Instituts fuer Arbeitsmarkt- und Berufsforschung, allgemein verstaendlich aufbereitet. */
function quelleIab(): array
{
    return rss(['iab', 'IAB-Forum', 'https://www.iab-forum.de/feed/', 'forschung', 4, 'Institut für Arbeitsmarkt- und Berufsforschung'], 'wirtschaft');
}

/** Der Einlagesatz der EZB - der Leitzins, der seit 2024 den Ton angibt. */
function quelleEzb(): array
{
    $von = date('Y-m-d', time() - 3 * 365 * TAG);
    $d = json(hole("https://data-api.ecb.europa.eu/service/data/FM/B.U2.EUR.4F.KR.DFR.LEV?format=jsondata&startPeriod=$von"));
    $zeiten = array_column($d['structure']['dimensions']['observation'][0]['values'], 'id');
    $beobachtung = array_values($d['dataSets'][0]['series'])[0]['observations'] ?? [];
    // Die Reihe nennt nur die Tage, an denen sich der Satz aendert - auf Monate auffuellen.
    $aenderungen = [];
    foreach ($zeiten as $i => $t) {
        if (isset($beobachtung[(string) $i][0])) {
            $aenderungen[$t] = (float) $beobachtung[(string) $i][0];
        }
    }
    ksort($aenderungen);
    if (!$aenderungen) {
        throw new RuntimeException('keine Werte');
    }
    $punkte = [];
    for ($m = 24; $m >= 0; $m--) {
        $monat = date('Y-m', strtotime(date('Y-m-01') . " -$m months"));
        $wert = null;
        foreach ($aenderungen as $t => $w) {
            if (substr($t, 0, 7) <= $monat) {
                $wert = $w;
            }
        }
        if ($wert !== null) {
            $punkte[] = ['t' => $monat, 'wert' => $wert];
        }
    }
    $letzt = end($punkte);
    $vorJahr = $punkte[count($punkte) - 13] ?? $punkte[0];
    $seit = array_key_last($aenderungen);
    $r = [
        'id' => 'ezb-leitzins', 'quelle' => 'ezb', 'quelleName' => 'EZB, Einlagesatz (FM.B.U2.EUR.4F.KR.DFR.LEV)', 'steep' => 'wirtschaft',
        'titel' => 'EZB-Leitzins (Einlagesatz)', 'einheit' => '%',
        'url' => 'https://data.ecb.europa.eu/data/datasets/FM/FM.B.U2.EUR.4F.KR.DFR.LEV', 'punkte' => $punkte,
        'aussage' => prozent($letzt['wert'], 2) . ' seit ' . date('j.', strtotime($seit)) . ' ' . monatName(substr($seit, 0, 7))
            . ', vor einem Jahr ' . prozent($vorJahr['wert'], 2) . '.',
        'richtung' => richtungVon($letzt['wert'], $vorJahr['wert'], 0.1), 'stand' => $seit,
    ];
    $reihen = [$r];
    // Der Abstand Frankreich zu Deutschland ist eine eigene Abfrage: faellt sie aus, bleibt der Einlagesatz (und die Quelle gilt als ok).
    try {
        $reihen[] = ezbAbstandFrDe();
    } catch (Throwable) {
    }
    return ['reihen' => $reihen, 'trends' => $r['richtung'] !== 'stabil' ? [trendAusReihe($r, ($letzt['wert'] + 2) / ($vorJahr['wert'] + 2))] : []];
}

/**
 * Der Abstand der Renditen zehnjaehriger Staatsanleihen Frankreichs zu Deutschlands (OAT gegen Bund), 30.10.2026 (RQ1): die
 * EZB-Monatsreihe "Langfristzins fuer die Konvergenzpruefung" (Datensatz IRS, Monatsmittel), Frankreich minus Deutschland.
 * Deutschland liegt seit 1990 vor, Frankreich seit 1986; frei abrufbar ohne Schluessel. Beide Reihen kommen aus derselben
 * Quelle mit gleicher Definition - nie mit Reihen anderer Quellen mischen (docs/sichtung/2026-10-28-markt-quellen.md, M1a).
 */
function ezbAbstandFrDe(): array
{
    $anfragen = [];
    foreach (['FR', 'DE'] as $land) {
        $anfragen[$land] = ['url' => "https://data-api.ecb.europa.eu/service/data/IRS/M.$land.L.L40.CI.0000.EUR.N.Z?format=jsondata"];
    }
    $monate = [];
    foreach (holeAlle($anfragen, 2) as $land => $a) {
        if ($a['status'] !== 200) {
            throw new RuntimeException("HTTP {$a['status']} ($land)");
        }
        $monate[$land] = ezbMonate(json($a['text']));
    }
    return ezbAbstandReihe($monate['FR'], $monate['DE']);
}

/** Die Monatswerte einer EZB-Reihe (Format jsondata): ['2026-09' => 4.44, ...]. Ein Monat ohne Beobachtung fehlt; die Monate gehen nach ihrer Kennung, nicht nach ihrer Stelle (Frankreich beginnt vier Jahre frueher als Deutschland). */
function ezbMonate(array $d): array
{
    $zeiten = array_column($d['structure']['dimensions']['observation'][0]['values'] ?? [], 'id');
    $beobachtung = array_values($d['dataSets'][0]['series'] ?? [])[0]['observations'] ?? [];
    $aus = [];
    foreach ($zeiten as $i => $t) {
        $w = $beobachtung[(string) $i][0] ?? null;
        if (is_numeric($w) && preg_match('/^\d{4}-\d{2}$/', (string) $t)) {
            $aus[(string) $t] = (float) $w;
        }
    }
    ksort($aus);
    return $aus;
}

/** Der Abstand zweier Monatsreihen in Prozentpunkten (a minus b): nur Monate, in denen beide einen Wert haben, auf zwei Stellen. */
function ezbAbstand(array $a, array $b): array
{
    $aus = [];
    foreach ($a as $t => $w) {
        if (isset($b[$t])) {
            $aus[$t] = round($w - $b[$t], 2);
        }
    }
    ksort($aus);
    return $aus;
}

/** Die Radar-Reihe aus den Monatswerten Frankreichs und Deutschlands. Unter zwei Jahren Abstand gibt es keine Reihe (wirft). */
function ezbAbstandReihe(array $fr, array $de): array
{
    $abstand = ezbAbstand($fr, $de);
    if (count($abstand) < 24) {
        throw new RuntimeException('Abstand FR/DE: zu wenige Monate');
    }
    $monat = (string) array_key_last($abstand);
    $wert = $abstand[$monat];
    $lage = round(abs($wert), 2) == 0.0 ? 'auf dem Niveau der deutschen' : number_format(abs($wert), 2, ',', '') . ' Prozentpunkte ' . ($wert > 0 ? 'über' : 'unter') . ' der deutschen';
    return makroReihe(
        'ezb-oat-bund', 'ezb', 'EZB, Langfristzins für die Konvergenzprüfung (IRS), Frankreich minus Deutschland', 'wirtschaft',
        'Abstand Frankreich zu Deutschland, 10 Jahre', 'Prozentpunkte', 'https://data.ecb.europa.eu/data/datasets/IRS', $abstand,
        'Die Rendite zehnjähriger französischer Staatsanleihen liegt ' . $lage . ', Monatsmittel im ' . monatName($monat) . '.', 0.1,
    );
}

/**
 * Offene Stellen in Personal- und Organisationsentwicklung: wie viel die
 * Betriebe gerade in Entwicklung und Veraenderung investieren. Die Jobboerse
 * nennt nur den heutigen Stand - der Verlauf waechst mit jedem Lauf
 * (FORTGESCHRIEBEN). Der Schluessel "jobboerse-jobsuche" ist der oeffentliche
 * der Jobboerse selbst, kein Geheimnis.
 */
function quelleArbeitsagentur(): array
{
    $begriffe = ['Personalentwicklung', 'Organisationsentwicklung', 'Change Management'];
    $anfragen = [];
    foreach ($begriffe as $b) {
        $anfragen[$b] = [
            'url' => 'https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs?angebotsart=1&size=1&was=' . rawurlencode($b),
            'kopf' => ['X-API-Key: jobboerse-jobsuche'],
        ];
    }
    $anzahl = [];
    foreach (holeAlle($anfragen, 3) as $b => $a) {
        if ($a['status'] !== 200) {
            throw new RuntimeException("HTTP {$a['status']} ($b)");
        }
        $anzahl[$b] = (int) (json($a['text'])['maxErgebnisse'] ?? 0);
    }
    $summe = array_sum($anzahl);
    return ['reihen' => [[
        'id' => 'ba-stellen-personalentwicklung', 'quelle' => 'arbeitsagentur', 'quelleName' => 'Jobbörse der Bundesagentur für Arbeit',
        'steep' => 'wirtschaft', 'titel' => 'Offene Stellen in Personal- und Organisationsentwicklung', 'einheit' => 'Stellen',
        'url' => 'https://www.arbeitsagentur.de/jobsuche/suche?angebotsart=1&was=Personalentwicklung',
        'punkte' => [['t' => date('Y-m-d'), 'wert' => $summe]],
        'aussage' => zahlDe($summe) . ' Stellenangebote heute: ' . implode(', ', array_map(fn($b) => zahlDe($anzahl[$b]) . " $b", $begriffe)) . '.',
        'wert' => $summe,
        'richtung' => 'stabil', 'stand' => date('Y-m-d'),
    ]]];
}

// -----------------------------------------------------------------------------
// Makroreihen fuer die Anzeichen des Foresight-Modells (data/anzeichen.json)
// -----------------------------------------------------------------------------

/** Eine Makroreihe im Format des Wissensstands. Quartale stehen unter ihrem ersten Monat. */
function makroReihe(string $id, string $quelle, string $quelleName, string $steep, string $titel, string $einheit, string $url, array $punkte, string $aussage, float $schwelle, int $zurueck = 12, int $stellen = 2): array
{
    ksort($punkte);
    $liste = array_map(fn($t, $w) => ['t' => $t, 'wert' => round($w, $stellen)], array_keys($punkte), array_values($punkte));
    $letzt = end($liste);
    // Richtung gegen den Wert vor einem Jahr: bei Monatswerten zwoelf Punkte zurueck, bei Jahreswerten einer ($zurueck).
    $vorJahr = $liste[count($liste) - 1 - $zurueck] ?? $liste[0];
    return [
        'id' => $id, 'quelle' => $quelle, 'quelleName' => $quelleName, 'steep' => $steep, 'titel' => $titel, 'einheit' => $einheit,
        'url' => $url, 'punkte' => $liste, 'aussage' => $aussage,
        'richtung' => richtungVon($letzt['wert'], $vorJahr['wert'], $schwelle), 'stand' => $letzt['t'] . (strlen($letzt['t']) === 7 ? '-01' : ''),
    ];
}

/** FREDs CSV-Ausgabe braucht keinen Schluessel. [JJJJ-MM-TT => wert] */
function fredReihe(string $antwort, string $reihe): array
{
    $zeilen = array_map('str_getcsv', preg_split('/\r?\n/', trim($antwort)));
    if (($zeilen[0][1] ?? '') !== $reihe) {
        throw new RuntimeException("$reihe: keine CSV");
    }
    $aus = [];
    foreach (array_slice($zeilen, 1) as $z) {
        if (isset($z[1]) && is_numeric($z[1])) {
            $aus[$z[0]] = (float) $z[1];
        }
    }
    return $aus;
}

function monatsmittel(array $tage): array
{
    $m = [];
    foreach ($tage as $t => $w) {
        $m[substr($t, 0, 7)][] = $w;
    }
    return array_map(fn($ws) => array_sum($ws) / count($ws), $m);
}

function quelleFred(): array
{
    $ab = (date('Y') - 4) . '-01-01';
    $ids = ['DCOILBRENTEU', 'DFII10', 'CPIAUCSL', 'B235RC1Q027SBEA', 'A255RC1Q027SBEA'];
    $anfragen = [];
    foreach ($ids as $id) {
        $anfragen[$id] = ['url' => "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$id&cosd=$ab"];
    }
    $antworten = holeAlle($anfragen, 3);
    $r = [];
    foreach ($ids as $id) {
        if ($antworten[$id]['status'] === 200) {
            try {
                $r[$id] = fredReihe($antworten[$id]['text'], $id);
            } catch (Throwable) {
            }
        }
    }
    $url = fn($id) => "https://fred.stlouisfed.org/series/$id";
    $reihen = [];
    if (!empty($r['DCOILBRENTEU'])) {
        $m = monatsmittel($r['DCOILBRENTEU']);
        $reihen[] = makroReihe('fred-brent', 'fred', 'FRED, Brent (DCOILBRENTEU)', 'wirtschaft', 'Ölpreis Brent', 'USD je Barrel', $url('DCOILBRENTEU'), $m,
            zahlDe(round(end($m))) . ' $ je Barrel im Mittel des ' . (array_key_last($m) === date('Y-m') ? 'laufenden Monats' : 'Monats ' . monatName(array_key_last($m))) . '.', 5);
    }
    if (!empty($r['DFII10'])) {
        $m = monatsmittel($r['DFII10']);
        $reihen[] = makroReihe('fred-realrendite-10j', 'fred', 'FRED, 10-jährige TIPS (DFII10)', 'wirtschaft', 'Reale Zehnjahresrendite USA', '%', $url('DFII10'), $m,
            prozent(end($m), 2) . ' Rendite inflationsgeschützter US-Staatsanleihen (10 Jahre), Monatsmittel.', 0.25);
    }
    if (!empty($r['CPIAUCSL'])) {
        $index = [];
        foreach ($r['CPIAUCSL'] as $t => $w) {
            $index[substr($t, 0, 7)] = $w;
        }
        $jahr = [];
        foreach ($index as $m => $w) {
            $vor = ((int) substr($m, 0, 4) - 1) . substr($m, 4);
            if (isset($index[$vor])) {
                $jahr[$m] = ($w / $index[$vor] - 1) * 100;
            }
        }
        if ($jahr) {
            $reihen[] = makroReihe('fred-inflation-usa', 'fred', 'FRED, Verbraucherpreise (CPIAUCSL)', 'wirtschaft', 'Inflation USA', '%', $url('CPIAUCSL'), $jahr,
                prozent(end($jahr)) . ' zum Vorjahresmonat im ' . monatName(array_key_last($jahr)) . '.', 0.3);
        }
    }
    if (!empty($r['B235RC1Q027SBEA']) && !empty($r['A255RC1Q027SBEA'])) {
        $satz = [];
        foreach ($r['B235RC1Q027SBEA'] as $t => $w) {
            if (!empty($r['A255RC1Q027SBEA'][$t])) {
                $satz[substr($t, 0, 7)] = $w / $r['A255RC1Q027SBEA'][$t] * 100;
            }
        }
        if ($satz) {
            $reihen[] = makroReihe('fred-zollsatz-usa', 'fred', 'FRED, Zolleinnahmen je Wareneinfuhr (BEA)', 'politik', 'Effektiver US-Zollsatz (erhoben)', '%', $url('B235RC1Q027SBEA'), $satz,
                prozent(end($satz)) . ' der Wareneinfuhr fließen als Zoll, im Quartal ab ' . monatName(array_key_last($satz)) . '. Der gesetzliche Satz liegt höher.', 0.5);
        }
    }
    if (!$reihen) {
        throw new RuntimeException('keine Reihe lesbar');
    }
    return ['reihen' => $reihen];
}

/** TFP-Wachstum des US-Unternehmenssektors (Fernald), Quartalsblatt der Excel-Datei. */
function quelleTfp(): array
{
    $datei = tempnam(sys_get_temp_dir(), 'tfp');
    file_put_contents($datei, hole('https://www.frbsf.org/wp-content/uploads/quarterly_tfp.xlsx'));
    $zip = new ZipArchive();
    if ($zip->open($datei) !== true) {
        unlink($datei);
        throw new RuntimeException('kein XLSX');
    }
    $texte = [];
    if (preg_match_all('/<si>(.*?)<\/si>/s', (string) $zip->getFromName('xl/sharedStrings.xml'), $m)) {
        $texte = array_map(fn($x) => html_entity_decode(strip_tags($x), ENT_QUOTES | ENT_XML1), $m[1]);
    }
    $blatt = (string) $zip->getFromName('xl/worksheets/sheet2.xml');
    $zip->close();
    unlink($datei);
    $spalte = [];
    $punkte = [];
    $ab = (int) date('Y') - 4;
    preg_match_all('/<row [^>]*>(.*?)<\/row>/s', $blatt, $zeilen);
    foreach ($zeilen[1] as $zeile) {
        $zellen = [];
        preg_match_all('/<c r="([A-Z]+)\d+"([^>]*?)(?:\/>|>(.*?)<\/c>)/s', $zeile, $cs, PREG_SET_ORDER);
        foreach ($cs as $c) {
            $v = preg_match('/<v>(.*?)<\/v>/', $c[3] ?? '', $vm) ? $vm[1] : '';
            $zellen[$c[1]] = str_contains($c[2], 't="s"') && $v !== '' ? ($texte[(int) $v] ?? '') : $v;
        }
        if (!$spalte && in_array('date', $zellen, true)) {
            $spalte = array_flip($zellen);
            continue;
        }
        $q = $zellen[$spalte['date'] ?? 'A'] ?? '';
        $w = $zellen[$spalte['dtfp'] ?? ''] ?? '';
        if (preg_match('/^(\d{4}):Q([1-4])$/', $q, $qm) && is_numeric($w) && (int) $qm[1] >= $ab) {
            $punkte[sprintf('%s-%02d', $qm[1], ((int) $qm[2] - 1) * 3 + 1)] = (float) $w;
        }
    }
    if (!$punkte) {
        throw new RuntimeException('Spalte dtfp nicht gefunden');
    }
    $letzte4 = array_slice($punkte, -4);
    return ['reihen' => [makroReihe('sffed-tfp-usa', 'sffed', 'SF Fed, Fernald (dtfp)', 'technologie', 'TFP-Wachstum USA', '% p. a.',
        'https://www.frbsf.org/research-and-insights/data-and-indicators/total-factor-productivity-tfp/', $punkte,
        prozent(array_sum($letzte4) / count($letzte4)) . ' pro Jahr im Mittel der letzten vier Quartale (US-Unternehmenssektor).', 0.5)]];
}

/** Eurostat: Industrie Deutschland, Kerninflation und BIP der Eurozone. */
function quelleEurostatMakro(): array
{
    $basis = 'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/';
    $antworten = holeAlle([
        'industrie' => ['url' => $basis . 'sts_inpr_m?geo=DE&nace_r2=C&s_adj=SCA&unit=I21&indic_bt=PRD&lastTimePeriod=48'],
        // Seit Januar 2026 nach ECOICOP 2 in einem neuen Datensatz; die alte Reihe endet 12/2025.
        'kern-alt' => ['url' => $basis . 'prc_hicp_manr?geo=EA&coicop=TOT_X_NRG_FOOD&lastTimePeriod=36'],
        'kern-neu' => ['url' => $basis . 'prc_hicp_minr?geo=EA&coicop18=TOT_X_NRG_FOOD&unit=RCH_A&lastTimePeriod=36'],
        'bip' => ['url' => $basis . 'namq_10_gdp?geo=EA&na_item=B1GQ&unit=CLV_PCH_SM&s_adj=SCA&lastTimePeriod=16'],
    ], 4, 60);
    $werte = function (string $k) use ($antworten): array {
        if (($antworten[$k]['status'] ?? 0) !== 200) {
            return [];
        }
        $d = json_decode($antworten[$k]['text'], true);
        $aus = [];
        foreach ($d['dimension']['time']['category']['index'] ?? [] as $t => $i) {
            if (isset($d['value'][(string) $i])) {
                $aus[$t] = (float) $d['value'][(string) $i];
            }
        }
        return $aus;
    };
    $reihen = [];
    if ($ip = $werte('industrie')) {
        $reihen[] = makroReihe('eurostat-industrie-de', 'eurostat-makro', 'Eurostat, Produktion im Verarbeitenden Gewerbe (sts_inpr_m)', 'wirtschaft',
            'Industrieproduktion Deutschland (Eurostat)', 'Index 2021=100', 'https://ec.europa.eu/eurostat/databrowser/view/sts_inpr_m/default/table', $ip,
            'Index ' . zahlDe(end($ip)) . ' im ' . monatName(array_key_last($ip)) . ', saisonbereinigt.', 1);
    }
    $kern = array_replace($werte('kern-alt'), $werte('kern-neu'));
    if ($kern) {
        $reihen[] = makroReihe('eurostat-kerninflation-ea', 'eurostat-makro', 'Eurostat, HICP ohne Energie und Lebensmittel', 'wirtschaft',
            'Kerninflation Eurozone', '%', 'https://ec.europa.eu/eurostat/databrowser/view/prc_hicp_minr/default/table', $kern,
            prozent(end($kern)) . ' zum Vorjahresmonat im ' . monatName(array_key_last($kern)) . '.', 0.3);
    }
    if ($bip = $werte('bip')) {
        $quartale = [];
        foreach ($bip as $t => $w) {
            $quartale[sprintf('%s-%02d', substr($t, 0, 4), ((int) substr($t, -1) - 1) * 3 + 1)] = $w;
        }
        $reihen[] = makroReihe('eurostat-bip-ea', 'eurostat-makro', 'Eurostat, BIP preisbereinigt (namq_10_gdp)', 'wirtschaft', 'Wirtschaftswachstum Eurozone', '%',
            'https://ec.europa.eu/eurostat/databrowser/view/namq_10_gdp/default/table', $quartale,
            prozent(end($quartale)) . ' zum Vorjahresquartal (' . array_key_last($bip) . ').', 0.3);
    }
    if (!$reihen) {
        throw new RuntimeException('keine Reihe lesbar');
    }
    return ['reihen' => $reihen];
}

// =============================================================================
// Messreihen zu Demokratie, Sicherheit und Vermoegen
// =============================================================================

/**
 * Messreihen zu den Treibern, die das Weltmodell bisher nicht messen konnte
 * (Leitstand Foresight, 15.10.2026: Krieg in Europa mit deutscher Beteiligung,
 * Radikalisierung, Abbau liberaler Demokratie und Freiheitsrechte, Angriffe auf
 * kritische Infrastruktur, Oligarchie; Treiber N1, G6, G4, T10, T9, M8, M4).
 * Die Liste stammt von D2 (foresight-model, data/entwurf/anzeichen_sorgen.json,
 * Lizenzen dort am 15.10.2026 geprueft). Ohne Sammler bleiben vorerst die
 * Jahreszahlen der Polizeilichen Kriminalstatistik (PMK) und der
 * Stromausfall-Kennzahl SAIDI: PDF und Webseite, von Hand.
 *
 * Diese Reihen gehen nur in wissensstand.json und stehen neutral als Zahlen
 * da - ohne Bezug zu einer Person; die Seite ist oeffentlich. Die Weltlage
 * bewegen sie erst, wenn das Modell ein Anzeichen mit ihrer id fuehrt (Urteil,
 * Karl). Jede Reihe nennt Herausgeber und Lizenz in `quelleName`, wie die
 * Lizenz es verlangt.
 *
 * Ein Eintrag je Reihe:
 *
 *   'id'         stabil; das Anzeichen im Modell verweist darauf (anzeichen.json: reihe)
 *   'treiber'    nur zur Dokumentation: welchen Treiber sie messbar macht
 *   'steep'      gesellschaft | technologie | wirtschaft | umwelt | politik
 *   'titel'      kurz und neutral, steht unter "Zahlen"
 *   'einheit'
 *   'quelleName' Herausgeber, Datensatz, Lizenz
 *   'url'        die Reihe fuer Menschen
 *   'art'        statistik (Standard) | messung (laufend gemessen)
 *   'schwelle'   ab dieser Aenderung zum Vorjahr gilt "steigt" oder "faellt" (nur Anzeige)
 *   'zurueck'    Punkte bis zum Vorjahr: 12 bei Monatswerten, 4 bei Quartalen, 1 bei Jahreswerten
 *   'stellen'    Nachkommastellen der gespeicherten Werte (Schwellen im Modell brauchen mehr als zwei)
 *   'abruf'      fn(): array - [JJJJ-MM => wert] (Jahreswerte als JJJJ-01); wirft bei Fehler
 *   'aussage'    fn(array $werte): string - ein Satz mit Stand
 *
 * Jede Reihe ist eine eigene Quelle: faellt sie aus, bleibt ihr letzter Stand
 * stehen (Hauptlauf), und die uebrigen laufen weiter. Mindestabstand und
 * Halbwertszeiten gelten wie bei allen Quellen (voller Lauf hoechstens alle
 * sechs Stunden); Dateien, die zwei Reihen brauchen, werden je Lauf einmal geholt.
 */
function sorgenReihen(): array
{
    $dez = fn(float $x, int $n = 2): string => number_format($x, $n, ',', '.');
    $quartal = fn(string $t): string => (intdiv((int) substr($t, 5, 2) - 1, 3) + 1) . '. Quartal ' . substr($t, 0, 4);

    // V-Dem ueber Our World in Data: [JJJJ-01 => wert] eines Landes.
    $vdem = function (string $datei, string $land): array {
        $csv = array_map(fn($z) => str_getcsv($z, ',', '"', ''), preg_split('/\r?\n/', trim(sorgenDatei("https://ourworldindata.org/grapher/$datei.csv?v=1&csvType=full&useColumnShortNames=true"))));
        if (($csv[0][1] ?? '') !== 'code' || ($csv[0][2] ?? '') !== 'year') {
            throw new RuntimeException("$datei: unbekannte Spalten");
        }
        $aus = [];
        foreach (array_slice($csv, 1) as $z) {
            if (($z[1] ?? '') === $land && is_numeric($z[3] ?? '')) {
                $aus[$z[2] . '-01'] = (float) $z[3];
            }
        }
        return $aus;
    };
    $vdemAussage = fn(string $was) => fn(array $w): string => $was . ' ' . $dez(end($w), 3) . ' im Jahr ' . substr(array_key_last($w), 0, 4)
        . ' (Skala 0 bis 1), ' . $dez(array_values(array_slice($w, -2, 1))[0] ?? end($w), 3) . ' im Vorjahr.';
    $vdemQuelle = 'V-Dem Institute (Universität Göteborg), %s, CC BY-SA 4.0, über Our World in Data';

    return [
        [
            'id' => 'gpr-deu', 'treiber' => ['N1', 'G6'], 'steep' => 'politik',
            'titel' => 'Geopolitisches Risiko in Deutschland (Zeitungsindex)', 'einheit' => '% der Artikel',
            'quelleName' => 'Caldara und Iacoviello, Geopolitical Risk Index, Länder-Index Deutschland (GPRC_DEU), CC BY',
            'url' => 'https://www.matteoiacoviello.com/gpr.htm',
            'schwelle' => 0.1, 'zurueck' => 12, 'stellen' => 3,
            'abruf' => function (): array {
                $s = dtaSpalten(sorgenDatei('https://www.matteoiacoviello.com/gpr_files/data_gpr_export.dta'), ['month', 'GPRC_DEU']);
                $aus = [];
                foreach ($s['month'] as $i => $m) {
                    // Stata zaehlt Monate ab Januar 1960 (auch negativ: vor 1960).
                    $m = (int) round($m);
                    $monat = (($m % 12) + 12) % 12;
                    $aus[sprintf('%04d-%02d', 1960 + intdiv($m - $monat, 12), $monat + 1)] = $s['GPRC_DEU'][$i];
                }
                return $aus;
            },
            'aussage' => function (array $w) use ($dez): string {
                $sortiert = array_values($w);
                sort($sortiert);
                return 'Anteil der Zeitungsartikel, die Deutschland mit geopolitischen Risiken nennen: ' . $dez(end($w)) . ' % im ' . monatName(array_key_last($w))
                    . '; Median seit ' . substr(array_key_first($w), 0, 4) . ': ' . $dez($sortiert[intdiv(count($sortiert), 2)]) . ' %.';
            },
        ],
        [
            'id' => 'vdem-libdem-de', 'treiber' => ['G4'], 'steep' => 'politik',
            'titel' => 'Liberale Demokratie in Deutschland (V-Dem-Index)', 'einheit' => 'Index 0 bis 1',
            'quelleName' => sprintf($vdemQuelle, 'Liberal Democracy Index'), 'url' => 'https://ourworldindata.org/grapher/liberal-democracy-index',
            'schwelle' => 0.01, 'zurueck' => 1, 'stellen' => 3,
            'abruf' => fn(): array => $vdem('liberal-democracy-index', 'DEU'),
            'aussage' => $vdemAussage('Liberal Democracy Index Deutschland:'),
        ],
        [
            'id' => 'vdem-libdem-usa', 'treiber' => ['G4'], 'steep' => 'politik',
            'titel' => 'Liberale Demokratie in den USA (V-Dem-Index)', 'einheit' => 'Index 0 bis 1',
            'quelleName' => sprintf($vdemQuelle, 'Liberal Democracy Index'), 'url' => 'https://ourworldindata.org/grapher/liberal-democracy-index',
            'schwelle' => 0.01, 'zurueck' => 1, 'stellen' => 3,
            'abruf' => fn(): array => $vdem('liberal-democracy-index', 'USA'),
            'aussage' => $vdemAussage('Liberal Democracy Index USA:'),
        ],
        [
            'id' => 'vdem-meinungsfreiheit-de', 'treiber' => ['T10', 'G4'], 'steep' => 'gesellschaft',
            'titel' => 'Meinungs- und Informationsfreiheit in Deutschland (V-Dem-Index)', 'einheit' => 'Index 0 bis 1',
            'quelleName' => sprintf($vdemQuelle, 'Freedom of Expression and Alternative Sources of Information Index'), 'url' => 'https://ourworldindata.org/grapher/freedom-of-expression-index',
            'schwelle' => 0.01, 'zurueck' => 1, 'stellen' => 3,
            'abruf' => fn(): array => $vdem('freedom-of-expression-index', 'DEU'),
            'aussage' => $vdemAussage('Freedom of Expression Index Deutschland:'),
        ],
        [
            'id' => 'cisa-kev-monat', 'treiber' => ['T9'], 'steep' => 'technologie', 'art' => 'messung',
            'titel' => 'Ausgenutzte Sicherheitslücken je Monat (CISA-Katalog)', 'einheit' => 'neue Einträge',
            'quelleName' => 'CISA, Known Exploited Vulnerabilities Catalog, CC0',
            'url' => 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog',
            'schwelle' => 3, 'zurueck' => 12, 'stellen' => 0,
            'abruf' => function (): array {
                $k = json(sorgenDatei('https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json'));
                $eintraege = $k['vulnerabilities'] ?? [];
                if (!$eintraege) {
                    throw new RuntimeException('cisa-kev: keine Einträge');
                }
                // Je Monat nach dateAdded, ab Juni 2022 (davor Altbestand der Einführung), ohne den laufenden Monat; Monate ohne Eintrag zählen null.
                $laufend = substr((string) ($k['dateReleased'] ?? date('Y-m')), 0, 7);
                $je = [];
                foreach ($eintraege as $e) {
                    $monat = substr((string) ($e['dateAdded'] ?? ''), 0, 7);
                    if (preg_match('/^\d{4}-\d{2}$/', $monat) && $monat >= '2022-06' && $monat < $laufend) {
                        $je[$monat] = ($je[$monat] ?? 0) + 1;
                    }
                }
                $aus = [];
                for ($m = '2022-06'; $m < $laufend; $m = date('Y-m', strtotime($m . '-01 +1 month'))) {
                    $aus[$m] = (float) ($je[$m] ?? 0);
                }
                return $aus;
            },
            'aussage' => function (array $w): string {
                $letzte = array_slice($w, -3);
                return zahlDe(end($w)) . ' neue Einträge im ' . monatName(array_key_last($w)) . ', Dreimonatsmittel ' . zahlDe(array_sum($letzte) / count($letzte)) . '.';
            },
        ],
        [
            'id' => 'fed-dfa-top01', 'treiber' => ['M8'], 'steep' => 'wirtschaft',
            'titel' => 'Vermögensanteil der reichsten 0,1 % in den USA', 'einheit' => '% des Nettovermögens',
            'quelleName' => 'Board of Governors of the Federal Reserve System (US), Distributional Financial Accounts, über FRED (gemeinfrei, Quellenangabe erbeten)',
            'url' => 'https://fred.stlouisfed.org/series/WFRBSTP1300',
            'schwelle' => 0.3, 'zurueck' => 4, 'stellen' => 3,
            'abruf' => function (): array {
                $aus = [];
                foreach (fredReihe(sorgenDatei('https://fred.stlouisfed.org/graph/fredgraph.csv?id=WFRBSTP1300'), 'WFRBSTP1300') as $t => $w) {
                    $aus[substr($t, 0, 7)] = $w;
                }
                return $aus;
            },
            'aussage' => fn(array $w): string => 'Die reichsten 0,1 % der Haushalte halten ' . $dez(end($w), 1) . ' % des Nettovermögens (' . $quartal(array_key_last($w)) . '), vor einem Jahr '
                . $dez(array_values(array_slice($w, -5, 1))[0] ?? end($w), 1) . ' %.',
        ],
    ];
}

/** Eine Reihe aus der Liste oben: abrufen, in das Format des Wissensstands bringen. */
function sorgenReihe(array $d): array
{
    $werte = ($d['abruf'])();
    if (!$werte) {
        throw new RuntimeException($d['id'] . ': keine Werte');
    }
    ksort($werte);
    return makroReihe(
        $d['id'], $d['id'], $d['quelleName'], $d['steep'], $d['titel'], $d['einheit'], $d['url'], $werte, ($d['aussage'])($werte),
        (float) $d['schwelle'], (int) ($d['zurueck'] ?? 12), (int) ($d['stellen'] ?? 2),
    );
}

/** Eine Datei je Lauf nur einmal holen - V-Dem liefert Deutschland und die USA aus derselben CSV. */
function sorgenDatei(string $url): string
{
    static $geholt = [];
    return $geholt[$url] ??= hole($url);
}

/**
 * Spalten aus einer Stata-Datei (.dta, Format 118, kleinstes Byte zuerst) - fuer den GPR-Export, der nur als
 * xls und dta vorliegt. Gelesen werden nur Zahlenspalten; Fehlwerte fehlen im Ergebnis, die Zeilennummern bleiben.
 * Ein anderes Format wirft einen Fehler, damit die Quelle sichtbar ausfaellt statt falsche Zahlen zu liefern.
 *
 * @param string[] $namen
 * @return array<string, array<int, float>> Spaltenname => [Zeile => Wert]
 */
function dtaSpalten(string $b, array $namen): array
{
    $tag = function (string $name) use ($b): int {
        $i = strpos($b, "<$name>");
        if ($i === false) {
            throw new RuntimeException("dta: <$name> fehlt");
        }
        return $i + strlen($name) + 2;
    };
    if (substr($b, $tag('release'), 3) !== '118' || substr($b, $tag('byteorder'), 3) !== 'LSF') {
        throw new RuntimeException('dta: nur Format 118, kleinstes Byte zuerst');
    }
    $k = unpack('v', substr($b, $tag('K'), 2))[1];
    $n = unpack('P', substr($b, $tag('N'), 8))[1];
    $karte = array_values(unpack('P14', substr($b, $tag('map'), 112)));
    $typen = array_values(unpack("v$k", substr($b, $karte[2] + strlen('<variable_types>'), 2 * $k)));
    $vn = $karte[3] + strlen('<varnames>');
    $vf = $karte[5] + strlen('<formats>');
    $spalten = [];
    $versatz = 0;
    $breiten = [65526 => 8, 65527 => 4, 65528 => 4, 65529 => 2, 65530 => 1, 32768 => 8];
    foreach ($typen as $i => $typ) {
        $breite = $breiten[$typ] ?? ($typ >= 1 && $typ <= 2045 ? $typ : null);
        if ($breite === null) {
            throw new RuntimeException("dta: unbekannter Typ $typ");
        }
        $name = explode("\0", substr($b, $vn + 129 * $i, 129))[0];
        $spalten[$name] = ['typ' => $typ, 'versatz' => $versatz, 'format' => explode("\0", substr($b, $vf + 57 * $i, 57))[0]];
        $versatz += $breite;
    }
    $zeile = $versatz;
    $daten = $karte[9] + strlen('<data>');
    $aus = [];
    foreach ($namen as $name) {
        $s = $spalten[$name] ?? throw new RuntimeException("dta: Spalte $name fehlt");
        $lesen = match ($s['typ']) {
            65526 => ['e', 8, 1e300, fn($x) => $x],
            65527 => ['g', 4, 1e30, fn($x) => $x],
            default => throw new RuntimeException("dta: Spalte $name ist keine Kommazahl"),
        };
        $werte = [];
        for ($r = 0; $r < $n; $r++) {
            $x = unpack($lesen[0], substr($b, $daten + $r * $zeile + $s['versatz'], $lesen[1]))[1];
            if (is_finite($x) && abs($x) < $lesen[2]) {
                $werte[$r] = (float) $x;
            }
        }
        $aus[$name] = $werte;
    }
    if (($spalten['month']['format'] ?? '') !== '%tm' && in_array('month', $namen, true)) {
        throw new RuntimeException('dta: month ist kein Monatsdatum');
    }
    // Nur Zeilen, in denen alle gewuenschten Spalten einen Wert haben, in derselben Reihenfolge.
    $gemeinsam = array_keys(array_intersect_key(...array_values($aus)));
    return array_map(fn($w) => array_intersect_key($w, array_flip($gemeinsam)), $aus);
}

// =============================================================================
// Trends aus dem Nachrichtenstrom
// =============================================================================

/**
 * Themen, die sich in den Meldungen haeufen - und ob sie zulegen.
 *
 * Grundlage sind die Schlagworte, die die tagesschau-Redaktion selbst vergibt.
 * Gezaehlt und verglichen wird NUR die tagesschau: ihre Tagesseiten decken
 * beide Wochen gleich ab. Der Deutschlandfunk-Feed reicht nur Stunden zurueck -
 * mitgezaehlt, liesse er jedes Thema in der laufenden Woche wachsen (Karl,
 * 27.09.2026: "deutlich mehr als in der Woche davor" war so ein Artefakt).
 * Seine Treffer stehen nur als Belege dabei. Die Beschreibung nennt beide
 * Zahlen statt eines Urteils.
 */
function themenImNachrichtenstrom(array $bestand, int $jetzt): array
{
    $alter = fn(array $s) => ($jetzt - strtotime($s['datum'])) / TAG;
    $meldungen = array_values(array_filter($bestand, fn($s) => $s['art'] === 'nachricht' && $alter($s) < TAGE_ZURUECK));
    if (!$meldungen) {
        return [];
    }
    // Themen sind die Schlagworte der tagesschau. Gezaehlt wird aber jede
    // Meldung, die das Thema traegt ODER in Titel und Anriss nennt: die
    // Redaktion vergibt Schlagworte uneinheitlich ("Friedrich Merz" stand an
    // 5 von 19 Meldungen ueber Merz).
    $themen = [];
    foreach ($meldungen as $m) {
        if ($m['quelle'] === 'tagesschau') {
            foreach ($m['stichworte'] as $t) {
                $themen[(string) $t] = true;
            }
        }
    }
    // Als ganzes Wort: "Euro" soll nicht "Europa" treffen.
    $alsWort = fn(string $text, string $t) => mb_strlen($t) >= 4
        && preg_match('/(?<!\p{L})' . preg_quote($t, '/') . '(?!\p{L})/iu', $text) === 1;
    $nennt = fn(array $m, string $t) => in_array($t, $m['stichworte'], true) || $alsWort($m['titel'] . ' ' . $m['text'], $t);
    $zuThema = [];
    foreach (array_keys($themen) as $t) {
        $t = (string) $t;
        foreach ($meldungen as $m) {
            // Deutschlandfunk nur ueber den Titel - sein Anriss ist laenger und nennt mehr nebenbei.
            if ($m['quelle'] === 'tagesschau' ? $nennt($m, $t) : $alsWort($m['titel'], $t)) {
                $zuThema[$t][] = $m;
            }
        }
    }
    // Zu allgemein ist, was in mehr als jeder zwanzigsten Meldung steckt.
    $zuAllgemein = count($meldungen) / 20;
    $kandidaten = [];
    foreach ($zuThema as $thema => $ms) {
        $thema = (string) $thema;
        if (count($ms) > $zuAllgemein || in_array(mb_strtolower($thema), KULISSE, true)) {
            continue;
        }
        $gezaehlt = array_filter($ms, fn($m) => $m['quelle'] === 'tagesschau');
        $verlauf = array_fill(0, TAGE_ZURUECK, 0);
        foreach ($gezaehlt as $m) {
            $i = TAGE_ZURUECK - 1 - (int) floor($alter($m));
            if ($i >= 0 && $i < TAGE_ZURUECK) {
                $verlauf[$i]++;
            }
        }
        $woche = array_sum(array_slice($verlauf, -7));
        $vorwoche = array_sum(array_slice($verlauf, 0, -7));
        if ($woche < 4) {
            continue;
        }
        // Geglaettet, damit 5 gegen 0 Meldungen nicht als Verfuenffachung durchgeht.
        $momentum = ($woche + 3) / ($vorwoche + 3);
        $kandidaten[] = compact('thema', 'ms', 'verlauf', 'woche', 'vorwoche', 'momentum');
    }
    usort($kandidaten, fn($a, $b) => $b['woche'] * sqrt($b['momentum']) <=> $a['woche'] * sqrt($a['momentum']));
    // Varianten desselben Themas ("Linke", "Die Linke", "Die LINKE") nur einmal:
    // weg, was zu drei Vierteln dieselben Meldungen betrifft wie ein schon genommenes.
    $genommen = [];
    foreach ($kandidaten as $k) {
        $ids = array_column($k['ms'], 'id');
        foreach ($genommen as $g) {
            $gemeinsam = count(array_intersect($ids, array_column($g['ms'], 'id')));
            if ($gemeinsam >= 0.75 * min(count($ids), count($g['ms']))) {
                continue 2;
            }
        }
        $genommen[] = $k;
    }
    $kandidaten = $genommen;
    return array_map(fn($k) => [
        'id' => 'thema-' . preg_replace('/\W+/u', '-', mb_strtolower($k['thema'])),
        'art' => 'thema',
        'steep' => mehrheit(array_column($k['ms'], 'steep')),
        'titel' => $k['thema'],
        'beschreibung' => "{$k['woche']} Meldungen in den letzten sieben Tagen, {$k['vorwoche']} in den sieben davor "
            . "(tagesschau, mit Schlagwort oder Nennung „{$k['thema']}“).",
        'momentum' => $k['momentum'],
        'verlauf' => $k['verlauf'],
        'belege' => array_slice(array_values(array_unique(array_column($k['ms'], 'id'))), 0, 10),
    ], array_slice($kandidaten, 0, 16));
}

/** Das Suchmuster eines Themenfelds: seine Woerter am Wortanfang, kurze als ganzes Wort. Gegen kleingeschriebenen Text. */
function themaMuster(array $de): string
{
    return '/(?<!\p{L})(' . implode('|', array_map(
        fn($w) => preg_quote(mb_strtolower($w), '/') . (mb_strlen($w) <= 3 ? '(?!\p{L})' : '') . (THEMA_SPERREN[mb_strtolower($w)] ?? ''),
        $de,
    )) . ')/u';
}

/**
 * Die Themenfelder mit ihrem Gewicht aus den Nachrichten, den Kennzahlen dazu
 * und neuer Forschung. Sortiert nach Gewicht - oben steht, was gerade zaehlt.
 */
function themenfelder(array $signale, array $reihen, int $jetzt): array
{
    $alter = fn(array $s) => ($jetzt - strtotime($s['datum'])) / TAG;
    $meldungen = array_values(array_filter($signale, fn($s) => $s['quelle'] === 'tagesschau' && $alter($s) < TAGE_ZURUECK));
    $forschung = array_values(array_filter($signale, fn($s) => $s['art'] === 'forschung'));
    $felder = [];
    foreach (THEMENFELDER as [$id, $name, $steep, $de, $en, $reihenIds]) {
        $muster = themaMuster($de);
        $treffer = array_values(array_filter($meldungen, fn($m) => preg_match(
            $muster,
            mb_strtolower($m['titel'] . ' ' . $m['text'] . ' ' . implode(' ', $m['stichworte'])),
        ) === 1));
        $verlauf = array_fill(0, TAGE_ZURUECK, 0);
        foreach ($treffer as $m) {
            $i = TAGE_ZURUECK - 1 - (int) floor($alter($m));
            if ($i >= 0) {
                $verlauf[$i]++;
            }
        }
        $woche = array_sum(array_slice($verlauf, -7));
        $vorwoche = array_sum(array_slice($verlauf, 0, -7));
        usort($treffer, fn($a, $b) => strcmp($b['datum'], $a['datum']));

        // Forschung: aus OpenAlex fuer dieses Feld geholt, oder ein Paper, dessen
        // Titel und Zusammenfassung mindestens zwei Suchwoerter des Felds enthalten -
        // darunter eins, das nicht nur "KI" oder "Politik" heisst. Sonst hinge
        // jedes KI-Paper an "KI und Arbeitswelt".
        $allgemein = ['artificial', 'intelligence', 'policy', 'change', 'system', 'systems', 'prices', 'social', 'media', 'united', 'states', 'europe', 'european', 'reform'];
        $suchwoerter = array_filter(explode(' ', mb_strtolower($en)), fn($w) => mb_strlen($w) >= 5);
        $studien = array_values(array_filter($forschung, function ($s) use ($id, $suchwoerter, $allgemein) {
            if (in_array($id, $s['themen'] ?? [], true)) {
                return true;
            }
            $text = mb_strtolower($s['titel'] . ' ' . $s['text']);
            $treffer = array_filter($suchwoerter, fn($w) => str_contains($text, $w));
            return count($treffer) >= 2 && array_diff($treffer, $allgemein);
        }));
        usort($studien, fn($a, $b) => [$b['guete'], $b['datum']] <=> [$a['guete'], $a['datum']]);

        $zugehoerig = array_values(array_filter(array_column($reihen, 'id'), fn($r) => array_filter(
            $reihenIds,
            fn($muster) => str_ends_with($muster, '*') ? str_starts_with($r, rtrim($muster, '*')) : $r === $muster,
        )));
        $felder[] = [
            'id' => $id,
            'name' => $name,
            'steep' => $steep,
            // Gewicht: Meldungen der Woche, verstaerkt, wenn es mehr werden.
            'gewicht' => round($woche * sqrt(($woche + 3) / ($vorwoche + 3)), 2),
            'woche' => $woche,
            'vorwoche' => $vorwoche,
            'verlauf' => $verlauf,
            'meldungen' => array_slice(array_column($treffer, 'id'), 0, 6),
            'reihen' => $zugehoerig,
            'forschung' => array_slice(array_column($studien, 'id'), 0, 4),
        ];
    }
    usort($felder, fn($a, $b) => $b['gewicht'] <=> $a['gewicht']);
    return $felder;
}

function mehrheit(array $ebenen): string
{
    $n = array_count_values($ebenen);
    arsort($n);
    return (string) array_key_first($n);
}

// =============================================================================
// Wetter: die Radardaten in drei Zeitschichten (radar/wetter.json, wetter/v1)
// =============================================================================

// ---- WETTER-ANFANG (die Tests laden genau diesen Abschnitt) ----

/**
 * Boeen (Stunden bis Tage), Luftdruck (Wochen) und Fronten (Themen, die sich
 * mischen) fuer die Wetter-Ansicht des Foresight Studios (Karl, 16.10.2026:
 * Hypes, Moden und Launen, die nicht von Dauer sein muessen). Nur eigene
 * Radardaten. Die Schwellen (Konstanten WETTER_* im Kopf der Datei) sind eine Darstellungsregel, kein Urteil.
 */

/** Das Wetter der letzten sieben Tage, gegen die vier Wochen davor. $themen sind die Themenfelder des Wissensstands, $reihen und $trends die Messreihen und Trends fuer die Saison. */
function wetter(array $signale, array $themen, int $jetzt, array $reihen = [], array $trends = []): array
{
    $tag = fn(array $s) => (int) floor(($jetzt - strtotime($s['datum'])) / TAG);
    $nachrichten = array_values(array_filter($signale, fn($s) => in_array($s['quelle'], WETTER_QUELLEN, true) && preg_match(WETTER_RAUSCHEN, $s['titel']) !== 1));
    // Faktor der Boeen: Quellen mit zwei brauchbaren Vorwochen. Zaehlungen (Regionen, Luftdruck): Quellen, deren Vorwoche brauchbar ist.
    $bezug = wetterBezug($nachrichten, $tag, WETTER_VORWOCHEN_MIN);
    $zaehlen = array_keys(array_filter(wetterBezug($nachrichten, $tag, 1), fn($wochen) => in_array(1, $wochen, true)));
    // Themen der Saison zaehlen in denselben Quellen wie der Luftdruck, und nur, wenn jede davon alle vier Wochen vergleichbar abdeckt. Dann
    // sind ihre letzten zwei Wochen Woche und Vorwoche der Wetterlage. Vorher zaehlte sie in weniger Quellen (22.10.2026, "Wohnen und Mieten":
    // Saison 2 Meldungen diese Woche und fallend, Wetterlage 49 und steigend). Fehlt einer Quelle eine Woche, zeigt nur die Wetterlage das Thema.
    $vierWochen = array_keys(array_filter(wetterBezug($nachrichten, $tag, 1), fn($wochen) => array_diff([1, 2, 3], $wochen) === []));
    $saisonQuellen = array_diff($zaehlen, $vierWochen) === [] ? $zaehlen : [];
    return [
        'schema' => 'wetter/v1',
        'stand' => iso($jetzt),
        'zeitraum' => ['woche_von' => gmdate('Y-m-d', $jetzt - 7 * TAG), 'woche_bis' => gmdate('Y-m-d', $jetzt)],
        'regionen' => wetterRegionen($nachrichten, $zaehlen, $tag),
        'boeen' => wetterBoeen($nachrichten, $bezug, $tag, $jetzt, $zaehlen),
        'luftdruck' => wetterLuftdruck($themen, $nachrichten, $zaehlen, $tag),
        'fronten' => wetterFronten($nachrichten, $tag, $zaehlen, $jetzt),
        'saison' => wetterSaisonSicher($reihen, $trends, $nachrichten, $saisonQuellen, $tag, $jetzt),
    ];
}

/** Die Saison darf die Boeen nicht mitnehmen: stolpert sie ueber eine Reihe, die anders aussieht als gedacht, bleibt sie leer und der Lauf meldet es. */
function wetterSaisonSicher(array $reihen, array $trends, array $nachrichten, array $quellen, callable $tag, int $jetzt): array
{
    try {
        return wetterSaison($reihen, $trends, $nachrichten, $quellen, $tag, $jetzt);
    } catch (Throwable $e) {
        fwrite(STDERR, '  ✗ Saison nicht gerechnet: ' . $e->getMessage() . "\n");
        return [];
    }
}

/**
 * Welche Quellen sich fuer den Vergleich mit frueheren Wochen eignen: [quelle => brauchbare Vorwochen], mit mindestens $mindestens davon.
 * Die tagesschau deckt mit ihren Tagesseiten alle Wochen gleich ab. Die anderen reichen nur 10 bis 21 Tage
 * zurueck (KURZLEBIG), kamen im Oktober dazu oder melden seit dem stuendlichen Lauf ein Vielfaches - mitgezaehlt
 * liessen sie jedes Thema wachsen (derselbe Grund wie bei den Trends im Nachrichtenstrom). Mit der Zeit
 * kommen sie von selbst dazu: fuer Zaehlungen mit einer brauchbaren Vorwoche, fuer den Faktor einer Boee mit zweien.
 */
function wetterBezug(array $nachrichten, callable $tag, int $mindestens = WETTER_VORWOCHEN_MIN): array
{
    $summe = [];
    foreach ($nachrichten as $s) {
        $w = intdiv($tag($s), 7);
        if ($w >= 0 && $w <= WETTER_VORWOCHEN) {
            $summe[$s['quelle']][$w] = ($summe[$s['quelle']][$w] ?? 0) + 1;
        }
    }
    $bezug = [];
    foreach ($summe as $quelle => $je) {
        $brauchbar = array_values(array_filter(range(1, WETTER_VORWOCHEN), fn($w) => ($je[$w] ?? 0) >= WETTER_VORWOCHE_ANTEIL * ($je[0] ?? 0)));
        if (($je[0] ?? 0) > 0 && count($brauchbar) >= $mindestens) {
            $bezug[$quelle] = $brauchbar;
        }
    }
    return $bezug;
}

function wetterRegionen(array $nachrichten, array $quellen, callable $tag): array
{
    $aus = [];
    foreach (WETTER_REGIONEN as $id => $name) {
        $aus[$id] = ['id' => $id, 'name' => $name, 'meldungen_woche' => 0, 'meldungen_vorwoche' => 0];
    }
    foreach ($nachrichten as $s) {
        $t = $tag($s);
        if (isset($aus[$s['steep']]) && $t < 14 && in_array($s['quelle'], $quellen, true)) {
            $aus[$s['steep']][$t < 7 ? 'meldungen_woche' : 'meldungen_vorwoche']++;
        }
    }
    return array_values($aus);
}

/** Wie stark ein Thema zu- oder abnimmt: Woche gegen Vorwoche. */
function wetterRichtung(int $woche, int $vorwoche): string
{
    $schwelle = max(WETTER_GLEICH_MIN, WETTER_GLEICH_ANTEIL * $vorwoche);
    return $woche - $vorwoche >= $schwelle ? 'steigt' : ($vorwoche - $woche >= $schwelle ? 'faellt' : 'gleich');
}

/**
 * Luftdruck: Woche gegen Vorwoche je Themenfeld. Gezaehlt wird in allen Quellen, deren Vorwoche brauchbar ist ($quellen); die tagesschau allein
 * traegt Technik und Wissenschaft nicht. Ein Thema, das der Katalog nicht kennt, behaelt die Zahlen aus dem Wissensstand. Themen ohne
 * Meldung in beiden Wochen bleiben weg.
 * beispiele (18.10.2026, Karl: "bei Wetterlage auch Kurzerklaerung oder Links"): bis zu drei Schlagzeilen dieser Woche, die juengsten
 * aus verschiedenen Quellen, in der Form der Boeen (titel, url, quelleName, datum). Es sind Meldungen, die in "woche" mitgezaehlt sind;
 * fuer ein Thema, das der Katalog nicht kennt, und fuer eines ohne Meldung diese Woche bleibt die Liste leer.
 */
function wetterLuftdruck(array $themen, array $nachrichten, array $quellen, callable $tag): array
{
    $verlauf = [];
    $diese = [];
    foreach ($nachrichten as $m) {
        $t = $tag($m);
        if ($t < 0 || $t >= WETTER_VERLAUF_TAGE || !in_array($m['quelle'], $quellen, true)) {
            continue;
        }
        foreach (array_keys(wetterThemenVon($m)) as $id) {
            $verlauf[$id] ??= array_fill(0, WETTER_VERLAUF_TAGE, 0);
            $verlauf[$id][WETTER_VERLAUF_TAGE - 1 - $t]++;
            if ($t < 7) {
                $diese[$id][] = $m;
            }
        }
    }
    $bekannt = array_column(THEMENFELDER, 0);
    $themen = array_map(function ($t) use ($verlauf, $diese, $bekannt) {
        $beispiele = [];
        if (in_array($t['id'], $bekannt, true)) {
            $v = $verlauf[$t['id']] ?? array_fill(0, WETTER_VERLAUF_TAGE, 0);
            $t['woche'] = array_sum(array_slice($v, -7));
            $t['vorwoche'] = array_sum(array_slice($v, 0, -7));
            $t['verlauf'] = $v;
            // Zuerst Meldungen, die mehrere Woerter des Themas nennen (ein Wort allein trifft oft nebenbei, Persona-Durchlauf
            // 22.10.2026), darin die juengste, bei gleichem Zeitpunkt die bessere Quelle; je Quelle eine.
            $id = $t['id'];
            $beispiele = wetterBeispiele($diese[$id] ?? [], fn(array $m) => min(count(wetterThemaWoerter($m)[$id][1] ?? []), WETTER_THEMA_WOERTER) * 1e10
                + strtotime($m['datum']));
        }
        return [
            'thema_id' => $t['id'],
            'name' => $t['name'],
            'steep' => $t['steep'],
            'woche' => $t['woche'],
            'vorwoche' => $t['vorwoche'],
            'verlauf' => $t['verlauf'],
            'richtung' => wetterRichtung($t['woche'], $t['vorwoche']),
            'beispiele' => $beispiele,
        ];
    }, $themen);
    // Ein Thema, das in beiden Wochen nicht vorkommt, hat kein Wetter.
    return array_values(array_filter($themen, fn($t) => $t['woche'] + $t['vorwoche'] > 0));
}

/** Ob die Meldung den Begriff nennt: die Redaktion mit Schlagwort oder in Titel und Anriss, jede andere nur im Titel (ihr Anriss nennt mehr nebenbei). $stamm: Wortanfang genuegt. */
function wetterNennt(array $m, string $begriff, bool $stamm = false): bool
{
    $alsWort = fn(string $text) => preg_match('/(?<!\p{L})' . preg_quote($begriff, '/') . ($stamm ? '' : '(?!\p{L})') . '/iu', $text) === 1;
    return $m['quelle'] === WETTER_SCHLAGWORTE
        ? in_array($begriff, $m['stichworte'] ?? [], true) || $alsWort($m['titel'] . ' ' . $m['text'])
        : $alsWort($m['titel']);
}

/** Welche Themenfelder eine Meldung traegt: id => Name. */
function wetterThemenVon(array $m): array
{
    return array_map(fn($w) => $w[0], wetterThemaWoerter($m));
}

/** Welche Themenfelder eine Meldung traegt, mit den Woertern, die getroffen haben: id => [Name, [wort, ...]]. */
function wetterThemaWoerter(array $m): array
{
    static $muster = null;
    $muster ??= array_map(fn($t) => [$t[0], $t[1], themaMuster($t[3])], THEMENFELDER);
    $text = mb_strtolower($m['titel'] . ' ' . $m['text'] . ' ' . implode(' ', $m['stichworte'] ?? []));
    $aus = [];
    foreach ($muster as [$id, $name, $regex]) {
        if (preg_match_all($regex, $text, $t) > 0) {
            $aus[$id] = [$name, array_values(array_unique($t[1]))];
        }
    }
    return $aus;
}

/** Bis zu drei Meldungen aus verschiedenen Quellen, die besten zuerst. */
function wetterBeispiele(array $meldungen, ?callable $punkte = null): array
{
    usort($meldungen, fn($a, $b) => [$punkte ? $punkte($b) : 0, $b['guete'], $b['datum']] <=> [$punkte ? $punkte($a) : 0, $a['guete'], $a['datum']]);
    $aus = [];
    foreach ($meldungen as $m) {
        if (!in_array($m['quelleName'], array_column($aus, 'quelleName'), true)) {
            $aus[] = ['titel' => kurz($m['titel'], 140), 'url' => $m['url'], 'quelleName' => $m['quelleName'], 'datum' => $m['datum']];
        }
        if (count($aus) === 3) {
            break;
        }
    }
    return $aus;
}

/** Kandidaten fuer Begriffe aus den Meldungen der letzten sieben Tage: Schlagworte der tagesschau und gross geschriebene Titelwoerter. [klein => [Begriff, Meldungen]] */
function wetterKandidaten(array $meldungen, callable $tag): array
{
    $kandidaten = [];
    foreach ($meldungen as $s) {
        if ($tag($s) >= 7) {
            continue;
        }
        $begriffe = $s['quelle'] === WETTER_SCHLAGWORTE ? array_map('strval', $s['stichworte'] ?? []) : [];
        preg_match_all('/\p{Lu}\p{L}{' . (WETTER_WORT_LAENGE - 1) . ',}/u', $s['titel'], $woerter);
        foreach (array_unique([...$begriffe, ...$woerter[0]]) as $b) {
            $kandidaten[mb_strtolower($b)] = [$b, ($kandidaten[mb_strtolower($b)][1] ?? 0) + 1];
        }
    }
    return $kandidaten;
}

/** Ob ein Wort nichts benennt: zu kurz, Kulisse, Zeitangabe oder Floskel. */
function wetterKeinBegriff(string $begriff): bool
{
    return mb_strlen($begriff) < 4 || in_array(mb_strtolower($begriff), [...KULISSE, ...WETTER_ZEIT, ...WETTER_FLOSKELN], true);
}

/**
 * Begriffe, die ploetzlich in vielen Meldungen stehen. Kandidaten sind die
 * Schlagworte der tagesschau und gross geschriebene Titelwoerter der Woche. Der
 * Faktor misst die Quellen mit brauchbarer Vorgeschichte (wetterBezug) gegen
 * ihre eigenen Vorwochen. Gezaehlt wird danach in allen deutschen Quellen.
 * Begriffe, die dieselben Meldungen tragen, sind eine Boee.
 *
 * Quellen ohne Vorwochen koennen keinen Faktor liefern (heise und Golem behalten ihre Meldungen erst seit dem 17.10.2026 laenger als
 * eine Woche, die Wissenschaftsquellen sind neu). Damit eine Region trotzdem Boeen hat, kommen ihre staerksten Begriffe der Woche
 * ohne Faktor dazu (wetterRegionBoeen).
 */
function wetterBoeen(array $nachrichten, array $bezug, callable $tag, int $jetzt, array $zaehlen = []): array
{
    $rueckblick = array_values(array_filter($nachrichten, fn($s) => $tag($s) < WETTER_RUECKBLICK_TAGE));
    $gefunden = [];
    if ($bezug) {
        foreach (wetterKandidaten(array_values(array_filter($nachrichten, fn($s) => isset($bezug[$s['quelle']]))), $tag) as [$begriff, $n]) {
            if ($n < WETTER_KANDIDAT_MIN || wetterKeinBegriff($begriff)) {
                continue;
            }
            $treffer = array_values(array_filter($rueckblick, fn($m) => wetterNennt($m, $begriff)));
            $je = [];
            foreach ($treffer as $m) {
                if (isset($bezug[$m['quelle']])) {
                    $je[$m['quelle']][intdiv($tag($m), 7)] = ($je[$m['quelle']][intdiv($tag($m), 7)] ?? 0) + 1;
                }
            }
            $diese = 0;
            $erwartet = 0.0;
            foreach ($bezug as $quelle => $brauchbar) {
                $diese += $je[$quelle][0] ?? 0;
                $erwartet += array_sum(array_map(fn($w) => $je[$quelle][$w] ?? 0, $brauchbar)) / count($brauchbar);
            }
            $faktor = $diese / max(1, $erwartet);
            $woche = array_values(array_filter($treffer, fn($m) => $tag($m) < 7));
            if ($diese >= WETTER_BEZUG_MIN && $faktor >= WETTER_BOE_FAKTOR && count($woche) >= WETTER_BOE_MELDUNGEN) {
                $gefunden[] = ['begriffe' => [$begriff], 'faktor' => $faktor, 'treffer' => $treffer, 'woche' => $woche];
            }
        }
    }
    usort($gefunden, fn($a, $b) => [$b['faktor'], count($b['woche'])] <=> [$a['faktor'], count($a['woche'])]);
    // Hoechstens WETTER_BOEN_MAX je Region, die staerksten zuerst.
    $je = [];
    $boeen = array_values(array_filter(wetterZusammen($gefunden), function ($b) use (&$je) {
        $region = mehrheit(array_column($b['woche'], 'steep'));
        $je[$region] = ($je[$region] ?? 0) + 1;
        return $je[$region] <= WETTER_BOEN_MAX;
    }));
    $boeen = [...$boeen, ...wetterRegionBoeen($nachrichten, $rueckblick, $boeen, $tag)];
    $boeen = [...$boeen, ...wetterTrends($rueckblick, $zaehlen, $boeen, $tag)];
    return array_map(fn($b) => wetterBoe($b, $tag, $jetzt), $boeen);
}

/** Boeen, die dieselben Meldungen tragen oder dieselbe Schlagzeile haben, sind eine; die staerkere (zuerst genannte) fuehrt. */
function wetterZusammen(array $gefunden): array
{
    // Begriffe, die zu 60 % dieselben Meldungen betreffen wie eine schon genommene Boee, gehoeren zu ihr.
    $boeen = [];
    foreach ($gefunden as $g) {
        foreach ($boeen as $i => $b) {
            if (wetterGleichen($g, $b)) {
                $boeen[$i] = wetterVerschmelze($b, $g);
                continue 2;
            }
        }
        $boeen[] = $g;
    }
    // Dieselbe Schlagzeile ist dieselbe Boee, auch wenn ihre Begriffe nur zum Teil dieselben Meldungen tragen
    // ("Papst" und "Waffenruhe" fuehrten beide zu "Papst bittet Putin um Waffenruhe in Oleschky").
    $nachTitel = [];
    foreach ($boeen as $b) {
        $schluessel = wetterSchlagzeile($b);
        $nachTitel[$schluessel] = isset($nachTitel[$schluessel]) ? wetterVerschmelze($nachTitel[$schluessel], $b) : $b;
    }
    return array_values($nachTitel);
}

/** Ob zwei Boeen sich zu 60 % in den Meldungen der Woche decken. */
function wetterGleichen(array $a, array $b): bool
{
    $ids = array_column($a['woche'], 'id');
    return count(array_intersect($ids, array_column($b['woche'], 'id'))) >= WETTER_UEBERLAPP * min(count($ids), count($b['woche']));
}

function wetterSchlagzeile(array $b): string
{
    return mb_strtolower(trim((string) preg_replace('/\s+/u', ' ', wetterBeispiele($b['woche'], wetterTitelPunkte($b))[0]['titel'])));
}

/**
 * Wortanfaenge aus dem Themenkatalog (ein Wort ab vier Buchstaben, ohne Leerzeichen) und wie viele Meldungen der Woche sie am Wortanfang eines Titels
 * tragen: [[Wortanfang, Meldungen]]. Wie bei den Titelwoertern zaehlt bei der tagesschau auch der Anriss. Der laengste Anfang gewinnt.
 */
function wetterStaemme(array $woche): array
{
    static $staemme = null;
    $staemme ??= (function () {
        $alle = [];
        foreach (THEMENFELDER as $t) {
            foreach ($t[3] as $wort) {
                if (mb_strlen($wort) >= 4 && !str_contains($wort, ' ')) {
                    $alle[mb_strtolower($wort)] = $wort;
                }
            }
        }
        uksort($alle, fn($a, $b) => mb_strlen($b) <=> mb_strlen($a));
        return $alle;
    })();
    $muster = '/(?<!\p{L})(' . implode('|', array_map(fn($w) => preg_quote((string) $w, '/'), array_keys($staemme))) . ')/u';
    $je = [];
    foreach ($woche as $m) {
        preg_match_all($muster, mb_strtolower($m['quelle'] === WETTER_SCHLAGWORTE ? $m['titel'] . ' ' . $m['text'] : $m['titel']), $treffer);
        foreach (array_unique($treffer[1]) as $stamm) {
            $je[$stamm] = ($je[$stamm] ?? 0) + 1;
        }
    }
    return array_map(fn($stamm, $n) => [$staemme[$stamm], $n], array_keys($je), $je);
}

/** Woerter, die in den Meldungen auch klein geschrieben vorkommen: [wort => true]. Ein gross geschriebenes Titelwort davon ist kein Hauptwort und kein Name. */
function wetterKleinWoerter(array $meldungen): array
{
    $klein = [];
    foreach ($meldungen as $m) {
        foreach (preg_split('/[^\p{L}]+/u', $m['titel'] . ' ' . $m['text'], -1, PREG_SPLIT_NO_EMPTY) ?: [] as $wort) {
            if (mb_strtolower($wort) === $wort) {
                $klein[$wort] = true;
            }
        }
    }
    return $klein;
}

/**
 * Die staerksten Begriffe einer Region, wenn sie weniger als WETTER_REGION_MIN Boeen hat: ein Begriff, der diese Woche in mindestens
 * WETTER_REGION_MELDUNGEN Meldungen aus mindestens zwei Quellen steht und dessen Meldungen zur Haelfte aus den letzten Tagen kommen
 * (gleichmaessig verteilt waeren es drei von sieben) und die zu mindestens 60 % in einer Region stehen. Ein Titelwort, das in der Woche auch klein
 * geschrieben vorkommt ("neue", "warum"), ist kein Hauptwort und kein Name; eine Rubrik vor dem Doppelpunkt ("Technologie: ...") auch nicht. Die Zahl
 * der Meldungen wird nach dem Volumen der Region gestaffelt. Ohne Faktor, weil die Vorwochen fehlen.
 */
function wetterRegionBoeen(array $nachrichten, array $rueckblick, array $vorhanden, callable $tag): array
{
    $woche = array_values(array_filter($nachrichten, fn($s) => $tag($s) >= 0 && $tag($s) < 7));
    if (!$woche) {
        return [];
    }
    $volumen = array_count_values(array_column($woche, 'steep'));
    $klein = wetterKleinWoerter($woche);
    $kandidaten = array_map(fn($k) => [...$k, false], array_values(wetterKandidaten($woche, $tag)));
    foreach (wetterStaemme($woche) as [$stamm, $n]) {
        $kandidaten[] = [$stamm, $n, true];
    }
    $gefunden = [];
    foreach ($kandidaten as [$begriff, $n, $stamm]) {
        if ($n < WETTER_REGION_MELDUNGEN || wetterKeinBegriff($begriff) || (!$stamm && isset($klein[mb_strtolower($begriff)]))) {
            continue;
        }
        $diese = array_values(array_filter($woche, fn($m) => wetterNennt($m, $begriff, $stamm)));
        $region = mehrheit(array_column($diese, 'steep'));
        $noetig = max(WETTER_REGION_MELDUNGEN, (int) ceil(WETTER_REGION_WURZEL * sqrt($volumen[$region] ?? 0)));
        $rubrik = '/^\s*' . preg_quote($begriff, '/') . '\s*(:|-|–)/iu';
        if (count($diese) < $noetig || count(array_unique(array_column($diese, 'quelle'))) < WETTER_REGION_QUELLEN
            || count(array_filter($diese, fn($m) => $m['steep'] === $region)) < WETTER_REGION_KONZENTRATION * count($diese)
            || count(array_filter($diese, fn($m) => preg_match($rubrik, $m['titel']) === 1)) >= 0.5 * count($diese)) {
            continue;
        }
        $jung = count(array_filter($diese, fn($m) => $tag($m) < WETTER_REGION_JUNG_TAGE));
        if ($jung >= WETTER_REGION_JUNG_ANTEIL * count($diese)) {
            // Erst jetzt die ganze Rueckschau: Verlauf, Beginn und Halbwertszeit der Boee.
            $treffer = array_values(array_filter($rueckblick, fn($m) => wetterNennt($m, $begriff, $stamm)));
            $gefunden[] = ['begriffe' => [$begriff], 'faktor' => null, 'treffer' => $treffer, 'woche' => $diese, 'jung' => $jung, 'stamm' => $stamm];
        }
    }
    usort($gefunden, fn($a, $b) => [$b['jung'], count($b['woche'])] <=> [$a['jung'], count($a['woche'])]);
    $je = array_count_values(array_map(fn($b) => mehrheit(array_column($b['woche'], 'steep')), $vorhanden));
    $schluessel = array_map('wetterSchlagzeile', $vorhanden);
    $neu = [];
    foreach (wetterZusammen($gefunden) as $g) {
        $region = mehrheit(array_column($g['woche'], 'steep'));
        if (($je[$region] ?? 0) >= WETTER_REGION_MIN || in_array(wetterSchlagzeile($g), $schluessel, true)
            || array_filter($vorhanden, fn($b) => wetterGleichen($g, $b))) {
            continue;
        }
        $neu[] = $g;
        $je[$region] = ($je[$region] ?? 0) + 1;
    }
    return $neu;
}

/**
 * Trends fuer Regionen mit weniger als WETTER_REGION_MIN Boeen (Konstanten WETTER_TREND_*): Begriffe, die in den Quellen mit brauchbarer Vorwoche
 * ($zaehlen) ueber zwei Wochen stetig zunehmen. Ohne Faktor; der Anstieg ist Woche gegen die eine Vorwoche. Verlauf und Meldungen stammen aus
 * denselben Quellen, damit die Kurve nicht von Quellen mit kurzer Geschichte hochgezogen wird.
 */
function wetterTrends(array $rueckblick, array $zaehlen, array $vorhanden, callable $tag): array
{
    $pool = array_values(array_filter($rueckblick, fn($s) => $tag($s) >= 0 && in_array($s['quelle'], $zaehlen, true)));
    $woche = array_values(array_filter($pool, fn($s) => $tag($s) < 7));
    if (!$woche) {
        return [];
    }
    $je = array_count_values(array_map(fn($b) => mehrheit(array_column($b['woche'], 'steep')), $vorhanden));
    $platz = [];
    foreach (array_keys(WETTER_REGIONEN) as $region) {
        $platz[$region] = min(WETTER_TREND_MAX, WETTER_REGION_MIN - ($je[$region] ?? 0));
    }
    if (max($platz) <= 0) {
        return [];
    }
    $volumen = array_count_values(array_column($woche, 'steep'));
    $quellenJe = [];
    foreach ($woche as $m) {
        $quellenJe[$m['steep']][$m['quelle']] = true;
    }
    $klein = wetterKleinWoerter($woche);
    $kandidaten = array_map(fn($k) => [...$k, false], array_values(wetterKandidaten($woche, $tag)));
    foreach (wetterStaemme($woche) as [$stamm, $n]) {
        $kandidaten[] = [$stamm, $n, true];
    }
    $gefunden = [];
    foreach ($kandidaten as [$begriff, $n, $stamm]) {
        if ($n < WETTER_REGION_MELDUNGEN || wetterKeinBegriff($begriff) || (!$stamm && isset($klein[mb_strtolower($begriff)]))) {
            continue;
        }
        $diese = array_values(array_filter($woche, fn($m) => wetterNennt($m, $begriff, $stamm)));
        $region = mehrheit(array_column($diese, 'steep'));
        if (($platz[$region] ?? 0) <= 0) {
            continue;
        }
        $vor = count(array_filter($pool, fn($m) => $tag($m) >= 7 && $tag($m) < 14 && wetterNennt($m, $begriff, $stamm)));
        $noetig = max(WETTER_REGION_MELDUNGEN, (int) ceil(WETTER_REGION_WURZEL * sqrt($volumen[$region] ?? 0)));
        $rubrik = '/^\s*' . preg_quote($begriff, '/') . '\s*(:|-|–)/iu';
        $proTag = array_count_values(array_map($tag, $diese));
        if (count($diese) < $noetig || $vor < WETTER_TREND_VORWOCHE_MIN || wetterRichtung(count($diese), $vor) !== 'steigt'
            || count($proTag) < WETTER_TREND_TAGE || max($proTag) > WETTER_TREND_SPITZE * count($diese)
            || count(array_unique(array_column($diese, 'quelle'))) < min(WETTER_REGION_QUELLEN, count($quellenJe[$region] ?? []))
            || count(array_filter($diese, fn($m) => $m['steep'] === $region)) < WETTER_REGION_KONZENTRATION * count($diese)
            || count(array_filter($diese, fn($m) => preg_match($rubrik, $m['titel']) === 1)) >= 0.5 * count($diese)) {
            continue;
        }
        $treffer = array_values(array_filter($pool, fn($m) => wetterNennt($m, $begriff, $stamm)));
        $gefunden[] = ['begriffe' => [$begriff], 'faktor' => null, 'treffer' => $treffer, 'woche' => $diese, 'stamm' => $stamm,
            'trend' => true, 'anstieg' => round(count($diese) / $vor, 1), 'zuwachs' => count($diese) - $vor];
    }
    usort($gefunden, fn($a, $b) => [$b['zuwachs'], count($b['woche'])] <=> [$a['zuwachs'], count($a['woche'])]);
    $schluessel = array_map('wetterSchlagzeile', $vorhanden);
    $neu = [];
    foreach (wetterZusammen($gefunden) as $g) {
        $region = mehrheit(array_column($g['woche'], 'steep'));
        if (($platz[$region] ?? 0) <= 0 || in_array(wetterSchlagzeile($g), $schluessel, true)
            || array_filter([...$vorhanden, ...$neu], fn($b) => wetterGleichen($g, $b))) {
            continue;
        }
        $neu[] = $g;
        $platz[$region]--;
    }
    return $neu;
}

/** Zwei Boeen zu einer: die staerkere (zuerst genannte) behaelt ihren Faktor, Begriffe und Meldungen kommen zusammen. */
function wetterVerschmelze(array $a, array $b): array
{
    $a['begriffe'] = array_values(array_unique([...$a['begriffe'], ...$b['begriffe']]));
    $a['woche'] = array_values(array_column([...$a['woche'], ...$b['woche']], null, 'id'));
    $a['treffer'] = array_values(array_column([...$a['treffer'], ...$b['treffer']], null, 'id'));
    return $a;
}

/** Die Schlagzeile einer Boee ist die, die am meisten ihrer Begriffe im Titel nennt, am liebsten die der Redaktion. */
/**
 * Rangfolge fuer den Titel einer Boee: zuerst ihre Begriffe im Titel, dann Woerter ihres Themas $heim (bis WETTER_THEMA_WOERTER), dann die Schlagworte.
 * Ohne Thema stand "Erde steuert auf 2,8 Grad Erwaermung zu" ueber der Boee "Steuer" unter Haushalt und
 * "Transporter ... fuer Familien" ueber der Boee "Familie" (Persona-Durchlauf 22.10.2026).
 */
function wetterTitelPunkte(array $b, ?string $heim = null): callable
{
    $ende = empty($b['stamm']) ? '(?!\p{L})' : '';
    return fn(array $m) => 100 * count(array_filter($b['begriffe'], fn($x) => preg_match('/(?<!\p{L})' . preg_quote($x, '/') . $ende . '/iu', $m['titel']) === 1))
        + ($heim === null ? 0 : 10 * min(count(wetterThemaWoerter($m)[$heim][1] ?? []), WETTER_THEMA_WOERTER))
        + ($m['quelle'] === WETTER_SCHLAGWORTE ? 5 : 0);
}

function wetterBoe(array $b, callable $tag, int $jetzt): array
{
    $trend = !empty($b['trend']);
    // Meldungen je Tag, 0 = die letzten 24 Stunden.
    $je = array_fill(0, WETTER_RUECKBLICK_TAGE, 0);
    foreach ($b['treffer'] as $m) {
        if (($t = $tag($m)) >= 0 && $t < WETTER_RUECKBLICK_TAGE) {
            $je[$t]++;
        }
    }
    $verlauf = array_reverse(array_slice($je, 0, WETTER_VERLAUF_TAGE));
    $gipfel = max($verlauf);
    $gipfelTag = array_search($gipfel, $verlauf, true);

    // Halbwertszeit: Tage vom Gipfel bis zum ersten Tag mit der Haelfte; null, solange es nicht so weit ist.
    $halb = null;
    for ($i = $gipfelTag + 1; $i < WETTER_VERLAUF_TAGE; $i++) {
        if ($verlauf[$i] <= WETTER_HALB * $gipfel) {
            $halb = $i - $gipfelTag;
            break;
        }
    }
    // Beginn: vom Gipfel zurueck, solange Tage mindestens einen Viertel des Gipfels haben (eine Luecke von einem Tag gilt nicht als Ende).
    $schwelle = max(1, WETTER_TAGESANTEIL * $gipfel);
    $beginn = WETTER_VERLAUF_TAGE - 1 - $gipfelTag;
    for ($t = $beginn + 1; $t < WETTER_RUECKBLICK_TAGE; $t++) {
        if ($je[$t] >= $schwelle) {
            $beginn = $t;
        } elseif ($t - $beginn > 1) {
            break;
        }
    }

    $themen = [];
    foreach ($b['woche'] as $m) {
        foreach (array_keys(wetterThemenVon($m)) as $id) {
            $themen[$id] = ($themen[$id] ?? 0) + 1;
        }
    }
    arsort($themen);
    $heim = array_key_first($themen);
    $heim = $heim !== null && $themen[$heim] >= 0.5 * count($b['woche']) ? $heim : null;

    $beste = wetterBeispiele($b['woche'], wetterTitelPunkte($b, $heim));
    $titel = $beste[0]['titel'];

    return [
        'id' => preg_replace('/\W+/u', '-', mb_strtolower($b['begriffe'][0])),
        'titel' => $titel,
        'steep' => mehrheit(array_column($b['woche'], 'steep')),
        'thema_id' => $heim,
        'meldungen_woche' => count($b['woche']),
        'faktor' => $b['faktor'] === null ? null : round($b['faktor'], 1),
        // Woher die Staerke kommt: "vorwochen" (Faktor gegen zwei bis vier Vorwochen), "woche" (ohne Vorwoche: nur die Verteilung innerhalb der Woche,
        // jung_anteil), "vorwoche" (Trend: Woche gegen die eine Vorwoche, anstieg). Ein Faktor, der keiner ist, steht nicht da.
        'basis' => $trend ? 'vorwoche' : ($b['faktor'] === null ? 'woche' : 'vorwochen'),
        'anstieg' => $trend ? $b['anstieg'] : null,
        'jung_anteil' => round(count(array_filter($b['woche'], fn($m) => $tag($m) < WETTER_REGION_JUNG_TAGE)) / max(1, count($b['woche'])), 2),
        'verlauf_tage' => $verlauf,
        'beginn' => gmdate('Y-m-d', $jetzt - $beginn * TAG),
        'halbwertszeit_tage' => $trend ? null : $halb,
        'art' => $trend || $beginn + 1 > WETTER_VERLAUF_TAGE ? 'trend' : 'boee',
        'beispiele' => $beste,
    ];
}

/**
 * Saison: je Region die Groessen, die sich ueber vier bis zwoelf Wochen am staerksten bewegen (Konstanten WETTER_SAISON_*).
 * Drei Arten: "reihe" (Messreihen des Wissensstands, meist monatlich), "interesse" (Wikipedia-Aufrufe, Wochensummen der letzten 16 Wochen)
 * und "meldungen" (Themenfelder in den Meldungen, vier Wochen, nur aus Quellen mit drei brauchbaren Vorwochen). Der Verlauf sind die Werte der Reihe
 * selbst (takt: woche, monat oder quartal), nie zu Wochen umgerechnet. Trends der Art "reihe" sind dieselben Messreihen und zaehlen nicht doppelt,
 * die "forschung" (Jahreswerte) gehoert zum Klima.
 */
function wetterSaison(array $reihen, array $trends, array $nachrichten, array $quellen, callable $tag, int $jetzt): array
{
    $kandidaten = [];
    foreach ($reihen as $r) {
        $punkte = array_values(array_filter($r['punkte'] ?? [], fn($p) => isset($p['t'], $p['wert']) && is_numeric($p['wert']) && strtotime(strlen((string) $p['t']) === 7 ? $p['t'] . '-01' : (string) $p['t']) !== false));
        $zeiten = array_map(fn($p) => strtotime(strlen((string) $p['t']) === 7 ? $p['t'] . '-01' : (string) $p['t']), $punkte);
        $abstaende = [];
        for ($i = max(1, count($zeiten) - 8); $i < count($zeiten); $i++) {
            $abstaende[] = ($zeiten[$i] - $zeiten[$i - 1]) / TAG;
        }
        sort($abstaende);
        $mitte = $abstaende ? $abstaende[intdiv(count($abstaende), 2)] : null;
        $takt = $mitte === null ? null : ($mitte <= 10 ? 'woche' : ($mitte <= 45 ? 'monat' : ($mitte <= 120 ? 'quartal' : null)));
        if ($takt === null || ($jetzt - end($zeiten)) / TAG > WETTER_SAISON_ALTER_TAGE + ($takt === 'quartal' ? 90 : 0)) {
            continue;
        }
        $werte = array_map(fn($p) => (float) $p['wert'], $punkte);
        $k = wetterSaisonBewegung($werte, $zeiten, $takt === 'woche' ? 2 : 1);
        if ($k === null) {
            continue;
        }
        $zeigen = WETTER_SAISON_PUNKTE[$takt];
        $kandidaten[] = $k + [
            'steep' => $r['steep'], 'id' => $r['id'], 'titel' => $r['titel'], 'einheit' => $r['einheit'] ?? null, 'typ' => 'reihe', 'takt' => $takt,
            'verlauf' => array_slice($werte, -$zeigen), 'von' => (string) $punkte[max(0, count($punkte) - $zeigen)]['t'], 'bis' => (string) end($punkte)['t'],
            'quelleName' => $r['quelleName'] ?? null, 'url' => $r['url'] ?? null, 'gruppe' => $r['quelle'] ?? $r['id'],
        ];
    }
    foreach ($trends as $t) {
        if (($t['art'] ?? '') !== 'aufmerksamkeit' || count($t['verlauf'] ?? []) < 8) {
            continue;
        }
        $werte = array_map('floatval', array_values($t['verlauf']));
        $n = count($werte);
        $zeiten = array_map(fn($i) => $jetzt - TAG - ($n - 1 - $i) * 7 * TAG, range(0, $n - 1));
        $k = wetterSaisonBewegung($werte, $zeiten, 2);
        if ($k === null) {
            continue;
        }
        $zeigen = WETTER_SAISON_PUNKTE['woche'];
        $artikel = (string) preg_replace('/^aufmerksamkeit-/', '', (string) $t['id']);
        $kandidaten[] = $k + [
            'steep' => $t['steep'], 'id' => $t['id'], 'titel' => $t['titel'], 'einheit' => 'Aufrufe je Woche', 'typ' => 'interesse', 'takt' => 'woche',
            'verlauf' => array_slice($werte, -$zeigen), 'von' => gmdate('Y-m-d', $zeiten[max(0, $n - $zeigen)]), 'bis' => gmdate('Y-m-d', end($zeiten)),
            'quelleName' => 'Wikipedia (de), Seitenaufrufe', 'url' => 'https://de.wikipedia.org/wiki/' . rawurlencode($artikel), 'gruppe' => 'wikipedia',
        ];
    }
    // Themen in den Meldungen: vier Wochen, Wochenzaehlung in den Quellen der Wetterlage ($quellen, leer, solange einer davon eine Woche fehlt).
    $je = [];
    $namen = [];
    foreach ($nachrichten as $m) {
        $t = $tag($m);
        if ($t < 0 || $t >= 28 || !in_array($m['quelle'], $quellen, true)) {
            continue;
        }
        foreach (wetterThemenVon($m) as $id => $name) {
            $je[$id] ??= [0, 0, 0, 0];
            $je[$id][3 - intdiv($t, 7)]++;
            $namen[$id] = $name;
        }
    }
    $steepJe = array_column(array_map(fn($t) => [$t[0], $t[2]], THEMENFELDER), 1, 0);
    foreach ($je as $id => $wochen) {
        if (array_sum($wochen) < WETTER_SAISON_MELDUNGEN || max($wochen) > WETTER_SAISON_SPITZE * array_sum($wochen) || !isset($steepJe[$id])) {
            continue;
        }
        $k = wetterSaisonBewegung(array_map('floatval', $wochen), [0, 7 * TAG, 14 * TAG, 21 * TAG], 2);
        if ($k === null) {
            continue;
        }
        // Wie beim Luftdruck: ein Unterschied unter drei Meldungen je Woche oder einem Viertel ist Zufall.
        if (abs($k['bis_wert'] - $k['von_wert']) < max(WETTER_GLEICH_MIN, WETTER_GLEICH_ANTEIL * $k['von_wert'])) {
            $k['richtung'] = 'stabil';
        }
        // Prozent von zwei Meldungen auf sechs ist kein Mass.
        if ($k['von_wert'] < WETTER_GLEICH_MIN) {
            $k['aenderung'] = null;
        }
        $kandidaten[] = $k + [
            'steep' => $steepJe[$id], 'id' => "themen-$id", 'titel' => $namen[$id], 'einheit' => 'Meldungen', 'typ' => 'meldungen', 'takt' => 'woche',
            'verlauf' => $wochen, 'von' => gmdate('Y-m-d', $jetzt - 27 * TAG), 'bis' => gmdate('Y-m-d', $jetzt),
            'quelleName' => 'Nachrichtenquellen im Radar', 'url' => null, 'gruppe' => 'meldungen',
        ];
    }
    // Je Region die staerksten, aus einer Quelle hoechstens zwei: erst die staerksten Messreihen, dann alles Bewegte, zuletzt (unter dem Mindestwert) die naechstbesten als "stabil".
    usort($kandidaten, fn($a, $b) => [$b['bewegung'], $a['id']] <=> [$a['bewegung'], $b['id']]);
    $aus = [];
    $paesse = [
        [fn($c) => $c['typ'] === 'reihe' && $c['richtung'] !== 'stabil', WETTER_SAISON_REIHEN],
        [fn($c) => $c['richtung'] !== 'stabil', WETTER_SAISON_JE_REGION],
        [fn($c) => true, WETTER_SAISON_MINDEST],
    ];
    foreach (array_keys(WETTER_REGIONEN) as $region) {
        $genommen = [];
        $gruppen = [];
        foreach ($paesse as [$passt, $bis]) {
            foreach ($kandidaten as $c) {
                if (count($genommen) >= $bis) {
                    break;
                }
                if ($c['steep'] !== $region || !$passt($c) || in_array($c['id'], array_column($genommen, 'id'), true) || ($gruppen[$c['gruppe']] ?? 0) >= WETTER_SAISON_JE_QUELLE) {
                    continue;
                }
                $genommen[] = $c;
                $gruppen[$c['gruppe']] = ($gruppen[$c['gruppe']] ?? 0) + 1;
            }
        }
        usort($genommen, fn($a, $b) => [$b['bewegung'], $a['id']] <=> [$a['bewegung'], $b['id']]);
        foreach ($genommen as $c) {
            $aus[] = ['steep' => $c['steep'], 'id' => $c['id'], 'titel' => $c['titel'], 'typ' => $c['typ'], 'einheit' => $c['einheit'], 'takt' => $c['takt'],
                'richtung' => $c['richtung'], 'bewegung' => round($c['bewegung'], 2), 'aenderung' => $c['aenderung'], 'verlauf' => $c['verlauf'],
                'von' => $c['von'], 'bis' => $c['bis'], 'quelleName' => $c['quelleName'], 'url' => $c['url']];
        }
    }
    return $aus;
}

/**
 * Wie weit sich eine Reihe im Fenster bewegt hat: [bewegung (Anteil des Spielraums), richtung, aenderung (Prozent oder null), von_wert, bis_wert],
 * oder null, wenn zu wenig da ist. $glatt Punkte an jedem Ende werden gemittelt (Wochenwerte schwanken).
 */
function wetterSaisonBewegung(array $werte, array $zeiten, int $glatt): ?array
{
    $n = count($werte);
    if ($n < 4) {
        return null;
    }
    $ende = $zeiten[$n - 1];
    $i0 = 0;
    while ($i0 < $n - 1 && $zeiten[$i0] < $ende - WETTER_SAISON_WOCHEN * 7 * TAG) {
        $i0++;
    }
    if ($ende - $zeiten[$i0] < WETTER_SAISON_MIN_TAGE * TAG) {
        return null;
    }
    $k = $i0 + $glatt <= $n - $glatt ? $glatt : 1;
    $von = array_sum(array_slice($werte, $i0, $k)) / $k;
    $bis = array_sum(array_slice($werte, -$k)) / $k;
    $spielraum = array_slice($werte, -WETTER_SAISON_SPIELRAUM);
    $weite = max($spielraum) - min($spielraum);
    if ($weite <= 0) {
        return null;
    }
    $bewegung = abs($bis - $von) / $weite;
    return [
        'bewegung' => $bewegung,
        'richtung' => $bewegung < WETTER_SAISON_MIN ? 'stabil' : ($bis > $von ? 'steigt' : 'faellt'),
        'aenderung' => abs($von) < 1e-9 ? null : round(($bis - $von) / abs($von) * 100, 1),
        'von_wert' => $von,
        'bis_wert' => $bis,
    ];
}

/**
 * Themenfelder, die dieselben Meldungen der Woche tragen. Was eine Front ist, bestimmen die Meldungen der Woche aus allen Quellen (wie bisher). Dazu
 * (18.10.2026, wie bei einer Boee): titel (die Schlagzeile, die beide Themen am staerksten traegt, die Redaktion bevorzugt), begriffe (die haeufigsten
 * Hauptwoerter der gemeinsamen Meldungen), verlauf_tage (14 Tage, aelteste zuerst), gemeinsam_vorwoche und richtung (steigt, faellt, gleich wie beim
 * Luftdruck), beginn (erster Tag mit gemeinsamen Meldungen im Fenster) und art (neu: keine gemeinsame Meldung in der Woche davor, sonst anhaltend).
 * Verlauf, Vorwoche und Richtung zaehlen nur die Quellen mit brauchbarer Vorwoche ($zaehlen, wie Regionen und Luftdruck): sonst waechst jede Front mit
 * jeder neuen Quelle. Darum gibt es gemeinsam_woche_gezaehlt: die Woche in denselben Quellen, die Summe der letzten sieben Tage des Verlaufs, vergleichbar
 * mit gemeinsam_vorwoche; gemeinsam_woche (alle Quellen) kann hoeher liegen. Beginn und Art fragen nur, ob es Meldungen gab, und nehmen alle Quellen.
 */
function wetterFronten(array $nachrichten, callable $tag, array $zaehlen = [], int $jetzt = 0): array
{
    $woche = array_values(array_filter($nachrichten, fn($s) => $tag($s) < 7));
    $je = [];
    $paare = [];
    $namen = [];
    foreach ($woche as $m) {
        $mit = wetterThemenVon($m);
        $namen += $mit;
        foreach ($mit as $id => $name) {
            $je[$id] = ($je[$id] ?? 0) + 1;
        }
        $ids = array_keys($mit);
        sort($ids);
        foreach ($ids as $i => $a) {
            foreach (array_slice($ids, $i + 1) as $b) {
                $paare["$a|$b"][] = $m;
            }
        }
    }
    $fronten = [];
    foreach ($paare as $schluessel => $ms) {
        [$a, $b] = explode('|', $schluessel);
        $zufall = $je[$a] * $je[$b] / count($woche);
        if (count($ms) >= WETTER_FRONT_MIN && count($ms) >= WETTER_FRONT_UEBER_ZUFALL * $zufall) {
            $fronten[] = ['themen' => [$a, $b], 'namen' => [$namen[$a], $namen[$b]], 'gemeinsam_woche' => count($ms), 'ms' => $ms];
        }
    }
    usort($fronten, fn($x, $y) => $y['gemeinsam_woche'] <=> $x['gemeinsam_woche']);
    $fronten = array_slice($fronten, 0, WETTER_FRONTEN_MAX);
    if (!$fronten) {
        return [];
    }
    // Die Woche davor: nur fuer die Fronten, die es gibt.
    $davor = array_values(array_filter($nachrichten, fn($s) => $tag($s) >= 7 && $tag($s) < WETTER_VERLAUF_TAGE));
    $davorMit = array_map('wetterThemenVon', $davor);
    return array_map(function ($f) use ($tag, $zaehlen, $jetzt, $davor, $davorMit) {
        [$a, $b] = $f['themen'];
        $frueher = [];
        foreach ($davor as $i => $m) {
            if (isset($davorMit[$i][$a], $davorMit[$i][$b])) {
                $frueher[] = $m;
            }
        }
        $verlauf = array_fill(0, WETTER_VERLAUF_TAGE, 0);
        foreach ([...$f['ms'], ...$frueher] as $m) {
            if (($t = $tag($m)) >= 0 && $t < WETTER_VERLAUF_TAGE && in_array($m['quelle'], $zaehlen, true)) {
                $verlauf[WETTER_VERLAUF_TAGE - 1 - $t]++;
            }
        }
        $vorwoche = array_sum(array_slice($verlauf, 0, 7));
        $gezaehlt = array_sum(array_slice($verlauf, 7));
        $aelteste = max(array_map($tag, [...$f['ms'], ...$frueher]));
        // Titel und Beispiele: die Schlagzeile, in der beide Themen stehen, vorn; bei der Redaktion zaehlt auch der Anriss nicht, nur der Titel.
        $punkte = fn(array $m) => 10 * count(array_intersect(array_keys(wetterThemenVon(['titel' => $m['titel'], 'text' => '', 'stichworte' => []])), [$a, $b]))
            + ($m['quelle'] === WETTER_SCHLAGWORTE ? 5 : 0);
        $klein = wetterKleinWoerter($f['ms']);
        $begriffe = array_filter(
            wetterKandidaten($f['ms'], $tag),
            fn($k) => $k[1] >= WETTER_FRONT_BEGRIFF_MIN && !wetterKeinBegriff($k[0]) && !isset($klein[mb_strtolower($k[0])]),
        );
        uasort($begriffe, fn($x, $y) => [$y[1], mb_strtolower($x[0])] <=> [$x[1], mb_strtolower($y[0])]);
        // Eine Front ist eine Geschichte, nicht nur ein Themenpaar: Titel und Beispiele teilen sich die Begriffe der Front.
        // Vorher standen unter "Moegliche AfD-Regierung ..." zwei Zuckersteuer-Meldungen, verbunden nur ueber "Koalition"
        // (Karl, 18.10.2026). Es fuehrt die Meldung mit den meisten Front-Begriffen in Titel und Anriss; ein Beispiel braucht
        // zwei Begriffe mit ihr gemeinsam (einen, wenn sie selbst nur einen traegt; ohne Begriffe wie bisher).
        $top = array_slice(array_values(array_map(fn($k) => mb_strtolower($k[0]), $begriffe)), 0, WETTER_FRONT_BEGRIFFE_MAX);
        $treffer = fn(array $m) => array_values(array_filter($top, fn($w) => mb_stripos($m['titel'] . ' ' . ($m['text'] ?? ''), $w) !== false));
        $sortiert = $f['ms'];
        usort($sortiert, fn($x, $y) => [20 * count($treffer($y)) + $punkte($y), $y['guete'], $y['datum']] <=> [20 * count($treffer($x)) + $punkte($x), $x['guete'], $x['datum']]);
        $kern = $sortiert ? $treffer($sortiert[0]) : [];
        $mind = min(2, count($kern));
        $passend = $mind ? array_values(array_filter($f['ms'], fn($m) => count(array_intersect($treffer($m), $kern)) >= $mind)) : $f['ms'];
        $beispiele = wetterBeispiele($passend, fn(array $m) => 10 * count(array_intersect($treffer($m), $kern)) + $punkte($m));
        return [
            'themen' => $f['themen'],
            'namen' => $f['namen'],
            'gemeinsam_woche' => $f['gemeinsam_woche'],
            'beispiele' => $beispiele,
            'titel' => $beispiele[0]['titel'] ?? '',
            'begriffe' => array_slice(array_values(array_map(fn($k) => $k[0], $begriffe)), 0, WETTER_FRONT_BEGRIFFE_MAX),
            'verlauf_tage' => $verlauf,
            'gemeinsam_woche_gezaehlt' => $gezaehlt,
            'gemeinsam_vorwoche' => $vorwoche,
            'richtung' => wetterRichtung($gezaehlt, $vorwoche),
            'beginn' => gmdate('Y-m-d', $jetzt - $aelteste * TAG),
            'art' => $frueher ? 'anhaltend' : 'neu',
        ];
    }, $fronten);
}

// ---- WETTER-ENDE ----

/**
 * radar/wissensstand-kern.json: der Wissensstand ohne die Meldungen (signale), 0,1 statt 7 MB (24.10.2026). Der Horizont laedt nur ihn,
 * am Handy 1,4 MB weniger ueber die Leitung. Der ganze Wissensstand bleibt, wie er ist: der Radar, Schritt 1, das Weltmodell und der
 * naechste Lauf ($alt) lesen ihn. Fehlt der Kern (Server vor diesem Stand), nimmt die App den ganzen.
 */
function schreibeKern(array $stand, string $datei): void
{
    unset($stand['signale']);
    file_put_contents("$datei.neu", json_encode($stand, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
    rename("$datei.neu", $datei);
}

/** radar/wetter.json neben den Wissensstand schreiben; faellt es aus, bleibt der Radar, wie er ist. */
function schreibeWetter(array $signale, array $themen, int $jetzt, string $datei, array $reihen = [], array $trends = []): void
{
    try {
        $wetter = wetter($signale, $themen, $jetzt, $reihen, $trends);
        $zwischen = $datei . '.neu';
        file_put_contents($zwischen, json_encode($wetter, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
        rename($zwischen, $datei);
        printf("  Wetter: %d Böen, %d Fronten, %d Themen im Luftdruck, %d Größen in der Saison\n", count($wetter['boeen']), count($wetter['fronten']), count($wetter['luftdruck']), count($wetter['saison']));
    } catch (Throwable $e) {
        echo '  ✗ Wetter nicht gerechnet: ' . $e->getMessage() . "\n";
    }
}

// =============================================================================
// STEEP-Zuordnung und Woerter
// =============================================================================

/**
 * Welcher STEEP-Ebene gehoert ein Fund an? Nach Wortanfaengen gezaehlt - das
 * Deutsche setzt zusammen ("Klimaschutzgesetz"), also zaehlt "klima" auch dort.
 * Englische Wurzeln fuer die Forschung. Kurze Kuerzel (KI, EU) nur als ganzes
 * Wort. Bei Gleichstand entscheidet, was die Quelle selbst sagt.
 */
function steepVon(string $text, string $vorgabe): string
{
    static $wurzeln = [
        'technologie' => ['ki', 'künstlich', 'digital', 'software', 'chip', 'halbleiter', 'cyber', 'hacker', 'daten', 'internet',
            'roboter', 'quanten', 'raumfahrt', 'satellit', 'technolog', 'plattform', 'algorithm', 'chatgpt', 'openai', 'sprachmodell',
            'automatisier', 'rechenzentr', 'app', 'smartphone', 'batterie',
            'ai', 'llm', 'artificial', 'machine', 'neural', 'robot', 'quantum', 'comput', 'model', 'agent', 'reasoning', 'benchmark'],
        'umwelt' => ['klima', 'co2', 'emission', 'hitze', 'dürre', 'flut', 'hochwasser', 'erneuerbar', 'windkraft', 'windenergie',
            'solar', 'photovolta', 'artensterben', 'artenvielfalt', 'umwelt', 'unwetter', 'waldbrand', 'wärmepumpe', 'wetter', 'meer',
            'gletscher', 'natur', 'plastik', 'kohle', 'energiewende', 'wasserstoff', 'biodiversität',
            'climate', 'carbon', 'renewable', 'environment', 'biodivers', 'drought', 'flood', 'pollution', 'sustainab', 'energy'],
        'wirtschaft' => ['wirtschaft', 'inflation', 'preis', 'konjunktur', 'unternehm', 'insolvenz', 'arbeitsmarkt', 'arbeitslos',
            'export', 'zoll', 'zölle', 'börse', 'dax', 'zins', 'ezb', 'industrie', 'stellenabbau', 'handel', 'bank', 'umsatz', 'gewinn',
            'konzern', 'investition', 'fachkräft', 'lohn', 'löhne', 'steuer', 'mittelstand', 'autobau',
            'econom', 'market', 'labor', 'labour', 'employment', 'firms', 'price', 'trade', 'financ', 'productiv', 'wage', 'job'],
        'politik' => ['regierung', 'bundestag', 'partei', 'wahl', 'minister', 'gesetz', 'koalition', 'afd', 'spd', 'cdu', 'csu',
            'grüne', 'fdp', 'bsw', 'linke', 'kanzler', 'nato', 'krieg', 'militär', 'bundeswehr', 'diplomat', 'sanktion', 'präsident',
            'parlament', 'opposition', 'verfassung', 'gericht', 'ukraine', 'russland', 'israel', 'gaza',
            'policy', 'polic', 'regulat', 'government', 'election', 'democra', 'law', 'legal', 'governance', 'war', 'military', 'geopolit'],
        'gesellschaft' => ['gesellschaft', 'bildung', 'schule', 'kita', 'gesundheit', 'pflege', 'migration', 'flüchtling', 'familie',
            'rente', 'armut', 'wohn', 'miete', 'kultur', 'religion', 'jugend', 'demograf', 'protest', 'einsamkeit', 'studie', 'umfrage',
            'kinder', 'frauen', 'gleichberechtig', 'integration', 'ehrenamt', 'krankenhaus',
            'social', 'societ', 'education', 'health', 'inequal', 'gender', 'youth', 'wellbeing', 'communit', 'misinformation', 'students'],
        // Zuletzt: bei Gleichstand gewinnt eine andere Ebene. Die Fachpresse der Wissenschaft traegt den Bereich selbst (rss, $fest).
        'wissenschaft' => ['forsch', 'wissenschaft', 'astronom', 'teleskop', 'exoplanet', 'genom', 'crispr', 'impfstoff', 'krebs', 'physik', 'teilchen',
            'paläo', 'dinosaur', 'neandertal', 'archäolog', 'mikrobiom', 'protein', 'molekül', 'neurowissen', 'gehirn', 'stammzell', 'galaxie',
            'physics', 'biolog', 'astro', 'neuro', 'molecul', 'cosmolog', 'galax', 'species'],
    ];
    $worte = preg_split('/[^\p{L}\p{N}]+/u', mb_strtolower($text), -1, PREG_SPLIT_NO_EMPTY) ?: [];
    $bestes = $vorgabe;
    $hoechst = 0;
    foreach ($wurzeln as $ebene => $liste) {
        $n = 0;
        foreach ($worte as $w) {
            foreach ($liste as $r) {
                $treffer = mb_strlen($r) <= 3 ? $w === $r : (str_starts_with($w, $r) || (mb_strlen($r) >= 5 && str_contains($w, $r)));
                if ($treffer) {
                    $n++;
                    break;
                }
            }
        }
        // Gleichstand: die Vorgabe der Quelle gewinnt.
        if ($n > $hoechst || ($n === $hoechst && $n > 0 && $ebene === $vorgabe)) {
            $bestes = $ebene;
            $hoechst = $n;
        }
    }
    return $bestes;
}

/** Woerter wie src/lib/radar/text.ts: klein, ohne Fuellwoerter, grob gekuerzt. */
function woerter(string $text): array
{
    static $fuell = null;
    $fuell ??= array_flip(explode(' ', 'der die das den dem des ein eine einen einem einer eines und oder aber doch sondern denn als wie wenn weil '
        . 'dass daß ob zu zum zur im in ins am an auf aus bei mit nach von vom vor seit bis für fuer über ueber unter '
        . 'durch gegen ohne um zwischen hinter neben wegen trotz während waehrend ist sind war waren wird werden wurde '
        . 'wurden hat haben hatte hatten sein seine ihr ihre ihren ihrem es er sie wir ihr man sich nicht nur auch noch '
        . 'schon sehr mehr weniger viel viele vielen wieder immer jetzt heute gestern morgen hier dort so da dann nun '
        . 'kann können koennen soll sollen muss müssen muessen will wollen darf dürfen duerfen mal etwa rund fast '
        . 'neue neuen neuer neues neu erste ersten zwei drei vier fünf fuenf prozent jahr jahre jahren jahres '
        . 'dieser diese dieses diesen diesem jeder jede jedes alle allen alles andere anderen anderer kein keine '
        . 'mehrere einige unsere unser euch ihnen ihm ihn sei seien wäre waere würde wuerde würden wuerden '
        . 'sagt sagte sagen laut heißt heisst gibt geben gab geht gehen ging macht machen kommt kommen kam '
        . 'the of and to in for on with by from at is are was be as an or that this its their new study using based '
        . 'ab wo je ja du we us it'));
    $roh = preg_split('/[\s-]+/u', preg_replace('/[^\p{L}\p{N}\s-]/u', ' ', mb_strtolower($text)), -1, PREG_SPLIT_NO_EMPTY) ?: [];
    $aus = [];
    foreach ($roh as $w) {
        if (mb_strlen($w) >= 2 && !isset($fuell[$w]) && !ctype_digit($w)) {
            $aus[] = stamm($w);
        }
    }
    return $aus;
}

/**
 * Muss dieselben Stämme liefern wie `stamm` in src/lib/radar/text.ts (Prüffall:
 * scripts/tests/stamm-sammler.test.ts). "-rum" und "-eum" werden wie die Mehrzahl
 * auf "-en" gekürzt (Rechenzentrum/Rechenzentren); andere "-um" bleiben.
 */
function stamm(string $w): string
{
    if (str_ends_with($w, 'ungen')) {
        return mb_substr($w, 0, -2);
    }
    if (preg_match('/^(.{3,}[re])ums?$/u', $w, $m)) {
        $w = $m[1] . 'en';
    }
    for ($i = 0; $i < 2 && mb_strlen($w) > 5; $i++) {
        $w = preg_replace('/(innen|ern|en|er|es|e|s|n)$/u', '', $w);
    }
    return $w;
}

// =============================================================================
// Deutscher Bundestag: DIP
// =============================================================================

/**
 * Gesetzgebung als eigene Fundart ("parlament") und die Kleinen Anfragen je
 * Themenfeld als Mass fuer parlamentarische Aufmerksamkeit (Karl, 30.09.2026).
 *
 * Nutzungsbedingungen DIP (27.02.2023): Daten der API duerfen umfassend genutzt
 * und weitergegeben werden, mit der Quelle "Deutscher Bundestag/Bundesrat – DIP";
 * bei kommerzieller Nutzung mit dem Hinweis, dass die Daten in DIP kostenfrei
 * stehen (steht in der App am Abschnitt). Nicht in sinnentstellendem Zusammenhang
 * - deshalb werden die Kleinen Anfragen nur gezaehlt, nie nach Fraktion.
 * Hoechstens 25 gleichzeitige Anfragen erlaubt; hier laufen sie nacheinander.
 */
/** Alle Seiten einer DIP-Liste (Cursor), hoechstens $seiten zu je 100. */
function dipSeiten(string $pfad, array $filter, int $seiten): array
{
    if (DIP_SCHLUESSEL === '') {
        throw new RuntimeException('kein DIP-Schluessel (radar.dip_key)');
    }
    $alle = [];
    $cursor = null;
    for ($i = 0; $i < $seiten; $i++) {
        $abfrage = http_build_query($filter + ['format' => 'json'] + ($cursor ? ['cursor' => $cursor] : []), '', '&', PHP_QUERY_RFC3986);
        // Schluessel im Kopf, nicht in der Adresse - so steht er in keiner Fehlermeldung.
        $a = holeAlle(['x' => ['url' => DIP_API . $pfad . '?' . $abfrage, 'kopf' => ['Authorization: ApiKey ' . DIP_SCHLUESSEL, 'Accept: application/json']]])['x'];
        if ($a['status'] !== 200) {
            throw new RuntimeException("HTTP {$a['status']} {$a['fehler']} - DIP $pfad");
        }
        $d = json($a['text']);
        $neu = $d['documents'] ?? [];
        array_push($alle, ...$neu);
        if ($neu === [] || empty($d['cursor']) || $d['cursor'] === $cursor || count($alle) >= (int) ($d['numFound'] ?? 0)) {
            break;
        }
        $cursor = $d['cursor'];
    }
    return $alle;
}

/** Stichwortmuster eines Themenfelds - dieselben Regeln wie in themenfelder(). */
function feldMuster(array $de): string
{
    return '/(?<!\p{L})(' . implode('|', array_map(
        fn($w) => preg_quote(mb_strtolower($w), '/') . (mb_strlen($w) <= 3 ? '(?!\p{L})' : ''),
        $de,
    )) . ')/u';
}

/** Zu welchen Themenfeldern ein Vorgang gehoert: ueber seine Stichworte und sein Sachgebiet. */
function felderVon(string $text, array $sachgebiete): array
{
    static $muster = null;
    $muster ??= array_combine(array_column(THEMENFELDER, 0), array_map(fn($t) => feldMuster($t[3]), THEMENFELDER));
    $klein = mb_strtolower($text);
    $felder = [];
    foreach ($muster as $id => $m) {
        if (preg_match($m, $klein) === 1) {
            $felder[] = $id;
        }
    }
    foreach ($sachgebiete as $sg) {
        if (isset(DIP_SACHGEBIET_FELD[$sg])) {
            $felder[] = DIP_SACHGEBIET_FELD[$sg];
        }
    }
    return array_values(array_unique($felder));
}

function quelleDip(): array
{
    $jetzt = time();

    // Gesetzgebung: alles, was sich in den letzten 60 Tagen bewegt hat. Die
    // Frische zaehlt ab der letzten Bewegung - ein neuer Stand ("verabschiedet")
    // macht einen Vorgang wieder frisch.
    $gesetze = dipSeiten('vorgang', [
        'f.zuordnung' => 'BT',
        'f.vorgangstyp' => 'Gesetzgebung',
        'f.aktualisiert.start' => gmdate('Y-m-d\TH:i:s', $jetzt - 60 * TAG),
    ], 5);
    $signale = [];
    foreach ($gesetze as $v) {
        $sachgebiete = $v['sachgebiet'] ?? [];
        $deskriptoren = array_column($v['deskriptor'] ?? [], 'name');
        // Fuer die Themenfelder nur die Haupt-Schlagworte ("fundstelle") - der
        // Bundeshaushalt traegt sonst alle Ministerien und landete ueberall.
        $haupt = array_column(array_filter($v['deskriptor'] ?? [], fn($d) => !empty($d['fundstelle'])), 'name');
        $beratung = (string) ($v['beratungsstand'] ?? '');
        $kurzfassung = trim(html_entity_decode(strip_tags((string) ($v['abstract'] ?? '')), ENT_QUOTES | ENT_HTML5, 'UTF-8'));
        $initiative = implode(', ', $v['initiative'] ?? []);
        $themen = felderVon($v['titel'] . ' ' . $kurzfassung . ' ' . implode(' ', $haupt), $sachgebiete);
        $signale[] = signal([
            'id' => 'dip:' . $v['id'],
            'quelle' => 'dip',
            'quelleName' => 'Deutscher Bundestag/Bundesrat – DIP',
            'art' => 'parlament',
            'steep' => DIP_SACHGEBIET_STEEP[$sachgebiete[0] ?? ''] ?? 'politik',
            'titel' => (string) $v['titel'],
            'text' => kurz(trim(($beratung !== '' ? "Stand: $beratung. " : '') . $kurzfassung), 280),
            'url' => 'https://dip.bundestag.de/vorgang/-/' . $v['id'],
            'datum' => iso(strtotime((string) ($v['aktualisiert'] ?? $v['datum']))),
            'guete' => 5,
            'stichworte' => array_slice(array_values(array_unique([...$deskriptoren, ...$sachgebiete])), 0, 12) ?: null,
            'themen' => $themen ?: null,
            'pruefung' => $initiative !== '' ? "Initiative: $initiative" : null,
        ]);
    }

    // Kleine Anfragen: nur gezaehlt, je Themenfeld, 14 Tage gegen die 14 davor.
    $anfragen = dipSeiten('vorgang', [
        'f.zuordnung' => 'BT',
        'f.vorgangstyp' => 'Kleine Anfrage',
        'f.datum.start' => gmdate('Y-m-d', $jetzt - 28 * TAG),
    ], 8);
    $namen = array_column(THEMENFELDER, 1, 0);
    $zaehlung = [];
    $gesamt = ['jetzt' => 0, 'vorher' => 0];
    foreach ($anfragen as $a) {
        $spalte = ($jetzt - strtotime((string) $a['datum'])) / TAG < 14 ? 'jetzt' : 'vorher';
        $gesamt[$spalte]++;
        foreach (felderVon((string) $a['titel'], $a['sachgebiet'] ?? []) as $feld) {
            $zaehlung[$feld][$spalte] = ($zaehlung[$feld][$spalte] ?? 0) + 1;
        }
    }
    $felder = [];
    foreach ($zaehlung as $feld => $z) {
        $felder[] = ['feld' => $feld, 'name' => $namen[$feld] ?? $feld, 'jetzt' => $z['jetzt'] ?? 0, 'vorher' => $z['vorher'] ?? 0];
    }
    usort($felder, fn($a, $b) => [$b['jetzt'], $b['vorher']] <=> [$a['jetzt'], $a['vorher']]);

    return [
        'signale' => $signale,
        'parlament' => [
            'stand' => iso($jetzt),
            'anfragenJetzt' => $gesamt['jetzt'],
            'anfragenVorher' => $gesamt['vorher'],
            'felder' => $felder,
        ],
    ];
}


// =============================================================================
// Kleinteile
// =============================================================================

function signal(array $teil): array
{
    $teil = array_filter($teil, fn($v) => $v !== null);
    $teil['gesehen'] = iso(time());
    $teil['stichworte'] ??= array_slice(array_values(array_unique(woerter($teil['titel'] . ' ' . $teil['text']))), 0, 12);
    return $teil;
}

function trendAusReihe(array $r, float $momentum): array
{
    return [
        'id' => 'trend-' . $r['id'], 'art' => 'reihe', 'steep' => $r['steep'], 'titel' => $r['titel'], 'beschreibung' => $r['aussage'],
        'momentum' => $momentum, 'verlauf' => array_column($r['punkte'], 'wert'), 'belege' => [], 'reihe' => $r['id'],
    ];
}

function abgelaufen(array $s, int $jetzt): bool
{
    $alter = ($jetzt - strtotime($s['datum'])) / TAG;
    return 0.5 ** ($alter / HALBWERTSZEIT_TAGE[$s['art']]) < ABGELAUFEN;
}

function richtungVon(float $neu, float $alt, float $schwelle): string
{
    return $neu - $alt > $schwelle ? 'steigt' : ($alt - $neu > $schwelle ? 'faellt' : 'stabil');
}

/** ISO-Zeit wie Date.toISOString() in JavaScript. */
function iso(int|false $zeit): string
{
    return gmdate('Y-m-d\TH:i:s.000\Z', $zeit ?: time());
}

function kurz(string $t, int $n): string
{
    $s = trim((string) preg_replace('/\s+/u', ' ', $t));
    return mb_strlen($s) > $n ? rtrim(mb_substr($s, 0, $n - 1)) . '…' : $s;
}

/** Deutsche Zahl; Platzhalter der Statistik ("...", "-", "x") werden NAN, nicht 0. */
function zahl(string $s): float
{
    $s = trim($s);
    return preg_match('/^-?\d[\d.]*(,\d+)?$/', $s) ? (float) str_replace(',', '.', str_replace('.', '', $s)) : NAN;
}

function zahlDe(float|int $x): string
{
    return is_int($x) || floor($x) == $x ? number_format((float) $x, 0, ',', '.') : number_format((float) $x, 1, ',', '.');
}

function prozent(float $x, int $stellen = 1): string
{
    return number_format($x, $stellen, ',', '') . ' %';
}

function monatName(string $jjjjmm): string
{
    $monate = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
    return $monate[(int) substr($jjjjmm, 5, 2) - 1] . ' ' . substr($jjjjmm, 0, 4);
}

/** Die Zusammenfassung aus OpenAlex' Wortindex zurueckbauen. */
function abstractAus(array $index): string
{
    $woerter = [];
    foreach ($index as $wort => $stellen) {
        foreach ($stellen as $i) {
            $woerter[$i] = $wort;
        }
    }
    ksort($woerter);
    return implode(' ', $woerter);
}

function genesisCsv(string $text, string $name): array
{
    $text = preg_replace('/^\xEF\xBB\xBF/', '', $text);
    if (!str_starts_with($text, 'statistics_code')) {
        throw new RuntimeException("$name: " . kurz($text, 120));
    }
    $zeilen = preg_split('/\r?\n/', trim($text));
    $spalten = explode(';', array_shift($zeilen));
    return array_map(fn($z) => array_combine($spalten, array_pad(explode(';', $z), count($spalten), '')), $zeilen);
}

/** Monat einer GENESIS-Zeile als "JJJJ-MM" (Jahrestabellen: "JJJJ-12"). */
function genesisZeit(array $z): string
{
    foreach ($z as $k => $v) {
        if (str_ends_with($k, '_attribute_code') && preg_match('/^MONAT(\d\d)$/', (string) $v, $m)) {
            return $z['time'] . '-' . $m[1];
        }
    }
    return $z['time'] . '-12';
}

/** Die erste Datei aus einem ZIP - ueber das zentrale Verzeichnis, das die Groessen sicher kennt. */
function ersteDateiAusZip(string $zip): string
{
    $ende = strrpos($zip, "PK\x05\x06");
    if ($ende === false) {
        throw new RuntimeException('kein ZIP');
    }
    $verzeichnis = unpack('V', $zip, $ende + 16)[1];
    $methode = unpack('v', $zip, $verzeichnis + 10)[1];
    $groesse = unpack('V', $zip, $verzeichnis + 20)[1];
    $kopf = unpack('V', $zip, $verzeichnis + 42)[1];
    $start = $kopf + 30 + unpack('v', $zip, $kopf + 26)[1] + unpack('v', $zip, $kopf + 28)[1];
    $daten = substr($zip, $start, $groesse);
    return $methode === 0 ? $daten : (string) gzinflate($daten);
}

function json(string $text): array
{
    return json_decode($text, true, 512, JSON_THROW_ON_ERROR);
}

function xml(string $text): SimpleXMLElement
{
    $x = simplexml_load_string($text, 'SimpleXMLElement', LIBXML_NOCDATA | LIBXML_NONET);
    if ($x === false) {
        throw new RuntimeException('kein XML');
    }
    return $x;
}

function hole(string $url): string
{
    $a = holeAlle(['x' => ['url' => $url]])['x'];
    if ($a['status'] !== 200) {
        throw new RuntimeException(ohneSchluessel("HTTP {$a['status']} {$a['fehler']} - " . kurz($url, 90)));
    }
    return $a['text'];
}

/**
 * Viele Abrufe gleichzeitig, hoechstens $gleichzeitig auf einmal - die
 * tagesschau allein sind 56 Tagesseiten.
 *
 * @param array<string|int, array{url: string, methode?: string, kopf?: string[], rumpf?: string}> $anfragen
 * @return array<string|int, array{status: int, text: string, fehler: string}>
 */
function holeAlle(array $anfragen, int $gleichzeitig = 8, int $sekunden = 40): array
{
    $mh = curl_multi_init();
    $warte = $anfragen;
    $laufend = [];
    $ergebnis = [];
    $starte = function () use (&$warte, &$laufend, $mh, $sekunden): void {
        $schluessel = array_key_first($warte);
        $a = $warte[$schluessel];
        unset($warte[$schluessel]);
        $ch = curl_init($a['url']);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_FOLLOWLOCATION => true,
            CURLOPT_MAXREDIRS => 3,
            CURLOPT_POSTREDIR => CURL_REDIR_POST_ALL,
            CURLOPT_TIMEOUT => $sekunden,
            CURLOPT_CONNECTTIMEOUT => 15,
            CURLOPT_USERAGENT => ABSENDER,
            CURLOPT_ENCODING => '',
            CURLOPT_HTTPHEADER => $a['kopf'] ?? [],
        ]);
        if (($a['methode'] ?? 'GET') === 'POST') {
            curl_setopt($ch, CURLOPT_POST, true);
            curl_setopt($ch, CURLOPT_POSTFIELDS, $a['rumpf'] ?? '');
        }
        curl_multi_add_handle($mh, $ch);
        $laufend[spl_object_id($ch)] = $schluessel;
    };
    while ($warte && count($laufend) < $gleichzeitig) {
        $starte();
    }
    do {
        curl_multi_exec($mh, $aktiv);
        curl_multi_select($mh, 1.0);
        while ($info = curl_multi_info_read($mh)) {
            $ch = $info['handle'];
            $schluessel = $laufend[spl_object_id($ch)];
            unset($laufend[spl_object_id($ch)]);
            $ergebnis[$schluessel] = [
                'status' => (int) curl_getinfo($ch, CURLINFO_RESPONSE_CODE),
                'text' => (string) curl_multi_getcontent($ch),
                'fehler' => curl_error($ch),
            ];
            curl_multi_remove_handle($mh, $ch);
            if ($warte) {
                $starte();
            }
        }
    } while ($laufend);
    curl_multi_close($mh);
    return $ergebnis;
}

function option(string $name): ?string
{
    global $argv;
    $i = array_search($name, $argv ?? [], true);
    return $i !== false ? ($argv[$i + 1] ?? null) : null;
}

/** Open edition: credentials come only from environment variables (DESTATIS_TOKEN, OPENALEX_KEY, DIP_KEY). */
function keepass(string $eintrag): string
{
    return '';
}

/**
 * studio-config.php oberhalb des Web-Roots suchen - nie darin. Dieselbe Suche
 * wie in packages/kern/server/teilen.php.
 */
function konfiguration(): ?array
{
    $pfad = getenv('STUDIO_CONFIG') ?: null;
    if ($pfad === null) {
        $webRoot = rtrim(realpath($_SERVER['DOCUMENT_ROOT'] ?? '') ?: '', '/');
        $ordner = __DIR__;
        for ($i = 0; $i < 8 && $ordner !== dirname($ordner); $i++) {
            $ordner = dirname($ordner);
            $imWebRoot = $webRoot !== '' && str_starts_with($ordner . '/', $webRoot . '/');
            if (!$imWebRoot && is_file("$ordner/studio-config.php")) {
                $pfad = "$ordner/studio-config.php";
                break;
            }
        }
    }
    if ($pfad === null || !is_file($pfad)) {
        return null;
    }
    $k = require $pfad;
    return is_array($k) ? $k : null;
}
