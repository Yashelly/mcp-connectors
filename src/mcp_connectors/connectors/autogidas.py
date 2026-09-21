from urllib.parse import urlencode, parse_qs, urlsplit

from ..models import CarListing, CarSearch
from ..parsing import clean, text_at, require_title
from .base import Connector, ConnectorInfo, ParsedPage
from .car_parsing import make_model, mileage, parameter_values, price_fields, year


class AutogidasConnector(Connector):
    info = ConnectorInfo("autogidas", "Autogidas", "https://autogidas.lt", "cars", live_status="blocked", last_live_check="2026-09-21")
    listing_pattern = r"/skelbimas/[^/]+-\d+\.html"
    filters = ("query", "price_from", "price_to", "year_from", "year_to")

    def search_url(self, options: CarSearch, page: int):
        params = {"page": page}
        for field, key in (("query", "f_376"), ("price_from", "f_215"), ("price_to", "f_216"),
                           ("year_from", "f_41"), ("year_to", "f_42")):
            value = getattr(options, field)
            if value is not None and value != "":
                params[key] = value
        return self.info.website + "/skelbimai/automobiliai/?" + urlencode(params)

    def parse_search(self, html, url, page):
        soup = self.soup(html)
        items = []
        for node in soup.select("a.item-link"):
            title = require_title(text_at(node, ".item-title"))
            make, model = make_model(title)
            values = [clean(n) for n in node.select("span.parameter-value") if clean(n)]
            location = next((v for v in values if ", " in v and not any(u in v for u in ("kW", "L,"))), None)
            items.append(CarListing(source=self.info.id, url=self.listing_url(node["href"], relative=True),
                title=title, make=make, model=model, year=year(" ".join(values)), location=location,
                **price_fields(text_at(node, ".item-price")), **parameter_values(values)))
        if not items:
            self.empty_or_changed(soup, ("Skelbimų, pagal nustatytus kriterijus, nerasta", "Atsiprašome, ko ieškote neradome"))
        more = any(parse_qs(urlsplit(a["href"]).query).get("page") == [str(page + 1)] for a in soup.select("a.page[href]"))
        return ParsedPage(items, more)

    def parse_listing(self, html, url):
        soup = self.soup(html)
        title = require_title(text_at(soup, "h1.sticky-title"))
        fields = {clean(n): text_at(n.parent, "b") for n in soup.select("i")}
        crumbs = [n for n in soup.select("a.breadcrumb-item") if "/skelbimai/automobiliai/" in n.get("href", "")]
        make = clean(crumbs[1]) if len(crumbs) >= 2 else None
        model = clean(crumbs[2]) if len(crumbs) >= 3 else None
        metadata = {text_at(n, ".list-striped-item-title"): text_at(n, ".list-striped-item-value")
                    for n in soup.select(".list-striped-item-group")}
        return CarListing(source=self.info.id, url=url, title=title, make=make, model=model,
            year=year(fields.get("Metai")), fuel=fields.get("Kuro tipas"), transmission=fields.get("Pavarų dėžė"),
            mileage_km=mileage(fields.get("Rida")), engine=fields.get("Variklis"),
            description=text_at(soup, '.view-description [itemprop="description"]'),
            location=text_at(soup, ".view-location .user-location"), date_posted=metadata.get("Įkeltas"),
            **price_fields(text_at(soup, ".sticky-price strong")))
