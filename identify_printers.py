"""
identify_printers.py

Einmaliges Diagnose-Skript: druckt auf jedem der beiden baugleichen
Caysn-Drucker (Mitte/Rechts, gleiche USB-ID) eine eindeutige Kennung samt
Seriennummer aus. So siehst du physisch, welcher Drucker welche Seriennummer
hat — zuverlässiger als Bus-Adressen, die sich je nach Enumerations-
Reihenfolge beim Neustart verschieben können.

Ablauf:
1. Ausführen: python3 identify_printers.py
2. Auf jedem der beiden Drucker erscheint ein Zettel mit "DRUCKER A" bzw.
   "DRUCKER B" und der jeweiligen Seriennummer.
3. Schau nach, welcher Zettel aus dem physisch mittleren Drucker kommt,
   und welcher aus dem rechten.
4. Sag mir die Seriennummer des mittleren Druckers — dann trage ich sie
   fest im Hauptskript ein (statt Bus-Adressen-Sortierung), damit die
   Zuordnung nie wieder kippt.
"""

import usb.core
from escpos.printer import Usb

shared = list(usb.core.find(find_all=True, idVendor=0x4B43, idProduct=0x3830))

if len(shared) < 2:
    print(f"Nur {len(shared)} Drucker mit dieser ID gefunden — beide müssen")
    print("angeschlossen und erkannt sein, damit die Zuordnung funktioniert.")
    raise SystemExit(1)

labels = ["A", "B"]

for label, d in zip(labels, shared):
    try:
        serial = d.serial_number
    except Exception as e:
        serial = f"(nicht lesbar: {e})"

    print(f"Drucker {label}: Bus {d.bus}, Adresse {d.address}, Seriennummer: {serial}")

    try:
        p = Usb(0x4B43, 0x3830, in_ep=0x81, out_ep=0x03,
                usb_args={"bus": d.bus, "address": d.address})
        p.set(align="center")
        p.text(f"\n\n=== DRUCKER {label} ===\n")
        p.text(f"Bus {d.bus} / Adresse {d.address}\n")
        p.text(f"Seriennummer:\n{serial}\n\n\n")
        p.cut()
        p.close()
        print(f"  -> Testdruck an Drucker {label} gesendet.")
    except Exception as e:
        print(f"  -> Fehler beim Drucken auf Drucker {label}: {e}")

print("\nSchau nach, welcher physische Drucker (Mitte oder Rechts) den Zettel")
print("'DRUCKER A' bzw. 'DRUCKER B' ausgegeben hat, und sag mir die")
print("Seriennummer des MITTLEREN Druckers.")
