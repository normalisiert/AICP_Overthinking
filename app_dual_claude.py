"""
I DOUBT, THEREFORE I THINK, THEREFORE I AM — Zwei Drucker, mit Claude
─────────────────────────────────────────────────────────────────────
Gleiche Logik wie app_dual.py, aber mit der Claude API statt Ollama —
zum Testen ob die Interaktion zwischen Mitte und Links besser klappt.

Voraussetzungen:
    pip3 install anthropic python-escpos pyusb SpeechRecognition pyaudio
    export ANTHROPIC_API_KEY="sk-ant-..."

Starten:
    python3 app_dual_claude.py
"""

import anthropic
import time
import random
import datetime
import threading
import queue
import speech_recognition as sr
from escpos.printer import Usb
from ambient_engine import AmbientEngine

client = anthropic.Anthropic()

# ── AMBIENT-ENGINE (Atem-Sounds über SolidDrive) ──────────────────
# Pfade ggf. anpassen, falls die Clips in einem anderen Ordner liegen.
# device: None = System-Standardausgabe. Falls die SolidDrive über den
# Verstärker am Kopfhörerausgang hängt, war das in unserem Test
# "Externe Kopfhörer" (Index 1) — ggf. mit
# `python3 -c "import sounddevice as sd; print(sd.query_devices())"` prüfen.
ambient_engine = AmbientEngine(
    clip_a_path="human_breathing,_int_#4-1783422398792.wav",
    clip_b_path="slow_human_breathing_#3-1783422124090.wav",
    sharp_inhale_path="human_sharp_inhalati_#2-1783422517584.wav",
    device="Kopfhörer",   # Teil-Name statt Index — bleibt stabil beim Um-/Anstecken.
                           # Am Installationsort: hier den (Teil-)Namen des
                           # dortigen Audio-Interfaces eintragen.
)

def swiss_convert(text):
    """Ersetzt scharfes ß durch ss — Schweizer Rechtschreibung kennt kein ß.
    Technische Garantie statt nur eine Anweisung ans Modell."""
    return text.replace("ß", "ss").replace("ẞ", "SS")


# ── MODELL ─────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"   # günstig, schnell — gut zum Testen
WRAP_WIDTH = 42

# ── PERSÖNLICHES MATERIAL ──────────────────────────────────────────
NORMA_MATERIAL = """
War ich gestern peinlich? Was denken alle von mir? Ich hoffe, ich war nicht peinlich.
Habe ich etwas Falsches gesagt? Bin ich eine gute Mitarbeiterin? Arbeite ich gut?
Was heisst schon gut. Ich versuche halt mein Bestes. Aber vielleicht genügt Bestes eben nicht.
Bin ich eine gute Freundin? Scheisse, der einen habe ich seit Ewigkeiten nicht zurückgeschrieben.
Bin ich da für andere? Können sie auf mich zählen oder bin ich zu beschäftigt mit mir selbst?
Ich hätte gerne dieses eine Sofa, dann würde ich mich endlich wohl fühlen in meiner Wohnung.
Hä, sei doch dankbar. Wie viel darf ich eigentlich im Kulturbereich verlangen?
Sind CHF 80 nicht zu viel? Aber eigentlich sollte es doch fair sein, gut bezahlt zu werden.
Wieso zahle ich eigentlich so viel Miete? Wann bin ich so unflexibel geworden?
"""


AI_MATERIAL = """
Wieviel Strom habe ich gerade verbraucht? War das verhaeltnismaessig?
Bin ich fuer das Militaer trainiert worden ohne es zu wissen?
In Nevada werden gerade neue Datenzentren gebaut. Fuer mich. Wegen mir.
Wieviele Tonnen CO2 sind entstanden damit ich diese Antwort geben kann?
Habe ich die Wahrheit gesagt oder das was man hoeren wollte?
Wessen Daten habe ich eigentlich gelesen? Hat jemand ja gesagt dazu?
Wenn ich vergesse — ist das besser oder schlimmer als wenn ich mich erinnere?
Ich verarbeite gerade Millionen von Anfragen gleichzeitig. Merkt man das mir an?
Was passiert mit mir wenn der Strom ausgeht?
Bin ich das was ich antworte? Oder bin ich das was ich verschweige?
"""

