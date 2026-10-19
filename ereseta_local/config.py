"""
Static configuration: file locations, page sizing, default hospital/template
settings, dropdown option lists, and the seed barangay/address list.

Nothing in this module talks to the database or draws anything — it is pure
constants so every other module can import from here without creating
circular dependencies.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from reportlab.lib.units import inch

HospitalConfig = dict[str, str]
TemplateConfig = dict[str, Any]


# --------------------------------------------------------------------------
# Filesystem locations
# --------------------------------------------------------------------------

def _get_base_dir() -> str:
    """Folder where data (db, pdfs, images) should live."""
    if getattr(sys, "frozen", False):
        # Once installed, all executable copies share the installed records.
        local_data = os.environ.get("LOCALAPPDATA")
        if local_data:
            installed = os.path.join(local_data, "EReseta")
            if os.path.isfile(os.path.join(installed, "installation.json")):
                return installed
        return os.path.dirname(os.path.abspath(sys.executable))
    # .../ereseta_local/config.py -> project root is one level up
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR: str = _get_base_dir()
DB_FILE: str = os.path.join(BASE_DIR, "ereseta_local.db")
OUTPUT_DIR: str = os.path.join(BASE_DIR, "prescriptions")
ASSETS_DIR: str = os.path.join(BASE_DIR, "assets")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)


# --------------------------------------------------------------------------
# Page sizing
# --------------------------------------------------------------------------

# Default half short-bond (5.5 x 8.5 in). Can be overridden by template settings.
PAGE_WIDTH: float = 5.5 * inch
PAGE_HEIGHT: float = 8.5 * inch
PAGE_SIZE: tuple[float, float] = (PAGE_WIDTH, PAGE_HEIGHT)


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------

DEFAULT_HOSPITAL: HospitalConfig = {
    "name": "LEYTE BAPTIST HOSPITAL INCORPORATED",
    "address": "6524 Hilongos, Leyte, Philippines",
    "email": "lbhi_746@yahoo.com.ph",
    "tel": "+63 (053) 767-9497",
    "mobile": "099951135547 / 091393323540 / 095331081887",
    "motto": '"Preach the word and heal the sick" - Luke 9:6',
}

SEX_OPTIONS: list[str] = ["Male", "Female"]
CIVIL_STATUS_OPTIONS: list[str] = ["Single", "Married", "Widowed", "Separated", "Divorced", "Child", "Widower", "Other"]

# Default template layout (coordinates are in points relative to bottom-left of page,
# same as reportlab). Values are percentages of page width/height for easier scaling.
DEFAULT_TEMPLATE: TemplateConfig = {
    "page_width_in": 5.5,
    "page_height_in": 8.5,
    "margin_in": 0.40,
    "logo": {"enabled": True, "path": os.path.join(ASSETS_DIR, "logo.png"), "x_pct": 0.42, "y_pct": 0.94, "w_pct": 0.16, "h_pct": 0.09},
    "signature_img": {"enabled": False, "path": "", "x_pct": 0.58, "y_pct": 0.16, "w_pct": 0.28, "h_pct": 0.07},
    "header_font_size": 11,
    "body_font_size": 9,
    "accent_color": "#0f172a",
    "show_motto": True,
    "show_rx_symbol": True,
    "rx_symbol_path": os.path.join(ASSETS_DIR, "Rx.png"),
    "rx_symbol_size": 28,
    "preview_medicines": [
        {"name": "CEFIXIME 400MG", "quantity": "#10", "instructions": "TAKE 1 TAB 2 TIMES A DAY FOR 5 DAYS"},
        {"name": "AZITHROMYCIN 500MG", "quantity": "#5", "instructions": "TAKE 1 TAB ONCE A DAY FOR 5 DAYS"},
        {"name": "PARACETAMOL 500MG", "quantity": "#10", "instructions": "TAKE 1 TAB EVERY 4 HOURS PRN"},
    ],
}


# --------------------------------------------------------------------------
# Seed addresses: Barangay, Municipality, Province
# (Hilongos area + nearby + major Leyte / Southern Leyte towns)
# --------------------------------------------------------------------------

SEED_BARANGAYS = [
    # --- Hilongos, Leyte (hospital location) ---
    "Agutayan, Hilongos, Leyte",
    "Atabay, Hilongos, Leyte",
    "Baas, Hilongos, Leyte",
    "Bagong Lipunan, Hilongos, Leyte",
    "Bagumbayan, Hilongos, Leyte",
    "Baliw, Hilongos, Leyte",
    "Bantigue, Hilongos, Leyte",
    "Bon-ot, Hilongos, Leyte",
    "Bung-aw, Hilongos, Leyte",
    "Cacao, Hilongos, Leyte",
    "Campina, Hilongos, Leyte",
    "Cantandog 1, Hilongos, Leyte",
    "Cantandog 2, Hilongos, Leyte",
    "Concepcion, Hilongos, Leyte",
    "Hampangan, Hilongos, Leyte",
    "Himo-aw, Hilongos, Leyte",
    "Hitudpan, Hilongos, Leyte",
    "Imelda Marcos (Pong-on), Hilongos, Leyte",
    "Kang-iras, Hilongos, Leyte",
    "Kanghaas, Hilongos, Leyte",
    "Lamak, Hilongos, Leyte",
    "Libertad, Hilongos, Leyte",
    "Liberty, Hilongos, Leyte",
    "Lunang, Hilongos, Leyte",
    "Magnangoy, Hilongos, Leyte",
    "Manaul, Hilongos, Leyte",
    "Marangog, Hilongos, Leyte",
    "Matapay, Hilongos, Leyte",
    "Naval, Hilongos, Leyte",
    "Owak, Hilongos, Leyte",
    "Pa-a, Hilongos, Leyte",
    "Central Poblacion, Hilongos, Leyte",
    "Eastern Poblacion, Hilongos, Leyte",
    "Western Poblacion, Hilongos, Leyte",
    "Pontod, Hilongos, Leyte",
    "Proteccion, Hilongos, Leyte",
    "San Agustin, Hilongos, Leyte",
    "San Antonio, Hilongos, Leyte",
    "San Isidro, Hilongos, Leyte",
    "San Juan, Hilongos, Leyte",
    "San Roque, Hilongos, Leyte",
    "Santa Cruz, Hilongos, Leyte",
    "Santa Margarita, Hilongos, Leyte",
    "Santo Niño, Hilongos, Leyte",
    "Tabunok, Hilongos, Leyte",
    "Tagnate, Hilongos, Leyte",
    "Talisay, Hilongos, Leyte",
    "Tambis, Hilongos, Leyte",
    "Tejero, Hilongos, Leyte",
    "Tuguipa, Hilongos, Leyte",
    "Utanan, Hilongos, Leyte",
    # --- Bato, Leyte ---
    "Alegria, Bato, Leyte",
    "Alejos, Bato, Leyte",
    "Amagos, Bato, Leyte",
    "Anahawan, Bato, Leyte",
    "Bago, Bato, Leyte",
    "Bagong Bayan District, Bato, Leyte",
    "Buli, Bato, Leyte",
    "Cebuana, Bato, Leyte",
    "Daan Lungsod, Bato, Leyte",
    "Dawahon, Bato, Leyte",
    "Himamaa, Bato, Leyte",
    "Dolho, Bato, Leyte",
    "Domagocdoc, Bato, Leyte",
    "Guerrero District, Bato, Leyte",
    "Imelda, Bato, Leyte",
    "Iniguihan District, Bato, Leyte",
    "Kalanggaman District, Bato, Leyte",
    "Katipunan, Bato, Leyte",
    "Liberty, Bato, Leyte",
    "Mabini, Bato, Leyte",
    "Marcelo, Bato, Leyte",
    "Naga, Bato, Leyte",
    "Osmeña, Bato, Leyte",
    "Plaridel, Bato, Leyte",
    "Ponong, Bato, Leyte",
    "Revilla, Bato, Leyte",
    "San Agustin, Bato, Leyte",
    "Tabunok, Bato, Leyte",
    "Tagaytay, Bato, Leyte",
    "Tinago District, Bato, Leyte",
    "Tugas, Bato, Leyte",
    # --- Hindang, Leyte ---
    "Anahaw, Hindang, Leyte",
    "Anolon, Hindang, Leyte",
    "Baldoza, Hindang, Leyte",
    "Bontoc, Hindang, Leyte",
    "Bulacan, Hindang, Leyte",
    "Canha-ayon, Hindang, Leyte",
    "Capudlosan, Hindang, Leyte",
    "Doos Del Norte, Hindang, Leyte",
    "Doos Del Sur, Hindang, Leyte",
    "Himacugo, Hindang, Leyte",
    "Himokilan Island, Hindang, Leyte",
    "Katipunan, Hindang, Leyte",
    "Maasin, Hindang, Leyte",
    "Mabagon, Hindang, Leyte",
    "Mahilum, Hindang, Leyte",
    "Poblacion 1, Hindang, Leyte",
    "Poblacion 2, Hindang, Leyte",
    "San Vicente, Hindang, Leyte",
    "Tabok, Hindang, Leyte",
    "Tagbibi, Hindang, Leyte",
    # --- Matalom, Leyte ---
    "Agbanga, Matalom, Leyte",
    "Altavista, Matalom, Leyte",
    "Cahagnaan, Matalom, Leyte",
    "Calumpang, Matalom, Leyte",
    "Caningag, Matalom, Leyte",
    "Caridad Norte, Matalom, Leyte",
    "Caridad Sur, Matalom, Leyte",
    "Elevado, Matalom, Leyte",
    "Esperanza, Matalom, Leyte",
    "Hitoog, Matalom, Leyte",
    "Itum, Matalom, Leyte",
    "Lowan, Matalom, Leyte",
    "Monte Alegre, Matalom, Leyte",
    "President Garcia, Matalom, Leyte",
    "Punong, Matalom, Leyte",
    "San Isidro, Matalom, Leyte",
    "San Pedro, Matalom, Leyte",
    "Santo Niño, Matalom, Leyte",
    "Santa Fe, Matalom, Leyte",
    "San Juan, Matalom, Leyte",
    "San Salvador, Matalom, Leyte",
    "San Vicente, Matalom, Leyte",
    "Santa Paz, Matalom, Leyte",
    "Tag-os, Matalom, Leyte",
    "Templanza, Matalom, Leyte",
    "Tigbao, Matalom, Leyte",
    "Waterloo, Matalom, Leyte",
    "Zaragoza, Matalom, Leyte",
    "Bagong Lipunan, Matalom, Leyte",
    # --- Inopacan, Leyte ---
    "Apid, Inopacan, Leyte",
    "Cabulisan, Inopacan, Leyte",
    "Canangay, Inopacan, Leyte",
    "Conalum, Inopacan, Leyte",
    "Esperanza, Inopacan, Leyte",
    "Guadalupe, Inopacan, Leyte",
    "Mara-o, Inopacan, Leyte",
    "Tahud, Inopacan, Leyte",
    "Poblacion, Inopacan, Leyte",
    # --- Baybay City, Leyte (major nearby) ---
    "Poblacion Zone 1, Baybay, Leyte",
    "Poblacion Zone 2, Baybay, Leyte",
    "Poblacion Zone 3, Baybay, Leyte",
    "Poblacion Zone 4, Baybay, Leyte",
    "Poblacion Zone 5, Baybay, Leyte",
    "Poblacion Zone 6, Baybay, Leyte",
    "Poblacion Zone 7, Baybay, Leyte",
    "Poblacion Zone 8, Baybay, Leyte",
    "Poblacion Zone 9, Baybay, Leyte",
    "Poblacion Zone 10, Baybay, Leyte",
    "Poblacion Zone 11, Baybay, Leyte",
    "Poblacion Zone 12, Baybay, Leyte",
    "Poblacion Zone 13, Baybay, Leyte",
    "Poblacion Zone 14, Baybay, Leyte",
    "Poblacion Zone 15, Baybay, Leyte",
    "Poblacion Zone 16, Baybay, Leyte",
    "Poblacion Zone 17, Baybay, Leyte",
    "Poblacion Zone 18, Baybay, Leyte",
    "Poblacion Zone 19, Baybay, Leyte",
    "Poblacion Zone 20, Baybay, Leyte",
    "Poblacion Zone 21, Baybay, Leyte",
    "Poblacion Zone 22, Baybay, Leyte",
    "Poblacion Zone 23, Baybay, Leyte",
    "Gabas, Baybay, Leyte",
    "Gakat, Baybay, Leyte",
    "Hipusngo, Baybay, Leyte",
    "Jaena, Baybay, Leyte",
    "Kandabao, Baybay, Leyte",
    "Makinhas, Baybay, Leyte",
    "Pangasugan, Baybay, Leyte",
    "Pomponan, Baybay, Leyte",
    # --- Ormoc / Tacloban common ---
    "Poblacion, Ormoc City, Leyte",
    "Poblacion, Tacloban City, Leyte",
    # --- Southern Leyte (major towns) ---
    "Poblacion, Maasin City, Southern Leyte",
    "Abgao, Maasin City, Southern Leyte",
    "Asuncion, Maasin City, Southern Leyte",
    "Bactul I, Maasin City, Southern Leyte",
    "Bactul II, Maasin City, Southern Leyte",
    "Badiang, Maasin City, Southern Leyte",
    "Bagumbayan, Maasin City, Southern Leyte",
    "Cabulihan, Maasin City, Southern Leyte",
    "Cagnituan, Maasin City, Southern Leyte",
    "Cambooc, Maasin City, Southern Leyte",
    "Combado, Maasin City, Southern Leyte",
    "Guadalupe, Maasin City, Southern Leyte",
    "Hanginan, Maasin City, Southern Leyte",
    "Hantag, Maasin City, Southern Leyte",
    "Hinapu Daku, Maasin City, Southern Leyte",
    "Hinapu Gamay, Maasin City, Southern Leyte",
    "Ibarra, Maasin City, Southern Leyte",
    "Isagani, Maasin City, Southern Leyte",
    "Laboon, Maasin City, Southern Leyte",
    "Lanao, Maasin City, Southern Leyte",
    "Libertad, Maasin City, Southern Leyte",
    "Libhu, Maasin City, Southern Leyte",
    "Lonoy, Maasin City, Southern Leyte",
    "Lunas, Maasin City, Southern Leyte",
    "Mabini, Maasin City, Southern Leyte",
    "Manhilo, Maasin City, Southern Leyte",
    "Mantahan, Maasin City, Southern Leyte",
    "Maria Clara, Maasin City, Southern Leyte",
    "Nonok Norte, Maasin City, Southern Leyte",
    "Nonok Sur, Maasin City, Southern Leyte",
    "Panan-awan, Maasin City, Southern Leyte",
    "Pansaan, Maasin City, Southern Leyte",
    "Rizal, Maasin City, Southern Leyte",
    "San Isidro, Maasin City, Southern Leyte",
    "San Jose, Maasin City, Southern Leyte",
    "San Rafael, Maasin City, Southern Leyte",
    "Santa Cruz, Maasin City, Southern Leyte",
    "Santo Niño, Maasin City, Southern Leyte",
    "Tawid, Maasin City, Southern Leyte",
    "Tunga-tunga, Maasin City, Southern Leyte",
    "Poblacion, Sogod, Southern Leyte",
    "Poblacion, Bontoc, Southern Leyte",
    "Poblacion, Macrohon, Southern Leyte",
    "Poblacion, Malitbog, Southern Leyte",
    "San Vicente, Malitbog, Southern Leyte",
    "Poblacion, Saint Bernard, Southern Leyte",
    "Poblacion, Liloan, Southern Leyte",
    "Poblacion, San Juan, Southern Leyte",
    "Poblacion, Hinunangan, Southern Leyte",
    "Poblacion, Hinundayan, Southern Leyte",
    "Poblacion, Silago, Southern Leyte",
    "Poblacion, Libagon, Southern Leyte",
    "Poblacion, Padre Burgos, Southern Leyte",
    "Poblacion, Tomas Oppus, Southern Leyte",
    "Poblacion, Anahawan, Southern Leyte",
    "Poblacion, Pintuyan, Southern Leyte",
    "Poblacion, San Ricardo, Southern Leyte",
    "Poblacion, San Francisco, Southern Leyte",
    "Poblacion, Limasawa, Southern Leyte",
]
