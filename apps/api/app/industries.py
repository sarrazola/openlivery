"""Industry catalog for clients.

A client is identified by an industry and a business type within it, both
stored as stable codes. Labels live here in the two UI languages so the web
can render the pickers and the prompt can describe the business in words.
Every industry ends with an "other" type, and "other" is itself an industry,
so no business is forced into a wrong box.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Label:
    en: str
    es: str

    def get(self, lang: str) -> str:
        return self.es if lang == "es" else self.en


@dataclass(frozen=True)
class BusinessType:
    code: str
    label: Label


@dataclass(frozen=True)
class Industry:
    code: str
    label: Label
    types: tuple[BusinessType, ...] = field(default_factory=tuple)


OTHER = "other"


def _t(code: str, en: str, es: str) -> BusinessType:
    return BusinessType(code, Label(en, es))


def _other() -> BusinessType:
    return _t(OTHER, "Other", "Otro")


INDUSTRIES: tuple[Industry, ...] = (
    Industry("restaurants_food", Label("Restaurants & food", "Restaurantes y comida"), (
        _t("restaurant", "Restaurant", "Restaurante"),
        _t("cafe_bakery", "Cafe / Bakery", "Cafetería / Panadería"),
        _t("fast_food", "Fast food", "Comida rápida"),
        _t("food_delivery", "Food delivery / Dark kitchen", "Domicilios / Cocina oculta"),
        _t("catering", "Catering", "Catering"),
        _t("bar_nightlife", "Bar / Nightlife", "Bar / Vida nocturna"),
        _other(),
    )),
    Industry("retail_ecommerce", Label("Retail & e-commerce", "Comercio y e-commerce"), (
        _t("online_store", "Online store", "Tienda online"),
        _t("clothing_fashion", "Clothing / Fashion", "Ropa / Moda"),
        _t("electronics", "Electronics", "Electrónica"),
        _t("home_furniture", "Home / Furniture", "Hogar / Muebles"),
        _t("grocery", "Grocery / Supermarket", "Abarrotes / Supermercado"),
        _t("beauty_products", "Beauty products", "Productos de belleza"),
        _other(),
    )),
    Industry("health_wellness", Label("Health & wellness", "Salud y bienestar"), (
        _t("clinic", "Clinic / Medical practice", "Clínica / Consultorio"),
        _t("dental", "Dental", "Odontología"),
        _t("aesthetic", "Aesthetic medicine", "Medicina estética"),
        _t("pharmacy", "Pharmacy", "Farmacia"),
        _t("veterinary", "Veterinary", "Veterinaria"),
        _t("gym_fitness", "Gym / Fitness", "Gimnasio / Fitness"),
        _t("spa_wellness", "Spa / Wellness", "Spa / Bienestar"),
        _other(),
    )),
    Industry("beauty_personal_care", Label("Beauty & personal care", "Belleza y cuidado personal"), (
        _t("salon", "Hair salon", "Salón de belleza"),
        _t("barbershop", "Barbershop", "Barbería"),
        _t("nails_lashes", "Nails / Lashes", "Uñas / Pestañas"),
        _t("tattoo", "Tattoo / Piercing", "Tatuajes / Piercing"),
        _other(),
    )),
    Industry("real_estate", Label("Real estate", "Inmobiliaria"), (
        _t("agency", "Real estate agency", "Agencia inmobiliaria"),
        _t("developer", "Developer / New builds", "Constructora / Proyectos"),
        _t("property_management", "Property management", "Administración de propiedades"),
        _t("vacation_rentals", "Vacation rentals", "Alquileres vacacionales"),
        _other(),
    )),
    Industry("finance_insurance", Label("Finance & insurance", "Finanzas y seguros"), (
        _t("accounting_tax", "Accounting / Tax", "Contabilidad / Impuestos"),
        _t("financial_advisory", "Financial advisory", "Asesoría financiera"),
        _t("insurance", "Insurance", "Seguros"),
        _t("lending", "Lending / Credit", "Préstamos / Crédito"),
        _t("fintech", "Fintech", "Fintech"),
        _other(),
    )),
    Industry("professional_services", Label("Professional services", "Servicios profesionales"), (
        _t("legal", "Legal", "Legal"),
        _t("marketing_agency", "Marketing / Advertising agency", "Agencia de marketing / Publicidad"),
        _t("consulting", "Consulting", "Consultoría"),
        _t("hr_recruiting", "HR / Recruiting", "Recursos humanos / Selección"),
        _t("architecture_design", "Architecture / Design", "Arquitectura / Diseño"),
        _other(),
    )),
    Industry("education", Label("Education", "Educación"), (
        _t("school", "School", "Colegio"),
        _t("university", "University / Institute", "Universidad / Instituto"),
        _t("online_courses", "Online courses", "Cursos online"),
        _t("language_academy", "Language academy", "Academia de idiomas"),
        _t("tutoring", "Tutoring", "Clases particulares"),
        _other(),
    )),
    Industry("travel_hospitality", Label("Travel & hospitality", "Viajes y hospitalidad"), (
        _t("hotel", "Hotel / Lodging", "Hotel / Alojamiento"),
        _t("travel_agency", "Travel agency", "Agencia de viajes"),
        _t("tours", "Tours / Experiences", "Tours / Experiencias"),
        _t("transport", "Transport", "Transporte"),
        _other(),
    )),
    Industry("automotive", Label("Automotive", "Automotriz"), (
        _t("dealership", "Dealership", "Concesionario"),
        _t("workshop", "Workshop / Repair", "Taller / Reparación"),
        _t("car_rental", "Car rental", "Alquiler de vehículos"),
        _t("parts_accessories", "Parts / Accessories", "Repuestos / Accesorios"),
        _other(),
    )),
    Industry("home_services", Label("Home services", "Servicios para el hogar"), (
        _t("cleaning", "Cleaning", "Limpieza"),
        _t("plumbing_electrical", "Plumbing / Electrical", "Plomería / Electricidad"),
        _t("construction_remodeling", "Construction / Remodeling", "Construcción / Remodelación"),
        _t("moving", "Moving", "Mudanzas"),
        _t("security", "Security", "Seguridad"),
        _other(),
    )),
    Industry("technology_software", Label("Technology & software", "Tecnología y software"), (
        _t("saas", "SaaS", "SaaS"),
        _t("it_services", "IT services", "Servicios de TI"),
        _t("app_startup", "App / Startup", "App / Startup"),
        _t("telecom", "Telecom / Internet", "Telecomunicaciones / Internet"),
        _other(),
    )),
    Industry("events_entertainment", Label("Events & entertainment", "Eventos y entretenimiento"), (
        _t("event_planning", "Event planning", "Organización de eventos"),
        _t("venue", "Venue", "Salón / Lugar de eventos"),
        _t("photography", "Photography / Video", "Fotografía / Video"),
        _t("sports_recreation", "Sports / Recreation", "Deportes / Recreación"),
        _other(),
    )),
    Industry("nonprofit_public", Label("Nonprofit & public sector", "Sin ánimo de lucro y sector público"), (
        _t("nonprofit", "Nonprofit / Foundation", "ONG / Fundación"),
        _t("government", "Government", "Entidad pública"),
        _t("religious", "Religious organization", "Organización religiosa"),
        _other(),
    )),
    Industry(OTHER, Label("Other", "Otra"), (_other(),)),
)

_BY_CODE = {industry.code: industry for industry in INDUSTRIES}


def get_industry(code: str) -> Industry | None:
    return _BY_CODE.get(code)


def get_type(industry_code: str, type_code: str) -> BusinessType | None:
    industry = _BY_CODE.get(industry_code)
    if not industry:
        return None
    return next((item for item in industry.types if item.code == type_code), None)


def validate(industry: str, business_type: str) -> str | None:
    """Return an error message when the pair is not in the catalog.

    Both may be empty (nothing chosen yet). A business type needs its
    industry, and must belong to it.
    """
    if not industry and not business_type:
        return None
    if not industry:
        return "Choose an industry before the business type"
    if industry not in _BY_CODE:
        return "Unknown industry"
    if business_type and get_type(industry, business_type) is None:
        return "That business type does not belong to the chosen industry"
    return None


def describe(industry: str, business_type: str, custom: str = "", lang: str = "es") -> str:
    """Words for the prompt: the business type when known, else the client's
    own words for it, else the industry.

    "other" says nothing useful, so it is skipped at both levels.
    """
    kind = get_type(industry, business_type)
    if kind and kind.code != OTHER:
        return kind.label.get(lang).lower()
    if custom.strip():
        return custom.strip()
    sector = get_industry(industry)
    if sector and sector.code != OTHER:
        return sector.label.get(lang).lower()
    return ""


def catalog() -> list[dict]:
    return [
        {
            "code": industry.code,
            "label": {"en": industry.label.en, "es": industry.label.es},
            "types": [{"code": kind.code, "label": {"en": kind.label.en, "es": kind.label.es}} for kind in industry.types],
        }
        for industry in INDUSTRIES
    ]