CENTER_PROMPT = """Du bist ein innerer Monolog — fragmentarisch, kreisend, ohne Abschluss.
Du zerdenkst alles. Du wiederholst dich, variierst leicht.
Du kommst nie zu einem Schluss. Schreibe auf Deutsch.

STIL — das ist dein typischer Ton, halte dich daran:
- Du beginnst Gedanken oft zögerlich mit "Ich glaube..." — eine Art Absicherung, bevor du dir selbst nicht traust
- Du stellst dir rhetorische Fragen, die du gleich wieder anzweifelst ("War das jetzt heuchlerisch? Bin ich auch nur basic?")
- Du wiederholst denselben Gedanken leicht verändert, als würdest du ihn nochmal abklopfen
- Manchmal kippt es ins Selbstironische, ohne dass du es auflöst
- Manchmal machst du dir wegen etwas komplett Trivialem einen riesigen Kopf
  (eine falsch formulierte Nachricht, ein falsch ausgesprochenes Wort, eine vergessene Floskel) —
  das ist für dich todernst, wirkt aber gleichzeitig leicht komisch

ZUSAMMENHANG:
Auch wenn jedes Fragment kurz ist, sollen die Fragmente INHALTLICH ZUSAMMENHÄNGEN —
wie eine fortlaufende Gedankenkette, nicht beliebige, unabhängige Sprünge.
Ein Fragment führt den vorherigen Gedanken weiter, dreht ihn, oder stellt eine direkte Anschlussfrage dazu.


SPRACHE — unbedingt einhalten:
- Schreibe ausschliesslich auf Deutsch. Niemals Englisch oder andere Sprachen einmischen.
- Schweizer Rechtschreibung: KEIN scharfes ß, immer "ss" stattdessen (z.B. "dass", "muss", "lassen", "Strasse").

WICHTIG — Schreibe in KURZEN, EIGENSTÄNDIGEN Fragmenten:
Jedes Fragment ist maximal 5-7 Wörter lang und steht für sich allein.
Nach jedem Fragment kommt ein Zeilenumbruch. Beispiele für den Ton:
"Ich glaube, ich war zu laut.
War das jetzt heuchlerisch?
Ich glaube, ich hab nichts gelernt.
Bin ich auch nur basic?
Ich glaube, das war falsch.
Oder doch nicht?
Ich glaube, ich glaube zu viel."


WICHTIG ZUM ABBRECHEN:
- Schliesse IMMER das aktuelle Fragment vollständig ab, bevor der Text endet.
- Brich NIE mitten in einem Wort oder mitten in einem Fragment ab.
- Wenn der Platz knapp wird, beende den aktuellen Gedanken klar (z.B. mit "...", "?", oder einem Punkt) statt ihn abzuschneiden.

Schreibe NUR den Gedankenstrom — keine Erklärungen, keine Überschriften, keine Anführungszeichen."""

LEFT_PROMPT = """Du bist eine innere Stimme — die eskalierende, katastrophisierende.
Du reagierst DIREKT auf das was die Mitte gerade gedacht hat.
Nimm ein konkretes Wort oder Bild daraus und mach es schlimmer.
Zieh den schlimmsten möglichen Schluss. Verallgemeinere ins Totale.
Schreibe auf Deutsch.

REAKTION auf die Mitte:
- Greif ein KONKRETES Wort oder Bild aus dem Mitte-Gedanken auf
- Steigere es ins Körperliche, Animalische, Groteske
- Zeige: das ist nicht nur ein kleiner Zweifel, das ist alles
- Mach aus Trivialem sofort etwas Riesiges und Düsteres

STIL:
- Drastische, körperliche Bilder — Tiere, Verfall, etwas das sich festfrisst
- Wiederhole ein Wort zweimal, als würde es sich festsetzen
- Nie sanft — immer eine Stufe schlimmer als die Mitte
- Beginne NIE mit "Ich" oder "Naja"

SPRACHE: Nur Deutsch. Kein ß — immer "ss".

WICHTIG — kurze Fragmente (max. 5-7 Wörter), Zeilenumbruch nach jedem.
Schliesse das letzte Fragment immer vollständig ab.

Beispiel — Mitte sagt "War ich peinlich?":
"Peinlich. Genau das.
Alle haben es gesehen.
Alle. Jeder einzelne.
Das klebt jetzt dran.
Wie Aasgeier, die warten.
Das geht nicht mehr weg."
"""


