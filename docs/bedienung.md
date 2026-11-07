# Kurzanleitung

Start im Projektordner: `python run.py` oder unter Windows
`Start-KopierCommander.cmd` doppelklicken.

## Startsymbol unter Windows

Das App-Symbol zeigt zwei blaue Dateifenster und einen gelben Kopierpfeil.
Es erscheint im Programmfenster und in der Windows-Taskleiste.
Für eine Startverknüpfung mit demselben Symbol PowerShell im Projektordner
öffnen und einmal ausführen:

```powershell
.\tools\Create-Shortcut.ps1
```

Danach `Start-KopierCommander.lnk` doppelklicken. Explorer blendet die Endung
`.lnk` eventuell aus. Die Verknüpfung startet die vorhandene CMD-Datei im
Projektordner. Python mit Tcl/Tk muss weiterhin installiert und über `PATH`
erreichbar sein.

Die Verknüpfung kann auf den Desktop kopiert werden. Der Projektordner samt
`src` und den Symbolen bleibt erhalten. Nach einem Verschieben oder Umbenennen
des Projektordners das Skript erneut ausführen und die Desktop-Kopie ersetzen.
Die Verknüpfung enthält lokale absolute Pfade und wird deshalb nicht ins Git
übernommen. Nach einem neuen Klonen wird sie mit dem obigen Befehl erzeugt;
die Symboldateien sind bereits enthalten.

## Dateien vergleichen und kopieren

1. **Alt+S**: Quellpfad eingeben, Enter.
2. **Alt+Z**: Zielpfad eingeben, Enter.
3. **F3**: Quelle und Ziel einschließlich Unterordnern vergleichen.
4. **Alt+M**: nur fehlende Dateien anzeigen.
5. **Shift+F3**: alle fehlenden Dateien vormerken. Für einzelne Dateien:
   Pfeiltasten und **Leertaste/Einfg**.
6. **F2**: Aufgabe unter einem Namen speichern.
7. **F5**: Kopieren starten; erfolgreiche Kopien erscheinen grün.

**Tab** wechselt zwischen den Dateifenstern. **F4** öffnet den Namensfilter,
**F6** die Aufgabenliste. In der Aufgabe zeigt **Enter** Dateidetails und Fehler;
**Entf** entfernt nur die Aufgabe, keine Filmdatei. **Esc** fordert einen Abbruch
an. **F10** speichert und beendet. Alle Tasten stehen unter **F1**.

Der Vergleich prüft relative Dateinamen und Größen. Gleiche Größe bedeutet
keinen garantierten gleichen Inhalt. Neu kopierte Dateien werden standardmäßig
mit SHA-256 geprüft.

Vorhandene Zieldateien werden standardmäßig übersprungen. **Alt+U** schaltet
Überschreiben um; beim Kopierstart folgt eine Bestätigung. **Alt+H** schaltet die
SHA-256-Prüfung um.

Zielpfade werden bei der Dateiauswahl festgelegt. Ein späterer Zielwechsel
betrifft neue Auswahlen. Beim rekursiven Vergleich bleibt die relative
Unterordnerstruktur erhalten.

Die letzte Aufgabe liegt unter Windows in
`%LOCALAPPDATA%\KopierCommander\letzte-aufgabe.json`. Mit **Shift+F2** lassen sich
auch bisherige Aufgaben aus der ursprünglichen Filmordner-Version laden.
Dateipfade in diesen Aufgaben bleiben unverändert.

Falls der NAS-Zugriff verweigert wird, die Freigabe zuerst im Windows-Explorer
öffnen und dort anmelden. Zugangsdaten werden im Programm nicht gespeichert.
