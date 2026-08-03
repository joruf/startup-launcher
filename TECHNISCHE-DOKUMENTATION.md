# Startup Launcher — Technische Dokumentation

Architektur-Referenz für Entwickler. Für die reine Bedienung siehe das
[Benutzerhandbuch](MANUAL.md) (Englisch), für Installation/Requirements/Quick-Start
[README.md](README.md).

## 1. Architekturprinzip

Kein Framework, reines `tkinter`/`ttk`. Die Schichten sind strikt getrennt und
folgen alle demselben Muster: **`ui/` → `services/`/`config/` → `models/` →
`json_store.py`**. Jede Schicht kennt nur die darunterliegende, nie umgekehrt:

- **`ui/`** — Tkinter-Fenster/Dialoge. Enthält UI-Logik (Klick-Handling,
  Layout, Zustände wie "welche Zelle wird gerade bearbeitet"), aber keine
  Geschäftslogik und kein `subprocess`/`wmctrl` direkt.
- **`services/`** — Prozessstart, Fenstererkennung/-positionierung via
  `wmctrl`/`xprop`, Single-Instance-Lock/IPC, Start-/Exit-Log. Reine
  Funktionen/Klassen ohne Tkinter-Abhängigkeit — deshalb headless testbar
  (siehe [Tests](#6-tests)).
- **`config/`** — Anwendungsweite Einstellungen (`settings.json`) und die
  Autostart-`.desktop`-Datei.
- **`models/`** — Schema, Default-Seed und Persistenz für Einträge
  (`entries.json`) und Fensterpositionen (`window_geometry.json`).
- **`json_store.py`** — die einzige Stelle, die tatsächlich Dateien liest/schreibt.

`paths.py` definiert alle Pfad-Konstanten einmalig beim Import
(`ENTRIES_FILE`, `GEOMETRY_FILE`, `SETTINGS_FILE`, `LOCK_DIR`, ...). Jedes
Modul importiert die für sich relevanten Konstanten per
`from paths import X` in seinen **eigenen** Namensraum — wichtig beim Testen
(siehe [Tests](#6-tests)): patchen muss man `modul.X`, nicht `paths.X`, da der
Name zur Importzeit gebunden wurde.

## 2. Persistenz (`json_store.py`)

Alle drei Datendateien (`entries.json`, `window_geometry.json`,
`settings.json`) laufen durch dieselben zwei Funktionen:

- **`load_json(path, default)`** — gibt `default` zurück, wenn die Datei
  fehlt, leer oder kaputt ist (`JSONDecodeError`/`OSError`), statt eine
  Exception zu werfen. Ein abgeschnittener Absturz-Rest crasht die App beim
  nächsten Start also nie.
- **`save_json_atomic(path, data)`** — schreibt in eine temporäre Datei im
  selben Verzeichnis und benennt sie per `os.replace()` um (auf POSIX atomar).
  Ein Kill/Absturz mitten im Schreiben kann die Zieldatei nie in einem
  halbgeschriebenen Zustand hinterlassen.

### `models/entries.py`

`load_entries()` lädt `entries.json`; existiert die Datei nicht, wird aus
`entries.example.json` geseedet (falls vorhanden, sonst leere Liste) und
sofort gespeichert. `_ensure_schema()` ergänzt bei jedem Laden fehlende `id`
(UUID4-Hex) und `delay_seconds` (Default `0`) und persistiert das Backfill
sofort — alte `entries.json`-Dateien aus früheren Versionen werden so
transparent migriert.

### `models/geometry.py`

`window_geometry.json` ist ein simples `{entry_id: {x, y, width, height}}`.
Schlüssel ist die interne `id` des Eintrags, nicht Name oder Listenposition
— Umbenennen oder Umsortieren verliert die gespeicherte Position nicht.
`services/geometry.forget(entry_ids)` räumt beim Löschen eines Eintrags/einer
Gruppe die verwaisten Einträge auf.

### `config/settings.py`

Defaults werden über `load_settings()` mit dem gespeicherten Inhalt gemerged
(fehlende/neue Keys bekommen automatisch ihren Default, ohne die Datei zu
migrieren). Der `clean_shutdown`-Flag ist der interessante Teil:

- `mark_session_started()` wird einmal beim App-Start aufgerufen, gibt den
  *vorherigen* Wert zurück und setzt ihn danach sofort auf `False`.
- `mark_clean_shutdown()` wird nur im echten Quit-Pfad
  (`StartupLauncherApp._quit_application`) aufgerufen und setzt ihn auf `True`.

Das Ergebnis: der Flag ist nur zwischen einem sauberen Quit und dem
*unmittelbar folgenden* Autostart-Lauf `True`. Ein Crash, ein `kill -9` oder
ein Stromausfall lässt ihn auf `False` — und genau das ist das Signal, das
`_start_all()` nutzt, um "Restore saved window positions automatically at
startup" für genau einen Lauf zu überspringen, falls die zuletzt gespeicherten
Positionen nicht vertrauenswürdig sein könnten.

`launch_at_login` (Default `True`) ist der zweite Login-Schalter neben der
`.desktop`-Datei: er entscheidet, ob ein `--autostart`-Lauf die aktivierten
Einträge startet oder nur ins Tray geht. Beides ist absichtlich getrennt —
"Launcher startet mit" und "Launcher startet meine Programme" sind zwei
verschiedene Aussagen, und nur die erste steht in `~/.config/autostart/`.

### `config/autostart.py`

Schreibt/entfernt `~/.config/autostart/Startup Launcher.desktop`. Der Inhalt
wird bewusst so erzeugt, dass er nicht von der Login-Umgebung abhängt:

- **absoluter Interpreterpfad** (`sys.executable`, Fallback
  `shutil.which("python3")`): `PATH` ist im Autostart-Kontext nicht dasselbe
  wie in einer Login-Shell,
- **`Path=`** auf das Projektverzeichnis, statt sich auf ein Arbeitsverzeichnis
  zu verlassen,
- **`--autostart`** — ohne dieses Flag startet nur die GUI, und kein einziger
  Eintrag wird ausgeführt,
- **`X-GNOME-Autostart-Delay=10`**: Cinnamon/GNOME feuern Autostart-Einträge,
  während das Panel samt Systray-Bereich noch hochkommt. Der Lauf in dieses
  Rennen hinein kostete das Tray-Icon.

`refresh_if_enabled()` wird bei **jedem** App-Start aufgerufen
(`StartupLauncherApp.__init__`) und schreibt eine vorhandene, aber inhaltlich
abweichende `.desktop`-Datei neu (`is_outdated()`). Ohne das behält ein
Eintrag aus einer älteren Version — z. B. einer noch ohne `--autostart` — sein
Verhalten, bis die Checkbox einmal aus- und wieder eingeschaltet wird: die
Checkbox zeigt "an", der Login tut trotzdem nichts. Ist Autostart aus, tut die
Funktion nichts (sie schaltet nie von sich aus ein).

### `services/session_log.py`

Ein Autostart-Lauf hat kein Terminal. Läuft dort etwas schief, bleibt ohne
eigenes Log nichts übrig, was man nachher ansehen könnte — genau die Situation,
in der halb gestartete Programme und ein fehlendes Tray-Icon nicht mehr
erklärbar sind. Deshalb protokolliert `write()` zeilenweise nach
`$XDG_STATE_HOME/startup-launcher/session.log` (bewusst **nicht** in
`XDG_RUNTIME_DIR`, das beim Reboot verschwindet):

- Start mit Modus (`autostart`/`manual`) und PID, abgelehnte Zweitstarts,
- wie viele Einträge der Login-Lauf gestartet hat bzw. dass
  `launch_at_login` aus ist,
- fehlendes Tray, Traceback bei einem Absturz, sauberes Ende.

Fehlt eine Start-/Endezeile-Paarung, ist der Prozess unterwegs gestorben.
Schreibfehler werden geschluckt (`OSError`) — ein Log darf einen Start nie
verhindern. Ab `MAX_BYTES` wird einmal nach `session.log.1` rotiert.
**Help > Startup Log...** zeigt die letzten Zeilen in der UI.

## 3. Prozessstart & Fensterverwaltung

### `services/launcher.py`

`launch_entries()` iteriert über alle aktivierten Einträge; bei
`delay_seconds > 0` wird der Start verzögert eingeplant statt sofort
ausgeführt. Wie geplant wird, entscheidet der optionale
`schedule(delay_seconds, callback)`-Parameter:

- **ohne** ihn ein `threading.Timer` pro Eintrag (daemon-Thread, damit ein
  noch ausstehender Timer den App-Exit nicht blockiert) — der Default für
  Aufrufer ohne Tk,
- **mit** ihm die Tk-Uhr: `StartupLauncherApp` übergibt
  `_schedule_delayed_launch`, also `root.after(...)`. Der verzögerte Start und
  die Statuszeile, die er schreibt, laufen damit im Mainloop-Thread statt in
  einem Timer-Thread.

`launch_entry()` selbst:

1. flacht den (ggf. mehrzeiligen) Befehl über `_flatten_command()` auf eine
   Zeile ab und parst ihn mit `shlex.split()`,
2. startet ihn per `subprocess.Popen(cwd=Path.home())`,
3. startet danach — falls `window_mode != "normal"` — `_apply_window_state()`
   in einem Hintergrund-Thread: pollt `wmctrl -lx`/`wmctrl -l` alle 0,5s bis
   zu 20s lang, bis der konfigurierte Fenster-Match auftaucht, und wendet
   dann den passenden `wmctrl -b`-State an (`add,hidden` /
   `add,maximized_vert,maximized_horz` / `add,fullscreen`).

Bei aktivem `geometry_restore`-Callback (nur beim echten Autostart-Lauf mit
eingeschaltetem "restore on startup", siehe oben) läuft stattdessen
`services.geometry.wait_and_restore_geometry` in diesem Thread — das ersetzt
die normale Window-Mode-Behandlung komplett für diesen Lauf.

### `services/geometry.py`

Fenstererkennung läuft über zwei Linux-Bordmittel:

- `wmctrl -lG` liefert Position/Größe/Titel aller offenen Fenster. Der
  Parser-Regex (`_GEOMETRY_LINE_RE`) liest bewusst **keine** `WM_CLASS`-Spalte
  aus `wmctrl -lx`, weil dieses Feld selbst Leerzeichen enthalten kann (z. B.
  `"github desktop.GitHub Desktop"`) und eine rein Whitespace-basierte
  Spaltenerkennung damit bricht.
- `xprop -id <id> WM_CLASS` liefert stattdessen gezielt die Klasse für ein
  einzelnes Fenster, wenn `match_mode == "class"` gebraucht wird.

`_find_window()` matcht case-insensitive als Teilstring, je nach
`match_mode` entweder gegen den Fenstertitel oder gegen die `WM_CLASS`.
`_clear_and_apply_geometry()` entfernt zuerst maximiert/fullscreen (der
Fenstermanager ignoriert sonst eine explizite Geometrie-Anweisung), bevor die
neue Position/Größe gesetzt wird.

## 4. Single-Instance & IPC

Zwei kleine, unabhängig testbare Bausteine, die zusammen "nur eine Instanz
läuft je" garantieren:

- **`services/single_instance.py`** — `SingleInstanceGuard.acquire()` öffnet
  `$XDG_RUNTIME_DIR/startup-launcher/instance.lock` und versucht einen
  exklusiven, nicht-blockierenden `fcntl.flock`. Gelingt das nicht
  (`BlockingIOError`), läuft bereits eine Instanz. Der Lock ist
  Betriebssystem-Ebene und an den offenen File-Descriptor gebunden — stirbt
  der Prozess (Crash, `kill -9`), gibt der Kernel ihn automatisch frei. Kein
  klassisches PID-File, das nach einem Absturz von Hand aufgeräumt werden
  müsste.
- **`services/instance_ipc.py`** — `InstanceControlServer` lauscht auf einem
  Unix-Socket (`.../control.sock`) in einem Hintergrund-Thread und reagiert
  auf ein einziges Kommando (`b"SHOW"`), indem es den übergebenen
  `on_show`-Callback aufruft. `request_show_existing_instance()` ist die
  Client-Seite davon. Ein verwaistes Socket-File einer abgestürzten
  Instanz blockiert den nächsten Start nicht — `_run()` entfernt eine
  vorhandene Datei an diesem Pfad, bevor es selbst bindet.

`main()` in `ui/main_window.py` ruft `enforce_single_instance(quiet=auto_run)`
auf, **bevor** überhaupt ein `tk.Tk()`-Root erzeugt wird. Bei `quiet=True`
(Autostart-Lauf) wird ein zweiter Start lautlos abgebrochen; sonst wird die
laufende Instanz per IPC in den Vordergrund geholt und ein
"Already Running"-Dialog gezeigt.

Wichtig für den `on_show`-Callback: er läuft im Server-Thread, nicht im
Tkinter-Mainloop-Thread. Tkinter ist nicht thread-safe — deshalb wird der
Callback immer über `self.root.after(0, ...)` an den Mainloop zurück
delegiert (`ui/main_window.py`, `_start_control_server`), nie direkt
aufgerufen.

## 5. UI-Besonderheiten (`ui/main_window.py`)

### Checkbox-/Launch-Spalten als Overlay-Widgets

`ttk.Treeview` kann in einer Datenspalte nur Text rendern, kein größeres
Glyph und keinen anklickbaren "Button". Die Enabled-Checkbox (☑/☐/☒) und der
▶-Launch-Button sind deshalb echte `tk.Label`-Widgets, die per `.place()`
exakt über die jeweilige Zellen-Bbox gelegt werden (`_rebuild_column_overlay`,
aufgerufen aus `_position_overlays`). Sie werden bei jedem Scroll, Resize,
Sortieren und Auf-/Zuklappen einer Gruppe komplett neu aufgebaut — es gibt
keinen inkrementellen Diff-Mechanismus, das wäre bei der Tabellengröße dieser
App unnötige Komplexität.

### Inline-Zellbearbeitung: State Machine

Genau eine Zelle kann gleichzeitig im Bearbeitungsmodus sein, gehalten in
`self._active_edit` (`{widget, var, index, field}` oder `None`).

- **Öffnen** — `_on_tree_double_click` (gebunden an `<Double-1>` auf dem
  Tree) prüft Spalte und Zeile und ruft `_begin_inline_edit()`. Öffnen
  erfordert einen **Doppelklick**, ein einzelner Klick wählt nur die Zeile
  aus wie überall sonst.
- **Schließen durch Klick anderswo** — `root.bind_all("<Button-1>", ...)`
  fängt *jeden* Klick im ganzen Fenster ab und plant über
  `root.after_idle` eine Prüfung (`_maybe_close_inline_edit`): trifft der
  Klick nicht das gerade offene Editor-Widget selbst, wird committet.
- **Der Doppelklick-Fallstrick** — Öffnen braucht zwei rohe
  `<Button-1>`-Presses. Beide erreichen *zusätzlich* auch den globalen
  `bind_all`-Handler von oben — ohne Gegenmaßnahme würde der Editor sich
  augenblicklich selbst wieder schließen, in dem Moment, in dem er
  öffnet. Der Fix: `_begin_inline_edit` setzt
  `self._suppress_global_close_count = 2`; `_maybe_close_inline_edit`
  zählt das für die nächsten zwei Aufrufe einfach herunter, statt zu
  schließen. (Frühere Version hatte hier ein einzelnes Bool-Flag statt
  eines Zählers — das reichte, solange Öffnen noch ein einzelner Klick war,
  und wurde beim Umstieg auf Doppelklick zum Zähler erweitert.)
- **Commit/Cancel** — `<Return>`/`<KP_Enter>`/`<FocusOut>` committen,
  `<Escape>` verwirft. Committen validiert je nach Feld (Delay wird über
  `entry_model.clamp_delay_seconds` auf 0-60 geklemmt; XY/Size parsen
  `x,y` bzw. `breitexhöhe` und schreiben bei Erfolg direkt in
  `window_geometry.json` über `models.geometry`, bei Fehlschlag nur eine
  Statuszeile ohne Datenänderung).
- Der `tk.StringVar` von `_active_edit["var"]` wird bewusst als Python-Objekt
  am Leben gehalten (nicht nur im Widget referenziert) — ohne verbleibende
  Python-Referenz sammelt der Garbage Collector die Var vorzeitig ein, was
  die zugrundeliegende Tcl-Variable unsetzt und das Feld leer erscheinen
  lässt.

### Sortierung

Spaltenüberschriften sind über `heading(col, command=lambda c=col:
self._sort_by(c))` verdrahtet (außer `launch`, das keine Daten zum Sortieren
hat). `_sort_by` sortiert `self.entries` in-place per Sort-Key
(`_sort_key`, spaltenspezifisch — Name/Command case-insensitive, XY/Size
über die zugehörige `window_geometry.json`-Position, fehlende Werte sortieren
ans Ende via `float("inf")`), speichert sofort und baut die Tabelle neu auf.
Die Sortierreihenfolge ist damit genauso persistent wie eine manuelle
Move-Up/Down-Umsortierung.

### `ui/wrap_bar.py` — selbst umbrechende Buttonleiste

`WrapButtonBar` platziert Buttons per `.place()` (nicht `.pack()`/`.grid()`)
und berechnet bei jedem `<Configure>`-Event neu, wie viele in eine Zeile
passen. Ändert sich die Zeilenanzahl *nach* dem initialen Aufbau (der Nutzer
macht das Fenster schmaler), meldet der `on_rows_changed`-Callback das an
`StartupLauncherApp._on_button_rows_changed`, das die Fensterhöhe um genau
die Höhe der neuen Zeile(n) vergrößert — Buttons laufen nie unsichtbar über
den Fensterrand hinaus.

### Sichtbarkeit: manueller Start vs. Autostart-Lauf

Das Fenster wird komplett `withdraw()`ed aufgebaut (`__init__`) — wer es
wieder einblendet, entscheidet also, was der Nutzer sieht. Das passiert
ausschließlich in `_start_tray_icon()`:

- **manueller Start** — Fenster auf, egal ob das Tray funktioniert. Sonst
  sieht ein Start aus wie "nichts passiert".
- **Autostart-Lauf** (`--autostart`) — bleibt versteckt, auch wenn gar kein
  Tray-Icon zustande kommt (fehlende GTK3-Bindings). Ein Login-Lauf soll dem
  Nutzer kein Fenster ins Gesicht schieben; der Fall wird stattdessen ins
  Session-Log geschrieben.

### `_log()` und Threads

`launcher.py` loggt aus seinen Fenster-State-Workern, also aus fremden
Threads. `_log()` schreibt die Statuszeile deshalb nur direkt, wenn es im
Main-Thread läuft, und delegiert sonst über `root.after(0, ...)` an den
Mainloop — dieselbe Regel wie beim IPC-`on_show`-Callback (siehe
[Single-Instance & IPC](#4-single-instance--ipc)). Nach dem Fensterabbau
laufen Worker-Threads noch kurz weiter, deshalb schluckt der Delegationspfad
`TclError`/`RuntimeError`: eine Statuszeile ist keinen Absturz wert.

## 6. Tests

```bash
python3 -m unittest discover -s tests -v          # mit echtem $DISPLAY
xvfb-run -a python3 -m unittest discover -s tests -v   # headless, wie in CI
```

| Datei | Schicht | Was geprüft wird |
|---|---|---|
| `test_json_store.py` | `json_store.py` | Atomares Schreiben (kein Leftover-Tempfile, kein Datenverlust bei Fehler), resiliente Reads (fehlende/leere/kaputte Datei) |
| `test_models_entries.py` | `models/entries.py` | Schema-Backfill (`id`, `delay_seconds`), Seeding aus `entries.example.json`, `clamp_delay_seconds`, Gruppen-Set |
| `test_models_geometry.py` | `models/geometry.py` | Round-Trip Laden/Speichern |
| `test_config_settings.py` | `config/settings.py` | Defaults-Merge, `launch_at_login`-Default, `clean_shutdown`-Lebenszyklus (`mark_session_started`/`mark_clean_shutdown`) |
| `test_config_autostart.py` | `config/autostart.py` | `.desktop`-Datei anlegen/entfernen, Inhalt (`--autostart`-Flag, absoluter Interpreter, `Path=`, Autostart-Delay), Selbstreparatur eines veralteten Eintrags |
| `test_services_launcher.py` | `services/launcher.py` | Befehlsparsing/-fehler, Delay über `threading.Timer` bzw. eigenen `schedule`-Callback vs. Sofortstart, wmctrl-Statuswechsel inkl. Timeout (alles mit gemocktem `subprocess`/`threading`) |
| `test_services_session_log.py` | `services/session_log.py` | Anlegen/Anhängen mit Zeitstempel, mehrzeilige Einträge, Rotation ab `MAX_BYTES`, nicht schreibbarer Pfad wirft nicht |
| `test_services_geometry.py` | `services/geometry.py` | `wmctrl -lG`-Parsing, Klassen-/Titel-Matching, Scan/Restore/Forget-Round-Trip (gemocktes `subprocess`, echtes Temp-Filesystem für `window_geometry.json`) |
| `test_services_single_instance.py` | `services/single_instance.py` | Echter `fcntl.flock` gegen eine Temp-Lockdatei: zweiter Guard blockiert, Freigabe nach `release()`, `enforce_single_instance` in beiden Modi |
| `test_services_instance_ipc.py` | `services/instance_ipc.py` | Echter Unix-Socket-Roundtrip inkl. verwaistem Socket-File einer "abgestürzten" vorherigen Instanz |
| `test_ui_main_window.py` | `ui/main_window.py` | Inline-Edit öffnen/committen/abbrechen (inkl. der Doppelklick-Suppress-Counter-Regression von oben), Checkbox-/Gruppen-Kaskade, Launch-Button, Sortierung, Move Up/Down, Delete (bestätigt/abgelehnt), externe `entries.json`-Änderungserkennung, Autostart-Lauf (startet Einträge, respektiert `launch_at_login`), Fenstersichtbarkeit manuell vs. Autostart, Statuszeile aus einem Worker-Thread |
| `test_ui_entry_dialog.py` | `ui/entry_dialog.py` | Pflichtfeld-Validierung, Speichern-Ergebnisform, mehrzeiliger Befehl bleibt beim Speichern unverändert |
| `test_ui_settings_dialog.py` | `ui/settings_dialog.py` | Vorbefüllung, Speichern-Ergebnisform, Fallback bei ungültigem Scan-Intervall |

Die `test_ui_*`-Dateien bauen jeweils eine isolierte `StartupLauncherApp`
gegen temporäre Datendateien auf (alle relevanten `*_FILE`-Konstanten werden
per `unittest.mock.patch.object` umgebogen) — sie fassen nie die echten
`entries.json`/`window_geometry.json`/`settings.json` an. Dazu gehören auch
`autostart.AUTOSTART_DIR` und `session_log.SESSION_LOG_FILE`: die App prüft
beim Start ihren eigenen Autostart-Eintrag und protokolliert jeden Start, würde
also sonst in das echte `~/.config` bzw. `~/.local/state` desjenigen schreiben,
der die Suite laufen lässt. Tray-Icon und
IPC-Control-Server werden in diesen Tests zusätzlich auf No-Op gepatcht, da
sie in `test_services_instance_ipc.py` bereits eigenständig abgedeckt sind
und ein echter GTK-Thread/Socket in jedem einzelnen UI-Test nur unnötige
Flakiness einbringen würde.

**Bewusst nicht getestet** (geringes Regressionsrisiko, viel reines
Tk-Rendering statt eigener Logik): `ui/tray.py` (GTK3-Integration),
`ui/style.py` (ttk-Theme), `ui/tooltip.py`, sowie die genaue Pixel-Reflow-
Berechnung in `ui/wrap_bar.py`. `tests/test_cross_platform_contract.py`
bleibt als schneller Rauchtest erhalten (Pfade/Imports funktionieren
überhaupt).

GUI-Tests sind über `unittest.skipUnless(os.environ.get("DISPLAY"), ...)`
abgesichert und werden übersprungen, wo kein `$DISPLAY` gesetzt ist. In CI
wird stattdessen kein Test übersprungen — `xvfb-run -a` stellt ein virtuelles
X11-Display bereit, sodass exakt dieselben Tests laufen wie lokal.

## 7. CI-Pipeline

- **`.github/workflows/ci.yml`** — läuft bei jedem Push/PR auf
  `ubuntu-22.04`/`ubuntu-24.04` × Python `3.11`/`3.12`. Installiert
  `python3-tk`, `wmctrl`, `x11-utils`, `xvfb`; führt zuerst den schnellen
  Contract-Test aus, danach die volle Suite unter `xvfb-run -a`.
- **`.github/workflows/os-matrix.yml`** — manuell auslösbar
  (`workflow_dispatch`) für gezielte On-Demand-Checks auf einer bestimmten
  OS/Python-Kombination, z. B. über das lokale `os-test-matrix`-Tooling.

## 8. Bekannte Einschränkungen

- **Windows wird nicht unterstützt** — die Fensterverwaltung hängt komplett
  an `wmctrl`/`xprop` (X11 EWMH).
- **Wayland wird nicht erkannt oder gesondert behandelt** — `wmctrl`/`xprop`
  funktionieren zuverlässig nur unter X11. Auf einer nativen
  Wayland-Session würden Scan/Restore Position vermutlich schlicht nichts
  finden, ohne dass die App das meldet.
- **Kein Schutz gegen doppeltes Starten desselben Programms** — weder
  `launch_entry` noch die Tabelle prüfen, ob der Zielprozess schon läuft;
  zweimal auf ▶ klicken startet ihn zweimal (siehe
  [Benutzerhandbuch](MANUAL.md#4-launching-programs)).