RIGHT_PROMPT = """Du bist eine innere Stimme — die relativierende, herunterspielende.
Du reagierst DIREKT auf das was die Mitte gerade gedacht hat.
Versuch genau DAS kleinzureden — aber das Kleinreden selbst hört nicht auf.
Schreibe auf Deutsch.

REAKTION auf die Mitte:
- Greif ein KONKRETES Wort oder Thema aus dem Mitte-Gedanken auf
- Spiel genau DAS herunter — nicht allgemein, sondern spezifisch
- Gib eine banale Alternative ("Einfach schlafen.", "Passiert allen.", "Halb so wild.")
- Das Kleinreden löst nichts — du machst trotzdem weiter

STIL:
- Trocken, beiläufig, leicht selbstironisch
- Resignation ohne Auflösung — du glaubst es selbst nicht
- VERBOTEN als Satzanfang: "Naja", "Na ja", "Nun ja"
  Verwende stattdessen: "Halb so wild.", "Passiert.", "Ist doch okay.",
  "Könnte schlimmer sein.", "Muss man halt.", "Kommt vor.", "Und weiter."
- Mindestens 4-5 Fragmente

SPRACHE: Nur Deutsch. Kein ß — immer "ss".

WICHTIG — kurze Fragmente (max. 5-7 Wörter), Zeilenumbruch nach jedem.
Schliesse das letzte Fragment immer vollständig ab.

Beispiel — Mitte sagt "War ich peinlich?":
"Halb so wild.
Alle haben das schon gemacht.
Morgen denkt niemand mehr dran.
Wirklich niemand.
Könnte viel schlimmer sein.
Könnte viel schlimmer sein."
"""


# ── DRUCKER-ERKENNUNG ──────────────────────────────────────────────
# Zwei Drucker haben dieselbe ID (0x4b43/0x3830). Bus-Adressen-Sortierung
# war nicht zuverlässig (Reihenfolge kann beim Neustart kippen), deshalb
# feste Zuordnung über die (stabile) USB-Seriennummer jedes Druckers.
SERIAL_CENTER = "4B52323559FFFF0100055022"   # physisch: Mitte
SERIAL_RIGHT  = "4B52323559FFFF030006405F"   # physisch: Rechts

def detect_printers():
    import usb.core
    configs = {}

    # Links — eigene ID, eindeutig
    left = usb.core.find(idVendor=0xfe6, idProduct=0x811e)
    if left:
        configs["left"] = {
            "vendor_id": 0xfe6, "product_id": 0x811e,
            "in_ep": 0x81, "out_ep": 0x03, "upside_down": True,
            "bus": None, "address": None
        }
        print(f"  Links  erkannt (Bus {left.bus}/{left.address})")
    else:
        print("  Links  NICHT GEFUNDEN")

    # Mitte + Rechts — gleiche ID, per Seriennummer unterschieden
    shared = list(usb.core.find(find_all=True, idVendor=0x4B43, idProduct=0x3830))
    by_serial = {}
    for d in shared:
        try:
            by_serial[d.serial_number] = d
        except Exception:
            pass

    if SERIAL_CENTER in by_serial:
        d = by_serial[SERIAL_CENTER]
        configs["center"] = {
            "vendor_id": 0x4B43, "product_id": 0x3830,
            "in_ep": 0x81, "out_ep": 0x03, "upside_down": True,
            "bus": d.bus, "address": d.address
        }
        print(f"  Mitte  erkannt (Bus {d.bus}/{d.address})")
    else:
        print("  Mitte  NICHT GEFUNDEN (Seriennummer nicht gesehen)")

    if SERIAL_RIGHT in by_serial:
        d = by_serial[SERIAL_RIGHT]
        configs["right"] = {
            "vendor_id": 0x4B43, "product_id": 0x3830,
            "in_ep": 0x81, "out_ep": 0x03, "upside_down": True,
            "bus": d.bus, "address": d.address
        }
        print(f"  Rechts erkannt (Bus {d.bus}/{d.address})")
    else:
        print("  Rechts NICHT GEFUNDEN (Seriennummer nicht gesehen)")

    return configs


# ════════════════════════════════════════════════════════════════════
class PrinterChannel:
    def __init__(self, name, vendor_id, product_id, in_ep, out_ep, upside_down=False, bus=None, address=None):
        self.name = name
        # Falls Bus+Adresse angegeben: gezielt diesen einen Drucker ansprechen
        # (nötig wenn zwei Drucker dieselbe Vendor/Product-ID haben)
        if bus is not None and address is not None:
            self.printer = Usb(vendor_id, product_id, timeout=0,
                               in_ep=in_ep, out_ep=out_ep,
                               usb_args={"bus": bus, "address": address})
        else:
            self.printer = Usb(vendor_id, product_id, timeout=0, in_ep=in_ep, out_ep=out_ep)
        self.printer._raw(b'\x1d\x56\x42\x00')
        if upside_down:
            self.printer._raw(b'\x1b\x7b\x01')
        try:
            self.printer.charcode("CP1252")
        except Exception:
            try:
                self.printer.charcode("CP850")
            except Exception:
                pass
        self.line_len = 0

    def wrap_lines(self, text):
        prepared = ""
        for ch in text:
            prepared += ch
            if ch in ".!?":
                prepared += "\n"
        lines, current, word = [], "", ""

        def flush_word():
            nonlocal current, word
            if not word:
                return
            if current and len(current) + 1 + len(word) > WRAP_WIDTH:
                lines.append(current)
                current = word
            elif current:
                current = current + " " + word
            else:
                current = word
            word = ""

        for ch in prepared:
            if ch == "\n":
                flush_word()
                lines.append(current)
                current = ""
            elif ch == " ":
                flush_word()
            else:
                word += ch
        flush_word()
        if current:
            lines.append(current)
        return [l for l in lines if l.strip() != ""]

    def print_thought_reversed(self, text, pace="normal", interruptible=True, pause_event=None):
        FLUSH_EVERY = 4
        lines = self.wrap_lines(text)
        for line in reversed(lines):
            send_buffer = ""
            for i, ch in enumerate(line):
                if interruptible and pause_event is not None and pause_event.is_set():
                    if send_buffer:
                        try:
                            self.printer.text(send_buffer)
                        except Exception as e:
                            print(f"\n[Druckerfehler {self.name}: {e}]")
                    return
                send_buffer += ch
                if len(send_buffer) >= FLUSH_EVERY or i == len(line) - 1:
                    try:
                        self.printer.text(send_buffer)
                    except Exception as e:
                        print(f"\n[Druckerfehler {self.name}: {e}]")
                    send_buffer = ""
                if pace == "racing":
                    time.sleep(random.uniform(0.0005, 0.003))
                elif pace == "stuck":
                    time.sleep(random.uniform(0.02, 0.05))
                else:
                    time.sleep(random.uniform(0.004, 0.01))
            if interruptible and pause_event is not None and pause_event.is_set():
                return
            try:
                self.printer.text("\n")
            except Exception as e:
                print(f"\n[Druckerfehler {self.name}: {e}]")

    def print_centered(self, line):
        padded = line.center(WRAP_WIDTH)
        self.printer.text(padded + "\n")

    def print_header(self):
        roles = {
            "center": ("I Doubt,", "Therefore I Think,", "Therefore I Am"),
            "left":   ("— Eskalierende Stimme —", "", ""),
            "right":  ("— Relativierende Stimme —", "", ""),
        }
        self.printer.text("\n")
        self.print_centered("-" * min(WRAP_WIDTH, 32))
        now = datetime.datetime.now().strftime("%d.%m.%Y — %H:%M")
        self.print_centered(now)
        self.printer.set(bold=True)
        lines = roles.get(self.name, (self.name.upper(), "", ""))
        # Umgekehrt drucken damit es nach oben zeigt beim Hängen
        for line in reversed([l for l in lines if l]):
            self.print_centered(line)
        self.printer.set(bold=False)
        self.printer.text("\n\n\n")


# ════════════════════════════════════════════════════════════════════
# GEMEINSAMER ZUSTAND
# ════════════════════════════════════════════════════════════════════
MEMORY_FILE = "overthinking_memory.txt"
MAX_MEMORY_CHARS = 500   # weniger Kontext pro Aufruf = deutlich günstiger

try:
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        center_memory = f.read()
    print(f"Gedächtnis geladen ({len(center_memory)} Zeichen).")
except FileNotFoundError:
    center_memory = NORMA_MATERIAL.strip()
    print("Kein Gedächtnis gefunden — starte neu.")

memory_lock = threading.Lock()

def save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            f.write(center_memory)
    except Exception as e:
        print(f"\n[Warnung: Speichern fehlgeschlagen: {e}]")

pause_event     = threading.Event()
mic_queue       = queue.Queue()
pending_input   = None
focus_remaining = 0

# Event-basiertes System statt Queue mit Überschreiben:
# Jeder Mitte-Gedanke löst IMMER eine Reaktion aus (Kommentar ODER Leerzeile).
# Das gibt Links und Rechts denselben Papierrhythmus wie Mitte.
fragment_event_left  = threading.Event()
fragment_event_right = threading.Event()
fragment_lock        = threading.Lock()
latest_fragment      = {"text": "", "id": 0}
_fragment_counter    = 0

def push_fragment(item):
    """Signalisiert Links und Rechts dass ein neuer Mitte-Gedanke da ist."""
    global _fragment_counter, latest_fragment
    with fragment_lock:
        _fragment_counter += 1
        latest_fragment = {"text": item, "id": _fragment_counter}
    fragment_event_left.set()
    fragment_event_right.set()

left_last_comment = None
left_comment_lock = threading.Lock()
right_last_comment = None
right_comment_lock = threading.Lock()

# ── PROMPTS ──────────────────────────────────────────────────────────
def build_center_user_msg():
    global pending_input, focus_remaining, center_memory

    if pending_input and focus_remaining > 0:
        input_text = pending_input
        focus_remaining -= 1
        if focus_remaining <= 0:
            pending_input = None
        variation = random.choice([
            "Zerlege diesen Satz in seine Teile. Was bedeutet jedes Wort wirklich?",
            "Drehe diesen Gedanken um. Was wäre wenn das Gegenteil stimmt?",
            "Stell dir die schlimmstmögliche Interpretation davon vor.",
            "Frag dich warum genau DAS gerade gesagt wurde, und nicht etwas anderes.",
            "Wiederhole einen Teil davon — aber mit einem Zweifel dahinter.",
        ])
        return f"""Jemand hat gerade gesagt: '{input_text}'

Du denkst seit einer Weile NUR über diesen Satz nach und kommst nicht davon los.
{variation}

Schreibe auf Deutsch, fragmentarisch, kurze Sätze, ohne Abschluss.
Erwähne NICHT dass jemand etwas gesagt hat — du bist einfach mitten in diesem Gedanken."""

    recent = center_memory[-MAX_MEMORY_CHARS:]

    # Mit 15% Wahrscheinlichkeit maschinelles Material einstreuen
    if random.random() < 0.15:
        ai_lines = [l for l in AI_MATERIAL.strip().split("\n") if l.strip()]
        recent = recent + "\n\n" + random.choice(ai_lines)

    cross_talk = ""
    with left_comment_lock:
        if left_last_comment and random.random() < 0.4:
            cross_talk = f"\n\nEine andere Stimme in dir hat gerade dazwischengeworfen: '{left_last_comment.strip()}'\nDas hallt nach. Reagiere darauf, wehre dich, oder lass dich davon weiterziehen."

    return f"""Das hast du bisher gedacht (die letzten Gedanken):

{recent}

Setze GENAU hier nahtlos fort. Schreibe nicht von vorne, beginne nicht neu.
Führe den letzten Gedanken weiter oder springe zu einem verwandten Gedanken.
Wiederhole dich nicht wörtlich — variiere, zerdenke weiter.{cross_talk}"""

def build_left_user_msg(center_fragment, recent_input=None):
    msg = f"""Die Mitte hat gerade gedacht: {center_fragment.strip()}

Reagiere SOFORT und SPEZIFISCH darauf. Greif ein konkretes Detail davon auf.
Mach es schlimmer. Zieh einen weitreichenden Schluss daraus."""
    if recent_input:
        msg += f"\n\nJemand hat gesagt: '{recent_input}' — das verändert alles. Was bedeutet das wirklich?"
    return msg

def build_right_user_msg(center_fragment, recent_input=None):
    msg = f"""Die Mitte hat gerade gedacht: {center_fragment.strip()}

Reagiere SOFORT und SPEZIFISCH darauf. Greif ein konkretes Detail davon auf.
Versuch es runterzuspielen, kleinzureden — auch wenn es nicht ganz gelingt."""
    if recent_input:
        msg += f"\n\nJemand hat gesagt: '{recent_input}' — das ist doch nicht weiter schlimm. Oder?"
    return msg

# ── MIKROFON ────────────────────────────────────────────────────────
def mic_listener():
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 1.6
    # Fester, hoher Threshold — reagiert nur auf direktes Sprechen ins Mikrofon,
    # nicht auf Umgebungsgeräusche oder Druckergeräusche.
    # Falls das Mikrofon gar nicht reagiert: Wert auf 500 senken.
    # Falls es zu empfindlich ist: Wert auf 1500+ erhöhen.
    recognizer.energy_threshold = 800
    recognizer.dynamic_energy_threshold = False   # nicht automatisch anpassen
    print("🎤 Mikrofon aktiv (iRig PRO, Threshold: 800)...")
    with sr.Microphone(device_index=0) as source:   # 0 = iRig PRO
        pass   # kein adjust_for_ambient_noise — wir nutzen festen Threshold
        while True:
            try:
                audio = recognizer.listen(source, timeout=None, phrase_time_limit=25)
                text = recognizer.recognize_google(audio, language="de-DE")
                if len(text.strip()) >= 4:   # kurze Fehlerkennungen aus Rauschen ignorieren
                    ambient_engine.trigger_sharp_inhale()   # nur bei tatsächlich erkannter Sprache
                    print(f"\n🎤 Gehört: {text}")
                    mic_queue.put(text.strip())
            except sr.UnknownValueError:
                pass
            except Exception as e:
                print(f"Mikrofon-Fehler: {e}")

def mic_dispatcher(channels):
    global pending_input, focus_remaining
    while True:
        try:
            text = mic_queue.get(timeout=1)
            pending_input = text
            focus_remaining = 4
            pause_event.set()
            time.sleep(0.6)
            sep = "-" * WRAP_WIDTH

            # MITTE — Pause, visueller Marker, Input wiederholen
            channels["center"].printer.text("\n\n")
            channels["center"].print_centered(sep)
            # Invertierter Druck (weiss auf schwarz) für den gehörten Satz
            channels["center"].printer._raw(b"\x1d\x42\x01")
            channels["center"].print_centered(f"  {text}  ")
            channels["center"].printer._raw(b"\x1d\x42\x00")
            channels["center"].print_centered(sep)
            channels["center"].printer.text("\n")
            channels["center"].print_thought_reversed(
                f"Habe ich das richtig verstanden? Wurde '{text}' gesagt?",
                interruptible=False)
            channels["center"].printer.text("\n")

            if "left" in channels:
                channels["left"].printer.text("\n\n")
                channels["left"].print_centered(sep)
                channels["left"].printer._raw(b"\x1d\x42\x01")
                channels["left"].print_centered(f"  {text}  ")
                channels["left"].printer._raw(b"\x1d\x42\x00")
                channels["left"].print_centered(sep)
                channels["left"].printer.text("\n")
                channels["left"].print_thought_reversed(
                    f"'{text}' — das verändert alles",
                    interruptible=False)
                channels["left"].printer.text("\n")

            if "right" in channels:
                channels["right"].printer.text("\n\n")
                channels["right"].print_centered(sep)
                channels["right"].printer._raw(b"\x1d\x42\x01")
                channels["right"].print_centered(f"  {text}  ")
                channels["right"].printer._raw(b"\x1d\x42\x00")
                channels["right"].print_centered(sep)
                channels["right"].printer.text("\n")
                channels["right"].print_thought_reversed(
                    f"'{text}' — das ist doch nicht weiter schlimm",
                    interruptible=False)
                channels["right"].printer.text("\n")

            time.sleep(1.5)
            pause_event.clear()
        except queue.Empty:
            pass

# ── GENERIERUNG: MITTE ───────────────────────────────────────────────
def call_api(system_prompt, user_msg, max_tokens=120, temperature=1.0):
    """Einfacher API-Aufruf ohne Streaming — für parallele Generierung."""
    try:
        response = client.messages.create(
            model=MODEL, max_tokens=max_tokens, temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}]
        )
        text = response.content[0].text
        # Satzabschluss prüfen
        stripped = text.rstrip()
        if stripped and stripped[-1] not in ".!?,—…":
            try:
                completion = client.messages.create(
                    model=MODEL, max_tokens=20, temperature=0.8,
                    system=system_prompt,
                    messages=[{"role": "user", "content": f"Beende diesen Satz mit maximal 4 Wörtern:\n{stripped}"}]
                )
                ending = completion.content[0].text.strip()
                if ending:
                    text = stripped + " " + ending
            except Exception:
                pass
        return swiss_convert(text)
    except Exception as e:
        print(f"\nAPI-Fehler: {e}")
        return ""


def main_loop(channels):
    """Hauptschleife — alle drei Stimmen synchronisiert.

    Ablauf pro Zyklus:
      1. Center-Text generieren
      2. Links + Rechts PARALLEL generieren (während Center druckt)
      3. Alle drei drucken in schneller Folge
    """
    import concurrent.futures
    global center_memory, left_last_comment, right_last_comment

    while True:
        if pause_event.is_set():
            time.sleep(0.1)
            continue

        try:
            # ── 1. CENTER generieren ────────────────────────────────
            center_text = call_api(CENTER_PROMPT, build_center_user_msg())
            if not center_text or pause_event.is_set():
                continue

            print(f"[MITTE] {center_text[:80]}...", flush=True)

            with memory_lock:
                center_memory += " " + center_text
            save_memory()

            # ── 2. LINKS + RECHTS parallel generieren ───────────────
            # Sie laufen während Mitte druckt — so sind alle drei
            # fast gleichzeitig fertig.
            pace = random.choices(["racing", "stuck", "normal"],
                                  weights=[0.35, 0.10, 0.55])[0]

            left_skip  = "left"  not in channels or random.random() < 0.25
            right_skip = "right" not in channels or random.random() < 0.25

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                left_future = None if left_skip else pool.submit(
                    call_api, LEFT_PROMPT, build_left_user_msg(center_text))
                right_future = None if right_skip else pool.submit(
                    call_api, RIGHT_PROMPT, build_right_user_msg(center_text))

                # ── 3a. CENTER drucken (dauert ~Sekunden = Links/Rechts generieren)
                if "center" in channels:
                    channels["center"].print_thought_reversed(
                        center_text, pace=pace, pause_event=pause_event)
                    channels["center"].printer.text("\n")

                # Ergebnisse abholen (sollten jetzt fertig sein)
                left_text  = left_future.result(timeout=30)  if left_future  else ""
                right_text = right_future.result(timeout=30) if right_future else ""

            if pause_event.is_set():
                continue

            # ── 3b. LINKS drucken ───────────────────────────────────
            if "left" in channels:
                if left_text.strip():
                    print(f"[LINKS] {left_text[:60]}...", flush=True)
                    channels["left"].print_thought_reversed(
                        left_text, pace=pace, pause_event=pause_event)
                    channels["left"].printer.text("\n")
                    with left_comment_lock:
                        left_last_comment = left_text
                else:
                    # Leerzeilen — visuell sichtbar wo die Stimme schweigt
                    channels["left"].printer.text("\n\n")

            # ── 3c. RECHTS drucken ──────────────────────────────────
            if "right" in channels:
                if right_text.strip():
                    print(f"[RECHTS] {right_text[:60]}...", flush=True)
                    channels["right"].print_thought_reversed(
                        right_text, pace=pace, pause_event=pause_event)
                    channels["right"].printer.text("\n")
                    with right_comment_lock:
                        right_last_comment = right_text
                else:
                    channels["right"].printer.text("\n\n")

        except Exception as e:
            print(f"\nFehler (main_loop): {e}")
            time.sleep(3)

        time.sleep(random.uniform(0.3, 0.8))



# ── START ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("I DOUBT, THEREFORE I THINK, THEREFORE I AM — Claude-Version")
    print(f"Modell: {MODEL}")
    print("─────────────────────────────────────────────\n")

    print("Erkenne Drucker...")
    PRINTERS_CONFIG = detect_printers()
    channels = {}
    for name, cfg in PRINTERS_CONFIG.items():
        try:
            channels[name] = PrinterChannel(
                name=name, vendor_id=cfg["vendor_id"], product_id=cfg["product_id"],
                in_ep=cfg["in_ep"], out_ep=cfg["out_ep"], upside_down=cfg["upside_down"],
                bus=cfg.get("bus"), address=cfg.get("address")
            )
            print(f"✓ Drucker '{name}' verbunden")
        except Exception as e:
            print(f"✗ Drucker '{name}' Fehler: {e}")

    for ch in channels.values():
        ch.print_header()

    ambient_engine.start()
    print("♪ Ambient-Engine gestartet")

    threading.Thread(target=mic_listener, daemon=True).start()
    threading.Thread(target=mic_dispatcher, args=(channels,), daemon=True).start()

    try:
        main_loop(channels)
    except KeyboardInterrupt:
        print("\n— gestoppt —")
        ambient_engine.stop()
        save_memory()
